import argparse
import pathlib
import re

import requests
import requests.models
from bs4 import BeautifulSoup

from aniworld.aniskip import get_mal_id_from_title
from aniworld.config import DEFAULT_REQUEST_TIMEOUT, DEFAULT_ACTION

from aniworld.extractors import (
    get_direct_link_from_vidmoly,
    get_direct_link_from_vidoza,
    get_direct_link_from_voe
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
    Attributes:
        title: str = None,
        action: str = "Watch",
        provider: str = None
        aniskip: bool = False,
        only_command: bool = False,
        only_direct_link: bool = False,
        output_directory: str = pathlib.Path.home() / "Downloads",
        episode_list: list = None,
        description_german: str = None,
        description_english: str = None,
    """

    def __init__(
        self,
        title: str = None,
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
        arguments: argparse.Namespace = None
    ) -> None:
        if not episode_list:
            raise ValueError("Provide 'episode_list'.")

        self.title: str = title
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
        self.arguments = arguments

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

        if self.arguments.action:
            self.action = self.arguments.action
        else:
            self.action = "Download"

        if self.arguments.provider:
            self.provider = self.arguments.provider
        else:
            if self.action == "Download":
                self.provider = "VOE"
            else:
                self.provider = "Vidmoly"

    def __iter__(self):
        return iter(self.episode_list)

    def __str__(self) -> str:
        return (
            f"Anime(action={self.action}, provider={self.provider}, "
            f"aniskip={self.aniskip}, only_command={self.only_command}, "
            f"only_direct_link={self.only_direct_link}, output_directory={self.output_directory}, "
            f"episode_list={self.episode_list}, description_german={self.description_german}, "
            f"description_english={self.description_english})"
        )


class Episode:
    """
    Attributes:
        title_german (str): The German title of the episode. Default is None.
        title_english (str): The English title of the episode. Default is None.
        season (int): The season number of the episode. Default is None.
        episode (int): The episode number. Default is None.
        slug (str): A slug for the episode, typically used in URLs. Default is None.
        link (str): The link to the episode. Default is None.
        mal_id (int): The MAL (MyAnimeList) ID associated with the episode. Default is None.
        provider (dict): A dictionary of providers for the episode. Default is None.
        language (list): A list of languages the episode is available in. Default is None.
        html (requests.models.Response): The HTML response containing episode details. Default is None.
    """

    def __init__(
        self,
        title_german: str = None,
        title_english: str = None,
        season: int = None,
        episode: int = None,
        slug: str = None,
        link: str = None,
        mal_id: int = None,
        redirect_link: str = None,
        embeded_link: str = None,
        direct_link: str = None,
        provider: dict = None,  # available providers
        language: list = None,  # available languages
        html: requests.models.Response = None,
        arguments: argparse.Namespace = None
    ) -> None:
        if not link and not (slug and season and episode):
            raise ValueError("Provide either 'link' or ('slug', 'season', and 'episode').")

        self.title_german: str = title_german
        self.title_english: str = title_english
        self.season: int = season
        self.episode: int = episode
        self.slug: str = slug
        self.link: str = link
        self.mal_id: int = mal_id
        self.redirect_link = redirect_link
        self.embeded_link = embeded_link
        self.direct_link = direct_link
        self.provider: dict = provider
        self.language: list = language
        self.html: requests.models.Response = html
        self.arguments = arguments

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
        soup = BeautifulSoup(self.html.content, 'html.parser')
        providers = {}

        episode_links = soup.find_all('li', class_=lambda x: x and x.startswith('episodeLink'))

        for link in episode_links:
            provider_name_tag = link.find('h4')
            provider_name = provider_name_tag.text.strip() if provider_name_tag else None

            redirect_link_tag = link.find('a', class_='watchEpisode')
            redirect_link = redirect_link_tag['href'] if redirect_link_tag else None

            lang_key = link.get('data-lang-key')
            lang_key = int(lang_key) if lang_key and lang_key.isdigit() else None

            if provider_name and redirect_link and lang_key:
                if provider_name not in providers:
                    providers[provider_name] = []
                providers[provider_name].append({
                    'redirect_link': f"https://aniworld.to{redirect_link}",
                    'language': lang_key
                })

        return providers

    def _get_direct_link_from_provider(self) -> str:
        print(self.embeded_link)  # DEBUG
        if self.arguments.provider == "Vidmoly":
            return get_direct_link_from_vidmoly(embeded_vidmoly_link=self.embeded_link)
        if self.arguments.provider == "Vidoza":
            return get_direct_link_from_vidoza(embeded_vidoza_link=self.embeded_link)
        if self.arguments.provider == "VOE":
            return get_direct_link_from_voe(embeded_voe_link=self.embeded_link)

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

        self.html = requests.get(self.link, timeout=DEFAULT_REQUEST_TIMEOUT)

        title_german, title_english = self._get_episode_title_from_html()
        self.title_german = title_german
        self.title_english = title_english

        self.language = self._get_available_language_from_html()
        self.provider = self._get_provider_from_html()

        anime_title = get_anime_title_from_html(html=self.html)
        self.mal_id = get_mal_id_from_title(title=anime_title, season=self.season)

        if self.arguments.provider and self.arguments.language:
            redirect_links = self.provider.get(self.arguments.provider)

            for item in redirect_links:
                print(item)
                if int(item['language']) == self.provider.language:
                    self.redirect_link = item['redirect_link']  # TODO fix

            print(self.redirect_link)

        # self.embeded_link = requests.get(self.redirect_link, timeout=DEFAULT_REQUEST_TIMEOUT, allow_redirects=True).url
        self.embeded_link = requests.get(
            "https://aniworld.to/redirect/2835852",  # TODO - this is hardcoded
            timeout=DEFAULT_REQUEST_TIMEOUT,
            allow_redirects=True
        ).url

        self.direct_link = self._get_direct_link_from_provider()  # TODO - fix

    def __str__(self) -> str:
        return (
            f"Episode(title_german={self.title_german}, title_english={self.title_english}, "
            f"season={self.season}, episode={self.episode}, slug={self.slug}, "
            f"link={self.link}, mal_id={self.mal_id}, redirect_link={self.redirect_link}, provider={self.provider}, "
            f"language={self.language}, html={self.html})"
        )

    def to_pretty_string(self) -> str:
        provider_str = "{\n"
        for provider, entries in self.provider.items():
            provider_str += f"\t\t'{provider}': [\n"
            for entry in entries:
                provider_str += (
                    f"\t\t\t{{'redirect_link': '{entry['redirect_link']}', "
                    f"'language': {entry['language']}}},\n"
                )
            provider_str += "\t\t],\n"
        provider_str += "\t}"

        return (
            f"Episode(\n"
            f"\ttitle_german=\"{self.title_german}\",\n"
            f"\ttitle_english=\"{self.title_english}\",\n"
            f"\tseason={self.season},\n"
            f"\tepisode={self.episode},\n"
            f"\tslug=\"{self.slug}\",\n"
            f"\tlink=\"{self.link}\",\n"
            f"\tmal_id={self.mal_id},\n"
            f"\tprovider={provider_str},\n"
            f"\tlanguage={self.language},\n"
            f"\thtml={self.html}\n"
            f")"
        )
