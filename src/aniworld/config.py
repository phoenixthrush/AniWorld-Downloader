import os
import re
from enum import Enum
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import fake_useragent
from niquests import RequestException, Session
from packaging.version import parse as parse_version

from .env import merge_env
from .logger import get_logger

VERSION = None

try:
    VERSION = version("aniworld")
except PackageNotFoundError:
    VERSION = None


def is_newest_version() -> bool:
    """Checks if the installed version is the newest available on PyPI."""
    if not VERSION:
        return False

    try:
        response = GLOBAL_SESSION.get("https://pypi.org/pypi/aniworld/json")
        response.raise_for_status()
        latest_version = response.json()["info"]["version"]
        return parse_version(VERSION) >= parse_version(latest_version)
    except RequestException:
        # Could not fetch PyPI info, assume not newest
        return False


# AniWorld configuration directory
ANIWORLD_CONFIG_DIR = Path.home() / ".aniworld"

# Load .env file whenever config is imported
merge_env(
    Path(__file__).resolve().parent / ".env.example",
    ANIWORLD_CONFIG_DIR / ".env",
)

logger = get_logger(__name__)

NAMING_TEMPLATE = os.getenv(
    "ANIWORLD_NAMING_TEMPLATE",
    "{title} ({year}) [imdbid-{imdbid}]/Season {season}/{title} S{season}E{episode}.mkv",
)

# Video codec configuration
VIDEO_CODEC = os.getenv("ANIWORLD_VIDEO_CODEC", "copy")

# Simple codec mapping using ffmpeg defaults
VIDEO_CODEC_MAP = {
    "copy": "copy",
    "h264": "libx264",
    "h265": "libx265",
    "av1": "libsvtav1",
}

ACTION_METHODS = {
    "Download": "download",
    "Watch": "watch",
    "Syncplay": "syncplay",
}


def get_video_codec():
    """Get and validate video codec from environment variable."""
    codec = VIDEO_CODEC
    if codec not in VIDEO_CODEC_MAP:
        logger.warning(
            f"Invalid video codec '{codec}', falling back to 'copy'. Valid options: {list(VIDEO_CODEC_MAP.keys())}"
        )
        return "copy"
    return VIDEO_CODEC_MAP[codec]


# NIQUESTS

try:
    DEFAULT_USER_AGENT = str(
        fake_useragent.UserAgent(os=["Windows", "Mac OS X"]).random
    )
except fake_useragent.errors.FakeUserAgentError:
    # TODO: fix - currently happens on nuitka builds
    DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"

LULUVDO_USER_AGENT = (
    "Mozilla/5.0 (Android 15; Mobile; rv:132.0) Gecko/132.0 Firefox/132.0"
)

GLOBAL_SESSION = Session(
    resolver=["doh+google://"],
    headers={
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-Dest": "document",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Mode": "navigate",
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://aniworld.to/search",
        "Priority": "u=0, i",
    },
)

logger.debug("Config initialized successfully")

# -----------------------------
# Provider Stuff
# -----------------------------
SUPPORTED_PROVIDERS = (
    "VOE",
    "Vidmoly",
    "Vidoza",
    # "Doodstream",
    "Filemoon",
    # "LoadX",
    # "Luluvdo",
    # "Streamtape",
)

PROVIDER_HEADERS_D = {
    "Vidmoly": {"Referer": "https://vidmoly.biz"},
    "Doodstream": {"Referer": "https://dood.li/"},
    "VOE": {"User-Agent": DEFAULT_USER_AGENT},
    "LoadX": {"Accept": "*/*"},
    "Filemoon": {"User-Agent": DEFAULT_USER_AGENT, "Referer": "https://filemoon.to"},
    "Luluvdo": {
        "User-Agent": LULUVDO_USER_AGENT,
        "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
        "Origin": "https://luluvdo.com",
        "Referer": "https://luluvdo.com/",
    },
}

PROVIDER_HEADERS_W = {
    "Vidmoly": {"Referer": "https://vidmoly.biz"},
    "Doodstream": {"Referer": "https://dood.li/"},
    "VOE": {"User-Agent": DEFAULT_USER_AGENT},
    "Luluvdo": {"User-Agent": LULUVDO_USER_AGENT},
    "Filemoon": {"User-Agent": DEFAULT_USER_AGENT, "Referer": "https://filemoon.to"},
}


# -----------------------------
# Language Stuff
# -----------------------------
class Audio(Enum):
    """
    Available audio language options:

        - JAPANESE: Japanese dubbed audio
        - GERMAN:   German dubbed audio
        - ENGLISH:  English dubbed audio

    Required source for each option:

        Japanese Dub -> Source: German Sub, English Sub
        German Dub   -> Source: German Dub
        English Dub  -> Source: English Dub
    """

    JAPANESE = "Japanese"
    GERMAN = "German"
    ENGLISH = "English"


class Subtitles(Enum):
    """
    Available subtitle language options:

        - NONE:    No subtitles
        - GERMAN:  German subtitles
        - ENGLISH: English subtitles

    Required source for each option:

        German Sub   -> Source: German Sub
        English Sub  -> Source: English Sub
    """

    NONE = "None"
    GERMAN = "German"
    ENGLISH = "English"


# Map site-specific language keys to semantic meaning
LANG_KEY_MAP = {
    "1": (Audio.GERMAN, Subtitles.NONE),  # German Dub
    "2": (Audio.JAPANESE, Subtitles.ENGLISH),  # English Sub
    "3": (Audio.JAPANESE, Subtitles.GERMAN),  # German Sub
}

LANG_LABELS = {
    "1": "German Dub",
    "2": "English Sub",
    "3": "German Sub",
}

LANG_CODE_MAP = {
    Audio.ENGLISH: "eng",
    Audio.GERMAN: "deu",
    Audio.JAPANESE: "jpn",
    Subtitles.ENGLISH: "eng",
    Subtitles.GERMAN: "deu",
    Subtitles.NONE: None,
}


INVERSE_LANG_KEY_MAP = {v: k for k, v in LANG_KEY_MAP.items()}
INVERSE_LANG_LABELS = {v: k for k, v in LANG_LABELS.items()}

# -----------------------------
# Patterns
# -----------------------------


ANIWORLD_SERIES_PATTERN = re.compile(
    r"^https?://(www\.)?aniworld\.to/anime/stream/[a-zA-Z0-9\-]+/?$", re.IGNORECASE
)

# series slug + (/staffel-N or /filme)
ANIWORLD_SEASON_PATTERN = re.compile(
    r"^https?://(www\.)?aniworld\.to/anime/stream/"
    r"[a-zA-Z0-9\-]+/"
    r"(staffel-\d+|filme)"
    r"/?$",
    re.IGNORECASE,
)

ANIWORLD_EPISODE_PATTERN = re.compile(
    r"^https?://(www\.)?aniworld\.to/anime/stream/"
    r"[a-zA-Z0-9\-]+/"  # series slug
    r"(staffel-\d+/episode-\d+|"  # season/episode
    r"filme/film-\d+)"  # movie/film
    r"/?$",
    re.IGNORECASE,
)

HANIME_TV_SERIES_PATTERN = re.compile(
    r"^https?://(?:www\.)?hanime\.tv/videos/hentai/[A-Za-z0-9\-]+/?$",
    re.IGNORECASE,
)

SERIENSTREAM_SERIES_PATTERN = re.compile(
    r"^https?://(www\.)?(serienstream|s)\.to/serie/[a-zA-Z0-9\-]+/?$", re.IGNORECASE
)

SERIENSTREAM_SEASON_PATTERN = re.compile(
    r"^https?://(www\.)?(serienstream|s)\.to/serie/"
    r"[a-zA-Z0-9\-]+/"
    r"staffel-\d+"
    r"/?$",
    re.IGNORECASE,
)

SERIENSTREAM_EPISODE_PATTERN = re.compile(
    r"^https?://(www\.)?(serienstream|s)\.to/serie/"
    r"[a-zA-Z0-9\-]+/"
    r"staffel-\d+/episode-\d+"
    r"/?$",
    re.IGNORECASE,
)

HIANIME_SERIES_PATTERN = re.compile(r"", re.IGNORECASE)

HIANIME_SEASON_PATTERN = re.compile(r"", re.IGNORECASE)

HIANIME_EPISODE_PATTERN = re.compile(r"", re.IGNORECASE)

# -----------------------------
# Directories
# -----------------------------

# TODO: add many other directories and use them throughout the app

# Determine mpv scripts directory
# On Linux/macOS: ~/.config/mpv/scripts
# On Windows: %APPDATA%\mpv\scripts
if os.name == "nt":
    MPV_CONFIG_DIR = Path(os.getenv("APPDATA")) / "mpv"
else:
    MPV_CONFIG_DIR = Path.home() / ".config" / "mpv"

MPV_SCRIPTS_DIR = MPV_CONFIG_DIR / "scripts"
