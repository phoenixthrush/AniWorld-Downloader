"""English episode markers used by AniWorld and SerienStream."""

import os
import re
from collections import defaultdict
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

import ffmpeg

from ...config import is_sto_host, logger

EPISODE_URL_PREFIX = "aniworld_episode_url="
SEASON_EPISODE_NUMBERS_ENV = "ANIWORLD_SEASON_EPISODE_NUMBERS"

_EPISODE_MARKER = re.compile(
    r"\[\s*(?:JP\s+)?Episode\s+([0-9]+)\s*\]|^\s*(?:JP\s+)?Episode\s+([0-9]+)\s*$",
    re.IGNORECASE,
)


def season_episode_numbers_enabled():
    """Opt-in: keep the site's per-season index instead of title markers."""
    return os.environ.get(SEASON_EPISODE_NUMBERS_ENV, "0") == "1"


def episode_number_from_title(title):
    """Read an explicit marker, never an unrelated number in a title."""
    numbers = {
        int(marked or standalone)
        for marked, standalone in _EPISODE_MARKER.findall(title or "")
    }
    if len(numbers) == 1:
        number = numbers.pop()
        if number > 0:
            return number
    return None


def episode_url_from_file(path):
    """Read source metadata again only when the local file changes."""
    path = Path(path)
    try:
        stat = path.stat()
    except OSError:
        return None
    return _read_episode_url(path, stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=2048)
def _read_episode_url(path, _modified_ns, _size):
    try:
        tags = ffmpeg.probe(path).get("format", {}).get("tags", {})
    except (ffmpeg.Error, OSError):
        return None
    for key, value in tags.items():
        if (
            key.lower() == "comment"
            and isinstance(value, str)
            and value.startswith(EPISODE_URL_PREFIX)
        ):
            return value.removeprefix(EPISODE_URL_PREFIX)
    return None


def _episode_identity(url):
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    host = "serienstream" if is_sto_host(url) else parsed.hostname
    return host, parsed.path.rstrip("/")


def episode_file_matches_source(path, url):
    """Check a recorded source URL, including SerienStream's mirror domains."""
    source = episode_url_from_file(path)
    return bool(source and _episode_identity(source) == _episode_identity(url))


def downloaded_episode_owners(
    episodes, downloaded, *, strict=True, ambiguous_urls=None
):
    """Match source tags first, optionally collecting ambiguous URLs without guessing."""
    episodes = list(episodes)
    use_sources = any(hasattr(episode, "season_episode_number") for episode in episodes)
    identities = {_episode_identity(episode.url): episode.url for episode in episodes}
    candidates = defaultdict(set)
    seasonal = {}
    for episode in episodes:
        season = episode.season.season_number
        seasonal[
            season, getattr(episode, "season_episode_number", episode.episode_number)
        ] = episode.url
        for number in {
            episode.episode_number,
            getattr(episode, "season_episode_number", episode.episode_number),
        }:
            candidates[season, number].add(episode.url)

    owners = {}
    seasons = {season for season, _ in candidates}
    for key in downloaded:
        if key[0] not in seasons:
            continue
        urls = candidates.get(key, set())
        files = downloaded[key] if isinstance(downloaded, Mapping) else (key,)
        for file in files:
            source = (
                episode_url_from_file(file)
                if use_sources and isinstance(file, Path)
                else None
            )
            if source:
                url = identities.get(_episode_identity(source))
                if url is not None:
                    owners[file] = url
                continue
            if not urls:
                continue
            matches = urls
            if len(matches) != 1:
                season, number = key
                if not strict:
                    if ambiguous_urls is not None:
                        ambiguous_urls.update(matches)
                        continue
                    # Read-only callers fall back to the pre-English seasonal naming.
                    logger.warning(
                        "Ambiguous episode numbering at S%02dE%03d without source "
                        "metadata, assuming the seasonal index: %s",
                        season,
                        number,
                        file,
                    )
                    if key in seasonal:
                        owners[file] = seasonal[key]
                    continue
                raise ValueError(
                    f"Ambiguous episode numbering at S{season:02d}E{number:03d}: "
                    "the file could be a seasonal or English-title episode number "
                    "and has no matching source metadata. Check this file before retrying."
                )
            url = next(iter(matches))
            if file in owners and owners[file] != url:
                raise ValueError(f"Episode path matches multiple episodes: {file}")
            owners[file] = url
    return owners


def episode_is_downloaded(episode, downloaded, *, ambiguous_urls=None):
    """Recognise old and new names, resolving overlaps against the season list."""
    season = episode.season.season_number
    if not any(sn == season for sn, _ in downloaded):
        return False
    episodes = season_episode_context(episode)
    owners = downloaded_episode_owners(
        episodes, downloaded, strict=False, ambiguous_urls=ambiguous_urls
    )
    return episode.url in owners.values()


def season_episode_context(episode):
    """Include direct/feed entries even if the season listing is not updated yet."""
    return [
        entry
        for entry in getattr(episode.season, "episodes", ())
        if entry.url != episode.url
    ] + [episode]
