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

        if anime.provider == "Vidmoly":
            command.append('--add-header')
            command.append('Referer: "https://vidmoly.to"')

        if anime.provider == "Doodstream":
            command.append('--add-header')
            command.append('Referer: "https://dood.li/"')

        subprocess.run(command, check=False)
        print(' '.join(command))
