from ...config import logger


class HanimeTVSeason:
    """
    Represents a season of a hanime.tv franchise.

    hanime.tv doesn't have traditional seasons, so all episodes of a franchise
    are grouped into a single season (season 1).

    Parameters:
        episode_slugs:  List of video slugs belonging to this season.
        series:         Parent HanimeTVSeries object.

    Attributes:
        url:            ""
        season_number:  1
        are_movies:     False
        episode_count:  <number of episodes>
        episodes:       [<HanimeTVEpisode>, ...]
    """

    def __init__(self, episode_slugs=None, series=None, url=None):
        self._series = series
        self._episode_slugs = episode_slugs or []

        self.url = url or ""

        self.__episodes = None
        self.__episode_count = None

    @property
    def series(self):
        return self._series

    @property
    def season_number(self):
        return 1

    @property
    def are_movies(self):
        return False

    @property
    def episode_count(self):
        if self.__episode_count is None:
            self.__episode_count = len(self.episodes)
        return self.__episode_count

    @property
    def episodes(self):
        if self.__episodes is None:
            self.__episodes = self._build_episodes()
        return self.__episodes

    def _build_episodes(self):
        from .episode import HanimeTVEpisode

        episodes = []
        for i, slug in enumerate(self._episode_slugs, start=1):
            url = f"https://hanime.tv/videos/hentai/{slug}"
            episodes.append(
                HanimeTVEpisode(
                    url=url,
                    series=self._series,
                    season=self,
                    episode_number=i,
                )
            )
        return episodes

    def download(self):
        for episode in self.episodes:
            episode.download()

    def watch(self):
        for episode in self.episodes:
            episode.watch()

    def syncplay(self):
        for episode in self.episodes:
            episode.syncplay()
