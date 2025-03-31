import subprocess
import logging

from aniworld.aniskip import aniskip
from aniworld.common import download_mpv
from aniworld.config import MPV_PATH, PROVIDER_HEADERS
from aniworld.models import Anime


def watch(anime: Anime):
    download_mpv()
    for episode in anime:
        if episode.has_movies and episode.season not in list(episode.season_episode_count.keys()):
            mpv_title = (
                f"{anime.title} - Movie {episode.episode} - "
                f"{episode.title_german}"
            )
        else:
            mpv_title = (
                f"{anime.title} - S{episode.season}E{episode.episode} - "
                f"{episode.title_german}"
            )

        command = [
            MPV_PATH,
            episode.get_direct_link(),
            "--fs",
            "--quiet",
            f'--force-media-title="{mpv_title}"'
        ]

        # print(anime.provider)
        # print(bool(anime.provider in PROVIDER_HEADERS))

        if anime.provider in PROVIDER_HEADERS:
            command.append(
                f"--http-header-fields={PROVIDER_HEADERS[anime.provider]}")

        if anime.aniskip:
            build_flags = aniskip(anime.title, episode.episode, episode.season)
            command.append(build_flags)

        try:
            subprocess.run(command, check=True, shell=False)
        except subprocess.CalledProcessError as e:
            logging.error(
                "Error running command: %s\nCommand: %s",
                e, ' '.join(
                    str(item) if item is not None else '' for item in command)
            )
