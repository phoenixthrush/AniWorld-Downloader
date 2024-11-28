import re
import pathlib
import logging

import requests
import requests.models
from bs4 import BeautifulSoup


REQUEST_TIMEOUT = 15


# ANISKIP FUNCTIONS

def get_mal_id_from_title(title: str, season: int) -> int:
    logging.debug("Fetching MAL ID for: %s", title)

    name = re.sub(r' \(\d+ episodes\)', '', title)
    logging.debug("Processed name: %s", name)

    keyword = re.sub(r'\s+', '%20', name)
    logging.debug("Keyword for search: %s", keyword)

    response = requests.get(
        f"https://myanimelist.net/search/prefix.json?type=anime&keyword={keyword}",
        timeout=REQUEST_TIMEOUT
    )
    logging.debug("Response status code: %d", response.status_code)

    if response.status_code != 200:
        logging.error("Failed to fetch MyAnimeList data. HTTP Status: %d", response.status_code)
        raise ValueError("Error fetching data from MyAnimeList.")

    mal_metadata = response.json()
    results = [entry['name'] for entry in mal_metadata['categories'][0]['items']]
    logging.debug("Search results: %s", results)

    if not results:
        logging.error("No match found!")
        raise ValueError("No match found!")

    best_match = results[0]
    logging.debug("Best match: %s", best_match)

    for entry in mal_metadata['categories'][0]['items']:
        if entry['name'] == best_match:
            anime_id = entry['id']
            logging.debug("Found MAL ID: %s for %s", anime_id, best_match)

            while season > 1:
                url = f"https://myanimelist.net/anime/{anime_id}"
                logging.debug("Fetching URL: %s", url)

                response = requests.get(url, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, 'html.parser')
                sequel_div = soup.find("div", string=lambda text: text and "Sequel" in text and "(TV)" in text)

                if not sequel_div:
                    error_msg = "Sequel (TV) not found"
                    logging.error(error_msg)
                    raise ValueError(error_msg)

                title_div = sequel_div.find_next("div", class_="title")
                if not title_div:
                    error_msg = "No 'title'-Div found"
                    logging.error(error_msg)
                    raise ValueError(error_msg)

                link_element = title_div.find("a")
                if not link_element:
                    error_msg = "No Link found in 'title'-Div"
                    logging.error(error_msg)
                    raise ValueError(error_msg)

                link_url = link_element.get("href")
                logging.debug("Found Link: %s", link_url)
                match = re.search(r'/anime/(\d+)', link_url)

                if not match:
                    error_msg = "No Anime-ID found in the link URL"
                    logging.error(error_msg)
                    raise ValueError(error_msg)

                anime_id = match.group(1)
                logging.debug("Anime ID: %s", anime_id)
                season -= 1

            return anime_id

    error_msg = "No match found!"
    logging.error(error_msg)
    raise ValueError(error_msg)


# END OF ANISKIP FUNCTIONS


# INTERNAL EPISODE FUNCTIONS

def get_episode_title_from_html(html: requests.models.Response) -> str:
    episode_soup = BeautifulSoup(html.content, 'html.parser')
    series_title_div = episode_soup.find('div', class_='series-title')

    if series_title_div:
        episode_title = series_title_div.find('h1').find('span').text  # Kaguya-sama: Love is War
    else:
        return None

    return episode_title


def get_season_from_link(link: str) -> int:
    season = link.split("/")[-2]  # e.g. staffel-2
    numbers = re.findall(r'\d+', season)

    if numbers:
        return int(numbers[-1])  # e.g 2

    raise ValueError(f"No valid season number found in the link: {link}")


def get_episode_from_link(link: str) -> int:
    episode = link.split("/")[-1]  # e.g. episode-2
    numbers = re.findall(r'\d+', episode)

    if numbers:
        return int(numbers[-1])  # e.g 2

    raise ValueError(f"No valid episode number found in the link: {link}")


def get_available_language_from_html(html: requests.models.Response) -> list[int]:
    """
    Language Codes:
        1: German Dub
        2: English Sub
        3: German Sub
    """

    episode_soup = BeautifulSoup(html.content, 'html.parser')
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


def get_provider_from_html(html: requests.models.Response) -> dict:
    soup = BeautifulSoup(html.content, 'html.parser')
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

# END OF INTERNAL EPISODE FUNCTIONS


# INTERNAL EPISODE FUNCTIONS

def get_season_description_from_html(html: requests.models.Response):
    soup = BeautifulSoup(html.content, 'html.parser')
    seri_des_div = soup.find('p', class_='seri_des')
    description = seri_des_div['data-full-description']

    return description

# END OF INTERNAL EPISODE FUNCTIONS


class Anime:
    def __init__(
        self,
        action: str = "Watch",
        aniskip: bool = False,
        only_command: bool = False,
        only_direct_link: bool = False,
        output_directory: str = pathlib.Path.home() / "Downloads",
        episode_list: list = None,
        description: str = None
    ) -> None:
        if not episode_list:
            raise ValueError("Provide 'episode_list'.")

        self.action: str = action
        self.aniskip: bool = aniskip
        self.only_command: bool = only_command
        self.only_direct_link: bool = only_direct_link
        self.output_directory: str = output_directory
        self.episode_list: list = episode_list
        self.description: str = description

        self.auto_fill_details()

    def auto_fill_details(self) -> None:
        self.description = get_season_description_from_html(html=self.episode_list[0].html)

    def __str__(self) -> str:
        return (
            f"Anime(action={self.action}, "
            f"aniskip={self.aniskip}, "
            f"only_command={self.only_command}, "
            f"only_direct_link={self.only_direct_link}, "
            f"output_directory={self.output_directory}, "
            f"episode_list={self.episode_list}, "
            f"description={self.description})"
        )


class Episode:
    def __init__(
        self,
        title: str = None,
        season: int = None,
        episode: int = None,
        slug: str = None,
        link: str = None,
        mal_id: int = None,
        # redirect_link: str = None,
        # embeded_link: str = None,
        # direct_link: str = None,
        provider: str = None,
        language: str = None,
        html: requests.models.Response = None
    ) -> None:
        if not link and not (slug and season and episode):
            raise ValueError("Provide either 'link' or ('slug', 'season', and 'episode').")

        self.title = title
        self.season = season
        self.episode = episode
        self.slug = slug
        self.link = link
        self.mal_id = mal_id
        # self.redirect_link = redirect_link
        # self.embeded_link = embeded_link
        # self.direct_link = direct_link
        self.provider = provider
        self.language = language
        self.html = html

        self.auto_fill_details()

    def auto_fill_details(self) -> None:
        if self.slug and self.season and self.episode:
            self.link = (
                f"https://aniworld.to/anime/stream/{self.slug}/"
                f"staffel-{self.season}/episode-{self.episode}"
            )

        if self.link:
            self.slug = self.slug or self.link.split("/")[-3]
            self.season = self.season or get_season_from_link(link=self.link)
            self.episode = self.episode or get_episode_from_link(link=self.link)

        self.html = requests.get(self.link, timeout=REQUEST_TIMEOUT)

        self.title = self.title or get_episode_title_from_html(html=self.html)
        self.language = get_available_language_from_html(html=self.html)
        self.provider = get_provider_from_html(html=self.html)
        self.mal_id = get_mal_id_from_title(title=self.title, season=self.season)

    def __str__(self) -> str:
        return (
            f"Episode(title={self.title}, season={self.season}, episode={self.episode}, "
            f"slug={self.slug}, link={self.link}, mal_id={self.mal_id}, "
            f"provider={self.provider}, language={self.language}, html={self.html})"
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
            f"\ttitle=\"{self.title}\",\n"
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


def main() -> None:
    episode = Episode(
        link="https://aniworld.to/anime/stream/kaguya-sama-love-is-war/staffel-2/episode-3"
    )
    episode2 = Episode(
        slug="alya-sometimes-hides-her-feelings-in-russian",
        season=1,
        episode=2
    )

    anime = Anime(episode_list=[episode, episode2])

    print(anime)
    print(anime.episode_list[0])
    print(anime.episode_list[1])


if __name__ == "__main__":
    main()
