import subprocess

from aniworld.aniskip import aniskip
from aniworld.models import Anime
from aniworld.config import MPV_PATH


def watch(anime: Anime):
    # TODO - check for mpv
    for episode in anime:
        command = [
            MPV_PATH,
            episode.direct_link,
            "--fs",
            "--profile=fast",
            "--hwdec=auto-safe",
            "--video-sync=display-resample",
            "--quiet",
            "--really-quiet",
            f"--force-media-title={episode.title_german}"
        ]

        if anime.provider == "Vidmoly":
            command.append('--http-header-fields="Referer: https://vidmoly.to"')

        if anime.provider == "Doodstream":
            command.append('--http-header-fields="Referer: https://dood.li/"')

        if anime.aniskip:
            build_flags = aniskip(anime.title, episode.episode, episode.season)
            command.append(build_flags)

        subprocess.run(command, check=False)
