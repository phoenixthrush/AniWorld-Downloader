import os
import logging

IS_DEBUG_MODE = True
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/58.0.3029.110 Safari/537.3"
)

DEFAULT_ACTION = "Download"  # E.g. Watch, Download, Syncplay
DEFAULT_DOWNLOAD_PATH = os.path.join(os.path.expanduser('~'), 'Downloads')
DEFAULT_LANGUAGE = "German Sub"  # German Dub, English Sub, German Sub
DEFAULT_PROVIDER = "Vidoza"  # Vidoza, Streamtape, VOE, Doodstream
DEFAULT_PROVIDER_DOWNLOAD = DEFAULT_PROVIDER  # Vidoza, Streamtape, VOE, Doodstream
DEFAULT_ANISKIP = False
DEFAULT_KEEP_WATCHING = False
DEFAULT_ONLY_DIRECT_LINK = False
DEFAULT_ONLY_COMMAND = False
DEFAULT_PROXY = None

logging.basicConfig(
    level=logging.DEBUG if IS_DEBUG_MODE else logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# logging.getLogger('requests').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)