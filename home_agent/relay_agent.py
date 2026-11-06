#!/usr/bin/env python3
"""Highrise Radio - ev relay cihazi.

Render'daki bot sarki isteklerini bu cihaza gonderir; bu program sesi
ffmpeg ile indirip MP3 olarak Render'a geri yollar.

AVANTAJ: Baglanti DISARI dogru kurulur. Yani port yonlendirme, domain,
DuckDNS, Cloudflare Tunnel veya statik/public IP GEREKMEZ. CGNAT arkasinda
(ornegin mobil veri) bile calisir.

Gereksinimler:
  - Python 3.8+
  - ffmpeg (PATH'te olmali; Windows: winget install Gyan.FFmpeg)
  - pip install websockets

Kullanim:
  python relay_agent.py --url wss://highrise-ai-bot.onrender.com/relay --token TOKEN

  veya ortam degiskeni ile:
  set RELAY_URL=wss://highrise-ai-bot.onrender.com/relay
  set RELAY_TOKEN=...
  python relay_agent.py
"""

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import threading
import time

from websockets.sync.client import connect


def log(*parts):
    stamp = time.strftime("%H:%M:%S")
    print("[%s] %s" % (stamp, " ".join(str(p) for p in parts)), flush=True)


def ffmpeg_path():
    p = shutil.which("ffmpeg")
    if p:
        return p
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("ffmpeg.exe", "ffmpeg"):
        cand = os.path.join(here, name)
        if os.path.isfile(cand):
            return cand
    return None


class JobRunner:
    def __init__(self, ws, fmt):
        self.ws = ws
        self.fmt = fmt
        self._lock = threading.Lock()
        self._proc = None
        self._thread = None
        self._job_id = None
        self._stop = threading.Event()

    def start(self, job):
        self.stop()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, args=(job, self._stop), daemon=True
        )
        self._thread.start()

    def stop(self):
        with self._lock:
            stop, self._stop = self._stop, threading.Event()
            proc, self._proc = self._proc, None
        stop.set()
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def _send_json(self, obj):
        try:
            self.ws.send(json.dumps(obj, ensure_ascii=False))
        except Exception as err:
            log("gonderilemedi:", err)

    def _run(self, job, stop):
        job_id = job.get("id")
        url = job.get("url")
        title = job.get("title") or url
        ff = ffmpeg_path()
        if not ff:
            self._send_json({"type": "error", "id": job_id, "message": "ffmpeg bulunamadi"})
            log("HATA: ffmpeg bulunamadi (PATH'e ekleyin)")
            return
        cmd = [ff, "-hide_banner", "-nostdin", "-loglevel", "warning", "-re"]
        for k, v in (job.get("headers") or {}).items():
            cmd += ["-headers", "%s: %s" % (k, v)]
        cmd += ["-rw_timeout", "20000000", "-i", url, "-map", "0:a:0", "-vn", "-sn", "-dn"]
        cmd += ["-ac", str(self.fmt["channels"]), "-ar", str(self.fmt["sample_rate"])]
        cmd += ["-b:a", self.fmt["bitrate"], "-c:a", "libmp3lame"]
        cmd += ["-f", "mp3", "-flush_packets", "1", "pipe:1"]
        log("caliyor:", title)
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0
            )
        except Exception as err:
            self._send_json({"type": "error", "id": job_id, "message": "ffmpeg baslatilamadi: %s" % err})
            return
        with self._lock:
            if stop.is_set():
                try:
                    proc.kill()
                except Exception:
                    pass
                return
            self._proc = proc
        stderr_tail = []

        def drain():
            try:
                for raw in iter(proc.stderr.readline, b""):
                    line = raw.decode("utf-8", "replace").strip()
                    if line:
                        stderr_tail.append(line)
                        if len(stderr_tail) > 20:
                            stderr_tail.pop(0)
                        log("ffmpeg:", line)
            except Exception:
                pass

        threading.Thread(target=drain, daemon=True).start()
        sent = 0
        try:
            while not stop.is_set():
                chunk = proc.stdout.read(16384)
                if not chunk:
                    break
                try:
                    self.ws.send(chunk)
                except Exception as err:
                    log("baglanti koptu, ses gonderilemedi:", err)
                    break
                sent += len(chunk)
        finally:
            if proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            with self._lock:
                if self._proc is proc:
                    self._proc = None
        if stop.is_set():
            self._send_json({"type": "ended", "id": job_id})
            return
        if sent == 0:
            tail = " | ".join(stderr_tail[-3:])
            self._send_json(
                {"type": "error", "id": job_id, "message": "ses uretilemedi: %s" % tail}
            )
            log("HATA: ses uretilemedi:", tail)
        else:
            self._send_json({"type": "ended", "id": job_id})
            log("bitti:", title, "(%d KB)" % (sent // 1024))


def main():
    ap = argparse.ArgumentParser(description="Highrise Radio ev relay cihazi")
    ap.add_argument("--url", default=os.environ.get("RELAY_URL", ""))
    ap.add_argument("--token", default=os.environ.get("RELAY_TOKEN", ""))
    ap.add_argument("--bitrate", default=os.environ.get("RELAY_BITRATE", "192k"))
    ap.add_argument("--sample-rate", type=int, default=int(os.environ.get("RELAY_SAMPLE_RATE", "44100")))
    ap.add_argument("--channels", type=int, default=int(os.environ.get("RELAY_CHANNELS", "2")))
    args = ap.parse_args()

    if not args.url:
        ap.error("--url gerekli (ornek: wss://highrise-ai-bot.onrender.com/relay)")
    url = args.url
    if args.token:
        sep = "&" if "?" in url else "?"
        url = "%s%stoken=%s" % (url, sep, args.token)
    fmt = {
        "bitrate": args.bitrate,
        "sample_rate": args.sample_rate,
        "channels": args.channels,
    }
    host = socket.gethostname()
    log("relay cihazi basliyor:", host)
    log("sunucu:", url.split("?")[0])
    if not ffmpeg_path():
        log("UYARI: ffmpeg bulunamadi, sarki calinamaz")

    backoff = 3
    while True:
        try:
            with connect(url, max_size=16 * 1024 * 1024, open_timeout=25) as ws:
                backoff = 3
                log("Render'a baglandi")
                try:
                    ws.send(
                        json.dumps(
                            {
                                "type": "hello",
                                "host": host,
                                "platform": platform.platform(),
                                "ffmpeg": "var" if ffmpeg_path() else "yok",
                            }
                        )
                    )
                except Exception:
                    pass
                runner = JobRunner(ws, fmt)
                try:
                    for msg in ws:
                        if isinstance(msg, bytes):
                            continue
                        try:
                            data = json.loads(msg)
                        except Exception:
                            continue
                        kind = data.get("type")
                        if kind == "play":
                            runner.start(data)
                        elif kind == "stop":
                            log("durduruldu")
                            runner.stop()
                finally:
                    runner.stop()
        except KeyboardInterrupt:
            log("kapatiliyor")
            return
        except Exception as err:
            log("baglanti hatasi:", err)
        log("%d sn sonra yeniden denenecek" % backoff)
        time.sleep(backoff)
        backoff = min(backoff * 2, 30)


if __name__ == "__main__":
    main()
