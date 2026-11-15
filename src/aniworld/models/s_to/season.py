import re
from html import unescape
from urllib.parse import urljoin, urlsplit

from ...config import SERIENSTREAM_SEASON_PATTERN, STO_HOST_PATTERN, logger
from ..common import run_each
from .http import response_text, sto_get


class SerienstreamSeason:
    """
    Represents a single season of an Serienstream series.

    Parameters:
        url:        Required. The Serienstream URL for this season, e.g.
                    https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir/staffel-1
        series:     <Parent series object>

    Attributes (Example):
        series:         <SerienstreamSeries object>
        url:            "https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir/staffel-1"
        season_number:  1
        episode_count:  12
        episodes:       [<aniworld.models.s_to.episode.SerienstreamEpisode object at 0x108d2ae40>, ...]
        _html:          "<!doctype html>[...]"

    Methods:
        download()
        watch()
        syncplay()

    Attributes That Do Not Exists as on Aniworld:
        are_movies
    """

    def __init__(self, url, series=None):
        if not self.__is_valid_serienstream_season_url(url):
            raise ValueError(f"Invalid Serienstream season URL: {url}")

        self.url = url
        self._series = series

        self.__season_number = None
        self.__episode_count = None
        self.__episodes = None
        self.__episode_languages = None

        self.__html = None

    # -----------------------------
    # STATIC METHODS
    # -----------------------------

    @staticmethod
    def __is_valid_serienstream_season_url(url):
        """
        Checks if the URL is a valid Serienstream season URL.
        """

        return bool(SERIENSTREAM_SEASON_PATTERN.match(url))

    # -----------------------------
    # PUBLIC PROPERTIES (lazy load)
    # -----------------------------

    @property
    def series(self):
        if self._series is None:
            series_url = self.url.rsplit("/staffel-", 1)[0]
            from .series import SerienstreamSeries

            self._series = SerienstreamSeries(series_url)
        return self._series

    @property
    def season_number(self):
        if self.__season_number is None:
            self.__season_number = self.__extract_season_number()
        return self.__season_number

    @property
    def episode_count(self):
        if self.__episode_count is None:
            self.__episode_count = self.__extract_episode_count()
        return self.__episode_count

    @property
    def episodes(self):
        if self.__episodes is None:
            self.__episodes = self.__extract_episodes()
        return self.__episodes

    @property
    def episode_languages(self):
        """Language badges keyed by episode number, parsed from this page."""
        if self.__episode_languages is None:
            self.__episode_languages = self.__extract_episode_languages()
        return self.__episode_languages

    @property
    def _html(self):
        if self.__html is None:
            logger.debug(f"fetching ({self.url})...")
            resp = sto_get(self.url)
            self.__html = response_text(resp, self.url)
        return self.__html

    # -----------------------------
    # PRIVATE EXTRACTION FUNCTIONS
    # -----------------------------

    def __extract_season_number(self):
        """
        Extract from URL the season number.
        """

        return int(self.url.rstrip("/").split("-")[-1])

    def __extract_episode_count(self):
        """
        <a href="https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir/staffel-1/episode-1"
                    <a href="https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir/staffel-1/episode-2"
                    <a href="https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir/staffel-1/episode-3"
                    [...]
        """

        return len({urljoin(self.url, url) for url in self.__episode_urls(self._html)})

    def __episode_urls(self, html):
        # Support links on older pages and onclick rows on current pages.
        season_path = re.escape(urlsplit(self.url).path.rstrip("/"))
        return re.findall(
            rf"(?:href|window\.location)\s*=\s*[\"']((?:https?://{STO_HOST_PATTERN})?"
            rf"{season_path}/episode-\d+)[\"']",
            html,
            re.IGNORECASE,
        )

    def __extract_episodes(self):
        """
        <a href="https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir/staffel-1/episode-1"
                    <a href="https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir/staffel-1/episode-2"
                    <a href="https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir/staffel-1/episode-3"
                    [...]
        """
        from .episode import SerienstreamEpisode

        matches = self.__episode_urls(self._html)
        episode_list = []

        titles = {}
        for row in re.findall(r"<tr\b[^>]*>.*?</tr>", self._html, re.DOTALL):
            urls = self.__episode_urls(row)
            if not urls:
                continue
            values = []
            for tag, name in (("strong", "ger"), ("span", "eng")):
                title = re.search(
                    rf'<{tag}\b[^>]*class=["\'][^"\']*\bepisode-title-{name}\b[^"\']*["\'][^>]*>(.*?)</{tag}>',
                    row,
                    re.DOTALL,
                )
                values.append(unescape(title.group(1)).strip() if title else None)
            titles[urljoin(self.url, urls[0])] = values

        seen = set()
        for match in matches:
            full_url = urljoin(self.url, match)
            if full_url in seen:
                continue
            seen.add(full_url)
            title_de, title_en = titles.get(full_url, (None, None))
            episode_list.append(
                SerienstreamEpisode(
                    full_url,
                    season=self,
                    series=self.series,
                    title_de=title_de,
                    title_en=title_en,
                )
            )

        return episode_list

    def __extract_episode_languages(self):
        """Read flags from episode rows without fetching every episode page."""
        rows = re.findall(
            r'<tr\b(?=[^>]*class=["\'][^"\']*\bepisode-row\b)[^>]*>.*?</tr>',
            self._html,
            re.IGNORECASE | re.DOTALL,
        )
        languages = {}
        for row in rows:
            match = re.search(r"/episode-(\d+)", row, re.IGNORECASE)
            if not match:
                continue
            labels = []
            flags = set(re.findall(r"\bsvg-flag-[\w-]+", row.lower()))
            if "svg-flag-german" in flags:
                labels.append("German Dub")
            if "svg-flag-english" in flags:
                labels.append("English Dub")
            # Subtitle-only rows have flags, but no supported dub. Keep them
            # empty so the UI does not borrow another episode's languages.
            if flags:
                languages[int(match.group(1))] = tuple(labels)
        return languages

    # -----------------------------
    # PUBLIC METHODS
    # -----------------------------
    def download(self):
        # One failed episode must not abandon the rest of the batch.
        run_each(self.episodes, "download")

    def watch(self):
        # One failed episode must not abandon the rest of the batch.
        run_each(self.episodes, "watch")

    def syncplay(self):
        # One failed episode must not abandon the rest of the batch.
        run_each(self.episodes, "syncplay")
