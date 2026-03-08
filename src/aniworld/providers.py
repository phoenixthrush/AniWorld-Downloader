from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Pattern, Type
from urllib.parse import urlparse, urlunparse

from .config import (
    ANIWORLD_EPISODE_PATTERN,
    ANIWORLD_SEASON_PATTERN,
    ANIWORLD_SERIES_PATTERN,
    HANIME_TV_SERIES_PATTERN,
    HIANIME_EPISODE_PATTERN,
    HIANIME_SEASON_PATTERN,
    HIANIME_SERIES_PATTERN,
    SERIENSTREAM_EPISODE_PATTERN,
    SERIENSTREAM_SEASON_PATTERN,
    SERIENSTREAM_SERIES_PATTERN,
)
from .models import (
    AniworldEpisode,
    AniworldSeason,
    AniworldSeries,
    HanimeTVEpisode,
    HiAnimeEpisode,
    HiAnimeSeason,
    HiAnimeSeries,
    SerienstreamEpisode,
    SerienstreamSeason,
    SerienstreamSeries,
)


@dataclass(frozen=True)
class Provider:
    name: str
    series_pattern: Optional[Pattern[str]] = None
    season_pattern: Optional[Pattern[str]] = None
    episode_pattern: Optional[Pattern[str]] = None

    series_cls: Optional[Type] = None
    season_cls: Optional[Type] = None
    episode_cls: Optional[Type] = None


PROVIDERS = [
    Provider(
        name="AniWorld",
        series_pattern=ANIWORLD_SERIES_PATTERN,
        season_pattern=ANIWORLD_SEASON_PATTERN,
        episode_pattern=ANIWORLD_EPISODE_PATTERN,
        series_cls=AniworldSeries,
        season_cls=AniworldSeason,
        episode_cls=AniworldEpisode,
    ),
    Provider(
        name="HanimeTV",
        episode_pattern=HANIME_TV_SERIES_PATTERN,
        episode_cls=HanimeTVEpisode,
    ),
    Provider(
        name="SerienStream",
        series_pattern=SERIENSTREAM_SERIES_PATTERN,
        season_pattern=SERIENSTREAM_SEASON_PATTERN,
        episode_pattern=SERIENSTREAM_EPISODE_PATTERN,
        series_cls=SerienstreamSeries,
        season_cls=SerienstreamSeason,
        episode_cls=SerienstreamEpisode,
    ),
    Provider(
        name="HiAnime",
        series_pattern=HIANIME_SERIES_PATTERN,
        season_pattern=HIANIME_SEASON_PATTERN,
        episode_pattern=HIANIME_EPISODE_PATTERN,
        series_cls=HiAnimeSeries,
        season_cls=HiAnimeSeason,
        episode_cls=HiAnimeEpisode,
    ),
]


def normalize_url(url: str) -> str:
    if not url:
        return url

    url = url.strip()

    parsed = urlparse(url)
    path = parsed.path

    # --- SerienStream alias handling ---
    # Some endpoints use /serie/stream/<slug>; normalize to /serie/<slug>.
    if path.startswith("/serie/stream/"):
        slug = path[len("/serie/stream/") :].strip("/")
        if slug:
            path = f"/serie/{slug}"

    # remove trailing slash
    path = path.rstrip("/")

    return urlunparse(parsed._replace(path=path))


def resolve_provider(url: str) -> Provider:
    url = normalize_url(url)

    for provider in PROVIDERS:
        if provider.series_pattern and provider.series_pattern.fullmatch(url):
            return provider
        if provider.season_pattern and provider.season_pattern.fullmatch(url):
            return provider
        if provider.episode_pattern and provider.episode_pattern.fullmatch(url):
            return provider

    raise ValueError(f"Unsupported URL: {url}")
