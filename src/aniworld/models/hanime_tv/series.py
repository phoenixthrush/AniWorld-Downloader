import re
from datetime import UTC, datetime
from html import unescape

from ...config import logger
from ...extractors.provider.hanime_tv import fetch_hanime_api_data
from ..common import clean_title


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
        seasons:        [<HanimeTVSeason>]
        season_count:   1
    """

    def __init__(self, url: str):
        if not self.is_valid_url(url):
            raise ValueError(f"Invalid hanime.tv URL: {url}")

        self.url = url

        self.__title = None
        self.__title_cleaned = None
        self.__franchise_title = None
        self.__video_title = None

        self.__description = None
        self.__description_html = None

        self.__genres = None
        self.__tags = None

        self.__release_year = None
        self.__release_datetime = None
        self.__release_timestamp = None

        self.__poster_url = None

        self.__video_slug = None

        self.__episode_slugs = None

        self.__seasons = None
        self.__season_count = None

        self.__api_data = None

        logger.debug(f"Initialized HanimeTVSeries {self.url}")

    @staticmethod
    def is_valid_url(url):
        """Check whether the url is a valid hanime video url."""

        return bool(
            re.match(
                r"^https?://(?:www\.)?hanime\.tv/"
                r"(?:videos/hentai|hentai/video|playlists/[0-9a-z]+/video)/"
                r"[A-Za-z0-9\-]+/?$",
                url,
                re.IGNORECASE,
            )
        )

    @staticmethod
    def _slug_from_url(url):
        """Get the last path part from a hanime url."""

        return url.rstrip("/").split("/")[-1]

    @staticmethod
    def _strip_html(value):
        """Remove html tags from text."""

        if not value:
            return ""
        return re.sub(r"<[^>]+>", "", value).strip()

    @staticmethod
    def _title_from_slug(slug):
        """Build a readable title from a hanime slug."""

        if not slug:
            return ""
        title = re.sub(r"-\d+$", "", slug)
        title = title.replace("-", " ").strip()
        return title.title()

    @staticmethod
    def _parse_datetime(ts, fallback=""):
        """Convert a unix timestamp or date string into a datetime."""

        if ts:
            return datetime.fromtimestamp(ts, tz=UTC)

        if fallback:
            try:
                return datetime.fromisoformat(fallback)
            except ValueError:
                return None

        return None

    @property
    def _api_data(self):
        if self.__api_data is None:
            slug = self._slug_from_url(self.url)
            self.__api_data = fetch_hanime_api_data(slug)
        return self.__api_data

    @property
    def raw_video(self):
        """Return the raw hentai_video object."""

        return self._api_data.get("hentai_video") or {}

    @property
    def raw_franchise(self):
        """Return the raw hentai_franchise object."""

        return self._api_data.get("hentai_franchise") or {}

    @property
    def raw_franchise_videos(self):
        """Return the raw franchise video list."""

        return self._api_data.get("hentai_franchise_hentai_videos") or []

    @property
    def slug(self):
        """Return the series input slug."""

        return self._slug_from_url(self.url)

    @property
    def video_slug(self):
        """Return the source video slug."""

        if self.__video_slug is None:
            self.__video_slug = self.raw_video.get("slug") or self.slug
        return self.__video_slug

    @property
    def franchise_title(self):
        """Return the franchise title."""

        if self.__franchise_title is None:
            self.__franchise_title = (
                self.raw_franchise.get("title") or self.raw_franchise.get("name") or ""
            )
        return self.__franchise_title

    @property
    def video_title(self):
        """Return the current video title."""

        if self.__video_title is None:
            self.__video_title = self.raw_video.get("name", "")
        return self.__video_title

    @staticmethod
    def strip_episode_number(name):
        """Drop the trailing episode number from a video name."""

        if not name:
            return ""
        return re.sub(r"\s*\d+$", "", name).strip() or name

    def video_title_for_slug(self, slug):
        """Return one franchise video's own name, by slug.

        The franchise list comes with the api data we already fetched, so this
        never costs an extra request.
        """

        for video in self.raw_franchise_videos:
            if video.get("slug") == slug:
                return video.get("name") or ""
        return ""

    @property
    def title(self):
        """Return the best series title."""

        if self.__title is None:
            self.__title = self.franchise_title
            if not self.__title:
                self.__title = self.strip_episode_number(self.video_title)
            if not self.__title:
                self.__title = self._title_from_slug(self.slug)
        return self.__title

    @property
    def title_cleaned(self):
        """Return the cleaned series title."""

        if self.__title_cleaned is None:
            self.__title_cleaned = clean_title(unescape(self.title))
        return self.__title_cleaned

    @property
    def description_html(self):
        """Return the raw html description."""

        if self.__description_html is None:
            self.__description_html = self.raw_video.get("description", "") or ""
        return self.__description_html

    @property
    def description(self):
        """Return the plain text description."""

        if self.__description is None:
            self.__description = self._strip_html(self.description_html)
        return self.__description

    @property
    def tags(self):
        """Return the raw tag objects."""

        if self.__tags is None:
            self.__tags = self.raw_video.get("hentai_tags") or []
        return self.__tags

    @property
    def genres(self):
        """Return the tag text list."""

        if self.__genres is None:
            self.__genres = [
                tag["text"]
                for tag in self.tags
                if isinstance(tag, dict) and tag.get("text")
            ]
        return self.__genres

    @property
    def release_timestamp(self):
        """Return the release timestamp."""

        if self.__release_timestamp is None:
            self.__release_timestamp = self.raw_video.get("released_at_unix")
        return self.__release_timestamp

    @property
    def release_datetime(self):
        """Return the release datetime."""

        if self.__release_datetime is None:
            self.__release_datetime = self._parse_datetime(
                self.release_timestamp,
                self.raw_video.get("released_at", ""),
            )
        return self.__release_datetime

    @property
    def release_year(self):
        """Return the release year."""

        if self.__release_year is None:
            if self.release_datetime:
                self.__release_year = str(self.release_datetime.year)
            else:
                released = self.raw_video.get("released_at", "") or ""
                self.__release_year = released[:4] if released else ""
        return self.__release_year

    @property
    def poster_url(self):
        """Return the poster url."""

        if self.__poster_url is None:
            self.__poster_url = (
                self.raw_video.get("cover_url")
                or self.raw_video.get("poster_url")
                or ""
            )
        return self.__poster_url

    @property
    def episode_slugs(self):
        """Return the franchise episode slugs."""

        if self.__episode_slugs is None:
            videos = self.raw_franchise_videos
            if not videos:
                if self.video_slug:
                    self.__episode_slugs = [self.video_slug]
                else:
                    self.__episode_slugs = []
            else:
                self.__episode_slugs = [v["slug"] for v in videos if v.get("slug")]
        return self.__episode_slugs

    @property
    def imdb(self):
        """Return imdb id if supported."""

        return ""

    @property
    def seasons(self):
        """Return the season list."""

        if self.__seasons is None:
            self.__seasons = self._build_seasons()
        return self.__seasons

    @property
    def season_count(self):
        """Return the season count."""

        if self.__season_count is None:
            self.__season_count = len(self.seasons)
        return self.__season_count

    def _build_seasons(self):
        """Build the season list."""

        from .season import HanimeTVSeason

        return [HanimeTVSeason(episode_slugs=self.episode_slugs, series=self)]

    # -----------------------------
    # public methods
    # -----------------------------

    def download(self):
        # One failed episode must not abandon the rest of the batch.
        for season in self.seasons:
            season.download()

    def watch(self):
        # One failed episode must not abandon the rest of the batch.
        for season in self.seasons:
            season.watch()

    def syncplay(self):
        # One failed episode must not abandon the rest of the batch.
        for season in self.seasons:
            season.syncplay()
