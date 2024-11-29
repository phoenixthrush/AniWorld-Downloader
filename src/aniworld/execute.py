from aniworld.models import Anime


def execute(anime: Anime):
    if anime.action != "Watch" or anime.action != "Download" or anime.action != "Syncplay":
        raise ValueError("Please specify a valid action ('Watch', 'Download', 'Syncplay').")

    print(anime.title)
