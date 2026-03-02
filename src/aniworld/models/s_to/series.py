import re
from urllib.parse import urljoin

from ...config import GLOBAL_SESSION, SERIENSTREAM_SERIES_PATTERN, logger
from ..common import clean_title


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
        directors:      ['Bradley Buecker', 'Alfonso Gomez-Rejon', 'Michael Uppendahl', ...]
        actors:         ['Evan Peters', 'Sarah Paulson', 'Denis O`Hare', ...]
        producer:       ['Bradley Buecker', 'Brad Falchuk', 'Ryan Murphy', ...]
        country:        "USA"
        age_rating:     "16"
        imdb:           "tt1844624"
        seasons:        [<aniworld.models.s_to.season.SerienstreamSeason object at 0x106d427b0>, ...]
        season_count:   13
        _html:          "<!DOCTYPE html>[...]"

    Methods:
        download()
        watch()
        syncplay()

    Attributes That Do Not Exists as on Aniworld:
        rating, mal_id, has_movies
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
        self.__directors = None
        self.__actors = None
        self.__producer = None
        self.__country = None
        self.__age_rating = None
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
    def directors(self):
        if self.__directors is None:
            self.__directors = self.__extract_directors()
        return self.__directors

    @property
    def actors(self):
        if self.__actors is None:
            self.__actors = self.__extract_actors()
        return self.__actors

    @property
    def producer(self):
        if self.__producer is None:
            self.__producer = self.__extract_producer()
        return self.__producer

    @property
    def country(self):
        if self.__country is None:
            self.__country = self.__extract_country()
        return self.__country

    @property
    def age_rating(self):
        if self.__age_rating is None:
            self.__age_rating = self.__extract_age_rating()
        return self.__age_rating

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
            resp = GLOBAL_SESSION.get(self.url)
            self.__html = resp.text
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
            title = match.group(1).strip()
            return title

        return None

    # TODO: description is clamped in html and loaded via js
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
            r'<a class="small text-muted" href="(?:https://(?:serienstream|s)\.to)?/jahr/(\d{4})">(\d{4})</a>'
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

        # s.to uses both src= and data-src= depending on page version.
        slug = self.url.rstrip("/").split("/")[-1]
        pattern = re.compile(
            r'(?:data-)?src="((?:https://(?:serienstream|s)\.to)?/media/images/channel/desktop/'
            + re.escape(slug)
            + r'[^"]*)"'
        )
        match = pattern.search(self._html)
        if match:
            return match.group(1).strip()

        return None

    def __extract_directors(self):
        """
        <li class="series-group">
            <strong class="me-1">Regisseur:</strong>

            <a href="https://serienstream.to/regisseur/bradley-buecker" class="link-light">Bradley Buecker</a>, <a href="https://serienstream.to/regisseur/alfonso-gomez-rejon" class="link-light">Alfonso Gomez-Rejon</a>, <a href="https://serienstream.to/regisseur/michael-uppendahl" class="link-light">Michael Uppendahl</a>

            <span class="extra-items d-none">
                                                            , <a href="https://serienstream.to/regisseur/loni-peristere" class="link-light">Loni Peristere</a>
                                                                    , <a href="https://serienstream.to/regisseur/michael-goi" class="link-light">Michael Goi</a>
                                                                    , <a href="https://serienstream.to/regisseur/gwyneth-horder-payton" class="link-light">Gwyneth Horder-Payton</a>
                                                                    , <a href="https://serienstream.to/regisseur/jennifer-lynch" class="link-light">Jennifer Lynch</a>
                                                                    , <a href="https://serienstream.to/regisseur/ryan-murphy" class="link-light">Ryan Murphy</a>
                                                                    , <a href="https://serienstream.to/regisseur/michael-lehmann" class="link-light">Michael Lehmann</a>
                                                                    , <a href="https://serienstream.to/regisseur/david-semel" class="link-light">David Semel</a>
                                                                    , <a href="https://serienstream.to/regisseur/howard-deutch" class="link-light">Howard Deutch</a>
                                                                    , <a href="https://serienstream.to/regisseur/jeremy-podeswa" class="link-light">Jeremy Podeswa</a>
                                                                    , <a href="https://serienstream.to/regisseur/michael-rymer" class="link-light">Michael Rymer</a>
                                                                    , <a href="https://serienstream.to/regisseur/angela-bassett" class="link-light">Angela Bassett</a>
                                                                    , <a href="https://serienstream.to/regisseur/miguel-arteta" class="link-light">Miguel Arteta</a>
                                                                    , <a href="https://serienstream.to/regisseur/tim-hunter" class="link-light">Tim Hunter</a>
                                                                    , <a href="https://serienstream.to/regisseur/john-scott" class="link-light">John Scott</a>
                                                                    , <a href="https://serienstream.to/regisseur/craig-zisk" class="link-light">Craig Zisk</a>
                                                                    , <a href="https://serienstream.to/regisseur/anthony-hemingway" class="link-light">Anthony Hemingway</a>
                                                                    , <a href="https://serienstream.to/regisseur/nelson-cragg" class="link-light">Nelson Cragg</a>
                                                                    , <a href="https://serienstream.to/regisseur/marita-grabiak" class="link-light">Marita Grabiak</a>
                                                                    , <a href="https://serienstream.to/regisseur/elodie-keene" class="link-light">Elodie Keene</a>
                                                                    , <a href="https://serienstream.to/regisseur/alexis-ostrander" class="link-light">Alexis Ostrander</a>
                                                                    , <a href="https://serienstream.to/regisseur/barbara-brown" class="link-light">Barbara Brown</a>
                                                                    , <a href="https://serienstream.to/regisseur/rachel-goldberg" class="link-light">Rachel Goldberg</a>
                                                                    , <a href="https://serienstream.to/regisseur/liza-johnson" class="link-light">Liza Johnson</a>
                                                                    , <a href="https://serienstream.to/regisseur/maggie-kiley" class="link-light">Maggie Kiley</a>
                                                                    , <a href="https://serienstream.to/regisseur/jennifer-arnold" class="link-light">Jennifer Arnold</a>
                                                                    , <a href="https://serienstream.to/regisseur/sheree-folkson" class="link-light">Sheree Folkson</a>
                                                                    , <a href="https://serienstream.to/regisseur/sarah-paulson" class="link-light">Sarah Paulson</a>
                                                    </span>

            <button type="button" class="btn btn-sm text-white-50 p-0 toggle-more" data-count="27" aria-expanded="false">
                                    &amp; 27 mehr
                                </button>
        </li>
        """

        pattern = re.compile(
            r'<li class="series-group">\s*<strong class="me-1">Regisseur:</strong>(.*?)</li>',
            re.DOTALL,
        )

        match = pattern.search(self._html)

        if match:
            directors_html = match.group(1)
            director_pattern = re.compile(r'<a href=".*?" class="link-light">(.*?)</a>')
            directors = director_pattern.findall(directors_html)
            directors = [director.strip() for director in directors]
            return directors

        return []

    def __extract_actors(self):
        """
        <li class="series-group">
            <strong class="me-1">Besetzung:</strong>

            <a href="https://serienstream.to/schauspieler/evan-peters" class="link-light">Evan Peters</a>, <a href="https://serienstream.to/schauspieler/sarah-paulson" class="link-light">Sarah Paulson</a>, <a href="https://serienstream.to/schauspieler/denis-ohare" class="link-light">Denis O`Hare</a>

            <span class="extra-items d-none">
                                                            , <a href="https://serienstream.to/schauspieler/kathy-bates" class="link-light">Kathy Bates</a>
                                                                    , <a href="https://serienstream.to/schauspieler/jessica-lange" class="link-light">Jessica Lange</a>
                                                                    , <a href="https://serienstream.to/schauspieler/frances-conroy" class="link-light">Frances Conroy</a>
                                                                    , <a href="https://serienstream.to/schauspieler/lily-rabe" class="link-light">Lily Rabe</a>
                                                                    , <a href="https://serienstream.to/schauspieler/angela-bassett" class="link-light">Angela Bassett</a>
                                                                    , <a href="https://serienstream.to/schauspieler/cheyenne-jackson" class="link-light">Cheyenne Jackson</a>
                                                                    , <a href="https://serienstream.to/schauspieler/emma-roberts" class="link-light">Emma Roberts</a>
                                                                    , <a href="https://serienstream.to/schauspieler/taissa-farmiga" class="link-light">Taissa Farmiga</a>
                                                                    , <a href="https://serienstream.to/schauspieler/adina-porter" class="link-light">Adina Porter</a>
                                                                    , <a href="https://serienstream.to/schauspieler/wes-bentley" class="link-light">Wes Bentley</a>
                                                                    , <a href="https://serienstream.to/schauspieler/finn-wittrock" class="link-light">Finn Wittrock</a>
                                                                    , <a href="https://serienstream.to/schauspieler/billie-lourd" class="link-light">Billie Lourd</a>
                                                                    , <a href="https://serienstream.to/schauspieler/gabourey-sidibe" class="link-light">Gabourey Sidibe</a>
                                                                    , <a href="https://serienstream.to/schauspieler/jamie-brewer" class="link-light">Jamie Brewer</a>
                                                                    , <a href="https://serienstream.to/schauspieler/naomi-grossman" class="link-light">Naomi Grossman</a>
                                                                    , <a href="https://serienstream.to/schauspieler/chlo-sevigny" class="link-light">Chloë Sevigny</a>
                                                                    , <a href="https://serienstream.to/schauspieler/dylan-mcdermott" class="link-light">Dylan McDermott</a>
                                                                    , <a href="https://serienstream.to/schauspieler/zachary-quinto" class="link-light">Zachary Quinto</a>
                                                                    , <a href="https://serienstream.to/schauspieler/leslie-grossman" class="link-light">Leslie Grossman</a>
                                                                    , <a href="https://serienstream.to/schauspieler/erika-ervin" class="link-light">Erika Ervin</a>
                                                                    , <a href="https://serienstream.to/schauspieler/stefani-joanne-angelina-germanotta" class="link-light">Stefani Joanne Angelina Germanotta</a>
                                                                    , <a href="https://serienstream.to/schauspieler/mare-winningham" class="link-light">Mare Winningham</a>
                                                                    , <a href="https://serienstream.to/schauspieler/joseph-fiennes" class="link-light">Joseph Fiennes</a>
                                                                    , <a href="https://serienstream.to/schauspieler/connie-britton" class="link-light">Connie Britton</a>
                                                                    , <a href="https://serienstream.to/schauspieler/michael-chiklis" class="link-light">Michael Chiklis</a>
                                                                    , <a href="https://serienstream.to/schauspieler/matt-bomer" class="link-light">Matt Bomer</a>
                                                                    , <a href="https://serienstream.to/schauspieler/lizzie-brocher" class="link-light">Lizzie Brocheré</a>
                                                                    , <a href="https://serienstream.to/schauspieler/chaz-bono" class="link-light">Chaz Bono</a>
                                                    </span>

            <button type="button" class="btn btn-sm text-white-50 p-0 toggle-more" data-count="28" aria-expanded="false">
                                    &amp; 28 mehr
                                </button>
        </li>
        """

        pattern = re.compile(
            r'<li class="series-group">\s*<strong class="me-1">Besetzung:</strong>(.*?)</li>',
            re.DOTALL,
        )

        match = pattern.search(self._html)

        if match:
            actors_html = match.group(1)
            actor_pattern = re.compile(r'<a href=".*?" class="link-light">(.*?)</a>')
            actors = actor_pattern.findall(actors_html)
            actors = [actor.strip() for actor in actors]
            return actors

        return []

    def __extract_producer(self):
        """
        <li class="series-group">
            <strong class="me-1">Produzent:</strong>

            <a href="https://serienstream.to/produzent/bradley-buecker" class="link-light">Bradley Buecker</a>, <a href="https://serienstream.to/produzent/brad-falchuk" class="link-light">Brad Falchuk</a>, <a href="https://serienstream.to/produzent/ryan-murphy" class="link-light">Ryan Murphy</a>

            <span class="extra-items d-none">
                                                            , <a href="https://serienstream.to/produzent/tim-minear" class="link-light">Tim Minear</a>
                                                                    , <a href="https://serienstream.to/produzent/james-wong" class="link-light">James Wong</a>
                                                                    , <a href="https://serienstream.to/produzent/alexis-martin-woodall" class="link-light">Alexis Martin Woodall</a>
                                                                    , <a href="https://serienstream.to/produzent/jennifer-salt" class="link-light">Jennifer Salt</a>
                                                                    , <a href="https://serienstream.to/produzent/dante-di-loreto" class="link-light">Dante Di Loreto</a>
                                                                    , <a href="https://serienstream.to/produzent/robert-m-williams-jr" class="link-light">Robert M. Williams Jr.</a>
                                                                    , <a href="https://serienstream.to/produzent/chip-vucelich" class="link-light">Chip Vucelich</a>
                                                                    , <a href="https://serienstream.to/produzent/lou-eyrich" class="link-light">Lou Eyrich</a>
                                                                    , <a href="https://serienstream.to/produzent/eryn-krueger-mekash" class="link-light">Eryn Krueger Mekash</a>
                                                                    , <a href="https://serienstream.to/produzent/adam-penn" class="link-light">Adam Penn</a>
                                                                    , <a href="https://serienstream.to/produzent/joe-incaprera" class="link-light">Joe Incaprera</a>
                                                                    , <a href="https://serienstream.to/produzent/eric-kovtun" class="link-light">Eric Kovtun</a>
                                                                    , <a href="https://serienstream.to/produzent/patrick-mckee" class="link-light">Patrick McKee</a>
                                                    </span>

            <button type="button" class="btn btn-sm text-white-50 p-0 toggle-more" data-count="13" aria-expanded="false">
                                    &amp; 13 mehr
                                </button>
        </li>
        """

        pattern = re.compile(
            r'<li class="series-group">\s*<strong class="me-1">Produzent:</strong>(.*?)</li>',
            re.DOTALL,
        )

        match = pattern.search(self._html)

        if match:
            producers_html = match.group(1)
            producer_pattern = re.compile(r'<a href=".*?" class="link-light">(.*?)</a>')
            producers = producer_pattern.findall(producers_html)
            producers = [producer.strip() for producer in producers]
            return producers

        return []

    def __extract_country(self):
        """
        <li class="series-group">
            <strong class="me-1">Land:</strong>

            <a href="https://serienstream.to/land/usa" class="link-light">USA</a>

        </li>
        """

        pattern = re.compile(
            r'<li class="series-group">\s*<strong class="me-1">Land:</strong>(.*?)</li>',
            re.DOTALL,
        )

        match = pattern.search(self._html)

        if match:
            country_html = match.group(1)
            country_pattern = re.compile(r'<a href=".*?" class="link-light">(.*?)</a>')
            country_match = country_pattern.search(country_html)
            if country_match:
                country = country_match.group(1).strip()
                return country

        return None

    def __extract_age_rating(self):
        """
        <p class="small text-muted mb-2">

            <a class="small text-muted" href="https://serienstream.to/jahr/2011">2011</a> -
            <span class="small text-muted">NA</span> • FSK 16 •
            <a href="https://www.imdb.com/title/tt1844624/" target="_blank" rel="noopener noreferrer" class="small text-muted text-decoration-none">
                            IMDb
                        </a>
        </p>
        """

        pattern = re.compile(r"FSK (\d{1,2}|NA)")

        match = pattern.search(self._html)

        if match:
            age_rating = match.group(1).strip()
            return age_rating

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

        # s.to currently serves both absolute and relative hrefs.
        # Support both and normalize them to absolute URLs.
        pattern = re.compile(
            r'href="(?P<href>(?:https?://(?:serienstream|s)\.to)?/serie/[^\"\s]+/staffel-\d+)/?"'
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
            r'href="(?:https?://(?:serienstream|s)\.to)?/serie/[^\"\s]+/staffel-(\d+)'
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
