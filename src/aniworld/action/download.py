import os
import subprocess

from aniworld.models import Anime
from aniworld.config import DEFAULT_DOWNLOAD_PATH


def download(anime: Anime):
    for episode in anime:
        output_file = f"S{episode.season}E{episode.episode}"
        output_path = os.path.join(DEFAULT_DOWNLOAD_PATH, anime.title, output_file)

        command = [
            "yt-dlp",
            episode.get_direct_link(),
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

        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError:
            print(f"Command failed: {' '.join(str(item) if item is not None else '' for item in command)}")
