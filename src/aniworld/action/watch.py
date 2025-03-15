import subprocess
import logging
import platform
import shutil
import sys
import os
import re
import json

import requests

from aniworld.aniskip import aniskip
from aniworld.models import Anime
from aniworld.config import MPV_PATH, PROVIDER_HEADERS

def watch(anime: Anime):
    for episode in anime:
        if episode.has_movies and episode.season not in list(episode.season_episode_count.keys()):
            mpv_title = f"{anime.title} - Movie {episode.episode} - {episode.title_german}"
        else:
            mpv_title = f"{anime.title} - S{episode.season}E{episode.episode} - {episode.title_german}"

        command = [
            MPV_PATH,
            episode.get_direct_link(),
            "--fs",
            "--quiet",
            f"--force-media-title={mpv_title}"
        ]

        # print(anime.provider)
        # print(bool(anime.provider in PROVIDER_HEADERS))

        if anime.provider in PROVIDER_HEADERS:
            command.append(f"--http-header-fields={PROVIDER_HEADERS[anime.provider]}")

        if anime.aniskip:
            build_flags = aniskip(anime.title, episode.episode, episode.season)
            command.append(build_flags)

        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError:
            print(f"Error running command: {' '.join(str(item) if item is not None else '' for item in command)}")


def download_mpv(dep_path: str=None, appdata_path: str=None):
    if sys.platform == 'win32':
        if appdata_path is None:
            appdata_path = os.path.join(os.environ['USERPROFILE'], 'AppData', 'Roaming', 'aniworld')
        if dep_path is None:
            dep_path = os.path.join(appdata_path, "mpv")
            os.makedirs(dep_path, exist_ok=True)

        executable_path = os.path.join(dep_path, 'mpv.exe')
        zip_path = os.path.join(dep_path, 'mpv.7z')
        zip_tool = os.path.join(appdata_path, "7z", "7zr.exe")

        os.makedirs(os.path.dirname(zip_tool), exist_ok=True)

        if os.path.exists(executable_path):
            return
    else:
        return

    direct_links = get_github_release("shinchiro/mpv-winbuild-cmake")

    avx2_supported = check_avx2_support()

    pattern = r'mpv-x86_64-v3-\d{8}-git-[a-f0-9]{7}\.7z' if avx2_supported else r'mpv-x86_64-\d{8}-git-[a-f0-9]{7}\.7z'

    logging.debug("Downloading MPV using pattern: %s", pattern)
    direct_link = next(
        (link for name, link in direct_links.items() if re.match(pattern, name)), None
    )

    if not direct_link:
        logging.error(
            "No suitable MPV download link found. Please download manually."
        )
        return

    if not os.path.exists(zip_tool):
        print(f"Downloading 7z...")
        r = requests.get('https://7-zip.org/a/7zr.exe', allow_redirects=True)
        open(zip_tool, 'wb').write(r.content)

    if not os.path.exists(zip_path):
        logging.debug("Downloading MPV from %s to %s", direct_link, zip_path)
        try:
            print(f"Downloading MPV ({'without' if not avx2_supported else 'with'} AVX2)...")
            print(direct_link)
            r = requests.get(direct_link, allow_redirects=True)
            open(zip_path, 'wb').write(r.content)
        except requests.RequestException as e:
            logging.error("Failed to download MPV: %s", e)
            return

    logging.debug("Extracting MPV to %s", dep_path)
    try:
        subprocess.run(
            [zip_tool, "x", zip_path],
            check=True,
            cwd=dep_path
        )
    except subprocess.CalledProcessError as e:
        logging.error("Failed to extract files: %s", e)
    except FileNotFoundError:
        logging.error("7zr.exe not found at the specified path.")
    except Exception as e:
        logging.error("An unexpected error occurred: %s", e)

    # os.remove(zip_path)
    logging.debug("Download and extraction complete.")


# extremly unreliable lol
def check_avx2_support() -> bool:
    if platform.system() != "Windows":
        logging.debug("AVX2 check is only supported on Windows.")
        return False

    try:
        if shutil.which("wmic"):
            cpu_info = subprocess.run(
                ['wmic', 'cpu', 'get', 'Caption,InstructionSet'], capture_output=True, text=True, check=False
            )
            if 'avx2' in cpu_info.stdout.lower():
                return True
            else:
                logging.debug("AVX2 not found in CPU info.")
        else:
            logging.debug("wmic not found, unable to check AVX2 support.")
    except subprocess.SubprocessError as e:
        logging.error("Error checking AVX2 support: %s", e)

    try:
        registry_info = subprocess.run(
            ['reg', 'query', 'HKEY_LOCAL_MACHINE\\HARDWARE\\DESCRIPTION\\System\\CentralProcessor\\0', '/v', 'FeatureSet'],
            capture_output=True, text=True, check=False
        )
        if 'avx2' in registry_info.stdout.lower():
            return True
    except subprocess.SubprocessError as e:
        logging.error("Error checking AVX2 support via registry: %s", e)

    return False


def get_github_release(repo: str) -> dict:
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"

    try:
        response = requests.get(api_url)
        response.raise_for_status()
        release_data = response.json()
        return {asset['name']: asset['browser_download_url'] for asset in release_data.get('assets', [])}
    except (json.JSONDecodeError, requests.RequestException) as e:
        logging.error("Failed to fetch release data from GitHub: %s", e)
    return {}


if __name__ == '__main__':
    download_mpv()
