from ...config import GLOBAL_SESSION, HIANIME_SEASON_PATTERN, logger


class HiAnimeSeason:
    """
    Represents a single season (or a movie collection) of an HiAnime anime series.

    Parameters:
        url:        Required. The HiAnime URL for this season, e.g.
                    https://hianime.to/kaguya-sama-love-is-war-season-2-23
                    or
                    https://???
        series:     <Parent series object>

    Attributes (Example):
        series:         <HiAnimeSeries object>
        url:            "https://hianime.to/kaguya-sama-love-is-war-season-2-23"
        are_movies:     false
        season_number:  2
        episode_count:  12
        episodes:       [<hianime.models.hianime_to.episode.HiAnimeEpisode object at 0x10b2023c0>, [...]]
        _html:          "<!doctype html>[...]"

    Methods:
        download()
        watch()
        syncplay()
    """

    def __init__(self, url: str, series=None):
        if not self.is_valid_hianime_season_url(url):
            raise ValueError(f"Invalid HiAnime season URL: {url}")

        self.url = url

        self._series = series

        self.__are_movies = None
        self.__season_number = None
        self.__episode_count = None
        self.__episodes = None

        self.__html = None

    # -----------------------------
    # STATIC METHODS
    # -----------------------------

    @staticmethod
    def is_valid_aniworld_season_url(url):
        """
        Checks if the URL is a valid AniWorld season URL.
        """

        # https://aniworld.to/anime/stream/highschool-dxd/staffel-1
        # or
        # https://aniworld.to/anime/stream/highschool-dxd/filme

        url = url.strip()

        return bool(HIANIME_SEASON_PATTERN.match(url))

    # -----------------------------
    # PUBLIC PROPERTIES (lazy load)
    # -----------------------------

    @property
    def series(self):
        if self._series is None:
            # Extract series URL from season URL by removing /staffel-X or /filme part
            if self.are_movies:
                series_url = self.url.split("/filme")[0]
            else:
                series_url = self.url.split("/staffel-")[0]
            from .series import HiAnimeSeries

            self._series = HiAnimeSeries(series_url)
        return self._series

    @property
    def _html(self):
        if self.__html is None:
            logger.debug(f"fetching ({self.url})...")
            resp = GLOBAL_SESSION.get(self.url)
            self.__html = resp.text
        return self.__html

    @property
    def are_movies(self):
        if self.__are_movies is None:
            self.__are_movies = self.__check_if_are_movies()
        return self.__are_movies

    @property
    def season_number(self):
        if self.__season_number is None:
            self.__season_number = self.__extract_season_number()
        return self.__season_number

    @property
    def episodes(self):
        if self.__episodes is None:
            self.__episodes = self.__extract_episodes()
        return self.__episodes

    @property
    def episode_count(self):
        if self.__episode_count is None:
            # If episodes are already extracted, use that count
            if self.__episodes is not None:
                self.__episode_count = len(self.__episodes)
            else:
                self.__episode_count = self.__extract_episode_count()
        return self.__episode_count

    # -----------------------------
    # Extraction helpers
    # -----------------------------

    def __check_if_are_movies(self):
        return None

    def __extract_season_number(self):
        return None

    def __extract_episodes(self):
        return None

    def __extract_episode_count(self):
        return None

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
