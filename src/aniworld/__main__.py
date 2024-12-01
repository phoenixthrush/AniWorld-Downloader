from aniworld.models import Anime, Episode, get_episode_from_link, get_season_from_link
from aniworld.search import search_anime
from aniworld.execute import execute
from aniworld.parser import parse_arguments
from aniworld.config import DEFAULT_PROVIDER, DEFAULT_PROVIDER_WATCH, DEFAULT_LANGUAGE


def main() -> None:
    try:
        arguments = parse_arguments()
        anime_list = []

        if arguments.episode:
            for episode_link in arguments.episode:
                selected_provider = arguments.provider if arguments.provider else (
                    DEFAULT_PROVIDER_WATCH if arguments.action == "Watch" else DEFAULT_PROVIDER
                )

                selected_language = arguments.language if arguments.language else DEFAULT_LANGUAGE

                episode = Episode(
                    slug=episode_link.split("/")[-3],
                    season=get_season_from_link(link=episode_link),
                    episode=get_episode_from_link(link=episode_link),
                    selected_provider=selected_provider,
                    selected_language=selected_language
                )
                print(episode)
                anime_list.append(Anime(
                    **({"action": arguments.action} if arguments.action else {}),
                    **({"provider": arguments.provider} if arguments.provider else {}),
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
                **({"provider": arguments.provider} if arguments.provider else {}),
                episode_list=default_episodes, aniskip=True
            ))

        execute(anime_list=anime_list)

    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
