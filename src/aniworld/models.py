import pathlib
import re
import json
import logging

import requests
import requests.models
from bs4 import BeautifulSoup

from aniworld.aniskip import get_mal_id_from_title
from aniworld.config import (
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_ACTION
)

from aniworld.extractors import (
    get_direct_link_from_vidmoly,
    get_direct_link_from_vidoza,
    get_direct_link_from_voe,
    get_direct_link_from_doodstream,
    get_direct_link_from_speedfiles
)


def get_anime_title_from_html(html: requests.models.Response) -> str:
    episode_soup = BeautifulSoup(html.content, 'html.parser')
    series_title_div = episode_soup.find('div', class_='series-title')

    if series_title_div:
        episode_title = series_title_div.find('h1').find('span').text  # Kaguya-sama: Love is War
    else:
        return ""

    return episode_title


class Anime:
    """
        Represents an anime series with various attributes and methods to fetch and manage its details.

        Example:
            anime = Anime(
                episode_list=[
                    Episode(
                        slug="loner-life-in-another-world",
                        season=1,
                        episode=1
                    )
                ]
            )

        Required Attributes:
             episode_list (list): A list of Episode objects for the anime.

        Attributes:
            title (str): The title of the anime.
            slug (str): A URL-friendly version of the title used for web requests.
            action (str): The default action to be performed, e.g., download or watch.
            provider (str): The provider of the anime content.
            language (int): The language code for the anime.
            aniskip (bool): Whether to skip certain actions or not.
            only_command (bool): If true, only commands are executed without additional actions.
            only_direct_link (bool): If true, only direct links are fetched.
            output_directory (str): The directory where downloads are saved.
            episode_list (list): A list of Episode episodes for the anime.
            description_german (str): The German description of the anime.
            description_english (str): The English description of the anime.
            html (requests.models.Response): The HTML response object for the anime's webpage.
    """

    def __init__(
        self,
        title: str = None,
        slug: str = None,
        action: str = DEFAULT_ACTION,
        provider: str = None,
        language: int = None,
        aniskip: bool = False,
        only_command: bool = False,
        only_direct_link: bool = False,
        output_directory: str = pathlib.Path.home() / "Downloads",
        episode_list: list = None,
        description_german: str = None,
        description_english: str = None,
        html: requests.models.Response = None
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
        self.html: requests.models.Response = html

        self.auto_fill_details()

    def _get_aniworld_description_from_html(self):
        soup = BeautifulSoup(self.html.content, 'html.parser')
        seri_des_div = soup.find('p', class_='seri_des')

        if seri_des_div:
            description = seri_des_div.get('data-full-description', '')
            return description
        else:
            return "Could not fetch description."

    def _get_myanimelist_description_from_html(self):
        anime_id = get_mal_id_from_title(self.title, 1)
        response = requests.get(f"https://myanimelist.net/anime/{anime_id}", timeout=DEFAULT_REQUEST_TIMEOUT)
        soup = BeautifulSoup(response.content, 'html.parser')
        description_meta = soup.find('meta', property='og:description')

        if description_meta:
            description = description_meta['content']
            return description
        else:
            return "Could not fetch description."

    def auto_fill_details(self) -> None:
        self.html = requests.get(f"https://aniworld.to/anime/stream/{self.slug}", timeout=DEFAULT_REQUEST_TIMEOUT)
        self.title = get_anime_title_from_html(html=self.html)
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
    Represents an episode of an anime series with various attributes and methods to fetch and manage its details.

    Example:
        Episode(
            slug="loner-life-in-another-world",
            season=1,
            episode=1
        )

    Required Attributes:
        link (str) or slug (str), season (int), episode (int):
        Either a direct link to the episode or a slug with season and episode numbers for constructing the link.

    Attributes:
        anime_title (str): The title of the anime the episode belongs to.
        title_german (str): The German title of the episode.
        title_english (str): The English title of the episode.
        season (int): The season number of the episode.
        episode (int): The episode number within the season.
        slug (str): A URL-friendly version of the episode title used for web requests.
        link (str): The direct link to the episode.
        mal_id (int): The MyAnimeList ID for the episode.
        redirect_link (str): The redirect link for streaming the episode.
        embeded_link (str): The embedded link for the episode.
        direct_link (str): The direct streaming link for the episode.
        provider (dict): A dictionary of available providers and their links.
        provider_name (list): A list of provider names.
        language (list): A list of available language codes for the episode.
        language_name (list): A list of available language names for the episode.
        season_episode_count (dict): A dictionary mapping season numbers to episode counts.
        movie_episode_count (int): The count of movie episodes.
        html (requests.models.Response): The HTML response object for the episode's webpage.
        _selected_provider (str): The selected provider for streaming.
        _selected_language (int): The selected language code for streaming.
    """

    def __init__(
        self,
        anime_title: str = None,
        title_german: str = None,
        title_english: str = None,
        season: int = None,
        episode: int = None,
        slug: str = None,
        # slug_link: str = None,
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
        if not link and (not slug or not season or not episode):
            raise ValueError("Provide either 'link' or 'slug' with 'season' and 'episode'.")

        self.anime_title: str = anime_title
        self.title_german: str = title_german
        self.title_english: str = title_english
        self.season: int = season
        self.episode: int = episode
        self.slug: str = slug
        # self.slug_link: str = slug_link
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

        language_key = lang_mapping.get(language, None)

        if language_key is None:
            raise ValueError(f"Language: {language} not valid.")

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
        # if not self._selected_provider:
        #    raise ValueError(self._selected_provider)
        #    # return get_direct_link_from_voe(embeded_voe_link=self.embeded_link)
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
        # print(f"Selected language: {self._selected_language}")
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
                    f"{lang_key}' found. Checked providers: {list(self.provider.keys())}. "
                    f"Provider variable: {self.provider}"
                )
        else:
            self.redirect_link = self.provider[self._selected_provider][lang_key]

    def get_embeded_link(self):
        if not self.redirect_link:
            self.get_redirect_link()

        self.embeded_link = requests.get(self.redirect_link, timeout=DEFAULT_REQUEST_TIMEOUT).url
        return self.embeded_link

    def get_direct_link(self, provider=None, language=None):
        """
        Retrieves the direct streaming link for the episode.

        Example:
            episode.get_direct_link("VOE", "German Sub")

        Note:
            If this method is not being called from a menu or with arguments,
            ensure that 'provider' and 'language' are set before calling.

        Args:
            provider (str): The name of the provider to use for fetching the direct link.
            language (str): The language code to use for fetching the direct link.

        Returns:
            str: The direct streaming link for the episode.
        """
        if provider:
            self._selected_provider = provider

        if language:
            self._selected_language = language

        if not self.embeded_link:
            self.get_embeded_link()

        self.direct_link = self._get_direct_link_from_provider()
        return self.direct_link

    def auto_fill_details(self) -> None:
        # self.season = self._get_season_from_link()
        # self.episode = self._get_episode_from_link()

        self.season = 1
        self.episode = 1

        if self.slug and self.season and self.episode:
            self.link = (
                f"https://aniworld.to/anime/stream/{self.slug}/"
                f"staffel-{self.season}/episode-{self.episode}"
            )

        if self.link:
            self.slug = self.slug or self.link.split("/")[-3]

        # self.slug_link = f"https://aniworld.to/anime/stream/{self.slug}"
        self.html = requests.get(self.link, timeout=DEFAULT_REQUEST_TIMEOUT)
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
