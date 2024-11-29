from aniworld.search import search_anime
from aniworld.models import Anime, Episode


REQUEST_TIMEOUT = 15


def main() -> None:
    try:
        slug = search_anime()

        episode = Episode(
            slug=slug,
            season=1,
            episode=1
        )

        episode2 = Episode(
            link="https://aniworld.to/anime/stream/kaguya-sama-love-is-war/staffel-1/episode-3"
        )

        episode3 = Episode(
            slug="alya-sometimes-hides-her-feelings-in-russian",
            season=1,
            episode=2
        )

        anime_list = Anime(episode_list=[episode, episode2, episode3])

        for anime in anime_list:
            print(anime.title)

    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
