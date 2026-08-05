"""Download path resolution shared by the worker, the library and the API."""

import os
from pathlib import Path

from . import db

# Subfolder used per language when language separation is on.
LANG_FOLDERS = {
    "German Dub": "german-dub",
    "German Sub": "german-sub",
    "English Dub": "english-dub",
    "English Sub": "english-sub",
}

ALL_LANG_FOLDERS = tuple(LANG_FOLDERS.values())


def lang_separation_enabled():
    return os.environ.get("ANIWORLD_LANG_SEPARATION", "0") == "1"


def lang_folder_for(language):
    """Folder name for a language label, e.g. 'German Dub' -> 'german-dub'."""
    return LANG_FOLDERS.get(language, str(language).lower().replace(" ", "-"))


def expand(raw):
    """Turn a configured path into an absolute Path (relative = below $HOME)."""
    path = Path(str(raw)).expanduser()
    if not path.is_absolute():
        path = Path.home() / path
    return path


def default_download_path():
    raw = os.environ.get("ANIWORLD_DOWNLOAD_PATH", "").strip()
    return expand(raw) if raw else Path.home() / "Downloads"


def custom_path_base(custom_path_id):
    """Base directory of a custom path, or None when it no longer exists."""
    entry = db.get_custom_path(custom_path_id)
    return expand(entry["path"]) if entry else None


def base_for(custom_path_id=None):
    """Where a download goes: the chosen custom path, else the default path."""
    if custom_path_id:
        base = custom_path_base(custom_path_id)
        if base:
            return base
    return default_download_path()


def download_roots():
    """Every configured root: the default path plus all custom paths."""
    roots = [("Default", None, default_download_path())]
    for entry in db.get_custom_paths():
        roots.append((entry["name"], entry["id"], expand(entry["path"])))
    return roots


def scan_bases():
    """Flat list of directories that may hold downloaded titles.

    With language separation on, each root contributes its language subfolders
    instead of the root itself.
    """
    bases = []
    separated = lang_separation_enabled()
    for _, _, root in download_roots():
        if separated:
            bases.extend(root / folder for folder in ALL_LANG_FOLDERS)
        else:
            bases.append(root)
    return bases


def target_path(language, custom_path_id=None):
    """Directory a download should be written to, or None to let the downloader decide."""
    base = base_for(custom_path_id)
    if lang_separation_enabled():
        return str(base / lang_folder_for(language))
    if custom_path_id:
        return str(base)
    return None
