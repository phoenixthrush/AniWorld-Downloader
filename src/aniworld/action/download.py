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
            episode.direct_link,
            "--fragment-retries", "infinite",
            "--concurrent-fragments", "4",
            "-o", output_path,
            "--quiet",
            "--no-warnings",
            "--progress"
        ]

        if anime.provider == "Vidmoly":
            command.append('--add-header')
            command.append('Referer: "https://vidmoly.to"')

        subprocess.run(command, check=False)
