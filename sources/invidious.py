import re

import requests

from .base import AudioItem, ResolveError
from .youtube import extract_video_id

_ITAG_RANK = (140, 139, 251, 250, 249, 141, 171)
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


class InvidiousResolver:
    def __init__(self, instances):
        self.instances = list(instances or [])

    def resolve(self, url):
        video_id = extract_video_id(url) or self._from_url(url)
        if not video_id:
            raise ResolveError("video id bulunamadi")
        errors = []
        for inst in self.instances:
            try:
                resp = requests.get(
                    "%s/api/v1/videos/%s" % (inst.rstrip("/"), video_id),
                    params={"fields": "videoId,title,lengthSeconds,adaptiveFormats"},
                    headers={"User-Agent": _UA},
                    timeout=15,
                )
                if resp.status_code != 200:
                    errors.append("%s: HTTP %d" % (inst, resp.status_code))
                    continue
                data = resp.json()
                stream = self._pick_audio(data.get("adaptiveFormats") or [])
                if not stream:
                    errors.append("%s: ses formati yok" % inst)
                    continue
                return AudioItem(
                    url=url,
                    title=data.get("title") or url,
                    stream_url=stream["url"],
                    headers={"User-Agent": _UA},
                    source="invidious",
                    duration=int(data.get("lengthSeconds") or 0),
                )
            except Exception as err:
                errors.append("%s: %s" % (inst, err))
        raise ResolveError("; ".join(errors) or "invidious kullanilamadi")

    @staticmethod
    def _from_url(url):
        m = re.search(r"[?&]v=([\w-]{11})", url)
        return m.group(1) if m else None

    @staticmethod
    def _pick_audio(formats):
        by_itag = {}
        fallback = None
        for fmt in formats:
            if not fmt.get("url"):
                continue
            if (fmt.get("type") or "").startswith("audio") or fmt.get("audioQuality"):
                by_itag.setdefault(fmt.get("itag"), fmt)
                if fallback is None:
                    fallback = fmt
        for tag in _ITAG_RANK:
            if tag in by_itag:
                return by_itag[tag]
        return fallback