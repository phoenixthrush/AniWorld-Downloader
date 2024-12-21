import platform
import getpass
import subprocess

from aniworld.models import Anime
from aniworld.config import MPV_PATH


def syncplay(anime: Anime):
    for episode in anime:
        executable = "SyncplayConsole" if platform.system() == "Windows" else "syncplay"
        syncplay_username = getpass.getuser()
        syncplay_hostname = "syncplay.pl:8997"
        room_name = episode.title_german

        command = [
            executable,
            episode.get_direct_link(),
            "--no-gui",
            "--no-store",
            "--host", syncplay_hostname,
            "--room", room_name,
            "--name", syncplay_username,
            "--player-path", MPV_PATH,
            "--",
            "--fs",
            f"--force-media-title={episode.title_german}"
        ]

        headers = {
            "Vidmoly": "Referer: https://vidmoly.to",
            "Doodstream": "Referer: https://dood.li/"
        }

        if anime.provider in headers:
            command.extend(["--add-header", headers[anime.provider]])

        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError:
            print(f"Error running command: {' '.join(str(item) if item is not None else '' for item in command)}")
