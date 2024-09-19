import glob
import platform
import os
import shutil
import sys
import shlex
import subprocess
import re
import logging
from typing import List, Optional

from bs4 import BeautifulSoup
import requests

from aniworld import globals

def check_dependencies(dependencies: list) -> None:
    logging.debug("Entering check_dependencies function.")
    resolved_dependencies = []

    for dep in dependencies:
        if dep == "syncplay":
            if platform.system() == "Windows":
                resolved_dependencies.append("SyncplayConsole")
            else:
                resolved_dependencies.append("syncplay")
        else:
            resolved_dependencies.append(dep)

    logging.debug(f"Checking for {resolved_dependencies} in path.")
    missing = [dep for dep in resolved_dependencies if shutil.which(dep) is None]

    if missing:
        download_links = {
            "mpv": "https://mpv.io/installation/",
            "syncplay": "https://syncplay.pl/download/",
            "SyncplayConsole": "https://syncplay.pl/download/",
            "yt-dlp": "https://github.com/yt-dlp/yt-dlp#installation"
        }
        missing_with_links = [
            f"{dep} (Download: {download_links.get(dep, 'No link available')})"
            for dep in missing
        ]
        logging.critical(f"Missing dependencies: {', '.join(missing_with_links)} in path. Please add them to PATH and reopen the terminal to apply the changes.")
        sys.exit(1)

def fetch_url_content(url: str, proxy: Optional[str] = None, check: bool = True) -> Optional[bytes]:
    logging.debug("Entering fetch_url_content function.")
    headers = {
        'User-Agent': (globals.DEFAULT_USER_AGENT)
    }

    proxies = {}
    if proxy:
        if proxy.startswith('socks'):
            proxies = {
                'http': proxy,
                'https': proxy
            }
        else:
            proxies = {
                'http': f'http://{proxy}',
                'https': f'https://{proxy}'
            }
    elif globals.DEFAULT_PROXY:
        if globals.DEFAULT_PROXY.startswith('socks'):
            proxies = {
                'http': globals.DEFAULT_PROXY,
                'https': globals.DEFAULT_PROXY
            }
        else:
            proxies = {
                'http': f'http://{globals.DEFAULT_PROXY}',
                'https': f'https://{globals.DEFAULT_PROXY}'
            }
    else:
        proxies = {
            "http": os.getenv("HTTP_PROXY"),
            "https": os.getenv("HTTPS_PROXY"),
        }

    try:
        response = requests.get(url, headers=headers, proxies=proxies, timeout=10)
        response.raise_for_status()

        if "Deine Anfrage wurde als Spam erkannt." in response.text:
            logging.critical("Your IP address is blacklisted. Please use a VPN, complete the captcha by opening the browser link, or try again later.")
            sys.exit(1)

        return response.content
    except requests.exceptions.RequestException as error:
        if check:
            logging.critical(f"Request to {url} failed: {error}")
            sys.exit(1)
        return None

def clear_screen() -> None:
    logging.debug("Entering clear_screen function.")
    if not globals.IS_DEBUG_MODE:
        if platform.system() == "Windows":
            os.system("cls")
        else:
            os.system("clear")

def clean_up_leftovers(directory: str) -> None:
    logging.debug("Entering clean_up_leftovers function.")
    patterns: List[str] = ['*.part', '*.ytdl', '*.part-Frag*']

    leftover_files: List[str] = []
    for pattern in patterns:
        leftover_files.extend(glob.glob(os.path.join(directory, pattern)))

    for file_path in leftover_files:
        if not os.path.exists(directory):
            logging.warning(f"Directory {directory} no longer exists.")
            return

        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logging.debug(f"Removed leftover file: {file_path}")
            except PermissionError:
                logging.warning(f"Permission denied when trying to remove file: {file_path}")
            except OSError as e:
                logging.warning(f"OS error occurred while removing file {file_path}: {e}")

    if os.path.exists(directory) and not os.listdir(directory):
        try:
            os.rmdir(directory)
            logging.debug(f"Removed empty directory: {directory}")
        except PermissionError:
            logging.warning(f"Permission denied when trying to remove directory: {directory}")
        except OSError as e:
            logging.warning(f"OS error occurred while removing directory {directory}: {e}")

def setup_aniskip() -> None:
    logging.debug("Entering setup_aniskip function.")
    script_directory = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    skip_source_path = os.path.join(script_directory, 'aniskip', 'skip.lua')
    autostart_source_path = os.path.join(script_directory, 'aniskip', 'autostart.lua')
    autoexit_source_path = os.path.join(script_directory, 'aniskip', 'autoexit.lua')

    if os.name == 'nt':
        mpv_scripts_directory = os.path.join(
            os.environ.get('APPDATA', ''), 'mpv', 'scripts'
        )
    else:
        mpv_scripts_directory = os.path.expanduser('~/.config/mpv/scripts')

    logging.debug(f"Creating directory {mpv_scripts_directory}")
    os.makedirs(mpv_scripts_directory, exist_ok=True)

    skip_destination_path = os.path.join(mpv_scripts_directory, 'skip.lua')
    if not os.path.exists(skip_destination_path):
        logging.debug(f"Copying skip.lua to {mpv_scripts_directory}")
        shutil.copy(skip_source_path, skip_destination_path)

    autostart_destination_path = os.path.join(mpv_scripts_directory, 'autostart.lua')
    if not os.path.exists(autostart_destination_path):
        logging.debug(f"Copying autostart.lua to {mpv_scripts_directory}")
        shutil.copy(autostart_source_path, autostart_destination_path)

    autoexit_destination_path = os.path.join(mpv_scripts_directory, 'autoexit.lua')
    if not os.path.exists(autoexit_destination_path):
        logging.debug(f"Copying autoexit.lua to {mpv_scripts_directory}")
        shutil.copy(autoexit_source_path, autoexit_destination_path)

def execute_command(command: List[str], only_command: bool) -> None:
    logging.debug("Entering execute_command function.")
    if only_command:
        print(' '.join(shlex.quote(arg) for arg in command))
    else:
        subprocess.run(command, check=True)

def raise_runtime_error(message: str) -> None:
    logging.debug("Entering raise_runtime_error function.")
    raise RuntimeError(message)

def get_season_episodes(season_url):
    logging.debug("Entering get_season_episodes function.")
    season_url_old = season_url
    season_url = season_url[:-2]
    season_suffix = f"/staffel-{season_url_old.split('/')[-1]}"

    logging.debug(f"Fetching Episode URLs from Season {season_suffix}")
    
    season_html = fetch_url_content(season_url)
    if season_html is None:
        return []
    season_soup = BeautifulSoup(season_html, 'html.parser')
    episodes = season_soup.find_all('meta', itemprop='episodeNumber')
    episode_numbers = [int(episode['content']) for episode in episodes]
    highest_episode = max(episode_numbers, default=None)

    episode_urls = [
        f"{season_url}{season_suffix}/episode-{num}"
        for num in range(1, highest_episode + 1)
    ]

    return episode_urls

def get_season_data(anime_slug: str):
    logging.debug("Entering get_season_data function.")
    BASE_URL_TEMPLATE = "https://aniworld.to/anime/stream/{anime}/"
    base_url = BASE_URL_TEMPLATE.format(anime=anime_slug)

    logging.debug(f"Fetching Base URL {base_url}")
    main_html = fetch_url_content(base_url)
    if main_html is None:
        logging.critical("Failed to retrieve main page.")
        sys.exit(1)

    soup = BeautifulSoup(main_html, 'html.parser')
    season_meta = soup.find('meta', itemprop='numberOfSeasons')
    number_of_seasons = int(season_meta['content']) if season_meta else 0

    if soup.find('a', title='Alle Filme'):
        number_of_seasons -= 1

    season_data = {}
    for i in range(1, number_of_seasons + 1):
        season_url = f"{base_url}{i}"
        season_data[i] = get_season_episodes(season_url)

    return season_data

def set_terminal_size(columns: int=None, lines: int=None):
    logging.debug("Entering set_terminal_size function.")
    logging.debug(f"Setting terminal size to {columns} columns and {lines} lines.")
    system_name = platform.system()

    if not columns or not lines:
        columns, lines = globals.DEFAULT_TERMINAL_SIZE

    if system_name == 'Windows':
        os.system(f"mode con: cols={columns} lines={lines}")
    elif system_name in 'Darwin':
        os.system(f"printf '\033[8;{lines};{columns}t'")
    elif system_name in 'Linux':
        logging.debug("Not resizing terminal on Linux")
    else:
        logging.error(f"Unsupported platform: {system_name}")
        raise NotImplementedError(f"Unsupported platform: {system_name}")

def ftoi(value: float) -> str:
    logging.debug("Entering ftoi function.")
    return str(int(value * 1000))

def get_version_from_pyproject():
    try:
        with open(os.path.join(os.path.dirname(__file__), '../../../pyproject.toml'), 'r') as f:
            pyproject_data = f.read()
            match = re.search(r'version\s*=\s*["\'](.*?)["\']', pyproject_data)
            if match:
                return f" v{match.group(1)}"
            else:
                return ""
    except Exception as e:
        logging.error(f"Error reading version from pyproject.toml: {e}")
        return ""
    
def get_language_code(language: str) -> str:
    logging.debug(f"Getting language code for: {language}")
    return {
        "German Dub": "1",
        "English Sub": "2",
        "German Sub": "3"
    }.get(language, "")

def get_language_string(lang_key: int) -> str:
    logging.debug("Entering get_language_string function.")
    lang_map = {
        1: "German Dub",
        2: "English Sub",
        3: "German Sub"
    }
    return lang_map.get(lang_key, "Unknown Language")