import re
from html import unescape

from ...config import ANIWORLD_SERIES_PATTERN, GLOBAL_SESSION, logger
from ..common import clean_title
from .season import AniworldSeason


class AniworldSeries:
    """
    Represents an anime series on AniWorld.

    Parameters:
        url:    Required. Must be a valid AniWorld series URL,
                e.g. https://aniworld.to/anime/stream/highschool-dxd

    Attributes (Example):
        url:            "https://aniworld.to/anime/stream/highschool-dxd"
        title:          "Highschool DxD"
        title_cleaned:  "Highschool DxD"
        description:    "Oberschüler Issei Hyodo findet einfach keine Freundin [...]"
        genres:         ["Actionkomödie", "Action", "Ecchi", "EngSub", "Ger", "GerSub", "Harem", "Komödie", "Romanze"]
        release_year:   "2012-2018"
        poster_url:     "https://aniworld.to/public/img/cover/highschool-dxd-stream-cover-iepoc76t56fF6faMuE6yOo3f4RrvQW3a_220x330.jpg"
        imdb:           "tt1596341"
        mal_id:         [8074] # TODO: Highschool DxD entries broken yet others prob non nsfw work
        has_movies:     true
        seasons:        [<aniworld.models.aniworld_to.season.AniworldSeason object at 0x10afe5fd0>, [...]]
        season_count:   4
        _html:          "<!doctype html>[...]"

    Methods:
        download()
        watch()
        syncplay()
    """

    def __init__(self, url: str):
        if not self.is_valid_aniworld_series_url(url):
            raise ValueError(f"Invalid AniWorld series URL: {url}")

        self.url = url

        # Extracted from self.html
        self.__title = None
        self.__title_cleaned = None
        self.__description = None
        self.__genres = None
        self.__release_year = None
        self.__poster_url = None
        self.__imdb = None

        self.__mal_id = None

        self.__has_movies = None

        self.__seasons = None
        self.__season_count = None

        self.__html = None

        logger.debug(f"Initialized {self.url}")

    # -----------------------------
    # STATIC METHODS
    # -----------------------------

    @staticmethod
    def is_valid_aniworld_series_url(url):
        """Checks if the URL is a valid AniWorld series URL."""

        return bool(ANIWORLD_SERIES_PATTERN.match(url))

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
    def mal_id(self):
        if self.__mal_id is None:
            self.__mal_id = self.__extract_mal_id()
        return self.__mal_id

    @property
    def has_movies(self):
        if self.__has_movies is None:
            self.__has_movies = self.__extract_movies()
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

    # -----------------------------
    # PRIVATE EXTRACTION FUNCTIONS
    # -----------------------------

    def __extract_mal_id(self):
        from ...aniskip import get_all_seasons_by_query

        return get_all_seasons_by_query(self.title)

    def __extract_title(self):
        """
        <div class="series-title">
            <h1 itemprop="name" title="Animes Stream: 哥布林猎人, Goburin Sureiyā, 고블린슬레이어, Goblin Katili" data-alternativetitles="哥布林猎人, Goburin Sureiyā, 고블린슬레이어, Goblin Katili"><span>Goblin Slayer</span></h1>
            <small> (<span itemprop="startDate"><a href="https://aniworld.to/animes/jahr/2018">2018</a></span> - <span itemprop="endDate"><a href="https://aniworld.to/animes/jahr/2023">2023</a></span>)</small>
            <div title="Empfohlene Altersfreigabe: 16 Jahre" data-fsk="16" class="fsk fsk16">Ab: <span>16</span></div>
            <a href="https://www.imdb.com/title/tt8690728" title="IMDB ID: " data-imdb="tt8690728" class="imdb-link" target="_blank" rel="noopener">IMDB</a>
        </div>
        """
        logger.debug("extracting title...")

        html = self._html

        start = html.find('<div class="series-title">')
        if start == -1:
            return None

        span_start = html.find("<span>", start)
        span_end = html.find("</span>", span_start)

        if span_start == -1 or span_end == -1:
            return None

        title = html[span_start + len("<span>") : span_end].strip()
        title = unescape(title)

        return title

    def __extract_description(self):
        """
        <p class="seri_des" itemprop="accessibilitySummary" data-description-type="review" data-full-description="Goblins - die schwächsten aller Monster. Mit der Stärke und dem Verstand von kleinen Kindern ausgestattet, können sie lediglich ihre immerwährende Überzahl zu ihren Stärken zählen. Doch so dumm die Goblins auch sein mögen, sie sind keine Narren und ihr kindliches Denken schlägt schnell ins Grausame und Brutale um, wenn sie glauben, dass ihnen Unrecht geschieht. Eine junge Priesterin, gerade einmal 15 Jahre alt, beschließt, ihren Tempel zu verlassen und als Abenteuerin die Welt etwas sicherer zu machen. Jeder fängt klein an und so schließt sie sich spontan einer Gruppe Abenteurer an, die gerade einen Quest angenommen hat, der sie gegen eben diese schwächsten aller Monster führt: Ein paar Mädchen wurden von Goblins entführt und bevor diese zu deren Spielzeugen werden, gilt es, die Goblins zu töten und die Mädchen zu retten!">Goblins - die schwächsten aller Monster. Mit der Stärke und dem Verstand von kleinen Kindern ausgestattet, können sie lediglich ihre immerwährende Überzahl zu ihren Stärken zählen. Doch so dumm die Goblins auch sein mögen, sie sind keine Narren und ihr kindliches Denken schlägt schnell ins...<span class="showMore">mehr anzeigen</span></p>
        """
        logger.debug("extracting description...")

        html = self._html

        marker = 'class="seri_des"'
        start = html.find(marker)
        if start == -1:
            return None

        attr = 'data-full-description="'
        attr_start = html.find(attr, start)
        if attr_start == -1:
            return None

        value_start = attr_start + len(attr)
        value_end = html.find('"', value_start)
        if value_end == -1:
            return None

        description = html[value_start:value_end].strip()
        return description

    def __extract_genres(self):
        """
        <div class="genres">
            <ul data-main-genre="action">
                <li><a href="/genre/action" class="genreButton clearbutton" itemprop="genre">Action</a></li>
                <li><a href="/genre/abenteuer" class="genreButton clearbutton" itemprop="genre">Abenteuer</a></li>
                <li><a href="/genre/drama" class="genreButton clearbutton" itemprop="genre">Drama</a></li>
                <li><a href="/genre/engsub" class="genreButton clearbutton" itemprop="genre">EngSub</a></li>
                <li><a href="/genre/fantasy" class="genreButton clearbutton" itemprop="genre">Fantasy</a></li>
                <li><a href="/genre/ger" class="genreButton clearbutton" itemprop="genre">Ger</a></li>
                <li><a href="/genre/gersub" class="genreButton clearbutton" itemprop="genre">GerSub</a></li>
                <li><button class="hiddenArea">+ 2</button></li>
                <li><a href="/genre/horror" class="genreButton clearbutton" itemprop="genre">Horror</a></li>
                <li><a href="/genre/psychodrama" class="genreButton clearbutton" itemprop="genre">Psychodrama</a></li>
            </ul>
        </div>
        """
        logger.debug("extracting genres...")

        html = self._html

        genres = []

        block_start = html.find('<div class="genres">')
        if block_start == -1:
            return genres

        ul_start = html.find("<ul", block_start)
        ul_end = html.find("</ul>", ul_start)
        if ul_start == -1 or ul_end == -1:
            return genres

        ul_html = html[ul_start:ul_end]

        search_pos = 0
        marker = 'itemprop="genre"'

        while True:
            pos = ul_html.find(marker, search_pos)
            if pos == -1:
                break

            text_start = ul_html.find(">", pos) + 1
            text_end = ul_html.find("</a>", text_start)

            if text_start == -1 or text_end == -1:
                break

            genre = ul_html[text_start:text_end].strip()
            genres.append(genre)

            search_pos = text_end

        return genres

    def __extract_release_year(self):
        """
        <div class="series-title">
            <h1 itemprop="name" title="Animes Stream: 哥布林猎人, Goburin Sureiyā, 고블린슬레이어, Goblin Katili" data-alternativetitles="哥布林猎人, Goburin Sureiyā, 고블린슬레이어, Goblin Katili"><span>Goblin Slayer</span></h1>
            <small> (<span itemprop="startDate"><a href="https://aniworld.to/animes/jahr/2018">2018</a></span> - <span itemprop="endDate"><a href="https://aniworld.to/animes/jahr/2023">2023</a></span>)</small>
            <div title="Empfohlene Altersfreigabe: 16 Jahre" data-fsk="16" class="fsk fsk16">Ab: <span>16</span></div>
            <a href="https://www.imdb.com/title/tt8690728" title="IMDB ID: " data-imdb="tt8690728" class="imdb-link" target="_blank" rel="noopener">IMDB</a>
        </div>
        """
        logger.debug("extracting release year…")

        html = self._html

        div_start = html.find('<div class="series-title">')
        if div_start == -1:
            return None

        div_end = html.find("</div>", div_start)
        if div_end == -1:
            return None

        block = html[div_start:div_end]

        small_start = block.find("<small>")
        if small_start == -1:
            return None

        small_end = block.find("</small>", small_start)
        if small_end == -1:
            return None

        small_block = block[small_start:small_end]

        def extract_year(marker):
            pos = small_block.find(marker)
            if pos == -1:
                return None

            href_pos = small_block.find('href="', pos)
            if href_pos == -1:
                return None

            href_start = href_pos + len('href="')
            href_end = small_block.find('"', href_start)
            href = small_block[href_start:href_end]

            year = href.rstrip("/").split("/")[-1]
            return year if year.isdigit() else None

        start_year = extract_year('itemprop="startDate"')
        if not start_year:
            return None

        end_year = extract_year('itemprop="endDate"')
        if not end_year:
            return start_year

        return f"{start_year}-{end_year}"

    def __extract_poster_url(self):
        """
        <div class="seriesCoverBox"><img src="/public/img/cover/sentenced-to-be-a-hero-stream-cover-R6nfhysg9tvuw9XnflBmesyEmaLPrtp1_220x330.png" data-src="/public/img/cover/sentenced-to-be-a-hero-stream-cover-R6nfhysg9tvuw9XnflBmesyEmaLPrtp1_220x330.png" alt="Sentenced to Be a Hero, Cover, HD, Anime Stream, ganze Folge" itemprop="image" title="Cover Sentenced to Be a Hero AniWorld" class="loaded" data-was-processed="true"><noscript><img src="/public/img/cover/sentenced-to-be-a-hero-stream-cover-R6nfhysg9tvuw9XnflBmesyEmaLPrtp1_220x330.png" alt="Sentenced to Be a Hero, Cover, HD, Anime Stream, ganze Folge" itemprop="image" title="Cover Sentenced to Be a Hero AniWorld"></noscript></div>
        """
        logger.debug("extracting poster url...")

        html = self._html

        box_start = html.find('<div class="seriesCoverBox">')
        if box_start == -1:
            return None

        img_start = html.find("<img", box_start)
        if img_start == -1:
            return None

        attr = 'data-src="'
        src_start = html.find(attr, img_start)

        if src_start != -1:
            value_start = src_start + len(attr)
            value_end = html.find('"', value_start)
            rel_url = html[value_start:value_end].strip()
        else:
            attr = 'src="'
            src_start = html.find(attr, img_start)
            if src_start == -1:
                return None
            value_start = src_start + len(attr)
            value_end = html.find('"', value_start)
            rel_url = html[value_start:value_end].strip()

        return f"https://aniworld.to{rel_url}"

    def __extract_imdb(self):
        """
        Extract the IMDB ID from the series HTML
        <a href="https://www.imdb.com/title/tt2230051" title="IMDB ID: " data-imdb="tt2230051" class="imdb-link" target="_blank" rel="noopener">IMDB</a>
        """

        match = re.search(r'data-imdb="(tt\d+)"', self._html)
        if match:
            return match.group(1)

        return None

    def __extract_movies(self):
        """
        Detects if the series has movies by looking for the Filme link
        <li><a href="/anime/stream/goblin-slayer/filme" title="Alle Filme">Filme</a></li>
        """
        logger.debug("checking for movies...")

        html = self._html

        # Look for the Filme link
        marker = 'title="Alle Filme">Filme</a>'
        pos = html.find(marker)
        has_movies = pos != -1

        logger.debug(f"Has movies: {has_movies}")
        return has_movies

    def __extract_seasons(self):
        """
        Extracts:
          - Staffel-X seasons
          - Optional /filme container (NOT a season)
        """
        logger.debug("extracting seasons...")

        html = self._html

        seasons = []
        seen = set()

        # -----------------------------
        # Extract numbered seasons
        # -----------------------------
        staffel_matches = re.findall(
            r'href="(/anime/stream/[^/]+/staffel-(\d+))"', html
        )

        for rel_url, num in staffel_matches:
            url = "https://aniworld.to" + rel_url
            if url in seen:
                continue
            seen.add(url)
            seasons.append(AniworldSeason(url, series=self))

        logger.debug(f"Found {len([s for s in seasons if not s.are_movies])} seasons")

        if self.has_movies:
            seasons.append(AniworldSeason(f"{self.url}/filme", series=self))

        seasons.sort(key=lambda s: (s.are_movies, s.season_number or 0))

        return seasons

    def __extract_season_count(self):
        if self.has_movies:
            return len(self.seasons) - 1

        return len(self.seasons)

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
