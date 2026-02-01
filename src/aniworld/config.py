import logging
import os
import pathlib
import platform
import shutil
import tempfile
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from packaging.version import Version, InvalidVersion
from urllib3.exceptions import InsecureRequestWarning
import urllib3
import requests
from fake_useragent import UserAgent


#########################################################################################
# Global Constants
#########################################################################################

ANIWORLD_TO = "https://aniworld.to"
S_TO = "http://186.2.175.5"

# Supported streaming sites with their URL patterns
SUPPORTED_SITES = {
    "aniworld.to": {"base_url": ANIWORLD_TO, "stream_path": "anime/stream"},
    "s.to": {"base_url": S_TO, "stream_path": "serie/stream"},
}

# Language code mappings for consistent handling
LANGUAGE_CODES_ANIWORLD = {
    "German Dub": 1,
    "English Sub": 2,
    "German Sub": 3,
}
LANGUAGE_NAMES_ANIWORLD = {v: k for k, v in LANGUAGE_CODES_ANIWORLD.items()}

LANGUAGE_CODES_STO = {
    "German Dub": 1,
    "English Dub": 2,
    "German Sub": 3,
}
LANGUAGE_NAMES_STO = {v: k for k, v in LANGUAGE_CODES_STO.items()}

# Site-specific language mappings
SITE_LANGUAGE_CODES = {
    "aniworld.to": LANGUAGE_CODES_ANIWORLD,
    "s.to": LANGUAGE_CODES_STO,
}

SITE_LANGUAGE_NAMES = {
    "aniworld.to": LANGUAGE_NAMES_ANIWORLD,
    "s.to": LANGUAGE_NAMES_STO,
}

#########################################################################################
# Logging Configuration
#########################################################################################

log_file_path = os.path.join(tempfile.gettempdir(), "aniworld.log")


class CriticalErrorHandler(logging.Handler):
    """A custom logging handler that raises SystemExit on CRITICAL log records."""

    def emit(self, record):
        if record.levelno == logging.CRITICAL:
            raise SystemExit(record.getMessage())


logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)s:%(name)s:%(funcName)s: %(message)s",
    handlers=[logging.FileHandler(log_file_path, mode="w"), CriticalErrorHandler()],
)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.WARNING)
console_handler.setFormatter(
    logging.Formatter("%(levelname)s:%(name)s:%(funcName)s: %(message)s")
)
logging.getLogger().addHandler(console_handler)
logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
logging.getLogger("charset_normalizer").setLevel(logging.WARNING)
logging.getLogger().setLevel(logging.WARNING)
logging.getLogger("bs4.dammit").setLevel(logging.ERROR)

# Global TLS Verification setting
REQUEST_VERIFY = os.getenv("ANIWORLD_INSECURE", "false").lower() != "true"

DEFAULT_REQUEST_TIMEOUT = 30

try:
    VERSION = version("aniworld")
except PackageNotFoundError:
    VERSION = ""


@lru_cache(maxsize=1)
def get_latest_github_version():
    """Get latest GitHub version with caching to avoid repeated API calls"""
    try:
        url = "https://api.github.com/repos/phoenixthrush/AniWorld-Downloader/releases/latest"
        response = requests.get(url, timeout=DEFAULT_REQUEST_TIMEOUT)
        return (
            response.json().get("tag_name", "") if response.status_code == 200 else ""
        )
    except requests.RequestException as err:
        logging.error("Error fetching latest release: %s", err)
        return ""


def is_newest_version():
    """
    Checks if the current version of the application is the newest available on GitHub.

    Returns:
        tuple:
            - latest (Version or None): The latest version found on GitHub, or None if unavailable.
            - is_newest (bool): True if the current version is up-to-date or newer, False otherwise.

    Notes:
        - If the current version is not set or cannot be determined, returns (None, False).
        - Handles invalid version formats and network errors gracefully, logging them as errors.
    """
    if not VERSION:
        return None, False

    try:
        current = Version(VERSION.lstrip("v").lstrip("."))
        latest_str = get_latest_github_version().lstrip("v").lstrip(".")
        if not latest_str:
            return None, False
        latest = Version(latest_str)
        return latest, current >= latest
    except InvalidVersion as err:
        logging.error("Invalid version format: %s", err)
    except requests.RequestException as err:
        logging.error("Network error while fetching latest version: %s", err)

    return None, False


try:
    LATEST_VERSION, IS_NEWEST_VERSION = is_newest_version()
except (TypeError, ValueError):  # GitHub API Rate Limit (60/h) #52 or other errors
    LATEST_VERSION = None
    IS_NEWEST_VERSION = True

PLATFORM_SYSTEM = platform.system()

# Cache platform check for efficiency
_IS_WINDOWS = PLATFORM_SYSTEM == "Windows"

SUPPORTED_PROVIDERS = (
    "LoadX",
    "VOE",
    "Vidmoly",
    "Filemoon",
    "Luluvdo",
    "Doodstream",
    "Vidoza",
    "SpeedFiles",
    "Streamtape",
)

#########################################################################################


# User Agents - Lazy initialization to avoid UserAgent() call on import
@lru_cache(maxsize=1)
def get_random_user_agent():
    """Get random user agent with caching to avoid repeated UserAgent() calls"""
    ua = UserAgent(os=["Windows", "Mac OS X"])
    return ua.random


# Backward compatibility - keep RANDOM_USER_AGENT as a constant
RANDOM_USER_AGENT = get_random_user_agent()

LULUVDO_USER_AGENT = (
    "Mozilla/5.0 (Android 15; Mobile; rv:132.0) Gecko/132.0 Firefox/132.0"
)

# Use lazy getter for user agents in headers


def _get_provider_headers_d():
    return {
        "Vidmoly": ['Referer: "https://vidmoly.net"'],
        "Doodstream": ['Referer: "https://dood.li/"'],
        "VOE": [f"User-Agent: {RANDOM_USER_AGENT}"],
        "LoadX": ["Accept: */*"],
        "Filemoon": [
            f"User-Agent: {RANDOM_USER_AGENT}",
            'Referer: "https://filemoon.to"',
        ],
        "Luluvdo": [
            f"User-Agent: {LULUVDO_USER_AGENT}",
            "Accept-Language: de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
            'Origin: "https://luluvdo.com"',
            'Referer: "https://luluvdo.com/"',
        ],
    }


def _get_provider_headers_w():
    return {
        "Vidmoly": ['Referer: "https://vidmoly.net"'],
        "Doodstream": ['Referer: "https://dood.li/"'],
        "VOE": [f"User-Agent: {RANDOM_USER_AGENT}"],
        "Luluvdo": [f"User-Agent: {LULUVDO_USER_AGENT}"],
        "Filemoon": [
            f"User-Agent: {RANDOM_USER_AGENT}",
            'Referer: "https://filemoon.to"',
        ],
    }


# Properties for backward compatibility


def get_provider_headers_d():
    """Return provider headers used when downloading"""
    return _get_provider_headers_d()


def get_provider_headers_w():
    """Return provider headers used when streaming"""
    return _get_provider_headers_w()


# For backward compatibility, keep these as module-level variables
# but they will be lazily evaluated when accessed
PROVIDER_HEADERS_D = get_provider_headers_d()
PROVIDER_HEADERS_W = get_provider_headers_w()


USES_DEFAULT_PROVIDER = False

# E.g. Watch, Download, Syncplay
DEFAULT_ACTION = "Download"
DEFAULT_ANISKIP = False
DEFAULT_DOWNLOAD_PATH = pathlib.Path.home() / "Downloads"
DEFAULT_KEEP_WATCHING = False
# German Dub, English Sub, German Sub
DEFAULT_LANGUAGE = "German Sub"
DEFAULT_ONLY_COMMAND = False
DEFAULT_ONLY_DIRECT_LINK = False
# SUPPORTED_PROVIDERS above
DEFAULT_PROVIDER_DOWNLOAD = "VOE"
DEFAULT_PROVIDER_WATCH = "Filemoon"
DEFAULT_TERMINAL_SIZE = (90, 30)

# https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file
INVALID_PATH_CHARS = ("<", ">", ":", '"', "/", "\\", "|", "?", "*", "&")

#########################################################################################
# Executable Path Resolution
#########################################################################################

DEFAULT_APPDATA_PATH = os.path.join(
    os.getenv("APPDATA") or os.path.expanduser("~"), "aniworld"
)

# Use cached platform check
MPV_DIRECTORY = (
    os.path.join(os.environ.get("APPDATA", ""), "mpv")
    if os.name == "nt"
    else os.path.expanduser("~/.config/mpv")
)

MPV_SCRIPTS_DIRECTORY = os.path.join(MPV_DIRECTORY, "scripts")


@lru_cache(maxsize=1)
def _get_mpv_path():
    """Get MPV path with caching"""
    mpv_path = shutil.which("mpv")
    if _IS_WINDOWS and not mpv_path:
        mpv_path = os.path.join(os.getenv("APPDATA", ""), "aniworld", "mpv", "mpv.exe")
    return mpv_path


@lru_cache(maxsize=1)
def _get_syncplay_path():
    """Get Syncplay path with caching"""
    syncplay_path = shutil.which("syncplay")
    if _IS_WINDOWS:
        if syncplay_path:
            syncplay_path = syncplay_path.replace("syncplay.EXE", "SyncplayConsole.exe")
        else:
            syncplay_path = os.path.join(
                os.getenv("APPDATA", ""), "aniworld", "syncplay", "SyncplayConsole.exe"
            )
    return syncplay_path


def get_mpv_path():
    """Get MPV path with lazy initialization"""
    return _get_mpv_path()


def get_syncplay_path():
    """Get Syncplay path with lazy initialization"""
    return _get_syncplay_path()


# Backward compatibility - Initialize with function calls
MPV_PATH = get_mpv_path()
SYNCPLAY_PATH = get_syncplay_path()

YTDLP_PATH = shutil.which("yt-dlp")  # already in pip deps

#########################################################################################

if __name__ == "__main__":
    pass
