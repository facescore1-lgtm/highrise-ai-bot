import asyncio
import json
import os
import shutil
import sys

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "music_config.json")
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "music_cache")


def load_music_config(path=DEFAULT_CONFIG_PATH):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def _find_tool(name):
    candidates = [name]
    base = os.path.basename(name)
    if base.lower().endswith(".exe"):
        candidates.append(base[:-4])
    if base not in candidates:
        candidates.append(base)
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found
    scripts = os.path.join(os.path.dirname(os.path.abspath(sys.executable)))
    exe_candidate = os.path.join(scripts, os.path.basename(name) + ".exe")
    if os.path.exists(exe_candidate):
        return exe_candidate
    return name


class MusicPlayer:
    def __init__(self, config):
        self.config = config
        self.ffmpeg = _find_tool(config.get("ffmpeg_path") or "ffmpeg")
        self.ytdlp = _find_tool(config.get("ytdlp_path") or "yt-dlp")
        self.on_track = None
        self.on_track_end = None
        ic = config["icecast"]
        self._dest = (
            f"icecast://{ic['user']}:{ic['password']}@"
            f"{ic['host']}:{ic['port']}/{ic['mount']}"
        )
        self.queue = []
        self.current = None
        self._proc = None
        self._current_file = None
        self._stopped = False
        self._wake = asyncio.Event()
        self._task = None
        os.makedirs(CACHE_DIR, exist_ok=True)

    def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self._worker())

    async def _worker(self):
        while True:
            if self._proc is not None:
                await self._proc.wait()
                self._proc = None
                if self.current:
                    print(f"[muzik] bitti: {self.current}")
                self._cleanup_file()
                self.current = None
                if self.on_track_end:
                    try:
                        await self.on_track_end()
                    except Exception as e:
                        print(f"[muzik] on_track_end hatası: {e}")
            if self._stopped:
                self.queue.clear()
                self._wake.clear()
                await self._wake.wait()
                self._stopped = False
            elif self.queue:
                title, path = self.queue.pop(0)
                self.current = title
                if self.on_track:
                    try:
                        await self.on_track(title)
                    except Exception as e:
                        print(f"[muzik] on_track hatası: {e}")
                await self._stream(path)
            else:
                self._wake.clear()
                await self._wake.wait()

    def _cleanup_file(self):
        if self._current_file and os.path.exists(self._current_file):
            try:
                os.remove(self._current_file)
                print(f"[muzik] cache silindi: {os.path.basename(self._current_file)}")
            except Exception as e:
                print(f"[muzik] cache silinemedi: {e}")
        self._current_file = None

    async def _stream(self, path):
        cmd = [
            self.ffmpeg,
            "-hide_banner",
            "-loglevel", "error",
            "-re",
            "-i", path,
            "-vn",
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            "-f", "mp3",
            self._dest,
        ]
        print(f"[muzik] akış başladı: {self.current}")
        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        stderr = await self._proc.stderr.read() if self._proc.stderr else b""
        await self._proc.wait()
        if self._proc.returncode != 0 and stderr:
            print(
                f"[muzik] ffmpeg hata ({self._proc.returncode}): "
                f"{stderr.decode(errors='replace')[:300]}"
            )

    def _yt_base(self, client_args=None):
        base = ["--no-playlist", "--no-warnings", "--retries", "3"]
        if client_args:
            base += ["--extractor-args", client_args]
        return base

    async def _run_yt(self, cmd):
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return None, b"", b"yt-dlp not found"
        out, err = await proc.communicate()
        return proc.returncode, out, err

    async def _resolve_and_download(self, query):
        variants = [
            "youtube:player_client=android,tv",
            None,
            "youtube:player_client=web_safari,android,tv",
        ]
        search_args = ["--default-search", "ytsearch"] if not query.startswith("http") else []
        ok = None
        last_err = b""
        for client in variants:
            cmd = [
                self.ytdlp, *self._yt_base(client), *search_args,
                "--print", "%(title)s",
                "--get-id",
                query,
            ]
            code, out, err = await self._run_yt(cmd)
            if code == 0 and out:
                ok = (out, err)
                break
            last_err = err or b""
        if ok is None:
            if b"yt-dlp not found" in last_err:
                return False, "yt-dlp bulunamadı. 'pip install yt-dlp' ile kurmalısın."
            return False, f"Şarkı bulunamadı ({last_err.decode(errors='replace')[-200:].strip()})"
        out, err = ok
        lines = out.decode(errors="replace").splitlines()
        title = lines[0].strip() if lines else query
        video_id = lines[1].strip() if len(lines) > 1 else None
        if not video_id:
            return False, f"Video ID alınamadı: {query}"
        target = os.path.join(CACHE_DIR, f"{video_id}.%(ext)s")
        dl_err = b""
        for client in variants:
            cmd = [
                self.ytdlp, *self._yt_base(client),
                "-f", "bestaudio/best",
                "-o", target,
                f"https://www.youtube.com/watch?v={video_id}",
            ]
            code, _out, err = await self._run_yt(cmd)
            if code == 0:
                break
            dl_err = err or b""
        else:
            return False, f"İndirme başarısız ({dl_err.decode(errors='replace')[-200:].strip()})"
        matches = [f for f in os.listdir(CACHE_DIR) if f.startswith(video_id)]
        if not matches:
            return False, "İndirme dosyası bulunamadı."
        return True, title, os.path.join(CACHE_DIR, matches[0])

    async def add(self, query):
        ok, *rest = await self._resolve_and_download(query)
        if not ok:
            return rest[0]
        title, path = rest
        self.queue.append((title, path))
        self._wake.set()
        return f"Kuyruğa eklendi: {title}"

    async def skip(self):
        if self._proc:
            self._proc.kill()
            return "Sonraki şarkıya geçiliyor."
        return "Şu an çalan şarkı yok."

    async def stop(self):
        self._stopped = True
        if self._proc:
            self._proc.kill()
            await self._proc.wait()
        self.queue.clear()
        self._wake.set()
        return "Müzik durduruldu, kuyruk temizlendi."

    def current_text(self):
        return f"Şimdi çalıyor: {self.current}" if self.current else "Şu an müzik çalmıyor."

    def queue_text(self):
        if not self.queue and not self.current:
            return "Kuyruk boş. Müzik çalmak için -p <şarkı> yaz."
        lines = [f"Şimdi: {self.current}"] if self.current else []
        for i, (title, _u) in enumerate(self.queue, 1):
            lines.append(f"{i}. {title}")
        return "\n".join(lines)
