import subprocess
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

        if anime.provider in PROVIDER_HEADERS:
            command.append(f"--http-header-fields={PROVIDER_HEADERS[anime.provider]}")

        if anime.aniskip:
            build_flags = aniskip(anime.title, episode.episode, episode.season)
            command.append(build_flags)

        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError:
            print(f"Error running command: {' '.join(str(item) if item is not None else '' for item in command)}")
