from aniworld.models import Anime, Episode
from aniworld.parser import parse_arguments
from aniworld.search import search_anime
from aniworld.execute import execute


def main() -> None:
    try:
        arguments = parse_arguments()
        anime_list = []

        anime_list.extend(
            Anime(
                episode_list=[Episode(link=link, arguments=arguments)]
                if arguments.episode
                else [Episode(slug=search_anime(), season=1, episode=1, arguments=arguments)],
                arguments=arguments
            )
            for link in (arguments.episode or [None])
        )

        execute(anime_list=anime_list)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
