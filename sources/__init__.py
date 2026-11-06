from .base import AudioItem, ResolveError
from .invidious import InvidiousResolver
from .soundcloud import SoundCloudResolver
from .youtube import YouTubeResolver, extract_video_id, is_youtube


class BotResolver:
    def __init__(self, youtube, invidious, soundcloud=None, provider="youtube"):
        self.youtube = youtube
        self.invidious = invidious
        self.soundcloud = soundcloud or SoundCloudResolver()
        self.provider = (provider or "youtube").lower()

    def resolve(self, url):
        if self.provider == "soundcloud":
            return self.soundcloud.resolve(url)
        try:
            return self.youtube.resolve(url)
        except ResolveError as first_err:
            if is_youtube(url) and self.invidious.instances:
                try:
                    return self.invidious.resolve(url)
                except ResolveError as second_err:
                    raise ResolveError("%s | invidious: %s" % (first_err, second_err)) from second_err
            raise


def build_resolver(config):
    yt_cfg = config.get("youtube", {}) or {}
    inv_cfg = config.get("invidious", {}) or {}
    req_cfg = config.get("requests", {}) or {}
    return BotResolver(
        youtube=YouTubeResolver(
            cookies_file=yt_cfg.get("cookies_file", ""),
            proxy=yt_cfg.get("proxy", ""),
        ),
        invidious=InvidiousResolver(inv_cfg.get("instances", [])),
        soundcloud=SoundCloudResolver(),
        provider=req_cfg.get("provider", "youtube"),
    )
