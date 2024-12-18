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
            f'"{episode.direct_link}"',
            "--no-gui",
            "--no-store",
            "--host", f'"{syncplay_hostname}"',
            "--room", f'"{room_name}"',
            "--name", f'"{syncplay_username}"',
            "--player-path", f'"{MPV_PATH}"'
            # "--",
            # "--fs"
            # "--profile=fast",
            # "--hwdec=auto-safe",
            # "--fs",
            # "--video-sync=display-resample",
            # f'--force-media-title="{episode.title_german}"'
        ]

        headers = {
            "Vidmoly": 'Referer: "https://vidmoly.to"',
            "Doodstream": 'Referer: "https://dood.li/"'
        }

        if anime.provider in headers:
            command.extend(['--add-header', headers[anime.provider]])

        # subprocess.run(command, check=False)
        print(' '.join(command))
