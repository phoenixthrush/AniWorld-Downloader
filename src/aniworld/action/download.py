import os
import re
import subprocess

from aniworld.models import Anime
from aniworld.config import DEFAULT_DOWNLOAD_PATH, PROVIDER_HEADERS, INVALID_PATH_CHARS


def download(anime: Anime):
    for episode in anime:
        if anime.only_direct_link:
            msg = f"{anime.title} - S{episode.season}E{episode.episode} - ({anime.language}):"
            print(msg)
            print(f"{episode.get_direct_link()}\n")
            continue

        sanitized_anime_title = ''.join(
            char for char in anime.title if char not in INVALID_PATH_CHARS
        )
        output_file = (
            f"{sanitized_anime_title} - "
            f"S{episode.season}E{episode.episode} - "
            f"({anime.language}).mp4"
        )
        output_path = os.path.join(
            DEFAULT_DOWNLOAD_PATH, sanitized_anime_title, output_file
        )

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

        if anime.provider in PROVIDER_HEADERS:
            command.extend(["--add-header", PROVIDER_HEADERS[anime.provider]])

        if anime.only_command:
            msg = f"{anime.title} - S{episode.season}E{episode.episode} - ({anime.language}):"
            print(msg)
            print(f"{command}\n")
            continue

        try:
            print(f"Downloading to {output_path}...")
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError:
            print(
                "Error running command:\n"
                f"{' '.join(str(item) if item is not None else '' for item in command)}"
            )
        except KeyboardInterrupt:
            # directory containing the output_path
            output_dir = os.path.dirname(output_path)
            is_empty = True

            # delete all .part, .ytdl, or .part-Frag followed by any number in output_path
            for file_name in os.listdir(output_dir):
                if re.search(r'\.(part|ytdl|part-Frag\d+)$', file_name):
                    os.remove(os.path.join(output_dir, file_name))
                else:
                    is_empty = False

            # delete folder too if empty after
            if is_empty or not os.listdir(output_dir):
                os.rmdir(output_dir)
