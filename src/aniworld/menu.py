import os

import npyscreen

from aniworld.models import Episode
from aniworld.config import VERSION


IS_NEWEST_VERSION = True

SUPPORTED_PROVIDERS = [
    "VOE", "Doodstream", "Luluvdo", "Vidmoly", "Vidoza", "Speedfiles", "Streamtape"
]  # Not supported: "Filemoon"


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
    def __init__(self, slug, arguments):
        super().__init__()
        self.slug = slug
        self.ep = Episode(slug=slug, arguments=arguments)

    def main(self):
        available_languages = self.ep.language_name
        season_episode_count = self.ep.season_episode_count  # {1: 12, 2: 13, 3: 13}
        available_providers = self.ep.provider_name

        supported_providers = [provider for provider in available_providers if provider in SUPPORTED_PROVIDERS]
        available_episodes = []

        for season, episodes in season_episode_count.items():
            for episode in range(1, episodes + 1):
                available_episodes.append(f"{self.ep.anime_title} - Season {season} - Episode {episode}")

        terminal_height = os.get_terminal_size().lines
        total_reserved_height = 3 + 2 + 2 + len(available_languages) + len(supported_providers) + 5
        max_episode_height = max(3, terminal_height - total_reserved_height)

        npyscreen.setTheme(CustomTheme)
        F = npyscreen.Form(name=f"Welcome to Aniworld-Downloader {VERSION}")

        action_selection = F.add(npyscreen.TitleSelectOne, max_height=3, value=[1], name="Action",
                                 values=["Watch", "Download", "Syncplay"], scroll_exit=True)

        aniskip_selection = F.add(npyscreen.TitleMultiSelect, max_height=2, value=[1], name="Aniskip",
                                  values=["Enabled"], scroll_exit=True,
                                  rely=action_selection.rely + action_selection.height + 1)

        folder_selection = F.add(npyscreen.TitleFilenameCombo, max_height=2, name="Save Location",
                                 rely=action_selection.rely + action_selection.height + 1)

        language_selection = F.add(npyscreen.TitleSelectOne, max_height=len(available_languages), value=[1], name="Language",
                                   values=available_languages, scroll_exit=True,
                                   rely=aniskip_selection.rely + aniskip_selection.height)

        provider_selection = F.add(npyscreen.TitleSelectOne, max_height=len(supported_providers), value=[1], name="Provider",
                                   values=supported_providers, scroll_exit=True,
                                   rely=language_selection.rely + language_selection.height + 1)

        episode_selection = F.add(npyscreen.TitleMultiSelect, max_height=max_episode_height, name="Episode",
                                  values=available_episodes, scroll_exit=True,
                                  rely=provider_selection.rely + provider_selection.height + 1)

        def update_visibility():
            selected_action = action_selection.get_selected_objects()[0]
            if selected_action in ["Watch", "Syncplay"]:
                folder_selection.hidden = True
                aniskip_selection.hidden = False
            else:
                folder_selection.hidden = False
                aniskip_selection.hidden = True
            F.display()

        action_selection.when_value_edited = update_visibility

        update_visibility()

        F.edit()


def menu(arguments, slug):
    try:
        App = SelectionMenu(arguments=arguments, slug=slug)
        App.run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    menu()
