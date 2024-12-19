from aniworld.models import Anime, Episode
from aniworld.parser import parse_arguments
from aniworld.search import search_anime
from aniworld.execute import execute
from aniworld.menu import menu


def main() -> None:
    try:
        arguments = parse_arguments()

        if not arguments.episode:
            while True:
                try:
                    slug = search_anime()
                    break
                except ValueError:
                    continue

            anime = menu(arguments=arguments, slug=slug)
            execute(anime_list=[anime])
        else:
            anime_list = [
                Anime(
                    episode_list=[
                        Episode(
                            link=link,
                            _selected_provider="VOE",
                            _selected_language="German Sub"
                        ) if arguments.episode else Episode(
                            # yet defaults to season 1, episode 1
                            slug=search_anime(),
                            _selected_provider="VOE",
                            _selected_language="German Sub"
                        )
                    ]
                ) for link in (arguments.episode or [None])
            ]

            execute(anime_list=anime_list)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
