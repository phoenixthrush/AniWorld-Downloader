import re
from bs4 import BeautifulSoup


class Episode:
    def __init__(
        self,
        slug,
        season,
        episode,
        link,
        anime_title=None,
        title_german=None,
        title_english=None,
        html_content=None,
        mal_id=None,
        redirect_link=None,
        embeded_link=None,
        direct_link=None,
        provider=None,
        provider_name=None,
        language=None,
        language_name=None,
        season_episode_count=None,
        movie_episode_count=None
    ):
        self._slug = slug
        self._season = season
        self._episode = episode
        self._link = link
        self._anime_title = anime_title
        self._title_german = title_german
        self._title_english = title_english
        self._html_content = html_content
        self._mal_id = mal_id
        self._redirect_link = redirect_link
        self._embeded_link = embeded_link
        self._direct_link = direct_link
        self._provider = provider
        self._provider_name = provider_name
        self._language = language
        self._language_name = language_name
        self._season_episode_count = season_episode_count
        self._movie_episode_count = movie_episode_count

    @property
    def slug(self):
        return self._slug

    @property
    def season(self):
        return self._season

    @property
    def episode(self):
        return self._episode

    @property
    def anime_title(self):
        if self._anime_title is None:
            self._anime_title = self._fetch_anime_title()
        return self._anime_title

    @property
    def title_german(self):
        if self._title_german is None:
            self._title_german = self._fetch_titles()[0]
        return self._title_german

    @property
    def title_english(self):
        if self._title_english is None:
            self._title_english = self._fetch_titles()[1]
        return self._title_english

    @property
    def link(self):
        if self._link is None:
            self._link = f"https://aniworld.to/anime/stream/{self.slug}/staffel-{self.season}/episode-{self.episode}"
        return self._link

    @property
    def html_content(self):
        if self._html_content is None:
            self._html_content = self._fetch_html()
        return self._html_content

    @property
    def mal_id(self):
        return self._mal_id

    @property
    def redirect_link(self):
        return self._redirect_link

    @property
    def embeded_link(self):
        return self._embeded_link

    @property
    def direct_link(self):
        return self._direct_link

    @property
    def provider(self):
        return self._provider

    @property
    def provider_name(self):
        return self._provider_name

    @property
    def language(self):
        return self._language

    @property
    def language_name(self):
        return self._language_name

    @property
    def season_episode_count(self):
        return self._season_episode_count

    @property
    def movie_episode_count(self):
        return self._movie_episode_count

    def _fetch_anime_title(self):
        return "Placeholder Anime Title"

    def _fetch_titles(self):
        return "German Title", "English Title"

    def _fetch_html(self):
        return "<html></html>"

    def _get_episode_title_from_html(self):
        episode_soup = BeautifulSoup(self.html_content, 'html.parser')
        episode_german_title_div = episode_soup.find('span', class_='episodeGermanTitle')
        episode_english_title_div = episode_soup.find('small', class_='episodeEnglishTitle')

        german_title = episode_german_title_div.text if episode_german_title_div else ""
        english_title = episode_english_title_div.text if episode_english_title_div else ""

        return german_title, english_title

    def _get_season_from_link(self):
        season = self.link.split("/")[-2]
        numbers = re.findall(r'\d+', season)

        if numbers:
            return int(numbers[-1])

        raise ValueError(f"No valid season number found in the link: {self.link}")

    def _get_episode_from_link(self):
        episode = self.link.split("/")[-1]
        numbers = re.findall(r'\d+', episode)

        if numbers:
            return int(numbers[-1])

        raise ValueError(f"No valid episode number found in the link: {self.link}")

    def __str__(self):
        return (
            f"Episode(slug='{self.slug}', season={self.season}, episode={self.episode}, "
            f"anime_title='{self.anime_title}', title_german='{self.title_german}', "
            f"title_english='{self.title_english}', link='{self.link}', mal_id={self.mal_id}, "
            f"redirect_link='{self.redirect_link}', embeded_link='{self.embeded_link}', "
            f"direct_link='{self.direct_link}', provider={self.provider}, "
            f"provider_name={self.provider_name}, language={self.language}, "
            f"language_name={self.language_name}, season_episode_count={self.season_episode_count}, "
            f"movie_episode_count={self.movie_episode_count})"
        )


if __name__ == '__main__':
    episode = Episode(
        slug="loner-life-in-another-world",
        season=1,
        episode=1
    )

    print(episode)
