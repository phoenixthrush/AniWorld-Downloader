"""Library browsing.

Everything is loaded on demand: listing the locations only checks that the
directories exist, opening a location lists its folder names, and only opening
a single title walks that one folder. Nothing ever scans the whole tree.

Each title folder carries a `.aniworld` sidecar (see aniworld.sidecar): the
series URL, title, poster and episode titles the downloader knew, or what a
scan of the filenames could tell. The cards page reads those instead of
walking every folder, and the first visit to a folder without one writes it,
so a library that predates sidecars gets the fast path after one browse.
Watch positions are per account and live in the database, never in the
media folders.
"""

import base64
import re
import shutil
from pathlib import Path

from .. import sidecar
from ..logger import get_logger
from . import db, paths
from .media import EPISODE_RE

logger = get_logger(__name__)

VIDEO_EXTENSIONS = set(sidecar.VIDEO_EXTENSIONS)

# Containers a browser can open directly in <video>. Everything else is fed
# through the client-side remuxer (static/mkv-remux.js), never transcoded here.
BROWSER_NATIVE = {".mp4", ".m4v", ".mov", ".webm"}

# A cover frame is a small JPEG the browser rendered from the episode. Keep
# a hard ceiling so the endpoint cannot be used to fill the disk.
THUMBNAIL_MAX_BYTES = 600 * 1024
_JPEG_MAGIC = b"\xff\xd8\xff"

MIME_TYPES = {
    ".mkv": "video/x-matroska",
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".avi": "video/x-msvideo",
    ".ts": "video/mp2t",
    ".flv": "video/x-flv",
    ".wmv": "video/x-ms-wmv",
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


def _movie_files(target):
    """Video files with no SxxExx pattern, e.g. a standalone film. Stable order.

    ".temp_" is excluded wherever it appears in the name, not just as a
    prefix: an in-progress download can carry it as an infix (e.g.
    "Title.temp_full.mkv"), which a prefix-only check would miss and list
    as a finished file.
    """
    files = [
        f
        for f in target.rglob("*")
        if f.is_file()
        and ".temp_" not in f.name
        and f.suffix.lower() in VIDEO_EXTENSIONS
        and not EPISODE_RE.search(f.name)
        and not _under_dot_dir(target, f)
    ]
    files.sort(key=lambda f: f.name.lower())
    return files


def _under_dot_dir(root, file):
    """Our thumbnail cache (and any other dot folder) is not library content."""
    try:
        parts = file.relative_to(root).parts[:-1]
    except ValueError:
        return False
    return any(part.startswith(".") for part in parts)


def classify_title(target):
    """Whether a title folder has numbered seasons, movie files, or both.

    A folder-scoped walk (only this title, never the whole tree), used to
    sort a title into the "series" and/or "movies" groups in the library
    view. In-progress (.temp_) files count too: they already carry the
    SxxExx marker, or lack of it, in their filename, so classification does
    not have to wait for the download to finish.
    """
    has_series = False
    has_movies = False
    for file in target.rglob("*"):
        if not file.is_file() or _under_dot_dir(target, file):
            continue
        if EPISODE_RE.search(file.name):
            has_series = True
        elif file.suffix.lower() in VIDEO_EXTENSIONS:
            has_movies = True
    return has_series, has_movies


def _categories(target):
    """The series/movies categories of a folder, from its sidecar when it has one.

    The sidecar's TYPE line is written by the same walk classify_title does,
    so a title that has one costs a single small read here. Folders without
    one (or whose sidecar says nothing yet, e.g. only an in-progress file)
    are walked as before.
    """
    data = sidecar.read(target)
    if data and data["type"]:
        return data["type"].split(",")
    has_series, has_movies = classify_title(target)
    categories = [c for c, flag in (("series", has_series), ("movies", has_movies)) if flag]
    return categories or ["series"]


def _episode_titles(data, season, episode):
    entry = data["episodes"].get(sidecar.episode_key(season, episode)) if data else None
    return (entry or {}).get("title_de", ""), (entry or {}).get("title_en", "")


def read_title(folder, custom_path_id=None, lang_folder=None, username=None):
    """Seasons and episode files of one title. Only this folder is walked.

    Files without a SxxExx marker are not skipped outright: if they are a
    video file they are almost always a movie rather than a missing episode,
    so they are grouped under a synthetic "movie" season instead of vanishing
    from the listing.

    Every episode also carries its relative `path` (what the file and
    thumbnail endpoints take), the titles the sidecar knows, whether a cover
    frame is cached, and the caller's watch progress.
    """
    base = _resolve_base(custom_path_id, lang_folder)
    target = _safe_child(base, folder)
    if target is None or not target.is_dir():
        raise LibraryError("Title not found")

    data = sidecar.load(target)
    progress = db.get_watch_progress(
        username, db.location_key(custom_path_id, lang_folder), folder
    )

    seasons = {}
    total_size = 0
    total_episodes = 0
    files_seen = []

    for file in target.rglob("*"):
        if not file.is_file() or ".temp_" in file.name or _under_dot_dir(target, file):
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
        relative = file.relative_to(target).as_posix()
        if is_video:
            files_seen.append((relative, int(season), episode))

        entries = seasons.setdefault(season, [])
        if any(e["episode"] == episode and e["file"] == file.name for e in entries):
            continue
        title_de, title_en = _episode_titles(data, int(season), episode)
        entries.append(
            {
                "episode": episode,
                "file": file.name,
                "path": relative,
                "size": size,
                "is_video": is_video,
                "title_de": title_de,
                "title_en": title_en,
                "thumbnail": is_video
                and sidecar.thumbnail_path(target, relative).is_file(),
                "progress": progress.get(relative),
            }
        )
        total_size += size
        if is_video:
            total_episodes += 1

    for entries in seasons.values():
        entries.sort(key=lambda e: e["episode"])

    movie_files = _movie_files(target)
    if movie_files:
        entries = []
        for index, file in enumerate(movie_files):
            try:
                size = file.stat().st_size
            except OSError:
                size = 0
            relative = file.relative_to(target).as_posix()
            files_seen.append((relative, None, None))
            entries.append(
                {
                    "episode": index + 1,
                    "file": file.name,
                    "path": relative,
                    "size": size,
                    "is_video": True,
                    "title_de": "",
                    "title_en": "",
                    "thumbnail": sidecar.thumbnail_path(target, relative).is_file(),
                    "progress": progress.get(relative),
                }
            )
            total_size += size
            total_episodes += 1
        seasons["movie"] = entries

    # The walk just happened, so the sidecar's episode keys get to match it.
    data, changed = sidecar.reconcile(target, data, files_seen)
    if changed:
        sidecar.write(target, data)

    return {
        "folder": folder,
        "meta": _meta(data),
        "seasons": seasons,
        "total_episodes": total_episodes,
        "total_size": total_size,
    }


def _meta(data):
    return {
        "title": data["title"],
        "year": data["year"],
        "imdb": data["imdb"],
        "site": data["site"],
        "series_url": data["series_url"],
        "poster_url": data["poster_url"],
        "description": data["description"],
        "genres": list(data["genres"]),
        "origin": data["origin"],
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


def _safe_relative(target, relative):
    """Resolve a file path relative to a title folder, refusing to leave it.

    Unlike _safe_child this allows subdirectories ("Season 01/x.mkv"), which
    is exactly what the naming template produces, but nothing absolute, no
    "..", no NUL, and nothing that resolves outside the folder (symlinks
    included).
    """
    text = str(relative or "").replace("\\", "/")
    if not text or "\x00" in text or text.startswith("/"):
        return None
    parts = text.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return None
    file = target.joinpath(*parts)
    try:
        file.resolve().relative_to(target.resolve())
    except (ValueError, OSError):
        return None
    return file


def resolve_file(folder, relative, custom_path_id=None, lang_folder=None):
    """(title folder, video file) for a stream request, or a LibraryError.

    Only finished video files are served; the sidecar, thumbnails and
    in-progress downloads are not reachable through this.
    """
    base = _resolve_base(custom_path_id, lang_folder)
    target = _safe_child(base, folder)
    if target is None or not target.is_dir():
        raise LibraryError("Title not found")
    file = _safe_relative(target, relative)
    if (
        file is None
        or not file.is_file()
        or ".temp_" in file.name
        or file.suffix.lower() not in VIDEO_EXTENSIONS
        or _under_dot_dir(target, file)
    ):
        raise LibraryError("File not found")
    return target, file


def mime_type(file):
    return MIME_TYPES.get(Path(file).suffix.lower(), "application/octet-stream")


# ---------------------------------------------------------------------------
# Thumbnails
#
# A cover frame per episode, rendered in the browser (which already decoded
# the video to play it) and posted back so every later visitor, on any
# device, gets it without decoding anything. Stored next to the video in
# .aniworld-thumbs/, which travels with the library.
# ---------------------------------------------------------------------------
def thumbnail_file(folder, relative, custom_path_id=None, lang_folder=None):
    target, file = resolve_file(folder, relative, custom_path_id, lang_folder)
    thumb = sidecar.thumbnail_path(target, file.relative_to(target).as_posix())
    return thumb if thumb.is_file() else None


def thumbnail_by_stem(folder, stem, custom_path_id=None, lang_folder=None):
    """A cached frame by its file stem, for a card whose title has no poster."""
    base = _resolve_base(custom_path_id, lang_folder)
    target = _safe_child(base, folder)
    if target is None or not target.is_dir():
        raise LibraryError("Title not found")
    name = str(stem or "")
    if not name or "/" in name or "\\" in name or ".." in name or "\x00" in name:
        raise LibraryError("Invalid thumbnail")
    thumb = sidecar.thumbs_dir(target) / f"{name}.jpg"
    return thumb if thumb.is_file() else None


def decode_thumbnail(image):
    """The JPEG bytes out of a data URL or bare base64 string, or a LibraryError."""
    text = str(image or "").strip()
    if "," in text and text.lower().startswith("data:"):
        header, _, text = text.partition(",")
        if "image/jpeg" not in header.lower():
            raise LibraryError("Only JPEG thumbnails are accepted")
    try:
        raw = base64.b64decode(text, validate=True)
    except (ValueError, TypeError):
        raise LibraryError("Thumbnail is not valid base64") from None
    if not raw.startswith(_JPEG_MAGIC):
        raise LibraryError("Thumbnail is not a JPEG")
    if len(raw) > THUMBNAIL_MAX_BYTES:
        raise LibraryError("Thumbnail is too large")
    return raw


def store_thumbnail(folder, relative, raw, custom_path_id=None, lang_folder=None):
    """Write a cover frame. Returns False when sidecar writes are off."""
    target, file = resolve_file(folder, relative, custom_path_id, lang_folder)
    if not sidecar.writes_enabled():
        return False
    thumb = sidecar.thumbnail_path(target, file.relative_to(target).as_posix())
    try:
        thumb.parent.mkdir(exist_ok=True)
        temp = thumb.with_suffix(".tmp")
        temp.write_bytes(raw)
        temp.replace(thumb)
    except OSError as exc:
        logger.debug("Could not store thumbnail %s: %s", thumb, exc)
        return False
    return True


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------
def _cover(target, data):
    """What to show on the card: the poster if known, else a cached frame."""
    if data["poster_url"]:
        return {"kind": "poster", "url": data["poster_url"]}
    thumbs = sidecar.thumbs_dir(target)
    if thumbs.is_dir():
        try:
            for file in sorted(thumbs.iterdir()):
                if file.suffix == ".jpg":
                    return {"kind": "thumb", "stem": file.stem}
        except OSError:
            pass
    return None


def list_cards(custom_path_id=None, lang_folder=None, username=None):
    """One card per title: identity from the sidecar, progress from the database.

    Folders without a sidecar get one from a filename scan on this visit and
    are single reads from then on. No per-title walk happens for titles that
    already have one, which is what keeps this usable on large libraries.
    """
    base = _resolve_base(custom_path_id, lang_folder)
    titles = list_titles(custom_path_id, lang_folder)
    summary = db.watch_summary(username, db.location_key(custom_path_id, lang_folder))

    cards = []
    for folder in titles:
        target = _safe_child(base, folder)
        if target is None:
            continue
        data = sidecar.load(target)
        categories = data["type"].split(",") if data["type"] else _categories(target)
        watched = summary.get(folder, {})
        cards.append(
            {
                "folder": folder,
                "title": data["title"] or folder,
                "year": data["year"],
                "site": data["site"],
                "categories": categories,
                "genres": list(data["genres"]),
                "episodes": len(data["episodes"]),
                "cover": _cover(target, data),
                "watched": watched.get("watched", 0),
                "in_progress": watched.get("in_progress", 0),
                "last_watched": watched.get("last"),
                "origin": data["origin"],
            }
        )
    return cards


def _location_from_key(key):
    """Undo db.location_key: "3:german-dub" -> (3, "german-dub")."""
    path_id, _, lang_folder = str(key).partition(":")
    try:
        path_id = int(path_id)
    except ValueError:
        path_id = 0
    return (path_id or None), (lang_folder or None)


def continue_watching(username, limit=12):
    """Started but unfinished episodes, newest first, ready to render.

    Rows whose file has gone (deleted outside the app) are dropped from the
    result and from the table, so the strip never offers a dead link.
    """
    items = []
    for row in db.continue_watching(username, limit * 2):
        path_id, lang_folder = _location_from_key(row["location"])
        try:
            target, file = resolve_file(row["folder"], row["file"], path_id, lang_folder)
        except LibraryError:
            db.delete_watch_progress(row["location"], row["folder"], [row["file"]])
            continue
        data = sidecar.read(target) or sidecar.scan(target)
        match = EPISODE_RE.search(file.name)
        season = int(match.group(1)) if match else None
        episode = int(match.group(2)) if match else None
        title_de, title_en = (
            _episode_titles(data, season, episode) if match else ("", "")
        )
        items.append(
            {
                "custom_path_id": path_id,
                "lang_folder": lang_folder,
                "folder": row["folder"],
                "path": row["file"],
                "title": data["title"] or row["folder"],
                "season": season,
                "episode": episode,
                "title_de": title_de,
                "title_en": title_en,
                "thumbnail": sidecar.thumbnail_path(target, row["file"]).is_file(),
                "position": row["position"],
                "duration": row["duration"],
                "updated_at": row["updated_at"],
            }
        )
        if len(items) >= limit:
            break
    return items


# ---------------------------------------------------------------------------
# Deleting
# ---------------------------------------------------------------------------
def delete(folder, season=None, episode=None, custom_path_id=None, lang_folder=None):
    """Delete a whole title, one season, a single episode, or one movie file."""
    base = _resolve_base(custom_path_id, lang_folder)
    target = _safe_child(base, folder)
    if target is None:
        raise LibraryError("Invalid folder name")
    if not target.is_dir():
        raise LibraryError("Nothing found to delete")
    location = db.location_key(custom_path_id, lang_folder)

    if season is None:
        shutil.rmtree(target, ignore_errors=True)
        db.delete_watch_progress(location, folder)
        return 1

    if str(season) == "movie":
        movie_files = _movie_files(target)
        if episode is not None:
            index = int(episode) - 1
            if index < 0 or index >= len(movie_files):
                raise LibraryError("Nothing found to delete")
            movie_files = [movie_files[index]]
        deleted = _unlink_all(target, movie_files, location, folder)
        _prune_empty(target)
        if deleted == 0:
            raise LibraryError("Nothing found to delete")
        return deleted

    if episode is not None:
        pattern = re.compile(
            rf"S{int(season):02d}E{int(episode):03d}(?!\d)", re.IGNORECASE
        )
    else:
        pattern = re.compile(rf"S{int(season):02d}E\d{{2,3}}", re.IGNORECASE)

    files = [
        file
        for file in list(target.rglob("*"))
        if file.is_file() and pattern.search(file.name) and not _under_dot_dir(target, file)
    ]
    deleted = _unlink_all(target, files, location, folder)
    _prune_empty(target)
    if deleted == 0:
        raise LibraryError("Nothing found to delete")
    return deleted


def _unlink_all(target, files, location, folder):
    """Delete files and everything that referred to them: thumbnails, titles, progress."""
    deleted = 0
    gone = []
    for file in files:
        try:
            relative = file.relative_to(target).as_posix()
            file.unlink()
            deleted += 1
            gone.append(relative)
        except OSError:
            pass
    if gone:
        sidecar.forget_files(target, gone)
        db.delete_watch_progress(location, folder, gone)
    return deleted


def _prune_empty(root):
    """Remove directories left empty after a delete, deepest first.

    The sidecar and thumbnail cache do not keep a folder alive: a title whose
    last video went is gone, metadata about nothing is not worth keeping.
    """
    if root.is_dir() and not any(
        f.is_file() and not _under_dot_dir(root, f) and f.name != sidecar.SIDECAR_NAME
        for f in root.rglob("*")
    ):
        sidecar.remove(root)
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


def list_titles_with_meta(custom_path_id=None, lang_folder=None):
    """Titles plus which of "series"/"movies" each one belongs to.

    A title can be both (e.g. a series with a bonus film in the same
    folder), so this is a list of categories per title, not a single value.
    """
    base = _resolve_base(custom_path_id, lang_folder)
    titles = list_titles(custom_path_id, lang_folder)

    result = []
    for folder in titles:
        target = _safe_child(base, folder)
        categories = _categories(target) if target else ["series"]
        result.append({"folder": folder, "categories": categories})
    return result


def custom_path_labels():
    return {entry["id"]: entry["name"] for entry in db.get_custom_paths()}
