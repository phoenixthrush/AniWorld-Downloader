import platform
import getpass
import subprocess

from aniworld.models import Anime
from aniworld.config import MPV_PATH, PROVIDER_HEADERS


def syncplay(anime: Anime):
    for episode in anime:
        executable = "SyncplayConsole" if platform.system() == "Windows" else "syncplay"
        syncplay_username = getpass.getuser()
        syncplay_hostname = "syncplay.pl:8997"
        room_name = episode.title_german

        command = [
            executable,
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
            command.append(f"--http-header-fields={PROVIDER_HEADERS[anime.provider]}")

        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError:
            print(f"Error running command: {' '.join(str(item) if item is not None else '' for item in command)}")
