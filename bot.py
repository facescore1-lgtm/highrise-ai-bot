import argparse
import asyncio
import json
import logging
import os
import random
import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from control import ControlApi
from playlist import Playlist
from sources import ResolveError, build_resolver
from sources.base import AudioItem
from streamer.icecast import IcecastStreamer

import aiohttp
from aiohttp import ClientConnectorDNSError, WSMsgType

# --- Highrise WebSocket dayaniklilik yamasi ---------------------------------
# Highrise bazen SDK'nin bekledigi TEXT disinda bir WS mesaj tipi gonderebiliyor
# (orn. tip 257). aiohttp bunu alinca receive_str() bir WSMessageTypeError
# firlatiyor ve bot baglandigi gibi cokuyor; ayrica ana alma dongusunde
# converter.loads(frame.data, ...) cagrisi bilinmeyen tip icin patliyor.
# receive()'i yamayip sadece gecerli tipleri (TEXT/BINARY/CLOSE ...) iletiyoruz;
# bilinmeyen tipleri yok sayip dinlemeye devam ediyoruz. Bu hem metadata okumasini
# (receive_str) hem de ana olay dongusunu korur.
def _patch_highrise_ws():
    orig_receive = aiohttp.ClientWebSocketResponse.receive

    async def _safe_receive(self, timeout=None):
        while True:
            msg = await orig_receive(self, timeout)
            t = msg.type
            if t in (
                WSMsgType.TEXT,
                WSMsgType.BINARY,
                WSMsgType.CLOSE,
                WSMsgType.CLOSED,
                WSMsgType.CLOSING,
            ):
                return msg
            # bilinmeyen/beklenmeyen tip (orn. 257): yok say, dinlemeye devam et
            continue

    aiohttp.ClientWebSocketResponse.receive = _safe_receive


_patch_highrise_ws()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


MAX_SONG_SEC = 450   # bu sureden uzun sarkilar calinmaz ("cok uzun")


# YouTube datacenter IP'lerinde (Render) SABR/PO-token nedeniyle cozulemedigi
# icin otomatik radyo dogrudan Turk internet radyo stream'lerinden beslenir.
DEFAULT_RADIO_STREAMS = [
    {"name": "Power Türk", "url": "https://listen.powerapp.com.tr/powerturk/mpeg/icecast.audio"},
    {"name": "Power Türk Taptaze", "url": "https://listen.powerapp.com.tr/powerturktaptaze/mpeg/icecast.audio"},
    {"name": "Power Pop", "url": "https://listen.powerapp.com.tr/powerpop/mpeg/icecast.audio"},
    {"name": "Power FM", "url": "https://listen.powerapp.com.tr/powerfm/mpeg/icecast.audio"},
    {"name": "Power Love", "url": "https://listen.powerapp.com.tr/powerlove/mpeg/icecast.audio"},
    {"name": "Power Dance", "url": "https://listen.powerapp.com.tr/powerdance/mpeg/icecast.audio"},
]


def build_logger():
    logger = logging.getLogger("radio")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)
        try:
            fh = logging.FileHandler(os.path.join(BASE_DIR, "bot.log"), encoding="utf-8")
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        except OSError:
            pass
    return logger


class RadioBot:
    def __init__(self, config, log=None, config_path=None):
        self.config = config
        self.log = log or logging.getLogger("radio")
        self.resolver = build_resolver(config)
        pl = config.get("playlist", {}) or {}
        self.playlist = Playlist(
            pl.get("file", "playlist.txt"),
            repeat=pl.get("repeat", True),
            shuffle=pl.get("shuffle", False),
        )
        self.random_search = bool(pl.get("random_search", False))
        ry = config.get("radio", {}) or {}
        self.radio_secs = int(ry.get("duration", 480))
        streams = ry.get("streams") or DEFAULT_RADIO_STREAMS
        self._radio_streams = [
            (s.get("name") or "Radyo", s.get("url") or "")
            for s in streams
            if s.get("url")
        ]
        self._radio_idx = 0
        self.streamer = IcecastStreamer(config, self.resolver)
        self._running = False
        self._player_thread = None
        self._pending_advance = False
        self._hold = False
        self._shutdown = threading.Event()
        self._lock = threading.RLock()
        self._titles = {}
        self._requesters = {}
        # istek kuyrugu (kullanici istekleri - calininca silinir)
        self._requests = []
        self._force_url = None
        self._force_title = None
        self._force_requester = None
        self._cur_request = False
        self.on_track_start = None
        self._resolve_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="resolve")
        # banli sarkilar
        self.banned_path = os.path.join(BASE_DIR, "banned.json")
        self._banned = set()
        self._load_banned()
        # config / restart durumu
        self.config_path = config_path or os.path.join(BASE_DIR, "config.json")
        self.restart_state_path = os.path.join(BASE_DIR, "restart_state.json")
        self._ever_connected = False

    def _read_fails(self):
        try:
            with open(self.restart_state_path, "r", encoding="utf-8") as fh:
                return int(json.load(fh).get("fails", 0))
        except Exception:
            return 0

    def _write_fails(self, n):
        try:
            with open(self.restart_state_path, "w", encoding="utf-8") as fh:
                json.dump({"fails": n}, fh)
        except Exception as err:
            self.log.warning("restart durumu yazilamadi: %s", err)

    def _save_config(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as fh:
                json.dump(self.config, fh, ensure_ascii=False, indent=2)
        except Exception as err:
            self.log.warning("config kaydedilemedi: %s", err)

    def save_room_id(self, room_id):
        hr = self.config.setdefault("highrise", {})
        hr["room_id"] = room_id
        self._save_config()

    def mark_room_ok(self):
        self._ever_connected = True
        self._write_fails(0)
        hr = self.config.setdefault("highrise", {})
        rid = hr.get("room_id", "")
        if rid and hr.get("last_good_room_id") != rid:
            hr["last_good_room_id"] = rid
            self._save_config()

    def _load_banned(self):
        try:
            if os.path.exists(self.banned_path):
                with open(self.banned_path, "r", encoding="utf-8") as fh:
                    self._banned = set(json.load(fh))
        except Exception as err:
            self.log.warning("ban listesi yuklenemedi: %s", err)

    def _save_banned(self):
        try:
            with open(self.banned_path, "w", encoding="utf-8") as fh:
                json.dump(sorted(self._banned), fh, ensure_ascii=False, indent=1)
        except Exception as err:
            self.log.warning("ban listesi kaydedilemedi: %s", err)

    def is_banned(self, url):
        return url in self._banned

    def ban_current_text(self):
        cur = self.streamer.current()
        if cur is None:
            return False, "Su an calan sarki yok."
        url = cur.url
        self._banned.add(url)
        self._save_banned()
        with self._lock:
            idx = self.playlist.current_index()
            if 0 <= idx < len(self.playlist.items) and self.playlist.items[idx] == url:
                self.playlist.remove(idx)
        title = cur.title or url
        self.log.info("sarki banlandi: %s", title)
        return True, "Banlandi: %s" % title

    def status(self):
        cur = self.streamer.current()
        idx = self.playlist.current_index()
        return {
            "online": self._running,
            "playing": self._running and not self.streamer.is_paused(),
            "paused": self.streamer.is_paused(),
            "current_index": idx + 1 if idx >= 0 else None,
            "current": {
                "url": cur.url,
                "title": cur.title,
                "source": cur.source,
            } if cur else None,
            "queue_size": len(self._requests),
            "repeat": self.playlist.repeat,
            "shuffle": self.playlist.shuffle,
            "radio_url": self.radio_url(),
        }

    def playlist_items(self):
        out = []
        for i, url in enumerate(self.playlist.items):
            out.append({"index": i + 1, "url": url, "title": self._titles.get(url)})
        return out

    def radio_url(self):
        ice = self.config["icecast"]
        ext = ice.get("url", "").strip()
        if ext:
            return ext
        return "http://%s:%s%s" % (ice.get("host", "127.0.0.1"), ice.get("port", 8000), ice.get("mount", "/stream1"))

    @staticmethod
    def local_ip():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except OSError:
            return "127.0.0.1"

    def start(self):
        with self._lock:
            if self._running:
                return
            self._running = True
        self._player_thread = threading.Thread(target=self._player_loop, daemon=True)
        self._player_thread.start()

    def _make_provider(self):
        first = True

        RANDOM_TR = [
            "Tarkan - Şımarık",
            "Tarkan - Dudu",
            "Tarkan - Kuzu Kuzu",
            "Sezen Aksu - Gülümse",
            "Sezen Aksu - Hükümsüz",
            "Ajda Pekkan - Bambaşka Biri",
            "Ajda Pekkan - Pet'r Oil",
            "Barış Manço - Gülpembe",
            "Barış Manço - Dağlar Dağlar",
            "Cem Karaca - Resimdeki Gözyaşları",
            "Cem Karaca - Namus Belası",
            "Erkin Koray - Çöpçüler",
            "Erkin Koray - Fesuphanallah",
            "Müslüm Gürses - Bir Kadeh Daha",
            "Müslüm Gürses - İtirazım Var",
            "İbrahim Tatlıses - Bebeğim",
            "İbrahim Tatlıses - Sevda Kuşun Kanadında",
            "Hadise - Dum Tek Tek",
            "Hadise - Aşk Kaç Beden Giyer",
            "Sertab Erener - Everyway That I Can",
            "Sertab Erener - Yanan",
            "Duman - Bu Akşam",
            "Duman - Seni Kendime Sakladım",
            "Mor ve Ötesi - Cambaz",
            "Mor ve Ötesi - Bir Derdim Var",
            "Teoman - İki Yabancı",
            "Teoman - Paramparça",
            "Şebnem Ferah - Sigara",
            "Şebnem Ferah - Deli Kız",
            "Kenan Doğulu - Tutamıyorum Zamanı",
            "Kenan Doğulu - Çakkıdı",
            "Mabel Matiz - Kahrettim",
            "Mabel Matiz - Ya Bu İşler Ne",
            "Semicenk - Pişman Değilim",
            "Aleyna Tilki - Sen Olsan Bari",
            "Bengü - Sahici",
            "Ebru Gündeş - Eğer Ağlarsan",
            "Güliz Ayla - Sensiz Olmuyor",
            "Simge - Miş Miş",
            "Yalın - Ben Bugün",
            "Kıvanç - Aşk Yakar",
            "Edis - Çok Çok",
            "Reynmen - Derdim Olsun",
            "Murat Boz - Aşkı Bulamam Ben",
            "Zeynep Bastık - Fırça",
            "Hande Yener - Kırmızı",
            "Hadise - Oyalama Beni",
            "Sıla - Vazgeçmem",
            "Göksel - Depresyondayım",
        ]

        def pick_next():
            """Lock altinda bir sonraki url'i secer. Donus: (url, title_hint, istek_mi, istek_sahibi)"""
            nonlocal first
            if self._force_url is not None:
                url = self._force_url
                self._force_url = None
                hint = self._force_title
                self._force_title = None
                who = self._force_requester
                self._force_requester = None
                return url, hint, True, who
            if self._requests:
                req = self._requests.pop(0)
                return req["url"], req.get("title"), True, req.get("requester")
            if not self.playlist.items or self.random_search:
                # liste yok (veya random_search): dogrudan Turk radyo stream'lerinden
                if self._radio_streams:
                    return self._pick_radio_url(), None, False, "2beatbot"
                return random.choice(RANDOM_TR), None, False, "2beatbot"
            if first:
                first = False
                if self._pending_advance:
                    self._pending_advance = False
                    return self.playlist.advance(), None, False, "2beatbot"
                url = self.playlist.current()
                if url is None:
                    url = self.playlist.first()
                return url, None, False, "2beatbot"
            if self._hold:
                self._hold = False
                url = self.playlist.current()
                if url is None:
                    url = self.playlist.advance()
                return url, None, False, "2beatbot"
            return self.playlist.advance(), None, False, "2beatbot"

        def provider():
            banned_streak = 0
            long_streak = 0
            if self.random_search or not self.playlist.items:
                # rastgele arama modu: atlamalarda radyo asla durmasin
                limit = 10 ** 9
            else:
                limit = len(self.playlist.items) + len(self._requests) + 2
            while self._running:
                with self._lock:
                    url, hint, is_req, requester = pick_next()
                    self._cur_request = is_req
                if url is None:
                    return None
                if url in self._banned:
                    banned_streak += 1
                    if banned_streak > limit:
                        self.log.warning("tum sarkilar banli, radyo duruyor")
                        return None
                    continue
                banned_streak = 0
                if url.startswith("radio:"):
                    name, _, surl = url[6:].partition("|")
                    item = AudioItem(
                        url=url,
                        title=name or "Radyo",
                        stream_url=surl,
                        source="radio",
                        duration=self.radio_secs,
                    )
                    item.is_radio = True
                    item.stream_resolved = True
                    item.stream_url_ts = time.time()
                elif url.startswith("clip:"):
                    item = AudioItem(
                        url=url,
                        title=hint or "Ses mesaji",
                        stream_url=url[5:],
                        source="clip",
                        duration=0,
                    )
                    item.stream_resolved = True
                    item.stream_url_ts = time.time()
                else:
                    item = self._resolve_with_timeout(url, timeout=30)
                if item is None:
                    if self.random_search or not self.playlist.items:
                        # rastgele mod: cozulemeyen sarki atlanir, hemen yenisi denenir
                        continue
                    if is_req:
                        # istek baslamadi; kuyrugun onune geri koy, normal akis surer
                        with self._lock:
                            self._requests.insert(0, {"url": url, "title": hint, "requester": ""})
                    continue
                if not getattr(item, "is_radio", False):
                    item.stream_resolved = True
                    item.stream_url_ts = time.time()
                    if getattr(item, "duration", 0) and item.duration > MAX_SONG_SEC:
                        self.log.warning(
                            "cok uzun sarki atlandi (%ds): %s", item.duration, item.title
                        )
                        long_streak += 1
                        if long_streak > limit:
                            self.log.warning("tum sarkilar 6 dk uzeri, radyo duruyor")
                            return None
                        continue
                    long_streak = 0
                item.requester = requester or ""
                self._titles[url] = item.title
                self.log.info("caliniyor: %s", item.title)
                if self.on_track_start:
                    try:
                        self.on_track_start(item.title, requester or "2beatbot", item.duration)
                    except Exception as err:
                        self.log.debug("track duyurusu hata: %s", err)
                return item
            return None

        return provider

    def _resolve_with_timeout(self, url, timeout=15.0):
        fut = self._resolve_pool.submit(self.resolver.resolve, url)
        try:
            return fut.result(timeout=timeout)
        except Exception as err:
            self.log.warning("URL cozulemedi (%.0fs): %s (%s)", timeout, url, err)
            return None

    def _pick_radio_url(self):
        name, surl = self._radio_streams[self._radio_idx % len(self._radio_streams)]
        self._radio_idx += 1
        return "radio:%s|%s" % (name, surl)

    def _player_loop(self):
        try:
            self.streamer.run_radio(self._make_provider())
        finally:
            with self._lock:
                self._running = False

    def cmd_play(self):
        with self._lock:
            running = self._running
        if running:
            if self.streamer.is_paused():
                self.streamer.resume()
            return {"ok": True, "playing": True}
        self.start()
        return {"ok": True, "playing": True}

    def cmd_stop(self):
        with self._lock:
            self._running = False
        self.streamer.stop()
        return {"ok": True, "playing": False}

    def cmd_pause(self):
        if self._running:
            self.streamer.pause()
            return {"ok": True, "paused": True}
        return {"ok": False, "error": "bot calismiyor"}

    def cmd_resume(self):
        if self._running:
            self.streamer.resume()
            return {"ok": True, "paused": False}
        self.start()
        return {"ok": True, "paused": False}

    def cmd_next(self):
        with self._lock:
            running = self._running
            self._pending_advance = True
        if running:
            self.streamer.skip()
        else:
            self.start()
        return {"ok": True}

    def cmd_goto(self, pos):
        with self._lock:
            ok = self.playlist.goto(pos - 1)
            running = self._running
        if not ok:
            return {"ok": False, "error": "gecersiz sira numarasi"}
        if running:
            self._hold = True
            self.streamer.skip()
        else:
            self._hold = True
            self.start()
        return {"ok": True, "index": pos}

    def cmd_add(self, url):
        with self._lock:
            index = self.playlist.add(url)
        if index < 0:
            return {"ok": False, "error": "url gerekli"}
        self.log.info("kuyruga eklendi [%d]: %s", index + 1, url)
        return {"ok": True, "index": index + 1}

    def cmd_remove(self, pos):
        with self._lock:
            ok = self.playlist.remove(pos - 1)
        return {"ok": ok}

    def cmd_clear(self):
        with self._lock:
            self.playlist.clear()
        return {"ok": True, "queue_size": 0}

    def cmd_shuffle(self, on):
        with self._lock:
            self.playlist.set_shuffle(on)
        return {"ok": True, "shuffle": on}

    def cmd_reload(self):
        with self._lock:
            self.playlist.reload()
        return {"ok": True, "queue_size": len(self.playlist.items)}

    def _pending_requester_count(self, username):
        if not username:
            return 0
        with self._lock:
            count = 0
            for req in self._requests:
                owner = req.get("requester", "")
                if owner and owner.lower() == username.lower():
                    count += 1
        return count

    def bump_up_text(self, username):
        with self._lock:
            pos = None
            for i, req in enumerate(self._requests):
                owner = req.get("requester", "")
                if owner and owner.lower() == (username or "").lower():
                    pos = i
                    break
            if pos is None:
                return False, "Kuyrukta senin sarkin yok."
            if pos == 0:
                return False, "Sarki zaten bir sonraki sırada."
            self._requests[pos - 1], self._requests[pos] = self._requests[pos], self._requests[pos - 1]
            title = self._requests[pos - 1].get("title") or "sarkin"
            return True, "Sarkin bir sıra öne alindi (#%d): %s" % (pos, title)

    def play_clip(self, path, title, requester=""):
        path = os.path.abspath(path)
        if not os.path.exists(path):
            return False, "Ses dosyasi bulunamadi: %s" % path
        with self._lock:
            running = self._running
        if running and self.streamer.request_overlay(path):
            return True, ""
        url = "clip:" + path
        with self._lock:
            interrupt = running and not self._cur_request and self._force_url is None
            if interrupt:
                self._force_url = url
                self._force_title = title
                self._force_requester = requester
            else:
                self._requests.append({"url": url, "title": title, "requester": requester})
                pos = len(self._requests)
        if interrupt:
            self.streamer.skip()
            return True, ""
        if not running:
            self.start()
            return True, ""
        return True, "Kuyruga eklendi (#%d): %s" % (pos, title)

    def remove_last_request(self, requester):
        with self._lock:
            for i in range(len(self._requests) - 1, -1, -1):
                req = self._requests[i]
                if (req.get("requester") or "") == requester:
                    removed = self._requests.pop(i)
                    self.log.info("istek cikarildi (%s): %s", requester, removed.get("title"))
                    return removed.get("title") or "?"
        return None

    def current_item(self):
        return self.streamer.current()

    def request_song_text(self, query, requester=""):
        text = (query or "").strip()
        if not text:
            return "Kullanim: -p <sarki adi veya link>"
        if requester and self._pending_requester_count(requester) >= 1:
            return "@%s kuyrukta zaten bir şarkın var. Sırasını yükseltmek için: -up" % requester
        try:
            item = self.resolver.resolve(text)
        except ResolveError as err:
            self.log.warning("istek cozulemedi (%s): %s", requester, err)
            return "Sarki bulunamadi: %s" % str(err)[:160]
        if getattr(item, "duration", 0) and item.duration > MAX_SONG_SEC:
            m, s = divmod(int(item.duration), 60)
            return (
                "@%s bu cok uzun! ⏳ (%d:%02d) En fazla %g dakikalik sarki isteyebilirsin."
                % (requester or "?", m, s, MAX_SONG_SEC / 60)
            )
        item.stream_resolved = True
        item.stream_url_ts = time.time()
        url = item.url
        if url in self._banned:
            return "Bu sarki banli listesinde: %s" % (item.title or "")
        self._titles[url] = item.title
        self.log.info("istek %s: %s", requester or "-", item.title)
        with self._lock:
            running = self._running
            interrupt = running and not self._cur_request and self._force_url is None
            if interrupt:
                self._force_url = url
                self._force_title = item.title
                self._force_requester = requester
            else:
                self._requests.append({"url": url, "title": item.title, "requester": requester})
                pos = len(self._requests)
        if interrupt:
            self.streamer.skip()
            return ""
        if not running:
            self.start()
            return ""
        return "Kuyruga eklendi (#%d): %s" % (pos, item.title)

    def queue_text(self):
        lines = []
        with self._lock:
            if self._cur_request:
                cur = self.streamer.current()
                if cur and cur.title:
                    lines.append("Simdi: %s" % cur.title)
            for i, req in enumerate(self._requests):
                lines.append("%d. %s" % (i + 1, req.get("title") or req["url"]))
        return "\n".join(lines) if lines else "Kuyruk bos (istek icin: -p <sarki>)."

    def playlist_text(self):
        lines = []
        with self._lock:
            for i, url in enumerate(self.playlist.items):
                title = self._titles.get(url)
                lines.append("%d. %s" % (i + 1, title or url))
        return "\n".join(lines) if lines else "Otomatik liste bos."

    def skip_text(self):
        result = self.cmd_next()
        return "Sonraki sarkiya geciliyor." if result.get("ok") else "Aktarilamadi."

    def now_text(self):
        cur = self.streamer.current()
        if cur and cur.title:
            return "Simdi caliyor: %s" % cur.title
        return "Su an sarki calmıyor."

    def start_room(self, room_id, api_token):
        from highrise.__main__ import BotDefinition, main

        from room_bot import RadioRoomBot

        def runner():
            nonlocal room_id
            fails = 0
            backoff = 5
            while True:
                self._ever_connected = False
                try:
                    asyncio.run(
                        main([BotDefinition(RadioRoomBot(self), room_id, api_token)])
                    )
                except KeyboardInterrupt:
                    return
                except (ClientConnectorDNSError, OSError) as err:
                    # DNS cozumlenemedi (gaierror) veya ag anlik koptu.
                    # Daha uzun, ustel artan bekleme ile yeniden dene.
                    fails += 1
                    wait = min(backoff * 2, 30)
                    self.log.warning(
                        "AG/DNS HATASI (%d): %r -> %ds sonra yeniden denenecek",
                        fails, err, wait,
                    )
                    backoff = wait
                    time.sleep(wait)
                    continue
                except BaseException as err:
                    # CancelledError / WSMessageTypeError / diger her sey:
                    # oturum kapandi, asagi inip yeniden baslat.
                    self.log.error("oda oturumu sonlandi: %r", err)
                # main() ya temiz cikti ya da hata verdi -> baglanti bitti
                if self._ever_connected:
                    fails = 0
                    backoff = 5
                    self.log.info("baglanti koptu, 5 sn sonra yeniden baglaniliyor")
                else:
                    fails += 1
                    self.log.warning("odaya baglanilamadi (%d/3)", fails)
                    if fails >= 3:
                        hr = self.config.get("highrise", {}) or {}
                        good = hr.get("last_good_room_id", "")
                        cur = hr.get("room_id", "")
                        if good and cur and good != cur:
                            self.log.warning("eski odaya donuluyor: %s", good)
                            self.save_room_id(good)
                            room_id = good
                        fails = 0
                time.sleep(backoff)

        threading.Thread(target=runner, daemon=True, name="room").start()

    def cmd_quit(self):
        with self._lock:
            self._running = False
        self.streamer.stop()
        self._shutdown.set()
        return {"ok": True}

    def interactive(self):
        for raw in sys.stdin:
            line = raw.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            command = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else None
            try:
                self._dispatch(command, arg)
            except Exception as err:
                self.log.error("komut hatasi: %s", err)
            if command == "quit":
                break

    def _dispatch(self, command, arg):
        if command == "play":
            print(self.cmd_play())
        elif command == "stop":
            print(self.cmd_stop())
        elif command == "next":
            print(self.cmd_next())
        elif command == "pause":
            print(self.cmd_pause())
        elif command == "resume":
            print(self.cmd_resume())
        elif command == "add":
            if not arg:
                print({"ok": False, "error": "url gerekli"})
            else:
                print(self.cmd_add(arg))
        elif command in ("goto", "jump"):
            print(self._int_command(arg, self.cmd_goto))
        elif command == "remove":
            print(self._int_command(arg, self.cmd_remove))
        elif command == "clear":
            print(self.cmd_clear())
        elif command == "list":
            for row in self.playlist_items():
                print("%d\t%s\t%s" % (row["index"], row["url"], row["title"] or ""))
        elif command == "status":
            print(json.dumps(self.status(), ensure_ascii=False, indent=2))
        elif command == "shuffle":
            print(self.cmd_shuffle((arg or "on").lower() in ("1", "true", "on")))
        elif command == "reload":
            print(self.cmd_reload())
        elif command == "help":
            print("komutlar: play stop next pause resume add <url> goto <n> remove <n> list status shuffle [on|off] reload quit")
        elif command == "quit":
            print(self.cmd_quit())
        else:
            print("bilinmeyen komut: %s (help yaz)" % command)

    def _int_command(self, arg, fn):
        if arg and arg.lstrip("-").isdigit():
            return fn(int(arg))
        return {"ok": False, "error": "giris numarasi lazim"}


def main():
    parser = argparse.ArgumentParser(description="Highrise radio bot")
    parser.add_argument("--config", default=os.path.join(BASE_DIR, "config.json"))
    parser.add_argument("--no-http", action="store_true")
    args = parser.parse_args()

    log = build_logger()
    with open(args.config, "r", encoding="utf-8") as fh:
        config = json.load(fh)

    bot = RadioBot(config, log=log, config_path=args.config)
    ctrl = None
    ctrl_cfg = config.get("control", {}) or {}
    if not args.no_http and ctrl_cfg.get("http", True):
        ctrl = ControlApi(bot, ctrl_cfg.get("host", "0.0.0.0"), int(ctrl_cfg.get("port", 8090)))
        ctrl.start()
        log.info("http kontrol: http://%s:%s", bot.local_ip(), ctrl_cfg.get("port", 8090))
    log.info("Radyo URL (Highrise radyosuna yaz): %s", bot.radio_url())
    log.info("komutlar: play | stop | next | pause | resume | add <url> | goto <n> | list | status | quit")

    hr = config.get("highrise", {}) or {}
    room_id = os.environ.get("ROOM_ID") or hr.get("room_id", "")
    api_token = os.environ.get("API_TOKEN") or hr.get("api_token", "")
    fails = bot._read_fails()
    good = hr.get("last_good_room_id", "")
    if room_id and fails >= 3 and good and good != room_id:
        log.warning("oda %d kez acilamadi, son calisan odaya donuluyor: %s", fails, good)
        bot.save_room_id(good)
        bot._write_fails(0)
        room_id = good
    elif room_id:
        bot._write_fails(fails + 1)
    if room_id and api_token:
        try:
            bot.start_room(room_id, api_token)
            log.info("oda botu basliyor (oda: %s)", room_id)
        except Exception as err:
            log.warning("oda botu baslatilamadi (%s) - yuklemek icin: pip install highrise-bot-sdk", err)
    else:
        log.info("highrise baglantisi yok (config.json: highrise.room_id / api_token)")

    threading.Thread(target=bot.interactive, daemon=True).start()
    bot.start()

    try:
        while not bot._shutdown.is_set():
            time.sleep(0.5)
    finally:
        bot.cmd_quit()
        if bot._player_thread:
            bot._player_thread.join(timeout=5)
        if ctrl:
            ctrl.stop()


if __name__ == "__main__":
    main()