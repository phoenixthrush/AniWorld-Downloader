import glob
import json
import logging
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
from typing import List, Optional

import requests
import py7zr
from bs4 import BeautifulSoup

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

    # TODO check if in appdata and return 

    if missing:
        download_links = {
            "mpv": "https://mpv.io/installation/",
            "syncplay": "https://syncplay.pl/download/",
            "SyncplayConsole": "https://syncplay.pl/download/",
            "yt-dlp": "https://github.com/yt-dlp/yt-dlp#installation"
        }

        if platform.system() == "Windows":
            logging.info(f"Missing dependencies: {missing}. Attempting to download.")
            missing = [dep.replace("SyncplayConsole", "syncplay") for dep in missing]
            download_dependencies(missing)
            # Info no need to check if in path
            # Will fallback to appdata binaries if found in execute.py
        else:
            missing_with_links = [
                f"{dep} (Download: {download_links.get(dep, 'No link available')})"
                for dep in missing
            ]
            logging.critical(f"Missing dependencies: {', '.join(missing_with_links)} in path. Please install them manually.")
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
    logging.debug(f"Initial command: {command}")
    
    if platform.system() == "Windows":
        appdata_path = os.path.join(os.getenv('APPDATA'), 'aniworld')
        logging.debug(f"AppData path: {appdata_path}")
        
        if os.path.exists(appdata_path):
            command_name = command[0]
            potential_path = os.path.join(appdata_path, command_name)
            logging.debug(f"Potential path for {command_name}: {potential_path}")

            if command_name == "mpv":
                if os.path.exists(potential_path):
                    command[0] = os.path.join(potential_path, "mpv.exe")
                    logging.debug(f"Updated command for mpv: {command}")

            # TODO needs to be fixed
            # rename SyncplayConsole folder to syncplay
            elif command_name == "SyncplayConsole":
                if os.path.exists(potential_path):
                    command[0] = os.path.join(potential_path, "SyncplayConsole.exe")
                    logging.debug(f"Updated command for SyncplayConsole: {command}")
                for i, arg in enumerate(command):
                    if arg == "--player-path" and i + 1 < len(command):
                        mpv_path = os.path.join(appdata_path, "mpv", "mpv.exe")
                        command[i + 1] = mpv_path
                        logging.debug(f"Updated --player-path argument: {command}")

            elif command_name == "yt-dlp":
                if os.path.exists(potential_path):
                    command[0] = os.path.join(potential_path, "yt-dlp.exe")
                    logging.debug(f"Updated command for yt-dlp: {command}")

    if only_command:
        command_str = ' '.join(shlex.quote(arg) for arg in command)
        logging.debug(f"Only command mode: {command_str}")
        print(command_str)
    else:
        logging.debug(f"Executing command: {command}")
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

    if system_name in 'Darwin':
        os.system(f"printf '\033[8;{lines};{columns}t'")

    # TODO Windows and Linux support

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

def get_github_release(repo: str) -> dict:
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"

    try:
        response_content = fetch_url_content(api_url, check=False)
        if not response_content:
            logging.error(f"Failed to fetch latest release from {repo}")
            return {}

        release_data = json.loads(response_content)
        return {asset['name']: asset['browser_download_url'] for asset in release_data.get('assets', [])}
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON response from {repo}: {e}")
    except Exception as e:
        logging.error(f"Unexpected error fetching latest release from {repo}: {e}")
    return {}

def download_dependencies(dependencies: list):
    logging.debug("Entering download_dependencies function.")
    logging.debug(f"Dependencies to download: {dependencies}")

    if platform.system() != "Windows":
        logging.debug("Not on Windows, skipping dependency download.")
        return

    for dep in dependencies:
        if shutil.which(dep):
            logging.info(f"{dep} is already in PATH. Skipping download.")
            dependencies.remove(dep)
    
    if not dependencies:
        logging.info("All required dependencies are already in PATH. No downloads needed.")
        return

    appdata_path = os.path.join(os.getenv('APPDATA'), 'aniworld')
    logging.debug(f"Creating appdata path: {appdata_path}")
    os.makedirs(appdata_path, exist_ok=True)

    for dep in dependencies:
        dep_path = os.path.join(appdata_path, dep)
        if os.path.exists(dep_path):
            logging.info(f"{dep_path} already exists. Skipping download.")
            continue

        logging.debug(f"Creating directory for {dep} at {dep_path}")
        os.makedirs(dep_path, exist_ok=True)

        if dep == 'mpv':
            direct_links = get_github_release("shinchiro/mpv-winbuild-cmake")
            direct_link = next((link for name, link in direct_links.items() if re.match(r'mpv-x86_64-v3-\d{8}-git-[a-f0-9]{7}\.7z', name)), None)
            if not direct_link:
                logging.error("No download link found for MPV.")
                return
            logging.debug(direct_link)

            zip_path = os.path.join(appdata_path, 'mpv.7z')
            logging.debug(f"Downloading {dep} from {direct_link} to {zip_path}")
            url_content = fetch_url_content(direct_link)
            with open(zip_path, 'wb') as f:
                f.write(url_content)
            logging.debug(f"Unpacking {zip_path} to {dep_path}")
            with py7zr.SevenZipFile(zip_path, mode='r') as archive:
                archive.extractall(path=dep_path)
            os.remove(zip_path)
            logging.debug(f"Removed {zip_path} after unpacking")
        elif dep == 'syncplay':
            direct_links = get_github_release("Syncplay/syncplay")
            direct_link = next((link for name, link in direct_links.items() if re.match(r'Syncplay_\d+\.\d+\.\d+_Portable\.zip', name)), None)
            if not direct_link:
                logging.error("No download link found for Syncplay.")
                return
            logging.debug(direct_link)

            exe_path = os.path.join(dep_path, 'syncplay.zip')
            logging.debug(f"Downloading {dep} from {direct_link} to {exe_path}")
            url_content = fetch_url_content(direct_link)
            with open(exe_path, 'wb') as f:
                f.write(url_content)
            
            logging.debug(f"Unpacking {exe_path} to {dep_path}")
            shutil.unpack_archive(exe_path, dep_path)
            os.remove(exe_path)
            logging.debug(f"Removed {exe_path} after unpacking")
        elif dep == 'yt-dlp':
            url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
            exe_path = os.path.join(dep_path, 'yt-dlp.exe')
            logging.debug(f"Downloading {dep} from {url} to {exe_path}")
            url_content = fetch_url_content(url)
            with open(exe_path, 'wb') as f:
                f.write(url_content)

    logging.debug("Windows dependencies downloaded.")

def is_tail_running():
    try:
        result = subprocess.run(
            ["sh", "-c", "ps aux | grep 'tail -f.*/aniworld.log' | grep -v grep"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        return result.returncode == 0
    except Exception as e:
        logging.error(f"Error checking if tail is running: {e}")
        return False