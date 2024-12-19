import os
import subprocess

from aniworld.models import Anime
from aniworld.config import DEFAULT_DOWNLOAD_PATH


def download(anime: Anime):
    for episode in anime:
        # print(episode)
        output_file = f"S{episode.season}E{episode.episode}"
        output_path = os.path.join(DEFAULT_DOWNLOAD_PATH, anime.title, output_file)

        command = [
            "yt-dlp",
            f'"{episode.get_direct_link()}"',
            "--fragment-retries", "infinite",
            "--concurrent-fragments", "4",
            "-o", output_path,
            "--quiet",
            "--no-warnings",
            "--progress"
        ]

        headers = {
            "Vidmoly": 'Referer: "https://vidmoly.to"',
            "Doodstream": 'Referer: "https://dood.li/"'
        }

        if anime.provider in headers:
            command.extend(['--add-header', headers[anime.provider]])

        subprocess.run(command, check=False)
        # print(' '.join(str(item) if item is not None else '' for item in command))
