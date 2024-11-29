from aniworld.models import Anime


def execute(anime_list: list[Anime]):
    for anime in anime_list:
        print(anime.title)
        for episode in anime:
            print(episode.title_english)
