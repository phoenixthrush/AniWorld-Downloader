import os
import logging
import npyscreen
# from aniworld.models import Anime, Episode
from aniworld.config import VERSION, DEFAULT_DOWNLOAD_PATH

# models.py
import pathlib
import re
import json

import requests
import requests.models
from bs4 import BeautifulSoup

from aniworld.aniskip import get_mal_id_from_title
from aniworld.config import (
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_LANGUAGE,
    DEFAULT_PROVIDER_DOWNLOAD,
    DEFAULT_PROVIDER_WATCH,
    DEFAULT_ACTION
)

from aniworld.extractors import (
    get_direct_link_from_vidmoly,
    get_direct_link_from_vidoza,
    get_direct_link_from_voe,
    get_direct_link_from_doodstream,
    get_direct_link_from_speedfiles
)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)s:%(name)s:%(funcName)s: %(message)s"
)
logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)


def get_anime_title_from_html(html: requests.models.Response) -> str:
    episode_soup = BeautifulSoup(html.content, 'html.parser')
    series_title_div = episode_soup.find('div', class_='series-title')

    if series_title_div:
        episode_title = series_title_div.find('h1').find('span').text  # Kaguya-sama: Love is War
    else:
        return ""

    return episode_title


class Anime:
    def __init__(
        self,
        title: str = None,
        slug: str = None,
        action: str = "Watch",
        provider: str = None,
        language: int = None,
        aniskip: bool = False,
        only_command: bool = False,
        only_direct_link: bool = False,
        output_directory: str = pathlib.Path.home() / "Downloads",
        episode_list: list = None,
        description_german: str = None,
        description_english: str = None
    ) -> None:
        if not episode_list:
            raise ValueError("Provide 'episode_list'.")

        self.title: str = title
        self.slug: str = slug
        self.action: str = action
        self.provider: str = provider
        self.language: str = language
        self.aniskip: bool = aniskip
        self.only_command: bool = only_command
        self.only_direct_link: bool = only_direct_link
        self.output_directory: str = output_directory
        self.episode_list: list = episode_list
        self.description_german: str = description_german
        self.description_english: str = description_english

        self.auto_fill_details()

    def _get_aniworld_description_from_html(self):
        soup = BeautifulSoup(self.episode_list[0].html.content, 'html.parser')
        seri_des_div = soup.find('p', class_='seri_des')
        description = seri_des_div['data-full-description']
        return description

    def _get_myanimelist_description_from_html(self):
        anime_id = get_mal_id_from_title(self.title, 1)
        response = requests.get(f"https://myanimelist.net/anime/{anime_id}", timeout=DEFAULT_REQUEST_TIMEOUT)
        soup = BeautifulSoup(response.content, 'html.parser')
        description = soup.find('meta', property='og:description')['content']
        return description

    def auto_fill_details(self) -> None:
        self.title = get_anime_title_from_html(html=self.episode_list[0].html)
        self.description_german = self._get_aniworld_description_from_html()
        self.description_english = self._get_myanimelist_description_from_html()

    def __iter__(self):
        return iter(self.episode_list)

    def __getitem__(self, index: int):
        return self.episode_list[index]

    def to_json(self) -> str:
        data = {
            "title": self.title,
            "action": self.action,
            "provider": self.provider,
            "language": self.language,
            "aniskip": self.aniskip,
            "only_command": self.only_command,
            "only_direct_link": self.only_direct_link,
            "output_directory": str(self.output_directory),
            "episode_list": self.episode_list,
            "description_german": self.description_german,
            "description_english": self.description_english,
        }
        # return json.dumps(data, indent=4)
        return str(data)

    def __str__(self) -> str:
        return self.to_json()


class Episode:
    """
    Attributes:
        anime_title (str): None
        title_german (str): None
        title_english (str): None
        season (int): 1
        episode (int): 1
        slug (str): None
        link (str): None
        mal_id (int): None
        redirect_link (str): None
        embeded_link (str): None
        direct_link (str): None
        provider (dict): None
        provider_name (list): None
        language (list): None
        language_name (list): None
        season_episode_count (dict): None
        html (requests.models.Response): None
        arguments (argparse.Namespace): None
    """

    def __init__(
        self,
        anime_title: str = None,
        title_german: str = None,
        title_english: str = None,
        season: int = 1,
        episode: int = 1,
        slug: str = None,
        slug_link: str = None,
        link: str = None,
        mal_id: int = None,
        redirect_link: str = None,
        embeded_link: str = None,
        direct_link: str = None,
        provider: dict = None,  # available providers
        provider_name: list = None,
        language: list = None,  # available languages
        language_name: list = None,
        season_episode_count: dict = None,
        movie_episode_count: int = None,
        html: requests.models.Response = None,
        _selected_provider: str = None,
        _selected_language: int = None
    ) -> None:
        if not link and not slug:
            raise ValueError("Provide either 'link' or 'slug'.")

        self.anime_title: str = anime_title
        self.title_german: str = title_german
        self.title_english: str = title_english
        self.season: int = season
        self.episode: int = episode
        self.slug: str = slug
        self.slug_link: str = slug_link
        self.link: str = link
        self.mal_id: int = mal_id
        self.redirect_link = redirect_link
        self.embeded_link = embeded_link
        self.direct_link = direct_link
        self.provider: dict = provider
        self.provider_name: list = provider_name
        self.language: list = language
        self.language_name: list = language_name
        self.season_episode_count: dict = season_episode_count
        self.movie_episode_count: int = movie_episode_count
        self.html: requests.models.Response = html
        self._selected_provider: str = _selected_provider
        self._selected_language: int = _selected_language

        self.auto_fill_details()

    def _get_episode_title_from_html(self) -> tuple:
        episode_soup = BeautifulSoup(self.html.content, 'html.parser')
        episode_german_title_div = episode_soup.find('span', class_='episodeGermanTitle')
        episode_english_title_div = episode_soup.find('small', class_='episodeEnglishTitle')

        german_title = episode_german_title_div.text if episode_german_title_div else ""
        english_title = episode_english_title_div.text if episode_english_title_div else ""

        return german_title, english_title

    def _get_season_from_link(self) -> int:
        season = self.link.split("/")[-2]  # e.g. staffel-2
        numbers = re.findall(r'\d+', season)

        if numbers:
            return int(numbers[-1])  # e.g 2

        raise ValueError(f"No valid season number found in the link: {self.link}")

    def _get_episode_from_link(self) -> int:
        episode = self.link.split("/")[-1]  # e.g. episode-2
        numbers = re.findall(r'\d+', episode)

        if numbers:
            return int(numbers[-1])  # e.g 2

        raise ValueError(f"No valid episode number found in the link: {self.link}")

    def _get_available_language_from_html(self) -> list[int]:
        """
        Language Codes:
            1: German Dub
            2: English Sub
            3: German Sub
        """

        episode_soup = BeautifulSoup(self.html.content, 'html.parser')
        change_language_box_div = episode_soup.find('div', class_='changeLanguageBox')
        language = []

        if change_language_box_div:
            img_tags = change_language_box_div.find_all('img')
            for img in img_tags:
                lang_key = img.get('data-lang-key')
                if lang_key and lang_key.isdigit():
                    language.append(int(lang_key))
        else:
            return []

        return language  # e.g. [1, 2, 3]

    def _get_provider_from_html(self) -> dict:
        """
            Parses the HTML content to extract streaming providers, their language keys, and redirect links.
            Returns a dictionary with provider names as keys and language key-to-redirect URL mappings as values.

            Example:
            {
                'VOE': {1: 'https://aniworld.to/redirect/1766412', 2: 'https://aniworld.to/redirect/1766405'},
                'Doodstream': {1: 'https://aniworld.to/redirect/1987922', 2: 'https://aniworld.to/redirect/2700342'},
                ...
            }

            Access redirect link with:
            print(self.provider["VOE"][2])
        """

        soup = BeautifulSoup(self.html.content, 'html.parser')
        providers = {}

        logging.debug("Parsed HTML content with BeautifulSoup.")

        episode_links = soup.find_all('li', class_=lambda x: x and x.startswith('episodeLink'))
        logging.debug(f"Found {len(episode_links)} episode links.")

        for link in episode_links:
            provider_name_tag = link.find('h4')
            provider_name = provider_name_tag.text.strip() if provider_name_tag else None
            logging.debug(f"Extracted provider name: {provider_name}")

            redirect_link_tag = link.find('a', class_='watchEpisode')
            redirect_link = redirect_link_tag['href'] if redirect_link_tag else None
            logging.debug(f"Extracted redirect link: {redirect_link}")

            lang_key = link.get('data-lang-key')
            lang_key = int(lang_key) if lang_key and lang_key.isdigit() else None
            logging.debug(f"Extracted language key: {lang_key}")

            if provider_name and redirect_link and lang_key:
                if provider_name not in providers:
                    providers[provider_name] = {}
                providers[provider_name][lang_key] = f"https://aniworld.to{redirect_link}"
                logging.debug(f"Added provider '{provider_name}' with language key '{lang_key}' to providers.")

        if not providers:
            raise ValueError(f"Could not get providers from {self.html.content}")

        logging.debug(f"Final providers dictionary: {providers}")
        return providers

    def _get_key_from_language(self, language: str) -> int:
        lang_mapping = {
            "German Dub": 1,
            "English Sub": 2,
            "German Sub": 3
        }

        language_key = lang_mapping.get(language, "Unknown Language")

        if language_key is None:
            raise ValueError("Language not valid.")

        return language_key

    def _get_languages_from_keys(self, keys: list[int]) -> list[str]:
        key_mapping = {
            1: "German Dub",
            2: "English Sub",
            3: "German Sub"
        }

        languages = [key_mapping.get(key, None) for key in keys]

        if None in languages:
            raise ValueError("One or more keys are not valid.")

        return languages

    def _get_direct_link_from_provider(self) -> str:
        if not self._selected_provider:
            return get_direct_link_from_voe(embeded_voe_link=self.embeded_link)
        if self._selected_provider == "Vidmoly":
            return get_direct_link_from_vidmoly(embeded_vidmoly_link=self.embeded_link)
        if self._selected_provider == "Vidoza":
            return get_direct_link_from_vidoza(embeded_vidoza_link=self.embeded_link)
        if self._selected_provider == "VOE":
            return get_direct_link_from_voe(embeded_voe_link=self.embeded_link)
        if self._selected_provider == "Doodstream":
            return get_direct_link_from_doodstream(embeded_doodstream_link=self.embeded_link)
        if self._selected_provider == "SpeedFiles":
            return get_direct_link_from_speedfiles(embeded_speedfiles_link=self.embeded_link)

        raise ValueError("No valid provider selected.")

    def _get_season_episode_count(self) -> dict:
        base_url = f"https://aniworld.to/anime/stream/{self.slug}/"
        response = requests.get(base_url, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')

        season_meta = soup.find('meta', itemprop='numberOfSeasons')
        number_of_seasons = int(season_meta['content']) if season_meta else 0

        episode_counts = {}

        for season in range(1, number_of_seasons + 1):
            season_url = f"{base_url}staffel-{season}"
            response = requests.get(season_url, timeout=15)
            soup = BeautifulSoup(response.content, 'html.parser')

            episode_links = soup.find_all('a', href=True)
            unique_links = set(link['href'] for link in episode_links if f"staffel-{season}/episode-" in link['href'])

            episode_counts[season] = len(unique_links)

        return episode_counts

    def _get_movie_episode_count(self) -> int:
        movie_page_url = f"https://aniworld.to/anime/stream/{self.slug}/filme"
        response = requests.get(movie_page_url, timeout=DEFAULT_REQUEST_TIMEOUT)

        parsed_html = BeautifulSoup(response.content, 'html.parser')
        movie_indices = []

        movie_index = 1
        while True:
            expected_subpath = f"{self.slug}/filme/film-{movie_index}"

            matching_links = [link['href'] for link in parsed_html.find_all(
                'a', href=True) if expected_subpath in link['href']]

            if matching_links:
                movie_indices.append(movie_index)
                movie_index += 1
            else:
                break

        return max(movie_indices) if movie_indices else 0

    def get_redirect_link(self):
        lang_key = self._get_key_from_language(self._selected_language)

        if self._selected_provider not in self.provider or lang_key not in self.provider[self._selected_provider]:
            for provider_name, lang_dict in self.provider.items():
                if lang_key in lang_dict:
                    self._selected_provider = provider_name
                    self.redirect_link = lang_dict[lang_key]
                    break
            else:
                raise KeyError(
                    "No provider with the language key '"
                    f"{lang_key}' found. Checked providers: {list(self.provider.keys())}"
                )
        else:
            self.redirect_link = self.provider[self._selected_provider][lang_key]

    def get_embeded_link(self):
        if not self.redirect_link:
            self.get_redirect_link()

        self.embeded_link = requests.get(self.redirect_link, timeout=DEFAULT_REQUEST_TIMEOUT).url
        return self.embeded_link

    def get_direct_link(self):
        if not self.embeded_link:
            self.get_embeded_link()

        self.direct_link = self._get_direct_link_from_provider()
        return self.direct_link

    def auto_fill_details(self) -> None:
        if self.slug and self.season and self.episode:
            self.link = (
                f"https://aniworld.to/anime/stream/{self.slug}/"
                f"staffel-{self.season}/episode-{self.episode}"
            )

        if self.link:
            self.slug = self.slug or self.link.split("/")[-3]
            self.season = self.season or self._get_season_from_link()
            self.episode = self.episode or self._get_episode_from_link()

        self.slug_link = f"https://aniworld.to/anime/stream/{self.slug}"
        self.html = requests.get(self.slug_link, timeout=DEFAULT_REQUEST_TIMEOUT)
        self.title_german, self.title_english = self._get_episode_title_from_html()
        self.language = self._get_available_language_from_html()
        self.language_name = self._get_languages_from_keys(self.language)
        self.provider = self._get_provider_from_html()
        self.provider_name = list(self.provider.keys())
        self.season_episode_count = self._get_season_episode_count()
        self.movie_episode_count = self._get_movie_episode_count()
        self.anime_title = get_anime_title_from_html(html=self.html)
        self.mal_id = get_mal_id_from_title(title=self.anime_title, season=self.season)

        """
        if not self.arguments:
            selected_provider = DEFAULT_PROVIDER_DOWNLOAD
            selected_language = DEFAULT_LANGUAGE
        else:
            selected_language = self.arguments.language

            if self.arguments.provider:
                selected_provider = self.arguments.provider
            else:
                if self.arguments.action == "Download":
                    selected_provider = DEFAULT_PROVIDER_DOWNLOAD
                else:
                    selected_provider = DEFAULT_PROVIDER_WATCH
        """

        # print(selected_provider)
        # print(selected_language)

        # TODO - fix "KeyError None" crash
        # if not selected_provider in self.provider_name:
        #    raise ValueError(f"Invalid provider: {selected_provider}. Available providers: {list(self.provider_name)}")

        # Those three depend on the Anime Class and should be asigned
        # from self._selected_provider and self._selected_language

        # TODO - self.redirect_link = self.provider[self._selected_provider][self._get_key_from_language(self._selected_language)]
        # self.redirect_link = self.provider["VOE"][3]
        # TODO - self.embeded_link = requests.get(self.redirect_link, timeout=DEFAULT_REQUEST_TIMEOUT).url

        # TODO - Fix Vidmoly Timeout
        # TODO - self.direct_link = self._get_direct_link_from_provider()
        # print(self.direct_link)

    def to_json(self) -> str:
        data = {
            "anime_title": self.anime_title,
            "title_german": self.title_german,
            "title_english": self.title_english,
            "season": self.season,
            "episode": self.episode,
            "slug": self.slug,
            "link": self.link,
            "mal_id": self.mal_id,
            "redirect_link": self.redirect_link,
            "embeded_link": self.embeded_link,
            "direct_link": self.direct_link,
            "provider": self.provider,
            "provider_name": self.provider_name,
            "language": self.language,
            "language_name": self.language_name,
            "season_episode_count": self.season_episode_count,
            "html": str(self.html)
        }
        return json.dumps(data, indent=4)

    def __str__(self) -> str:
        return self.to_json()

# end models.py


IS_NEWEST_VERSION = True
SUPPORTED_PROVIDERS = [
    "VOE", "Doodstream", "Luluvdo", "Vidmoly", "Vidoza", "SpeedFiles", "Streamtape"
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
    def __init__(self, slug):
        super().__init__()
        self.anime = Anime(slug=slug, episode_list=[Episode(slug=slug)])
        self.selected_episodes = []
        self.episode_dict = {}

    def main(self):
        available_languages = self.anime[0].language_name
        season_episode_count = self.anime[0].season_episode_count
        movie_episode_count = self.anime[0].movie_episode_count
        available_providers = self.anime[0].provider_name

        supported_providers = [provider for provider in available_providers if provider in SUPPORTED_PROVIDERS]

        for season, episodes in season_episode_count.items():
            for episode in range(1, episodes + 1):
                link_formatted = f"{self.anime.title} - Season {season} - Episode {episode}"
                link = f"https://aniworld.to/anime/stream/{self.anime.slug}/staffel-{season}/episode-{episode}"
                self.episode_dict[link] = link_formatted

        for episode in range(1, movie_episode_count + 1):
            movie_link_formatted = f"{self.anime.title} - Movie {episode}"
            movie_link = f"https://aniworld.to/anime/stream/{self.anime.slug}/filme/film-{episode}"
            self.episode_dict[movie_link] = movie_link_formatted

        available_episodes = list(self.episode_dict.values())

        terminal_height = os.get_terminal_size().lines
        total_reserved_height = 3 + 2 + 2 + len(available_languages) + len(supported_providers) + 5
        max_episode_height = max(3, terminal_height - total_reserved_height)

        npyscreen.setTheme(CustomTheme)
        F = npyscreen.Form(name=f"Welcome to AniWorld-Downloader {VERSION}")

        self.action_selection = F.add(npyscreen.TitleSelectOne, max_height=3, value=[1], name="Action",
                                      values=["Watch", "Download", "Syncplay"], scroll_exit=True)

        self.aniskip_selection = F.add(npyscreen.TitleMultiSelect, max_height=2, value=[1], name="Aniskip",
                                       values=["Enabled"], scroll_exit=True,
                                       rely=self.action_selection.rely + self.action_selection.height + 1)

        self.folder_selection = F.add(npyscreen.TitleFilenameCombo, max_height=2, name="Save Location",
                                      rely=self.action_selection.rely + self.action_selection.height + 1, value=DEFAULT_DOWNLOAD_PATH)

        self.language_selection = F.add(npyscreen.TitleSelectOne, max_height=len(available_languages), value=[1], name="Language",
                                        values=available_languages, scroll_exit=True,
                                        rely=self.aniskip_selection.rely + self.aniskip_selection.height)

        self.provider_selection = F.add(npyscreen.TitleSelectOne, max_height=len(supported_providers), value=[1], name="Provider",
                                        values=supported_providers, scroll_exit=True,
                                        rely=self.language_selection.rely + self.language_selection.height + 1)

        self.episode_selection = F.add(npyscreen.TitleMultiSelect, max_height=max_episode_height, name="Episode",
                                       values=available_episodes, scroll_exit=True,
                                       rely=self.provider_selection.rely + self.provider_selection.height + 1)

        def update_visibility():
            selected_action = self.action_selection.get_selected_objects()[0]
            if selected_action in ["Watch", "Syncplay"]:
                self.folder_selection.hidden = True
                self.aniskip_selection.hidden = False
            else:
                self.folder_selection.hidden = False
                self.aniskip_selection.hidden = True
            F.display()

        self.action_selection.when_value_edited = update_visibility

        update_visibility()

        self.episode_selection.when_value_edited = self.on_ok

        F.edit()

    def on_ok(self):
        selected_link_formatted = self.episode_selection.get_selected_objects() or []

        self.selected_episodes = [
            {"link": link, "name": name}
            for link, name in self.episode_dict.items() if name in selected_link_formatted
        ]

    def get_selected_values(self):
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
        # return self.selected_episodes


def menu(arguments, slug):
    try:
        app = SelectionMenu(slug=slug)
        app.run()
        anime = app.get_selected_values()

        return anime
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    selected_episodes = menu(slug="dan-da-dan", arguments=None)
    print("Selected Episodes:", selected_episodes)
