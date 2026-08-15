import asyncio
import sys

from highrise import BaseBot
from highrise.__main__ import BotDefinition, main

from music_player import MusicPlayer, load_music_config


class MusicAgent(BaseBot):
    def __init__(self, config, player):
        super().__init__()
        self.player = player

    async def on_start(self, session_metadata):
        print(f"[muzik-agent] Bağlandı. Bot ID: {session_metadata.user_id}")
        self.player.start()

    async def on_chat(self, user, message):
        if message.startswith("-"):
            await self._handle(user, message, whisper=False)

    async def on_whisper(self, user, message):
        if message.startswith("-"):
            await self._handle(user, message, whisper=True)

    async def _reply(self, user, text, whisper):
        if whisper:
            try:
                await self.highrise.send_whisper(user.id, text)
            except Exception as e:
                print(f"[muzik-agent] whisper hata: {e}")
        else:
            try:
                await self.highrise.send_whisper(user.id, text)
            except Exception as e:
                print(f"[muzik-agent] whisper hata: {e}")

    async def _announce(self, text):
        try:
            await self.highrise.chat(text)
        except Exception as e:
            print(f"[muzik-agent] oda duyurusu hata: {e}")

    async def _handle(self, user, message, whisper):
        parts = message[len("-"):].strip().split(maxsplit=1)
        cmd = parts[0].lower() if parts else ""
        args = parts[1].strip() if len(parts) > 1 else ""
        try:
            if cmd in ("p", "play", "çal"):
                if not args:
                    await self._reply(user, "Kullanım: -p <şarkı adı veya YouTube linki>", whisper)
                    return
                msg = await self.player.add(args)
                await self._reply(user, msg, whisper)
            elif cmd in ("q", "queue", "kuyruk"):
                await self._reply(user, self.player.queue_text(), whisper)
            elif cmd in ("skip", "geç", "next"):
                await self._reply(user, await self.player.skip(), whisper)
            elif cmd in ("stop", "dur"):
                await self._reply(user, await self.player.stop(), whisper)
            elif cmd in ("now", "calan", "çalan"):
                await self._reply(user, self.player.current_text(), whisper)
            elif cmd in ("np",):
                await self._reply(user, self.player.current_text(), whisper)
                await self._announce(f"Şimdi çalıyor: {self.player.current}" if self.player.current else "Şu an müzik çalmıyor.")
        except Exception as e:
            print(f"[muzik-agent] komut hatası: {e}")
            await self._reply(user, f"Müzik komutu hatası: {e}", whisper)

    async def on_moderate(self, moderator_id, target_user_id, moderation_type, duration):
        pass

    async def on_message(self, user_id, conversation_id, is_new_conversation):
        pass


def run():
    config = load_music_config()
    room_id = config.get("room_id", "").strip()
    api_token = config.get("api_token", "").strip()
    if not room_id or not api_token:
        print("[muzik-agent] music_config.json içinde room_id ve api_token (2. bot token'ı) dolu olmalı.")
        return
    player = MusicPlayer(config)
    agent = MusicAgent(config, player)
    print(f"[muzik-agent] Odaya bağlanılıyor: {room_id}")
    asyncio.run(main([BotDefinition(agent, room_id, api_token)]))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    run()
