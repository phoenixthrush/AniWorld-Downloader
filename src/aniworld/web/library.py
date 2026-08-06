"""Library browsing.

Everything is loaded on demand: listing the locations only checks that the
directories exist, opening a location lists its folder names, and only opening
a single title walks that one folder. Nothing ever scans the whole tree.
"""

import re
import shutil

from ..logger import get_logger
from . import db, paths
from .media import EPISODE_RE

logger = get_logger(__name__)

VIDEO_EXTENSIONS = {
    ".mkv",
    ".mp4",
    ".avi",
    ".webm",
    ".flv",
    ".mov",
    ".wmv",
    ".m4v",
    ".ts",
}


class LibraryError(ValueError):
    """Raised for an invalid library request."""


def _resolve_base(custom_path_id, lang_folder):
    """Turn the request parameters into a directory, rejecting anything unknown."""
    if custom_path_id:
        base = paths.custom_path_base(custom_path_id)
        if base is None:
            raise LibraryError("Custom path not found")
    else:
        base = paths.default_download_path()

    if lang_folder:
        if lang_folder not in paths.ALL_LANG_FOLDERS:
            raise LibraryError("Invalid language folder")
        base = base / lang_folder
    return base


def list_locations():
    """Browsable roots, one entry per (download path x language folder)."""
    separated = paths.lang_separation_enabled()
    locations = []

    for label, path_id, root in paths.download_roots():
        if not separated:
            locations.append(
                {
                    "label": label,
                    "custom_path_id": path_id,
                    "lang_folder": None,
                    "path": str(root),
                    "exists": root.is_dir(),
                }
            )
            continue

        for folder in paths.ALL_LANG_FOLDERS:
            base = root / folder
            if not base.is_dir():
                continue
            locations.append(
                {
                    "label": label,
                    "custom_path_id": path_id,
                    "lang_folder": folder,
                    "path": str(base),
                    "exists": True,
                }
            )

    return {"lang_separation": separated, "locations": locations}


def list_titles(custom_path_id=None, lang_folder=None):
    """Folder names inside one location. A single iterdir, no recursion."""
    base = _resolve_base(custom_path_id, lang_folder)
    if not base.is_dir():
        return []

    skip = set(paths.ALL_LANG_FOLDERS) if not lang_folder else set()
    try:
        entries = list(base.iterdir())
    except OSError as exc:
        logger.warning("Could not read %s: %s", base, exc)
        return []

    titles = [
        entry.name
        for entry in entries
        if entry.is_dir() and entry.name not in skip and not entry.name.startswith(".")
    ]
    titles.sort(key=str.lower)
    return titles


def read_title(folder, custom_path_id=None, lang_folder=None):
    """Seasons and episode files of one title. Only this folder is walked."""
    base = _resolve_base(custom_path_id, lang_folder)
    target = _safe_child(base, folder)
    if target is None or not target.is_dir():
        raise LibraryError("Title not found")

    seasons = {}
    total_size = 0
    total_episodes = 0

    for file in target.rglob("*"):
        if not file.is_file() or file.name.startswith(".temp_"):
            continue
        match = EPISODE_RE.search(file.name)
        if not match:
            continue

        season = str(int(match.group(1)))
        episode = int(match.group(2))
        try:
            size = file.stat().st_size
        except OSError:
            size = 0
        is_video = file.suffix.lower() in VIDEO_EXTENSIONS

        entries = seasons.setdefault(season, [])
        if any(e["episode"] == episode and e["file"] == file.name for e in entries):
            continue
        entries.append(
            {
                "episode": episode,
                "file": file.name,
                "size": size,
                "is_video": is_video,
            }
        )
        total_size += size
        if is_video:
            total_episodes += 1

    for entries in seasons.values():
        entries.sort(key=lambda e: e["episode"])

    return {
        "folder": folder,
        "seasons": seasons,
        "total_episodes": total_episodes,
        "total_size": total_size,
    }


def _safe_child(base, folder):
    """Resolve `folder` inside `base`, refusing traversal and separators."""
    name = str(folder or "")
    if not name or "/" in name or "\\" in name or "\x00" in name or ".." in name:
        return None
    child = base / name
    try:
        child.resolve().relative_to(base.resolve())
    except (ValueError, OSError):
        return None
    return child


def delete(folder, season=None, episode=None, custom_path_id=None, lang_folder=None):
    """Delete a whole title, one season or a single episode."""
    base = _resolve_base(custom_path_id, lang_folder)
    target = _safe_child(base, folder)
    if target is None:
        raise LibraryError("Invalid folder name")
    if not target.is_dir():
        raise LibraryError("Nothing found to delete")

    if season is None:
        shutil.rmtree(target, ignore_errors=True)
        return 1

    if episode is not None:
        pattern = re.compile(
            rf"S{int(season):02d}E{int(episode):03d}(?!\d)", re.IGNORECASE
        )
    else:
        pattern = re.compile(rf"S{int(season):02d}E\d{{2,3}}", re.IGNORECASE)

    deleted = 0
    for file in list(target.rglob("*")):
        if file.is_file() and pattern.search(file.name):
            try:
                file.unlink()
                deleted += 1
            except OSError:
                pass

    _prune_empty(target)
    if deleted == 0:
        raise LibraryError("Nothing found to delete")
    return deleted


def _prune_empty(root):
    """Remove directories left empty after a delete, deepest first."""
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass
    try:
        root.rmdir()
    except OSError:
        pass


def custom_path_labels():
    return {entry["id"]: entry["name"] for entry in db.get_custom_paths()}
