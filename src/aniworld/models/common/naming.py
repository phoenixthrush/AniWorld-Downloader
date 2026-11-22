"""Template paths for movie and series models."""

import os
import re
from pathlib import Path

from ...config import NAMING_TEMPLATE
from .common import clean_title
from .numbering import (
    downloaded_episode_owners,
    episode_file_matches_source,
    season_episode_context,
    season_episode_numbers_enabled,
)


def numbered_episode_path(episode, number, *, padding=3, legacy_folders=False):
    """Render the existing AniWorld/SerienStream template with one episode number."""
    template = os.getenv("ANIWORLD_NAMING_TEMPLATE", NAMING_TEMPLATE)
    values = {
        "title": episode.series.title_cleaned,
        "year": episode.series.release_year,
        "imdbid": episode.series.imdb,
        "season": f"{episode.season.season_number:02d}",
        "episode": f"{number:0{padding}d}",
        "language": episode.selected_language,
        "resolution": getattr(episode, "_resolution", "unknown"),
    }
    folders, _, filename = template.rpartition("/")
    for key in values:
        placeholder = f"%{key}%"
        replacement = f"{{{key}}}"
        filename = filename.replace(placeholder, replacement)
        if not legacy_folders:
            folders = folders.replace(placeholder, replacement)
    parts = folders.split("/") if "/" in template else []
    base = Path(episode.selected_path)
    if parts:
        base /= parts[0].format(**values)
    folder = base / parts[1].format(**values) if len(parts) > 1 else base
    if "." in filename:
        filename = filename.rsplit(".", 1)[0]
    return base, folder / f"{filename.format(**values)}.{episode._file_extension}"


def legacy_numbered_episode_paths(episode):
    """Yield the paths rendered before percent placeholders worked in folders."""
    template = os.getenv("ANIWORLD_NAMING_TEMPLATE", NAMING_TEMPLATE)
    if "%" not in template.rpartition("/")[0]:
        return
    for number in dict.fromkeys(
        (episode.episode_number, episode.season_episode_number)
    ):
        for padding in (3, 2):
            legacy = numbered_episode_path(
                episode, number, padding=padding, legacy_folders=True
            )
            if legacy != numbered_episode_path(episode, number, padding=padding):
                yield legacy


def existing_numbered_episode_path(episode):
    """Keep using existing downloads at their seasonal or legacy template paths."""
    seasonal = episode.season_episode_number
    preferred = seasonal if season_episode_numbers_enabled() else episode.episode_number
    base, path = numbered_episode_path(episode, preferred)
    candidates = [
        (number, *numbered_episode_path(episode, number, padding=padding))
        for number in dict.fromkeys((episode.episode_number, seasonal))
        for padding in (3, 2)
    ]
    existing = [entry for entry in candidates if entry[2].is_file()]
    if existing:
        episodes = season_episode_context(episode)
        numbers = {
            number
            for entry in episodes
            for number in (entry.episode_number, entry.season_episode_number)
        }
        have = {}
        for number in numbers:
            files = {
                numbered_episode_path(episode, number, padding=padding)[1]
                for padding in (3, 2)
            }
            have[episode.season.season_number, number] = [
                file for file in files if file.is_file()
            ]
        owners = downloaded_episode_owners(episodes, have)
        for _, candidate_base, candidate in existing:
            if owners.get(candidate) == episode.url:
                return candidate_base, candidate
    # Literal folders could be shared across series, so numbering alone is unsafe.
    for candidate_base, candidate in legacy_numbered_episode_paths(episode):
        if candidate.is_file() and episode_file_matches_source(candidate, episode.url):
            return candidate_base, candidate
    if any(number == preferred for number, _, _ in existing):
        raise ValueError(f"Episode path belongs to a different episode: {path}")
    return base, path


def template_path(root, template, values, *, is_series, movie_folder=True):
    """Format all path components, keeping metadata inside each component."""
    for key in values:
        template = template.replace(f"%{key}%", f"{{{key}}}")
    values = {key: clean_title(str(value or "")) for key, value in values.items()}
    parts = template.split("/")
    if not is_series:
        parts = [part for part in parts[:-1] if "{season}" not in part] + parts[-1:]
        parts[-1] = parts[-1].replace("{title} S{season}E{episode}", "{title} ({year})")
        parts[-1] = parts[-1].replace("S{season}E{episode}", "")
        if not movie_folder:
            parts = parts[-1:]
    formatted = []
    for part in parts:
        part = part.format(**values)
        part = re.sub(r"\s*\[imdbid-\]\s*", " ", part)
        part = part.replace("()", "")
        part = clean_title(part)
        part = re.sub(r"\s+", " ", part).strip(" .")
        if part in {"", ".", ".."}:
            continue
        formatted.append(part)
    if not formatted:
        raise ValueError("Naming template does not produce a filename")
    path = Path(root).expanduser().joinpath(*formatted)
    return path if Path(parts[-1]).suffix else Path(f"{path}.mkv")
