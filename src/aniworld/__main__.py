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
            # TODO: this needs to pass all links to a function
            #       that will return Anime objects instead
            anime_list = []
            for link in (arguments.episode or [None]):
                if link:
                    episode = Episode(
                        link=link,
                        _selected_provider="VOE",
                        _selected_language="German Sub"
                    )
                else:
                    episode = Episode(
                        slug=search_anime(),
                        _selected_provider="VOE",
                        _selected_language="German Sub"
                    )
                anime = Anime(episode_list=[episode])
                anime_list.append(anime)

            execute(anime_list=anime_list)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
