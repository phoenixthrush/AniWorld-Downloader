import re
from html import unescape
from urllib.parse import urljoin, urlparse

from ...config import SERIENSTREAM_SERIES_PATTERN, STO_HOST_PATTERN, logger
from ..common import clean_title
from .http import response_text, sto_get


class SerienstreamSeries:
    """
    Represents a series on Serienstream.

    Parameters:
        url:    Required. Must be a valid Serienstream series URL,
                e.g. https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir

    Attributes (Example):
        url:            "https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir"
        title:          "American Horror Story"
        title_cleaned:  "American Horror Story"
        description:    "„American Horror Story“ ist eine US-amerikanische Horror - Fernsehserie. [...]"
        genres:         ['Horror']
        release_year:   "2011"
        poster_url:     "https://serienstream.to/media/images/channel/desktop/hannibal-z64ax0l0?format=jpg"
        imdb:           "tt1844624"
        seasons:        [<aniworld.models.s_to.season.SerienstreamSeason object at 0x106d427b0>, ...]
        season_count:   13
        _html:          "<!DOCTYPE html>[...]"

    Methods:
        download()
        watch()
        syncplay()

    Attributes That Do Not Exists as on Aniworld:
        mal_id, has_movies
    """

    def __init__(self, url: str):
        if not self.__is_valid_serienstream_series_url(url):
            raise ValueError(f"Invalid Serienstream series URL: {url}")

        self.url = url

        self.__title = None
        self.__title_cleaned = None
        self.__description = None
        self.__genres = None
        self.__release_year = None
        self.__poster_url = None
        self.__imdb = None
        self.__seasons = None
        self.__season_count = None
        self.__html = None

        logger.debug(f"Initialized {self.url}")

    # -----------------------------
    # STATIC METHODS
    # -----------------------------

    @staticmethod
    def __is_valid_serienstream_series_url(url):
        """Checks if the URL is a valid Serienstream series URL."""
        return bool(SERIENSTREAM_SERIES_PATTERN.match(url))

    # -----------------------------
    # PUBLIC PROPERTIES (lazy load)
    # -----------------------------

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
    def description(self):
        if self.__description is None:
            self.__description = self.__extract_description()
        return self.__description

    @property
    def genres(self):
        if self.__genres is None:
            self.__genres = self.__extract_genres()
        return self.__genres

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
    def imdb(self):
        if self.__imdb is None:
            self.__imdb = self.__extract_imdb()
        return self.__imdb

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
    def _html(self):
        if self.__html is None:
            logger.debug(f"fetching ({self.url})...")
            resp = sto_get(self.url)
            self.__html = response_text(resp, self.url)
        return self.__html

    # -----------------------------
    # PRIVATE EXTRACTION FUNCTIONS
    # -----------------------------

    def __extract_title(self):
        """
        <h1 class="h2 mb-1 fw-bold">
            American Horror Story
        </h1>
        """

        pattern = re.compile(r'<h1 class="h2 mb-1 fw-bold">\s*(.*?)\s*</h1>', re.DOTALL)
        match = pattern.search(self._html)

        if match:
            # The page stores the title HTML escaped, so "It's" arrives as
            # "It&#039;s" and would end up in the folder and file names.
            return unescape(match.group(1).strip())

        return None

    def __extract_description(self):
        """
        <span class="description-text">„American Horror Story“ ist eine US-amerikanische Horror - Fernsehserie. Jede ihrer Staffel setzt sich mit einem anderen Thema auseinander. Während die erste Staffel von einem Geisterhaus handelt, in welches die Familie Harmon unwissend einzieht, schildert die zweite Staffel die Geschehnisse in einer Nervenklinik im Jahre 1964. Die dritte Staffel beschäftigt sich mit einer kleinen </span>
        """

        pattern = re.compile(
            r'<span class="description-text">\s*(.*?)\s*</span>', re.DOTALL
        )
        match = pattern.search(self._html)

        if match:
            description = match.group(1).strip()
            return description

        return None

    def __extract_genres(self):
        """
        <li class="series-group">
            <strong class="me-1">Genre:</strong>
            <a href="https://serienstream.to/genre/horror" class="link-light">Horror</a>
        </li>
        """

        pattern = re.compile(
            r'<li class="series-group">\s*<strong class="me-1">Genre:</strong>(.*?)</li>',
            re.DOTALL,
        )

        match = pattern.search(self._html)

        if match:
            genres_html = match.group(1)
            genre_pattern = re.compile(r'<a href=".*?" class="link-light">(.*?)</a>')
            genres = genre_pattern.findall(genres_html)
            genres = [genre.strip() for genre in genres]
            return genres

        return []

    def __extract_release_year(self):
        """
        <p class="small text-muted mb-2">
            <a class="small text-muted" href="/jahr/2011">2011</a> -
            <span class="small text-muted">NA</span> • FSK 16 •
            <a href="https://www.imdb.com/title/tt1844624/" target="_blank" rel="noopener noreferrer" class="small text-muted text-decoration-none">
                IMDb
            </a>
        </p>
        """

        pattern = re.compile(
            rf'<a class="small text-muted" href="(?:https?://{STO_HOST_PATTERN})?/jahr/(\d{{4}})">(\d{{4}})</a>'
        )

        match = pattern.search(self._html)

        if match:
            release_year = match.group(1).strip()
            return release_year

        return None

    def __extract_poster_url(self):
        """
        <div class="col-3 col-md-3 col-lg-2 d-none d-md-block">
            <picture>
                <source type="image/avif" data-srcset="
                    /media/images/channel/mobile/american-horror-story-die-dunkle-seite-in-dir-lrd0j8zs?format=avif         375w,
                    /media/images/channel/tablet/american-horror-story-die-dunkle-seite-in-dir-lrd0j8zs?format=avif         768w,
                    /media/images/channel/desktop/american-horror-story-die-dunkle-seite-in-dir-lrd0j8zs?format=avif       1024w
                    " sizes="(max-width: 600px) 375px,
                        (max-width: 992px) 768px,
                        1024px" srcset="
                    /media/images/channel/mobile/american-horror-story-die-dunkle-seite-in-dir-lrd0j8zs?format=avif         375w,
                    /media/images/channel/tablet/american-horror-story-die-dunkle-seite-in-dir-lrd0j8zs?format=avif         768w,
                    /media/images/channel/desktop/american-horror-story-die-dunkle-seite-in-dir-lrd0j8zs?format=avif       1024w
                    ">

                <source type="image/webp" data-srcset="
                    /media/images/channel/mobile/american-horror-story-die-dunkle-seite-in-dir-lrd0j8zs?format=webp         375w,
                    /media/images/channel/tablet/american-horror-story-die-dunkle-seite-in-dir-lrd0j8zs?format=webp         768w,
                    /media/images/channel/desktop/american-horror-story-die-dunkle-seite-in-dir-lrd0j8zs?format=webp       1024w
                    " sizes="(max-width: 600px) 375px,
                        (max-width: 992px) 768px,
                        1024px" srcset="
                    /media/images/channel/mobile/american-horror-story-die-dunkle-seite-in-dir-lrd0j8zs?format=webp         375w,
                    /media/images/channel/tablet/american-horror-story-die-dunkle-seite-in-dir-lrd0j8zs?format=webp         768w,
                    /media/images/channel/desktop/american-horror-story-die-dunkle-seite-in-dir-lrd0j8zs?format=webp       1024w
                    ">

                <img data-src="/media/images/channel/desktop/american-horror-story-die-dunkle-seite-in-dir-lrd0j8zs?format=jpg" data-srcset="
                    /media/images/channel/desktop/american-horror-story-die-dunkle-seite-in-dir-lrd0j8zs?format=jpg      1x,
                    /media/images/channel/2x-desktop/american-horror-story-die-dunkle-seite-in-dir-lrd0j8zs?format=jpg   2x
                    " src="/media/images/channel/desktop/american-horror-story-die-dunkle-seite-in-dir-lrd0j8zs?format=jpg" alt="American Horror Story" class="img-fluid w-100 loaded" srcset="
                    /media/images/channel/desktop/american-horror-story-die-dunkle-seite-in-dir-lrd0j8zs?format=jpg      1x,
                    /media/images/channel/2x-desktop/american-horror-story-die-dunkle-seite-in-dir-lrd0j8zs?format=jpg   2x
                    " data-was-processed="true">
            </picture>
        </div>
        """

        # serienstream.to uses both src= and data-src= depending on page version.
        pattern = re.compile(
            rf'(?:data-)?src="(?P<url>(?:https?://{STO_HOST_PATTERN})?/media/images/channel/[^"]+)"'
        )
        match = pattern.search(self._html)
        if match:
            raw_url = urljoin(self.url, match.group("url").strip())
            parsed = urlparse(raw_url)
            path = parsed.path
            if parsed.query:
                query = f"?{parsed.query}"
            else:
                query = ""
            return f"http://186.2.175.5{path}" + query

        return None

    def __extract_imdb(self):
        """
        <a href="https://www.imdb.com/title/tt1844624/"
        """

        pattern = re.compile(r'href="https://www.imdb.com/title/(tt\d{7,8})/"')

        match = pattern.search(self._html)

        if match:
            imdb = match.group(1).strip()
            return imdb

        return None

    def __extract_seasons(self):
        """
        <meta property="og:url" content="https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir/staffel-1">
                    href="https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir/staffel-1"
                    href="https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir/staffel-2"
                    href="https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir/staffel-3"
                    [...]
        """
        from .season import SerienstreamSeason

        # serienstream.to currently serves both absolute and relative hrefs.
        # Support both and normalize them to absolute URLs.
        pattern = re.compile(
            rf'href="(?P<href>(?:https?://{STO_HOST_PATTERN})?/serie/[^\"\s]+/staffel-\d+)/?"'
        )

        matches = pattern.finditer(self._html)
        seen = set()
        seasons_list = []

        for m in matches:
            href = (m.group("href") or "").strip()
            if not href:
                continue
            full_url = urljoin(self.url, href)
            if full_url in seen:
                continue
            seen.add(full_url)
            seasons_list.append(SerienstreamSeason(full_url, series=self))

        return seasons_list

    def __extract_season_count(self):
        """
        <meta property="og:url" content="https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir/staffel-1">
                    href="https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir/staffel-1"
                    href="https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir/staffel-2"
                    href="https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir/staffel-3"
                    [...]
        """

        pattern = re.compile(
            rf'href="(?:https?://{STO_HOST_PATTERN})?/serie/[^\"\s]+/staffel-(\d+)'
        )

        matches = pattern.findall(self._html)
        season_numbers = [int(match) for match in matches]

        if season_numbers:
            return max(season_numbers)

        return 0

    # -----------------------------
    # PUBLIC METHODS
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
