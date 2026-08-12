from __future__ import annotations

from dataclasses import dataclass
from re import Pattern
from urllib.parse import urlparse, urlunparse

from .config import (
    ANIWORLD_EPISODE_PATTERN,
    ANIWORLD_SEASON_PATTERN,
    ANIWORLD_SERIES_PATTERN,
    BURNINGSERIES_EPISODE_PATTERN,
    BURNINGSERIES_SEASON_PATTERN,
    BURNINGSERIES_SERIES_PATTERN,
    CINEBY_EPISODE_PATTERN,
    CINEBY_SERIES_PATTERN,
    FILMPALAST_SERIES_PATTERN,
    HANIME_TV_SERIES_PATTERN,
    KINOX_SERIES_PATTERN,
    MANGA_FIRE_CHAPTER_PATTERN,
    MANGA_FIRE_SERIES_PATTERN,
    MEGAKINO_SERIES_PATTERN,
    SERIENSTREAM_EPISODE_PATTERN,
    SERIENSTREAM_SEASON_PATTERN,
    SERIENSTREAM_SERIES_PATTERN,
)
from .models import (
    AniworldEpisode,
    AniworldSeason,
    AniworldSeries,
    BurningSeriesEpisode,
    BurningSeriesSeason,
    BurningSeriesSeries,
    CinebyEpisode,
    CinebySeason,
    CinebySeries,
    FilmPalastEpisode,
    HanimeTVEpisode,
    HanimeTVSeason,
    HanimeTVSeries,
    KinoxEpisode,
    KinoxSeason,
    KinoxSeries,
    MangaFireToChapter,
    MangaFireToSeries,
    MegaKinoEpisode,
    SerienstreamEpisode,
    SerienstreamSeason,
    SerienstreamSeries,
)


@dataclass(frozen=True)
class Provider:
    name: str
    series_pattern: Pattern[str] | None = None
    season_pattern: Pattern[str] | None = None
    episode_pattern: Pattern[str] | None = None

    series_cls: type | None = None
    season_cls: type | None = None
    episode_cls: type | None = None


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
        series_pattern=HANIME_TV_SERIES_PATTERN,
        episode_pattern=HANIME_TV_SERIES_PATTERN,
        series_cls=HanimeTVSeries,
        season_cls=HanimeTVSeason,
        episode_cls=HanimeTVEpisode,
    ),
    Provider(
        name="MegaKino",
        series_pattern=MEGAKINO_SERIES_PATTERN,
        series_cls=MegaKinoEpisode,
        season_cls=None,
        episode_cls=MegaKinoEpisode,
    ),
    Provider(
        name="FilmPalast",
        series_pattern=FILMPALAST_SERIES_PATTERN,
        series_cls=FilmPalastEpisode,
        season_cls=None,
        episode_cls=FilmPalastEpisode,
    ),
    Provider(
        name="Kinox",
        series_pattern=KINOX_SERIES_PATTERN,
        season_pattern=KINOX_SERIES_PATTERN,
        episode_pattern=KINOX_SERIES_PATTERN,
        series_cls=KinoxSeries,
        season_cls=KinoxSeason,
        episode_cls=KinoxEpisode,
    ),
    Provider(
        name="BurningSeries",
        series_pattern=BURNINGSERIES_SERIES_PATTERN,
        season_pattern=BURNINGSERIES_SEASON_PATTERN,
        episode_pattern=BURNINGSERIES_EPISODE_PATTERN,
        series_cls=BurningSeriesSeries,
        season_cls=BurningSeriesSeason,
        episode_cls=BurningSeriesEpisode,
    ),
    Provider(
        name="Cineby",
        series_pattern=CINEBY_SERIES_PATTERN,
        season_pattern=CINEBY_SERIES_PATTERN,
        episode_pattern=CINEBY_EPISODE_PATTERN,
        series_cls=CinebySeries,
        season_cls=CinebySeason,
        episode_cls=CinebyEpisode,
    ),
    Provider(
        name="MangaFire",
        series_pattern=MANGA_FIRE_SERIES_PATTERN,
        season_pattern=MANGA_FIRE_CHAPTER_PATTERN,
        episode_pattern=MANGA_FIRE_CHAPTER_PATTERN,
        series_cls=MangaFireToSeries,
        season_cls=MangaFireToChapter,
        episode_cls=MangaFireToChapter,
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
