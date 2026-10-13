import http.client
import json
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

PORT = int(os.environ.get("PORT", "10000"))
ICECAST_PORT = int(os.environ.get("ICECAST_PORT", "9000"))
CTRL_PORT = int(os.environ.get("CONTROL_PORT", "8090"))

CTRL_PREFIX = "/control"
ICECAST_BUFFER_ROOTS = (
    "/admin",
    "/list_",
    "/server_version",
    "/robots.txt",
    "/favicon.ico",
    "/style.css",
    "/static",
    "/server_info.xsl",
)


class Gateway(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json404(self):
        self._json({"error": "bulunamadi"}, 404)

    def _health(self):
        self._json(
            {
                "status": "ok",
                "stream": "/stream1",
                "control": "/control/status",
            }
        )

    def do_HEAD(self):
        path = urlparse(self.path).path
        if path.startswith("/stream"):
            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Connection", "close")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/health"):
            return self._health()
        if path.startswith(CTRL_PREFIX):
            return self._relay(CTRL_PORT, path[len(CTRL_PREFIX):] or "/", "GET", None, self.headers.get("Content-Type"))
        if path.startswith("/stream"):
            return self._stream()
        if path.startswith(("/status-json.xsl", "/status.xsl")) or self._is_icecast_buffered(path):
            return self._relay(ICECAST_PORT, path, "GET", None, None)
        return self._json404()

    def do_POST(self):
        path = urlparse(self.path).path
        if not path.startswith(CTRL_PREFIX):
            return self._json404()
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        return self._relay(
            CTRL_PORT,
            (path[len(CTRL_PREFIX):] or "/") + ("?%s" % urlparse(self.path).query if urlparse(self.path).query else ""),
            "POST",
            body,
            self.headers.get("Content-Type"),
        )

    def _is_icecast_buffered(self, path):
        return any(path.startswith(root) for root in ICECAST_BUFFER_ROOTS)

    def _relay(self, port, path, method, body, ctype):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        try:
            if body is not None:
                headers = {"Content-Type": ctype or "application/json", "Content-Length": str(len(body))}
                conn.request(method, path, body=body, headers=headers)
            else:
                conn.request(method, path or "/")
            resp = conn.getresponse()
            data = resp.read()
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() in ("connection", "keep-alive", "transfer-encoding", "content-length", "date"):
                    continue
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if method != "HEAD" or True:
                self.wfile.write(data)
        except Exception as err:
            try:
                self._json({"error": "proxy hatasi: %s" % err}, 502)
            except Exception:
                pass
        finally:
            conn.close()

    def _stream(self):
        path = urlparse(self.path).path or "/stream1"
        try:
            s = socket.create_connection(("127.0.0.1", ICECAST_PORT), timeout=5)
            s.settimeout(30)
        except OSError:
            return self._json({"error": "icecast kapali"}, 502)
        req = "GET %s HTTP/1.0\r\nHost: 127.0.0.1:%d\r\nConnection: close\r\n\r\n" % (path, ICECAST_PORT)
        try:
            s.sendall(req.encode("utf-8"))
        except OSError:
            s.close()
            return self._json({"error": "icecast yanit vermedi"}, 502)
        buf = b""
        try:
            while b"\r\n\r\n" not in buf:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
                if len(buf) > 65536:
                    break
        except OSError:
            pass
        head, _, rest = buf.partition(b"\r\n\r\n")
        lines = head.split(b"\r\n") if head else [b"HTTP/1.0 200 OK"]
        try:
            code = int(lines[0].split(b" ", 2)[1])
        except (IndexError, ValueError):
            code = 200
        self.send_response(code)
        for line in lines[1:]:
            if b":" not in line:
                continue
            k, _, v = line.partition(b":")
            if k.strip().lower() in (b"connection", b"keep-alive", b"transfer-encoding", b"content-length", b"date"):
                continue
            self.send_header(k.strip().decode("latin-1"), v.strip().decode("latin-1"))
        self.send_header("Connection", "close")
        self.end_headers()
        body = rest
        try:
            while True:
                if body:
                    self.wfile.write(body)
                    self.wfile.flush()
                    body = b""
                chunk = s.recv(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except OSError:
            pass
        finally:
            try:
                s.close()
            except OSError:
                pass


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Gateway)
    server.daemon_threads = True
    server.serve_forever()


if __name__ == "__main__":
    main()