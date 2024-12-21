import os
import subprocess

from aniworld.models import Anime
from aniworld.config import DEFAULT_DOWNLOAD_PATH


def download(anime: Anime):
    for episode in anime:
        output_file = f"{anime.title} - S{episode.season}E{episode.episode} - ({anime.language}).mp4"
        output_path = os.path.join(DEFAULT_DOWNLOAD_PATH, anime.title, output_file)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

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
            "Vidmoly": "Referer: https://vidmoly.to",
            "Doodstream": "Referer: https://dood.li/"
        }

        if anime.provider in headers:
            command.extend(["--add-header", headers[anime.provider]])

        try:
            print(f"Downloading to {output_path}...")
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError:
            print(f"Error running command: {' '.join(str(item) if item is not None else '' for item in command)}")
