"""Template paths for movie and series models."""

import os
import re
from pathlib import Path

from ...config import NAMING_TEMPLATE
from .common import clean_title
from .numbering import downloaded_episode_owners, season_episode_context


def numbered_episode_path(episode, number, *, padding=3):
    """Render the existing AniWorld/SerienStream template with one episode number."""
    parts = os.getenv("ANIWORLD_NAMING_TEMPLATE", NAMING_TEMPLATE).split("/")
    values = {
        "title": episode.series.title_cleaned,
        "year": episode.series.release_year,
        "imdbid": episode.series.imdb,
        "season": f"{episode.season.season_number:02d}",
        "episode": f"{number:0{padding}d}",
        "language": episode.selected_language,
        "resolution": getattr(episode, "_resolution", "unknown"),
    }
    base = Path(episode.selected_path)
    if len(parts) > 1:
        base /= parts[0].format(**values)
    folder = base / parts[1].format(**values) if len(parts) > 2 else base
    filename = parts[-1]
    if "." in filename:
        filename = filename.rsplit(".", 1)[0]
    for key in values:
        filename = filename.replace(f"%{key}%", f"{{{key}}}")
    return base, folder / f"{filename.format(**values)}.{episode._file_extension}"


def existing_numbered_episode_path(episode):
    """Prefer the new path, but keep using a download at its seasonal path."""
    base, path = numbered_episode_path(episode, episode.episode_number)
    seasonal = episode.season_episode_number
    candidates = [
        (number, *numbered_episode_path(episode, number, padding=padding))
        for number in dict.fromkeys((episode.episode_number, seasonal))
        for padding in (3, 2)
    ]
    existing = [entry for entry in candidates if entry[2].is_file()]
    if not existing:
        return base, path
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
    for number, candidate_base, candidate in existing:
        if owners.get(candidate) == episode.url:
            return candidate_base, candidate
    if any(number == episode.episode_number for number, _, _ in existing):
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
