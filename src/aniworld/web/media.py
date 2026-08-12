"""Shared helpers for turning the downloader's models into JSON for the UI."""

import os
import re
from urllib.parse import quote, urlparse

from ..config import LANG_KEY_MAP, LANG_LABELS, SUPPORTED_PROVIDERS
from ..extractors import provider_functions
from ..logger import get_logger
from . import paths

logger = get_logger(__name__)


def _detect_working_providers():
    """Keep only providers whose extractor is actually implemented.

    Calling the extractor with an empty URL is enough: unimplemented ones raise
    NotImplementedError, working ones fail on the bogus input instead.
    """
    working = []
    for provider in SUPPORTED_PROVIDERS:
        function = provider_functions.get(f"get_direct_link_from_{provider.lower()}")
        if function is None:
            continue
        try:
            function("")
        except NotImplementedError:
            continue
        except Exception:
            working.append(provider)
    return tuple(working)


WORKING_PROVIDERS = _detect_working_providers()
_PROVIDER_BY_LOWER = {p.lower(): p for p in WORKING_PROVIDERS}


# ---------------------------------------------------------------------------
# Sites
# ---------------------------------------------------------------------------
# Site keys the front-end uses. Custom paths can be the default for any of them.
SITE_KEYS = (
    "aniworld",
    "sto",
    "megakino",
    "mangafire",
    "htv",
    "kinox",
    "burningseries",
    "filmpalast",
    "cineby",
)

SITE_LABELS = {
    "aniworld": "AniWorld",
    "sto": "SerienStream",
    "megakino": "MegaKino",
    "mangafire": "MangaFire",
    "htv": "Hanime",
    "kinox": "Kinox",
    "burningseries": "BurningSeries",
    "filmpalast": "FilmPalast",
    "cineby": "Cineby",
}


def normalize_default_sites(value):
    """Validate a default_sites value into a clean CSV of known site keys."""
    raw = value if isinstance(value, (list, tuple)) else str(value or "").split(",")
    seen = []
    for item in raw:
        key = str(item).strip().lower()
        if key in SITE_KEYS and key not in seen:
            seen.append(key)
    return ",".join(seen)


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------
def normalize_image(value):
    """Posters arrive as a string, a dict of sizes or a model object."""
    if not value:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("large", "medium", "small", "url", "href", "src"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
        for candidate in value.values():
            if isinstance(candidate, str) and candidate:
                return candidate
    return getattr(value, "url", None) or getattr(value, "href", None) or str(value)


def proxy_image(url):
    """Route posters through our own proxy so hotlink protection can't block them."""
    url = normalize_image(url)
    if not url:
        return ""
    return f"/api/proxy-image?url={quote(url, safe='')}"


def absolute_poster(poster, page_url):
    """serienstream.to returns relative poster paths, make them absolute."""
    poster = normalize_image(poster)
    if poster.startswith("/"):
        parsed = urlparse(page_url)
        return f"{parsed.scheme}://{parsed.netloc}{poster}"
    return poster


# ---------------------------------------------------------------------------
# Languages
# ---------------------------------------------------------------------------
BADGE_ORDER = ("German Dub", "German Sub", "English Dub", "English Sub")

# serienstream and friends only expose dubs, and use plain enum-keyed dicts
_PLAIN_LABELS = {
    ("German", "None"): "German Dub",
    ("English", "None"): "English Dub",
}


def _aniworld_label_map():
    labels = {}
    for key, (audio, subtitles) in LANG_KEY_MAP.items():
        label = LANG_LABELS.get(key)
        if label:
            labels[(audio.value, subtitles.value)] = label
    return labels


def provider_map(provider_data, drop_english_sub=False):
    """Map {language label: [provider names]} from a model's provider data."""
    if not provider_data:
        return {}

    result = {}
    if hasattr(provider_data, "_data"):
        # AniWorld exposes a ProviderData object keyed by (Audio, Subtitles)
        labels = _aniworld_label_map()
        for (audio, subtitles), providers in provider_data._data.items():
            label = labels.get((audio.value, subtitles.value))
            if not label or (drop_english_sub and label == "English Sub"):
                continue
            usable = [
                _PROVIDER_BY_LOWER[name.lower()]
                for name in providers
                if name.lower() in _PROVIDER_BY_LOWER
            ]
            if usable:
                result[label] = usable
    else:
        for (audio, subtitles), providers in provider_data.items():
            label = _PLAIN_LABELS.get((audio.value, subtitles.value))
            if not label or (drop_english_sub and label == "English Sub"):
                continue
            usable = [name for name in providers if name in WORKING_PROVIDERS]
            if usable:
                result[label] = usable
    return result


def language_labels(provider_data):
    """Ordered language badges for an episode row."""
    labels = list(provider_map(provider_data))
    order = {label: index for index, label in enumerate(BADGE_ORDER)}
    labels.sort(key=lambda label: (order.get(label, len(order)), label))
    return labels


# ---------------------------------------------------------------------------
# Downloaded episode detection
# ---------------------------------------------------------------------------
# Matched on the filename rather than the naming template so files keep being
# recognised after the template changes.
EPISODE_RE = re.compile(r"S(\d{2})E(\d{2,3})", re.IGNORECASE)


# clean_title strips these from a folder name, so a title still carrying them
# would never match its own folder. A test keeps the two lists in step.
FOLDER_UNSAFE = re.compile(r'[<>:"/\\|?*]')

# The same title reads back with straight or curly quotes depending on where
# it came from, "Ao-chan Can't Study!" against "Ao-chan Can’t Study!".
_SMART_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})

# What the naming template appends is bracketed: "(2019)", "[imdbid-tt0409591]"
_DECORATION_OPENERS = "([{"

# A custom template may separate instead, "Naruto - 2002". That is only an
# extra when a number follows it, or "Ao-chan Can't Study! - The Movie" would
# be claimed by "Ao-chan Can't Study!".
_DECORATION_SEPARATORS = "-–—_~."


def _normalise_title(value):
    text = str(value).translate(_SMART_QUOTES)
    text = FOLDER_UNSAFE.sub("", text)
    # collapse whitespace, dropping a character can leave a double space
    return " ".join(text.lower().split())


def _is_decoration(rest):
    """Whether what trails the title is the template's doing, not more title."""
    if not rest:
        return True
    if rest[0] in _DECORATION_OPENERS:
        return True
    if rest[0] in _DECORATION_SEPARATORS:
        tail = rest[1:].lstrip()
        return bool(tail) and (tail[0].isdigit() or tail[0] in _DECORATION_OPENERS)
    return False


def folder_matches_title(folder_name, title):
    """Whether a folder on disk holds this title.

    The folder carries whatever the naming template added, so "Naruto (2002)
    [imdbid-tt0409591]" belongs to "Naruto". Anything else trailing it is a
    different series, and punctuation counts: "K-On!!" is not "K-On!" any
    more than "Naruto Shippuden" is "Naruto".
    """
    name = _normalise_title(folder_name)
    title = _normalise_title(title)
    if not title or not name.startswith(title):
        return False
    return _is_decoration(name[len(title) :].lstrip())


def _title_folders(base, title):
    if not base.is_dir():
        return
    try:
        entries = list(base.iterdir())
    except OSError:
        return
    for entry in entries:
        if entry.is_dir() and folder_matches_title(entry.name, title):
            yield entry


def downloaded_episodes(series):
    """Set of (season, episode) numbers already on disk for a series."""
    title = (
        getattr(series, "title_cleaned", None) or getattr(series, "title", "") or ""
    ).lower()
    if not title:
        return set()

    found = set()
    for base in paths.scan_bases():
        for folder in _title_folders(base, title):
            for file in folder.rglob("*"):
                if not file.is_file():
                    continue
                match = EPISODE_RE.search(file.name)
                if match:
                    found.add((int(match.group(1)), int(match.group(2))))
    return found


def downloaded_folder_names():
    """Folder names present in any download root, used for the 'downloaded' badge."""
    names = set()
    for base in paths.scan_bases():
        if not base.is_dir():
            continue
        try:
            entries = list(base.iterdir())
        except OSError:
            continue
        names.update(entry.name for entry in entries if entry.is_dir())
    return sorted(names)


def mangafire_format():
    return os.environ.get("MANGAFIRE_FORMAT", "jpg")
