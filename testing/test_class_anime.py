import pathlib
import requests
from bs4 import BeautifulSoup
from aniworld.aniskip import get_mal_id_from_title
from aniworld.config import (
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_ACTION,
    DEFAULT_PROVIDER_DOWNLOAD,
    DEFAULT_PROVIDER_WATCH,
    DEFAULT_LANGUAGE
)
from aniworld.models import Episode


def get_anime_title_from_html(html: requests.models.Response) -> str:
    soup = BeautifulSoup(html.content, 'html.parser')
    title_div = soup.find('div', class_='series-title')

    if title_div:
        return title_div.find('h1').find('span').text

    return ""


class Anime:
    def __init__(
        self,
        title=None,
        slug=None,
        action=DEFAULT_ACTION,
        provider=None,
        language=None,
        aniskip=False,
        only_command=False,
        only_direct_link=False,
        output_directory=pathlib.Path.home() / "Downloads",
        episode_list=None,
        description_german=None,
        description_english=None,
        html=None
    ) -> None:
        if not episode_list:
            raise ValueError("Provide 'episode_list'.")

        self.slug = slug or episode_list[0].slug
        if not self.slug:
            raise ValueError("Slug of Anime is None.")

        self._title = title
        self.action = action
        self.provider = provider or (
            DEFAULT_PROVIDER_DOWNLOAD if action == "Download" else DEFAULT_PROVIDER_WATCH
        )
        self.language = language or DEFAULT_LANGUAGE

        self.aniskip = aniskip
        self.only_command = only_command
        self.only_direct_link = only_direct_link
        self.output_directory = output_directory
        self.episode_list = episode_list

        self._description_german = description_german
        self._description_english = description_english
        self._html = html

    def _fetch_html(self):
        if self._html is None:
            self._html = requests.get(
                f"https://aniworld.to/anime/stream/{self.slug}",
                timeout=DEFAULT_REQUEST_TIMEOUT
            )
        return self._html

    def _fetch_title(self):
        if self._title is None:
            self._title = get_anime_title_from_html(self._fetch_html())
        return self._title

    def _fetch_description_german(self):
        if self._description_german is None:
            soup = BeautifulSoup(self._fetch_html().content, 'html.parser')
            desc_div = soup.find('p', class_='seri_des')
            self._description_german = (
                desc_div.get('data-full-description', '')
                if desc_div else "Could not fetch description."
            )
        return self._description_german

    def _fetch_description_english(self):
        if self._description_english is None:
            anime_id = get_mal_id_from_title(self._fetch_title(), 1)
            response = requests.get(
                f"https://myanimelist.net/anime/{anime_id}",
                timeout=DEFAULT_REQUEST_TIMEOUT
            )
            soup = BeautifulSoup(response.content, 'html.parser')
            desc_meta = soup.find('meta', property='og:description')
            self._description_english = (
                desc_meta['content']
                if desc_meta else "Could not fetch description."
            )
        return self._description_english

    @property
    def html(self):
        return self._fetch_html()

    @property
    def title(self):
        return self._fetch_title()

    @property
    def description_german(self):
        return self._fetch_description_german()

    @property
    def description_english(self):
        return self._fetch_description_english()

    def __iter__(self):
        return iter(self.episode_list)

    def __getitem__(self, index: int):
        return self.episode_list[index]

    def to_json(self) -> str:
        data = {
            "title": self.title,
            "slug": self.slug,
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
        return str(data)

    def __str__(self):
        return self.to_json()


if __name__ == '__main__':
    anime = Anime(
        episode_list=[
            Episode(
                slug="loner-life-in-another-world",
                season=1,
                episode=1
            )
        ]
    )

    print(anime)
