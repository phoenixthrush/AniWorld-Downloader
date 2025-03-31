import logging
import os
import pathlib
import platform
import random
import shutil
import tempfile

from importlib.metadata import PackageNotFoundError, version


#########################################################################################
# Logging Configuration
#########################################################################################

log_file_path = os.path.join(tempfile.gettempdir(), 'aniworld.log')


class CriticalErrorHandler(logging.Handler):
    def emit(self, record):
        if record.levelno == logging.CRITICAL:
            raise SystemExit(record.getMessage())


logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)s:%(name)s:%(funcName)s: %(message)s",
    handlers=[
        logging.FileHandler(log_file_path, mode='w'),
        CriticalErrorHandler()
    ]
)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.WARNING)
console_handler.setFormatter(logging.Formatter(
    "%(levelname)s:%(name)s:%(funcName)s: %(message)s")
)
logging.getLogger().addHandler(console_handler)

logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
logging.getLogger().setLevel(logging.WARNING)


#########################################################################################
# Default Configuration Constants
#########################################################################################

try:
    VERSION = version('aniworld')
except PackageNotFoundError:
    VERSION = ""

IS_NEWEST_VERSION = True  # For now :)
PLATFORM_SYSTEM = platform.system()

SUPPORTED_PROVIDERS = [
    # "Luluvdo" not supported
    "VOE", "Doodstream", "Vidmoly", "Vidoza", "SpeedFiles", "Streamtape"
]

PROVIDER_HEADERS = {
    "Vidmoly": 'Referer: "https://vidmoly.to"',
    "Doodstream": 'Referer: "https://dood.li/"'
}

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
DEFAULT_PROVIDER_DOWNLOAD = "SpeedFiles"
DEFAULT_PROVIDER_WATCH = "SpeedFiles"
DEFAULT_REQUEST_TIMEOUT = 30
DEFAULT_TERMINAL_SIZE = (90, 30)

# https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file
INVALID_PATH_CHARS = ['<', '>', ':', '"', '/', '\\', '|', '?', '*', '&']


#########################################################################################
# User Agents
#########################################################################################

USER_AGENTS = [
    # Windows
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.2849.80"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 "
        "Firefox/132.0"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 OPR/114.0.0.0"
    ),

    # MacOS
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.7; rv:132.0) Gecko/20100101 "
        "Firefox/132.0"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_1) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/18.0 Safari/605.1.15"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_1) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 OPR/114.0.0.0"
    ),

    # Linux
    (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux i686; rv:132.0) Gecko/20100101 "
        "Firefox/132.0"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 OPR/114.0.0.0"
    ),

    # Android
    (
        "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.6723.102 Mobile Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Android 15; Mobile; rv:132.0) Gecko/132.0 "
        "Firefox/132.0"
    ),
    (
        "Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.6723.102 Mobile Safari/537.36 "
        "EdgA/130.0.2849.68"
    ),
    (
        "Mozilla/5.0 (Linux; Android 10; Pixel 3 XL) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.6723.102 Mobile Safari/537.36 "
        "EdgA/130.0.2849.68"
    ),

    # iOS
    (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_7 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) CriOS/131.0.6778.31 Mobile/15E148 Safari/604.1"
    ),
    (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_7_1 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/18.0 EdgiOS/130.2849.68 Mobile/15E148 "
        "Safari/605.1.15"
    ),
    (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) FxiOS/132.0 Mobile/15E148 Safari/605.1.15"
    ),
    (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_7_1 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
    )
]

RANDOM_USER_AGENT = random.choice(USER_AGENTS)


#########################################################################################
# Executable Path Resolution
#########################################################################################

DEFAULT_APPDATA_PATH = os.getenv("APPDATA") or os.path.expanduser("~/.aniworld")

if platform.system() == "Windows":
    mpv_path = shutil.which("mpv")
    if not mpv_path:
        mpv_path = os.path.join(os.getenv('APPDATA', ''), "aniworld", "mpv", "mpv.exe")
else:
    mpv_path = shutil.which("mpv")

MPV_PATH = mpv_path

if platform.system() == "Windows":
    syncplay_path = shutil.which("syncplay")
    if not syncplay_path:
        syncplay_path = os.path.join(os.getenv('APPDATA', ''), "aniworld", "syncplay", "SyncplayConsole.exe")
else:
    syncplay_path = shutil.which("syncplay")

SYNCPLAY_PATH = syncplay_path

YTDLP_PATH = shutil.which("yt-dlp")  # already in pip deps

#########################################################################################

if __name__ == '__main__':
    pass
