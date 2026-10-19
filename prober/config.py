from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import yaml

DEFAULT_CONFIG = Path(__file__).parent / "config.yaml"


@dataclass
class Site:
    name: str
    url: str
    expected_text: str | None = None
    # per-site override, if not set the global interval is used
    interval_seconds: float | None = None

    @property
    def hostname(self) -> str:
        return urlparse(self.url).hostname or ""

    @property
    def is_https(self) -> bool:
        return urlparse(self.url).scheme == "https"


@dataclass
class Config:
    interval_seconds: float = 30
    timeout_seconds: float = 10
    sites: list[Site] = field(default_factory=list)


def load_config(path: str | Path = DEFAULT_CONFIG) -> Config:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    sites = [Site(**s) for s in raw.get("sites", [])]
    if not sites:
        raise ValueError(f"no sites defined in {path}")

    config = Config(
        interval_seconds=raw.get("interval_seconds", 30),
        timeout_seconds=raw.get("timeout_seconds", 10),
        sites=sites,
    )
    for site in config.sites:
        if site.interval_seconds is None:
            site.interval_seconds = config.interval_seconds
    return config
