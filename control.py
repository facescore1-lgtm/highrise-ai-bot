import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


class ControlApi:
    def __init__(self, bot, host, port):
        self.bot = bot
        self.host = host
        self.port = port
        self._httpd = None
        self._thread = None

    def start(self):
        handler = lambda *a, **k: _Handler(*a, bot=self.bot, **k)
        self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        if self._httpd:
            self._httpd.shutdown()


class _Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, bot=None, **kwargs):
        self.bot = bot
        super().__init__(*args, **kwargs)

    def _json(self, obj, status=200):
        payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path in ("/", "/status"):
            self._json(self.bot.status())
        elif path == "/playlist":
            self._json({"playlist": self.bot.playlist_items()})
        else:
            self._json({"error": "bulunamadi"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        query = parse_qs(urlparse(self.path).query)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        params = {}
        if body:
            try:
                data = json.loads(body)
                if isinstance(data, dict):
                    params.update(data)
            except ValueError:
                for pair in body.split("&"):
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        params[k] = v
        for k, v in query.items():
            params[k] = v[0]

        if path == "/add":
            url = params.get("url", "").strip()
            if not url:
                self._json({"ok": False, "error": "url gerekli"}, 400)
                return
            self._json(self.bot.cmd_add(url))
        elif path == "/next":
            self._json(self.bot.cmd_next())
        elif path == "/goto":
            self._json(self._pos_command(params, self.bot.cmd_goto))
        elif path == "/remove":
            self._json(self._pos_command(params, self.bot.cmd_remove))
        elif path == "/stop":
            self._json(self.bot.cmd_stop())
        elif path == "/play":
            self._json(self.bot.cmd_play())
        elif path == "/pause":
            self._json(self.bot.cmd_pause())
        elif path == "/resume":
            self._json(self.bot.cmd_resume())
        elif path == "/clear":
            self._json(self.bot.cmd_clear())
        elif path == "/shuffle":
            on = params.get("on", "on")
            self._json(self.bot.cmd_shuffle(on in ("1", "true", "on")))
        elif path == "/reload":
            self._json(self.bot.cmd_reload())
        else:
            self._json({"error": "bulunamadi"}, 404)

    def _pos_command(self, params, fn):
        raw = params.get("pos") or params.get("index") or params.get("n")
        try:
            pos = int(raw)
        except (TypeError, ValueError):
            return {"ok": False, "error": "gecersiz sira numarasi"}
        return fn(pos)

    def log_message(self, fmt, *args):
        pass