import getpass
import subprocess
import logging

from aniworld.models import Anime
from aniworld.config import MPV_PATH, PROVIDER_HEADERS, SYNCPLAY_PATH
from aniworld.common import download_mpv, download_syncplay
from aniworld.aniskip import aniskip
from aniworld.parser import arguments


def syncplay(anime: Anime or None):
    download_mpv()
    download_syncplay()
    if anime is None:
        syncplay_local_file()
    else:
        for episode in anime:
            if arguments.only_direct_link:
                msg = f"{anime.title} - S{episode.season}E{episode.episode} - ({anime.language}):"
                print(msg)
                print(f"{episode.get_direct_link()}\n")
                continue

            if arguments.username:
                syncplay_username = arguments.username
            else:
                syncplay_username = getpass.getuser()

            if arguments.hostname:
                syncplay_hostname = arguments.hostname
            else:
                syncplay_hostname = "syncplay.pl:8997"

            if arguments.room:
                room_name = arguments.room
            else:
                room_name = episode.title_german

            command = [
                SYNCPLAY_PATH,
                "--no-gui",
                "--no-store",
                "--host", syncplay_hostname,
                "--room", room_name,
                "--name", syncplay_username,
                "--player-path", MPV_PATH,
                episode.get_direct_link(),
                "--",
                "--fs",
                f'--force-media-title="{episode.title_german}"'
            ]
            logging.debug("Executing command:\n%s", command)

            if arguments.password:
                command.append("--password")
                command.append(arguments.password)

            if anime.provider in PROVIDER_HEADERS:
                command.append(
                    f"--http-header-fields={PROVIDER_HEADERS[anime.provider]}")

            if anime.aniskip:
                build_flags = aniskip(
                    anime.title, episode.episode, episode.season)
                sanitized_build_flags = build_flags.split()
                command.append(sanitized_build_flags[0])
                command.append(sanitized_build_flags[1])

            if arguments.only_command:
                print(
                    f"\n{anime.title} - S{episode.season}E{episode.episode} - ({anime.language}):"
                )
                print(
                    f"{' '.join(str(item) if item is not None else '' for item in command)}"
                )
                continue

            try:
                subprocess.run(command, check=True)
            except (subprocess.CalledProcessError, TypeError):
                print(
                    "Error running command:\n"
                    f"{' '.join(str(item) if item is not None else '' for item in command)}"
                )


def syncplay_local_file():
    for file in arguments.local_episodes:
        if arguments.username:
            syncplay_username = arguments.username
        else:
            syncplay_username = getpass.getuser()

        if arguments.hostname:
            syncplay_hostname = arguments.hostname
        else:
            syncplay_hostname = "syncplay.pl:8997"

        if arguments.room:
            room_name = arguments.room
        else:
            room_name = file

        command = [
            SYNCPLAY_PATH,
            "--no-gui",
            "--no-store",
            "--host", syncplay_hostname,
            "--room", room_name,
            "--name", syncplay_username,
            "--player-path", MPV_PATH,
            file,
            "--",
            "--fs"
        ]
        logging.debug("Executing command:\n%s", command)

        if arguments.password:
            command.append("--password")
            command.append(arguments.password)

        if arguments.only_command:
            print(
                f"\n{file}:"
            )
            print(
                f"{' '.join(str(item) if item is not None else '' for item in command)}"
            )
            continue

        try:
            subprocess.run(command, check=True)
        except (subprocess.CalledProcessError, TypeError):
            print(
                "Error running command:\n"
                f"{' '.join(str(item) if item is not None else '' for item in command)}"
            )


if __name__ == '__main__':
    download_syncplay()
