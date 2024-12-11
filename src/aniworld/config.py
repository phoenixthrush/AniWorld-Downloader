import random
import pathlib
import shutil
import platform
import os

DEFAULT_ACTION = "Download"      # E.g. Watch, Download, Syncplay
DEFAULT_DOWNLOAD_PATH = pathlib.Path.home() / "Downloads"
DEFAULT_LANGUAGE = "German Sub"  # German Dub, English Sub, German Sub
DEFAULT_PROVIDER_DOWNLOAD = "VOE"         # Vidoza, Streamtape, VOE, Doodstream
DEFAULT_PROVIDER_WATCH = "Doodstream"
DEFAULT_ANISKIP = False
DEFAULT_KEEP_WATCHING = False
DEFAULT_ONLY_DIRECT_LINK = False
DEFAULT_ONLY_COMMAND = False
DEFAULT_PROXY = None
DEFAULT_USE_PLAYWRIGHT = False
DEFAULT_TERMINAL_SIZE = (90, 30)
DEFAULT_REQUEST_TIMEOUT = 30

# pylint: disable=line-too-long
USER_AGENTS = [
    # Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.2849.80",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 OPR/114.0.0.0",

    # MacOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.7; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 OPR/114.0.0.0",

    # Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux i686; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 OPR/114.0.0.0",

    # Android
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.6723.102 Mobile Safari/537.36",
    "Mozilla/5.0 (Android 15; Mobile; rv:132.0) Gecko/132.0 Firefox/132.0",
    "Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.6723.102 Mobile Safari/537.36 EdgA/130.0.2849.68",
    "Mozilla/5.0 (Linux; Android 10; Pixel 3 XL) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.6723.102 Mobile Safari/537.36 EdgA/130.0.2849.68",

    # iOS
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/131.0.6778.31 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 EdgiOS/130.2849.68 Mobile/15E148 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) FxiOS/132.0 Mobile/15E148 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
]

RANDOM_USER_AGENT = random.choice(USER_AGENTS)
DEFAULT_APPDATA_PATH = os.path.join(os.getenv("APPDATA") or os.path.expanduser("~"), ".aniworld")


def find_program(program_name: str, fallback_path: str) -> str:
    program_path = shutil.which(program_name)

    if program_path:
        return program_path

    if platform.system() == "Windows" and program_name.lower() == "syncplayconsole":
        fallback_program_path = os.path.join(fallback_path, "syncplay")
    else:
        fallback_program_path = os.path.join(fallback_path, program_name.lower())

    # if os.path.isfile(fallback_program_path):
    return fallback_program_path


MPV_PATH = find_program("mpv", DEFAULT_APPDATA_PATH)

SYNCPLAY_PATH = find_program("syncplay", DEFAULT_APPDATA_PATH)
if platform.system() == "Windows" and not SYNCPLAY_PATH:
    SYNCPLAY_PATH = find_program("SyncplayConsole", DEFAULT_APPDATA_PATH)

YTDLP_PATH = find_program("yt-dlp", DEFAULT_APPDATA_PATH)

if __name__ == '__main__':
    pass
