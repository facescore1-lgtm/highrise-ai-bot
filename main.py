import asyncio
import http.server
import json
import os
import sys
import threading

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from highrise.__main__ import BotDefinition, main

from bot import Bot


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _env(name, default):
    value = os.environ.get(name)
    return value if value else default


def load_config():
    with open(os.path.join(BASE_DIR, "config.json"), "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["room_id"] = _env("ROOM_ID", cfg.get("room_id", ""))
    cfg["api_token"] = _env("API_TOKEN", cfg.get("api_token", ""))
    cfg["gemini_api_key"] = _env("GEMINI_API_KEY", cfg.get("gemini_api_key", ""))
    try:
        with open(os.path.join(BASE_DIR, "music_config.json"), "r", encoding="utf-8-sig") as f:
            cfg["music"] = json.load(f)
    except Exception:
        cfg["music"] = None
    return cfg


def start_health_server():
    port = int(os.environ.get("PORT", "8001"))

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *args):
            pass

    try:
        httpd = http.server.ThreadingHTTPServer(("0.0.0.0", port), Handler)
    except OSError as e:
        print(f"[main] Sağlık sunucusu port {port} açılamadı ({e}). Devam ediliyor.")
        return
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    print(f"[main] Sağlık sunucusu port {port} üzerinde çalışıyor.")


def main_run():
    cfg = load_config()
    room_id = cfg.get("room_id", "").strip()
    api_token = cfg.get("api_token", "").strip()
    if not room_id or not api_token:
        print("[main] ROOM_ID ve API_TOKEN gerekli. config.json veya ortam değişkenlerini ayarla.")
        return
    start_health_server()
    cfg["_config_path"] = os.path.join(BASE_DIR, "config.json")
    bot = Bot(cfg)
    print(f"[main] Highrise botu başlatılıyor (oda: {room_id})...")
    asyncio.run(main([BotDefinition(bot, room_id, api_token)]))


if __name__ == "__main__":
    main_run()
