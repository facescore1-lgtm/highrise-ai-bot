import base64
import logging
import socket
import subprocess
import threading
import time

import requests

from sources.base import ResolveError


class TransientError(Exception):
    pass


class IcecastStreamer:
    def __init__(self, config, resolver):
        self.ice = config["icecast"]
        self.audio = config["audio"]
        self.resolver = resolver
        self.log = logging.getLogger("radio.streamer")
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._skip = threading.Event()
        self._proc = None
        self._sock = None
        self._current = None
        self._started = 0.0
        self._backoff = 1
        self._stderr_tail = []
        codecs = {
            "mp3": ("-c:a", "libmp3lame", "mp3", "audio/mpeg"),
            "aac": ("-c:a", "aac", "adts", "audio/aacp"),
            "ogg": ("-c:a", "libvorbis", "ogg", "application/ogg"),
        }
        codec = self.audio.get("codec", "mp3")
        self.codec, self._enc_arg, self._fmt, self._content_type = codecs.get(codec, codecs["mp3"])

    def current(self):
        return self._current

    def is_paused(self):
        return self._paused.is_set()

    def run_radio(self, item_provider):
        self._stop.clear()
        self._paused.clear()
        self._skip.clear()
        item = None
        while not self._stop.is_set():
            if self._paused.is_set():
                self._kill_ffmpeg()
                self._paused.wait()
                continue
            if item is None:
                item = item_provider()
                if item is None:
                    break
                self._current = item
                self._metadata(item.title)
                self.log.info("-> %s", item.title)
            try:
                result = self._play_track(item)
            except ResolveError as err:
                self.log.warning("akis cozulemedi: %s", err)
                self._disconnect()
                item = None
                self._sleep(5)
                continue
            except TransientError as err:
                self.log.warning("gecici hata: %s", err)
                self._disconnect()
                item.stream_resolved = False
                self._sleep(self._backoff)
                self._backoff = min(self._backoff * 2, 60)
                continue
            self._backoff = 1
            if result != "paused":
                item = None
        self._disconnect()

    def stop(self):
        self._stop.set()
        self._paused.clear()
        self._skip.clear()
        self._kill_ffmpeg()

    def skip(self):
        self._skip.set()
        self._kill_ffmpeg()

    def pause(self):
        self._paused.set()
        self._kill_ffmpeg()

    def resume(self):
        self._paused.clear()

    def _play_track(self, item):
        if self._skip.is_set():
            self._skip.clear()
            return "ended"
        try:
            stream_url, headers = self._fresh_url(item)
        except ResolveError:
            raise
        proc = self._spawn_ffmpeg(
            stream_url,
            headers,
            getattr(item, "duration", 0) if getattr(item, "is_radio", False) else 0,
        )
        self._proc = proc
        threading.Thread(target=self._drain_stderr, args=(proc,), daemon=True).start()
        sock = self._ensure_socket(item, stream_url, headers)
        self._started = time.time()
        sent = False
        try:
            while True:
                if self._stop.is_set():
                    self._kill_ffmpeg(proc)
                    return None
                if self._paused.is_set():
                    self._kill_ffmpeg(proc)
                    return "paused"
                if self._skip.is_set():
                    self._kill_ffmpeg(proc)
                    self._skip.clear()
                    return "ended"
                chunk = proc.stdout.read(65536)
                if not chunk:
                    break
                sock.sendall(b"%x\r\n" % len(chunk))
                sock.sendall(chunk)
                sock.sendall(b"\r\n")
                sent = True
        except OSError as err:
            raise TransientError("icecast akisi kesildi: %s" % err) from err
        if self._skip.is_set():
            self._skip.clear()
            return "ended"
        code = proc.wait()
        if code != 0 and not sent and time.time() - self._started < 15:
            raise TransientError("ffmpeg erken cikti (%d): %s" % (code, self._tail()))
        return "ended"

    def _fresh_url(self, item):
        if getattr(item, "is_radio", False):
            return item.stream_url, item.headers
        if not item.stream_resolved or (time.time() - item.stream_url_ts) > 1200:
            fresh = self.resolver.resolve(item.url)
            item.url = fresh.url
            item.title = fresh.title
            item.stream_url = fresh.stream_url
            item.headers = fresh.headers
            item.source = fresh.source
            item.duration = fresh.duration
            item.stream_url_ts = time.time()
            item.stream_resolved = True
        return item.stream_url, item.headers

    def _spawn_ffmpeg(self, stream_url, headers, duration=0):
        a = self.audio
        cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-re"]
        for k, v in (headers or {}).items():
            cmd += ["-headers", "%s: %s" % (k, v)]
        cmd += ["-i", stream_url, "-map", "0:a:0", "-vn", "-sn", "-dn"]
        cmd += ["-ac", str(a.get("channels", 2))]
        cmd += ["-ar", str(a.get("sample_rate", 44100))]
        cmd += ["-b:a", a.get("bitrate", "192k")]
        if duration and duration > 0:
            cmd += ["-t", str(int(duration))]
        cmd += list(self._enc_arg)
        cmd += ["-f", self._fmt, "pipe:1"]
        return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)

    def _ensure_socket(self, item, stream_url, headers):
        if self._sock is not None:
            return self._sock
        sock = self._connect_source()
        self._sock = sock
        self.log.info("icecast kaynagi baglandi: %s", stream_url[:60])
        return sock

    def _connect_source(self):
        host = self.ice.get("host", "127.0.0.1")
        port = int(self.ice.get("port", 8000))
        mount = self.ice.get("mount", "/stream1")
        audio_info = "ice-samplerate=%s;ice-bitrate=%s;ice-channels=%s" % (
            self.audio.get("sample_rate", 44100),
            self.audio.get("bitrate", "128k"),
            self.audio.get("channels", 2),
        )
        header_lines = [
            "PUT %s HTTP/1.1" % mount,
            "Host: %s:%d" % (host, port),
            "Authorization: Basic %s" % self._basic_auth(),
            "Content-Type: %s" % self._content_type,
            "Transfer-Encoding: chunked",
            "Connection: keep-alive",
            "Ice-Name: %s" % self.ice.get("name", "Highrise Radio"),
            "Ice-Description: %s" % self.ice.get("description", ""),
            "Ice-Genre: %s" % self.ice.get("genre", "Various"),
            "Ice-URL: %s" % self.ice.get("url", "http://%s:%d%s" % (host, port, mount)),
            "Ice-Public: %s" % self.ice.get("public", 1),
            "Ice-Audio-Info: %s" % audio_info,
            "User-Agent: highrise-radio-bot/1.0",
            "",
            "",
        ]
        try:
            sock = socket.create_connection((host, port), timeout=15)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.sendall(("\r\n".join(header_lines)).encode("utf-8"))
            return sock
        except OSError as err:
            raise TransientError("icecast baglantisi kurulamadi: %s" % err) from err

    def _disconnect(self):
        self._kill_ffmpeg()
        sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.sendall(b"0\r\n\r\n")
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

    def _basic_auth(self):
        raw = "%s:%s" % (self.ice.get("source_user", "source"), self.ice.get("source_password", ""))
        return base64.b64encode(raw.encode("utf-8")).decode("ascii")

    def _kill_ffmpeg(self, proc=None):
        if proc is None:
            proc = self._proc
        if proc is None:
            return
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
        self._proc = None

    def _metadata(self, title):
        host = self.ice.get("host", "127.0.0.1")
        port = int(self.ice.get("port", 8000))
        admin_pass = self.ice.get("admin_password", "")
        if not admin_pass:
            return
        try:
            requests.get(
                "http://%s:%s/admin/metadata" % (host, port),
                params={
                    "mount": self.ice.get("mount", "/stream1"),
                    "mode": "updinfo",
                    "song": title,
                },
                auth=(self.ice.get("admin_user", "admin"), admin_pass),
                timeout=5,
            )
        except Exception as err:
            self.log.debug("metadata guncellenemedi: %s", err)

    def _sleep(self, seconds):
        end = time.time() + seconds
        while time.time() < end and not self._stop.is_set():
            time.sleep(0.2)

    def _drain_stderr(self, proc):
        lines = []
        for raw in iter(proc.stderr.readline, b""):
            line = raw.decode("utf-8", "replace").rstrip()
            if line:
                lines.append(line)
                if len(lines) > 40:
                    lines.pop(0)
                self.log.debug("ffmpeg: %s", line)
        self._stderr_tail = lines

    def _tail(self):
        if not self._stderr_tail:
            return ""
        return " | ".join(self._stderr_tail[-3:])