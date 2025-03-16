import getpass
import subprocess
import sys
import os
import re
import json
import logging

import requests

from aniworld.models import Anime
from aniworld.config import MPV_PATH, PROVIDER_HEADERS, SYNCPLAY_PATH


def syncplay(anime: Anime):
    for episode in anime:
        syncplay_username = getpass.getuser()
        syncplay_hostname = "syncplay.pl:8997"
        room_name = episode.title_german

        command = [
            SYNCPLAY_PATH,
            "--no-gui",
            "--no-store",
            "--host", syncplay_hostname,
            "--room", room_name,
            "--name", syncplay_username,
            "--player-path", MPV_PATH,
            episode.get_direct_link(),
            "--",
            "--fs",
            f"--force-media-title={episode.title_german}"
        ]

        if anime.provider in PROVIDER_HEADERS:
            command.append(
                f"--http-header-fields={PROVIDER_HEADERS[anime.provider]}")

        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError:
            print(
                f"Error running command: {' '.join(str(item) if item is not None else '' for item in command)}")


def download_syncplay(dep_path: str = None, appdata_path: str = None):
    if sys.platform == 'win32':
        if appdata_path is None:
            appdata_path = os.path.join(
                os.environ['USERPROFILE'], 'AppData', 'Roaming', 'aniworld')
        if dep_path is None:
            dep_path = os.path.join(appdata_path, "syncplay")
            os.makedirs(dep_path, exist_ok=True)

        executable_path = os.path.join(dep_path, 'SyncplayConsole.exe')
        zip_path = os.path.join(dep_path, 'syncplay.zip')

        if os.path.exists(executable_path):
            return
    else:
        return

    direct_links = get_github_release("Syncplay/syncplay")
    direct_link = next(
        (link for name, link in direct_links.items()
         if re.match(r'Syncplay_\d+\.\d+\.\d+_Portable\.zip', name)),
        None
    )

    if not os.path.exists(executable_path):
        print("Downloading Syncplay...")
        r = requests.get(direct_link, allow_redirects=True)
        open(zip_path, 'wb').write(r.content)

    logging.debug("Extracting Syncplay to %s", dep_path)
    try:
        subprocess.run(
            ["tar", "-xf", zip_path],
            check=True,
            cwd=dep_path
        )
    except subprocess.CalledProcessError as e:
        logging.error("Failed to extract files: %s", e)
    except FileNotFoundError:
        logging.error("7zr.exe not found at the specified path.")
    except Exception as e:
        logging.error("An unexpected error occurred: %s", e)


# import from common.py in future
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
    download_syncplay()
