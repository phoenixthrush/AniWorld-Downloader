import os
import logging
import colorlog
import tempfile

IS_DEBUG_MODE = False
LOG_FILE_PATH = os.path.join(tempfile.gettempdir(), 'aniworld.log')

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/58.0.3029.110 Safari/537.3"
)

DEFAULT_ACTION = "Download"  # E.g. Watch, Download, Syncplay
DEFAULT_DOWNLOAD_PATH = os.path.join(os.path.expanduser('~'), 'Downloads')
DEFAULT_LANGUAGE = "German Sub"  # German Dub, English Sub, German Sub
DEFAULT_PROVIDER = "Vidoza"  # Vidoza, Streamtape, VOE, Doodstream
DEFAULT_PROVIDER_DOWNLOAD = "VOE"  # Vidoza, Streamtape, VOE, Doodstream
DEFAULT_ANISKIP = False
DEFAULT_KEEP_WATCHING = False
DEFAULT_ONLY_DIRECT_LINK = False
DEFAULT_ONLY_COMMAND = False
DEFAULT_PROXY = None

log_colors = {
    'DEBUG': 'bold_blue',
    'INFO': 'bold_green',
    'WARNING': 'bold_yellow',
    'ERROR': 'bold_red',
    'CRITICAL': 'bold_purple'
}

formatter = colorlog.ColoredFormatter(
    '%(log_color)s%(asctime)s - %(levelname)s - %(message)s',
    log_colors=log_colors
)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)

file_handler = logging.FileHandler(LOG_FILE_PATH)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

logging.basicConfig(
    level=logging.DEBUG if IS_DEBUG_MODE else logging.INFO,
    handlers=[stream_handler, file_handler]
)

# logging.getLogger('requests').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)