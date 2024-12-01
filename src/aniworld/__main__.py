from aniworld.models import Anime, Episode, get_episode_from_link, get_season_from_link
from aniworld.search import search_anime
from aniworld.execute import execute
from aniworld.parser import parse_arguments


def main() -> None:
    try:
        arguments = parse_arguments()
        anime_list = []

        if arguments.episode:
            for episode_link in arguments.episode:
                episode = Episode(
                    slug=episode_link.split("/")[-3],
                    season=get_season_from_link(link=episode_link),
                    episode=get_episode_from_link(link=episode_link)
                )
                anime_list.append(Anime(
                    **({"action": arguments.action} if arguments.action else {}),
                    episode_list=[episode]
                ))
        else:
            slug = search_anime()

            default_episodes = [
                Episode(slug=slug, season=1, episode=1),
                Episode(slug=slug, season=1, episode=2),
                Episode(slug=slug, season=1, episode=3)
            ]

            anime_list.append(Anime(
                **({"action": arguments.action} if arguments.action else {}),
                episode_list=default_episodes, aniskip=True
            ))

        execute(anime_list=anime_list)

    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
