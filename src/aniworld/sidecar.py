"""The `.aniworld` sidecar: a `.env`-style identity card in every title folder.

Why it exists. Everything the library and the "already downloaded" checks
know about a folder today, they learn by walking it: one rglob per title to
classify it, one more to list its episodes, and a name heuristic
(folder_matches_title) to decide which folder belongs to which series. That is
fine for fifty titles and slow for the multi-terabyte libraries people run
this against, and the heuristic cannot tell "K-On!" from "K-On!!" for sure.

The downloader, on the other hand, knows everything at the moment it writes an
episode: the site, the series URL, the poster, the episode titles in both
languages. This module writes that down next to the files, so that a later
lookup is one small read and an exact match, and so that anything else (a
script, a media-server post-processor, the web UI's cards page) can identify
the folder without parsing filenames.

The format is deliberately the one everybody already has a parser for:

    # AniWorld series metadata
    ANIWORLD=1
    ORIGIN=download
    SITE=aniworld
    SERIES_URL="https://aniworld.to/anime/stream/black-torch"
    TITLE="BLACK TORCH"
    YEAR="2026-2026"
    IMDB="tt37532893"
    POSTER_URL="https://aniworld.to/public/img/cover/black-torch.jpg"
    GENRES="Action, Fantasy"
    TYPE=series
    S01E001="Die schwarze Fackel|The Black Torch"

Design rules:
- Dot-prefixed, so the library's title listing and media servers ignore it.
- KEY=VALUE, UTF-8, read with python-dotenv. Titles and URLs, never binary,
  never secrets. Per-episode lines carry "German title|English title" only;
  which files exist is always read from disk, a cache must not claim files.
- Tolerant reader: anything malformed reads as "no sidecar". A broken file can
  never break a download or a page.
- Writes are atomic (temp file + os.replace) and never raise into the caller.
- `scan()` builds one from the filenames so an existing library gets the fast
  path the first time it is browsed; `origin` says whether the data came from
  a download (trusted) or a scan (titles unknown, URL unknown).
- ANIWORLD_LIBRARY_SIDECARS=0 turns every write off (read-only mounts, people
  who want nothing extra in their media folders); reads still work.
"""

import io
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values

from .logger import get_logger

logger = get_logger(__name__)

SIDECAR_NAME = ".aniworld"
THUMBS_DIR = ".aniworld-thumbs"
VERSION = 1

# Matched on the filename rather than the naming template so files keep being
# recognised after the template changes. web/media.py re-exports this.
EPISODE_RE = re.compile(r"S(\d{2})E(\d{2,3})", re.IGNORECASE)
_EPISODE_KEY_RE = re.compile(r"^S(\d{2})E(\d{3})$")

VIDEO_EXTENSIONS = frozenset(
    {".mkv", ".mp4", ".avi", ".webm", ".flv", ".mov", ".wmv", ".m4v", ".ts"}
)

# What the default naming template turns a title into:
# "Naruto (2002-2007) [imdbid-tt0409591]". Both decorations are optional.
_FOLDER_NAME_RE = re.compile(
    r"^(?P<title>.+?)"
    r"(?:\s+\((?P<year>\d{4}(?:\s*[-–]\s*\d{4})?)\))?"
    r"(?:\s+\[imdbid-(?P<imdb>tt\d+)\])?$"
)

# aniworld.to lists the available languages among the genres ("Ger", "GerSub",
# "EngSub"). Those describe the site's streams, not the show.
_LANGUAGE_TAG_RE = re.compile(r"^(ger|eng|jap)(sub|dub)?$", re.IGNORECASE)

# Series-level keys, in the order they are written.
FIELDS = (
    "origin",
    "site",
    "series_url",
    "title",
    "year",
    "imdb",
    "poster_url",
    "description",
    "genres",
    "type",
    "updated",
)


def writes_enabled():
    return os.environ.get("ANIWORLD_LIBRARY_SIDECARS", "1") != "0"


def sidecar_path(folder):
    return Path(folder) / SIDECAR_NAME


def thumbs_dir(folder):
    return Path(folder) / THUMBS_DIR


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_url(url):
    """Series URLs compare without scheme noise, trailing slashes or case."""
    text = str(url or "").strip()
    if not text:
        return ""
    parsed = urlparse(text if "://" in text else f"https://{text}")
    host = (parsed.netloc or "").lower().removeprefix("www.")
    return f"{host}{(parsed.path or '').rstrip('/')}"


def episode_key(season, episode):
    return f"S{int(season):02d}E{int(episode):03d}"


# ---------------------------------------------------------------------------
# The in-memory shape
# ---------------------------------------------------------------------------
def empty(title="", origin="scan"):
    return {
        "origin": origin,
        "site": "",
        "series_url": "",
        "title": title,
        "year": "",
        "imdb": "",
        "poster_url": "",
        "description": "",
        "genres": [],
        "type": "",
        "updated": "",
        # {"S01E001": {"title_de": ..., "title_en": ...}}
        "episodes": {},
    }


def _parse(text):
    try:
        values = dotenv_values(stream=io.StringIO(text))
    except Exception:
        return None
    if not values or str(values.get("ANIWORLD", "")).strip() != str(VERSION):
        return None

    data = empty()
    for key in FIELDS:
        if key == "genres":
            raw = values.get("GENRES") or ""
            data["genres"] = [g.strip() for g in raw.split(",") if g.strip()]
        else:
            data[key] = str(values.get(key.upper()) or "").strip()
    if data["origin"] not in ("download", "scan"):
        data["origin"] = "scan"

    for key, value in values.items():
        match = _EPISODE_KEY_RE.match(key or "")
        if not match:
            continue
        title_de, _, title_en = str(value or "").partition("|")
        data["episodes"][key] = {
            "title_de": title_de.strip(),
            "title_en": title_en.strip(),
        }
    return data


def _quote(value):
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    text = text.replace("\r", " ").replace("\n", "\\n")
    return f'"{text}"'


def _serialize(data):
    lines = [
        "# AniWorld series metadata. Written by aniworld after a download,",
        "# read by the library and the 'already downloaded' checks. Safe to",
        "# edit; safe to delete (it is rebuilt from the filenames).",
        f"ANIWORLD={VERSION}",
    ]
    for key in FIELDS:
        if key == "genres":
            value = ", ".join(data.get("genres") or [])
        else:
            value = data.get(key) or ""
        if key in ("origin", "type"):
            lines.append(f"{key.upper()}={value}")
        else:
            lines.append(f"{key.upper()}={_quote(value)}")

    episodes = data.get("episodes") or {}
    if episodes:
        lines.append("")
        lines.append("# Episode titles: SxxEyyy=\"German|English\"")
        for key in sorted(episodes):
            entry = episodes[key]
            lines.append(
                f"{key}={_quote(entry.get('title_de', '') + '|' + entry.get('title_en', ''))}"
            )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Reading and writing
# ---------------------------------------------------------------------------
def read(folder):
    """The sidecar of a title folder, or None when there is none worth using."""
    path = sidecar_path(folder)
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except FileNotFoundError:
        return None
    except OSError as exc:
        logger.debug("Ignoring unreadable sidecar %s: %s", path, exc)
        return None
    data = _parse(text)
    if data is None:
        logger.debug("Ignoring sidecar %s: not a version %s file", path, VERSION)
    return data


def write(folder, data):
    """Write atomically. Returns True when the file was written.

    Never raises: a read-only share or a vanished folder must not turn into a
    failed download or a failed page, the sidecar is only a cache.
    """
    if not writes_enabled():
        return False
    folder = Path(folder)
    if not folder.is_dir():
        return False

    data = dict(data)
    data["updated"] = _now()
    target = sidecar_path(folder)
    temp = None
    try:
        fd, temp = tempfile.mkstemp(prefix=".aniworld.", suffix=".tmp", dir=folder)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(_serialize(data))
        os.replace(temp, target)
    except OSError as exc:
        logger.debug("Could not write sidecar %s: %s", target, exc)
        if temp:
            try:
                os.unlink(temp)
            except OSError:
                pass
        return False
    return True


def remove(folder):
    """Delete the sidecar and the thumbnail cache of a title folder."""
    try:
        sidecar_path(folder).unlink(missing_ok=True)
    except OSError:
        pass
    thumbs = thumbs_dir(folder)
    if thumbs.is_dir():
        for file in thumbs.iterdir():
            try:
                file.unlink()
            except OSError:
                pass
        try:
            thumbs.rmdir()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# What is actually on disk
# ---------------------------------------------------------------------------
def parse_folder_name(name):
    """(title, year, imdb) from a folder named by the default template."""
    match = _FOLDER_NAME_RE.match(str(name).strip())
    if not match:
        return str(name).strip(), "", ""
    return (
        match.group("title").strip(),
        (match.group("year") or "").replace(" ", ""),
        match.group("imdb") or "",
    )


def _is_hidden(folder, file):
    """Anything under a dot-directory (our thumbnails, a media server's cache)."""
    return any(part.startswith(".") for part in file.relative_to(folder).parts)


def video_files(folder):
    """Finished video files of one title, (relative posix path, season, episode).

    season/episode are None for a file without the SxxEyyy marker, which the
    library treats as a movie. In-progress downloads (".temp_" anywhere in
    the name) and anything under a dot-directory are skipped.
    """
    folder = Path(folder)
    found = []
    try:
        files = sorted(folder.rglob("*"), key=lambda f: f.as_posix().lower())
    except OSError:
        return found
    for file in files:
        try:
            if not file.is_file():
                continue
        except OSError:
            continue
        if ".temp_" in file.name or _is_hidden(folder, file):
            continue
        if file.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        match = EPISODE_RE.search(file.name)
        found.append(
            (
                file.relative_to(folder).as_posix(),
                int(match.group(1)) if match else None,
                int(match.group(2)) if match else None,
            )
        )
    return found


def _type_of(files):
    has_series = any(season is not None for _, season, _ in files)
    has_movies = any(season is None for _, season, _ in files)
    parts = [name for name, flag in (("series", has_series), ("movies", has_movies)) if flag]
    return ",".join(parts)


def scan(folder):
    """A sidecar built from filenames alone: the fallback for old libraries.

    Episode titles and the series URL are unknown here, ORIGIN says so, and
    a later download into the same folder fills them in.
    """
    folder = Path(folder)
    title, year, imdb = parse_folder_name(folder.name)
    data = empty(title, origin="scan")
    data["year"] = year
    data["imdb"] = imdb
    files = video_files(folder)
    data["type"] = _type_of(files)
    for _, season, episode in files:
        if season is not None:
            data["episodes"].setdefault(
                episode_key(season, episode), {"title_de": "", "title_en": ""}
            )
    return data


def load(folder, write_back=True):
    """Sidecar of a folder, scanning and (optionally) storing one when missing.

    The scan is the same folder walk the library did before sidecars existed,
    so the first visit costs what it always cost and later ones cost one read.

    Only a folder with SxxEyyy episode files gets a scanned sidecar written.
    A download root is often a general Downloads folder, and a directory that
    merely contains some video is not this tool's series; a movie the
    downloader saved gets its sidecar from the download itself.
    """
    folder = Path(folder)
    data = read(folder)
    if data is not None:
        return data
    data = scan(folder)
    if write_back and data["episodes"]:
        write(folder, data)
    return data


def reconcile(folder, data, files):
    """Make the episode keys match the files that are really there.

    Keeps titles for episodes that still exist, adds untitled keys for new
    files, forgets deleted ones. Returns (data, changed).
    """
    keys = {
        episode_key(season, episode)
        for _, season, episode in files
        if season is not None
    }
    episodes = {k: v for k, v in data["episodes"].items() if k in keys}
    for key in keys - set(episodes):
        episodes[key] = {"title_de": "", "title_en": ""}
    kind = _type_of(files)
    changed = episodes != data["episodes"] or kind != data["type"]
    if changed:
        data = dict(data)
        data["episodes"] = episodes
        data["type"] = kind
    return data, changed


# ---------------------------------------------------------------------------
# Recording a finished download
# ---------------------------------------------------------------------------
def _site_key(url):
    """A short site name from a page URL, e.g. 'aniworld', 'sto', 'megakino'."""
    host = (urlparse(str(url or "")).netloc or "").lower().removeprefix("www.")
    if not host:
        return ""
    for key, needles in (
        ("aniworld", ("aniworld",)),
        ("sto", ("s.to", "serienstream", "serien.sx", "186.2.175.5")),
        ("htv", ("hanime",)),
        ("megakino", ("megakino",)),
        ("cineby", ("cineby",)),
        ("kinox", ("kinox",)),
        ("burningseries", ("bs.to", "burningseries")),
        ("filmpalast", ("filmpalast",)),
        ("mangafire", ("mangafire",)),
    ):
        if any(needle in host for needle in needles):
            return key
    return host.split(".")[0]


def clean_genres(genres):
    """Genres without the language tags aniworld mixes into them."""
    seen = []
    for genre in genres:
        text = str(genre or "").strip()
        if text and not _LANGUAGE_TAG_RE.match(text) and text not in seen:
            seen.append(text)
    return seen


def _attr(obj, name, default=""):
    """getattr that also survives a property raising (a page that failed to load)."""
    if obj is None:
        return default
    try:
        value = getattr(obj, name, default)
    except Exception:
        return default
    return default if value is None else value


def describe(episode, final_path):
    """(title folder, series patch, episode key, titles) for a finished episode.

    Works on any of the episode models: they share attribute names loosely,
    so everything is read defensively and missing pieces stay empty rather
    than failing the download that just succeeded.

    Returns None when the naming template puts files straight into the
    download root (no title folder), because a sidecar there would describe
    every series at once.
    """
    final_path = Path(final_path)
    base = _attr(episode, "_base_folder", None)
    root = _attr(episode, "selected_path", None)
    if not base:
        return None
    base = Path(base)
    try:
        if root and base.resolve() == Path(root).expanduser().resolve():
            return None
        final_path.resolve().relative_to(base.resolve())
    except (OSError, ValueError):
        return None

    series = _attr(episode, "series", None)
    url = str(_attr(episode, "url", ""))
    series_url = str(_attr(series, "url", ""))

    patch = {
        "site": _site_key(series_url or url),
        "series_url": series_url,
        "title": str(_attr(series, "title", "") or _attr(episode, "_naming_title", "")),
        "year": str(_attr(series, "release_year", "")),
        "imdb": str(_attr(series, "imdb", "")),
        "poster_url": str(
            _attr(series, "poster_url", "") or _attr(episode, "poster_url", "")
        ),
        "description": str(
            _attr(series, "description", "") or _attr(episode, "description", "")
        ),
        "genres": clean_genres(_attr(series, "genres", []) or []),
    }
    if not patch["title"]:
        patch["title"] = parse_folder_name(base.name)[0]

    match = EPISODE_RE.search(final_path.name)
    key = episode_key(match.group(1), match.group(2)) if match else None
    titles = {
        "title_de": str(_attr(episode, "title_de", "")).strip(),
        "title_en": str(_attr(episode, "title_en", "")).strip(),
    }
    return base, patch, key, titles


def record_download(episode, final_path):
    """Update the title folder's sidecar after a download finished.

    Called from the download finaliser, so it must never raise. A sidecar that
    was only scanned is upgraded to a downloaded one; one that already carries
    metadata keeps whatever the new download does not know better.
    """
    if not writes_enabled():
        return False
    try:
        described = describe(episode, final_path)
        if described is None:
            return False
        base, patch, key, titles = described
        data = read(base) or scan(base)
        for field, value in patch.items():
            if value or not data.get(field):
                data[field] = value
        data["origin"] = "download"
        data, _ = reconcile(base, data, video_files(base))
        if key:
            current = data["episodes"].setdefault(key, {"title_de": "", "title_en": ""})
            for field, value in titles.items():
                if value:
                    current[field] = value
        return write(base, data)
    except Exception as exc:
        logger.debug("Sidecar not updated for %s: %s", final_path, exc)
        return False


def forget_files(folder, relative_files):
    """Drop thumbnails and titles of files that were just deleted."""
    folder = Path(folder)
    for name in relative_files:
        try:
            thumbnail_path(folder, name).unlink(missing_ok=True)
        except OSError:
            pass
    data = read(folder)
    if data is None:
        return
    data, changed = reconcile(folder, data, video_files(folder))
    if changed:
        write(folder, data)


# ---------------------------------------------------------------------------
# Lookups the rest of the package uses
# ---------------------------------------------------------------------------
def episodes_on_disk(folder):
    """{(season, episode)} of one title folder, from the sidecar when it has one.

    The sidecar's keys are a cache of the last walk. Files deleted by hand
    since then are the only way it can be wrong, and the library reconciles
    it on the next visit; for the "already downloaded" badge that is the
    right trade against walking every title on every search.
    """
    data = load(folder)
    found = set()
    for key in data["episodes"]:
        match = _EPISODE_KEY_RE.match(key)
        if match:
            found.add((int(match.group(1)), int(match.group(2))))
    return found


def find_folders(bases, series_url):
    """Title folders whose sidecar names this series URL, across download roots.

    The exact match the name heuristic cannot give: a renamed folder, a title
    that changed upstream, two shows that differ only in punctuation.
    """
    wanted = normalize_url(series_url)
    if not wanted:
        return []
    found = []
    for base in bases:
        base = Path(base)
        if not base.is_dir():
            continue
        try:
            entries = list(base.iterdir())
        except OSError:
            continue
        for entry in entries:
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            data = read(entry)
            if data and normalize_url(data["series_url"]) == wanted:
                found.append(entry)
    return found


def thumbnail_path(folder, relative_file):
    """Where the episode's cover frame is cached: one .jpg per video file.

    Named after the video's relative path with separators flattened, so two
    seasons with the same filename cannot collide.
    """
    flat = str(relative_file).replace("\\", "/").strip("/").replace("/", "__")
    return thumbs_dir(folder) / f"{Path(flat).stem}.jpg"
