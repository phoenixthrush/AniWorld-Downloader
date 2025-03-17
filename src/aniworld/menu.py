import os
import curses
import npyscreen

from aniworld.models import Anime, Episode
from aniworld.config import (
    VERSION,
    DEFAULT_DOWNLOAD_PATH,
    SUPPORTED_PROVIDERS,
    DEFAULT_PROVIDER_DOWNLOAD,
    DEFAULT_PROVIDER_WATCH,
    DEFAULT_ACTION
)


class CustomTheme(npyscreen.ThemeManager):
    default_colors = {
        'DEFAULT': 'WHITE_BLACK',
        'FORMDEFAULT': 'MAGENTA_BLACK',
        'NO_EDIT': 'BLUE_BLACK',
        'STANDOUT': 'CYAN_BLACK',
        'CURSOR': 'WHITE_BLACK',
        'CURSOR_INVERSE': 'BLACK_WHITE',
        'LABEL': 'CYAN_BLACK',
        'LABELBOLD': 'CYAN_BLACK',
        'CONTROL': 'GREEN_BLACK',
        'IMPORTANT': 'GREEN_BLACK',
        'SAFE': 'GREEN_BLACK',
        'WARNING': 'YELLOW_BLACK',
        'DANGER': 'RED_BLACK',
        'CRITICAL': 'BLACK_RED',
        'GOOD': 'GREEN_BLACK',
        'GOODHL': 'GREEN_BLACK',
        'VERYGOOD': 'BLACK_GREEN',
        'CAUTION': 'YELLOW_BLACK',
        'CAUTIONHL': 'BLACK_YELLOW',
    }


class SelectionMenu(npyscreen.NPSApp):
    def __init__(self, slug):
        super().__init__()
        self.anime = Anime(slug=slug, episode_list=[
                           Episode(slug=slug, season=1, episode=1)])
        self.selected_episodes = []
        self.episode_dict = {}
        self.action_selection = None
        self.aniskip_selection = None
        self.folder_selection = None
        self.language_selection = None
        self.provider_selection = None
        self.episode_selection = None

    def main(self):
        available_languages = self.anime[0].language_name
        season_episode_count = self.anime[0].season_episode_count
        movie_episode_count = self.anime[0].movie_episode_count
        available_providers = self.anime[0].provider_name

        supported_providers = [
            provider for provider in available_providers if provider in SUPPORTED_PROVIDERS]

        for season, episodes in season_episode_count.items():
            for episode in range(1, episodes + 1):
                link_formatted = f"{self.anime.title} - Season {season} - Episode {episode}"
                link = (
                    f"https://aniworld.to/anime/stream/{self.anime.slug}/"
                    f"staffel-{season}/episode-{episode}"
                )
                self.episode_dict[link] = link_formatted

        for episode in range(1, movie_episode_count + 1):
            movie_link_formatted = f"{self.anime.title} - Movie {episode}"
            movie_link = f"https://aniworld.to/anime/stream/{self.anime.slug}/filme/film-{episode}"
            self.episode_dict[movie_link] = movie_link_formatted

        available_episodes = list(self.episode_dict.values())

        terminal_height = os.get_terminal_size().lines
        total_reserved_height = 3 + 2 + 2 + \
            len(available_languages) + len(supported_providers) + 5
        max_episode_height = max(3, terminal_height - total_reserved_height)

        if DEFAULT_ACTION == "Download":
            default_provider = DEFAULT_PROVIDER_DOWNLOAD
        else:
            default_provider = DEFAULT_PROVIDER_WATCH

        if default_provider in supported_providers:
            DEFAULT_PROVIDER_INDEX = supported_providers.index(
                default_provider)
        else:
            DEFAULT_PROVIDER_INDEX = 0

        npyscreen.setTheme(CustomTheme)
        f = npyscreen.Form(name=f"Welcome to AniWorld-Downloader {VERSION}")

        self.action_selection = f.add(
            npyscreen.TitleSelectOne,
            max_height=3,
            value=[1],
            name="Action",
            values=["Watch", "Download", "Syncplay"],
            scroll_exit=True
        )

        self.aniskip_selection = f.add(
            npyscreen.TitleMultiSelect,
            max_height=2,
            value=[1],
            name="Aniskip",
            values=["Enabled"],
            scroll_exit=True,
            rely=self.action_selection.rely + self.action_selection.height + 1
        )

        self.folder_selection = f.add(
            npyscreen.TitleFilenameCombo,
            max_height=2,
            name="Save Location",
            rely=self.action_selection.rely + self.action_selection.height + 1,
            value=DEFAULT_DOWNLOAD_PATH
        )

        self.language_selection = f.add(
            npyscreen.TitleSelectOne,
            max_height=len(available_languages),
            value=[1],
            name="Language",
            values=available_languages,
            scroll_exit=True,
            rely=self.aniskip_selection.rely + self.aniskip_selection.height
        )

        self.provider_selection = f.add(
            npyscreen.TitleSelectOne,
            max_height=len(supported_providers),
            value=[DEFAULT_PROVIDER_INDEX],
            name="Provider",
            values=supported_providers,
            scroll_exit=True,
            rely=self.language_selection.rely + self.language_selection.height + 1
        )

        self.episode_selection = f.add(
            npyscreen.TitleMultiSelect,
            max_height=max_episode_height,
            name="Episode",
            values=available_episodes,
            scroll_exit=True,
            rely=self.provider_selection.rely + self.provider_selection.height + 1
        )

        def update_visibility():
            selected_action = self.action_selection.get_selected_objects()[0]
            if selected_action in ["Watch", "Syncplay"]:
                self.folder_selection.hidden = True
                self.aniskip_selection.hidden = False

                try:
                    provider_index = supported_providers.index(
                        DEFAULT_PROVIDER_WATCH)
                except ValueError:
                    provider_index = 0

                if self.provider_selection.value != [provider_index]:
                    self.provider_selection.value = [provider_index]
            else:
                self.folder_selection.hidden = False
                self.aniskip_selection.hidden = True

                try:
                    provider_index = supported_providers.index(
                        DEFAULT_PROVIDER_DOWNLOAD)
                except ValueError:
                    provider_index = 0

                if self.provider_selection.value != [provider_index]:
                    self.provider_selection.value = [provider_index]
            f.display()

        self.action_selection.when_value_edited = update_visibility

        update_visibility()

        self.episode_selection.when_value_edited = self.on_ok

        f.edit()

    def on_ok(self):
        selected_link_formatted = self.episode_selection.get_selected_objects() or []

        # self.selected_episodes = [
        #    {"link": link, "name": name}
        #    for link, name in self.episode_dict.items() if name in selected_link_formatted
        # ]

        self.selected_episodes = [
            link
            for link, name in self.episode_dict.items() if name in selected_link_formatted
        ]

    def get_selected_values(self):
        """
        return Anime(
            title=self.anime.title,
            episode_list=[
                Episode(
                    episode=episode["name"],
                    slug=self.anime.slug,
                    link=episode["link"],
                    # _selected_provider=self.anime.provider,
                    # _selected_language=self.anime.language
                    _selected_provider="VOE",
                    _selected_language="German Sub"
                ) for episode in self.selected_episodes
            ]
        )
        """

        # return self.selected_episodes

        # return Anime(
        #     action=self.action_selection.get_selected_objects()[0],
        #     language=self.language_selection.get_selected_objects()[0],
        #     provider=self.provider_selection.get_selected_objects()[0],
        #     output_directory=self.folder_selection.value,
        #     episode_list=self.selected_episodes
        # )

        selected_action = self.action_selection.get_selected_objects()[0]
        selected_language = self.language_selection.get_selected_objects()[0]
        selected_provider = self.provider_selection.get_selected_objects()[0]
        selected_output_directory = self.folder_selection.value

        # print(f"Anime Title: {self.anime.title}")
        # print(f"Selected Episodes: {self.selected_episodes}")
        # print(f"Action: {selected_action}")
        # print(f"Language: {selected_language}")
        # print(f"Provider: {selected_provider}")
        # print(f"Output Directory: {selected_output_directory}")

        return Anime(
            title=self.anime.title,
            episode_list=[
                Episode(
                    slug=self.anime.slug,
                    link=link,
                    _selected_language=selected_language,
                    _selected_provider=selected_provider
                ) for link in self.selected_episodes
            ],
            action=selected_action,
            language=selected_language,
            provider=selected_provider,
            output_directory=selected_output_directory
        )


def menu(slug):
    try:
        app = SelectionMenu(slug=slug)
        app.run()
        anime = app.get_selected_values()
        curses.endwin()
        return anime
    except KeyboardInterrupt:
        curses.endwin()


if __name__ == "__main__":
    selected_episodes = menu(slug="dan-da-dan", arguments=None)
    print("Selected Episodes:", selected_episodes)
