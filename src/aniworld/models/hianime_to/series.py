from ...config import GLOBAL_SESSION, HIANIME_SERIES_PATTERN, logger
from ..common import clean_title


class HiAnimeSeries:
    """
    Represents a series on HiAnime.

    Parameters:
        url:    Required. Must be a valid HiAnime series URL,
                e.g. https://hianime.to/kaguya-sama-love-is-war-123

    Attributes (Example):
        url:            "https://hianime.to/kaguya-sama-love-is-war-123"
        title:          "Kaguya-sama: Love is War"
        title_cleaned:  "Kaguya-sama Love is War"
        title_jp:       "かぐや様は告らせたい～天才たちの恋愛頭脳戦～"
        aired:          "Jan 12, 2019 to Mar 30, 2019"
        status:         "Finished Airing"
        description:    "At the renowned Shuchiin Academy, Miyuki Shirogane and Kaguya Shinomiya are the student [...]"
        genres:         ["Comedy", "Romance", "School", "Psychological", "Seinen"]
        studios:        ["A-1 Pictures"]
        release_year:   "2019"
        poster_url:     "https://cdn.noitatnemucod.net/thumbnail/300x400/100/f4f7470c7b0fedc1df5ec703c2d7fbc0.jpg"
        producer:       ["Aniplex", [...]]
        age_rating:     "PG-13"
        rating:         "8.4"
        imdb:           ""
        mal_id:         ""
        has_movies:     true
        seasons:        [<aniworld.models.hianime.season.HiAnimeSeason object at 0x106d427b0>, ...]
        season_count:   0
        _html:          "<!DOCTYPE html>[...]"

    Methods:
        download()
        watch()
        syncplay()
    """

    def __init__(self, url: str):
        if not self.is_valid_aniworld_series_url(url):
            raise ValueError(f"Invalid HiAnime series URL: {url}")

        self.url = url

        self.__title = None
        self.__title_cleaned = None
        self.__title_jp = None
        self.__aired = None
        self.__status = None
        self.__description = None
        self.__genres = None
        self.__studios = None
        self.__release_year = None
        self.__poster_url = None
        self.__producer = None
        self.__age_rating = None
        self.__rating = None
        self.__imdb = None

        self.__mal_id = None

        self.__has_movies = None

        self.__seasons = None
        self.__season_count = None

        self.__html = None

    # -----------------------------
    # STATIC METHODS
    # -----------------------------

    @staticmethod
    def is_valid_aniworld_series_url(url):
        """Checks if the URL is a valid AniWorld series URL."""

        return bool(HIANIME_SERIES_PATTERN.match(url))

    # -----------------------------
    # PUBLIC PROPERTIES (lazy load)
    # -----------------------------

    @property
    def _html(self):
        if self.__html is None:
            logger.debug(f"fetching ({self.url})...")
            resp = GLOBAL_SESSION.get(self.url)
            self.__html = resp.text
        return self.__html

    @property
    def title(self):
        if self.__title is None:
            self.__title = self.__extract_title()
        return self.__title

    @property
    def title_cleaned(self):
        if self.__title_cleaned is None:
            self.__title_cleaned = clean_title(self.title)
        return self.__title_cleaned

    @property
    def title_jp(self):
        if self.__title_jp is None:
            self.__title_jp = self.__extract_title_jp()
        return self.__title_jp

    @property
    def aired(self):
        if self.__aired is None:
            self.__aired = self.__extract_aired()
        return self.__aired

    @property
    def status(self):
        if self.__status is None:
            self.__status = self.__extract_status()
        return self.__status

    @property
    def genres(self):
        if self.__genres is None:
            self.__genres = self.__extract_genres()
        return self.__genres

    @property
    def studios(self):
        if self.__studios is None:
            self.__studios = self.__extract_studios()
        return self.__studios

    @property
    def release_year(self):
        if self.__release_year is None:
            self.__release_year = self.__extract_release_year()
        return self.__release_year

    @property
    def poster_url(self):
        if self.__poster_url is None:
            self.__poster_url = self.__extract_poster_url()
        return self.__poster_url

    @property
    def producer(self):
        if self.__producer is None:
            self.__producer = self.__extract_producer()
        return self.__producer

    @property
    def age_rating(self):
        if self.__age_rating is None:
            self.__age_rating = self.__extract_age_rating()
        return self.__age_rating

    @property
    def rating(self):
        if self.__rating is None:
            self.__rating = self.__extract_rating()
        return self.__rating

    @property
    def imdb(self):
        if self.__imdb is None:
            self.__imdb = self.__extract_imdb()
        return self.__imdb

    @property
    def mal_id(self):
        if self.__mal_id is None:
            self.__mal_id = self.__extract_mal_id()
        return self.__mal_id

    @property
    def has_movies(self):
        if self.__has_movies is None:
            self.__has_movies = self.__extract_has_movies()
        return self.__has_movies

    @property
    def seasons(self):
        if self.__seasons is None:
            self.__seasons = self.__extract_seasons()
        return self.__seasons

    @property
    def season_count(self):
        if self.__season_count is None:
            self.__season_count = self.__extract_season_count()
        return self.__season_count

    @property
    def description(self):
        if self.__description is None:
            self.__description = self.__extract_description()
        return self.__description

    # -----------------------------
    # PRIVATE EXTRACTION FUNCTIONS
    # -----------------------------

    def __extract_title(self):
        return ""

    def __extract_title_jp(self):
        return ""

    def __extract_aired(self):
        return ""

    def __extract_status(self):
        return ""

    def __extract_description(self):
        return ""

    def __extract_genres(self):
        return []

    def __extract_studios(self):
        return []

    def __extract_release_year(self):
        return ""

    def __extract_poster_url(self):
        return ""

    def __extract_producer(self):
        return []

    def __extract_age_rating(self):
        return ""

    def __extract_rating(self):
        return ""

    def __extract_imdb(self):
        return ""

    def __extract_mal_id(self):
        return ""

    def __extract_has_movies(self):
        return False

    def __extract_seasons(self):
        return []

    def __extract_season_count(self):
        return 0

    # -----------------------------
    # PUBLIC METHODS
    # -----------------------------

    def download(self):
        for season in self.seasons:
            for episode in season.episodes:
                episode.download()

    def watch(self):
        for season in self.seasons:
            for episode in season.episodes:
                episode.watch()

    def syncplay(self):
        for season in self.seasons:
            for episode in season.episodes:
                episode.syncplay()
