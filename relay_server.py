"""Ev (residential IP) relay sunucusu.

Render'daki botun sarki isteklerini evdeki cihaz uzerinden calmasini saglar.
Ev cihazi bu sunucuya OUTBOUND WebSocket ile baglanir; boylece port
yonlendirme, domain veya CGNAT sorunu olmaz.

Akis:
  Render botu  --(m3u8/ses URL'si, WebSocket)-->  ev cihazi
  ev cihazi    --(ffmpeg ile MP3 byte'lari)----->  Render botu -> icecast

WebSocket sunucusu sadece 127.0.0.1'de degil 0.0.0.0'da dinler ama Render'da
disariya sadece gateway uzerinden /relay yolu acilir; token ile korunur.
"""

import json
import logging
import queue
import threading
import time
import uuid
from urllib.parse import parse_qs, urlparse

try:
    from websockets.sync.server import serve as ws_serve
except Exception:  # pragma: no cover - paket yoksa relay kapali kalir
    ws_serve = None


class RelayJob:
    def __init__(self, url, headers, duration, title=""):
        self.id = uuid.uuid4().hex[:12]
        self.url = url
        self.headers = headers or {}
        self.duration = int(duration or 0)
        self.title = title or ""
        self.created = time.time()
        self.sent = 0
        self.error = None
        self.done = threading.Event()
        self._q = queue.Queue()

    def feed(self, data):
        self.sent += len(data)
        self._q.put(data)

    def finish(self, error=None):
        if error and not self.error:
            self.error = error
        self.done.set()
        self._q.put(None)

    def read(self, timeout=5.0):
        """Ses byte'i dondurur; is bittiyse b''; sure dolarsa queue.Empty."""
        end = time.time() + timeout
        while True:
            left = end - time.time()
            if left <= 0:
                raise queue.Empty()
            try:
                item = self._q.get(timeout=min(left, 0.5))
            except queue.Empty:
                if self.done.is_set() and self._q.empty():
                    return b""
                continue
            if item is None:
                return b""
            return item


class RelayServer:
    def __init__(self, token="", host="0.0.0.0", port=8111, log=None):
        self.token = token or ""
        self.host = host
        self.port = int(port)
        self.log = log or logging.getLogger("radio.relay")
        self._server = None
        self._conn = None
        self._conn_lock = threading.Lock()
        self._job = None
        self._job_lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._started = 0.0
        self._last_seen = 0.0

    # ---------- durum ----------

    def available(self):
        with self._conn_lock:
            return self._conn is not None

    def agent_info(self):
        with self._conn_lock:
            return {
                "connected": self._conn is not None,
                "connected_since": self._started,
                "last_seen": self._last_seen,
            }

    # ---------- yasam dongusu ----------

    def start(self):
        if ws_serve is None:
            self.log.warning("relay: 'websockets' paketi yok, relay devre disi")
            return False
        if not self.token:
            self.log.warning("relay: RELAY_TOKEN tanimli degil, relay devre disi")
            return False

        def handler(conn):
            try:
                self._handle(conn)
            except Exception as err:  # baglanti koptu vs.
                self.log.warning("relay isleyici hatasi: %s", err)

        self._server = ws_serve(
            handler,
            self.host,
            self.port,
            max_size=8 * 1024 * 1024,
        )
        threading.Thread(
            target=self._server.serve_forever,
            name="relay-ws",
            daemon=True,
        ).start()
        self.log.info("relay sunucusu dinliyor: %s:%d", self.host, self.port)
        return True

    def stop(self):
        with self._job_lock:
            job, self._job = self._job, None
        if job is not None:
            job.finish(None)
        if self._server is not None:
            try:
                self._server.shutdown()
            except Exception:
                pass
            self._server = None

    # ---------- baglanti ----------

    def _handle(self, conn):
        path = ""
        try:
            path = conn.request.path or ""
        except Exception:
            pass
        given = (parse_qs(urlparse(path).query).get("token") or [""])[0]
        if given != self.token:
            self.log.warning("relay: hatali token ile baglanti reddedildi")
            try:
                conn.close(1008, "token gecersiz")
            except Exception:
                pass
            return

        with self._conn_lock:
            old = self._conn
            self._conn = conn
            self._started = time.time()
            self._last_seen = time.time()
        if old is not None and old is not conn:
            try:
                old.close(1000, "yeni cihaz baglandi")
            except Exception:
                pass

        peer = ""
        try:
            peer = "%s:%s" % conn.remote_address[:2]
        except Exception:
            pass
        self.log.info("relay cihazi baglandi (%s)", peer or "?")
        try:
            for msg in conn:
                self._last_seen = time.time()
                if isinstance(msg, bytes):
                    with self._job_lock:
                        job = self._job
                    if job is not None and not job.done.is_set():
                        job.feed(msg)
                    continue
                self._on_text(msg)
        finally:
            with self._conn_lock:
                if self._conn is conn:
                    self._conn = None
            with self._job_lock:
                job, self._job = self._job, None
            if job is not None:
                job.finish("relay cihazi ayrildi")
            self.log.warning("relay cihazi ayrildi (%s)", peer or "?")

    def _on_text(self, msg):
        try:
            data = json.loads(msg)
        except Exception:
            return
        if not isinstance(data, dict):
            return
        kind = data.get("type")
        job_id = data.get("id")
        if kind == "hello":
            self.log.info(
                "relay cihaz bilgisi: host=%s ffmpeg=%s",
                data.get("host", "?"),
                data.get("ffmpeg", "?"),
            )
        elif kind in ("ended", "error"):
            with self._job_lock:
                job = self._job
                if job is not None and (not job_id or job_id == job.id):
                    self._job = None
                else:
                    job = None
            if job is not None:
                if kind == "error":
                    job.finish(str(data.get("message") or "relay hatasi"))
                else:
                    job.finish(None)

    def _send(self, obj):
        with self._conn_lock:
            conn = self._conn
        if conn is None:
            return False
        try:
            with self._send_lock:
                conn.send(json.dumps(obj, ensure_ascii=False))
            return True
        except Exception as err:
            self.log.warning("relay gonderilemedi: %s", err)
            return False

    # ---------- isler ----------

    def play(self, url, headers=None, duration=0, title=""):
        """Ev cihazindan calma isi baslatir; RelayJob dondurur (yoksa None)."""
        if not self.available():
            return None
        self.stop_current()
        job = RelayJob(url, headers, duration, title)
        with self._job_lock:
            self._job = job
        ok = self._send(
            {
                "type": "play",
                "id": job.id,
                "url": url,
                "headers": job.headers,
                "duration": job.duration,
                "title": job.title,
            }
        )
        if not ok:
            with self._job_lock:
                if self._job is job:
                    self._job = None
            job.finish("relay cihazina ulasilamadi")
            return None
        self.log.info("relay isi basladi: %s", title or url[:60])
        return job

    def stop_current(self):
        with self._job_lock:
            job, self._job = self._job, None
        if job is None:
            return
        self._send({"type": "stop", "id": job.id})
        job.finish(None)

    def stop_job(self, job):
        if job is None:
            return
        with self._job_lock:
            if self._job is job:
                self._job = None
                self._send({"type": "stop", "id": job.id})
        job.finish(None)
