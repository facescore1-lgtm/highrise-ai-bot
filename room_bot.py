import asyncio
import json
import logging
import os
import random
import re
import requests
import sys
import time
import unicodedata

from functools import partial

from highrise import BaseBot
from highrise.models import Error, ModerateRoomRequest, Position

from kelimeler import get_random_category, get_category_color, get_random_word
from emotes import find_emote, search_emotes, emote_count

log = logging.getLogger("radio.room")

PREFIX = "-"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BJ_MIN_BET = 10
BJ_MAX_BET = 100000
BJ_BLACKJACK_PAYOUT = 2.5   # dogal 21 -> bahsin 2.5 kati
BJ_IDLE_TIMEOUT = 300       # sn hareketsizlik -> bahis iade

DAILY_REWARD = 50           # -daily gunluk odul

VIP_DURATION = 86400        # 1 gun
# plan: anahtar -> (etiket, gun sayisi, puan fiyati)
VIP_PLANS = {
    "10": ("10 gun", 10, 1500),
    "20": ("20 gun", 20, 3000),
    "120": ("120 gun", 120, 18000),
    "200": ("200 gun", 200, 30000),
    "350": ("350 gun", 350, 52500),
}

ROLE_LEVELS = {"vip": 1, "admin": 2, "yonetici": 3, "kurucu": 4}
ROLE_LABELS = {"vip": "VIP", "admin": "Admin", "yonetici": "Yönetici", "kurucu": "Kurucu"}

HELP_TEXT = (
    "🎵 **KOMUTLAR**\n"
    "-p <sarki> → sarki iste | -myskip → kendi sarkini gec\n"
    "-q → kuyruk | -now → calan | -list → otomatik liste\n"
    "-up → sirani bir one al (100 puan)\n"
    "-puan → puanin | -top → siralama | -daily → gunluk 50 puan\n"
    "-gift @isim <puan> → puan hediye et\n"
    "-bj <miktar> → blackjack\n"
    "-emote <ad/numara> → emote yap ('stop' durdurur)\n"
    "-kat1 / -kat2 → kata isinlan\n"
    "-favekle <sarki> | -favoriler | -favori <no>\n"
    "-rep @kisi <sebep> → sikayet | -good @kisi → takdir\n"
    "-role → roller | -online → odadakiler\n"
    "-puanal → VIP al (puan veya gold)\n"
    "Kelime oyunu: dogru cevap +10 puan!\n"
    "Rol komutlari: -helpvip / -helpadmin / -helpyonetici / -helpkurucu"
)

HELP_SECTIONS = {
    "vip": (
        "👑 **VIP KOMUTLARI**",
        "-vip → VIP alanina isinlan\n"
        "-tp @isim → o kisinin yanina isinlan | -tp 9.5 0.25 12.5 → o koordinata isinlan\n"
        "-bemote <emote> → bota emote yaptir | -bemstop → durdur\n"
        "-double @kisi <emote> → o kisiyle birlikte emote yapin\n"
        "VIP almak icin: -puanal",
    ),
    "admin": (
        "🛡 **ADMIN KOMUTLARI**",
        "-gec → direkt sarkiyi gec\n"
        "-del → calan sarkiyi banla\n"
        "-summ @isim → yanina cek\n"
        "-summ @isim x y z | kat1 | kat2 | vip → o noktaya gonder\n"
        "-emoteall <emote> → odadaki herkese emote yaptir\n"
        "-kick @isim → odadan at\n"
        "-ban @isim → banla | -unban @isim → bandi ac\n"
        "-mute @isim → sustur | -unmute @isim → konustur",
    ),
    "yonetici": (
        "⚙️ **YONETICI KOMUTLARI** (admin komutlari dahil)",
        "-bot <x> <y> <z> → botun ev koordinatini ayarla",
    ),
    "kurucu": (
        "👑 **KURUCU KOMUTLARI** (hepsi dahil)",
        "-sil @kisi <puan> → puan sil\n"
        "-give @nick <rol> → rol ver (vip/admin/yonetici)\n"
        "-roledel @nick → kisinin rolunu al\n"
        "-wallet → botun cuzdani | -tip @kisi <miktar> → gold gonder\n"
        "-kapat / -ac → kelime oyununu kalici kapat/ac\n"
        "-repler → sikayet listesi\n"
        "-oda → kayitli odalari listele | -oda <num> → o numarali odaya gec\n"
        "-degis <id> → odayi degistir (DM)\n"
        "-oda-ad <num> <ad> → kayitli odaya ad ver (DM)\n"
        "-say <mesaj> → sesli anons yap\n"
        "-copy @kullanici → kombini bota giydir\n"
        "-gel → botu yanina cagir",
    ),
}


def _bj_deal():
    """Baslangic dagitimi, -art ve krupiye: 2-11."""
    return random.randint(2, 11)


def _bj_low():
    """-az: 1-10."""
    return random.randint(1, 10)


def _bj_high():
    """-cok: 10-21."""
    return random.randint(10, 21)


class RadioRoomBot(BaseBot):
    def __init__(self, radio):
        super().__init__()
        self.radio = radio
        hr = radio.config.get("highrise", {}) or {}
        self.owner_username = (hr.get("owner_username") or "Slyshader_").lower()
        # VIP gold odemelerinin yapildigi bahsis kavanozu kullanicisi
        self.pay_to = (hr.get("pay_to") or "").lower()
        pos = hr.get("positions", {}) or {}
        k2 = pos.get("kat2", [7.0, 5.5, 12.0])
        vp = pos.get("vip", [11.0, 11.0, 11.0])
        # botun her acilista canlandigi varsayilan nokta (-bot ile degistirilir,
        # bot_home.json varsa o gecerli olur)
        self.home_position = Position(9.5, 0.25, 12.510000228882, "Front")
        self.kat2_position = Position(k2[0], k2[1], k2[2])
        self.vip_position = Position(vp[0], vp[1], vp[2])
        self.bot_id = None
        self.room_user_cache = []
        self.following_user_id = None
        self._last_move = {}
        self._left_ts = {}
        # Freeze mekanizmasi: user_id -> dondugu (baslangic) konum
        self.frozen = {}
        self.skip_votes = {}
        self.room_id = (radio.config.get("highrise", {}) or {}).get("room_id", "")
        # kelime oyunu durumu
        self.current_word = ""
        self.game_active = False
        self.game_paused = False
        self.revealed_letters = []
        self.letter_task = None
        self.ask_task = None
        self.settings_path = os.path.join(BASE_DIR, "settings.json")
        self.word_game_enabled = bool(
            self._read_json(self.settings_path, {}).get("word_game", True)
        )
        # emote loop durumu (user_id -> asyncio.Task)
        self.emote_loops = {}
        self.emote_pairs = {}  # double icin: user_id -> partner_id
        self._emote_resolved = {}
        self._seen_emotes = {}
        self.bot_emote_path = os.path.join(BASE_DIR, "bot_emote.json")
        self.bot_emote = {}  # {name/code/id (whichever find returns)} kalici bos emote
        self.roles = {}
        self.roles_path = os.path.join(BASE_DIR, "roles.json")
        self.scores = {}
        self.scores_path = os.path.join(BASE_DIR, "scores.json")
        self.nova_pending_path = os.path.join(BASE_DIR, "nova_pending.json")
        self.bj_games = {}
        self.home_path = os.path.join(BASE_DIR, "bot_home.json")
        self.favorites = {}
        self.favorites_path = os.path.join(BASE_DIR, "favorites.json")
        self.reports = {}
        self.reports_path = os.path.join(BASE_DIR, "reports.json")
        self.goods = {}
        self.goods_path = os.path.join(BASE_DIR, "goods.json")
        self.vip_path = os.path.join(BASE_DIR, "vip.json")
        self.gold_path = os.path.join(BASE_DIR, "vip_gold.json")
        self._load_roles()
        self._load_scores()
        self._load_home()
        self.favorites = self._read_json(self.favorites_path, {})
        self.reports = self._read_json(self.reports_path, {})
        self.goods = self._read_json(self.goods_path, {})
        self.vip_until = self._read_json(self.vip_path, {})
        self.vip_gold = self._read_json(self.gold_path, {})
        self.bot_emote = self._read_json(self.bot_emote_path, {})
        # DM abonelik sistemi: user_id -> {user_id, ...}. Yeni DM = abone.
        self.subscribers_path = os.path.join(BASE_DIR, "subscribers.json")
        self.subscribers = self._read_json(self.subscribers_path, {})
        # Kalici chat loop (-loop): restart'ta da devam eder, -loopstop ile durur.
        self.chat_loop_path = os.path.join(BASE_DIR, "loop.json")
        self.chat_loop_data = self._read_json(self.chat_loop_path, {})
        self.chat_loop_task = None
        self.chat_loop_msg = self.chat_loop_data.get("msg") or None
        self.chat_loop_sec = int(self.chat_loop_data.get("sec") or 0)

    def _read_json(self, path, default):
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as fh:
                    return json.load(fh) or default
        except Exception as err:
            log.warning("%s yuklenemedi: %s", os.path.basename(path), err)
        return default

    def _write_json(self, path, data):
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=1)
        except Exception as err:
            log.warning("%s kaydedilemedi: %s", os.path.basename(path), err)

    # ---------- kalicilik ----------

    def _load_roles(self):
        try:
            if os.path.exists(self.roles_path):
                with open(self.roles_path, "r", encoding="utf-8") as fh:
                    self.roles = json.load(fh)
        except Exception as err:
            log.warning("roller yuklenemedi: %s", err)
        if self.owner_username:
            self.roles[self.owner_username] = "kurucu"

    def _save_roles(self):
        try:
            with open(self.roles_path, "w", encoding="utf-8") as fh:
                json.dump(self.roles, fh, ensure_ascii=False, indent=2)
        except Exception as err:
            log.warning("roller kaydedilemedi: %s", err)

    def _load_scores(self):
        try:
            if os.path.exists(self.scores_path):
                with open(self.scores_path, "r", encoding="utf-8") as fh:
                    self.scores = dict(json.load(fh))
        except Exception as err:
            log.warning("puanlar yuklenemedi: %s", err)

    def _save_scores(self):
        try:
            with open(self.scores_path, "w", encoding="utf-8") as fh:
                json.dump(self.scores, fh, ensure_ascii=False)
        except Exception as err:
            log.warning("puanlar kaydedilemedi: %s", err)

    def _consume_nova_pending(self):
        """Nova botunun puan harcama taleplerini uygular (tek dosya - tek yazici)."""
        try:
            if not os.path.exists(self.nova_pending_path):
                return
            with open(self.nova_pending_path, "r", encoding="utf-8") as fh:
                items = json.load(fh)
            try:
                os.remove(self.nova_pending_path)
            except OSError:
                with open(self.nova_pending_path, "w", encoding="utf-8") as fh:
                    fh.write("[]")
            if not isinstance(items, list):
                return
            for it in items:
                try:
                    uid = str(it.get("id", "")).strip()
                    amount = int(it.get("amount", 0))
                    if not uid or amount <= 0:
                        continue
                    self._add_score(uid, it.get("username", uid), -amount)
                    log.info("[puan] nova harcamasi: %s -%d", it.get("username", uid), amount)
                except Exception as err:
                    log.warning("[puan] nova talebi uygulanamadi: %s", err)
        except FileNotFoundError:
            pass
        except Exception as err:
            log.warning("[puan] nova talepleri okunamadi: %s", err)

    async def _nova_pending_loop(self):
        while True:
            try:
                self._consume_nova_pending()
            except Exception as err:
                log.debug("nova pending: %s", err)
            await asyncio.sleep(5)

    def _load_home(self):
        try:
            if os.path.exists(self.home_path):
                with open(self.home_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self.home_position = Position(
                    data["x"], data["y"], data["z"], data.get("facing", "FrontRight")
                )
        except Exception as err:
            log.warning("ev koordinati yuklenemedi: %s", err)

    def _save_home(self, pos=None):
        p = pos or self.home_position
        try:
            with open(self.home_path, "w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "x": p.x,
                        "y": p.y,
                        "z": p.z,
                        "facing": getattr(p, "facing", None) or "FrontRight",
                    },
                    fh,
                    ensure_ascii=False,
                )
        except Exception as err:
            log.warning("ev koordinati kaydedilemedi: %s", err)

    # ---------- yetki / kullanici ----------

    def _role_level(self, username):
        rol = self.roles.get((username or "").lower(), "")
        return ROLE_LEVELS.get(rol, 0)

    def _is_owner_cmd(self, user_id, username):
        if self.bot_id and user_id == self.bot_id:
            return False
        if username and username.lower() == self.owner_username:
            return True
        return self._role_level(username) >= 4

    def _is_baba(self, user_id, username):
        return bool(username) and username.lower() == self.owner_username

    def _find_user(self, arg):
        q = (arg or "").strip().lstrip("@").lower()
        if not q:
            return None
        for user, _pos in self.room_user_cache:
            if user.username and user.username.lower() == q:
                return user
        for user, _pos in self.room_user_cache:
            if user.username and user.username.lower().startswith(q):
                return user
        return None

    async def _refresh_room_users(self):
        try:
            resp = await self.highrise.get_room_users()
            if isinstance(resp, Error):
                self.room_user_cache = []
                return
            self.room_user_cache = resp.content
        except Exception as err:
            log.debug("oda listesi alinamadi: %s", err)
            self.room_user_cache = []

    def _add_score(self, user_id, username, points):
        data = self.scores.get(user_id, {"username": username, "score": 0, "id": user_id})
        data["score"] += points
        data["username"] = username
        self.scores[user_id] = data
        self._save_scores()

    # ---------- olaylar ----------

    async def on_start(self, session_metadata):
        try:
            self.bot_id = session_metadata.user_id
            log.info("odaya baglandi (bot id: %s)", self.bot_id)
            try:
                self._save_room_pass(self._current_room_id())
            except Exception as err:
                log.debug("oda gecis kaydi: %s", err)
            # NOT: baglantinin hemen ardindan gereksiz chat/teleport istegi atmioruz;
            # sunucu ilk isteklerde rate-limit/timeout verip baglantisiyi dusurebiliyor.
            try:
                await self._refresh_room_users()
            except Exception as err:
                log.debug("oda listesi alinamadi (on_start): %s", err)
            self._loop = asyncio.get_running_loop()
            self.radio.on_track_start = self._make_track_announcer()
            try:
                self.radio.mark_room_ok()
            except Exception as err:
                log.debug("mark_room_ok hatasi: %s", err)
            # Kelime oyunu SUKUNET icin simdilik otomatik BASLATILMIYOR.
            # (Her 10sn chat atmasi sunucu rate-limit -> reconnect nedeni olabilirdi.)
            # Istersen odadayken ac: -kelimeac  (veya kelime oyunu komutu)
            self.bj_sweeper = asyncio.create_task(self._bj_sweeper())
            self.home_return_task = asyncio.create_task(self._home_return_loop())
            self.vip_sweeper = asyncio.create_task(self._vip_sweeper())
            self.nova_pending_task = asyncio.create_task(self._nova_pending_loop())
            self.req_cleanup_task = asyncio.create_task(self._req_cleanup_loop())
            # NOT: _ws_watchdog (her 20sn get_room_users) KALDIRILDI (reconnect
            # kaynagiydi). Kalici emote (bot_emote.json - bemote) baglanti
            # oturduktan sonra (5sn) 5 sn gecikmeyle geri yuklenir. Kelime oyunu
            # ise otomatik baslamaz, -ac komutuyla baslar.
            asyncio.create_task(self._restore_bot_emote_later())
            # Kalici chat loop varsa (loop.json) oda bossa bile devam ettir.
            if self.chat_loop_msg and self.chat_loop_sec:
                self._start_chat_loop(self.chat_loop_msg, self.chat_loop_sec)
                log.info("kayitli chat loop yeniden baslatildi (%ds)",
                         self.chat_loop_sec)
        except Exception as err:
            log.error("on_start hata (yutuldu, reconnect onleniyor): %s", err)

    async def _home_return_loop(self):
        """Bot sabit konumunda degilse 90sn'de bir teleport ile geri doner."""
        while True:
            try:
                await asyncio.sleep(90)
                pos = self._last_move.get(self.bot_id)
                if isinstance(pos, Position):
                    if (
                        abs(pos.x - self.home_position.x) < 0.4
                        and abs(pos.z - self.home_position.z) < 0.4
                        and abs(pos.y - self.home_position.y) < 0.5
                    ):
                        continue
                try:
                    await self.highrise.teleport(self.bot_id, self.home_position)
                    log.info("bot sabit konumuna teleport edildi")
                except Exception as err:
                    log.debug("teleport hatasi: %s", err)
            except asyncio.CancelledError:
                return
            except Exception as err:
                log.debug("home return loop hatasi: %s", err)

    async def _req_cleanup_loop(self):
        """-p ile sarki isteyen kisi odadan ayrildiysa ve 5dk icinde donmediyse
        istegi/isteklerini kuyruktan kaldirir."""
        while True:
            try:
                await asyncio.sleep(60)
                reqs = getattr(getattr(self, "radio", None), "_requests", None)
                if reqs is None:
                    continue
                names = set()
                for u, _p in self.room_user_cache:
                    if u.username:
                        names.add(u.username.lower())
                now = time.time()
                kalan = []
                degisti = False
                with self.radio._lock:
                    for r in reqs:
                        who = (r.get("requester") or "").lower()
                        ts = self._left_ts.get(who)
                        if ts and (now - ts) >= 300 and who not in names:
                            degisti = True
                            log.info("istek sahibi 5dk donmedi, istek kaldirildi: %s", who)
                            continue
                        kalan.append(r)
                    if degisti:
                        reqs[:] = kalan
            except asyncio.CancelledError:
                return
            except Exception as err:
                log.debug("istek temizlik loop hatasi: %s", err)

    async def _ws_watchdog(self):
        """Baglanti canliligini izler. NOT: get_room_users probe'unu KALDIRDIK;
        her 20sn'da bir get_room_users istegi sunucuya fazladan yuk bindirip
        rate-limit/timeout -> reconnect dongusune yol acabiliyordu. SDK zaten kendi
        keepalive/reconnect'ini yapiyor, bu gorev sadece bosta bekler."""
        while True:
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                return

    def _teardown_session(self):
        """Aktif event loop'taki tum gorevleri iptal eder; asyncio.run sonlanir,
        bot.py'deki runner dongusu temiz sekilde yeniden baglanir."""
        loop = getattr(self, "_loop", None)
        if loop is None or loop.is_closed():
            return
        try:
            tasks = [t for t in asyncio.all_tasks(loop) if not t.done()]
            for t in tasks:
                t.cancel()
            log.info("oturum kapatildi (%d gorev iptal), 5 sn icinde yeniden baglaniliyor", len(tasks))
        except Exception as err:
            log.debug("oturum kapatma hatasi: %s", err)

    async def on_user_join(self, user, position):
        try:
            try:
                await self._refresh_room_users()
            except Exception as err:
                log.debug("oda listesi alinamadi (join): %s", err)
            uname = (getattr(user, "username", "") or "").lower()
            if uname:
                self._left_ts.pop(uname, None)
            # NOT: karsilama whisper'i kaldirildi. Bot reconnect oldugunda odadaki
            # HERKES icin on_user_join tetiklenir; hepsine aninda whisper atmak
            # Highrise rate-limit -> 'timeout' hatasi -> bot duser -> reconnect
            # dongusu yaratiyordu. Hos geldin mesaji sadece on_start'ta bir kez.
        except Exception as err:
            log.error("on_user_join hata (yutuldu): %s", err)

    async def _baba_welcome(self, user):
        log.debug("baba karsilamasi kaldi (owner normal kullanici gibi)")

    async def on_user_leave(self, user):
        try:
            task = self.emote_loops.pop(user.id, None)
            if task:
                task.cancel()
            partner = self.emote_pairs.pop(user.id, None)
            if partner:
                self.emote_pairs.pop(partner, None)
                ptask = self.emote_loops.pop(partner, None)
                if ptask:
                    ptask.cancel()
            uname = (getattr(user, "username", "") or "").lower()
            if uname:
                self._left_ts[uname] = time.time()
            await self._refresh_room_users()
        except Exception as err:
            log.error("on_user_leave hata (yutuldu): %s", err)

    async def on_user_move(self, user, pos):
        try:
            self._last_move[user.id] = pos
            # Freeze: donmus kullanici hareket etmeye calistiginda baslangic
            # konumuna geri cekilir.
            fp = self.frozen.get(user.id)
            if isinstance(fp, Position) and isinstance(pos, Position):
                if (
                    abs(pos.x - fp.x) + abs(pos.z - fp.z) + abs(pos.y - fp.y) > 0.6
                ):
                    try:
                        asyncio.ensure_future(self.highrise.teleport(user.id, fp))
                    except Exception as err:
                        log.debug("freeze geri cekme hatasi: %s", err)
            if self.following_user_id and user.id == self.following_user_id and isinstance(pos, Position):
                try:
                    asyncio.ensure_future(
                        self.highrise.walk_to(Position(pos.x, pos.y, pos.z, getattr(pos, "facing", None)))
                    )
                except Exception as err:
                    log.debug("takip yurus hatasi: %s", err)
        except Exception as err:
            log.error("on_user_move hata (yutuldu): %s", err)

    async def _follow_loop(self, uid):
        try:
            last = None
            while self.following_user_id == uid:
                pos = self._last_move.get(uid)
                if isinstance(pos, Position):
                    key = (round(pos.x, 1), round(pos.y, 1), round(pos.z, 1))
                    if key != last:
                        last = key
                        try:
                            await asyncio.wait_for(
                                self.highrise.walk_to(
                                    Position(pos.x, pos.y, pos.z, getattr(pos, "facing", None))
                                ),
                                timeout=5,
                            )
                        except Exception as err:
                            log.debug("takip dongu yurus: %s", err)
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass

    # ---------- tts ----------

    async def _tts_play(self, text, title, requester):
        """edge-tts ile mp3 uretir ve icecast akisina verir."""
        try:
            import edge_tts
        except ImportError:
            log.warning("edge-tts kurulu degil: pip install edge-tts")
            return False
        tts_dir = os.path.join(BASE_DIR, "tts_cache")
        try:
            os.makedirs(tts_dir, exist_ok=True)
            path = os.path.join(tts_dir, "tts_%d.mp3" % int(time.time() * 1000))
            await edge_tts.Communicate(text, voice="tr-TR-AhmetNeural").save(path)
        except Exception as err:
            log.warning("tts uretilemedi: %s", err)
            return False
        ok, msg = self.radio.play_clip(path, title, requester)
        if msg:
            log.info(msg)
        return ok

    async def _cmd_say(self, user, sender, arg, reply):
        if not self._is_baba(user.id, sender):
            await reply("-say sadece @%s icin." % self.owner_username)
            return
        text = (arg or "").strip()
        if not text:
            await reply("Kullanim: -say <mesaj>")
            return
        await reply("🎙️ Ses hazirlaniyor...")
        ok = await self._tts_play(text, "🎤 @%s" % sender, sender)
        if not ok:
            await reply("Ses hazirlanamadi (pip install edge-tts kurulu mu?)")

    async def on_chat(self, user, message):
        try:
            self._consume_nova_pending()
            if await self._check_word_answer(user, message):
                return
            if await self._maybe_emote(user, message):
                return
            if (message or "").strip().lower() in ("!base", "!yerine"):
                try:
                    await self.highrise.teleport(
                        self.bot_id,
                        Position(
                            self.home_position.x,
                            self.home_position.y,
                            self.home_position.z,
                            getattr(self.home_position, "facing", None),
                        ),
                    )
                    await self.highrise.chat(f"@{user.username} Yerime geçtim!")
                except Exception as err:
                    log.debug("!base donusu hatasi: %s", err)
                return
            await self._handle(user, message, whisper=False)
        except Exception as err:
            log.error("on_chat hata (yutuldu, reconnect onleniyor): %s", err)

    async def on_whisper(self, user, message):
        try:
            await self._handle(user, message, whisper=True)
        except Exception as err:
            log.error("on_whisper hata (yutuldu): %s", err)

    async def on_message(self, user_id, conversation_id, is_new_conversation):
        try:
            uid = str(user_id)
            # Zaten aboneyse tekrar islem yapma
            if uid in self.subscribers:
                return
            if not await self._dm_says_sub(conversation_id):
                return
            self.subscribers[uid] = {
                "user_id": uid,
                "conversation_id": str(conversation_id),
            }
            self._write_json(self.subscribers_path, self.subscribers)
            log.info("yeni abone (-sub): %s (%s)", uid, conversation_id)
        except Exception as err:
            log.error("on_message hata (yutuldu): %s", err)

    async def _dm_says_sub(self, conversation_id):
        # SDK olay icerigini vermediginden, konusma listesini cekip son mesajin
        # icerigine bakariz; yalnizca "-sub" yazan kullanici abone olur.
        try:
            resp = await self.highrise.get_conversations()
            if isinstance(resp, Error):
                return False
            for conv in resp.conversations or []:
                if conv.id != conversation_id:
                    continue
                lm = conv.last_message
                if not lm or not lm.content:
                    return False
                norm = self._norm_tr(lm.content).strip()
                norm = norm.replace("-", " ", 1).split()
                return bool(norm) and norm[0].lower() == "sub"
        except Exception as err:
            log.error("konusma icerigi okunamadi: %s", err)
        return False

    async def on_emote(self, user, emote_id, receiver=None):
        try:
            self._seen_emotes[(emote_id or "").lower()] = time.time()
        except Exception as err:
            log.debug("emote event kaydi: %s", err)

    # ---------- emote loop ----------

    async def _maybe_emote(self, user, message):
        text = (message or "").strip()
        if text.lower() == "stop":
            stopped = False
            task = self.emote_loops.pop(user.id, None)
            if task:
                task.cancel()
                stopped = True
            partner = self.emote_pairs.pop(user.id, None)
            if partner:
                self.emote_pairs.pop(partner, None)
                ptask = self.emote_loops.pop(partner, None)
                if ptask:
                    ptask.cancel()
                    stopped = True
            if stopped:
                try:
                    # emote'u ponder ile direkt kes
                    for uid in (user.id, partner) if partner else (user.id,):
                        await self.highrise.send_emote("idle-lookup", uid)
                    await self.highrise.send_whisper(user.id, "⏹️ Emote durduruldu.")
                except Exception as err:
                    log.debug("emote stop mesaji: %s", err)
                return True
            return False
        emote = find_emote(text)
        if emote is None:
            return False
        old = self.emote_loops.pop(user.id, None)
        if old:
            old.cancel()
        partner = self.emote_pairs.pop(user.id, None)
        if partner:
            self.emote_pairs.pop(partner, None)
            ptask = self.emote_loops.pop(partner, None)
            if ptask:
                ptask.cancel()
        work = await self._resolve_emote(user.id, emote)
        if work is None:
            try:
                await self.highrise.send_whisper(user.id, "❌ Emote oynatilamadi: %s" % text)
            except Exception as err:
                log.debug("emote hata mesaji: %s", err)
            return True
        task = asyncio.create_task(self._emote_loop(user.id, work, emote["duration"]))
        self.emote_loops[user.id] = task
        return True

    async def _resolve_emote(self, uid, emote):
        emote_id = emote.get("id")
        alts = emote.get("alts") or [emote_id]
        cached = self._emote_resolved.get(emote_id)
        if cached:
            try:
                await self.highrise.send_emote(cached, uid)
                return cached
            except Exception:
                self._emote_resolved.pop(emote_id, None)
        for cid in alts:
            try:
                await self.highrise.send_emote(cid, uid)
                self._emote_resolved[emote_id] = cid
                return cid
            except Exception as err:
                log.debug("emote gonderilemedi (%s): %s", cid, err)
        return None

    async def _emote_loop(self, user_id, emote_id, duration):
        loop_sec = duration if emote_id == "dance-floss" else min(duration, 13.0)
        try:
            while True:
                try:
                    await self.highrise.send_emote(emote_id, user_id)
                    await asyncio.sleep(max(0.3, loop_sec - 0.3))
                except asyncio.CancelledError:
                    self.emote_loops.pop(user_id, None)
                    try:
                        await self.highrise.send_emote("idle-lookup", user_id)
                    except Exception:
                        pass
                    raise
                except Exception as err:
                    log.debug("emote gonderilemedi (%s): %s", emote_id, err)
                    self.emote_loops.pop(user_id, None)
                    return
        except asyncio.CancelledError:
            pass

    # ---------- komut dispatch ----------

    async def _handle(self, user, message, whisper):
        if not message.startswith(PREFIX):
            return
        text = message[len(PREFIX):].strip()
        parts = text.split(None, 1)
        command = parts[0].lower() if parts else ""
        arg = parts[1].strip() if len(parts) > 1 else ""
        sender = user.username or user.id

        async def reply(msg):
            try:
                msg = "%s %s" % (self._neon(), msg)
                if whisper:
                    await self.highrise.send_whisper(user.id, msg)
                else:
                    await self.highrise.chat(msg)
            except Exception as err:
                log.debug("cevap gonderilemedi: %s", err)

        handlers = {
            "help": self._cmd_help,
            "yardim": self._cmd_help,
            "helpvip": partial(self._cmd_help_sec, "vip"),
            "helpadmin": partial(self._cmd_help_sec, "admin"),
            "helpyonetici": partial(self._cmd_help_sec, "yonetici"),
            "helpkurucu": partial(self._cmd_help_sec, "kurucu"),
            "p": self._cmd_play,
            "play": self._cmd_play,
            "cal": self._cmd_play,
            "q": self._cmd_queue,
            "queue": self._cmd_queue,
            "kuyruk": self._cmd_queue,
            "list": self._cmd_list,
            "liste": self._cmd_list,
            "skip": self._cmd_skip,
            "next": self._cmd_skip,
            "myskip": self._cmd_myskip,
            "gec": self._cmd_gec,
            "del": self._cmd_del,
            "oy": self._cmd_oy,
            "pause": self._cmd_pause,
            "duraklat": self._cmd_pause,
            "resume": self._cmd_resume,
            "devam": self._cmd_resume,
            "stop": self._cmd_stop,
            "now": self._cmd_now,
            "calan": self._cmd_now,
            "puan": self._cmd_puan,
            "skor": self._cmd_puan,
            "bakiye": self._cmd_puan,
            "wallet": self._cmd_wallet,
            "cuzdan": self._cmd_wallet,
            "tip": self._cmd_tip,
            "top": self._cmd_top,
            "gift": self._cmd_gift,
            "bj": self._cmd_bj,
            "blackjack": self._cmd_bj,
            "art": self._cmd_bj_art,
            "az": self._cmd_bj_az,
            "cok": self._cmd_bj_cok,
            "kal": self._cmd_bj_kal,
            "bot": self._cmd_bot,
            "t": self._cmd_takip,
            "takip": self._cmd_takip,
            "copy": self._cmd_copy,
            "vipal": self._cmd_puanal,
            "puanal": self._cmd_puanal,
            "roledel": self._cmd_roledel,
            "daily": self._cmd_daily,
            "gunluk": self._cmd_daily,
            "sil": self._cmd_sil,
            "saldir": self._cmd_takip,
            "gel": self._cmd_gel,
            "online": self._cmd_online,
            "kat1": self._cmd_kat1,
            "kat2": self._cmd_kat2,
            "vip": self._cmd_vip,
            "role": self._cmd_role,
            "rol": self._cmd_role,
            "emote": self._cmd_emote,
            "delm": self._cmd_delm,
            "dm": self._cmd_delm,
            "favekle": self._cmd_favekle,
            "favcalan": self._cmd_favcalan,
            "faveklecalan": self._cmd_favcalan,
            "favoriler": self._cmd_favoriler,
            "favorilerkendi": self._cmd_favoriler,
            "favori": self._cmd_favori,
            "favorisil": self._cmd_favorisil,
            "favoritemizle": self._cmd_favoritemizle,
            "rep": self._cmd_rep,
            "good": self._cmd_good,
            "repler": self._cmd_repler,
            "goodlar": self._cmd_goodlar,
            "bemote": self._cmd_bemote,
            "emoteall": self._cmd_emoteall,
            "double": self._cmd_double,
            "loop": self._cmd_loop,
            "loopstop": self._cmd_loopstop,
            "loopdur": self._cmd_loopstop,
            "botemote": self._cmd_bemote,
            "bemstop": self._cmd_bemstop,
            "botdur": self._cmd_bemstop,
            "give": self._cmd_give,
            "oda": self._cmd_oda,
            "degis": self._cmd_degis,
            "oda-ad": self._cmd_oda_ad,
            "odaad": self._cmd_oda_ad,
            "say": self._cmd_say,
            "up": self._cmd_up,
            "tp": self._cmd_tp,
            "summ": self._cmd_summ,
            "summon": self._cmd_summ,
            "cek": self._cmd_summ,
            "dur": self._cmd_dur,
            "start": self._cmd_start,
            "kapat": self._cmd_kapat,
            "ac": self._cmd_ac,
            "kick": self._cmd_kick,
            "ban": self._cmd_ban,
            "mute": self._cmd_mute,
            "unmute": self._cmd_unmute,
            "unban": self._cmd_unban,
            "gonder": self._cmd_gonder,
            "konum": self._cmd_konum,
            "aboneler": self._cmd_aboneler,
            "abone": self._cmd_aboneler,
            "freeze": self._cmd_freeze,
            "dondur": self._cmd_freeze,
            "unfreeze": self._cmd_unfreeze,
            "coz": self._cmd_unfreeze,
        }
        handler = handlers.get(command)
        if handler is None:
            await reply("Bilinmeyen komut: -%s (-help yaz)" % command)
            return
        try:
            self._cmd_whisper = whisper
            await handler(user, sender, arg, reply)
        except Exception as err:
            log.error("komut hatasi: %s", err)
            await reply("Komut calisirken hata olustu.")

    # ---------- muzik ----------

    async def _cmd_help(self, user, sender, arg, reply):
        await reply(HELP_TEXT)

    async def _cmd_help_sec(self, section, user, sender, arg, reply):
        title, body = HELP_SECTIONS[section]
        await reply(title + "\n" + body)

    async def _cmd_play(self, user, sender, arg, reply):
        if not arg:
            await reply("Kullanim: -p <sarki adi veya link>")
            return
        await reply("Sarki araniyor, birazdan basliyor...")
        result = await asyncio.to_thread(self.radio.request_song_text, arg, sender)
        if result:
            await reply(result)

    def _make_track_announcer(self):
        def cb(title, requester, duration):
            asyncio.run_coroutine_threadsafe(
                self._announce_track(title, requester, duration), self._loop
            )
        return cb

    @staticmethod
    def _fmt_duration(sec):
        try:
            sec = int(sec or 0)
        except Exception:
            sec = 0
        if sec <= 0:
            return ""
        m, s = divmod(sec, 60)
        return "%d:%02d" % (m, s)

    def _neon(self):
        """Rastgele bir canli neon rengi (<#RRGGBB>), Highrise'da desteklenir."""
        return "<#" + format(random.randint(0, 0xFFFFFF), "06X") + ">"

    async def _announce_track(self, title, requester, duration):
        bar = "▶︎•|၊|၊။|||၊၊|။||၊||၊"
        text = "🎵 %s\n👤 @%s" % (title, requester)
        t = self._fmt_duration(duration)
        if t:
            text += "\n%s %s" % (bar, t)
        try:
            await self.highrise.chat("%s %s" % (self._neon(), text))
        except Exception as err:
            log.debug("muzik duyurusu gonderilemedi: %s", err)

    async def _cmd_queue(self, user, sender, arg, reply):
        await reply(self.radio.queue_text())

    async def _cmd_list(self, user, sender, arg, reply):
        await reply(self.radio.playlist_text())

    def _prune_votes(self, current):
        tid = id(current)
        for key in list(self.skip_votes):
            if key != tid:
                del self.skip_votes[key]
        return tid

    def _vote_need(self):
        online = max(1, len(self.room_user_cache))
        return max(2, (online + 1) // 2)

    async def _do_skip(self, reply):
        self.skip_votes.clear()
        await reply(self.radio.skip_text())

    async def _cmd_skip(self, user, sender, arg, reply):
        cur = self.radio.streamer.current()
        if cur is None or not self.radio._running:
            await reply("Su an calan sarki yok.")
            return
        if self._is_owner_cmd(user.id, sender) or self._role_level(sender) >= 3:
            await self._do_skip(reply)
            return
        tid = self._prune_votes(cur)
        votes = self.skip_votes.setdefault(tid, set())
        need = self._vote_need()
        if user.id in votes:
            await reply("@%s zaten oy verdin! (%d/%d)" % (sender, len(votes), need))
            return
        votes.add(user.id)
        if len(votes) >= need:
            await reply("✅ Skip oylamasi tamamlandi (%d/%d)!" % (len(votes), need))
            await self._do_skip(reply)
        else:
            await reply(
                "🗳️ @%s skip oylamasi baslatti! (%d/%d)\nKatilmak icin: -oy" % (sender, len(votes), need)
            )

    async def _cmd_gec(self, user, sender, arg, reply):
        if self._role_level(sender) < 2 and not self._is_owner_cmd(user.id, sender):
            await reply("-gec sadece admin ve ustu icin. Oylama icin: -skip")
            return
        cur = self.radio.streamer.current()
        if cur is None or not self.radio._running:
            await reply("Su an calan sarki yok.")
            return
        await self._do_skip(reply)

    async def _cmd_myskip(self, user, sender, arg, reply):
        cur = self.radio.streamer.current()
        if cur is None or not self.radio._running:
            await reply("Su an calan sarki yok.")
            return
        req = (getattr(cur, "requester", "") or "").strip()
        if not req or req.casefold() != sender.casefold():
            await reply("-myskip sadece KENDI istedigin sarkiyi gecmek icin. Baskasinin sarkisi icin: -skip")
            return
        self.skip_votes.clear()
        result = self.radio.cmd_next()
        if result.get("ok"):
            await reply("⏭️ @%s kendi istegini gecirdi" % sender)
        else:
            await reply("Aktarilamadi.")

    async def _cmd_del(self, user, sender, arg, reply):
        if self._role_level(sender) < 2 and not self._is_owner_cmd(user.id, sender):
            await reply("-del sadece admin ve ustu icin.")
            return
        cur = self.radio.streamer.current()
        if cur is None or not self.radio._running:
            await reply("Su an calan sarki yok.")
            return
        ok, text = self.radio.ban_current_text()
        if ok:
            await self._do_skip(reply)
            await reply("🚫 %s (bir daha calmamak uzere banlandi)" % text)
        else:
            await reply(text)

    async def _cmd_oy(self, user, sender, arg, reply):
        cur = self.radio.streamer.current()
        if cur is None or not self.radio._running:
            await reply("Su an calan sarki yok, oylama yok.")
            return
        tid = self._prune_votes(cur)
        votes = self.skip_votes.setdefault(tid, set())
        need = self._vote_need()
        if user.id in votes:
            await reply("@%s zaten oy verdin! (%d/%d)" % (sender, len(votes), need))
            return
        votes.add(user.id)
        total = len(votes)
        if total >= need:
            await reply("✅ Skip oylamasi tamamlandi (%d/%d)!" % (total, need))
            await self._do_skip(reply)
        else:
            await reply("🗳️ @%s oy verdi (%d/%d). Eksik oy: %d" % (sender, total, need, need - total))

    async def _cmd_pause(self, user, sender, arg, reply):
        self.radio.cmd_pause()
        await reply("Radyo duraklatildi.")

    async def _cmd_resume(self, user, sender, arg, reply):
        self.radio.cmd_resume()
        await reply("Radyo devam ediyor.")

    async def _cmd_stop(self, user, sender, arg, reply):
        self.radio.cmd_stop()
        emote_kesildi = False
        task = self.emote_loops.pop(user.id, None)
        if task:
            task.cancel()
            emote_kesildi = True
        partner = self.emote_pairs.pop(user.id, None)
        if partner:
            self.emote_pairs.pop(partner, None)
            ptask = self.emote_loops.pop(partner, None)
            if ptask:
                ptask.cancel()
                emote_kesildi = True
        try:
            # emote'u ponder ile direkt kes
            for uid in (user.id, partner) if partner else (user.id,):
                await self.highrise.send_emote("idle-lookup", uid)
        except Exception as err:
            log.debug("emote ponder kesme: %s", err)
        if emote_kesildi:
            await reply("Radyo durduruldu. Emote durduruldu.")
        else:
            await reply("Radyo durduruldu.")

    async def _cmd_now(self, user, sender, arg, reply):
        await reply(self.radio.now_text())

    # ---------- puan ----------

    def _is_kurucu(self, user_id, username):
        return self._role_level(username) >= 4 or self._is_owner_cmd(user_id, username)

    async def _cmd_puan(self, user, sender, arg, reply):
        if self._is_kurucu(user.id, sender):
            try:
                await self.highrise.send_whisper(user.id, "👑 Puanin: sinirsiz")
            except Exception as err:
                log.debug("kurucu puan whisper: %s", err)
            return
        data = self.scores.get(user.id)
        if not data:
            await reply("@%s: Henuz puanin yok!" % sender)
        else:
            await reply("@%s: %d puan" % (sender, data["score"]))

    async def _cmd_wallet(self, user, sender, arg, reply):
        try:
            wallets = await self.highrise.get_wallet()
            content = getattr(wallets, "content", wallets) or []
            parts = []
            for w in content:
                amount = getattr(w, "amount", None)
                currency = getattr(w, "type", None) or getattr(w, "currency", None) or "?"
                if amount is not None:
                    parts.append("%s %s" % (amount, currency))
            if parts:
                await reply("💰 Bot cuzdani: %s" % ", ".join(parts))
            else:
                await reply("💰 Bot cuzdani bos.")
        except Exception as err:
            log.warning("wallet: %s", err)
            await reply("Cuzdan alinamadi.")

    async def _cmd_tip(self, user, sender, arg, reply):
        if not self._is_kurucu(user.id, sender):
            await reply("Bu komut sadece kurucu icin.")
            return
        parts = arg.split()
        if len(parts) < 2:
            await reply("Kullanim: -tip @kisi <1|5|10|50|100|500|1k|5k|10k>")
            return
        target = self._find_user(parts[0])
        if target is None:
            await reply("Odada kisi bulunamadi: %s" % parts[0])
            return
        raw = parts[1].lower().strip()
        bar_map = {
            "1": "gold_bar_1",
            "5": "gold_bar_5",
            "10": "gold_bar_10",
            "50": "gold_bar_50",
            "100": "gold_bar_100",
            "500": "gold_bar_500",
            "1000": "gold_bar_1k",
            "1k": "gold_bar_1k",
            "5000": "gold_bar_5000",
            "5k": "gold_bar_5000",
            "10000": "gold_bar_10k",
            "10k": "gold_bar_10k",
        }
        bar = bar_map.get(raw)
        if bar is None:
            await reply("Gecersiz miktar. Barlar: 1, 5, 10, 50, 100, 500, 1k, 5k, 10k")
            return
        try:
            res = await self.highrise.tip_user(target.id, bar)
        except Exception as err:
            log.warning("tip_user: %s", err)
            await reply("Gonderim hatasi: %s" % str(err)[:120])
            return
        if isinstance(res, Error):
            msg = getattr(res, "message", "") or str(res)
            await reply("Gonderilemedi: %s" % msg[:120])
            return
        if res == "insufficient_funds":
            await reply("Bot cuzdaninda yeterli gold yok! (-wallet ile bak)")
            return
        await reply("💸 @%s bot cuzdanindan @%s kisine %s gold gonderdi!" % (sender, target.username, raw))

    async def _cmd_top(self, user, sender, arg, reply):
        top = sorted(self.scores.values(), key=lambda d: d.get("score", 0), reverse=True)[:5]
        if not top:
            await reply("Henuz skor yok!")
            return
        medals = ["🥇", "🥈", "🥉", "4.", "5."]
        msg = "**SKOR TABLOSU**\n\n"
        for i, p in enumerate(top):
            msg += "%s **@%s**: %d puan\n" % (medals[i], p.get("username", "?"), p.get("score", 0))
        await reply(msg)

    # ---------- blackjack (puan ile) ----------

    def _bj_score(self, user_id):
        return int(self.scores.get(user_id, {}).get("score", 0))

    async def _cmd_bj(self, user, sender, arg, reply):
        try:
            bet = int(arg.strip().replace(".", "").replace("_", ""))
        except ValueError:
            await reply("Kullanim: -bj <miktar> (%d-%d puan)" % (BJ_MIN_BET, BJ_MAX_BET))
            return
        if bet < BJ_MIN_BET or bet > BJ_MAX_BET:
            await reply("Bahis %d-%d puan arasinda olmali." % (BJ_MIN_BET, BJ_MAX_BET))
            return
        if user.id in self.bj_games:
            await reply("Aktif elin var! (-art / -kal)")
            return
        kurucu = self._is_kurucu(user.id, sender)
        if not kurucu and self._bj_score(user.id) < bet:
            await reply("Yeterli puanin yok! Mevcut puanin: %d" % self._bj_score(user.id))
            return
        if kurucu:
            # kurucunun puani 0'in altina dusmez (sinirsiz oyun)
            self._add_score(user.id, sender, -min(self._bj_score(user.id), bet))
        else:
            self._add_score(user.id, sender, -bet)
        player = [_bj_deal(), _bj_deal()]
        dealer = [_bj_deal(), _bj_deal()]
        self.bj_games[user.id] = {
            "player": player,
            "dealer": dealer,
            "bet": bet,
            "last": time.time(),
            "settling": False,
            "arts": 0,
            "az_used": False,
            "cok_used": False,
            "username": sender,
        }
        pv = sum(player)
        dv = sum(dealer)
        if pv == 21 and dv == 21:
            del self.bj_games[user.id]
            self._add_score(user.id, sender, bet)
            await self.highrise.chat("🤝 @%s ikisi de Blackjack! İade %d puan" % (sender, bet))
        elif pv == 21:
            payout = int(bet * BJ_BLACKJACK_PAYOUT)
            del self.bj_games[user.id]
            self._add_score(user.id, sender, payout)
            await self.highrise.chat(
                "🎉 @%s BLACKJACK! +%d puan (toplam: %d)" % (sender, payout, self._bj_score(user.id))
            )
        elif dv == 21:
            del self.bj_games[user.id]
            await self.highrise.chat("🂠 Kasa Blackjack! @%s -%d puan" % (sender, bet))
        else:
            await self.highrise.chat(
                "♠️ @%s %d puan | Sen %d | Kasa %d? | 🎯-art ✋-kal" % (sender, bet, pv, dealer[1])
            )

    async def _cmd_bj_art(self, user, sender, arg, reply):
        await self._bj_draw(user, sender, "art")

    async def _cmd_bj_az(self, user, sender, arg, reply):
        await self._bj_draw(user, sender, "az")

    async def _cmd_bj_cok(self, user, sender, arg, reply):
        await self._bj_draw(user, sender, "cok")

    async def _bj_draw(self, user, sender, kind):
        game = self.bj_games.get(user.id)
        if not game or game["settling"]:
            return
        if kind in ("az", "cok"):
            if game["arts"] == 0:
                try:
                    await self.highrise.send_whisper(user.id, "⚠️ Önce bir -art çek")
                except Exception:
                    pass
                return
            if kind == "az" and game["az_used"]:
                try:
                    await self.highrise.send_whisper(user.id, "⚠️ -az bu elde bitti")
                except Exception:
                    pass
                return
            if kind == "cok" and game["cok_used"]:
                try:
                    await self.highrise.send_whisper(user.id, "⚠️ -cok bu elde bitti")
                except Exception:
                    pass
                return
        value = {"art": _bj_deal, "az": _bj_low, "cok": _bj_high}[kind]()
        game["player"].append(value)
        game["last"] = time.time()
        if kind == "art":
            game["arts"] += 1
        elif kind == "az":
            game["az_used"] = True
        else:
            game["cok_used"] = True
        total = sum(game["player"])
        icon = {"art": "🎯", "az": "🔽", "cok": "🔼"}[kind]
        if total > 21:
            bet = game["bet"]
            del self.bj_games[user.id]
            await self.highrise.chat("💥 @%s %s%d → %d! (-%d puan)" % (sender, icon, value, total, bet))
        elif total == 21:
            await self._bj_settle(user.id, sender)
        else:
            await self.highrise.chat("@%s %s%d → %d" % (sender, icon, value, total))

    async def _cmd_bj_kal(self, user, sender, arg, reply):
        game = self.bj_games.get(user.id)
        if not game or game["settling"]:
            return
        await self._bj_settle(user.id, sender)

    async def _bj_settle(self, uid, sender):
        game = self.bj_games.get(uid)
        if not game:
            return
        game["settling"] = True
        bet = game["bet"]
        pv = sum(game["player"])
        dealer = list(game["dealer"])
        dv = sum(dealer)
        while dv < 17:
            dealer.append(_bj_deal())
            dv = sum(dealer)
        del self.bj_games[uid]
        if dv > 21:
            self._add_score(uid, sender, bet * 2)
            await self.highrise.chat("🂠 Kasa %d 💥 🎉 @%s +%d puan (toplam: %d)" % (dv, sender, bet, self._bj_score(uid)))
        elif pv > dv:
            self._add_score(uid, sender, bet * 2)
            await self.highrise.chat("🂠 Kasa %d | 🎉 @%s +%d puan (toplam: %d)" % (dv, sender, bet, self._bj_score(uid)))
        elif dv > pv:
            await self.highrise.chat("🂠 Kasa %d | 😔 @%s -%d puan" % (dv, sender, bet))
        else:
            self._add_score(uid, sender, bet)
            await self.highrise.chat("🂠 Kasa %d | ⚖️ @%s berabere (toplam: %d)" % (dv, sender, self._bj_score(uid)))

    async def _bj_sweeper(self):
        while True:
            try:
                await asyncio.sleep(20)
                now = time.time()
                for uid, game in list(self.bj_games.items()):
                    if now - game["last"] > BJ_IDLE_TIMEOUT:
                        del self.bj_games[uid]
                        self._add_score(uid, game.get("username", uid), game["bet"])
                        try:
                            await self.highrise.send_whisper(
                                uid, "⌛ Blackjack eli iptal, %d puan iade edildi." % game["bet"]
                            )
                        except Exception as err:
                            log.debug("bj iade whisper: %s", err)
            except asyncio.CancelledError:
                return
            except Exception as err:
                log.warning("bj sweeper hatasi: %s", err)

    async def _cmd_gift(self, user, sender, arg, reply):
        parts = arg.split()
        if len(parts) < 2:
            await reply("Kullanim: -gift <kisi> <puan>")
            return
        target = self._find_user(parts[0])
        if target is None:
            await reply("@%s odada bulunamadi." % parts[0].lstrip("@"))
            return
        try:
            amount = int(parts[1])
        except ValueError:
            await reply("Puan miktari sayi olmali.")
            return
        if amount <= 0:
            await reply("Gecerli bir puan miktari gir.")
            return
        if not self._is_owner_cmd(user.id, sender):
            src = self.scores.get(user.id)
            if not src or src["score"] < amount:
                await reply("Yeterli puanin yok! Toplam puanin: %d" % (src["score"] if src else 0))
                return
            src["score"] -= amount
            self.scores[user.id] = src
        self._add_score(target.id, target.username, amount)
        new_score = self.scores[target.id]["score"]
        await reply(
            "🎁 @%s, @%s kisisine **%d** puan hediye etti! (Toplam: %d)"
            % (sender, target.username, amount, new_score)
        )

    # ---------- bot hareket ----------

    async def _teleport_bot_home(self):
        bot_id = self.bot_id
        if not bot_id:
            info = await self.highrise.get_my_user()
            bot_id = info.id
        await self.highrise.teleport(bot_id, self.home_position)

    async def _cmd_bot(self, user, sender, arg, reply):
        parts = arg.split()
        if len(parts) == 3:
            if self._role_level(sender) < 3 and not self._is_owner_cmd(user.id, sender):
                await reply("Koordinat ayarlama yetkisi yok (Yonetici ve ustu).")
                return
            try:
                x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
            except ValueError:
                await reply("Gecersiz koordinat. Ornek: -bot 8.0 0.0 7.0")
                return
            self.home_position = Position(x, y, z)
            self._save_home()
            await reply("🤖 Bot donus koordinati guncellendi: %s, %s, %s" % (x, y, z))
            return
        if parts and parts[0].lower() in ("buraya", "here"):
            if not (
                self._is_kurucu(user.id, sender) or self._is_owner_cmd(user.id, sender)
            ):
                await reply("-bot buraya sadece @%s icin." % self.owner_username)
                return
            my_pos = None
            for u, p in self.room_user_cache:
                if u.id == user.id and isinstance(p, Position):
                    my_pos = p
                    break
            if my_pos is None:
                await reply("Konumunu bulamadim, biraz yuruyup tekrar dene.")
                return
            self.home_position = Position(
                my_pos.x,
                my_pos.y,
                my_pos.z,
                getattr(my_pos, "facing", None) or "Front",
            )
            self._save_home()
            try:
                await self.highrise.teleport(self.bot_id, self.home_position)
            except Exception as err:
                log.debug("buraya teleport hatasi: %s", err)
            await reply(
                "🤖 Botun yeni evi ayarlandi: %s, %s, %s"
                % (my_pos.x, my_pos.y, my_pos.z)
            )
            return
        if not parts:
            cost = 100
            if not self._is_kurucu(user.id, sender):
                score = self.scores.get(user.id, {}).get("score", 0)
                if score < cost:
                    await reply("-bot icin %d puan gerekli! Mevcut puanin: %d" % (cost, score))
                    return
                self._add_score(user.id, sender, -cost)
                cost_text = " -%d puan." % cost
            else:
                cost_text = "."
            try:
                await self._teleport_bot_home()
            except Exception as err:
                await reply("Isinlanamadi: %s" % err)
                return
            await reply(
                "✅ Bot varsayilan konumuna isinlandi (%s, %s, %s)%s"
                % (self.home_position.x, self.home_position.y, self.home_position.z, cost_text)
            )
            return
        await reply("Kullanim: -bot (isinlan) | -bot buraya | -bot <x> <y> <z>")

    async def _cmd_takip(self, user, sender, arg, reply):
        target = self._find_user(arg)
        if target is None:
            await reply("@%s odada bulunamadi." % arg.strip().lstrip("@"))
            return
        if target.id == user.id:
            await reply("Kendini takip edemezsin!")
            return
        if self.following_user_id is not None:
            await reply("Bot su anda baskasini takip ediyor.")
            return
        cost = 100
        if not self._is_kurucu(user.id, sender):
            score = self.scores.get(user.id, {}).get("score", 0)
            if score < cost:
                await reply("-t icin %d puan gerekli! Mevcut puanin: %d" % (cost, score))
                return
            self._add_score(user.id, sender, -cost)
            cost_text = " (-%d puan)" % cost
        else:
            cost_text = ""
        self.following_user_id = target.id
        tpos = self._last_move.get(target.id)
        if isinstance(tpos, Position):
            try:
                await self.highrise.walk_to(Position(tpos.x, tpos.y, tpos.z))
            except Exception as err:
                log.debug("takip yaklasma: %s", err)
        follow_task = asyncio.ensure_future(self._follow_loop(target.id))
        await reply("🔒 @%s 15 saniye boyunca takip ediliyor...%s" % (target.username, cost_text))
        try:
            await asyncio.sleep(15)
        finally:
            self.following_user_id = None
            follow_task.cancel()
        try:
            await self._teleport_bot_home()
        except Exception as err:
            log.debug("takip donus hatasi: %s", err)
        await reply("🏠 Takip suresi bitti, bot varsayilan konumuna dondu.")

    async def _cmd_gel(self, user, sender, arg, reply):
        if not self._is_baba(user.id, sender):
            await reply("-gel sadece @%s icin." % self.owner_username)
            return
        pos = None
        for u, p in self.room_user_cache:
            if u.id == user.id:
                pos = p
                break
        if pos is None:
            await reply("Konumun bulunamadi.")
            return
        hedef = Position(
            pos.x, pos.y, pos.z, getattr(pos, "facing", None) or "FrontRight"
        )
        try:
            await self.highrise.walk_to(hedef)
            await reply("👋 @%s yanina geliyorum! (ana konumuma geri donecegim)" % sender)
        except Exception as err:
            await reply("Gidilemedi: %s" % err)

    async def _cmd_online(self, user, sender, arg, reply):
        names = ["@%s" % u.username for u, _p in self.room_user_cache if u.username]
        if not names:
            await reply("Odada gorunur kullanici yok.")
            return
        await reply("Odadaki kullanicilar (%d):\n%s" % (len(names), ", ".join(names)))

    # ---------- isinlama ----------

    async def _cmd_kat1(self, user, sender, arg, reply):
        await self._kat(user, sender, reply, self.home_position, "1. kat")

    async def _cmd_kat2(self, user, sender, arg, reply):
        await self._kat(user, sender, reply, self.kat2_position, "2. kat")

    async def _kat(self, user, sender, reply, target, kat_ad):
        try:
            await self.highrise.teleport(user.id, target)
            await reply("@%s %sa isinlandiniz!" % (sender, kat_ad))
        except Exception as err:
            await reply("Isinlama basarisiz: %s" % err)

    async def _cmd_vip(self, user, sender, arg, reply):
        if self._role_level(sender) >= 1:
            await self._kat(user, sender, reply, self.vip_position, "VIP alani")
            return
        await reply("@%s VIP alani sadece rollu kullanıcılara acik. Rol icin kurucuya basvur." % sender)

    # ---------- roller ----------

    async def _cmd_emote(self, user, sender, arg, reply):
        parts = arg.split(None, 1)
        sub = parts[0].lower() if parts else ""
        rest = parts[1].strip() if len(parts) > 1 else ""
        if sub in ("", "list", "liste"):
            await self._send_emote_list(user)
            return
        if sub in ("ara", "search", "bul"):
            if not rest:
                await reply("Kullanim: -emote ara <kelime>")
                return
            found = search_emotes(rest)
            if not found:
                await reply("🔍 '%s' icin emote bulunamadi." % rest)
                return
            lines = ["🔍 '%s' icin %d sonuc:" % (rest, len(found))]
            lines += ["%d %s" % (e["num"], e["name"]) for e in found[:30]]
            await self._whisper_long(user.id, "\n".join(lines))
            return
        emote = find_emote(arg.strip())
        if emote is None:
            await reply("Emote bulunamadi: %s\nTam adi veya numarasi lazim. Liste: -emote list" % arg.strip()[:40])
            return
        old = self.emote_loops.pop(user.id, None)
        if old:
            old.cancel()
        work = await self._resolve_emote(user.id, emote)
        if work is None:
            await reply("❌ Emote oynatilamadi: %s" % emote["name"])
            return
        task = asyncio.create_task(self._emote_loop(user.id, work, emote["duration"]))
        self.emote_loops[user.id] = task
        try:
            await self.highrise.send_whisper(user.id, "💃 Emote: %s (loop). Durdurmak icin: stop" % emote["name"])
        except Exception as err:
            log.debug("emote onay: %s", err)

    async def _send_emote_list(self, user):
        from emotes import EMOTES

        pages = []
        chunk = []
        size = 0
        for e in EMOTES:
            line = "%d %s" % (e["num"], e["name"])
            if size + len(line) + 1 > 380 and chunk:
                pages.append("\n".join(chunk))
                chunk, size = [], 0
            chunk.append(line)
            size += len(line) + 1
        if chunk:
            pages.append("\n".join(chunk))
        total = len(pages)
        for i, page in enumerate(pages, 1):
            try:
                await self.highrise.send_whisper(user.id, "📜 Emote listesi %d/%d (kullanmak icin numara/tam ad yaz):\n%s" % (i, total, page))
                await asyncio.sleep(0.4)
            except Exception as err:
                log.debug("emote liste: %s", err)
                break

    async def _whisper_long(self, user_id, text):
        size = 420
        for i in range(0, len(text), size):
            try:
                await self.highrise.send_whisper(user.id, text[i:i + size])
                await asyncio.sleep(0.3)
            except Exception as err:
                log.debug("uzun whisper: %s", err)
                break

    async def _cmd_bemote(self, user, sender, arg, reply):
        if self._role_level(sender) < 1:
            await reply("-bemote sadece rollu kullanicilara acik (VIP+).")
            return
        emote = find_emote((arg or "").strip())
        if emote is None:
            await reply("Emote bulunamadi — tam ad veya numara gerekli. Liste: -emote list")
            return
        old = self.emote_loops.pop("__bot__", None)
        if old:
            old.cancel()
        work = await self._resolve_emote(self.bot_id, emote)
        if work is None:
            await reply("❌ Bot emotesu oynatilamadi: %s" % emote["name"])
            return
        task = asyncio.create_task(self._emote_loop(self.bot_id, work, emote["duration"]))
        self.emote_loops["__bot__"] = task
        self.bot_emote = {
            "id": emote["id"],
            "name": emote["name"],
            "duration": emote["duration"],
        }
        self._write_json(self.bot_emote_path, self.bot_emote)
        await reply("🤖 Bot simdi '%s' yapiyor! (durdurmak icin: -bemstop)" % emote["name"])

    async def _restore_bot_emote(self):
        if not self.bot_emote or not self.bot_emote.get("id"):
            return
        emote = find_emote(self.bot_emote["id"])
        if emote is None:
            emote = find_emote(self.bot_emote.get("name", ""))
        if emote is None:
            return
        work = await self._resolve_emote(self.bot_id, emote)
        if work is None:
            return
        old = self.emote_loops.pop("__bot__", None)
        if old:
            old.cancel()
        task = asyncio.create_task(self._emote_loop(self.bot_id, work, emote["duration"]))
        self.emote_loops["__bot__"] = task
        log.info("kalici bot emote geri yuklendi: %s", emote["name"])

    async def _restore_bot_emote_later(self):
        try:
            await asyncio.sleep(5)
            if not self.bot_emote or not self.bot_emote.get("id"):
                return
            emote = find_emote(self.bot_emote["id"])
            if emote is None:
                emote = find_emote(self.bot_emote.get("name", ""))
            if emote is None:
                self.bot_emote = {}
                self._write_json(self.bot_emote_path, self.bot_emote)
                return
            work = await self._resolve_emote(self.bot_id, emote)
            if work is None:
                self.bot_emote = {}
                self._write_json(self.bot_emote_path, self.bot_emote)
                log.warning("kalici bot emote cozulemedi, bot_emote.json temizlendi")
                return
            old = self.emote_loops.pop("__bot__", None)
            if old:
                old.cancel()
            task = asyncio.create_task(self._emote_loop(self.bot_id, work, emote["duration"]))
            self.emote_loops["__bot__"] = task
            log.info("kalici bot emote geri yuklendi: %s", emote["name"])
        except Exception as err:
            log.debug("kalici bot emote (gecikmeli) hatasi: %s", err)

    async def _cmd_bemstop(self, user, sender, arg, reply):
        if self._role_level(sender) < 1:
            await reply("-bemstop sadece rollu kullanicilara acik (VIP+).")
            return
        old = self.emote_loops.pop("__bot__", None)
        if old:
            old.cancel()
            self.bot_emote = {}
            self._write_json(self.bot_emote_path, self.bot_emote)
            await reply("🤖 Botun emotesu durduruldu.")
        else:
            await reply("Botun devam eden bir emotesu yok.")

    # ---------- kuyruk duzenleme ----------

    async def _cmd_delm(self, user, sender, arg, reply):
        title = self.radio.remove_last_request(sender)
        if title is None:
            await reply("@%s kuyrukta senin bir sarkin yok." % sender)
        else:
            await reply("🗑️ Kuyruktan cikarildi: %s" % title)

    # ---------- favoriler ----------

    def _my_favs(self, user):
        data = self.favorites.get(user.id)
        if not isinstance(data, dict) or "songs" not in data:
            data = {"username": user.username, "songs": []}
            self.favorites[user.id] = data
        return data

    async def _cmd_favekle(self, user, sender, arg, reply):
        q = (arg or "").strip()
        if not q:
            await reply("Kullanim: -favekle <sarki adi veya link>")
            return
        favs = self._my_favs(user)
        if len(favs["songs"]) >= 20:
            await reply("Favori listen dolu (20 sarki). Yer acmak icin: -favorisil <no> veya -favoritemizle")
            return
        try:
            item = self.radio.resolver.resolve(q)
        except Exception as err:
            await reply("Sarki bulunamadi: %s" % str(err)[:100])
            return
        if not item or not item.url or item.url.startswith("clip:"):
            await reply("Bu sarki favorilere eklenemiyor.")
            return
        for s in favs["songs"]:
            if s.get("url") == item.url:
                await reply("⭐ Zaten favorilerinde (#%d): %s" % (favs["songs"].index(s) + 1, item.title))
                return
        favs["username"] = user.username
        favs["songs"].append({"title": item.title or q, "url": item.url})
        self._write_json(self.favorites_path, self.favorites)
        await reply("⭐ Favorilere eklendi (#%d): %s" % (len(favs["songs"]), item.title))

    async def _cmd_favcalan(self, user, sender, arg, reply):
        cur = self.radio.current_item()
        if cur is None or not getattr(cur, "url", ""):
            await reply("Su an calan sarki yok.")
            return
        if (cur.url or "").startswith("clip:"):
            await reply("Su an ses anonsu caliyor, sarki degil.")
            return
        favs = self._my_favs(user)
        if len(favs["songs"]) >= 20:
            await reply("Favori listen dolu (20 sarki). Yer acmak icin: -favorisil <no> veya -favoritemizle")
            return
        for i, s in enumerate(favs["songs"]):
            if s.get("url") == cur.url:
                await reply("⭐ Zaten favorilerinde (#%d): %s" % (i + 1, cur.title))
                return
        favs["username"] = user.username
        favs["songs"].append({"title": cur.title or "?", "url": cur.url})
        self._write_json(self.favorites_path, self.favorites)
        await reply("⭐ Calan sarki favorilere eklendi (#%d): %s" % (len(favs["songs"]), cur.title))

    async def _cmd_favoriler(self, user, sender, arg, reply):
        favs = self.favorites.get(user.id)
        songs = (favs or {}).get("songs") or []
        if not songs:
            await reply("@%s favori listen bos. Ekleme: -favekle <sarki>" % sender)
            return
        lines = ["⭐ @%s favorileri (%d/20):" % (sender, len(songs))]
        lines += ["%d. %s" % (i + 1, s.get("title", "?")) for i, s in enumerate(songs)]
        try:
            await self.highrise.send_whisper(user.id, "\n".join(lines))
            await reply("📜 Favori listen ozel mesajla gonderildi.")
        except Exception as err:
            log.debug("favori liste whisper: %s", err)
            await reply("\n".join(lines))

    async def _cmd_favori(self, user, sender, arg, reply):
        num = (arg or "").strip()
        favs = self.favorites.get(user.id)
        songs = (favs or {}).get("songs") or []
        if not num.isdigit() or not songs:
            await reply("Kullanim: -favori <numara> (listeni gor: -favoriler)")
            return
        idx = int(num) - 1
        if idx < 0 or idx >= len(songs):
            await reply("Gecersiz numara. Listen 1-%d arasi." % len(songs))
            return
        song = songs[idx]
        msg = self.radio.request_song_text(song["url"], sender)
        await reply(msg if msg else "▶️ Favorin calasiyor: %s" % song.get("title", "?"))

    async def _cmd_favorisil(self, user, sender, arg, reply):
        num = (arg or "").strip()
        favs = self.favorites.get(user.id)
        songs = (favs or {}).get("songs") or []
        if not num.isdigit() or not songs:
            await reply("Kullanim: -favorisil <numara>")
            return
        idx = int(num) - 1
        if idx < 0 or idx >= len(songs):
            await reply("Gecersiz numara. Listen 1-%d arasi." % len(songs))
            return
        removed = songs.pop(idx)
        self._write_json(self.favorites_path, self.favorites)
        await reply("🗑️ Favoriden silindi: %s" % removed.get("title", "?"))

    async def _cmd_favoritemizle(self, user, sender, arg, reply):
        favs = self.favorites.get(user.id)
        songs = (favs or {}).get("songs") or []
        if not songs:
            await reply("Favori listen zaten bos.")
            return
        n = len(songs)
        songs.clear()
        self._write_json(self.favorites_path, self.favorites)
        await reply("🧹 %d favori temizlendi." % n)

    # ---------- sikayet / takdir ----------

    async def _cmd_rep(self, user, sender, arg, reply):
        parts = arg.split(None, 1)
        target = self._find_user(parts[0] if parts else "")
        if target is None:
            await reply("Kullanim: -rep @kisi <sebep (opsiyonel)>")
            return
        if target.id == user.id:
            await reply("Kendini sikayet edemezsin!")
            return
        reason = parts[1].strip()[:120] if len(parts) > 1 else ""
        entry = self.reports.setdefault(target.id, {"username": target.username, "count": 0, "details": []})
        now = time.time()
        for d in entry.get("details", []):
            if d.get("by_id") == user.id and now - d.get("ts", 0) < 60:
                await reply("@%s az once bu kisiyi sikayet ettin, biraz bekle." % sender)
                return
        entry["username"] = target.username
        entry["count"] = int(entry.get("count", 0)) + 1
        details = entry.setdefault("details", [])
        details.append({"by": sender, "by_id": user.id, "reason": reason, "ts": now})
        entry["details"] = details[-50:]
        self._write_json(self.reports_path, self.reports)
        if entry["count"] == 5:
            await reply(
                "🚨 DUYURU: @%s hakkinda sikayet siniri doldu (%d sikayet)! @%s ilglenip gerekli cezayi verecek."
                % (target.username, entry["count"], self.owner_username)
            )
        elif entry["count"] > 5:
            await reply("📋 @%s sikayet kaydi alindi (toplam: %d, ceza listesinde)." % (target.username, entry["count"]))
        else:
            await reply("📋 @%s hakkinda sikayet kaydi alindi (toplam: %d)." % (target.username, entry["count"]))

    async def _cmd_good(self, user, sender, arg, reply):
        target = self._find_user((arg or "").split()[0] if arg.strip() else "")
        if target is None:
            await reply("Kullanim: -good @kisi")
            return
        if target.id == user.id:
            await reply("Kendine good veremezsin 😄")
            return
        entry = self.goods.setdefault(target.id, {"username": target.username, "count": 0})
        entry["username"] = target.username
        entry["count"] = int(entry.get("count", 0)) + 1
        self._write_json(self.goods_path, self.goods)
        await reply("🌟 @%s takdir edildi! (toplam: %d)" % (target.username, entry["count"]))

    async def _cmd_repler(self, user, sender, arg, reply):
        if not self._is_kurucu(user.id, sender):
            await reply("-repler sadece kurucuya acik.")
            return
        items = sorted(self.reports.values(), key=lambda d: int(d.get("count", 0)), reverse=True)[:5]
        if not items:
            await reply("Henuz sikayet kaydi yok.")
            return
        lines = ["📋 EN COK SIKAYET ALANLAR:"]
        lines += ["%d. @%s — %d sikayet" % (i + 1, d.get("username", "?"), d.get("count", 0)) for i, d in enumerate(items)]
        await reply("\n".join(lines))

    async def _cmd_goodlar(self, user, sender, arg, reply):
        items = sorted(self.goods.values(), key=lambda d: int(d.get("count", 0)), reverse=True)[:5]
        if not items:
            await reply("Henuz takdir kaydi yok. Takdir icin: -good @kisi")
            return
        lines = ["🌟 EN SEVILENLER:"]
        lines += ["%d. @%s — %d 🌟" % (i + 1, d.get("username", "?"), d.get("count", 0)) for i, d in enumerate(items)]
        await reply("\n".join(lines))

    async def _cmd_role(self, user, sender, arg, reply):
        lines = []
        for rol in ("vip", "admin", "yonetici", "kurucu"):
            sahipler = ["@%s" % n for n, r in self.roles.items() if r == rol]
            lines.append("%s: %s" % (ROLE_LABELS[rol], ", ".join(sahipler) if sahipler else "-"))
        await reply("\n".join(lines))

    @staticmethod
    async def _find_global_user(nick):
        """Highrise genel veritabaninda kullanici ara (oda disi dahil).

        Not: webapi.highrise.game/users listeleme endpoint'i kaldirildi (404).
        Calisan yol: highrise.game/profile/<kullanici> sayfasindaki
        __NEXT_DATA__ icindeki profile.user_id.
        """

        def _http():
            resp = requests.get(
                "https://highrise.game/profile/%s" % nick,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            resp.raise_for_status()
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', resp.text, re.S)
            if not m:
                raise RuntimeError("profil sayfasi cozulemedi")
            data = json.loads(m.group(1))
            prof = ((data.get("props") or {}).get("pageProps") or {}).get("profile") or {}
            uid = str(prof.get("user_id") or "")
            if not uid:
                raise RuntimeError("kullanici bulunamadi")
            return {"id": uid, "username": str(prof.get("username") or nick)}

        loop = asyncio.get_running_loop()
        return await asyncio.wait_for(loop.run_in_executor(None, _http), timeout=15)

    async def _cmd_copy(self, user, sender, arg, reply):
        if not self._is_baba(user.id, sender):
            await reply("-copy sadece @%s icin." % self.owner_username)
            return
        nick = (arg or "").strip().lstrip("@").split()
        if not nick:
            await reply("Kullanim: -copy @kullanici_adi")
            return
        nick = nick[0]
        tid = ""
        tname = nick
        try:
            _resp = await self.highrise.get_room_users()
            for u, n in (_resp.content or []):
                if n.username.lower() == nick.lower():
                    tid = u.id
                    tname = n.username
                    break
        except Exception:
            pass
        if not tid:
            await reply("'%s' araniyor..." % nick)
            try:
                target = await self._find_global_user(nick)
            except Exception as err:
                log.warning("copy arama hatasi: %s", err)
                await reply("'%s' adinda kullanici bulunamadi." % nick)
                return
            tid = str(target.get("id", ""))
            tname = str(target.get("username", nick))
        try:
            resp = await self.highrise.get_user_outfit(tid)
        except Exception as err:
            log.warning("copy kombin alinamadi: %s", err)
            await reply("@%s kombine erisilemedi." % tname)
            return
        outfit = getattr(resp, "outfit", None)
        if not outfit:
            await reply("@%s kombini bos gorunuyor." % tname)
            return
        try:
            await self.highrise.set_outfit(outfit)
        except Exception as err:
            log.warning("copy giyme hatasi: %s", err)
            await reply(
                "Kombin giyilemedi: bot sadece ucretsiz veya kendi dolabindaki esyalari giyebilir."
            )
            return
        await reply("✅ @%s kullanicisinin kombini bota giydirildi!" % tname)

    async def _cmd_daily(self, user, sender, arg, reply):
        today = time.strftime("%Y-%m-%d")
        rec = self.scores.get(user.id)
        if rec is None:
            rec = {"username": sender, "score": 0, "id": user.id}
            self.scores[user.id] = rec
        if rec.get("last_daily") == today:
            await reply("📅 Gunluk odulunu bugun aldin! Yarin tekrar gel.")
            return
        rec["last_daily"] = today
        rec["username"] = sender
        self._add_score(user.id, sender, DAILY_REWARD)
        await reply(
            "🎁 Gunluk odul: +%d puan! Toplam puanin: %d"
            % (DAILY_REWARD, int(self.scores.get(user.id, {}).get("score", 0)))
        )

    async def _cmd_sil(self, user, sender, arg, reply):
        if not self._is_kurucu(user.id, sender):
            await reply("-sil sadece kurucular icin.")
            return
        parts = arg.split()
        if len(parts) < 2:
            await reply("Kullanim: -sil @kisi <puan>")
            return
        try:
            amount = int(parts[1])
        except ValueError:
            await reply("Puan miktari sayi olmali.")
            return
        if amount <= 0:
            await reply("Gecerli bir puan miktari gir.")
            return
        q = parts[0].lstrip("@").lower()
        target = self._find_user(q)
        if target is not None:
            disp = target.username
            rec = self.scores.get(target.id)
            if rec is None:
                rec = {"username": target.username, "score": 0, "id": target.id}
                self.scores[target.id] = rec
        else:
            rec = None
            for r in self.scores.values():
                if str(r.get("username", "")).lower() == q:
                    rec = r
                    break
            if rec is None:
                await reply("'%s' bulunamadi (odada degil ve kaydi yok)." % q)
                return
            disp = str(rec.get("username", q))
        cur = int(rec.get("score", 0))
        silinen = min(cur, amount)
        rec["score"] = cur - silinen
        self._save_scores()
        await reply(
            "🗑️ @%s kisisinden %d puan silindi. Kalan: %d" % (disp, silinen, rec["score"])
        )

    @staticmethod
    def _fmt_vip_time(sec):
        sec = max(0, int(sec))
        h, rem = divmod(sec, 3600)
        m = rem // 60
        if h:
            return "%d sa %d dk" % (h, m)
        return "%d dk" % m

    async def _cmd_puanal(self, user, sender, arg, reply):
        parts = (arg or "").split()
        key = sender.lower()
        if not parts:
            lines = ["👑 **VIP PLANLARI** (puan ile)"]
            for _pk, (label, days, cost) in VIP_PLANS.items():
                lines.append("• %s → %d puan" % (label, cost))
            left = int(self.vip_until.get(key, 0) or 0) - time.time()
            if left > 0:
                lines.append("Kalan VIP suren: %s" % self._fmt_vip_time(left))
            lines.append("Puanin: %d" % int(self.scores.get(user.id, {}).get("score", 0)))
            lines.append("Kullanim: -puanal <sure>  (orn: -puanal 20)")
            lines.append("💳 Gold ile: bota gold at (fiyatlar ayni)")
            await reply("\n".join(lines))
            return
        plan_key = parts[0].lower()
        if plan_key not in VIP_PLANS:
            await reply("Gecerli sureler: %s. Liste icin: -vipal" % ", ".join(VIP_PLANS))
            return
        label, days, cost = VIP_PLANS[plan_key]
        current = self.roles.get(key, "")
        if ROLE_LEVELS.get(current, 0) >= 2:
            await reply(
                "Zaten %s rolu varsin, VIP almana gerek yok." % ROLE_LABELS.get(current, "yuksek")
            )
            return
        kurucu = self._is_kurucu(user.id, sender)
        paid_text = ""
        if not kurucu:
            score = int(self.scores.get(user.id, {}).get("score", 0))
            if score < cost:
                await reply(
                    "%s VIP icin %d puan gerekli! Mevcut puanin: %d (-daily ve kelime oyunuyla kazan)"
                    % (label, cost, score)
                )
                return
            self._add_score(user.id, sender, -cost)
            paid_text = " (-%d puan)" % cost
        now = time.time()
        base = int(self.vip_until.get(key, 0) or 0)
        start = base if base > now else now
        new_until = start + days * VIP_DURATION
        self.vip_until[key] = new_until
        dur_text = self._fmt_vip_time(new_until - now)
        self.roles[key] = "vip"
        self._save_roles()
        self._write_json(self.vip_path, self.vip_until)
        await reply(
            "👑 @%s VIP oldu (%s)!%s Kalan sure: %s"
            % (sender, label, paid_text, dur_text)
        )

    async def _vip_try_purchase(self, uid, name, added=0):
        """Kullaniciya gelen goldlarla alabilecegi VIP planlarini otomatik alir."""
        key = name.lower()
        rec = self.vip_gold.get(uid) or {"username": name, "gold": 0}
        bal = int(rec.get("gold", 0))
        bought = []
        changed = True
        while changed:
            changed = False
            if ROLE_LEVELS.get(self.roles.get(key, ""), 0) >= 2:
                break
            for pk in sorted(VIP_PLANS, key=lambda k: -VIP_PLANS[k][2]):
                label, days, cost = VIP_PLANS[pk]
                if bal < cost:
                    continue
                bal -= cost
                now = time.time()
                base = int(self.vip_until.get(key, 0) or 0)
                start = base if base > now else now
                self.vip_until[key] = start + days * VIP_DURATION
                self.roles[key] = "vip"
                bought.append((label, cost))
                changed = True
                break
        if bought:
            self._save_roles()
            self._write_json(self.vip_path, self.vip_until)
            left = int(self.vip_until[key]) - time.time()
            try:
                await self.highrise.chat(
                    "👑 @%s %d gold ile VIP aldi (%s)! Kalan sure: %s"
                    % (
                        name,
                        sum(c for _l, c in bought),
                        ", ".join(label for label, _c in bought),
                        self._fmt_vip_time(left),
                    )
                )
            except Exception as err:
                log.debug("vip gold duyuru: %s", err)
            try:
                await self.highrise.send_whisper(
                    uid,
                    "👑 Gold odemen alindi! VIP aktif: %s. Kalan sure: %s"
                    % (
                        ", ".join(label for label, _c in bought),
                        self._fmt_vip_time(left),
                    ),
                )
            except Exception as err:
                log.debug("vip gold whisper: %s", err)
        else:
            try:
                await self.highrise.send_whisper(
                    uid,
                    "💰 +%d gold hesabina eklendi (toplam: %d). Planlar icin: -puanal"
                    % (added, bal),
                )
            except Exception as err:
                log.debug("vip gold whisper2: %s", err)
        rec["gold"] = bal
        self.vip_gold[uid] = rec
        self._write_json(self.gold_path, self.vip_gold)

    async def on_tip(self, sender, receiver, amount):
        """Odadaki tipleri izler; bota gelen goldlar VIP planlarina donusur."""
        try:
            rid = getattr(receiver, "id", None)
            rname = (getattr(receiver, "username", "") or "").lower()
            uid = getattr(sender, "id", "")
            name = getattr(sender, "username", "?") or "?"
            amt = int(amount or 0)
            if not uid or amt <= 0:
                return
            log.info(
                "tip algilandi: @%s -> @%s (%d gold)",
                name,
                rname or (rid or "?"),
                amt,
            )
            if rid != self.bot_id:
                return
            rec = self.vip_gold.get(uid) or {"username": name, "gold": 0}
            rec["username"] = name
            rec["gold"] = int(rec.get("gold", 0)) + amt
            self.vip_gold[uid] = rec
            self._write_json(self.gold_path, self.vip_gold)
            await self._vip_try_purchase(uid, name, amt)
        except Exception as err:
            log.debug("on_tip hatasi: %s", err)

    async def _cmd_roledel(self, user, sender, arg, reply):
        if not self._is_kurucu(user.id, sender):
            await reply("-roledel sadece kurucular icin.")
            return
        q = (arg or "").strip().lstrip("@").lower()
        if not q:
            await reply("Kullanim: -roledel @nick")
            return
        if q == self.owner_username:
            await reply("Kurucunun rolu alinamaz.")
            return
        old = self.roles.pop(q, None)
        self.vip_until.pop(q, None)
        self._write_json(self.vip_path, self.vip_until)
        if old is None:
            await reply("@%s zaten rolsuz." % q)
            return
        self._save_roles()
        await reply("🚫 @%s kullanicisinin rolu alindi (%s)." % (q, ROLE_LABELS.get(old, old)))

    async def _vip_sweeper(self):
        while True:
            try:
                await asyncio.sleep(60)
                now = time.time()
                expired = [k for k, until in self.vip_until.items() if now >= until]
                if not expired:
                    continue
                for k in expired:
                    del self.vip_until[k]
                    was_vip = self.roles.get(k) == "vip"
                    if was_vip:
                        del self.roles[k]
                    log.info("VIP suresi doldu: %s", k)
                    try:
                        for u, _p in self.room_user_cache:
                            if u.username and u.username.lower() == k:
                                msg = (
                                    "⌛ VIP suresin doldu, rolu geri alindi."
                                    if was_vip
                                    else "⌛ VIP suresin doldu."
                                )
                                await self.highrise.send_whisper(u.id, msg)
                                break
                    except Exception as err:
                        log.debug("vip bitis whisper: %s", err)
                self._save_roles()
                self._write_json(self.vip_path, self.vip_until)
            except asyncio.CancelledError:
                return
            except Exception as err:
                log.warning("vip sweeper hatasi: %s", err)

    async def _cmd_give(self, user, sender, arg, reply):
        if not self._is_owner_cmd(user.id, sender):
            await reply("Rol verme yetkisi sadece kurucuda (@%s)." % self.owner_username.lstrip("@"))
            return
        parts = arg.split()
        if len(parts) < 2:
            await reply("Kullanim: -give @kullanici <rol>")
            return
        target = self._find_user(parts[0])
        if target is None:
            await reply("Hedef odada bulunamadi.")
            return
        rol = parts[1].lower()
        if rol not in ROLE_LEVELS:
            await reply("Gecersiz rol: %s. Gecerli roller: vip, admin, yonetici, kurucu" % rol)
            return
        self.roles[target.username.lower()] = rol
        self._save_roles()
        await reply("@%s artik %s" % (target.username, ROLE_LABELS[rol]))

    # ---------- oda degistirme ----------

    async def _cmd_oda(self, user, sender, arg, reply):
        # sadece owner + sadece DM
        if not getattr(self, "_cmd_whisper", False):
            await reply("-oda sadece DM'den calisir. Lutfen bana gizli mesaj at.")
            return
        if not self._is_baba(user.id, sender):
            await reply("-oda sadece @%s icin." % self.owner_username)
            return
        self._save_room_pass(self._current_room_id())
        rooms = self._load_rooms()
        rid = (arg or "").strip()
        if not rid:
            # liste goster
            if not rooms:
                await reply("Kayitli oda yok. Kullanim:\n-oda <oda idsi>  → kaydedip gec\n-oda 1 / -oda 2  → kayitli odalardan sec")
                return
            lines = ["🏠 Kayitli odalar (numarali):"]
            for num, info in rooms.items():
                nm = info.get("name") or ("Oda %s" % info["id"])
                lines.append("%s: %s (%s)" % (num, nm, info["id"]))
            lines.append("\nGecmek icin: -oda <numara>")
            await reply("\n".join(lines))
            return
        # sayisal secim
        if rid.isdigit():
            info = rooms.get(str(int(rid)))
            if info is None:
                await reply("%s numarali kayitli oda bulunamadi. -oda ile listeye bak." % rid)
                return
            await self._switch_to_room(info["id"], reply)
            return
        # dogrudan id
        if len(rid) < 16 or not all(c.isalnum() or c == "-" for c in rid):
            await reply("Kullanim: -oda <numara> veya -oda <oda idsi>")
            return
        await self._switch_to_room(rid, reply)

    async def _cmd_degis(self, user, sender, arg, reply):
        # sadece owner + sadece DM
        if not getattr(self, "_cmd_whisper", False):
            await reply("-degis sadece DM'den calisir. Lutfen bana gizli mesaj at.")
            return
        if not self._is_baba(user.id, sender):
            await reply("-degis sadece @%s icin." % self.owner_username)
            return
        rid = (arg or "").strip()
        if len(rid) < 16 or not all(c.isalnum() or c == "-" for c in rid):
            await reply("Kullanim: -degis <oda idsi>\nOrnek: -degis 6a83afe77bc3d51abe4b900a")
            return
        if rid == self._current_room_id():
            await reply("Bot zaten bu odada.")
            return
        self._save_room_pass(rid)
        await self._switch_to_room(rid, reply)

    # ---------- oda kayit / gecis yardimcilari ----------

    async def _cmd_oda_ad(self, user, sender, arg, reply):
        if not getattr(self, "_cmd_whisper", False):
            await reply("-oda-ad sadece DM'den calisir. Lutfen bana gizli mesaj at.")
            return
        if not self._is_baba(user.id, sender):
            await reply("-oda-ad sadece @%s icin." % self.owner_username)
            return
        parts = (arg or "").split(None, 1)
        if len(parts) != 2 or not parts[0].isdigit():
            await reply("Kullanim: -oda-ad <numara> <oda adi>\nOrnek: -oda-ad 1 Ana Radyo")
            return
        num = str(int(parts[0]))
        rooms = self._load_rooms()
        if num not in rooms:
            await reply("%s numarali kayitli oda bulunamadi. -oda ile listeye bak." % num)
            return
        rooms[num]["name"] = parts[1].strip()
        try:
            hr = self.radio.config.setdefault("highrise", {})
            hr["rooms"] = rooms
            self.radio._save_config()
        except Exception as err:
            await reply("Ad kaydedilemedi: %s" % err)
            return
        await reply("✅ %s numarali odaya ad verildi: %s" % (num, parts[1].strip()))

    def _current_room_id(self):
        try:
            return (self.radio.config.get("highrise", {}) or {}).get("room_id", "")
        except Exception:
            return ""

    def _load_rooms(self):
        try:
            hr = self.radio.config.get("highrise", {}) or {}
            rooms = hr.get("rooms") or {}
        except Exception:
            rooms = {}
        out = {}
        for k, v in rooms.items():
            num = str(k)
            if isinstance(v, dict) and v.get("id"):
                out[num] = {"id": v["id"], "name": v.get("name") or ""}
            elif isinstance(v, str) and len(v) >= 16:
                out[num] = {"id": v, "name": ""}
        return out

    def _save_room_pass(self, rid):
        """Botun gectigi odayi kayitli listeye ekler (varsa gunceller)."""
        if not rid or len(rid) < 16:
            return
        rooms = self._load_rooms()
        for num, info in rooms.items():
            if info["id"] == rid:
                return  # zaten kayitli
        free = 1
        while str(free) in rooms:
            free += 1
        rooms[str(free)] = {"id": rid, "name": ""}
        try:
            hr = self.radio.config.setdefault("highrise", {})
            hr["rooms"] = rooms
            self.radio._save_config()
        except Exception as err:
            log.debug("oda kaydi yazilamadi: %s", err)

    async def _switch_to_room(self, rid, reply):
        if rid == self._current_room_id():
            await reply("Bot zaten bu odada.")
            return
        self.radio.save_room_id(rid)
        await reply("🔄 Odaya geciliyor: %s\nBot birkac saniye icinde yeniden baslayacak." % rid)
        await asyncio.sleep(2)
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # ---------- sira yukseltme ----------

    async def _cmd_up(self, user, sender, arg, reply):
        cost = 100
        if not self._is_kurucu(user.id, sender):
            score = self.scores.get(user.id, {}).get("score", 0)
            if score < cost:
                await reply("-up icin %d puan gerekli! Mevcut puanin: %d" % (cost, score))
                return
        ok, text = self.radio.bump_up_text(sender)
        if ok:
            if not self._is_kurucu(user.id, sender):
                self._add_score(user.id, sender, -cost)
                text += " (-%d puan)" % cost
        await reply(text)

    # ---------- tp ----------

    async def _cmd_summ(self, user, sender, arg, reply):
        if self._role_level(sender) < 2:
            await reply("-summ sadece admin+ icin (VIP kullanamaz).")
            return
        await self._refresh_room_users()
        parts = arg.split()
        if not parts:
            await reply(
                "Kullanim:\n"
                "-summ @isim → yanina cek\n"
                "-summ @isim 999 99 9 → koordinata firlat\n"
                "-summ @isim kat1|kat2|vip → o bolgeye gonder"
            )
            return
        target = self._find_user(parts[0])
        if target is None or target.id == user.id:
            await reply("Kullanici bulunamadi: %s" % parts[0])
            return
        rest = parts[1:]
        pos = None
        yer_adi = None
        floats = []
        for p in rest[:3]:
            try:
                floats.append(float(p))
            except ValueError:
                floats = []
                break
        if len(floats) == 3:
            pos = Position(floats[0], floats[1], floats[2], "FrontRight")
            yer_adi = "%s, %s, %s koordinati" % tuple(int(f) if f == int(f) else f for f in floats)
        elif rest:
            anahtar = rest[0].lower().lstrip("-")
            yerler = {
                "kat1": ("kat1_position", "1. kat"),
                "kat2": ("kat2_position", "2. kat"),
                "vip": ("vip_position", "VIP alani"),
            }
            if anahtar in yerler:
                attr, ad = yerler[anahtar]
                pos = getattr(self, attr)
                yer_adi = ad
        if pos is not None:
            try:
                await self.highrise.teleport(target.id, pos)
                await reply("@%s, @%s kisisini %s'e gonderdi 🚀" % (sender, target.username, yer_adi))
            except Exception as err:
                await reply("Gonderilemedi: %s" % err)
            return
        mypos = None
        lm = self._last_move.get(user.id)
        if isinstance(lm, Position):
            mypos = lm
        if mypos is None:
            for u, p in self.room_user_cache:
                if u.id == user.id:
                    mypos = p
                    break
        if mypos is None:
            await reply("Konumun bulunamadi.")
            return
        try:
            await self.highrise.teleport(
                target.id, Position(mypos.x, mypos.y, mypos.z, getattr(mypos, "facing", None))
            )
            await reply("@%s @%s kisisinin yanina cekildi." % (target.username, sender))
        except Exception as err:
            await reply("Isinlama basarisiz: %s" % err)

    async def _cmd_tp(self, user, sender, arg, reply):
        if self._role_level(sender) < 1:
            await reply("-tp sadece rollu kullanicilara acik (VIP+).")
            return
        await self._refresh_room_users()
        parts = (arg or "").split()
        if parts:
            floats = []
            for p in parts[:3]:
                try:
                    floats.append(float(p))
                except ValueError:
                    floats = []
                    break
            if len(floats) == 3:
                fmt = tuple(int(f) if f == int(f) else f for f in floats)
                try:
                    await self.highrise.teleport(
                        user.id, Position(floats[0], floats[1], floats[2], "FrontRight")
                    )
                    await reply("@%s %s koordinatina isinlandi." % (sender, ", ".join(str(v) for v in fmt)))
                except Exception as err:
                    await reply("Isinlama basarisiz: %s" % err)
                return
        target = self._find_user(arg)
        if target is None or target.id == user.id:
            await reply("Kullanim: -tp @isim → o kisinin yanina git | -tp 9.5 0.25 12.5 → o koordinata isinlan")
            return
        pos = self._last_move.get(target.id)
        if not isinstance(pos, Position):
            for u, p in self.room_user_cache:
                if u.id == target.id:
                    pos = p
                    break
        if pos is None:
            await reply("@%s kisisinin konumu bulunamadi." % target.username)
            return
        try:
            await self.highrise.teleport(
                user.id, Position(pos.x, pos.y, pos.z, getattr(pos, "facing", None))
            )
            await reply("@%s, @%s kisisinin yanina isinlandi." % (sender, target.username))
        except Exception as err:
            await reply("Isinlama basarisiz: %s" % err)

    # ---------- kelime oyunu ----------

    def _level_for_len(self, length):
        if length <= 6:
            return "kolay"
        if length <= 8:
            return "orta"
        return "zor"

    async def _start_word_game(self):
        await asyncio.sleep(3)
        if not self.word_game_enabled:
            return
        try:
            await self.highrise.chat(
                "**KELIME OYUNU BASLADI!** Her 10 saniyede 1 harf acilacak! Cevabi yaz, +10 puan!"
            )
        except Exception as err:
            log.debug("kelime duyurusu gonderilemedi: %s", err)
        await self._ask_question()

    async def _ask_question(self):
        if not self.word_game_enabled:
            self.game_active = False
            return
        if self.letter_task:
            self.letter_task.cancel()
            self.letter_task = None
        self.current_category = get_random_category()
        self.current_word = get_random_word(self.current_category)
        self.current_level = self._level_for_len(len(self.current_word))
        self.revealed_letters = []
        self.game_active = True
        emoji, label = {
            "kolay": ("🟢", "KOLAY"),
            "orta": ("🟠", "ORTA"),
            "zor": ("🔴", "ZOR"),
        }[self.current_level]
        try:
            cat_color = get_category_color(self.current_category)
            await self.highrise.chat(
                "%s **SORU**\n\n%s **SEVIYE: %s** | **KATEGORI: %s**\n**Kelime (%d harf):** %s\n\nCevabi yaz, dogru bil +10 puan!"
                % (
                    cat_color,
                    emoji,
                    label,
                    self.current_category.upper(),
                    len(self.current_word),
                    self._show_word(),
                )
            )
        except Exception as err:
            log.debug("kelime sorusu gonderilemedi: %s", err)
        self.letter_task = asyncio.create_task(self._letter_ticker())

    def _show_word(self):
        return " ".join(
            c.upper() if i in self.revealed_letters else "_"
            for i, c in enumerate(self.current_word)
        )

    def _hidden_count(self):
        return len(self.current_word) - len(self.revealed_letters)

    def _reveal_one_letter(self):
        hidden = [i for i in range(len(self.current_word)) if i not in self.revealed_letters]
        if not hidden:
            return None
        idx = random.choice(hidden)
        self.revealed_letters.append(idx)
        return self.current_word[idx]

    async def _letter_ticker(self):
        try:
            while True:
                await asyncio.sleep(10)
                if self.game_paused or not self.game_active:
                    self.letter_task = None
                    return
                if self._hidden_count() <= 2:
                    self.game_active = False
                    self.letter_task = None
                    await self.highrise.chat(
                        "⏰ Sure doldu! Cevap: **%s**\n\n%s"
                        % (self.current_word.upper(), self._show_word())
                    )
                    await asyncio.sleep(3)
                    await self._ask_question()
                    return
                harf = self._reveal_one_letter()
                if harf:
                    await self.highrise.chat(
                        "⏳ **%s** harfi acildi! %s" % (harf.upper(), self._show_word())
                    )
        except asyncio.CancelledError:
            pass

    @staticmethod
    def _norm_tr(text):
        """Turkce karakter ve buyuk/kucuk harf duyarsiz normalizasyon."""
        t = (text or "").strip().lower()
        t = t.translate(
            str.maketrans({
                "ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c",
                "â": "a", "î": "i", "û": "u",
            })
        )
        t = unicodedata.normalize("NFKD", t)
        return "".join(ch for ch in t if not unicodedata.combining(ch))

    async def _check_word_answer(self, user, message):
        if not self.game_active or self.game_paused:
            return False
        if self._norm_tr(message) != self._norm_tr(self.current_word):
            return False
        self.game_active = False
        if self.letter_task:
            self.letter_task.cancel()
            self.letter_task = None
        self._add_score(user.id, user.username or user.id, 10)
        total = self.scores.get(user.id, {}).get("score", 10)
        try:
            await self.highrise.chat(
                "**DOGRU!** ✅\n\n**Kelime:** %s\n**Bilen:** @%s\n**Puan:** +10\n**Toplam:** %d"
                % (self.current_word.upper(), user.username, total)
            )
        except Exception as err:
            log.debug("kelime cevabi gonderilemedi: %s", err)
        await asyncio.sleep(2)
        await self._ask_question()
        return True

    async def _cmd_emoteall(self, user, sender, arg, reply):
        if self._role_level(sender) < 2:
            await reply("-emoteall sadece admin ve ustunun komutu.")
            return
        text = (arg or "").strip()
        emote = find_emote(text) if text else None
        if emote is None:
            await reply(
                "Kullanim: -emoteall <emote adi/numara>  (orn: -emoteall tiktok)"
            )
            return
        try:
            people = await self.highrise.get_room_users()
            items = people.content or []
        except Exception as err:
            log.warning("emoteall kullanici listesi: %s", err)
            await reply("Odadaki kisiler alinamadi.")
            return
        count = 0
        for it in items:
            try:
                if isinstance(it, (tuple, list)) and len(it) >= 1:
                    u = it[0]
                else:
                    u = it
                await self.highrise.send_emote(emote["id"], u.id)
                count += 1
                await asyncio.sleep(0.1)
            except Exception as err:
                log.debug("emoteall (%s): %s", getattr(u, "username", u.id), err)
        await reply("🕺 '%s' -> %d kisiye gonderildi!" % (emote["name"], count))

    async def _cmd_double(self, user, sender, arg, reply):
        if self._role_level(sender) < 1:
            await reply("-double sadece VIP ve ustunun komutu.")
            return
        parts = (arg or "").strip().split(None, 1)
        if len(parts) < 2:
            await reply("Kullanim: -double @kisi <emote>  (orn: -double @ali floss)")
            return
        nick, etext = parts[0], parts[1].strip()
        target = self._find_user(nick)
        if target is None:
            await reply("'%s' odada bulunamadi." % nick.lstrip("@"))
            return
        emote = find_emote(etext)
        if emote is None:
            await reply(
                "Emote bulunamadi: %s (-emote ara %s)" % (etext.split()[0], etext.split()[0])
            )
            return
        for uid in dict.fromkeys((user.id, target.id)):
            old = self.emote_loops.pop(uid, None)
            if old:
                old.cancel()
            old_partner = self.emote_pairs.pop(uid, None)
            if old_partner:
                self.emote_pairs.pop(old_partner, None)
                ptask = self.emote_loops.pop(old_partner, None)
                if ptask:
                    ptask.cancel()
        work = await self._resolve_emote(user.id, emote)
        if work is None:
            try:
                await self.highrise.send_whisper(user.id, "❌ Emote oynatilamadi: %s" % emote["name"])
            except Exception as err:
                log.debug("double whisper: %s", err)
            return
        for uid in dict.fromkeys((user.id, target.id)):
            self.emote_loops[uid] = asyncio.create_task(
                self._emote_loop(uid, work, emote["duration"])
            )
        self.emote_pairs[user.id] = target.id
        self.emote_pairs[target.id] = user.id
        await reply(
            "💃 @%s ve @%s birlikte '%s' yapiyor! (durdurmak icin: stop) 🎶"
            % (sender, target.username, emote["name"])
        )

    def _set_word_game_enabled(self, enabled):
        self.word_game_enabled = enabled
        data = self._read_json(self.settings_path, {})
        data["word_game"] = enabled
        self._write_json(self.settings_path, data)

    async def _cmd_dur(self, user, sender, arg, reply):
        self.game_paused = True
        if self.letter_task:
            self.letter_task.cancel()
            self.letter_task = None
        if self.ask_task:
            self.ask_task.cancel()
            self.ask_task = None
        await reply("⏸️ Kelime oyunu durduruldu. Devam etmek icin -start yaz.")

    async def _cmd_start(self, user, sender, arg, reply):
        if not self.word_game_enabled:
            await reply("⛔ Kelime oyunu kalici olarak kapali. Acmak icin: -ac")
            return
        self.game_paused = False
        self.game_active = False
        if self.letter_task:
            self.letter_task.cancel()
            self.letter_task = None
        if self.ask_task:
            self.ask_task.cancel()
            self.ask_task = None
        await reply("▶️ Kelime oyunu baslatildi!")
        self.ask_task = asyncio.create_task(self._start_word_game())

    async def _cmd_kapat(self, user, sender, arg, reply):
        if not self._is_kurucu(user.id, sender):
            await reply("⛔ Bu komut sadece kurucu icin.")
            return
        self._set_word_game_enabled(False)
        self.game_paused = True
        self.game_active = False
        if self.letter_task:
            self.letter_task.cancel()
            self.letter_task = None
        if self.ask_task:
            self.ask_task.cancel()
            self.ask_task = None
        await reply("⛔ Kelime oyunu KALICI olarak kapatildi (restart sonrasi de acilmaz). Acmak icin: -ac")

    async def _cmd_ac(self, user, sender, arg, reply):
        if not self._is_kurucu(user.id, sender):
            await reply("⛔ Bu komut sadece kurucu icin.")
            return
        self._set_word_game_enabled(True)
        await reply("✅ Kelime oyunu kalici olarak acildi!")
        await self._cmd_start(user, sender, arg, reply)

    # ---------- moderasyon ----------

    async def _mod_check(self, user, sender, reply):
        if self._role_level(sender) >= 2 or self._is_owner_cmd(user.id, sender):
            return True
        await reply("Bu komut sadece modlar ve kurucu icin.")
        return False

    async def _moderate(self, target_id, action, length=None):
        await self.highrise.moderate_room(target_id, action, length)

    async def _cmd_kick(self, user, sender, arg, reply):
        if not await self._mod_check(user, sender, reply):
            return
        target = self._find_user(arg)
        if target is None:
            await reply("Kullanim: -kick @isim")
            return
        try:
            await self._moderate(target.id, "kick")
            await reply("@%s odadan kicklendi." % target.username)
        except Exception as err:
            await reply("Kick basarisiz: %s" % err)

    async def _cmd_ban(self, user, sender, arg, reply):
        if not await self._mod_check(user, sender, reply):
            return
        parts = arg.split()
        if not parts:
            await reply("Kullanim: -ban @isim [dakika]")
            return
        target = self._find_user(parts[0])
        if target is None:
            await reply("@%s odada bulunamadi." % parts[0].lstrip("@"))
            return
        minutes = 5
        if len(parts) > 1:
            try:
                minutes = int(parts[1])
            except ValueError:
                await reply("Dakika sayi olmali.")
                return
        length = max(60, min(minutes * 60, 2592000))
        try:
            await self._moderate(target.id, "ban", length)
            await reply("@%s %d dakika banlandi." % (target.username, length // 60))
        except Exception as err:
            await reply("Ban basarisiz: %s" % err)

    async def _cmd_mute(self, user, sender, arg, reply):
        if not await self._mod_check(user, sender, reply):
            return
        parts = arg.split()
        if not parts:
            await reply("Kullanim: -mute @isim [dakika]")
            return
        target = self._find_user(parts[0])
        if target is None:
            await reply("@%s odada bulunamadi." % parts[0].lstrip("@"))
            return
        minutes = 5
        if len(parts) > 1:
            try:
                minutes = int(parts[1])
            except ValueError:
                await reply("Dakika sayi olmali.")
                return
        length = max(60, min(minutes * 60, 3600))
        try:
            await self._moderate(target.id, "mute", length)
            await reply("@%s %d dakika mutelendi." % (target.username, length // 60))
        except Exception as err:
            await reply("Mute basarisiz: %s" % err)

    async def _cmd_unmute(self, user, sender, arg, reply):
        if not await self._mod_check(user, sender, reply):
            return
        target = self._find_user(arg)
        if target is None:
            await reply("Kullanim: -unmute @isim")
            return
        try:
            await self._moderate(target.id, "mute", 0)
            await reply("@%s unmute edildi." % target.username)
        except Exception as err:
            await reply("Unmute basarisiz: %s" % err)

    async def _cmd_unban(self, user, sender, arg, reply):
        if not await self._mod_check(user, sender, reply):
            return
        target = self._find_user(arg)
        if target is None:
            await reply("Kullanim: -unban @isim (kisi odada olmali)")
            return
        try:
            await self._moderate(target.id, "unban")
            await reply("@%s unban edildi." % target.username)
        except Exception as err:
            await reply("Unban basarisiz: %s" % err)

    # ---------- freeze / unfreeze ----------

    def _player_position(self, user_id):
        pos = self._last_move.get(user_id)
        if isinstance(pos, Position):
            return pos
        for user, p in self.room_user_cache:
            if user.id == user_id and isinstance(p, Position):
                return p
        return None

    async def _cmd_freeze(self, user, sender, arg, reply):
        if not self._is_kurucu(user.id, sender):
            await reply("⛔ -freeze sadece kurucuya ozel (@%s)." % self.owner_username)
            return
        target = self._find_user(arg)
        if target is None:
            await reply("Kullanim: -freeze @isim")
            return
        if target.username and target.username.lower() == self.owner_username:
            await reply("⛔ @%s dondurulamaz." % target.username)
            return
        pos = self._player_position(target.id)
        if pos is None:
            await reply("@%s konumu bulunamadi." % target.username)
            return
        self.frozen[target.id] = pos
        try:
            await self.highrise.teleport(target.id, pos)
        except Exception as err:
            log.debug("freeze teleport: %s", err)
        await reply("🧊 @%s donduruldu (hareket edemez). -unfreeze ile kaldir." % target.username)

    async def _cmd_unfreeze(self, user, sender, arg, reply):
        if not self._is_kurucu(user.id, sender):
            await reply("⛔ -unfreeze sadece kurucuya ozel (@%s)." % self.owner_username)
            return
        target = self._find_user(arg)
        if target is None:
            await reply("Kullanim: -unfreeze @isim")
            return
        if target.id in self.frozen:
            del self.frozen[target.id]
            await reply("✅ @%s cozuldu, artik serbest." % target.username)
        else:
            await reply("@%s donmus degil." % target.username)

    # ---------- DM abone duyurulari ----------

    def _subscriber_ids(self):
        return [str(s["user_id"]) for s in self.subscribers.values()]

    async def _cmd_aboneler(self, user, sender, arg, reply):
        if self._role_level(sender) < 2:
            await reply("-aboneler sadece admin ve ustunun komutu.")
            return
        await reply("Toplam abone: %d" % len(self._subscriber_ids()))

    async def _cmd_gonder(self, user, sender, arg, reply):
        if self._role_level(sender) < 2:
            await reply("-gonder sadece admin ve ustunun komutu.")
            return
        text = (arg or "").strip()
        if not text:
            await reply("Kullanim: -gonder <mesaj>  (DM'den abone olanlara mesaj atar)")
            return
        ids = self._subscriber_ids()
        if not ids:
            await reply("Henuz abone yok.")
            return
        try:
            res = await self.highrise.send_message_bulk(ids, text, "text")
            if isinstance(res, Error):
                await reply("Mesaj gonderilemedi: %s" % res.message)
            else:
                log.info("duyuru %d aboneye gonderildi: %s", len(ids), text)
                await reply("Mesaj %d aboneye gonderildi." % len(ids))
        except Exception as err:
            log.error("duyuru gonderilemedi: %s", err)
            await reply("Mesaj gonderilemedi: %s" % err)

    async def _cmd_konum(self, user, sender, arg, reply):
        if self._role_level(sender) < 2:
            await reply("-konum sadece admin ve ustunun komutu.")
            return
        text = (arg or "").strip()
        if not text:
            await reply("Kullanim: -konum <mesaj>  (DM'den abone olanlara oda daveti atar)")
            return
        ids = self._subscriber_ids()
        if not ids:
            await reply("Henuz abone yok.")
            return
        room_id = self._current_room_id()
        try:
            res = await self.highrise.send_message_bulk(
                ids, text, "invite", room_id=room_id
            )
            if isinstance(res, Error):
                await reply("Davet gonderilemedi: %s" % res.message)
            else:
                log.info("davet %d aboneye gonderildi (oda %s): %s", len(ids), room_id, text)
                await reply("Davet %d aboneye gonderildi." % len(ids))
        except Exception as err:
            log.error("davet gonderilemedi: %s", err)
            await reply("Davet gonderilemedi: %s" % err)

    # ---------- chat loop ----------

    async def _cmd_loop(self, user, sender, arg, reply):
        if not self._is_kurucu(user.id, sender):
            await reply("⛔ Bu komut sadece kurucu icin.")
            return
        if not arg or arg.strip().lower() in ("stop", "kapat", "dur"):
            vardi = self.chat_loop_task and not self.chat_loop_task.done()
            self._stop_chat_loop()
            if vardi:
                await reply("🔄 Loop durduruldu.")
            else:
                await reply("Aktif loop yok.")
            return
        parts = arg.rsplit(None, 1)
        if len(parts) < 2:
            await reply("Kullanim: -loop <mesaj> <sure>  (orn: -loop selam 5dk / -loop merhaba 30sn)")
            return
        msg, sure_text = parts[0], parts[1].strip().lower()
        sec = 0
        if sure_text.endswith("dk"):
            try:
                sec = int(sure_text[:-2]) * 60
            except ValueError:
                pass
        elif sure_text.endswith("sn"):
            try:
                sec = int(sure_text[:-2])
            except ValueError:
                pass
        elif sure_text.endswith("sa"):
            try:
                sec = int(sure_text[:-2]) * 3600
            except ValueError:
                pass
        if sec < 10 or sec > 86400:
            await reply("Gecersiz sure. Minimum 10sn, maksimum 24saat. Orn: 5dk, 30sn, 2sa")
            return
        self._start_chat_loop(msg, sec)
        if sec >= 3600:
            sure_goster = "%d saat" % (sec // 3600)
        elif sec >= 60:
            sure_goster = "%d dk" % (sec // 60)
        else:
            sure_goster = "%d sn" % sec
        await reply("🔄 Loop kalici baslatildi: '%s' her %s (-loopstop ile durur)"
                    % (msg, sure_goster))

    async def _cmd_loopstop(self, user, sender, arg, reply):
        if not self._is_kurucu(user.id, sender):
            await reply("⛔ Bu komut sadece kurucu icin.")
            return
        vardi = self.chat_loop_task and not self.chat_loop_task.done()
        self._stop_chat_loop()
        if vardi:
            await reply("🔄 Loop durduruldu.")
        else:
            await reply("Aktif loop yok.")

    def _start_chat_loop(self, msg, sec):
        if self.chat_loop_task and not self.chat_loop_task.done():
            self.chat_loop_task.cancel()
        self.chat_loop_msg = msg
        self.chat_loop_sec = sec
        self.chat_loop_data = {"msg": msg, "sec": sec}
        self._write_json(self.chat_loop_path, self.chat_loop_data)

        async def _loop():
            try:
                while True:
                    await asyncio.sleep(self.chat_loop_sec)
                    try:
                        await self.highrise.chat(self.chat_loop_msg)
                    except Exception as err:
                        log.debug("loop mesaji gonderilemedi: %s", err)
            except asyncio.CancelledError:
                pass

        self.chat_loop_task = asyncio.create_task(_loop())
        log.info("chat loop baslatildi: %r (%ds)", msg, sec)

    def _stop_chat_loop(self):
        if self.chat_loop_task and not self.chat_loop_task.done():
            self.chat_loop_task.cancel()
        self.chat_loop_task = None
        self.chat_loop_msg = None
        self.chat_loop_sec = 0
        self.chat_loop_data = {}
        self._write_json(self.chat_loop_path, {})
