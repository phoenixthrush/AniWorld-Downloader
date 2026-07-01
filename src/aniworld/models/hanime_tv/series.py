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
        self.__franchise_title = None
        self.__video_title = None

        self.__description = None
        self.__description_html = None

        self.__genres = None
        self.__tags = None
        self.__tag_ids = None
        self.__tag_slugs = None

        self.__release_year = None
        self.__release_date = None
        self.__release_datetime = None
        self.__release_timestamp = None

        self.__poster_url = None
        self.__cover_url = None

        self.__brand = None
        self.__brand_id = None
        self.__brand_slug = None

        self.__video_slug = None
        self.__franchise_slug = None
        self.__video_id = None
        self.__franchise_id = None

        self.__episode_count = None
        self.__episode_slugs = None
        self.__episode_titles = None
        self.__episode_urls = None
        self.__has_multiple_episodes = None

        self.__seasons = None
        self.__season_count = None

        self.__api_data = None

        logger.debug(f"Initialized HanimeTVSeries {self.url}")

    @staticmethod
    def is_valid_url(url):
        """Check whether the url is a valid hanime video url."""

        return bool(
            re.match(
                r"^https?://(?:www\.)?hanime\.tv/videos/hentai/[A-Za-z0-9\-]+/?$",
                url,
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
    def _parse_datetime(ts, fallback=""):
        """Convert a unix timestamp or date string into a datetime."""

        if ts:
            return datetime.fromtimestamp(ts, tz=timezone.utc)

        if fallback:
            try:
                return datetime.fromisoformat(fallback.replace("Z", "+00:00"))
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
    def raw_brand(self):
        """Return the raw brand object."""

        return self._api_data.get("brand") or {}

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
    def franchise_slug(self):
        """Return the franchise slug."""

        if self.__franchise_slug is None:
            self.__franchise_slug = self.raw_franchise.get("slug") or ""
        return self.__franchise_slug

    @property
    def video_id(self):
        """Return the source video id."""

        if self.__video_id is None:
            self.__video_id = self.raw_video.get("id")
        return self.__video_id

    @property
    def franchise_id(self):
        """Return the franchise id."""

        if self.__franchise_id is None:
            self.__franchise_id = self.raw_franchise.get("id")
        return self.__franchise_id

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

    @property
    def title(self):
        """Return the best series title."""

        if self.__title is None:
            self.__title = self.franchise_title
            if not self.__title:
                name = self.video_title
                self.__title = re.sub(r"\s*\d+\s*$", "", name).strip() or name
        return self.__title

    @property
    def title_cleaned(self):
        """Return the cleaned series title."""

        if self.__title_cleaned is None:
            self.__title_cleaned = clean_title(self.title)
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
    def tag_ids(self):
        """Return the tag ids."""

        if self.__tag_ids is None:
            self.__tag_ids = [
                tag["id"]
                for tag in self.tags
                if isinstance(tag, dict) and tag.get("id")
            ]
        return self.__tag_ids

    @property
    def tag_slugs(self):
        """Return the tag slugs."""

        if self.__tag_slugs is None:
            self.__tag_slugs = [
                tag["slug"]
                for tag in self.tags
                if isinstance(tag, dict) and tag.get("slug")
            ]
        return self.__tag_slugs

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
    def release_date(self):
        """Return the release date string."""

        if self.__release_date is None:
            if self.release_datetime:
                self.__release_date = self.release_datetime.date().isoformat()
            else:
                self.__release_date = self.raw_video.get("released_at", "") or ""
        return self.__release_date

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
    def cover_url(self):
        """Return the cover url."""

        if self.__cover_url is None:
            self.__cover_url = (
                self.raw_video.get("cover_url")
                or self.raw_video.get("poster_url")
                or ""
            )
        return self.__cover_url

    @property
    def brand(self):
        """Return the brand name."""

        if self.__brand is None:
            self.__brand = (
                self.raw_brand.get("title") or self.raw_video.get("brand") or ""
            )
        return self.__brand

    @property
    def brand_id(self):
        """Return the brand id."""

        if self.__brand_id is None:
            self.__brand_id = self.raw_brand.get("id")
        return self.__brand_id

    @property
    def brand_slug(self):
        """Return the brand slug."""

        if self.__brand_slug is None:
            self.__brand_slug = self.raw_brand.get("slug") or ""
        return self.__brand_slug

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
    def episode_titles(self):
        """Return the franchise episode titles."""

        if self.__episode_titles is None:
            videos = self.raw_franchise_videos
            if not videos:
                self.__episode_titles = [self.video_title] if self.video_title else []
            else:
                self.__episode_titles = [v["name"] for v in videos if v.get("name")]
        return self.__episode_titles

    @property
    def episode_urls(self):
        """Return the franchise episode urls."""

        if self.__episode_urls is None:
            self.__episode_urls = [
                f"https://hanime.tv/videos/hentai/{slug}" for slug in self.episode_slugs
            ]
        return self.__episode_urls

    @property
    def episode_count(self):
        """Return the episode count."""

        if self.__episode_count is None:
            self.__episode_count = len(self.episode_slugs)
        return self.__episode_count

    @property
    def has_multiple_episodes(self):
        """Return whether the franchise has more than one episode."""

        if self.__has_multiple_episodes is None:
            self.__has_multiple_episodes = self.episode_count > 1
        return self.__has_multiple_episodes

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

    def to_dict(self):
        """Return the series as a dictionary."""

        return {
            "url": self.url,
            "slug": self.slug,
            "video_slug": self.video_slug,
            "franchise_slug": self.franchise_slug,
            "video_id": self.video_id,
            "franchise_id": self.franchise_id,
            "title": self.title,
            "franchise_title": self.franchise_title,
            "video_title": self.video_title,
            "title_cleaned": self.title_cleaned,
            "description": self.description,
            "description_html": self.description_html,
            "genres": self.genres,
            "tags": self.tags,
            "tag_ids": self.tag_ids,
            "tag_slugs": self.tag_slugs,
            "release_year": self.release_year,
            "release_date": self.release_date,
            "release_timestamp": self.release_timestamp,
            "poster_url": self.poster_url,
            "cover_url": self.cover_url,
            "brand": self.brand,
            "brand_id": self.brand_id,
            "brand_slug": self.brand_slug,
            "episode_count": self.episode_count,
            "episode_slugs": self.episode_slugs,
            "episode_titles": self.episode_titles,
            "episode_urls": self.episode_urls,
            "has_multiple_episodes": self.has_multiple_episodes,
            "season_count": self.season_count,
        }

    # -----------------------------
    # public methods
    # -----------------------------

    def download(self):
        print(self.to_dict())
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
