import re

from ...config import ANIWORLD_SEASON_PATTERN, GLOBAL_SESSION, logger
from .episode import AniworldEpisode


class AniworldSeason:
    """
    Represents a single season (or a movie collection) of an AniWorld anime series.

    Parameters:
        url:        Required. The AniWorld URL for this season, e.g.
                    https://aniworld.to/anime/stream/highschool-dxd/staffel-1
                    or
                    https://aniworld.to/anime/stream/highschool-dxd/filme
        series:     <Parent series object>

    Attributes (Example):
        series:         <AniworldSeries object>
        url:            "https://aniworld.to/anime/stream/highschool-dxd/staffel-1"
        are_movies:     false
        season_number:  1
        episode_count:  12
        episodes:       [<aniworld.models.aniworld_to.episode.AniworldEpisode object at 0x10b2023c0>, [...]]
        _html:          "<!doctype html>[...]"

    Methods:
        download()
        watch()
        syncplay()
    """

    def __init__(self, url, series=None):
        if not self.is_valid_aniworld_season_url(url):
            raise ValueError(f"Invalid AniWorld season URL: {url}")

        self.url = url

        self._series = series

        self.__are_movies = None
        self.__season_number = None
        self.__episode_count = None
        self.__episodes = None

        self.__html = None

    @staticmethod
    def is_valid_aniworld_season_url(url):
        """
        Checks if the URL is a valid AniWorld season URL.
        """

        # https://aniworld.to/anime/stream/highschool-dxd/staffel-1
        # or
        # https://aniworld.to/anime/stream/highschool-dxd/filme

        url = url.strip()

        return bool(ANIWORLD_SEASON_PATTERN.match(url))

    @property
    def series(self):
        if self._series is None:
            # Extract series URL from season URL by removing /staffel-X or /filme part
            if self.are_movies:
                series_url = self.url.split("/filme")[0]
            else:
                series_url = self.url.split("/staffel-")[0]
            from .series import AniworldSeries

            self._series = AniworldSeries(series_url)
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
        """
        Check whether the current URL represents the movie collection page
        of a series on AniWorld.

        A movie collection URL follows this pattern:
            https://aniworld.to/anime/stream/<series>/filme

        Returns:
            bool: True if the URL matches the movie collection pattern,
                otherwise False.
        """
        return (
            re.fullmatch(r"https://aniworld\.to/anime/stream/[^/]+/filme", self.url)
            is not None
        )

    def __extract_season_number(self):
        """
        Extract the season number from the URL.

        Behavior:
        - If the series consists only of movies (no seasons), return 0.
        - If the URL contains a season indicator of the form "staffel-<number>",
        return that number.
        - If no season number can be determined, raise a ValueError.

        Returns:
            int: The extracted season number, or 0 for movie-only series.

        Raises:
            ValueError: If the URL does not contain a valid season number and the
                        series is not movie-only.
        """
        if self.are_movies:
            return 0

        match = re.search(r"staffel-(\d+)", self.url)
        if match:
            return int(match.group(1))

        raise ValueError(f"Could not extract season number from URL: {self.url}")

    def __extract_episodes(self):
        """
            <tbody id="season1">
            <tr class="" data-episode-id="2311" data-episode-season-id="1" itemprop="episode" itemscope="" itemtype="http://schema.org/Episode">
                <td class="season1EpisodeID">
                    <meta itemprop="episodeNumber" content="1"><a itemprop="url" href="/anime/stream/goblin-slayer/staffel-1/episode-1"> Folge 1 </a>
                </td>
                <td class="seasonEpisodeTitle"><a href="/anime/stream/goblin-slayer/staffel-1/episode-1"> <strong>Das Schicksal der Abenteurer</strong> - <span>The Fate of Particular Adventurers</span> </a></td>
                <td><a href="/anime/stream/goblin-slayer/staffel-1/episode-1"> <i class="icon VOE" title="VOE"></i><i class="icon Filemoon" title="Filemoon"></i><i class="icon Vidmoly" title="Vidmoly"></i> </a></td>
                <td class="editFunctions"><a href="/anime/stream/goblin-slayer/staffel-1/episode-1"> <img class="flag" src="/public/img/german.svg" alt="Deutsche Sprache, Flagge" title="Deutsch/German"> <img class="flag" src="/public/img/japanese-german.svg" alt="Deutsche Flagge, Untertitel, Flagge" title="Mit deutschem Untertitel"> <img class="flag" src="/public/img/japanese-english.svg" alt="Englische Sprache, Flagge" title="Englisch"> </a></td>
            </tr>
            <tr class="" data-episode-id="2312" data-episode-season-id="2" itemprop="episode" itemscope="" itemtype="http://schema.org/Episode">
                <td class="season1EpisodeID">
                    <meta itemprop="episodeNumber" content="2"><a itemprop="url" href="/anime/stream/goblin-slayer/staffel-1/episode-2"> Folge 2 </a>
                </td>
                <td class="seasonEpisodeTitle"><a href="/anime/stream/goblin-slayer/staffel-1/episode-2"> <strong>Dämonentöter</strong> - <span>Goblin Slayer</span> </a></td>
                <td><a href="/anime/stream/goblin-slayer/staffel-1/episode-2"> <i class="icon VOE" title="VOE"></i><i class="icon Filemoon" title="Filemoon"></i><i class="icon Vidmoly" title="Vidmoly"></i> </a></td>
                <td class="editFunctions"><a href="/anime/stream/goblin-slayer/staffel-1/episode-2"> <img class="flag" src="/public/img/german.svg" alt="Deutsche Sprache, Flagge" title="Deutsch/German"> <img class="flag" src="/public/img/japanese-german.svg" alt="Deutsche Flagge, Untertitel, Flagge" title="Mit deutschem Untertitel"> <img class="flag" src="/public/img/japanese-english.svg" alt="Englische Sprache, Flagge" title="Englisch"> </a></td>
            </tr>
            <tr class="" data-episode-id="2313" data-episode-season-id="3" itemprop="episode" itemscope="" itemtype="http://schema.org/Episode">
                <td class="season1EpisodeID">
                    <meta itemprop="episodeNumber" content="3"><a itemprop="url" href="/anime/stream/goblin-slayer/staffel-1/episode-3"> Folge 3 </a>
                </td>
                <td class="seasonEpisodeTitle"><a href="/anime/stream/goblin-slayer/staffel-1/episode-3"> <strong>Unerwarteter Besuch</strong> - <span>Unexpected Visitors</span> </a></td>
                <td><a href="/anime/stream/goblin-slayer/staffel-1/episode-3"> <i class="icon VOE" title="VOE"></i><i class="icon Filemoon" title="Filemoon"></i><i class="icon Vidmoly" title="Vidmoly"></i> </a></td>
                <td class="editFunctions"><a href="/anime/stream/goblin-slayer/staffel-1/episode-3"> <img class="flag" src="/public/img/german.svg" alt="Deutsche Sprache, Flagge" title="Deutsch/German"> <img class="flag" src="/public/img/japanese-german.svg" alt="Deutsche Flagge, Untertitel, Flagge" title="Mit deutschem Untertitel"> <img class="flag" src="/public/img/japanese-english.svg" alt="Englische Sprache, Flagge" title="Englisch"> </a></td>
            </tr>
            ...
        </tbody>
        """
        logger.debug("extracting episodes...")

        html = self._html
        episodes = []

        marker = 'itemtype="http://schema.org/Episode"'
        pos = 0

        while True:
            pos = html.find(marker, pos)
            if pos == -1:
                break

            tr_start = html.rfind("<tr", 0, pos)
            tr_end = html.find("</tr>", pos)
            if tr_start == -1 or tr_end == -1:
                break

            tr_html = html[tr_start:tr_end]

            # Episode number - different extraction for movies vs episodes
            ep_num = None
            if self.are_movies:
                # For movies, extract from data-episode-season-id or film-X URL
                data_season_id_pos = tr_html.find("data-episode-season-id")
                if data_season_id_pos != -1:
                    id_start = tr_html.find('"', data_season_id_pos) + 1
                    id_end = tr_html.find('"', id_start)
                    try:
                        ep_num = int(tr_html[id_start:id_end])
                    except ValueError:
                        pass

                # Fallback: extract from film-X in URL
                if ep_num is None:
                    href_pos = tr_html.find("film-")
                    if href_pos != -1:
                        num_start = href_pos + 5  # after 'film-'
                        num_end = tr_html.find('"', num_start)
                        if num_end == -1:
                            num_end = tr_html.find("<", num_start)
                        try:
                            ep_num = int(tr_html[num_start:num_end])
                        except ValueError:
                            pass
            else:
                # For regular episodes, extract from meta tag
                meta_pos = tr_html.find('itemprop="episodeNumber"')
                if meta_pos != -1:
                    c_start = tr_html.find('content="', meta_pos) + 9
                    c_end = tr_html.find('"', c_start)
                    ep_num = int(tr_html[c_start:c_end])

            # Episode URL - different extraction for movies vs episodes
            ep_url = None
            if self.are_movies:
                # For movies, look for any href containing "film-"
                href_pos = tr_html.find("film-")
                if href_pos != -1:
                    h_start = tr_html.rfind('href="', 0, href_pos) + 6
                    h_end = tr_html.find('"', h_start)
                    ep_url = tr_html[h_start:h_end]
                    if ep_url.startswith("/"):
                        ep_url = "https://aniworld.to" + ep_url
            else:
                # For regular episodes, look for itemprop="url"
                url_pos = tr_html.find('itemprop="url"')
                if url_pos != -1:
                    h_start = tr_html.find('href="', url_pos) + 6
                    h_end = tr_html.find('"', h_start)
                    ep_url = tr_html[h_start:h_end]
                    if ep_url.startswith("/"):
                        ep_url = "https://aniworld.to" + ep_url

            # Titles - different handling for movies vs episodes
            title_de = None
            title_en = None

            if self.are_movies:
                # For movies, title is usually in span, strong tag is empty
                span_start = tr_html.find("<span>")
                if span_start != -1:
                    span_start += 6
                    span_end = tr_html.find("</span>", span_start)
                    title_en = tr_html[span_start:span_end].strip()
                    # For movies, use English title as German title since strong is empty
                    title_de = title_en
            else:
                # For regular episodes, German title is in strong, English in span
                s_start = tr_html.find("<strong>")
                if s_start != -1:
                    s_start += 8
                    s_end = tr_html.find("</strong>", s_start)
                    title_de = tr_html[s_start:s_end].strip()

                span_start = tr_html.find("<span>")
                if span_start != -1:
                    span_start += 6
                    span_end = tr_html.find("</span>", span_start)
                    title_en = tr_html[span_start:span_end].strip()

            if ep_url:
                # For movies, ep_num might be None, but we can still create the episode object
                # The AniworldEpisode class should handle None episode_number appropriately
                episodes.append(
                    AniworldEpisode(
                        series=self.series,
                        season=self,
                        url=ep_url,
                        episode_number=ep_num,
                        title_de=title_de,
                        title_en=title_en,
                    )
                )

            pos = tr_end

        return episodes

    def __extract_episode_count(self):
        """
        Counts episodes by counting episode markers in HTML without full extraction
        """
        logger.debug("counting episodes...")

        html = self._html

        marker = 'itemtype="http://schema.org/Episode"'
        count = 0
        pos = 0

        while True:
            pos = html.find(marker, pos)
            if pos == -1:
                break
            count += 1
            pos += 1

        return count

    def download(self):
        for episode in self.episodes:
            episode.download()

    def watch(self):
        for episode in self.episodes:
            episode.watch()

    def syncplay(self):
        for episode in self.episodes:
            episode.syncplay()
