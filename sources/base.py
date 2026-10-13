from dataclasses import dataclass, field


class ResolveError(Exception):
    pass


@dataclass
class AudioItem:
    url: str = ""
    title: str = ""
    stream_url: str = ""
    headers: dict = field(default_factory=dict)
    source: str = "auto"
    duration: int = 0
    stream_url_ts: float = 0.0
    stream_resolved: bool = False
    is_radio: bool = False