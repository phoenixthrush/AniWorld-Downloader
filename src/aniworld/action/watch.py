from aniworld.models import Anime
from aniworld.config import MPV_PATH


def watch(anime: Anime):
    # TODO - check for mpv
    # TODO - add aniskip
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

        print(command)
