import base64
import glob
import json
import logging
import os
import pathlib
import platform
import random
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
from importlib.metadata import version, PackageNotFoundError
from typing import List, Optional

import requests
import py7zr
from bs4 import BeautifulSoup
from requests.exceptions import HTTPError
from packaging.version import Version

import aniworld.globals as aniworld_globals


def check_dependencies(dependencies: list) -> None:
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

        if platform.system() == "Windows" or platform.system() == "Linux":
            logging.debug("Missing dependencies: %s. Attempting to download.", missing)
            missing = [dep.replace("SyncplayConsole", "syncplay") for dep in missing]
            download_dependencies(missing)
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
    if aniworld_globals.DEFAULT_USE_PLAYWRIGHT or os.getenv("USE_PLAYWRIGHT"):
        logging.debug("Now fetching without playwright: %s", url)
        return fetch_url_content_with_playwright(url, proxy, check)

    logging.debug("Now fetching using playwright: %s", url)
    return fetch_url_content_without_playwright(url, proxy, check)


def fetch_url_content_without_playwright(
    url: str, proxy: Optional[str] = None, check: bool = True
) -> Optional[bytes]:
    headers = {
        'User-Agent': aniworld_globals.DEFAULT_USER_AGENT
    }

    logging.debug("Using headers: %s", headers)

    proxies = {}
    if proxy:
        proxies = {
            'http': proxy,
            'https': proxy
        } if proxy.startswith('socks') else {
            'http': f'http://{proxy}',
            'https': f'https://{proxy}'
        }
    elif aniworld_globals.DEFAULT_PROXY:
        default_proxy = aniworld_globals.DEFAULT_PROXY
        proxies = {
            'http': default_proxy,
            'https': default_proxy
        } if default_proxy.startswith('socks') else {
            'http': f'http://{default_proxy}',
            'https': f'https://{default_proxy}'
        }
    else:
        proxies = {
            "http": os.getenv("HTTP_PROXY"),
            "https": os.getenv("HTTPS_PROXY"),
        }

    try:
        response = requests.get(url, headers=headers, proxies=proxies, timeout=300)
        response.raise_for_status()

        if "Deine Anfrage wurde als Spam erkannt." in response.text:
            logging.critical(
                "Your IP address is blacklisted. Please use a VPN, complete the captcha "
                "by opening the browser link, or try again later."
            )

        return response.content

    except requests.exceptions.Timeout as timeout_error:
        logging.critical("Request to %s timed out: %s", url, timeout_error)
        return fetch_url_content_with_playwright(url, proxy, check)

    except requests.exceptions.RequestException as request_error:
        if check:
            logging.critical("Request to %s failed: %s", url, request_error)
        return fetch_url_content_with_playwright(url, proxy, check)


def fetch_url_content_with_playwright(
    url: str, proxy: Optional[str] = None, check: bool = True
) -> Optional[bytes]:

    if "aniworld.to/redirect/" in url:
        return fetch_url_content_without_playwright(url, proxy, check)

    headers = {'User-Agent': aniworld_globals.DEFAULT_USER_AGENT}

    install_and_import("playwright")
    from playwright.sync_api import sync_playwright  # pylint: disable=import-error, import-outside-toplevel

    with sync_playwright() as p:
        options = {'proxy': {'server': proxy}} if proxy else {}
        headless = os.getenv("HEADLESS", not aniworld_globals.IS_DEBUG_MODE)
        browser = p.chromium.launch(headless=headless)

        context = browser.new_context(**options)
        page = context.new_page()
        page.set_extra_http_headers(headers)

        try:
            response = page.goto(url, timeout=10000)
            content = page.content()
            logging.debug(content)

            if page.locator(
                "h1#ddg-l10n-title:has-text('Checking your browser before accessing')"
            ).count() > 0:
                logging.debug("Captcha detected, attempting to solve.")

                for attempt in range(120):
                    page.wait_for_timeout(1000)
                    if page.locator(
                        "h1#ddg-l10n-title:has-text('Checking your browser before accessing')"
                    ).count() == 0:
                        logging.debug("Captcha solved.")
                        break
                    logging.debug("Captcha still present, retry %s/120", attempt + 1)

                if page.locator(
                    "h1#ddg-l10n-title:has-text('Checking your browser before accessing')"
                ).count() > 0:
                    raise TimeoutError("Captcha not solved within the time limit.")

            if response.status != 200:
                raise HTTPError(f"Failed to fetch page: {response.status}")

            page.wait_for_timeout(3000)
            return page.content()

        except (TimeoutError, HTTPError) as error:
            if check:
                logging.critical("Request to %s failed: %s", url, error)
                sys.exit(1)
            return None
        finally:
            context.close()
            browser.close()


def clear_screen() -> None:
    if not aniworld_globals.IS_DEBUG_MODE:
        if platform.system() == "Windows":
            os.system("cls")
        else:
            os.system("clear")


def clean_up_leftovers(directory: str) -> None:
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
    script_directory = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.name == 'nt':
        mpv_scripts_directory = os.path.join(
            os.environ.get('APPDATA', ''), 'mpv', 'scripts'
        )
    else:
        mpv_scripts_directory = os.path.expanduser('~/.config/mpv/scripts')

    if not os.path.exists(mpv_scripts_directory):
        os.makedirs(mpv_scripts_directory)

    skip_source_path = os.path.join(script_directory, 'aniskip', 'skip.lua')
    skip_destination_path = os.path.join(mpv_scripts_directory, 'skip.lua')

    if os.path.exists(skip_destination_path):
        with open(skip_source_path, 'r', encoding="utf-8") as source_file:
            source_content = source_file.read()

        with open(skip_destination_path, 'r', encoding="utf-8") as destination_file:
            destination_content = destination_file.read()

        if source_content != destination_content:
            logging.debug("Content differs, overwriting skip.lua")
            shutil.copy(skip_source_path, skip_destination_path)
        else:
            logging.debug("skip.lua already exists and is identical, no overwrite needed")
    else:
        logging.debug("Copying skip.lua to %s", mpv_scripts_directory)
        shutil.copy(skip_source_path, skip_destination_path)


def setup_autostart() -> None:
    logging.debug("Copying autostart.lua to mpv script directory")
    script_directory = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.name == 'nt':
        mpv_scripts_directory = os.path.join(
            os.environ.get('APPDATA', ''), 'mpv', 'scripts'
        )
    else:
        mpv_scripts_directory = os.path.expanduser('~/.config/mpv/scripts')

    if not os.path.exists(mpv_scripts_directory):
        os.makedirs(mpv_scripts_directory)

    autostart_source_path = os.path.join(script_directory, 'aniskip', 'autostart.lua')
    autostart_destination_path = os.path.join(mpv_scripts_directory, 'autostart.lua')

    if not os.path.exists(autostart_destination_path):
        logging.debug("Copying autostart.lua to %s", mpv_scripts_directory)
        shutil.copy(autostart_source_path, autostart_destination_path)


def setup_autoexit() -> None:
    logging.debug("Copying autoexit.lua to mpv script directory")
    script_directory = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.name == 'nt':
        mpv_scripts_directory = os.path.join(
            os.environ.get('APPDATA', ''), 'mpv', 'scripts'
        )
    else:
        mpv_scripts_directory = os.path.expanduser('~/.config/mpv/scripts')

    if not os.path.exists(mpv_scripts_directory):
        os.makedirs(mpv_scripts_directory)

    autoexit_source_path = os.path.join(script_directory, 'aniskip', 'autoexit.lua')
    autoexit_destination_path = os.path.join(mpv_scripts_directory, 'autoexit.lua')

    if not os.path.exists(autoexit_destination_path):
        logging.debug("Copying autoexit.lua to %s", mpv_scripts_directory)
        shutil.copy(autoexit_source_path, autoexit_destination_path)


def get_updated_command_for_mpv(command: List[str], appdata_path: str) -> List[str]:
    command_name = command[0]
    potential_path = os.path.join(appdata_path, command_name)
    if os.path.exists(potential_path):
        command[0] = os.path.join(potential_path, "mpv.exe")
        logging.debug("Updated command for mpv: %s", command)
    return command


def get_updated_command_for_syncplayconsole(command: List[str], appdata_path: str) -> List[str]:
    command_name = command[0]
    potential_path = os.path.join(appdata_path, command_name)
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
    return command


def get_updated_command_for_yt_dlp(command: List[str], appdata_path: str) -> List[str]:
    command_name = command[0]
    potential_path = os.path.join(appdata_path, command_name)
    if os.path.exists(potential_path):
        command[0] = os.path.join(potential_path, "yt-dlp.exe")
        logging.debug("Updated command for yt-dlp: %s", command)
    return command


def execute_command(command: List[str], only_command: bool) -> None:
    logging.debug("Initial command: %s", command)

    if platform.system() == "Windows":
        appdata_path = os.path.join(os.getenv('APPDATA'), 'aniworld')
        logging.debug("AppData path: %s", appdata_path)

        if os.path.exists(appdata_path):
            command_name = command[0]

            if command_name == "mpv":
                command = get_updated_command_for_mpv(command, appdata_path)
            elif command_name == "SyncplayConsole":
                command = get_updated_command_for_syncplayconsole(command, appdata_path)
            elif command_name == "yt-dlp":
                command = get_updated_command_for_yt_dlp(command, appdata_path)

    if only_command:
        command_str = ' '.join(shlex.quote(arg) for arg in command)
        logging.debug("Only command mode: %s", command_str)
        print(command_str)
    else:
        logging.debug("Executing command: %s", command)
        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError as e:
            logging.critical(e)


def raise_runtime_error(message: str) -> None:
    raise RuntimeError(message)


def get_season_episode_count(slug: str, season: str) -> int:
    series_url = f"https://aniworld.to/anime/stream/{slug}/staffel-{season}"

    response = requests.get(series_url, timeout=15)
    soup = BeautifulSoup(response.content, 'html.parser')
    episode_numbers = []
    counter = 1
    while True:
        target = f"{slug}/staffel-{season}/episode-{counter}"

        matching_links = []
        for link in soup.find_all('a', href=True):
            if target in link['href']:
                matching_links.append(link['href'])
        if matching_links:
            episode_numbers.append(counter)
            counter += 1
        else:
            break

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
    movie_url = f"https://aniworld.to/anime/stream/{slug}/filme"
    season_html = fetch_url_content(movie_url)
    if season_html is None:
        return 0
    soup = BeautifulSoup(season_html, 'html.parser')

    movie_numbers = []
    counter = 1
    while True:
        target = f"{slug}/filme/film-{counter}"

        matching_links = []
        for link in soup.find_all('a', href=True):
            if target in link['href']:
                matching_links.append(link['href'])
        if matching_links:
            movie_numbers.append(counter)
            counter += 1
        else:
            break

    return max(movie_numbers) if movie_numbers else 0


def get_season_data(anime_slug: str):
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
        movie_number = re.findall(r'film-(\d+)', episode_url)
        season_episode = 0, int(movie_number[0]) if movie_number else 1
    else:
        logging.error("URL format not recognized: %s", episode_url)
        raise ValueError("URL format not recognized")
    logging.debug("Extracted season and episode numbers: %s", season_episode)
    return season_episode


def ftoi(value: float) -> str:
    return str(int(value * 1000))


def get_version():
    try:
        __version__ = version("aniworld")
    except PackageNotFoundError:
        __version__ = "0.0.0"

    return f" v.{__version__}"


def get_latest_github_version():
    repo = "phoenixthrush/aniworld-downloader"
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"

    try:
        response_content = fetch_url_content(api_url, check=False)
        if not response_content:
            logging.error("Failed to fetch latest release from %s", repo)
            return ""

        release_data = json.loads(response_content)
        latest_version = release_data.get('tag_name', '')
        logging.debug("Latest GitHub version: %s", latest_version)
        return latest_version
    except json.JSONDecodeError as e:
        logging.error("Error decoding JSON response from %s: %s", repo, e)
    except requests.exceptions.RequestException as e:
        logging.error("Unexpected error fetching latest release from %s: %s", repo, e)
    return ""


def is_version_outdated():
    current_version = get_version()
    latest_version = get_latest_github_version()

    if not current_version or not latest_version:
        logging.error("Could not determine version information.")
        return False

    current_version = Version(current_version.strip().lstrip('v').lstrip('.'))
    latest_version = Version(latest_version.strip().lstrip('v').lstrip('.'))

    logging.debug("Current version: %s, Latest version: %s", current_version, latest_version)

    return current_version < latest_version


def get_language_code(language: str) -> str:
    logging.debug("Getting language code for: %s", language)
    return {
        "German Dub": "1",
        "English Sub": "2",
        "German Sub": "3"
    }.get(language, "")


def get_language_string(lang_key: int) -> str:
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
    logging.debug("Dependencies to download: %s", dependencies)

    if platform.system() == "Linux" or platform.system() == "Darwin":
        logging.debug("Installing using Package-Manager...!")
        install_packages(get_package_manager(), dependencies)
        return

    if platform.system() != "Windows":
        logging.debug("Not on Windows, skipping dependency download.")
        return

    dependencies = [dep for dep in dependencies if not shutil.which(dep)]
    if not dependencies:
        logging.debug("All required dependencies are already in PATH. No downloads needed.")
        return

    appdata_path = os.path.join(os.getenv('APPDATA'), 'aniworld')
    logging.debug("Creating appdata path: %s", appdata_path)
    os.makedirs(appdata_path, exist_ok=True)

    for dep in dependencies:
        dep_path = os.path.join(appdata_path, dep)
        if os.path.exists(dep_path):
            logging.debug("%s already exists. Skipping download.", dep_path)
            continue

        logging.debug("Creating directory for %s at %s", dep, dep_path)
        os.makedirs(dep_path, exist_ok=True)
        download_and_extract_dependency(dep, dep_path, appdata_path)

    logging.debug("Windows dependencies downloaded.")


def download_and_extract_dependency(dep: str, dep_path: str, appdata_path: str):
    if dep == 'mpv':
        if platform.system() == "Windows":
            logging.debug("Downloading mpv...")
            print_progress_info("Downloading mpv...")
        else:
            logging.info("Downloading mpv...")
        download_mpv(dep_path, appdata_path)
    elif dep == 'syncplay':
        if platform.system() == "Windows":
            logging.debug("Downloading Syncplay...")
            print_progress_info("Downloading Syncplay...")
        else:
            logging.info("Downloading Syncplay...")
        download_syncplay(dep_path)
    elif dep == 'yt-dlp':
        if platform.system() == "Windows":
            logging.debug("Downloading yt-dlp...")
            print_progress_info("Downloading yt-dlp...")
        else:
            logging.info("Downloading yt-dlp...")
        download_yt_dlp(dep_path)


def download_mpv(dep_path: str, appdata_path: str):
    direct_links = get_github_release("shinchiro/mpv-winbuild-cmake")
    try:
        logging.debug("Checking for AVX2 support...")
        avx2_supported = check_avx2_support()
        if avx2_supported:
            logging.debug("AVX2 is supported.")
        else:
            logging.debug("AVX2 is not supported.")
    except Exception:  # pylint: disable=broad-exception-caught  # TODO explicitly specify
        logging.debug("Exception while checking for avx2, defaulting support to False.")
        avx2_supported = False
    pattern = r'mpv-x86_64-\d{8}-git-[a-f0-9]{7}\.7z'
    if avx2_supported:
        logging.debug("AVX2 is supported, using mpv v3.")
        pattern = r'mpv-x86_64-v3-\d{8}-git-[a-f0-9]{7}\.7z'
    else:
        logging.debug("AVX2 is not supported.")

    logging.debug("Downloading %s", pattern)

    direct_link = next(
        (link for name, link in direct_links.items()
         if re.match(pattern, name)),
        None
    )

    logging.debug("Direct link: %s", direct_link)

    if not direct_link:
        logging.error("No download link found for MPV. Please download it manually.")
        return
    logging.debug(direct_link)

    zip_path = os.path.join(appdata_path, 'mpv.7z')
    logging.debug("Downloading MPV from %s to %s", direct_link, zip_path)
    url_content = fetch_url_content(direct_link)

    logging.debug("Saving url content.")
    with open(zip_path, 'wb') as f:
        f.write(url_content)

    logging.debug("Unpacking %s to %s", zip_path, dep_path)
    with py7zr.SevenZipFile(zip_path, mode='r') as archive:
        archive.extractall(path=dep_path)

    logging.debug("Removing %s after unpacking", zip_path)
    os.remove(zip_path)


def download_syncplay(dep_path: str):
    logging.debug("Getting latest syncplay direct link.")
    direct_links = get_github_release("Syncplay/syncplay")
    direct_link = next(
        (link for name, link in direct_links.items()
         if re.match(r'Syncplay_\d+\.\d+\.\d+_Portable\.zip', name)),
        None
    )
    if not direct_link:
        logging.error("No download link found for Syncplay. Please install it manually.")
        return
    logging.debug(direct_link)

    exe_path = os.path.join(dep_path, 'syncplay.zip')
    logging.debug("Downloading Syncplay from %s to %s", direct_link, exe_path)
    url_content = fetch_url_content(direct_link)
    with open(exe_path, 'wb') as f:
        f.write(url_content)

    logging.debug("Unpacking %s to %s", exe_path, dep_path)
    shutil.unpack_archive(exe_path, dep_path)

    logging.debug("Removing %s after unpacking", exe_path)
    os.remove(exe_path)


def download_yt_dlp(dep_path: str):
    url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
    exe_path = os.path.join(dep_path, 'yt-dlp.exe')

    logging.debug("Downloading yt-dlp from %s to %s", url, exe_path)
    url_content = fetch_url_content(url)

    logging.debug("Saving url content.")
    with open(exe_path, 'wb') as f:
        f.write(url_content)


def is_tail_running():
    try:
        result = subprocess.run(
            ["sh", "-c", "ps aux | grep 'tail -f.*/aniworld.log' | grep -v grep"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False  # TODO fix on MacOS
        )
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        logging.error("CalledProcessError checking if tail is running: %s", e)
        return False
    except subprocess.SubprocessError as e:
        logging.error("SubprocessError checking if tail is running: %s", e)
        return False


def check_avx2_support() -> bool:
    if platform.system() != "Windows":
        logging.debug("AVX2 check is only supported on Windows, defaulting to False.")
        return False

    try:
        if shutil.which("wmic"):
            logging.debug("wmic is in path.")
            cpu_info = subprocess.run(
                ['wmic', 'cpu', 'get',
                 'Caption, Architecture, DataWidth, Manufacturer, ProcessorType, Status'],
                capture_output=True, text=True, check=False
            )
            logging.debug("CPU Info: %s", cpu_info.stdout.decode('utf-8', errors='replace'))
            if 'avx2' in cpu_info.stdout.decode('utf-8', errors='replace').lower():
                logging.debug("AVX2 is supported.")
                return True
        else:
            logging.debug("wmic is not in path, defaulting to False.")
        return False
    except subprocess.CalledProcessError as e:
        logging.error("Error checking AVX2 support, defaulting to False.: %s", e)
        return False
    except subprocess.SubprocessError as e:
        logging.error("Subprocess error checking AVX2 support, defaulting to False.: %s", e)
        return False


def remove_path(path):
    try:
        if os.path.isfile(path):
            logging.debug("Removing file: %s", path)
            os.remove(path)
        elif os.path.isdir(path):
            logging.debug("Removing directory: %s", path)
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
            msg = f"Anime4K: Current mode is already set to {mode}. No changes made."
            print(msg)
            logging.debug(msg)
            sys.exit()

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
        print("Anime4K: Uninstalled.")
        sys.exit()

    download_anime4k(mode)
    set_anime4k_config(mode)

    print(f"Anime4K: Installed using mode: {mode}.")
    sys.exit()


def process_episode_file_line(line: str) -> tuple:
    if "https://aniworld.to/anime/stream/" in line:
        if "/staffel-" in line and "/episode-" in line:
            slug = line.split('/')[5]
            return [line], slug
        if "/staffel-" in line:
            return get_season_episodes(line), line.split('/')[-2]

        slug = line.split('/')[-1]
        return list(get_season_data(slug)), slug

    return [], None


def read_episode_file(file: str) -> dict:
    animes = {}

    try:
        with open(file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                episode, slug = process_episode_file_line(line)
                if episode:
                    if slug not in animes:
                        animes[slug] = []
                    animes[slug].extend(episode)
    except FileNotFoundError:
        msg = "The specified episode file was not found!"
        logging.debug(msg)
        print(msg)

    return animes


def check_package_installation(package_name: str = "aniworld"):
    site_packages = next(p for p in sys.path if 'site-packages' in p)

    package_path = pathlib.Path(site_packages) / package_name
    git_path = package_path / "../../../../.git"

    if git_path.exists():
        return "clone"

    dist_info_path = pathlib.Path(site_packages) / f"{package_name}-*.dist-info"
    dist_info_dirs = list(dist_info_path.parent.glob(f"{package_name}-*.dist-info"))

    if dist_info_dirs:
        direct_url_file = dist_info_dirs[0] / "direct_url.json"
        if direct_url_file.exists():
            return "git"

    return "pypi"


def remove_files(paths):
    for path in paths:
        try:
            if os.path.isfile(path):
                os.remove(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
        except OSError as e:
            print(f"Error removing {path}: {e}")


def get_uninstall_paths():
    base_path = (
        os.getenv('APPDATA') if platform.system() == "Windows"
        else os.path.expanduser("~/.config/mpv")
    )

    config_dir = (
        os.path.expanduser("~/.aniworld") if platform.system() != "Windows"
        else os.path.join(os.getenv('APPDATA'), "aniworld")
    )

    return [
        os.path.join(base_path, "scripts", "autoexit.lua"),
        os.path.join(base_path, "scripts", "autostart.lua"),
        os.path.join(base_path, "scripts", "skip.lua"),
        os.path.join(base_path, "input.conf"),
        os.path.join(base_path, "mpv.conf"),
        os.path.join(base_path, "shaders"),
        config_dir,
    ]


def execute_detached_command_windows(command):
    subprocess.Popen(  # pylint: disable=consider-using-with
        f'timeout 3 >nul & {" ".join(command)}',
        shell=True,
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )


def uninstall_aniworld():
    if shutil.which("pip"):
        command = ["pip", "uninstall", "aniworld", "-y"]

        if platform.system() == "Windows":
            execute_detached_command_windows(command)
        else:
            execute_command(command, only_command=False)


def self_uninstall():
    paths = get_uninstall_paths()

    logging.debug("Removed Files:\n%s", paths)
    remove_files(paths)

    logging.debug("Uninstalling using pip.")
    print("Uninstalling, please wait up to 3 seconds...")
    uninstall_aniworld()
    sys.exit()


def get_component_paths():
    base_path = (
        os.path.join(os.getenv('APPDATA'), "aniworld")
        if platform.system() == "Windows"
        else os.path.expanduser("~/.aniworld")
    )

    return {
        "mpv": os.path.join(base_path, "mpv"),
        "yt-dlp": os.path.join(base_path, "yt-dlp"),
        "syncplay": os.path.join(base_path, "syncplay")
    }


def update_component(component: str):
    paths = get_component_paths()

    components = ["mpv", "yt-dlp", "syncplay"] if component == "all" else [component]

    for comp in components:
        remove_path(paths[comp])
        logging.debug("Removed: %s", comp)
        logging.debug("Downloading component: %s", comp)
        download_dependencies([comp])
        if not platform.system() == "Darwin":
            print(f"Installed latest {comp} version.")


def print_progress_info(msg: str):
    command = f"""cmd /c echo {msg.replace('"', "'")} """
    execute_command(command, only_command=False)


def get_anime_season_title(slug: str, season: int) -> str:
    # TODO this should be replaced with a logic for the actual name for each season using api
    # this will also be called for each season but for now once
    logging.debug("Fetching %s season %s name", slug, season)

    season_html = fetch_url_content(f"https://aniworld.to/anime/stream/{slug}/staffel-{season}")

    if not season_html:
        logging.error("Failed to fetch content for %s season %s", slug, season)
        return slug.replace("-", " ").title()

    soup = BeautifulSoup(season_html, 'html.parser')

    series_div = soup.find('div', class_='series-title')

    if series_div:
        name = series_div.find('h1').find('span').text
    else:
        logging.warning("No series title found for %s season %s, using slug instead", slug, season)
        name = slug.replace("-", " ").title()

    logging.debug("Anime season title: %s", name)

    return name


def countdown():
    try:
        msg = "You now have 3 seconds to press CTRL+C to exit!"
        if not platform.system() == "Windows":
            print(msg)
        else:
            print_progress_info(msg)
        time.sleep(3)
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit()


def sanitize_path(path):
    invalid_chars = r'\/:*?"<>|&'

    translation_table = str.maketrans('', '', invalid_chars)

    sanitized_path = path.translate(translation_table)

    return sanitized_path


def get_package_manager():
    try:
        system = platform.system()
        package_manager = 'unknown'

        if system == "Darwin":
            package_manager = 'brew' if shutil.which("brew") else 'unknown'

        if os.path.exists('/etc/os-release'):
            with open('/etc/os-release', encoding='utf-8') as f:
                os_release_info = f.read().lower()

            if 'arch' in os_release_info:
                package_manager = 'pacman'
            if 'ubuntu' in os_release_info or 'debian' in os_release_info:
                package_manager = 'apt'
            if 'fedora' in os_release_info:
                package_manager = 'dnf'
            if 'centos' in os_release_info or 'rhel' in os_release_info:
                package_manager = 'yum'
            if 'gentoo' in os_release_info:
                package_manager = 'emerge'
            if 'opensuse' in os_release_info:
                package_manager = 'zypper'
            if 'alpine' in os_release_info:
                package_manager = 'apk'

        return package_manager

    except FileNotFoundError as e:
        return f'Error: {e}'
    except PermissionError as e:
        return f'Error: {e}'


def install_packages(package_manager, packages):
    try:
        if package_manager == 'pacman':
            subprocess.run(
                ['pkexec', 'pacman', '-S', '--noconfirm'] + packages,
                stdout=subprocess.DEVNULL,
                check=False
            )
        elif package_manager == 'apt':
            subprocess.run(
                ['pkexec', 'apt-get', 'install', '-y'] + packages,
                stdout=subprocess.DEVNULL,
                check=False
            )
        elif package_manager == 'dnf':
            subprocess.run(
                ['pkexec', 'dnf', 'install', '-y'] + packages,
                stdout=subprocess.DEVNULL,
                check=False
            )
        elif package_manager == 'yum':
            subprocess.run(
                ['pkexec', 'yum', 'install', '-y'] + packages,
                stdout=subprocess.DEVNULL,
                check=False
            )
        elif package_manager == 'emerge':
            subprocess.run(
                ['pkexec', 'emerge'] + packages,
                stdout=subprocess.DEVNULL,
                check=False
            )
        elif package_manager == 'zypper':
            subprocess.run(
                ['pkexec', 'zypper', 'install', '-y'] + packages,
                stdout=subprocess.DEVNULL,
                check=False
            )
        elif package_manager == 'apk':
            subprocess.run(
                ['pkexec', 'apk', 'add'] + packages,
                stdout=subprocess.DEVNULL,
                check=False
            )
        elif package_manager == 'brew':
            msg = (
                f'Please update "{packages[0]}" manually as it is not currently '
                'supported yet on MacOS!'
            )
            logging.debug(msg)
            print(msg)
        else:
            print(f'Package manager "{package_manager}" not supported or unknown.')
    except subprocess.SubprocessError as e:
        print(f'Error while installing: {e}')


def open_terminal_with_command(command):
    terminal_emulators = [
        ('gnome-terminal', ['gnome-terminal', '--', 'bash', '-c', f'{command}; exec bash']),
        ('xterm', ['xterm', '-hold', '-e', command]),
        ('konsole', ['konsole', '--hold', '-e', command])
    ]

    for terminal, cmd in terminal_emulators:
        try:
            subprocess.Popen(cmd)  # pylint: disable=consider-using-with
            return
        except FileNotFoundError:
            logging.debug("%s not found, trying the next option.", terminal)
        except subprocess.SubprocessError as e:
            logging.error("Error opening terminal with %s: %e", terminal, e)

    logging.error(
        "No supported terminal emulator found. "
        "Please install gnome-terminal, xterm, or konsole."
    )


def get_random_anime(genre: str) -> str:
    url = 'https://aniworld.to/ajax/randomGeneratorSeries'
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Accept': '*/*',
        'Sec-Fetch-Site': 'same-origin',
        'Accept-Language': 'en-GB,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Sec-Fetch-Mode': 'cors',
        'Origin': 'https://aniworld.to',
        'User-Agent': aniworld_globals.DEFAULT_USER_AGENT,
        'Referer': 'https://aniworld.to/random',
        'X-Requested-With': 'XMLHttpRequest',
    }
    data = {
        'productionStart': 'all',
        'productionEnd': 'all',
        'genres[]': genre
    }

    response = requests.post(url, headers=headers, data=data, timeout=15)
    logging.debug("Response Status Code: %s", response.status_code)
    logging.debug("Response Text: %s", response.text)

    try:
        anime_list = json.loads(response.text)
        logging.debug("Anime List: %s", anime_list)
    except json.JSONDecodeError as e:
        logging.error("JSON Decode Error: %s", e)
        return None

    try:
        random_anime = random.choice(anime_list)
        logging.debug("Selected Anime: %s", random_anime)
    except (IndexError, TypeError):
        logging.warning("No anime found in the list using this genre: %s.", genre)
        return None

    name = random_anime['name']
    link = random_anime['link']

    logging.debug("Random Anime: %s", name)
    logging.debug("Link: https://aniworld.to/%s", link)

    return link


def check_internet_connection():
    # return False  # debug
    # offline mini game coming soon!

    try:
        socket.create_connection(("github.com", 80), timeout=5)
        return True
    except OSError:
        pass

    try:
        socket.create_connection(("1.1.1.1", 53), timeout=5)
        return True
    except OSError:
        pass

    try:
        socket.create_connection(("8.8.8.8", 53), timeout=5)
        return True
    except OSError:
        pass

    return False


def get_windows_messagebox_response(message, title, box_type):
    import ctypes  # pylint: disable=import-outside-toplevel
    msg_box_type = {
        "info": 0x40,
        "yesno": 0x04 | 0x20,
        "warning": 0x30,
        "error": 0x10,
    }.get(box_type, 0x40)

    response = ctypes.windll.user32.MessageBoxW(0, message, title, msg_box_type)
    return response == 6 if box_type == "yesno" else True


def get_darwin_messagebox_response(message, title, box_type):
    script = {
        "info": (
            f'display dialog "{message}" with title "{title}" buttons "OK"'
        ),
        "yesno": (
            f'display dialog "{message}" with title "{title}" '
            'buttons {"Yes", "No"}'
        ),
        "warning": (
            f'display dialog "{message}" with title "{title}" '
            'buttons "OK" with icon caution'
        ),
        "error": (
            f'display dialog "{message}" with title "{title}" '
            'buttons "OK" with icon stop'
        ),
    }.get(box_type, (
        f'display dialog "{message}" with title "{title}" buttons "OK"'
    ))

    try:
        result_obj = subprocess.run(
            ["osascript", "-e", script],
            text=True,
            capture_output=True,
            check=False
        )
        return "Yes" in result_obj.stdout if box_type == "yesno" else True
    except subprocess.SubprocessError as e:
        logging.debug("Error showing messagebox on macOS: %s", e)
        return False


def get_linux_messagebox_response(message, title, box_type):
    dialog_program = "zenity" if subprocess.run(
        ["which", "zenity"], capture_output=True, text=True, check=False
    ).returncode == 0 else "kdialog"

    cmd = {
        "zenity": {
            "info": ["zenity", "--info", "--text", message, "--title", title],
            "yesno": ["zenity", "--question", "--text", message, "--title", title],
            "warning": ["zenity", "--warning", "--text", message, "--title", title],
            "error": ["zenity", "--error", "--text", message, "--title", title],
        },
        "kdialog": {
            "info": ["kdialog", "--msgbox", message, "--title", title],
            "yesno": ["kdialog", "--yesno", message, "--title", title],
            "warning": ["kdialog", "--sorry", message, "--title", title],
            "error": ["kdialog", "--error", message, "--title", title],
        }
    }

    cmd = cmd[dialog_program].get(
        box_type,
        [
            "zenity",
            "--info",
            "--text",
            message,
            "--title",
            title
        ]
    )

    try:
        result_obj = subprocess.run(cmd, check=False)
        return (result_obj.returncode == 0) if box_type == "yesno" else True
    except subprocess.SubprocessError as e:
        logging.debug("Error showing messagebox on Linux: %s", e)
        return False


def get_tkinter_messagebox_response(message, title, box_type):
    import tkinter as tk  # pylint: disable=import-outside-toplevel
    from tkinter import messagebox  # pylint: disable=import-outside-toplevel
    root = tk.Tk()
    root.withdraw()

    if box_type == "yesno":
        return messagebox.askyesno(title, message)
    if box_type == "warning":
        messagebox.showwarning(title, message)
    elif box_type == "error":
        messagebox.showerror(title, message)
    else:
        messagebox.showinfo(title, message)
    return True


def show_messagebox(message, title="Message", box_type="info"):
    system = platform.system()

    if system == "Windows":
        return get_windows_messagebox_response(message, title, box_type)

    if system == "Darwin":
        return get_darwin_messagebox_response(message, title, box_type)

    if system == "Linux":
        return get_linux_messagebox_response(message, title, box_type)

    # Fallback for unsupported systems
    return get_tkinter_messagebox_response(message, title, box_type)


def get_current_wallpaper():
    system = platform.system()

    if system == "Windows":
        import ctypes  # pylint: disable=import-outside-toplevel
        buf = ctypes.create_unicode_buffer(512)
        ctypes.windll.user32.SystemParametersInfoW(0x73, len(buf), buf, 0)
        return buf.value

    if system == "Darwin":
        result = os.popen(
            'osascript -e \'tell application "System Events" to '
            'get the picture of the current desktop\''
        ).read().strip()

        if not result:
            result = os.popen(
                'osascript -e \'tell application "System Events" to get the desktop picture\''
            ).read().strip()
        return result

    if system == "Linux":
        try:
            result = os.popen(
                'gsettings get org.gnome.desktop.background picture-uri'
            ).read().strip().strip("'").replace("file://", "")
            return result
        except OSError as e:
            print(f"Could not get current wallpaper: {e}")
            return None

    return None


def set_wallpaper_fit(image_path):
    try:
        import winreg  # pylint: disable=import-error, import-outside-toplevel
        import ctypes  # pylint: disable=import-error, import-outside-toplevel
    except ModuleNotFoundError as e:
        raise ImportError(
            "Required modules (winreg, ctypes) not found. "
            "Ensure you're on Windows."
        ) from e

    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        "Control Panel\\Desktop",
        0,
        winreg.KEY_SET_VALUE
    )
    winreg.SetValueEx(key, "WallpaperStyle", 0, winreg.REG_SZ, "6")
    winreg.SetValueEx(key, "TileWallpaper", 0, winreg.REG_SZ, "0")
    winreg.CloseKey(key)

    ctypes.windll.user32.SystemParametersInfoW(20, 0, image_path, 3)


def set_wallpaper(image_path):
    system = platform.system()
    if system == "Windows":
        set_wallpaper_fit(image_path)
    elif system == "Darwin":
        os.system(
            f'osascript -e \'tell application "System Events" to '
            f'set picture of every desktop to "{image_path}"\''
        )
    elif system == "Linux":
        subprocess.call([
            "gsettings",
            "set",
            "org.gnome.desktop.background",
            "picture-uri",
            f"file://{image_path}"
        ])


def minimize_all_windows():
    if platform.system() == "Windows":
        import ctypes  # pylint: disable=import-outside-toplevel
        ctypes.windll.user32.keybd_event(0x5B, 0, 0, 0)  # Press Windows key
        ctypes.windll.user32.keybd_event(0x44, 0, 0, 0)  # Press 'D' key
        ctypes.windll.user32.keybd_event(0x44, 0, 2, 0)  # Release 'D' key
        ctypes.windll.user32.keybd_event(0x5B, 0, 2, 0)  # Release Windows key
    elif platform.system() == "Linux":
        try:
            subprocess.run(["wmctrl", "-k", "on"], check=False)
        except subprocess.SubprocessError as e:
            logging.debug("Error minimizing windows: %s", e)


def show_all_windows():
    if platform.system() == "Linux":
        try:
            subprocess.run(["wmctrl", "-k", "off"], check=True)
        except subprocess.CalledProcessError as e:
            logging.debug("Subprocess error while minimizing windows: %s", e)
        except FileNotFoundError as e:
            logging.debug("wmctrl not found, ensure it's installed: %s", e)


def set_temp_wallpaper():
    # TODO - if no old background set use default windows background
    data = ("aHR0cHM6Ly9naXRodWIuY29tL3Bob2VuaXh0aHJ1c2gvTWFnaWMtRW5naW5l"
            "L2Jsb2IvbWFzdGVyL2xpYnJhcnkvZG9ub3RkZWxldGUucG5nP3Jhdz10cnVl")

    current_wallpaper = get_current_wallpaper()
    logging.debug("Current wallpaper: %s", current_wallpaper)

    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = os.path.join(temp_dir, 'wallpaper.png')

        try:
            response = requests.get(base64.b64decode(data), timeout=15)
            response.raise_for_status()

            with open(file_path, 'wb') as f:
                f.write(response.content)

            set_wallpaper(file_path)
            logging.debug("New wallpaper set: %s", file_path)

            minimize_all_windows()
            if platform.system() == "Darwin":
                show_messagebox(
                    "DO NOT LOOK AT YOUR DESKTOP!\n(DO NOT PRESS FN + F11!!!)",
                    "IMPORTANT!!!",
                    "info"
                )
            elif platform.system() == "Linux":
                time.sleep(5)
                show_all_windows()
            else:
                time.sleep(5)
                minimize_all_windows()

            if current_wallpaper:
                set_wallpaper(current_wallpaper)
                logging.debug("Reverted to original wallpaper: %s", current_wallpaper)
        except requests.RequestException as e:
            logging.debug("Failed to download the wallpaper: %s", e)


def fetch_anime_id(anime_title, season):
    def clean_anime_title(title):
        name = re.sub(r' \(\d+ episodes\)', '', title)
        return re.sub(r'\s+', '%20', name)

    def fetch_mal_data(keyword):
        response = requests.get(
            f"https://myanimelist.net/search/prefix.json?type=anime&keyword={keyword}",
            headers={"User-Agent": aniworld_globals.DEFAULT_USER_AGENT},
            timeout=10
        )
        return response.json() if response.status_code == 200 else None

    def find_best_match(mal_data):
        results = [
            entry for entry in mal_data['categories'][0]['items']
            if 'OVA' not in entry['name']
        ]

        return results[0] if results else None

    def fetch_next_season_id(anime_id):
        url = f"https://myanimelist.net/anime/{anime_id}"
        soup = BeautifulSoup(fetch_url_content(url), 'html.parser')

        sequel_div = soup.find(
            "div",
            string=lambda text: text and "Sequel" in text and "(TV)" in text
        )

        if sequel_div:
            title_div = sequel_div.find_next("div", class_="title")
            link_element = title_div.find("a") if title_div else None

            if link_element:
                match = re.search(r'/anime/(\d+)', link_element.get("href"))
                return match.group(1) if match else None

        return None

    logging.debug("Fetching MAL ID for: %s", anime_title)
    anime_id = None
    keyword = clean_anime_title(anime_title)

    mal_metadata = fetch_mal_data(keyword)
    if not mal_metadata:
        logging.debug("Failed to fetch MyAnimeList data.")
        return None

    best_match = find_best_match(mal_metadata)
    if best_match:
        anime_id = best_match['id']

    while season > 1 and anime_id:
        anime_id = fetch_next_season_id(anime_id)
        if not anime_id:
            logging.debug("Sequel (TV) not found")
            return None
        season -= 1

    return anime_id


def get_description(anime_slug: str):
    url = f"https://aniworld.to/anime/stream/{anime_slug}"

    page_content = fetch_url_content(url)
    soup = BeautifulSoup(page_content, 'html.parser')

    description = soup.find('p', class_='seri_des')['data-full-description']

    return description


def get_description_with_id(anime_title: str, season: int = 1):
    anime_id = fetch_anime_id(anime_title=anime_title, season=season)
    url = f"https://myanimelist.net/anime/{anime_id}"

    page_content = fetch_url_content(url)
    soup = BeautifulSoup(page_content, 'html.parser')
    description = soup.find('meta', property='og:description')['content']
    return description


def install_and_import(package):
    try:
        __import__(package)
    except ImportError:
        while True:
            print(f'The Package "{package}" is not installed!')
            user_input = input(
                f'Do you want me to run “pip install {package}” for you?  (Y|N) '
            ).upper()
            if user_input == "Y":
                print(f"{package} is installing...")
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                break
            if user_input == "N":
                sys.exit()
            else:
                clear_screen()
    finally:
        globals()[package] = __import__(package)


if __name__ == "__main__":
    pass
