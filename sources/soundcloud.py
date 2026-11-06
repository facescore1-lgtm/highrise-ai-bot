import yt_dlp

from .base import AudioItem, ResolveError

SC_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "socket_timeout": 15,
    "retries": 2,
    "fragment_retries": 2,
    "noprogress": True,
}


class SoundCloudResolver:
    """YouTube yerine SoundCloud: datacenter IP'lerinde bot-check/PO-token yok."""

    def resolve(self, query):
        text = (query or "").strip()
        if not text:
            raise ResolveError("bos sorgu")
        if text.lower().startswith(("http://", "https://")):
            target = text
        else:
            target = "scsearch1:" + text
        try:
            with yt_dlp.YoutubeDL(dict(SC_OPTS)) as ydl:
                info = ydl.extract_info(target, download=False)
        except Exception as err:
            raise ResolveError("soundcloud: %s" % err) from err
        if isinstance(info, dict) and info.get("entries") is not None:
            entries = [e for e in info.get("entries") if e]
            if not entries:
                raise ResolveError("sonuc bulunamadi")
            info = entries[0]
        if not info or not info.get("url"):
            raise ResolveError("oynanabilir akis bulunamadi")
        return AudioItem(
            url=info.get("webpage_url") or text,
            title=info.get("title") or text,
            stream_url=info["url"],
            headers=dict(info.get("http_headers") or {}),
            source="soundcloud",
            duration=int(info.get("duration") or 0),
        )
