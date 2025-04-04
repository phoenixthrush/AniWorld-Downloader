from aniworld.models import Anime, Episode
from aniworld.parser import arguments
from aniworld.search import search_anime
from aniworld.execute import execute
from aniworld.menu import menu


def aniworld() -> None:
    try:
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
                        link=link
                    )
                else:
                    episode = Episode(
                        slug=search_anime()
                    )
                anime = Anime(episode_list=[episode])
                anime_list.append(anime)

            execute(anime_list=anime_list)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    aniworld()
