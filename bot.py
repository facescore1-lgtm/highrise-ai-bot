import asyncio
import json
import os
import random
import re

from highrise import BaseBot
from highrise.models import Error, ModerateRoomRequest

from ai import GeminiAI
from music_player import MusicPlayer

PREFIX = "-"
DANCE_EMOTES = [
    "dance-macarena",
    "dance-twerk",
    "dance-ritmo",
    "dance-maniac",
    "dance-armwave",
]
HELP_TEXT = (
    "Komutlar:\n"
    "-help → komut listesi\n"
    "-info [@isim] → kullanıcı bilgisi\n"
    "-room → oda bilgisi\n"
    "-oda <oda_id> → odayı değiştirir (sadece @Slyshader_)\n"
    "-wallet → bot cüzdanı\n"
    "-online → odadaki kullanıcılar\n"
    "-dans / -dance → dans eder\n"
    "-selam / -hi → selam verir\n"
    "-emote <ad> → emote gönderir\n"
    "-tp @isim → o kişiyi yanına ışınlar\n"
    "-kick @isim → odadan atar (mod)\n"
    "-ban @isim → yasaklar (mod)\n"
    "-unban @isim → yasağı kaldırır (mod)\n"
    "-mute @isim [dakika] → susturur (mod)\n"
    "-unmute @isim → susturmayı kaldırır (mod)\n"
    "-p <şarkı> → müzik çalar (YouTube)\n"
    "-q → kuyruğu gösterir\n"
    "-skip → sonraki şarkıya geçer\n"
    "-stop → müziği durdurur\n"
    "-now → çalan şarkıyı gösterir"
)

TR_POP_SONGS = [
    "Tarkan Şımarık",
    "Tarkan Dudu",
    "Sezen Aksu Gülümse",
    "Sıla Vazgeçmem",
    "Hadise Düm Tek Tek",
    "Derya Uluğ Nedenini Sorma",
    "Mabel Matiz Antidepresan",
    "Reynmen Derdim Olsun",
    "Aleyna Tilki Sen Olsan Bari",
    "İlyas Yalçıntaş Unuturum Elbet",
    "Semicenk Batık Gemi",
    "Emir Can İğrek Başka Bi Şey",
    "Sezen Aksu Firuze",
    "Madrigal Seni Dert Etmeler",
    "Simge Miş Miş",
    "Edis Çok Çok",
    "Zeynep Bastık Fırlat Samanyolu'na",
    "Sertab Erener Yanıyor Mu Sana",
]


class Bot(BaseBot):
    def __init__(self, config=None):
        super().__init__()
        self.config = config or {}
        self.ai = GeminiAI(
            api_key=self.config.get("gemini_api_key", ""),
            model=self.config.get("gemini_model", "gemini-3.5-flash"),
        )
        self.owner = self.config.get("owner_name", "")
        self.owner_username = self.config.get("owner_username", "")
        self.owner_id = self.config.get("owner_id")
        self.owner_conv_id = None
        self.history = {}
        self.room_user_cache = []
        self._pending_room_id = None
        self._previous_room_id = None
        self._fallback_room_id = config.get("last_good_room_id") or config.get("_fallback_room_id")
        self._auto_task = None
        self.player = MusicPlayer(config["music"]) if config.get("music") else None

    # ---------- eventler ----------

    async def on_start(self, session_metadata):
        print(f"[bot] Bağlandı. Bot ID: {session_metadata.user_id}")
        await self._refresh_room_users()
        await self._resolve_owner()
        if self.player:
            self.player.on_track = self._on_track
            self.player.on_track_end = self._on_track_end
            self.player.start()
            print("[bot] Müzik sistemi hazır (Icecast + ffmpeg + yt-dlp).")
            if self._auto_task is None:
                self._auto_task = asyncio.create_task(self._auto_worker())

    async def on_user_join(self, user, position):
        print(f"[join] {user.username}")
        try:
            await self.highrise.send_whisper(
                user.id,
                f"Odaya hoş geldin {user.username}! Sana yardımcı olabilirim. Komut listesi için -help yaz.",
            )
        except Exception as e:
            print(f"[join] karşılama gönderilemedi: {e}")

    async def on_chat(self, user, message):
        if message.startswith(PREFIX):
            await self._handle_command(
                user.id, user.username, message,
                lambda text: self.highrise.send_whisper(user.id, text),
            )

    async def on_whisper(self, user, message):
        print(f"[whisper] {user.username}: {message}")
        if self._is_owner(user):
            self._set_owner(user.id)
        await self._forward_to_owner(user, message)
        if message.startswith(PREFIX):
            await self._handle_command(
                user.id, user.username, message,
                lambda text: self.highrise.send_whisper(user.id, text),
            )
            return
        reply = self._ask_gemini(user.id, user.username, message)
        try:
            await self.highrise.send_whisper(user.id, reply)
            print(f"[whisper ->] {user.username}: {reply[:60]}")
        except Exception as e:
            print(f"[whisper] gönderilemedi: {e}")

    async def on_message(self, user_id, conversation_id, is_new_conversation):
        try:
            conv = await self.highrise.get_messages(conversation_id)
            if isinstance(conv, Error):
                print(f"[dm] hata: {conv}")
                return
            message = conv.messages[0].content if conv.messages else ""
            print(f"[dm] {user_id}: {message}")
            if message.startswith(PREFIX):
                await self._handle_command(
                    user_id, "", message,
                    lambda text: self.highrise.send_message(conversation_id, text),
                )
                return
            reply = self._ask_gemini(user_id, user_id, message)
            await self.highrise.send_message(conversation_id, reply)
            print(f"[dm ->] {user_id}: {reply[:60]}")
        except Exception as e:
            print(f"[dm] hata: {e}")

    async def on_moderate(self, moderator_id, target_user_id, moderation_type, duration):
        print(f"[moderate] {moderator_id} -> {target_user_id}: {moderation_type} {duration}")

    # ---------- sahip ----------

    def _is_owner(self, user) -> bool:
        return bool(user.username) and user.username.lower() == self.owner_username.lower()

    def _is_owner_cmd(self, user_id, username) -> bool:
        if self.owner_id and user_id == self.owner_id:
            return True
        return bool(username) and username.lower() == self.owner_username.lower()

    async def _resolve_owner(self):
        if not self.owner_username:
            print("[bot] owner_username config'de yok, iletme kapalı.")
            return
        try:
            for user, _pos in self.room_user_cache:
                if self._is_owner(user):
                    self._set_owner(user.id)
                    return
            print(f"[bot] @{self.owner_username} odada değil; ilk yazdığında yakalanacak.")
        except Exception as e:
            print(f"[bot] Sahip çözülemedi: {e}")

    def _set_owner(self, user_id):
        if self.owner_id == user_id:
            return
        self.owner_id = user_id
        print(f"[bot] Sahip yakalandı: @{self.owner_username} = {self.owner_id}")
        cfg_path = self.config.get("_config_path")
        if not cfg_path:
            return
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            cfg["owner_id"] = user_id
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            print("[bot] owner_id config'e kaydedildi.")
        except Exception as e:
            print(f"[bot] owner_id kaydedilemedi: {e}")

    # ---------- yönlendirme ----------

    async def _forward_to_owner(self, user, message):
        if not self.owner_id or user.id == self.owner_id:
            return
        text = f"@{user.username} fısıltı: {message}"
        try:
            if self.owner_conv_id is None:
                convs = await self.highrise.get_conversations()
                if isinstance(convs, Error):
                    raise RuntimeError(str(convs))
                for conv in convs.conversations or []:
                    if self.owner_id in (conv.member_ids or []):
                        self.owner_conv_id = conv.id
                        break
            if self.owner_conv_id:
                await self.highrise.send_message(self.owner_conv_id, text)
            else:
                await self.highrise.send_whisper(self.owner_id, text)
            print(f"[forward -> @{self.owner_username}] {text[:60]}")
        except Exception as e:
            print(f"[forward] gönderilemedi: {e}")

    # ---------- AI ----------

    def _ask_gemini(self, uid, username, message):
        history = self.history.get(uid, [])
        reply = self.ai.respond(self.owner, username, message, history)
        self.history[uid] = (history + [("other", message), ("owner", reply)])[-20:]
        return reply

    # ---------- komut sistemi ----------

    async def _refresh_room_users(self):
        try:
            resp = await self.highrise.get_room_users()
            if isinstance(resp, Error):
                self.room_user_cache = []
                return
            self.room_user_cache = resp.content
        except Exception as e:
            print(f"[cmd] oda listesi alınamadı: {e}")
            self.room_user_cache = []

    async def _handle_command(self, user_id, username, text, reply):
        try:
            await self._refresh_room_users()
            parts = text[len(PREFIX):].strip().split(maxsplit=1)
            cmd = parts[0].lower() if parts else ""
            args = parts[1].strip() if len(parts) > 1 else ""
            handler = self._commands().get(cmd)
            if handler is None:
                await reply(f"Bilinmeyen komut: -{cmd}. Komut listesi için -help yaz.")
                return
            is_mod = cmd in self._mod_commands()
            if is_mod and not await self._is_moderator(user_id):
                await reply("Bu komut için yetkin yok (sadece sahip ve moderatörler).")
                return
            await handler(user_id, username, args, reply)
        except Exception as e:
            print(f"[cmd] hata: {e}")
            try:
                await reply(f"Komut çalışırken hata oluştu: {e}")
            except Exception:
                pass

    def _commands(self):
        return {
            "help": self._cmd_help,
            "yardim": self._cmd_help,
            "info": self._cmd_info,
            "room": self._cmd_room,
            "oda": self._cmd_room,
            "wallet": self._cmd_wallet,
            "online": self._cmd_online,
            "dans": self._cmd_dance,
            "dance": self._cmd_dance,
            "selam": self._cmd_hi,
            "hi": self._cmd_hi,
            "emote": self._cmd_emote,
            "tp": self._cmd_teleport,
            "teleport": self._cmd_teleport,
            "kick": self._cmd_kick,
            "ban": self._cmd_ban,
            "unban": self._cmd_unban,
            "mute": self._cmd_mute,
            "unmute": self._cmd_unmute,
            "p": self._cmd_music_play,
            "play": self._cmd_music_play,
            "q": self._cmd_music_queue,
            "queue": self._cmd_music_queue,
            "skip": self._cmd_music_skip,
            "next": self._cmd_music_skip,
            "stop": self._cmd_music_stop,
            "now": self._cmd_music_now,
        }

    def _mod_commands(self):
        return {"kick", "ban", "unban", "mute", "unmute"}

    async def _is_moderator(self, user_id) -> bool:
        if self.owner_id and user_id == self.owner_id:
            return True
        try:
            priv = await self.highrise.get_room_privilege(user_id)
            if isinstance(priv, Error):
                return False
            return bool(priv.moderator)
        except Exception:
            return False

    def _find_user(self, args):
        name = args.strip().lstrip("@").lower()
        for user, _pos in self.room_user_cache:
            if user.username.lower() == name:
                return user
        return None

    async def _cmd_help(self, user_id, username, args, reply):
        await reply(HELP_TEXT)

    async def _cmd_info(self, user_id, username, args, reply):
        target = None
        if args.strip():
            target = self._find_user(args)
            if target is None:
                await reply(f"@{args.strip().lstrip('@')} odada bulunamadı.")
                return
        target_id = target.id if target else user_id
        try:
            resp = await self.webapi.get_user(target_id)
            u = resp.user
            active = f" | aktif oda: {u.active_room.room_id}" if u.active_room else ""
            text = (
                f"@{u.username}\n"
                f"ID: {u.user_id}\n"
                f"Bio: {u.bio or '-'}\n"
                f"Katılım: {str(u.joined_at)[:10]}\n"
                f"Takipçi: {u.num_followers} | Takip: {u.num_following} | Arkadaş: {u.num_friends}"
                f"{active}"
            )
            await reply(text)
        except Exception as e:
            await reply(f"Bilgi alınamadı: {e}")

    async def _cmd_room(self, user_id, username, args, reply):
        room_id = args.strip()
        if room_id:
            if not self._is_owner_cmd(user_id, username):
                await reply("Bu komutu sadece @Slyshader_ kullanabilir.")
                return
            await self._switch_room(room_id, reply)
            return
        try:
            resp = await self.webapi.get_room(self.config.get("room_id", ""))
            r = resp.room
            await reply(
                f"Oda: {r.disp_name}\n"
                f"ID: {r.room_id}\n"
                f"Açıklama: {r.description or '-'}\n"
                f"Erişim: {r.access_policy} | Kategori: {r.category}\n"
                f"Bağlı kullanıcı: {r.num_connected}"
            )
        except Exception as e:
            await reply(f"Oda bilgisi alınamadı: {e}")

    async def _switch_room(self, room_id, reply):
        room_id = room_id.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{24}", room_id):
            await reply(f"Geçersiz oda ID'si: {room_id}")
            return
        name = room_id
        try:
            resp = await self.webapi.get_room(room_id)
            name = resp.room.disp_name
        except Exception:
            pass
        current_room = self.config.get("room_id")
        self._previous_room_id = current_room
        self._pending_room_id = room_id
        self.config["room_id"] = room_id
        cfg_path = self.config.get("_config_path")
        if cfg_path:
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                if current_room:
                    cfg["last_good_room_id"] = current_room
                cfg["room_id"] = room_id
                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"[oda] config kaydedilemedi: {e}")
        print(f"[oda] oda değiştiriliyor: {name} ({room_id})")
        await reply(f"Oda değiştiriliyor: {name} ({room_id})...")

    async def _cmd_wallet(self, user_id, username, args, reply):
        try:
            resp = await self.highrise.get_wallet()
            if isinstance(resp, Error):
                await reply(f"Cüzdan alınamadı: {resp}")
                return
            parts = []
            for item in resp.content:
                parts.append(f"{item.amount} {item.type}")
            await reply("Bot cüzdanı: " + (", ".join(parts) if parts else "boş"))
        except Exception as e:
            await reply(f"Cüzdan alınamadı: {e}")

    async def _cmd_online(self, user_id, username, args, reply):
        names = [f"@{u.username}" for u, _p in self.room_user_cache if u.username]
        if not names:
            await reply("Odada görünür kullanıcı yok.")
            return
        await reply(f"Odadaki kullanıcılar ({len(names)}):\n" + ", ".join(names))

    async def _cmd_dance(self, user_id, username, args, reply):
        emote = random.choice(DANCE_EMOTES)
        await self.highrise.send_emote(emote, user_id)
        await reply("Dans et! 💃")
        if user_id != self.owner_id and self.owner_id:
            await self.highrise.send_whisper(self.owner_id, f"@{username} dans etti.")

    async def _cmd_hi(self, user_id, username, args, reply):
        await self.highrise.send_emote("emote-wave", user_id)
        await reply(f"Selam @{username or 'yeni arkadaş'}! 👋")

    async def _cmd_emote(self, user_id, username, args, reply):
        emote = args.strip().lstrip("-").strip()
        if not emote:
            await reply("Kullanım: -emote <emote adı> (örn: emote-laugh)")
            return
        try:
            await self.highrise.send_emote(emote, user_id)
            await reply(f"Emote gönderildi: {emote}")
        except Exception as e:
            await reply(f"Emote gönderilemedi ({e}). Geçerli bir emote adı dene.")

    async def _cmd_teleport(self, user_id, username, args, reply):
        target = self._find_user(args)
        if target is None:
            await reply(f"@{args.strip().lstrip('@')} odada bulunamadı.")
            return
        my_pos = None
        for u, pos in self.room_user_cache:
            if u.id == user_id:
                my_pos = pos
                break
        if my_pos is None:
            await reply("Konumun bulunamadı.")
            return
        try:
            await self.highrise.teleport(target.id, my_pos)
            await reply(f"@{target.username} yanına ışınlandı!")
        except Exception as e:
            await reply(f"Işınlama başarısız: {e}")

    async def _cmd_kick(self, user_id, username, args, reply):
        target = self._find_user(args)
        if target is None:
            await reply("Hedef odada bulunamadı.")
            return
        try:
            await self.highrise.moderate_room(target.id, "kick")
            await reply(f"@{target.username} odadan atıldı.")
        except Exception as e:
            await reply(f"Kick başarısız: {e}")

    async def _cmd_ban(self, user_id, username, args, reply):
        target = self._find_user(args)
        if target is None:
            await reply("Hedef odada bulunamadı.")
            return
        try:
            await self.highrise.moderate_room(target.id, "ban")
            await reply(f"@{target.username} yasaklandı.")
        except Exception as e:
            await reply(f"Ban başarısız: {e}")

    async def _cmd_unban(self, user_id, username, args, reply):
        target = self._find_user(args)
        if target is None:
            await reply("Hedef odada bulunamadı. (Yasaklı kullanıcı odada değilse unban yapılamaz.)")
            return
        try:
            await self.highrise.moderate_room(target.id, "unban")
            await reply(f"@{target.username} yasağı kaldırıldı.")
        except Exception as e:
            await reply(f"Unban başarısız: {e}")

    async def _cmd_mute(self, user_id, username, args, reply):
        parts = args.split()
        if not parts:
            await reply("Kullanım: -mute @isim [dakika]")
            return
        target = self._find_user(parts[0])
        if target is None:
            await reply("Hedef odada bulunamadı.")
            return
        minutes = 10
        if len(parts) > 1:
            try:
                minutes = max(1, int(parts[1]))
            except ValueError:
                await reply("Süre sayı olmalı (dakika).")
                return
        try:
            await self.highrise.moderate_room(target.id, "mute", minutes * 60)
            await reply(f"@{target.username} {minutes} dakika susturuldu.")
        except Exception as e:
            await reply(f"Mute başarısız: {e}")

    async def _cmd_unmute(self, user_id, username, args, reply):
        target = self._find_user(args)
        if target is None:
            await reply("Hedef odada bulunamadı.")
            return
        try:
            await self.highrise.moderate_room(target.id, "unmute")
            await reply(f"@{target.username} susturması kaldırıldı.")
        except Exception as e:
            await reply(f"Unmute başarısız: {e}")

    async def _cmd_music_play(self, user_id, username, args, reply):
        if not self.player:
            await reply("Müzik sistemi bu sunucuda kapalı (Icecast ayarı yok).")
            return
        if not args.strip():
            await reply("Kullanım: -p <şarkı adı veya YouTube linki>")
            return
        await reply("Şarkı aranıyor, birazdan başlıyor...")
        result = await self.player.add(args.strip())
        await reply(result)

    async def _cmd_music_queue(self, user_id, username, args, reply):
        if not self.player:
            await reply("Müzik sistemi bu sunucuda kapalı.")
            return
        await reply(self.player.queue_text())

    async def _cmd_music_skip(self, user_id, username, args, reply):
        if not self.player:
            await reply("Müzik sistemi bu sunucuda kapalı.")
            return
        await reply(await self.player.skip())

    async def _cmd_music_stop(self, user_id, username, args, reply):
        if not self.player:
            await reply("Müzik sistemi bu sunucuda kapalı.")
            return
        await reply(await self.player.stop())
        try:
            await self.highrise.send_channel("STOP", {"radio"})
        except Exception as e:
            print(f"[muzik] STOP gönderilemedi: {e}")

    async def _cmd_music_now(self, user_id, username, args, reply):
        if not self.player:
            await reply("Müzik sistemi bu sunucuda kapalı.")
            return
        await reply(self.player.current_text())

    async def _on_track(self, title):
        try:
            await self.highrise.chat(f"Şimdi çalıyor: {title}")
        except Exception as e:
            print(f"[muzik] oda duyurusu hata: {e}")
        try:
            pub = os.environ.get("STREAM_PUBLIC_URL") or self.player.config["icecast"].get("publicUrl")
            if pub:
                await self.highrise.send_channel(f"PLAY_URL:{pub}", {"radio"})
        except Exception as e:
            print(f"[muzik] PLAY_URL gönderilemedi: {e}")

    # ---------- otomatik pop (oda boşken) ----------

    async def _auto_worker(self):
        await asyncio.sleep(10)
        while True:
            try:
                if (
                    self.player
                    and not self.player.current
                    and not self.player.queue
                ):
                    await self._auto_play_next()
            except Exception as e:
                print(f"[otomatik] hata: {e}")
            await asyncio.sleep(90)

    async def _on_track_end(self):
        try:
            if self.player and not self.player.current and not self.player.queue:
                await self._auto_play_next()
        except Exception as e:
            print(f"[otomatik] hata: {e}")

    async def _auto_play_next(self):
        try:
            song = random.choice(TR_POP_SONGS)
            print(f"[otomatik] istek yok, çalınıyor: {song}")
            ok, *rest = await self.player._resolve_and_download(song)
            if not ok:
                print(f"[otomatik] şarkı yüklenemedi: {rest[0]}")
                return
            title, path = rest
            self.player.queue.append((title, path))
            self.player._wake.set()
        except Exception as e:
            print(f"[otomatik] hata: {e}")
