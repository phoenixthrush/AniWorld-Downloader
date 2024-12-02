from aniworld.models import Anime
from aniworld.action import watch, download, syncplay


def execute(anime_list: list[Anime]):
    for anime in anime_list:
        print(anime)
        if anime.action == "Watch":
            watch(anime)
        elif anime.action == "Download":
            download(anime)
        elif anime.action == "Syncplay":
            syncplay(anime)
        else:
            raise ValueError("Invalid action specified for anime: {anime}")
