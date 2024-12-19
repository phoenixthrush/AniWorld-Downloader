import subprocess
from aniworld.aniskip import aniskip
from aniworld.models import Anime
from aniworld.config import MPV_PATH


def watch(anime: Anime):
    for episode in anime:
        command = [
            MPV_PATH,
            f'"{episode.get_direct_link()}"',
            "--fs",
            "--quiet",
            f'--force-media-title="{episode.title_german}"'
        ]

        headers = {
            "Vidmoly": 'Referer: "https://vidmoly.to"',
            "Doodstream": 'Referer: "https://dood.li/"'
        }

        if anime.provider in headers:
            command.extend(['--add-header', headers[anime.provider]])

        if anime.aniskip:
            build_flags = aniskip(anime.title, episode.episode, episode.season)
            command.append(build_flags)

        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError:
            print(f"Error running command: {' '.join(str(item) if item is not None else '' for item in command)}")
