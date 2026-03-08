from ...config import GLOBAL_SESSION, logger
from ..common.common import (
    download as episode_download,
)
from ..common.common import (
    syncplay as episode_syncplay,
)
from ..common.common import (
    watch as episode_watch,
)


class HiAnimeEpisode:
    """
    Represents a single episode (or movie entry) of a HiAnime anime series.

    Parameters:
        url:                Required. The HiAnime URL for this episode, e.g.,
                            https://hianime.to/watch/kaguya-sama-love-is-war-season-2-23?ep=800
        series:             The parent series object.
        season:             The parent season object this episode belongs to.
        episode_number:     Optional. The episode index within the season; generated when creating a season object.
        title_de:           Optional. The German episode title; generated when creating a season object.
        title_en:           Optional. The English episode title; generated when creating a season object.
        selected_path:      Optional. The chosen path; provided in cases such as using a menu.
        selected_language:  Optional. The chosen language; provided in cases such as using a menu.
        selected_provider:  Optional. The chosen provider; provided in cases such as using a menu.

    Attributes (Example):
        url:                    "https://hianime.to/watch/kaguya-sama-love-is-war-season-2-23?ep=800"
        series:                 <HiAnimeSeries object>
        season:                 <HiAnimeSeason object>

        title_de:               ""
        title_en:               ""
        episode_number:         1
        provider_data:          ProviderData({(<Audio.GERMAN: 'German'>, <Subtitles.NONE: 'None'>): {'VOE': 'https://aniworld.to/redirect/2526098', 'Filemoon': 'https://aniworld.to/redirect/2883363', 'Vidmoly': 'https://aniworld.to/redirect/3028732'}, (<Audio.JAPANESE: 'Japanese'>, <Subtitles.ENGLISH: 'English'>): {'VOE': 'https://aniworld.to/redirect/1791080', 'Filemoon': 'https://aniworld.to/redirect/2883251', 'Vidmoly': 'https://aniworld.to/redirect/3674098'}, (<Audio.JAPANESE: 'Japanese'>, <Subtitles.GERMAN: 'German'>): {'VOE': 'https://aniworld.to/redirect/1791211', 'Filemoon': 'https://aniworld.to/redirect/2883481', 'Vidmoly': 'https://aniworld.to/redirect/3028797'}})

        selected_path:          "/Users/phoenixthrush/Downloads"
        selected_language:      "German Dub"
        selected_provider:      "VOE"

        redirect_url:           "https://aniworld.to/redirect/2526098"
        provider_url:           "https://voe.sx/e/brrfb6svahr0"
        stream_url:             "https://cdn-9hkqbevdlsunmsrc.edgeon-bandwidth.com/engine/hls2-c/01/11265/brrfb6svahr0_,n,l,.urlset/master.m3u8?t=7H-ROabLHNhRW7YUk7ukuV3gtpx-WPTn0Lhl9ZYwqkk&s=1768754148&e=14400&f=56328906&node=j9A3uKlh9EJIvaW3p3v65VuzDBUEiinc24sqRscdXcg=&i=185.213&sp=2500&asn=39351&q=n,l&rq=F2b2aGFqiQE6hVBHR3zxjsqBxOeHRuB3Setre8LO"

        self._base_folder:      /Users/phoenixthrush/Downloads/Kaguya-sama Love is War (2012-2018) [imdbid-tt2230051]
        self._folder_path:      /Users/phoenixthrush/Downloads/Kaguya-sama Love is War (2012-2018) [imdbid-tt2230051]/Season 01
        self._file_name:        Kaguya-sama Love is War S01E01
        self._file_extension:   mkv
        self._episode_path:     /Users/phoenixthrush/Downloads/Kaguya-sama Love is War (2012-2018) [imdbid-tt2230051]/Season 01/Kaguya-sama Love is War S01E01.mkv

        is_movie                false
        is_downloaded           {'exists': False, 'video_langs': set(), 'audio_langs': set()}

        skip_times:             {'found': True, 'results': [{'interval': {'start_time': 123.014, 'end_time': 213.014}, 'skip_type': 'op', 'skip_id': '1fd0d19a-4332-479e-9e3d-03e9b293db6a', 'episode_length': 1422.0416}, {'interval': {'start_time': 1187.09, 'end_time': 1277.09}, 'skip_type': 'ed', 'skip_id': '17a28c6e-5104-4142-9334-b57dbd024425', 'episode_length': 1422.0416}]}

        _html:                  "<!doctype html>[...]"

    Methods:
        download()
        watch()
        syncplay()

        provider_link(language=None, provider=None)  # <Audio.GERMAN: 'German'>, <Subtitles.NONE: 'None'>)
    """

    def __init__(
        self,
        url=None,
        series=None,
        season=None,
        episode_number=None,
        title_de=None,
        title_en=None,
        selected_path=None,
        selected_language=None,
        selected_provider=None,
    ):
        if not self.is_valid_aniworld_episode_url(url):
            raise ValueError(f"Invalid AniWorld episode URL: {url}")

        self.url = url
        self._series = series
        self._season = season

        self.__title_de = title_de
        self.__title_en = title_en
        self.__episode_number = episode_number

        self.__selected_path_param = selected_path
        self.__selected_language_param = selected_language
        self.__selected_provider_param = selected_provider

        self.__provider_data = None

        self.__selected_path = None
        self.__selected_language = None
        self.__selected_provider = None

        self.__redirect_url = None
        self.__provider_url = None

        self.__base_folder = None
        self.__folder_path = None
        self.__file_name = None
        self.__file_extension = None
        self.__episode_path = None

        self.__is_movie = None
        self.__is_downloaded = None

        self.__skip_times = None

        self.__html = None

    @staticmethod
    def is_valid_aniworld_episode_url(url):
        pass

    @property
    def series(self):
        if self._series is None:
            print("bla")
        return self._series

    @property
    def season(self):
        if self._season is None:
            print("bla")
        return self._season

    @property
    def title_de(self):
        if self.__title_de is None:
            self.__title_de = self.__extract_title_de()
        return self.__title_de

    @property
    def title_en(self):
        if self.__title_en is None:
            self.__title_en = self.__extract_title_en()
        return self.__title_en

    @property
    def episode_number(self):
        if self.__episode_number is None:
            self.__episode_number = self.__extract_episode_number()
        return self.__episode_number

    @property
    def provider_data(self):
        if self.__provider_data is None:
            self.__provider_data = self.__extract_provider_data()
        return self.__provider_data

    @property
    def selected_path(self):
        if self.__selected_path is None:
            self.__selected_path = self.__extract_selected_path()
        return self.__selected_path

    @property
    def selected_language(self):
        if self.__selected_language is None:
            self.__selected_language = self.__extract_selected_language()
        return self.__selected_language

    @property
    def selected_provider(self):
        if self.__selected_provider is None:
            self.__selected_provider = self.__extract_selected_provider()
        return self.__selected_provider

    @property
    def redirect_url(self):
        if self.__redirect_url is None:
            self.__redirect_url = self.__extract_redirect_url()
        return self.__redirect_url

    @property
    def provider_url(self):
        if self.__provider_url is None:
            self.__provider_url = self.__extract_provider_url()
        return self.__provider_url

    @property
    def stream_url(self):
        pass

    @property
    def is_movie(self):
        if self.__is_movie is None:
            self.__is_movie = self.__determine_is_movie()
        return self.__is_movie

    @property
    def is_downloaded(self):
        if self.__is_downloaded is None:
            self.__is_downloaded = self.__determine_is_downloaded()
        return self.__is_downloaded

    @property
    def skip_times(self):
        if self.__skip_times is None:
            self.__skip_times = self.__extract_skip_times()
        return self.__skip_times

    @property
    def _html(self):
        if self.__html is None:
            logger.debug(f"fetching ({self.url})...")
            resp = GLOBAL_SESSION.get(self.url)
            self.__html = resp.text
        return self.__html

    # -----------------------------
    # Extraction helpers
    # -----------------------------

    def __extract_title_de(self):
        pass

    def __extract_title_en(self):
        pass

    def __extract_episode_number(self):
        pass

    def __extract_provider_data(self):
        pass

    def __extract_selected_path(self):
        pass

    def __extract_selected_language(self):
        pass

    def __extract_selected_provider(self):
        pass

    def __extract_redirect_url(self):
        pass

    def __extract_provider_url(self):
        pass

    def __determine_is_movie(self):
        pass

    def __determine_is_downloaded(self):
        pass

    def __extract_skip_times(self):
        pass

    # -----------------------------
    # PUBLIC METHODS
    # -----------------------------

    download = episode_download
    watch = episode_watch
    syncplay = episode_syncplay
