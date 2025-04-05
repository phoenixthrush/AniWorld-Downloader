import getpass
import subprocess
import sys
import os
import re
import logging

import requests

from aniworld.models import Anime
from aniworld.config import MPV_PATH, PROVIDER_HEADERS, SYNCPLAY_PATH
from aniworld.common import get_github_release, download_mpv
from aniworld.aniskip import aniskip
from aniworld.parser import arguments


def syncplay(anime: Anime):
    download_mpv()
    download_syncplay()

    for episode in anime:
        if arguments.only_direct_link:
            msg = f"{anime.title} - S{episode.season}E{episode.episode} - ({anime.language}):"
            print(msg)
            print(f"{episode.get_direct_link()}\n")
            continue

        if arguments.username:
            syncplay_username = arguments.username
        else:
            syncplay_username = getpass.getuser()

        if arguments.hostname:
            syncplay_hostname = arguments.hostname
        else:
            syncplay_hostname = "syncplay.pl:8997"

        if arguments.room:
            room_name = arguments.room
        else:
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
            f'--force-media-title="{episode.title_german}"'
        ]
        logging.debug("Executing command:\n%s", command)

        if arguments.password:
            command.append("--password")
            command.append(arguments.password)

        if anime.provider in PROVIDER_HEADERS:
            command.append(
                f"--http-header-fields={PROVIDER_HEADERS[anime.provider]}")

        if anime.aniskip:
            build_flags = aniskip(anime.title, episode.episode, episode.season)
            sanitized_build_flags = build_flags.split()
            command.append(sanitized_build_flags[0])
            command.append(sanitized_build_flags[1])

        if arguments.only_command:
            print(
                f"\n{anime.title} - S{episode.season}E{episode.episode} - ({anime.language}):"
            )
            print(
                f"{' '.join(str(item) if item is not None else '' for item in command)}"
            )
            continue

        try:
            subprocess.run(command, check=True)
        except (subprocess.CalledProcessError, TypeError):
            print(
                "Error running command:\n"
                f"{' '.join(str(item) if item is not None else '' for item in command)}"
            )


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
        r = requests.get(direct_link, allow_redirects=True, timeout=15)
        with open(zip_path, 'wb') as file:
            file.write(r.content)

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
    except subprocess.SubprocessError as e:
        logging.error("An error occurred: %s", e)


if __name__ == '__main__':
    download_syncplay()
