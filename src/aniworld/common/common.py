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
import random
import zipfile
from typing import List, Optional

import requests
import py7zr
from bs4 import BeautifulSoup

import aniworld.globals as aniworld_globals


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

    logging.debug("Checking for %s in path.", resolved_dependencies)
    missing = [dep for dep in resolved_dependencies if shutil.which(dep) is None]

    # TODO: Check if in appdata and return

    if missing:
        download_links = {
            "mpv": "https://mpv.io/installation/",
            "syncplay": "https://syncplay.pl/download/",
            "SyncplayConsole": "https://syncplay.pl/download/",
            "yt-dlp": "https://github.com/yt-dlp/yt-dlp#installation"
        }

        if platform.system() == "Windows":
            logging.info("Missing dependencies: %s. Attempting to download.", missing)
            missing = [dep.replace("SyncplayConsole", "syncplay") for dep in missing]
            download_dependencies(missing)
            # Info no need to check if in path
            # Will fallback to appdata binaries if found in execute.py
        else:
            missing_with_links = [
                f"{dep} (Download: {download_links.get(dep, 'No link available')})"
                for dep in missing
            ]
            logging.critical(
                "Missing dependencies: %s in path. Please install them manually.",
                ', '.join(missing_with_links)
            )
            sys.exit(1)


def fetch_url_content(url: str, proxy: Optional[str] = None, check: bool = True) -> Optional[bytes]:
    logging.debug("Entering fetch_url_content function.")
    headers = {
        'User-Agent': aniworld_globals.DEFAULT_USER_AGENT
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
    elif aniworld_globals.DEFAULT_PROXY:
        if aniworld_globals.DEFAULT_PROXY.startswith('socks'):
            proxies = {
                'http': aniworld_globals.DEFAULT_PROXY,
                'https': aniworld_globals.DEFAULT_PROXY
            }
        else:
            proxies = {
                'http': f'http://{aniworld_globals.DEFAULT_PROXY}',
                'https': f'https://{aniworld_globals.DEFAULT_PROXY}'
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
            logging.critical(
                "Your IP address is blacklisted. Please use a VPN, complete the captcha "
                "by opening the browser link, or try again later."
            )
            sys.exit(1)

        return response.content
    except requests.exceptions.RequestException as error:
        if check:
            logging.critical("Request to %s failed: %s", url, error)
            sys.exit(1)
        return None


def clear_screen() -> None:
    logging.debug("Entering clear_screen function.")
    if not aniworld_globals.IS_DEBUG_MODE:
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
            logging.warning("Directory %s no longer exists.", directory)
            return

        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logging.debug("Removed leftover file: %s", file_path)
            except PermissionError:
                logging.warning("Permission denied when trying to remove file: %s", file_path)
            except OSError as e:
                logging.warning("OS error occurred while removing file %s: %s", file_path, e)

    if os.path.exists(directory) and not os.listdir(directory):
        try:
            os.rmdir(directory)
            logging.debug("Removed empty directory: %s", directory)
        except PermissionError:
            logging.warning("Permission denied when trying to remove directory: %s", directory)
        except OSError as e:
            logging.warning("OS error occurred while removing directory %s: %s", directory, e)


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

    logging.debug("Creating directory %s", mpv_scripts_directory)
    os.makedirs(mpv_scripts_directory, exist_ok=True)

    skip_destination_path = os.path.join(mpv_scripts_directory, 'skip.lua')
    if not os.path.exists(skip_destination_path):
        logging.debug("Copying skip.lua to %s", mpv_scripts_directory)
        shutil.copy(skip_source_path, skip_destination_path)

    autostart_destination_path = os.path.join(mpv_scripts_directory, 'autostart.lua')
    if not os.path.exists(autostart_destination_path):
        logging.debug("Copying autostart.lua to %s", mpv_scripts_directory)
        shutil.copy(autostart_source_path, autostart_destination_path)

    autoexit_destination_path = os.path.join(mpv_scripts_directory, 'autoexit.lua')
    if not os.path.exists(autoexit_destination_path):
        logging.debug("Copying autoexit.lua to %s", mpv_scripts_directory)
        shutil.copy(autoexit_source_path, autoexit_destination_path)


def execute_command(command: List[str], only_command: bool) -> None:
    logging.debug("Entering execute_command function.")
    logging.debug("Initial command: %s", command)

    if platform.system() == "Windows":
        appdata_path = os.path.join(os.getenv('APPDATA'), 'aniworld')
        logging.debug("AppData path: %s", appdata_path)

        if os.path.exists(appdata_path):
            command_name = command[0]
            potential_path = os.path.join(appdata_path, command_name)
            logging.debug("Potential path for %s: %s", command_name, potential_path)

            if command_name == "mpv":
                if os.path.exists(potential_path):
                    command[0] = os.path.join(potential_path, "mpv.exe")
                    logging.debug("Updated command for mpv: %s", command)

            elif command_name == "SyncplayConsole":
                if os.path.exists(potential_path):
                    command[0] = os.path.join(potential_path, "SyncplayConsole.exe")
                    logging.debug("Updated command for SyncplayConsole: %s", command)
                else:
                    command[0] = os.path.join(appdata_path, "syncplay", "SyncplayConsole.exe")
                    logging.debug("Updated command for SyncplayConsole: %s", command)
                for i, arg in enumerate(command):
                    if arg == "--player-path" and i + 1 < len(command):
                        mpv_path = os.path.join(appdata_path, "mpv", "mpv.exe")
                        command[i + 1] = mpv_path
                        logging.debug("Updated --player-path argument: %s", command)

            elif command_name == "yt-dlp":
                if os.path.exists(potential_path):
                    command[0] = os.path.join(potential_path, "yt-dlp.exe")
                    logging.debug("Updated command for yt-dlp: %s", command)

    if only_command:
        command_str = ' '.join(shlex.quote(arg) for arg in command)
        logging.debug("Only command mode: %s", command_str)
        print(command_str)
    else:
        logging.debug("Executing command: %s", command)

        # TODO Somehow I can't supress the warnings or it crashes on MacOS
        subprocess.run(command, check=True)


def raise_runtime_error(message: str) -> None:
    logging.debug("Entering raise_runtime_error function.")
    raise RuntimeError(message)


def get_season_episode_count(slug: str, season: str) -> int:
    series_url = f"https://aniworld.to/anime/stream/{slug}/staffel-{season}"
    season_html = fetch_url_content(series_url)
    if season_html is None:
        return 0
    season_soup = BeautifulSoup(season_html, 'html.parser')

    episode_links = season_soup.find_all(
        'a',
        href=True,
        title=lambda x: x and x.startswith("Staffel")
    )

    episode_numbers = []
    for link in episode_links:
        match = re.search(r'\d+', link.get_text())
        if match:
            episode_numbers.append(int(match.group()))

    return max(episode_numbers) if episode_numbers else 0


def get_season_episodes(season_url):
    episode_urls = []

    logging.debug("Season URL: %s", season_url)

    parts = season_url.split('/')

    slug = parts[-1]
    season = slug.split('-')[-1]

    slug = parts[-2]

    logging.debug("Slug: %s", slug)
    logging.debug("Season: %s", season)

    for i in range(1, get_season_episode_count(slug, season) + 1):
        episode_urls.append(f"{season_url}/episode-{i}")

    logging.debug("Episode URLs: %s", episode_urls)
    return episode_urls


def get_movies_episode_count(slug: str) -> int:
    movie_url = f"https://aniworld.to/anime/stream/{slug}/filme/film-1"
    season_html = fetch_url_content(movie_url)
    if season_html is None:
        return 0
    season_soup = BeautifulSoup(season_html, 'html.parser')

    episode_links = season_soup.find_all('a', href=re.compile(r'/filme/film-\d+'))
    episode_numbers = [int(re.search(r'\d+', link['href']).group()) for link in episode_links]
    return max(episode_numbers, default=0)


def get_season_data(anime_slug: str):
    logging.debug("Entering get_season_data function.")
    base_url_template = "https://aniworld.to/anime/stream/{anime}/"
    base_url = base_url_template.format(anime=anime_slug)

    logging.debug("Fetching Base URL %s", base_url)
    main_html = fetch_url_content(base_url)
    if main_html is None:
        logging.critical("Failed to retrieve main page.")
        sys.exit(1)

    soup = BeautifulSoup(main_html, 'html.parser')
    season_meta = soup.find('meta', itemprop='numberOfSeasons')
    number_of_seasons = int(season_meta['content']) if season_meta else 0

    movies = False

    if soup.find('a', title='Alle Filme'):
        number_of_seasons -= 1
        movies = True

    season_data = []
    for i in range(1, number_of_seasons + 1):
        season_url = f"{base_url}staffel-{i}"
        season_data.extend(get_season_episodes(season_url))

    if movies:
        movie_data = []
        number_of_movies = get_movies_episode_count(anime_slug)
        for i in range(1, number_of_movies + 1):
            movie_data.append(f"https://aniworld.to/anime/stream/{anime_slug}/filme/film-{i}")

        season_data.extend(movie_data)

    return season_data


def set_terminal_size(columns: int = None, lines: int = None):
    logging.debug("Entering set_terminal_size function.")
    logging.debug("Setting terminal size to %s columns and %s lines.", columns, lines)
    system_name = platform.system()

    if not columns or not lines:
        columns, lines = aniworld_globals.DEFAULT_TERMINAL_SIZE

    if system_name == 'Darwin':
        os.system(f"printf '\033[8;{lines};{columns}t'")

    # TODO: Windows and Linux support


def get_season_and_episode_numbers(episode_url: str) -> tuple:
    logging.debug("Extracting season and episode numbers from URL: %s", episode_url)
    if "staffel" in episode_url and "episode" in episode_url:
        matches = re.findall(r'\d+', episode_url)
        season_episode = int(matches[-2]), int(matches[-1])
    elif "filme" in episode_url:
        movie_number = re.findall(r'\d+', episode_url)
        season_episode = 0, int(movie_number[0]) if movie_number else 1
    else:
        logging.error("URL format not recognized: %s", episode_url)
        raise ValueError("URL format not recognized")
    logging.debug("Extracted season and episode numbers: %s", season_episode)
    return season_episode


def ftoi(value: float) -> str:
    logging.debug("Entering ftoi function.")
    return str(int(value * 1000))


def get_version_from_pyproject():
    try:
        pyproject_path = os.path.join(os.path.dirname(__file__), '../../../pyproject.toml')
        with open(pyproject_path, 'r', encoding='utf-8') as f:
            pyproject_data = f.read()
            match = re.search(r'version\s*=\s*["\'](.*?)["\']', pyproject_data)
            if match:
                return f" v{match.group(1)}"
            return ""
    except (OSError, IOError, re.error) as e:
        logging.error("Error reading version from pyproject.toml: %s", e)
        return ""


def get_language_code(language: str) -> str:
    logging.debug("Getting language code for: %s", language)
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
            logging.error("Failed to fetch latest release from %s", repo)
            return {}

        release_data = json.loads(response_content)
        return {
            asset['name']: asset['browser_download_url']
            for asset in release_data.get('assets', [])
        }
    except json.JSONDecodeError as e:
        logging.error("Error decoding JSON response from %s: %s", repo, e)
    except requests.exceptions.RequestException as e:
        logging.error("Unexpected error fetching latest release from %s: %s", repo, e)
    return {}


def download_dependencies(dependencies: list):
    logging.debug("Entering download_dependencies function.")
    logging.debug("Dependencies to download: %s", dependencies)

    if platform.system() != "Windows":
        logging.debug("Not on Windows, skipping dependency download.")
        return

    dependencies = [dep for dep in dependencies if not shutil.which(dep)]
    if not dependencies:
        logging.info("All required dependencies are already in PATH. No downloads needed.")
        return

    appdata_path = os.path.join(os.getenv('APPDATA'), 'aniworld')
    logging.debug("Creating appdata path: %s", appdata_path)
    os.makedirs(appdata_path, exist_ok=True)

    for dep in dependencies:
        dep_path = os.path.join(appdata_path, dep)
        if os.path.exists(dep_path):
            logging.info("%s already exists. Skipping download.", dep_path)
            continue

        logging.debug("Creating directory for %s at %s", dep, dep_path)
        os.makedirs(dep_path, exist_ok=True)
        download_and_extract_dependency(dep, dep_path, appdata_path)

    logging.debug("Windows dependencies downloaded.")


def download_and_extract_dependency(dep: str, dep_path: str, appdata_path: str):
    if dep == 'mpv':
        logging.info("Downloading mpv...")
        download_mpv(dep_path, appdata_path)
    elif dep == 'syncplay':
        logging.info("Downloading Syncplay...")
        download_syncplay(dep_path)
    elif dep == 'yt-dlp':
        logging.info("Downloading yt-dlp...")
        download_yt_dlp(dep_path)


def download_mpv(dep_path: str, appdata_path: str):
    direct_links = get_github_release("shinchiro/mpv-winbuild-cmake")

    avx2_supported = check_avx2_support()
    pattern = r'mpv-x86_64-\d{8}-git-[a-f0-9]{7}\.7z'
    if avx2_supported:
        pattern = r'mpv-x86_64-v3-\d{8}-git-[a-f0-9]{7}\.7z'

    direct_link = next(
        (link for name, link in direct_links.items()
         if re.match(pattern, name)),
        None
    )

    if not direct_link:
        logging.error("No download link found for MPV.")
        return
    logging.debug(direct_link)

    zip_path = os.path.join(appdata_path, 'mpv.7z')
    logging.debug("Downloading MPV from %s to %s", direct_link, zip_path)
    url_content = fetch_url_content(direct_link)
    with open(zip_path, 'wb') as f:
        f.write(url_content)
    logging.debug("Unpacking %s to %s", zip_path, dep_path)
    with py7zr.SevenZipFile(zip_path, mode='r') as archive:
        archive.extractall(path=dep_path)
    os.remove(zip_path)
    logging.debug("Removed %s after unpacking", zip_path)


def download_syncplay(dep_path: str):
    direct_links = get_github_release("Syncplay/syncplay")
    direct_link = next(
        (link for name, link in direct_links.items()
         if re.match(r'Syncplay_\d+\.\d+\.\d+_Portable\.zip', name)),
        None
    )
    if not direct_link:
        logging.error("No download link found for Syncplay.")
        return
    logging.debug(direct_link)

    exe_path = os.path.join(dep_path, 'syncplay.zip')
    logging.debug("Downloading Syncplay from %s to %s", direct_link, exe_path)
    url_content = fetch_url_content(direct_link)
    with open(exe_path, 'wb') as f:
        f.write(url_content)

    logging.debug("Unpacking %s to %s", exe_path, dep_path)
    shutil.unpack_archive(exe_path, dep_path)
    os.remove(exe_path)
    logging.debug("Removed %s after unpacking", exe_path)


def download_yt_dlp(dep_path: str):
    url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
    exe_path = os.path.join(dep_path, 'yt-dlp.exe')
    logging.debug("Downloading yt-dlp from %s to %s", url, exe_path)
    url_content = fetch_url_content(url)
    with open(exe_path, 'wb') as f:
        f.write(url_content)


def is_tail_running():
    try:
        result = subprocess.run(
            ["sh", "-c", "ps aux | grep 'tail -f.*/aniworld.log' | grep -v grep"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        logging.error("Error checking if tail is running: %s", e)
        return False
    except subprocess.SubprocessError as e:
        logging.error("Subprocess error checking if tail is running: %s", e)
        return False


def check_avx2_support() -> bool:
    logging.debug("Entering check_avx2_support function.")
    if platform.system() != "Windows":
        logging.info("AVX2 check is only supported on Windows.")
        return False

    try:
        cpu_info = subprocess.run(
            ['wmic', 'cpu', 'get',
             'Caption, Architecture, DataWidth, Manufacturer, ProcessorType, Status'],
            capture_output=True, text=True, check=True
        )
        logging.debug("CPU Info: %s", cpu_info.stdout)
        if 'avx2' in cpu_info.stdout.lower():
            logging.info("AVX2 is supported.")
            return True
        logging.info("AVX2 is not supported.")
        return False
    except subprocess.CalledProcessError as e:
        logging.error("Error checking AVX2 support: %s", e)
        return False
    except subprocess.SubprocessError as e:
        logging.error("Subprocess error checking AVX2 support: %s", e)
        return False


def display_ascii_art() -> str:
    lucky_star = R"""
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠳⢬⣳⣄⣠⠤⠤⠶⠶⠒⠋⠀⠀⠀⠀⠹⡀⠀⠀⠀⠀⠈⠉⠛⠲⢦⣄⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣠⠤⠖⠋⠉⠉⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠱⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⢳⠦⣄⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⣠⠖⠋⠀⠀⠀⣠⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢱⠀⠀⠀⠀⠀⠀⠀⠀⢀⣀⠀⢃⠈⠙⠲⣄⡀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⢠⠞⠁⠀⠀⠀⢀⢾⠃⠀⠀⠀⠀⠀⠀⠀⠀⢢⠀⠀⠀⠀⠀⠀⠀⢣⠀⠀⠀⠀⠀⠀⠀⠀⠀⣹⠮⣄⠀⠀⠀⠙⢦⡀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⣰⠋⠀⠀⢀⡤⡴⠃⠈⠦⣀⠀⠀⠀⠀⠀⠀⢀⣷⢸⠀⠀⠀⠀⢀⣀⠘⡄⠤⠤⢤⠔⠒⠂⠉⠁⠀⠀⠀⠑⢄⡀⠀⠀⠙⢦⡀⠀⠀⠀
        ⠀⠀⠀⠀⣼⠃⠀⠀⢠⣞⠟⠀⠀⠀⡄⠀⠉⠒⠢⣤⣤⠄⣼⢻⠸⠀⠀⠀⠀⠉⢤⠀⢿⡖⠒⠊⢦⠤⠤⣀⣀⡀⠀⠀⠀⠈⠻⡝⠲⢤⣀⠙⢦⠀⠀
        ⠀⠀⠀⢰⠃⠀⠀⣴⣿⠎⠀⠀⢀⣜⠤⠄⢲⠎⠉⠀⠀⡼⠸⠘⡄⡇⠀⠀⠀⠀⢸⠀⢸⠘⢆⠀⠘⡄⠀⠀⠀⢢⠉⠉⠀⠒⠒⠽⡄⠀⠈⠙⠮⣷⡀
        ⠀⠀⠀⡟⠀⠀⣼⢻⠧⠐⠂⠉⡜⠀⠀⡰⡟⠀⠀⠀⡰⠁⡇⠀⡇⡇⠀⠀⠀⠀⢺⠇⠀⣆⡨⢆⠀⢽⠀⠀⠀⠈⡷⡄⠀⠀⠀⠀⠹⡄⠀⠀⠀⠈⠁
        ⠀⠀⢸⠃⠀⠀⢃⠎⠀⠀⠀⣴⠃⠀⡜⠹⠁⠀⠀⡰⠁⢠⠁⠀⢸⢸⠀⠀⠀⢠⡸⢣⠔⡏⠀⠈⢆⠀⣇⠀⠀⠀⢸⠘⢆⠀⠀⠀⠀⢳⠀⠀⠀⠀⠀
        ⠀⠀⢸⠀⠀⠀⡜⠀⠀⢀⡜⡞⠀⡜⠈⠏⠀⠈⡹⠑⠒⠼⡀⠀⠀⢿⠀⠀⠀⢀⡇⠀⢇⢁⠀⠀⠈⢆⢰⠀⠀⠀⠈⡄⠈⢢⠀⠀⠀⠈⣇⠀⠀⠀⠀
        ⠀⠀⢸⡀⠀⢰⠁⠀⢀⢮⠀⠇⡜⠀⠘⠀⠀⢰⠃⠀⠀⡇⠈⠁⠀⢘⡄⠀⠀⢸⠀⠀⣘⣼⠤⠤⠤⣈⡞⡀⠀⠀⠀⡇⠰⡄⢣⡀⠀⠀⢻⠀⠀⠀⠀
        ⠀⠀⠈⡇⠀⡜⠀⢀⠎⢸⢸⢰⠁⠀⠄⠀⢠⠃⠀⠀⢸⠀⠀⠀⠀⠀⡇⠀⠀⡆⠀⠀⣶⣿⡿⠿⡛⢻⡟⡇⠀⠀⠀⡇⠀⣿⣆⢡⠀⠀⢸⡇⠀⠀⠀
        ⠀⠀⢠⡏⠀⠉⢢⡎⠀⡇⣿⠊⠀⠀⠀⢠⡏⠀⠀⠀⠎⠀⠀⠀⠀⠀⡇⠀⡸⠀⠀⠀⡇⠀⢰⡆⡇⢸⢠⢹⠀⠀⠀⡇⠀⢹⠈⢧⣣⠀⠘⡇⠀⠀⠀
        ⠀⠀⢸⡇⠀⠀⠀⡇⠀⡇⢹⠀⠀⠀⢀⡾⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⡇⢠⠃⠀⠀⠠⠟⡯⣻⣇⢃⠇⢠⠏⡇⠀⢸⡆⠀⢸⠀⠈⢳⡀⠀⡇⠀⠀⠀
        ⠀⠀⠀⣇⠀⡔⠋⡇⠀⢱⢼⠀⠀⡂⣼⡇⢹⣶⣶⣶⣤⣤⣀⠀⠀⠀⣇⠇⠀⠀⠀⠀⣶⡭⢃⣏⡘⠀⡎⠀⠇⠀⡾⣷⠀⣼⠀⠀⠀⢻⡄⡇⠀⠀⠀
        ⠀⠀⠀⣹⠜⠋⠉⠓⢄⡏⢸⠀⠀⢳⡏⢸⠹⢀⣉⢭⣻⡽⠿⠛⠓⠀⠋⠀⠀⠀⠀⠀⠘⠛⠛⠓⠀⡄⡇⠀⢸⢰⡇⢸⡄⡟⠀⠀⠀⠀⢳⡇⠀⠀⠀
        ⠀⣠⠞⠁⠀⠀⠀⠀⠀⢙⠌⡇⠀⣿⠁⠀⡇⡗⠉⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠰⠀⠀⠀⠀⠀⠀⠁⠁⠀⢸⣼⠀⠈⣇⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⢸⠁⠀⠀⢀⡠⠔⠚⠉⠉⢱⣇⢸⢧⠀⠀⠸⣱⠀⠀⠀⠀⠀⠀⠀⠀⣀⣀⡤⠦⡔⠀⠀⠀⠀⠀⢀⡼⠀⠀⣼⡏⠀⠀⢹⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⢸⠀⠀⠀⠋⠀⠀⠀⢀⡠⠤⣿⣾⣇⣧⠀⠀⢫⡆⠀⠀⠀⠀⠀⠀⠀⢨⠀⠀⣠⠇⠀⠀⢀⡠⣶⠋⠀⠀⡸⣾⠁⠀⠀⠈⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⢸⡄⠀⠀⠀⠀⠠⠊⠁⠀⠀⢸⢃⠘⡜⡵⡀⠈⢿⡱⢲⡤⠤⢀⣀⣀⡀⠉⠉⣀⡠⡴⠚⠉⣸⢸⠀⠀⢠⣿⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⢧⠀⠀⠀⠀⠀⠀⠀⣀⠤⠚⠚⣤⣵⡰⡑⡄⠀⢣⡈⠳⡀⠀⠀⠀⢨⡋⠙⣆⢸⠀⠀⣰⢻⡎⠀⠀⡎⡇⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠈⢷⡀⠀⠀⠀⠀⠀⠁⠀⠀⠀⡸⢌⣳⣵⡈⢦⡀⠳⡀⠈⢦⡀⠀⠘⠏⠲⣌⠙⢒⠴⡧⣸⡇⠀⡸⢸⠇⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⢠⣿⠢⡀⠀⠀⠀⠠⠄⡖⠋⠀⠀⠙⢿⣳⡀⠑⢄⠹⣄⡀⠙⢄⡠⠤⠒⠚⡖⡇⠀⠘⣽⡇⢠⠃⢸⢀⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⣾⠃⠀⠀⠀⠀⠀⢀⡼⣄⠀⠀⠀⠀⠀⠑⣽⣆⠀⠑⢝⡍⠒⠬⢧⣀⡠⠊⠀⠸⡀⠀⢹⡇⡎⠀⡿⢸⠇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⡼⠁⠀⠀⠀⠀⠀⠀⢀⠻⣺⣧⠀⠀⠀⠰⢢⠈⢪⡷⡀⠀⠙⡄⠀⠀⠱⡄⠀⠀⠀⢧⠀⢸⡻⠀⢠⡇⣾⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⢰⠇⠀⠀⠀⠀⠀⠀⠀⢸⠀⡏⣿⠀⠀⠀⠀⢣⢇⠀⠑⣄⠀⠀⠸⡄⠀⠀⠘⡄⠀⠀⠸⡀⢸⠁⠀⡾⢰⡏⢳⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
    """

    cinnamoroll = R"""
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣀⣤⡤⠤⠤⠤⣤⣄⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⡤⠞⠋⠁⠀⠀⠀⠀⠀⠀⠀⠉⠛⢦⣤⠶⠦⣤⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⢀⣴⠞⢋⡽⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠃⠀⠀⠙⢶⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⣰⠟⠁⠀⠘⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢰⡀⠀⠀⠉⠓⠦⣤⣤⣤⣤⣤⣤⣄⣀⠀⠀⠀
        ⠀⠀⠀⠀⣠⠞⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣴⣷⡄⠀⠀⢻⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠻⣆⠀
        ⠀⠀⣠⠞⠁⠀⠀⣀⣠⣏⡀⠀⢠⣶⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠹⠿⡃⠀⠀⠄⣧⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠸⡆
        ⢀⡞⠁⠀⣠⠶⠛⠉⠉⠉⠙⢦⡸⣿⡿⠀⠀⠀⡄⢀⣀⣀⡶⠀⠀⠀⢀⡄⣀⠀⣢⠟⢦⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣸⠃
        ⡞⠀⠀⠸⠁⠀⠀⠀⠀⠀⠀⠀⢳⢀⣠⠀⠀⠀⠉⠉⠀⠀⣀⠀⠀⠀⢀⣠⡴⠞⠁⠀⠀⠈⠓⠦⣄⣀⠀⠀⠀⠀⣀⣤⠞⠁⠀
        ⣧⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣼⠀⠁⠀⢀⣀⣀⡴⠋⢻⡉⠙⠾⡟⢿⣅⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠉⠙⠛⠉⠉⠀⠀⠀⠀
        ⠘⣦⡀⠀⠀⠀⠀⠀⠀⣀⣤⠞⢉⣹⣯⣍⣿⠉⠟⠀⠀⣸⠳⣄⡀⠀⠀⠙⢧⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠈⠙⠒⠒⠒⠒⠚⠋⠁⠀⡴⠋⢀⡀⢠⡇⠀⠀⠀⠀⠃⠀⠀⠀⠀⠀⢀⡾⠋⢻⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⡇⠀⢸⡀⠸⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⠀⠀⢠⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⣇⠀⠀⠉⠋⠻⣄⠀⠀⠀⠀⠀⣀⣠⣴⠞⠋⠳⠶⠞⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠳⠦⢤⠤⠶⠋⠙⠳⣆⣀⣈⡿⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
    """

    cat = R"""
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣤⣤⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣀⣀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣾⣿⣿⣿⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣼⣿⣿⣿⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⢀⣾⣿⣿⣿⣿⣷⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣼⣿⣿⣿⣿⣿⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⣾⣿⣿⣿⣿⣿⣿⣧⠀⠀⠀⠀⠀⠀⠀⠀⠀⢰⣿⣿⣿⣿⣿⣿⣧⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⣼⣿⣿⣿⣿⣿⣿⣿⣿⣇⠀⠀⠀⠀⠀⠀⠀⢀⣿⣿⣿⣿⣿⣿⣿⣿⡆⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⢰⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡄⠀⠀⠀⠀⠀⠀⣼⣿⣿⣿⣿⣿⣿⣿⣿⣷⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⢀⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣧⠀⠀⠀⠀⠀⢰⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⢸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡄⠀⠀⠀⢀⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣇⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⢀⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⢸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠈⣿⣿⣿⣿⣿⣿⠟⠉⠀⠀⠀⠙⢿⣿⣿⣿⣿⣿⣿⣿⡿⠋⠀⠀⠙⢻⣿⣿⣿⣿⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⣿⣿⣿⣿⣿⠃⠀⠀⠀⠀⣠⣄⠀⢻⣿⣿⣿⣿⣿⡿⠀⣠⣄⠀⠀⠀⢻⣿⣿⣏⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⣾⣿⣿⣿⣿⠀⠀⠀⠀⠰⣿⣿⠀⢸⣿⣿⣿⣿⣿⡇⠀⣿⣿⡇⠀⠀⢸⣿⣿⣿⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⣿⣿⣿⣿⣿⣄⠀⠀⠀⠀⠙⠃⠀⣼⣿⣿⣿⣿⣿⣇⠀⠙⠛⠁⠀⠀⣼⣿⣿⣿⡇⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⣿⣿⣿⣿⣿⣿⣷⣤⣄⣀⣠⣤⣾⣿⣿⣿⣿⣽⣿⣿⣦⣄⣀⣀⣤⣾⣿⣿⣿⣿⠃⠀⠀⢀⣀⠀⠀
        ⠰⡶⠶⠶⠶⠿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡟⠛⠉⠉⠙⠛⠋⠀
        ⠀⠀⢀⣀⣠⣤⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠷⠶⠶⠶⢤⣤⣀⠀
        ⠀⠛⠋⠉⠁⠀⣀⣴⡿⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣯⣤⣀⡀⠀⠀⠀⠀⠘⠃
        ⠀⠀⢀⣤⡶⠟⠉⠁⠀⠀⠉⠛⠿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠿⠟⠉⠀⠀⠀⠉⠙⠳⠶⣄⡀⠀⠀
        ⠀⠀⠙⠁⠀⠀⠀⠀⠀⠀⠀⠀⢰⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡏⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠁⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢠⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣼⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⣸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⣴⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
    """

    coding = R"""
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣀⣤⠶⣻⠝⠋⠠⠔⠛⠁⡀⠀⠈⢉⡙⠓⠶⣄⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣠⠞⢋⣴⡮⠓⠋⠀⠀⢄⠀⠀⠉⠢⣄⠀⠈⠁⠀⡀⠙⢶⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣠⠞⢁⣔⠟⠁⠀⠀⠀⠀⠀⠈⡆⠀⠀⠀⠈⢦⡀⠀⠀⠘⢯⢢⠙⢦⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⡼⠃⠀⣿⠃⠀⠀⠀⠀⠀⠀⠀⠀⠸⠀⠀⠀⠀⠀⢳⣦⡀⠀⠀⢯⠀⠈⣷⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣾⠆⡄⢠⢧⠀⣸⠀⠀⠀⠀⠀⠀⠀⢰⠀⣄⠀⠀⠀⠀⢳⡈⢶⡦⣿⣷⣿⢉⣷⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢠⣿⣯⣿⣁⡟⠈⠣⡇⠀⠀⢸⠀⠀⠀⠀⢸⡄⠘⡄⠀⠀⠀⠈⢿⢾⣿⣾⢾⠙⠻⣾⣧⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣿⡿⣮⠇⢙⠷⢄⣸⡗⡆⠀⢘⠀⠀⠀⠀⢸⠧⠀⢣⠀⠀⠀⡀⡸⣿⣿⠘⡎⢆⠈⢳⣽⣆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⢠⡟⢻⢷⣄⠀⠀⠀⠀⠀⠀⣾⣳⡿⡸⢀⣿⠀⠀⢸⠙⠁⠀⠼⠀⠀⠀⠀⢸⣇⠠⡼⡤⠴⢋⣽⣱⢿⣧⠀⢳⠈⢧⠀⢻⣿⣧⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⢀⡿⣠⡣⠃⣿⠃⠀⠀⠀⠀⣸⣳⣿⠇⣇⢸⣿⢸⣠⠼⠀⠀⠀⡇⠀⡀⠉⠒⣾⢾⣆⢟⣳⡶⠓⠶⠿⢼⣿⣇⠈⡇⠘⢆⠈⢿⡘⣷⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠈⢷⣍⣤⡶⣿⡄⠀⠀⠀⢠⣿⠃⣿⠀⡏⢸⣿⣿⠀⢸⠀⠀⢠⡗⢀⠇⠀⢠⡟⠀⠻⣾⣿⠀⠀⠀⠀⡏⣿⣿⡀⢹⡀⠈⢦⠈⢷⣿⡆⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⢁⣤⣄⠁⠀⠀⠀⣼⡏⢰⣟⠀⣇⠘⣿⣿⣾⣾⣆⢀⣾⠃⣼⢠⣶⣿⣭⣷⣶⣾⣿⣤⠀⠀⠀⡇⡯⣍⣧⠀⣷⠄⠈⢳⡀⢻⡁⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠺⣿⡿⠀⠀⠀⠀⡿⢀⣾⣧⠀⡗⡄⢿⣿⡙⣽⣿⣟⠛⠚⠛⠙⠉⢹⣿⣿⣦⠀⢸⡿⠀⠀⠀⢰⡯⣌⢻⡀⢸⢠⢰⡄⠹⡷⣿⣦⣤⠤⣶⡇⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⠀⠀⠀⣇⣾⣿⢸⢠⣧⢧⠘⣿⡇⠸⣿⢿⡆⠀⠀⠀⠀⠘⣯⠇⣿⠂⣸⢰⠀⠀⢀⣸⡧⣊⣼⡇⢸⣼⣸⣷⢣⢻⣄⠉⠙⠛⠉⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣳⣤⣴⣿⣏⣿⣾⢸⣿⡘⣧⣘⢿⣀⡙⣞⠁⠀⠀⠀⠀⢀⡬⢀⣉⢠⣧⡏⠀⠀⡎⣿⣿⣿⣿⠃⣸⡏⣿⣿⡎⢿⡘⡆⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠉⠉⣠⣼⣿⣿⣿⣼⣿⣧⢿⣿⣿⣯⡻⠟⠀⠀⠀⠀⠀⠐⢯⠣⡽⢟⣽⠀⠀⢘⡇⣿⣿⣿⡟⣴⣿⣷⣿⣿⣧⣿⣷⡽⠀⠀⠀⠀⠀⠀⠀
        ⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣼⣹⣿⣇⣸⣿⣿⣿⣻⣚⣿⡿⣿⣿⣦⣤⣀⡉⠃⠀⢀⣀⣤⡶⠛⡏⠀⢀⣼⢸⣿⣿⣿⣿⣿⣿⣿⢋⣿⣿⣿⣿⡇⠀⠀⠀⠀⠀⠀⠀
        ⣿⠛⠛⠛⠛⠛⠛⠛⠛⠛⠛⠛⠛⠛⠛⠛⠛⠛⠛⠛⠛⠛⠒⠒⠒⢭⢻⣽⣿⣿⣿⣿⣿⣿⢿⠿⣿⡏⠀⡼⠁⣀⣾⣿⣿⣿⣿⡿⣿⣿⣟⡻⣿⣿⡿⠣⠟⠀⠀⠀⠀⠀⠀⠀⠀
        ⠸⡆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⢧⢿⣯⡽⠿⠛⠋⣵⢟⣋⣿⣶⣞⣤⣾⣿⣿⡟⢉⡿⢋⠻⢯⡉⢻⡟⢿⡅⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⢻⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⡞⣿⣆⡀⠀⡼⡏⠉⠚⠭⢉⣠⠬⠛⠛⢁⡴⣫⠖⠁⠀⠀⣩⠟⠁⣸⣇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠈⢷⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢹⣽⣿⣿⣾⠳⡙⣦⡤⠜⠊⠁⠀⣀⡴⠯⠾⠗⠒⠒⠛⠛⠛⠛⠛⠓⠿⣦⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠘⣧⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠰⣄⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢷⣻⣿⣿⠔⢪⠓⠬⢍⠉⣩⣽⢻⣤⣶⣦⠀⠀⠀⢀⣀⣤⣴⣾⣿⣿⣿⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠹⡆⠀⠀⠀⠀⠀⠀⠀⠀⠀⣰⣾⡏⢦⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⣯⣿⣿⠀⠀⣇⠀⣠⠎⠁⢹⡎⡟⡏⣷⣶⠿⠛⡟⠛⠛⣫⠟⠉⢿⣿⡿⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⢻⡄⠀⠀⠀⠀⠀⠀⠀⠀⠹⣿⣷⠈⢷⡤⠀⠀⠀⠀⠀⠀⠀⠀⠀⢹⣾⣷⡀⣀⣀⣷⡅⠀⠀⠈⣷⢳⡇⣿⠀⠀⣸⠁⢠⡾⣟⣛⣻⣟⡿⣇⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⢷⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢯⢻⣏⡵⠿⠿⢤⣄⠀⢀⣿⢸⣹⣿⣀⣴⣿⣴⣿⣛⠋⠉⠉⡉⠛⣿⣧⡀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠘⣧⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⡎⣿⣥⣶⠖⢉⣿⡿⣿⣿⡿⣿⣟⠿⠿⣿⣿⣿⡯⠻⣿⣿⣿⣷⡽⣿⡗⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠸⣇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠸⡘⣿⣩⠶⣛⣋⡽⠿⣷⢬⣙⣻⣿⣿⣿⣯⣛⠳⣤⣬⡻⣿⣿⣿⣿⣧⠀⠀⠀⠀⠀⠀⠀
    """

    female = R"""
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⡤⠤⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⠁⣬⡳⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⢠⠊⣰⠀⣦⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⡎⠀⢳⠈⢺⣦⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⢠⡃⡁⡇⠀⠈⠛⢤⡀⠀⠀⠀⠀⠀⣀⣀⣀⣀⡀⠀⠀⢀⠔⠋⠀⠀⢸⢼⡄⠈⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⡏⣀⡏⡇⠀⠀⠉⠢⠈⣖⣉⡉⠉⣹⢧⣀⣀⠤⠬⠭⢹⣋⠀⠀⠀⠀⡜⠈⠹⣄⢹⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⢸⠻⡁⠀⢧⠀⠀⢀⡤⠚⠉⠀⠀⠀⠘⡾⣷⡀⠀⠀⠀⠀⠈⢍⡒⢤⣰⠃⠀⠀⣼⢸⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⢸⢶⡃⠀⠈⣦⠞⠁⠀⢠⣮⣤⣴⣾⣿⣷⠹⣿⣿⣷⣿⣿⣶⣦⣷⣄⣈⡳⣄⠀⡬⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⣠⣟⢀⡜⠁⠀⠀⢠⣿⣿⣿⣿⣿⣿⣽⣧⠹⣿⣿⣿⣯⣵⣾⣿⣶⣲⠃⠈⢳⣳⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⣸⠃⢸⠏⠀⠀⠀⢀⣿⣿⣿⠿⡿⢿⠿⠟⠛⢧⠙⢟⠉⠙⠛⠛⢻⠛⠻⡄⠀⢄⠹⣇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⣰⡏⢀⠏⠀⠀⠀⠀⡜⠁⠀⠀⢠⡇⡜⠀⠀⠀⠀⠳⡌⢻⡀⠀⠀⠈⡆⠀⢸⡀⠈⠆⠹⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⢰⠻⠀⡼⠀⠀⠀⠀⢰⠃⠀⠀⢠⠇⡇⣷⠀⣧⠀⠦⠀⢸⢦⡹⣄⠀⠀⢧⠀⠀⡇⠠⠘⡄⢱⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⢼⡇⢀⠇⠀⠀⠀⠀⢸⠀⠀⣾⣸⠀⡇⡿⡀⣿⡆⠀⠀⢸⡀⣷⢮⣦⡀⢸⡆⠀⢸⠀⠀⢱⡀⣇⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⣾⠀⢸⠀⠀⠀⠀⠀⠸⡆⢰⢹⡇⠀⢸⡇⢧⣷⣽⡄⠀⢸⣧⣻⣎⣿⡿⣾⣿⠀⢸⠀⠀⠀⢃⢸⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⡍⠀⡇⢀⠀⠀⠀⠀⠀⣷⢼⠬⣧⣀⣈⣷⠘⢧⣹⢿⣄⠈⣏⢻⣞⣿⣷⣼⠿⡷⣦⣀⠀⠀⠘⠌⡆⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⡇⠀⡆⠀⣇⠀⠀⠀⠀⡿⣼⠀⠀⠀⠀⠙⣍⠉⠃⠀⠉⠓⠾⣉⣙⣈⣈⠃⠀⣷⠃⠉⠓⡦⣄⡀⣇⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⡇⠀⡇⠀⠘⣆⠀⠀⠀⣇⠙⠟⠛⣻⣿⡏⠉⠀⠀⠀⠀⠀⠈⠉⢛⣿⣟⡟⠋⢸⠆⠀⣠⠇⠀⠈⡏⠙⠒⠲⠦⠤⠄⠀⠀
        ⠀⠀⠀⡇⠀⡷⡀⠀⠘⣆⠀⠀⢹⠀⠀⠀⠙⠛⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠛⠋⠀⢸⠀⣠⠋⠀⠀⢀⡇⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠃⠀⣧⠱⡄⠀⠈⢧⡀⠘⣇⠀⣴⡶⡢⠾⠂⠀⠀⠀⠀⠀⠀⠀⠺⠊⢴⡷⢴⣏⡴⠃⠀⠀⢠⣾⠁⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⢧⠀⢸⡀⠙⢄⠀⠀⠙⢦⣘⣆⠉⠀⠀⠀⠀⠀⠀⠀⠀⠈⠀⠀⠀⠀⠀⢀⢾⡟⠀⠀⠀⡴⠃⡞⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⢸⡀⠀⢳⡀⠈⠣⡀⠀⠈⢻⡙⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⡼⠀⠀⢠⠞⠀⡼⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⢸⢃⠀⠀⠳⣄⠀⠈⢦⡀⠀⢧⣀⠀⠀⠀⠀⠀⠀⠉⠉⠀⠀⠀⠀⢀⡴⣾⠁⢀⡔⠁⢀⢾⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⡇⢸⡆⠀⠀⠈⡷⣦⡀⠙⢄⠘⣿⡝⠲⣤⣀⡀⠀⠀⠀⢀⣠⡴⠚⠁⣷⠇⡰⠋⣀⡴⠋⣸⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⡼⣡⢣⢷⠀⠀⢰⠀⡇⠈⠳⣄⠃⢹⣷⡿⠷⣄⣉⡉⠒⣊⡩⠿⣿⠀⠀⡟⣰⠕⣫⣾⠀⠀⣇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⣴⡵⠁⡜⠘⠀⣀⡦⠴⠥⢤⠤⢾⠳⣜⡏⡷⣤⠶⠤⣍⣷⣣⡤⠴⢻⢳⣶⣧⢣⠾⠖⠛⠒⠤⣼⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⡾⠋⢀⡜⠀⢠⠏⠁⠀⠀⠀⠈⣦⠎⠀⠘⢿⡇⢸⠀⢐⣺⣧⣿⣋⣀⣼⣀⣿⢰⢳⠀⠰⡄⠀⠀⠀⠙⡷⣄⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⣠⠎⠀⢠⠇⠀⠀⡄⠀⢀⠔⠃⠀⠀⢠⠟⡇⠈⡏⢡⣾⡿⠿⣿⡍⢹⡏⢹⡇⠈⠣⡀⡇⠀⠀⠀⠀⠘⡄⠉⠒⠒⠒⠢⣤⡶⠞
        ⠞⠁⠀⠀⡸⠀⠀⠀⢸⣶⠋⢦⣀⣀⣴⡟⠀⢧⠀⡼⠼⣇⠀⠀⢀⠗⠛⣿⠘⣦⣀⠀⠈⢳⣄⠀⠀⠀⠀⢻⢿⣉⠉⠉⠉⠁⠀⠀
    """

    catgirl = R"""
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢰⡒⣢⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⡤⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠻⠃⠀⠀⠀⠉⣁⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⡀⠀⠀⠈⠛⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠠⣶⣟⣛⠛⠋⠉⠉⠉⠉⠉⠉⠉⠉⠉⠙⢛⣛⣷⡦⢀⣤⣶⡶⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⢀⡀⠀⠀⠀⠀⠀⣴⣶⣶⠂⠤⢄⣀⠀⠀⠀⠈⠉⠛⠛⠛⠛⠛⠛⠛⠛⠛⠛⠛⠛⠛⠛⠋⠉⣰⣿⣿⣿⣇⢹⡄⠀⠀⠀⣀⠀⣠⠤⠠⡄⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⣀⡯⠹⢲⡄⠀⠀⠀⣿⣿⣿⣷⣤⡀⠈⣹⣶⠦⣄⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣾⣿⣿⣿⣿⣿⠀⢷⠀⠀⢰⡇⠋⠀⠀⢠⠇⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠛⠒⣎⡏⠀⠀⠀⠀⣿⣿⣿⡏⠙⠛⢦⡙⠉⠀⠀⠉⠓⢦⣀⠀⠀⢀⣀⣀⣀⣀⣀⡀⠀⢠⣿⣿⣿⠟⠻⣿⣿⡇⢸⡇⠀⠀⠓⠒⣦⠀⠛⢦⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⠿⠓⠂⠀⡠⠽⢦⡀⠀⠀⠀⠈⠛⢛⡉⢉⠉⠀⠀⠙⠛⠋⢛⣿⢯⡉⠛⠀⠀⠘⠈⢿⠗⢻⠀⠀⠀⠀⠛⠦⠶⠋⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣇⠀⠀⢠⠋⠀⢀⡾⢛⡆⠀⠀⠀⢉⡽⠛⠁⠈⣏⢦⠐⢶⣤⡹⣿⠒⠁⠀⠀⢀⡠⠤⢼⢣⢸⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⡴⠲⢤⡀⣀⣀⠀⠀⢸⣿⡗⠀⡇⠀⣠⣾⠟⠛⠡⣾⡴⢶⡯⠀⠤⠀⠀⢸⠸⡇⠀⡙⣿⣌⠻⣤⣀⡠⠋⠀⠀⢸⡏⢠⣇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⡇⠀⠀⠉⠁⣸⠀⠀⠀⢿⣿⠤⣫⡾⣿⣿⢱⣀⡼⠛⢒⡿⠀⠀⠀⠀⠀⠸⡇⢳⠐⠛⠉⠻⣇⢹⢿⣟⣦⣀⣸⣍⣷⣿⣿⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⢀⡴⠄⠀⢰⠚⠁⠀⠀⠀⠘⢿⣿⡿⣤⠉⠁⣠⡿⠁⠀⣼⠁⠀⠀⣀⣀⡤⠂⡇⢸⡀⠀⠀⠀⠹⡆⠀⠀⠀⢿⣿⣤⣿⣿⣿⡇⠀⠀⠀⢀⢤⡀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠸⣄⣀⣀⡼⠀⠀⠀⠀⠀⠀⣼⣿⡶⠟⠀⣴⣿⠶⢦⢰⡟⡆⠀⣀⣩⣀⠀⢰⡇⣸⡓⠄⢀⣀⡀⢿⡀⡴⠛⢶⠘⣿⣿⣿⣿⣿⡀⠀⠘⢧⣀⡕⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣼⣿⠃⠀⠀⢠⣿⠷⣤⡾⣼⡇⠁⢸⣏⠁⢘⡷⢘⡗⣿⣧⠆⣿⣈⡿⢺⣇⠉⢳⠟⠀⢸⣿⣿⣿⣿⣷⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣾⣽⡓⠀⠠⣼⢺⡅⠀⠂⣿⡩⡧⠀⠀⠛⠶⡛⠉⠁⣿⡏⠻⣬⠄⠨⠀⠀⢻⠀⠐⡄⠂⠀⣿⣿⣿⣿⣿⡆⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣠⣾⣿⡿⡄⠀⢸⣿⣿⠁⣀⣿⣟⣀⣇⠆⢠⣀⣤⣄⠀⠀⢿⣿⣶⣻⣮⡀⠀⠀⣼⠀⠀⡏⠁⠀⢸⣿⣿⣿⣿⣇⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⣠⣾⣿⡿⣿⢿⠀⠀⣿⣿⣿⠀⣿⠟⠉⠀⢹⡄⢸⣿⣿⣿⣿⣦⣸⡟⠀⠈⢻⣷⣆⡐⣿⡂⠀⡇⠀⠀⠘⣿⣿⣿⣿⣿⠀⠀⠀⠀⢀⡶⡄⠀⠀
        ⢀⣦⡀⠀⠀⠀⠠⠴⠾⠛⠋⠉⠀⣿⠀⠀⠀⣿⠁⣿⣿⠉⠀⠀⠀⠈⣿⣿⣿⣿⣿⣿⣿⣿⡇⠀⠀⠀⠙⢿⣿⣿⠀⠀⣅⠁⠀⠀⣿⣿⣿⣿⣿⠀⠀⠀⠸⡍⣰⣧⠀⠀
        ⠈⣇⠙⢦⡀⠀⠀⠀⠀⠀⠀⠀⢰⣿⠀⠀⠀⣿⠄⣿⠃⠀⠀⠀⠀⠀⢹⣿⣿⣿⠟⠛⠿⠛⢇⠀⠀⠀⠀⠀⠻⣿⠀⢸⣇⠀⠀⣼⣿⣿⣿⣿⣿⠀⠀⠀⠐⠷⠃⠉⠀⠀
        ⠀⢹⡀⠀⠙⢄⠀⠀⠀⠀⠀⠀⣾⣿⠀⠀⠀⣿⣆⣿⣠⣴⣶⣶⣤⣅⡒⢻⡀⠉⠳⣾⣷⣦⣸⣭⣴⡶⢶⣤⣤⣾⠀⣸⠧⠀⣸⣿⣿⣿⣿⣿⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⢻⡷⠀⠀⠈⠳⣄⠀⠀⠀⣸⣿⣿⣀⠄⠀⣿⣷⣿⠛⣋⣉⣀⡀⠉⠉⠀⠀⠀⠀⠀⠉⠈⠉⣉⣈⡉⠉⠛⠿⡿⠆⣿⠂⢰⣿⣿⣿⣿⣿⣿⣿⣷⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⣤⣳⡕⠄⠀⣦⠘⣦⠀⢠⣿⣿⣿⣿⣆⠀⠘⣿⣿⣜⠿⢳⠻⠁⠀⠀⢠⣠⢄⣀⣠⡄⠀⢚⢏⢎⣿⡿⡴⣸⣧⣾⣏⣴⣿⣿⣿⣿⣿⣿⣿⣿⣿⣆⠀⠀⠀⠀⠀⠀⠀
        ⠀⢻⡌⡛⠀⢀⣘⣿⣿⣄⣾⣿⣿⣿⣿⣿⣷⣤⣽⠟⠉⠉⠙⠒⢤⡀⠀⠘⢆⠀⠀⢠⠃⠀⠈⢈⡤⠞⠋⠉⠉⠛⠻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣼⣆⠀⠀⠀⠀⠀⠀
        ⠀⠀⠻⣮⣀⣺⣿⣿⣿⣟⣿⣿⣿⣿⣿⡻⢿⡿⠏⠀⠀⠀⠀⠀⠀⠙⢦⠀⠈⠑⠒⠋⠀⢀⡴⠋⠀⠀⠀⠀⠀⠀⢀⠈⠻⣿⣿⣿⣿⣿⣿⢿⣿⣿⣿⣿⣧⠀⠀⠀⠀⠀
        ⠀⠀⢺⣿⣿⣿⣿⣿⣿⣿⣵⣿⣿⣿⣿⣿⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀⢸⣷⣶⣦⣤⣶⣶⠊⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⡆⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⡄⠀⠀⠀
        ⠀⠀⠀⣽⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠀⠀⠀⠀⠀⠀⠀⠀⢸⣿⣿⣍⣉⣽⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣦⡀⠀
        ⠀⠀⠀⠘⣿⣿⣿⣿⣿⢟⣱⣿⣿⣿⣿⣿⣿⣿⡀⠀⠀⠀⠀⠀⠀⠀⠸⣿⣿⣿⣿⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣖
    """

    spy = R"""
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣠⣴⡶⣆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣾⣽⠟⣿⢸⡆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣟⡾⠁⠀⣿⢸⡅⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⣹⡇⠀⠀⣿⡞⢃⣀⣠⢤⢤⣤⣤⣤⣤⣤⠤⠤⣄⣀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⣿⣧⠀⢠⡟⣿⡽⠟⠚⠋⠉⠉⠉⠉⠉⠉⠉⠛⠒⠿⣭⣗⡲⢤⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣠⢴⣖⣿⡽⠆⠘⠋⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠉⠳⢮⣕⢦⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣴⣻⠞⠋⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠻⢮⣿⣭⣭⣽⣭⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⡴⣻⠟⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡀⠀⠀⠀⠀⠀⠀⠙⢷⡄⠀⢠⡿⡟⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⢀⣜⡿⠃⢀⣤⣤⣤⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠻⡄⠀⠀⠀⠀⠀⠀⠈⢻⣄⣸⣿⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⣠⢞⣟⣡⣴⠿⠯⣿⢿⣿⣦⠀⠀⠀⠀⠀⠀⠀⢀⣠⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠹⡆⠀⠀⠀⠠⡄⠀⠀⢻⡟⡟⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⣠⣴⣞⣽⡷⠟⠋⠁⠀⠀⠀⢿⣦⣿⣿⡆⠀⠀⠀⡆⠀⠰⠋⠀⢸⠂⠀⠀⠀⠀⠀⠀⠀⠰⣄⠀⠀⢹⣆⠀⠀⠀⠈⠢⠀⠀⣧⣿⠀⠀⠀⠀⠀⠀⠀⣀⡀⠀⠀
        ⠀⠹⡿⣿⡀⠀⠀⠀⠀⠀⠀⠀⢼⡏⢹⣿⡇⠀⠀⢠⠃⠀⠀⠀⣀⣀⣀⡀⠀⢠⡄⠀⠀⠀⠀⠀⠀⠶⢾⣿⡶⠦⠄⢰⠀⠀⠀⣹⣿⡇⠀⢀⣀⣠⣤⣞⣷⢿⠀⠀
        ⠀⠀⠈⠻⣿⣦⡀⠀⠀⠀⠀⠀⣨⡿⣾⣿⡇⠀⠀⣼⠀⢠⠖⠋⠁⠀⣼⠇⠀⢀⣷⠀⠀⠀⠀⠀⠀⠀⣼⣉⣧⡀⠀⣸⡆⠀⢀⣿⡟⣷⣾⣿⠟⠛⠳⠟⣿⡿⠀⠀
        ⠀⠀⠀⠀⢸⢸⠻⣦⡀⠀⠀⢸⡇⣰⣿⡿⠀⠀⠀⡏⠀⡌⠀⢀⣠⣴⣿⣄⣀⣾⠻⡆⠀⣠⠀⠀⢠⣾⣟⣛⡛⠿⣶⣟⣿⣠⣾⡟⣷⣿⣿⠁⠀⠀⠀⢸⣽⣧⣄⠀
        ⠀⠀⠀⠀⣸⣸⠀⠈⢿⣿⣏⣩⣿⣿⠟⠁⠀⠀⢰⡇⢸⢁⣴⣿⠿⠭⣍⡉⠙⠷⢤⣧⣴⢻⣠⡴⢻⡟⠁⠀⠙⢷⡈⢻⣿⣿⡞⠁⣿⣽⠋⠀⠀⠀⠀⣀⣭⠿⣿⠇
        ⠀⠀⠀⠀⡇⣿⡆⠀⠈⠻⣷⠾⠛⢹⡄⠀⠀⠀⢸⣇⣿⣿⡟⠁⠀⠀⠀⠹⣄⠀⠀⠉⠁⠈⠁⠀⢸⠀⡠⠒⣦⣈⡇⠈⣿⣿⠃⠀⣿⡟⢷⡀⢠⢾⣿⠷⠋⠉⠁⠀
        ⠀⠀⠀⠀⣿⡿⠀⠀⠀⣴⣿⠀⠀⠀⠙⣦⠀⠀⠸⣿⢿⣿⠆⠀⠰⠒⢶⣀⣽⡄⠀⠀⠀⠀⠀⠀⢸⡍⠁⠀⡀⢀⡇⠀⣿⡟⠀⢀⣿⡇⠈⢿⣿⡞⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⢰⣽⠃⠀⠀⢠⠇⣿⠀⠀⠀⠀⠈⢷⣄⠀⢿⣛⣿⣏⠀⠉⠓⠬⠤⣼⠇⠀⠀⠀⠀⠀⠀⠀⠻⢄⣀⡠⠞⡀⠀⢰⡇⢀⡞⢹⡇⠀⢸⡇⣷⠀⠀⠀⠀⠀⠀
        ⠀⠀⢰⣿⠇⠀⠀⠀⣾⠀⣿⠀⠀⠀⠀⢀⠀⠻⣷⣼⣯⠀⠉⠛⠦⣤⣤⠴⢋⡤⠀⠀⠀⠀⠀⠀⠀⠀⠘⠓⠒⠚⠁⠀⠈⠉⢻⡅⣼⡇⠀⢸⣇⣿⠀⠀⠀⠀⠀⠀
        ⠀⠀⣮⡞⠀⠀⠀⢀⡏⠀⢹⡇⠀⠀⠀⠀⠳⣤⡈⠻⢿⣷⡄⠀⠀⠀⠉⠉⠉⠀⠀⡴⠚⠋⠙⢿⡇⠀⠀⠀⠀⠀⠀⠀⠀⢀⡼⢣⠟⣿⠀⣼⣿⡟⠀⠀⠀⠀⠀⠀
        ⠀⣼⡼⠁⠀⠀⠀⢸⠁⠀⠀⣷⠀⠀⠀⠀⠀⠀⠙⠦⣄⡉⠛⢧⣄⠀⠀⠀⠀⠀⠀⢷⣄⠀⠀⣰⠇⠀⠀⠀⠀⠀⢀⣠⡴⠏⣠⡏⠀⣿⣾⣿⡼⠀⠀⠀⠀⠀⠀⠀
        ⢰⣳⠇⢠⠀⠀⠀⢸⡆⠀⠀⠸⣧⠀⠀⠀⠀⠀⠀⠀⠀⠙⠳⢤⣈⡻⣄⠀⠀⠀⠀⠀⠉⠛⠛⠁⠀⢀⣀⣤⡤⠞⠛⠁⣀⡼⠋⠀⢀⡿⠛⡿⡇⠀⠀⠀⠀⠀⠀⠀
        ⡼⡿⠀⢸⠀⠀⠀⠸⡇⠀⠀⠀⠙⢧⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠙⢿⡆⠒⠒⠒⠒⢲⣶⣶⣾⣿⣿⣯⡀⠀⢀⣤⠖⠋⠀⠀⠀⣾⠃⠀⡇⡇⠀⠀⠀⠀⠀⠀⠀
        ⡇⡇⠀⢸⡄⠀⠀⠀⣿⡄⠀⠀⠀⠈⠻⣦⡀⠀⠀⠀⣀⠀⠀⠀⠀⠀⠀⢻⡀⠀⠀⠀⠀⠹⣿⣿⣿⣿⣿⣷⣄⢻⠁⠀⠀⠀⢀⣼⣷⣄⣼⣻⠃⠀⠀⠀⠀⠀⠀⠀
        ⢷⣧⠀⢸⣧⡀⠀⠀⠘⣷⣄⠀⠀⠀⠀⠈⠻⢦⣀⡀⠈⠳⢦⡀⠀⠀⠀⢸⠇⠠⠀⠀⠀⢀⣽⣿⣿⣿⣿⣿⡿⣿⠀⠀⠀⣠⣾⢟⣵⣟⡵⠃⠀⠀⠀⠀⠀⠀⠀⠀
        ⠈⢻⣧⣸⣹⣧⣀⠀⠀⠹⣟⣷⢤⣀⣥⡀⠀⠀⢈⣽⡿⠶⢶⣭⣷⡆⠀⣼⣦⣶⣶⣶⣿⣿⣿⠿⠟⠛⣿⣿⢿⣟⣠⠴⣻⠵⠛⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠹⢝⣫⠗⠯⢿⣒⣦⣿⣾⡟⢶⡽⠧⣴⣞⣻⠟⠀⠀⠀⠈⢿⣿⣿⣿⣿⣿⠿⠟⡋⢩⣤⣀⣀⣀⣽⢿⡼⡯⠒⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠉⠉⠀⠈⠉⠉⣽⣿⠏⠀⠈⠀⠀⠀⠈⣿⣿⡿⠋⠀⠀⣠⣿⠛⣿⠹⣿⠉⠁⠈⣧⣷⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⣳⣟⠀⠀⠀⠀⠀⠀⠀⢿⣿⣿⣤⣴⣾⡇⢸⠀⢹⡆⢸⣧⣠⣤⡿⣿⠇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠻⢝⣳⢶⣤⣀⣀⣀⣀⣾⢿⣿⣾⣷⡿⣤⠼⣿⣛⡷⠞⠿⠷⠒⠉⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠙⠓⠒⠫⠭⠭⠥⠋⠀⠀⠀⠈⠉⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
    """

    return random.choice([lucky_star, cinnamoroll, cat, coding, female, catgirl, spy])


def remove_path(path):
    try:
        if os.path.isfile(path):
            os.remove(path)
        elif os.path.isdir(path):
            shutil.rmtree(path)
        logging.debug("Removed %s", path)
    except OSError as e:
        logging.error("Error removing %s: %s", path, e)


def get_mpv_directory():
    if platform.system() == "Windows":
        return os.path.join(os.getenv('APPDATA'), 'mpv')

    return os.path.join(os.getenv('HOME'), '.config', 'mpv')


def get_aniworld_data_directory():
    if platform.system() == "Windows":
        return os.path.join(os.getenv('APPDATA'), 'aniworld', 'anime4k')

    return os.path.join(os.getenv('HOME'), '.aniworld', 'anime4k')


def get_anime4k_download_link(mode: str):
    os_type = "Windows" if platform.system() == "Windows" else "Mac_Linux"
    return (
        f"https://github.com/Tama47/Anime4K/releases/download/v4.0.1/"
        f"GLSL_{os_type}_{mode}-end.zip"
    )


def download_anime4k(mode: str):
    download_link = get_anime4k_download_link(mode)
    logging.debug("Downloading Anime4k from %s", download_link)

    anime4k_path = get_aniworld_data_directory()
    shaders_path = os.path.join(anime4k_path, f"GLSL_{platform.system()}_{mode}-end")
    archive_path = os.path.join(shaders_path, "anime4k.zip")

    os.makedirs(shaders_path, exist_ok=True)
    logging.debug("Created shaders path: %s", shaders_path)

    content = fetch_url_content(download_link)
    logging.debug("Fetched content from %s", download_link)

    with open(archive_path, 'wb') as f:
        f.write(content)
    logging.debug("Saved archive to %s", archive_path)

    logging.debug("Extracting package")
    with zipfile.ZipFile(archive_path, 'r') as zip_ref:
        zip_ref.extractall(shaders_path)
    logging.debug("Extracted package to %s", shaders_path)

    remove_path(archive_path)
    logging.debug("Removed archive: %s", archive_path)
    remove_path(os.path.join(shaders_path, "__MACOSX"))
    logging.debug("Removed __MACOSX directory if it existed.")


def remove_anime4k_files():
    mpv_directory = get_mpv_directory()
    input_conf_path = os.path.join(mpv_directory, "input.conf")

    logging.debug("Removing existing configuration files.")
    remove_path(input_conf_path)
    remove_path(os.path.join(mpv_directory, "mpv.conf"))
    remove_path(os.path.join(mpv_directory, "shaders"))


def set_anime4k_config(mode: str):
    anime4k_path = get_aniworld_data_directory()
    shaders_path = os.path.join(anime4k_path, f"GLSL_{platform.system()}_{mode}-end")
    mpv_directory = get_mpv_directory()

    os.makedirs(mpv_directory, exist_ok=True)
    logging.debug("Created MPV directory: %s", mpv_directory)

    input_conf_path = os.path.join(mpv_directory, "input.conf")
    if os.path.exists(input_conf_path):
        logging.debug("Found existing input.conf at %s", input_conf_path)
        with open(input_conf_path, "r", encoding='utf-8') as file:
            lines = file.readlines()

        current_mode = None
        for line in lines:
            if "lower-end" in line:
                current_mode = "Low"
                break
            if "higher-end" in line:
                current_mode = "High"
                break

        if current_mode == mode:
            logging.debug("Current mode is already set to %s. No changes made.", mode)
            return

        remove_anime4k_files()

    logging.debug("Copying shaders from %s to %s", shaders_path, mpv_directory)
    for item in os.listdir(shaders_path):
        source = os.path.join(shaders_path, item)
        destination = os.path.join(mpv_directory, item)
        if os.path.isdir(source):
            shutil.copytree(source, destination, dirs_exist_ok=True)
            logging.debug("Copied directory %s to %s", source, destination)
        else:
            shutil.copy(source, destination)
            logging.debug("Copied file %s to %s", source, destination)


def setup_anime4k(mode: str):
    if mode == "Remove":
        remove_anime4k_files()
        return

    download_anime4k(mode)
    set_anime4k_config(mode)
