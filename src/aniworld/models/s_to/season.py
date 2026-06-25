import re
from urllib.parse import urljoin

from ...config import GLOBAL_SESSION, SERIENSTREAM_SEASON_PATTERN, logger


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
    def _html(self):
        if self.__html is None:
            logger.debug(f"fetching ({self.url})...")
            resp = GLOBAL_SESSION.get(self.url)
            self.__html = resp.text
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

        # Support both absolute and relative links.
        pattern = (
            r'<a\s+href="(?:https?://(?:serienstream|s)\.to)?/serie/.+/staffel-'
            + str(self.season_number)
            + r'/episode-\d+"'
        )

        matches = re.findall(pattern, self._html)

        return len(matches)

    def __extract_episodes(self):
        """
        <a href="https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir/staffel-1/episode-1"
                    <a href="https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir/staffel-1/episode-2"
                    <a href="https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir/staffel-1/episode-3"
                    [...]
        """
        from .episode import SerienstreamEpisode

        pattern = (
            r'<a\s+href="(?P<href>(?:https?://(?:serienstream|s)\.to)?/serie/.+/staffel-'
            + str(self.season_number)
            + r'/episode-\d+)"'
        )

        matches = re.findall(pattern, self._html)
        episode_list = []

        seen = set()
        for match in matches:
            full_url = urljoin(self.url, match)
            if full_url in seen:
                continue
            seen.add(full_url)
            episode_list.append(
                SerienstreamEpisode(full_url, season=self, series=self.series)
            )

        return episode_list

    # -----------------------------
    # PUBLIC METHODS
    # -----------------------------
    def download(self):
        for episode in self.episodes:
            episode.download()

    def watch(self):
        for episode in self.episodes:
            episode.watch()

    def syncplay(self):
        for episode in self.episodes:
            episode.syncplay()
