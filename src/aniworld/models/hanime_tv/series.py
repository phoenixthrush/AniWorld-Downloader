import re
from datetime import datetime, timezone

from ...config import logger
from ...extractors.provider.hanime_tv import fetch_hanime_api_data
from ..common import clean_title

HANIME_SEARCH_URL = "https://search.htv-services.com/"


class HanimeTVSeries:
    """
    Represents a franchise (series) on hanime.tv.

    A hanime.tv "franchise" groups multiple video episodes under one title.
    Since hanime.tv doesn't have traditional series pages, this is constructed
    from any episode URL belonging to the franchise.

    Parameters:
        url:    Required. A hanime.tv video URL belonging to the franchise,
                e.g. https://hanime.tv/videos/hentai/ane-yome-quartet-1

    Attributes (Example):
        url:            "https://hanime.tv/videos/hentai/ane-yome-quartet-1"
        title:          "Ane Yome Quartet"
        title_cleaned:  "Ane Yome Quartet"
        description:    "Based of the game by Candy Soft..."
        genres:         ["vanilla", "harem", "big boobs"]
        release_year:   "2015"
        poster_url:     "https://hanime-cdn.com/images/posters/ane-yome-quartet-1.jpg"
        brand:          "Mary Jane"
        seasons:        [<HanimeTVSeason>]
        season_count:   1
    """

    def __init__(self, url: str):
        if not self.is_valid_url(url):
            raise ValueError(f"Invalid hanime.tv URL: {url}")

        self.url = url

        self.__title = None
        self.__title_cleaned = None
        self.__description = None
        self.__genres = None
        self.__release_year = None
        self.__poster_url = None
        self.__brand = None

        self.__seasons = None
        self.__season_count = None

        self.__api_data = None

        logger.debug(f"Initialized HanimeTVSeries {self.url}")

    @staticmethod
    def is_valid_url(url):
        return bool(
            re.match(
                r"^https?://(?:www\.)?hanime\.tv/videos/hentai/[A-Za-z0-9\-]+/?$",
                url,
            )
        )

    @staticmethod
    def _slug_from_url(url):
        return url.rstrip("/").split("/")[-1]

    @property
    def _api_data(self):
        if self.__api_data is None:
            slug = self._slug_from_url(self.url)
            self.__api_data = fetch_hanime_api_data(slug)
        return self.__api_data

    @property
    def title(self):
        if self.__title is None:
            franchise = self._api_data.get("hentai_franchise") or {}
            self.__title = franchise.get("title") or franchise.get("name")
            if not self.__title:
                hv = self._api_data.get("hentai_video") or {}
                name = hv.get("name", "")
                self.__title = re.sub(r"\s*\d+\s*$", "", name).strip() or name
        return self.__title

    @property
    def title_cleaned(self):
        if self.__title_cleaned is None:
            self.__title_cleaned = clean_title(self.title)
        return self.__title_cleaned

    @property
    def description(self):
        if self.__description is None:
            hv = self._api_data.get("hentai_video") or {}
            raw = hv.get("description", "")
            self.__description = re.sub(r"<[^>]+>", "", raw).strip()
        return self.__description

    @property
    def genres(self):
        if self.__genres is None:
            hv = self._api_data.get("hentai_video") or {}
            tags = hv.get("hentai_tags") or []
            self.__genres = [t["text"] for t in tags if isinstance(t, dict) and "text" in t]
        return self.__genres

    @property
    def release_year(self):
        if self.__release_year is None:
            hv = self._api_data.get("hentai_video") or {}
            ts = hv.get("released_at_unix")
            if ts:
                self.__release_year = str(
                    datetime.fromtimestamp(ts, tz=timezone.utc).year
                )
            else:
                released = hv.get("released_at", "")
                if released:
                    self.__release_year = released[:4]
                else:
                    self.__release_year = ""
        return self.__release_year

    @property
    def poster_url(self):
        if self.__poster_url is None:
            hv = self._api_data.get("hentai_video") or {}
            self.__poster_url = hv.get("cover_url") or hv.get("poster_url") or ""
        return self.__poster_url

    @property
    def brand(self):
        if self.__brand is None:
            brand_obj = self._api_data.get("brand") or {}
            self.__brand = brand_obj.get("title") or ""
            if not self.__brand:
                hv = self._api_data.get("hentai_video") or {}
                self.__brand = hv.get("brand") or ""
        return self.__brand

    @property
    def imdb(self):
        return ""

    @property
    def seasons(self):
        if self.__seasons is None:
            self.__seasons = self._build_seasons()
        return self.__seasons

    @property
    def season_count(self):
        if self.__season_count is None:
            self.__season_count = len(self.seasons)
        return self.__season_count

    def _build_seasons(self):
        from .season import HanimeTVSeason

        franchise_videos = self._api_data.get("hentai_franchise_hentai_videos") or []
        if not franchise_videos:
            hv = self._api_data.get("hentai_video")
            if hv:
                franchise_videos = [hv]

        episode_slugs = [v["slug"] for v in franchise_videos if v.get("slug")]

        return [HanimeTVSeason(episode_slugs=episode_slugs, series=self)]

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
