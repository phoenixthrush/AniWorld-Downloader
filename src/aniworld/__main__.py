from aniworld.models import Anime, Episode
from aniworld.search import search_anime
from aniworld.execute import execute


def main() -> None:
    try:
        slug = search_anime()

        user_episode = Episode(
            slug=slug,
            season=1,
            episode=1
        )

        user_episode_2 = Episode(
            slug=slug,
            season=1,
            episode=2
        )

        kaguya_episode = Episode(
            link="https://aniworld.to/anime/stream/kaguya-sama-love-is-war/staffel-1/episode-3"
        )

        kaguya_episode2 = Episode(
            link="https://aniworld.to/anime/stream/kaguya-sama-love-is-war/staffel-1/episode-3"
        )

        kaguya_episode3 = Episode(
            link="https://aniworld.to/anime/stream/kaguya-sama-love-is-war/staffel-1/episode-3"
        )

        alya_episode = Episode(
            slug="alya-sometimes-hides-her-feelings-in-russian",
            season=1,
            episode=2
        )

        execute(
            anime_list=[
                Anime(episode_list=[user_episode, user_episode_2], ),
                Anime(episode_list=[kaguya_episode, kaguya_episode2, kaguya_episode3]),
                Anime(episode_list=[alya_episode])
            ]
        )

    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
