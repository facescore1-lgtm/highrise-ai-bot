import re

import yt_dlp

from .base import AudioItem, ResolveError

YDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "socket_timeout": 15,
    "retries": 2,
    "fragment_retries": 2,
    "noprogress": True,
    "extractor_args": {
        "youtube": {
            "player_client": [
                "tv_embedded",
                "web_safari",
                "android",
                "ios",
                "mweb",
                "web_embedded",
            ]
        }
    },
}

_YT_RE = re.compile(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/|live/)|youtu\.be/)([\w-]{11})")


def is_youtube(url):
    return "youtu.be" in url or "youtube.com" in url


def extract_video_id(url):
    m = _YT_RE.search(url)
    return m.group(1) if m else None


class YouTubeResolver:
    def __init__(self, cookies_file="", proxy=""):
        self.cookies_file = cookies_file
        self.proxy = proxy

    def _opts(self):
        opts = dict(YDL_OPTS)
        if self.cookies_file:
            opts["cookiefile"] = self.cookies_file
        if self.proxy:
            opts["proxy"] = self.proxy
        return opts

    def resolve(self, url):
        target = url if url.lower().startswith(("http://", "https://")) else "ytsearch:" + url
        try:
            with yt_dlp.YoutubeDL(self._opts()) as ydl:
                info = ydl.extract_info(target, download=False)
        except Exception as err:
            raise ResolveError("yt-dlp: %s" % err) from err
        if isinstance(info, dict) and info.get("entries"):
            info = info["entries"][0]
        if not info or not info.get("url"):
            raise ResolveError("oynanabilir akis bulunamadi")
        return AudioItem(
            url=info.get("webpage_url") or url,
            title=info.get("title") or url,
            stream_url=info["url"],
            headers=dict(info.get("http_headers") or {}),
            source="youtube",
            duration=int(info.get("duration") or 0),
        )