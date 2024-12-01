import platform
import getpass

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
            "--no-gui",
            "--no-store",
            "--host", syncplay_hostname,
            "--name", syncplay_username,
            "--room", room_name,
            "--player-path", MPV_PATH,
            "this-is-direct-link",
            "--",
            "--profile=fast",
            "--hwdec=auto-safe",
            "--fs",
            "--video-sync=display-resample",
            f"--force-media-title={episode.title_german}"
        ]

        if anime.provider == "Vidmoly":
            command.append('--add-header')
            command.append('Referer: "https://vidmoly.to"')

        print(command)
