from aniworld.aniskip import aniskip
from aniworld.models import Anime
from aniworld.config import MPV_PATH


def watch(anime: Anime):
    # TODO - check for mpv
    for episode in anime:
        command = [
            MPV_PATH,
            "this-is-direct-link",
            "--fs",
            "--profile=fast",
            "--hwdec=auto-safe",
            "--video-sync=display-resample",
            "--quiet",
            "--really-quiet",
            f"--force-media-title={episode.title_german}"
        ]
        if anime.aniskip:
            build_flags = aniskip(anime.title, episode.episode, episode.season)
            command.append(build_flags)
        #if episode.provider == "Vidmoly":
            #command.insert(1, '--referrer="https://vidmoly.to"')

        print(command)
