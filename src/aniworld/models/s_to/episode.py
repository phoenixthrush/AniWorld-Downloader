import os
import re
from enum import Enum
from html import unescape
from pathlib import Path

from ...config import (
    GLOBAL_SESSION,
    NAMING_TEMPLATE,
    SERIENSTREAM_EPISODE_PATTERN,
    logger,
)
from ...extractors import provider_functions
from ..common import check_downloaded
from ..common.common import (
    download as episode_download,
)
from ..common.common import (
    syncplay as episode_syncplay,
)
from ..common.common import (
    watch as episode_watch,
)


# -----------------------------
# Language Stuff (s.to only)
# -----------------------------
class Audio(Enum):
    """
    Available audio language options (s.to only):
        - GERMAN:  German dub
        - ENGLISH: English dub
    """

    GERMAN = "German"
    ENGLISH = "English"


class Subtitles(Enum):
    """
    Available subtitle options (s.to only):
        - NONE: no subtitles
    """

    NONE = "None"


# Map UI labels to enum tuples (s.to labels)
LANG_LABEL_TO_ENUM = {
    "Deutsch": (Audio.GERMAN, Subtitles.NONE),
    "Englisch": (Audio.ENGLISH, Subtitles.NONE),
}

# ISO language codes for media players (IINA/mpv)
LANG_CODE_MAP = {
    Audio.ENGLISH: "eng",
    Audio.GERMAN: "deu",
    Subtitles.NONE: None,
}


class SerienstreamEpisode:
    """
    Represents a single episode of an Serienstream series.

    Parameters:
        url:                Required. The Serienstream URL for this episode, e.g.,
                            https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir/staffel-1/episode-1
        series:             The parent series object.
        season:             The parent season object this episode belongs to.
        episode_number:     Optional. The episode index within the season; generated when creating a season object.
        title_de:           Optional. The German episode title; generated when creating a season object.
        title_en:           Optional. The English episode title; generated when creating a season object.
        selected_path:      Optional. The chosen path; provided in cases such as using a menu.
        selected_language:  Optional. The chosen language; provided in cases such as using a menu.
        selected_provider:  Optional. The chosen provider; provided in cases such as using a menu.

    Attributes (Example):
        url:                    "https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir/staffel-1/episode-1"
        series:                 <aniworld.models.s_to.series.SerienstreamSeries object at 0x10ad96cf0>
        season:                 <aniworld.models.s_to.season.SerienstreamSeason object at 0x10ad96e40>

        title_de:               "Neuanfang"
        title_en:               "Pilot"
        episode_number:         1
        provider_data:          {('German', 'None'): {'VOE': 'https://serienstream.to/r?t=eyJpdiI6IkdVR2hyQjFXOUVLUGRqRGd1Ylo3cUE9PSIsInZhbHVlIjoiRDVIOEdHb2xOcGk3MmsrTVB2Yk9lakZoYS9YVXFsNlJ0SVJwYTNXZTM1bmQvOFpQaFJ4TWdoSHRzUEhzRTZoQVg1Zkx1OFVxZjhpNWYyR3VUd1U0SVE9PSIsIm1hYyI6IjAzOTAxNjA1YTFkMmM0OWI0MDEzNGE3NzQ5YzI0NWZmYTRiZDgxZDRiMDg0ZGYzOGE2M2JiZDQyMjgyZGE4YjMiLCJ0YWciOiIifQ%3D%3D'}, ('English', 'None'): {'VOE': 'https://serienstream.to/r?t=eyJpdiI6IitKSjl2K1EwOGcyZjNHS1VrRW0yQ0E9PSIsInZhbHVlIjoiVDRSQ01RMnpUdFZLblpLb1BGSm1LdE5RQ0U2b2h0cmdDRGRlTi82Q1VPMWJGellGQjhGZE45TldoeE9ESWNxWEhNNDBPQWl0OHM1MjJlaDNRdVY3Z0E9PSIsIm1hYyI6IjUyYjNkZjIwZGMwZWFlZjA1ZTgzNzIzNWI0M2FmZDI3NDcxNmY3OTQ3YTMxNGE0ZjFkNjcyYzFiZWM0MWE2YWUiLCJ0YWciOiIifQ%3D%3D'}}

        selected_path:          Downloads
        selected_language:      "German Dub"
        selected_provider:      "VOE"

        redirect_url:           https://serienstream.to/r?t=eyJpdiI6IlNvVkFWOURJTklBT05wTiszQkF5VVE9PSIsInZhbHVlIjoiUCtoM3JETHQxbUZVMThkY1RuT2p6TTd1aXdnYW9LNzNOb2t3QU5DV2RzUGxJWFA0WUxBaUpZd0Y4dGhJazhrRjFzT1dWVTlISFRpWTE5N0t2dWFtUEE9PSIsIm1hYyI6IjhiMzIxOTljMThlN2ZiYmZlNjJmMjYxYmE5YjhhMjY1NjI0YzM4NThhYzUzMTg3YzdiZjg5Y2U0ZmRhYjU5YmYiLCJ0YWciOiIifQ%3D%3D
        provider_url:           https://voe.sx/e/2gevxuvhffzd
        stream_url:             https://cdn-ybrlgbugcqvfwfxm.edgeon-bandwidth.com/engine/hls2-c/01/12274/32xqoasasgio_,n,.urlset/master.m3u8?t=AyZvb2TAsfUJASynb8yS1VVvV9VLR4L6iELp5QnC5NY&s=1769786403&e=14400&f=69846104&node=5oVG/75jdb0Y5X40bYOVrWQ5Z8VHd1xf5E7nxyia+5E=&i=185.213&sp=2500&asn=39351&q=n&rq=pSN9X93FqA34kNMYDUcS0wTzZ2nLYuaQH60wgnXd

        self._base_folder:      Downloads/American Horror Story (2011) [imdbid-tt1844624]
        self._folder_path:      Downloads/American Horror Story (2011) [imdbid-tt1844624]/Season 1
        self._file_name:        American Horror Story S1E1
        self._file_extension:   mkv
        self._episode_path:     Downloads/American Horror Story (2011) [imdbid-tt1844624]/Season 1/American Horror Story S1E1.mkv

        is_downloaded           {'exists': False, 'video_langs': set(), 'audio_langs': set()}

        _html:                  "<!doctype html>[...]"

    Methods:
        download()
        watch()
        syncplay()

    Attributes That Do Not Exists as on Aniworld:
        is_movie, skip_times
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
        if not self.__is_valid_serienstream_episode_url(url):
            raise ValueError(f"Invalid Serienstream episode URL: {url}")

        self.url = url
        self._series = series
        self._season = season

        self.__episode_number = episode_number
        self.__title_de = title_de
        self.__title_en = title_en

        self.__selected_path_param = selected_path
        self.__selected_language_param = selected_language
        self.__selected_provider_param = selected_provider

        self.__provider_data = None

        self.__selected_path = None
        self.__selected_language = None
        self.__selected_provider = None

        self.__redirect_url = None
        self.__provider_url = None

        # https://jellyfin.org/docs/general/server/media/shows/#organization
        self.__base_folder = None
        self.__folder_path = None
        self.__file_name = None
        self.__file_extension = None
        self.__episode_path = None

        self.__is_downloaded = None

        self.__html = None

    # -----------------------------
    # STATIC METHODS
    # -----------------------------

    @staticmethod
    def __is_valid_serienstream_episode_url(url):
        return bool(SERIENSTREAM_EPISODE_PATTERN.match(url))

    # -----------------------------
    # PUBLIC PROPERTIES (lazy load)
    # -----------------------------

    @property
    def series(self):
        if self._series is None:
            from .series import SerienstreamSeries

            if not self.url:
                raise ValueError("Episode URL is missing for series extraction.")
            series_url = self.url.rsplit("/staffel-", 1)[0]
            self._series = SerienstreamSeries(url=series_url)
        return self._series

    @property
    def season(self):
        if self._season is None:
            from .season import SerienstreamSeason

            if not self.url:
                raise ValueError("Episode URL is missing for season extraction.")
            season_url = self.url.rsplit("/episode-", 1)[0]
            self._season = SerienstreamSeason(url=season_url)
        return self._season

    @property
    def episode_number(self):
        if self.__episode_number is None:
            self.__episode_number = self.__extract_episode_number()
        return self.__episode_number

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
    def provider_data(self):
        if self.__provider_data is None:
            self.__provider_data = self.__extract_provider_data()
        return self.__provider_data

    @property
    def selected_path(self):
        if self.__selected_path is None:
            raw_path = self.__selected_path_param or os.getenv(
                "ANIWORLD_DOWNLOAD_PATH", str(Path.home() / "Downloads")
            )

            path = Path(raw_path).expanduser()

            if not path.is_absolute():
                path = Path.home() / path

            self.__selected_path = str(path)
        return self.__selected_path

    @selected_path.setter
    def selected_path(self, value):
        self.__selected_path_param = value
        self.__selected_path = None
        self.__base_folder = None
        self.__folder_path = None
        self.__episode_path = None

    @property
    def selected_language(self):
        if self.__selected_language is None:
            self.__selected_language = self.__selected_language_param or os.getenv(
                "ANIWORLD_LANGUAGE", "German"
            )
        return self.__selected_language

    @selected_language.setter
    def selected_language(self, value):
        self.__selected_language_param = value
        self.__selected_language = None
        self.__redirect_url = None
        self.__provider_url = None
        self.__is_downloaded = None
        self.__base_folder = None
        self.__folder_path = None
        self.__episode_path = None
        self.__file_name = None

    @property
    def selected_provider(self):
        if self.__selected_provider is None:
            self.__selected_provider = self.__selected_provider_param or os.getenv(
                "ANIWORLD_PROVIDER", "VOE"
            )
        return self.__selected_provider

    @property
    def redirect_url(self):
        if self.__redirect_url is None:
            link = self.provider_link(self.selected_language, self.selected_provider)
            if link is None:
                raise ValueError(
                    f"Language '{self.selected_language}' with provider "
                    f"'{self.selected_provider}' is not available for "
                    f"episode: {self.url}"
                )
            self.__redirect_url = link
        return self.__redirect_url

    @property
    def provider_url(self):
        if self.__provider_url is None:
            self.__provider_url = GLOBAL_SESSION.get(self.redirect_url).url
        return self.__provider_url

    @property
    def stream_url(self):
        try:
            stream_url = provider_functions[
                f"get_direct_link_from_{self.selected_provider.lower()}"
            ](self.provider_url)
        except KeyError:
            raise ValueError(
                f"The provider '{self.selected_provider}' is not yet implemented."
            )

        return stream_url

    # TODO: add this into a common base class
    @property
    def _base_folder(self):
        if self.__base_folder is None:
            naming_template = os.getenv("ANIWORLD_NAMING_TEMPLATE", NAMING_TEMPLATE)
            parts = naming_template.split("/")
            if len(parts) <= 1:
                self.__base_folder = Path(self.selected_path)
            else:
                folder_str = parts[0].format(
                    title=self.series.title_cleaned,
                    year=self.series.release_year,
                    imdbid=self.series.imdb,
                    season=f"{self.season.season_number:02d}",
                    episode=f"{self.episode_number:03d}",
                    language=self.selected_language,
                )
                self.__base_folder = Path(self.selected_path) / folder_str
        return self.__base_folder

    @property
    def _folder_path(self):
        if self.__folder_path is None:
            naming_template = os.getenv("ANIWORLD_NAMING_TEMPLATE", NAMING_TEMPLATE)
            parts = naming_template.split("/")
            if len(parts) <= 2:
                self.__folder_path = self._base_folder
            else:
                folder_str = parts[1].format(
                    title=self.series.title_cleaned,
                    year=self.series.release_year,
                    imdbid=self.series.imdb,
                    season=f"{self.season.season_number:02d}",
                    episode=f"{self.episode_number:03d}",
                    language=self.selected_language,
                )
                self.__folder_path = self._base_folder / folder_str
        return self.__folder_path

    @property
    def _file_name(self):
        if self.__file_name is None:
            naming_template = os.getenv("ANIWORLD_NAMING_TEMPLATE", NAMING_TEMPLATE)
            try:
                file_template = naming_template.split("/")[-1]
            except IndexError:
                file_template = f"{self.series.title_cleaned} S{self.season.season_number:02d}E{self.episode_number:03d}.mkv"

            # Remove extension
            if "." in file_template:
                file_template = ".".join(file_template.split(".")[:-1])

            # Replace %style% with {style} for compatibility
            file_template = file_template.replace("%title%", "{title}")
            file_template = file_template.replace("%year%", "{year}")
            file_template = file_template.replace("%imdbid%", "{imdbid}")
            file_template = file_template.replace("%season%", "{season}")
            file_template = file_template.replace("%episode%", "{episode}")
            file_template = file_template.replace("%language%", "{language}")

            self.__file_name = file_template.format(
                title=self.series.title_cleaned,
                year=self.series.release_year,
                imdbid=self.series.imdb,
                season=f"{self.season.season_number:02d}",
                episode=f"{self.episode_number:03d}",
                language=self.selected_language,
            )
        return self.__file_name

    @property
    def _file_extension(self):
        if self.__file_extension is None:
            naming_template = os.getenv("ANIWORLD_NAMING_TEMPLATE", NAMING_TEMPLATE)
            try:
                file_part = naming_template.split("/")[-1]
                if "." in file_part:
                    ext = file_part.rsplit(".", 1)[-1]
                    self.__file_extension = ext if ext else "mkv"
                else:
                    self.__file_extension = "mkv"
            except IndexError:
                self.__file_extension = "mkv"
        return self.__file_extension

    @property
    def _episode_path(self):
        if self.__episode_path is None:
            self.__episode_path = (
                self._folder_path / f"{self._file_name}.{self._file_extension}"
            )
        return self.__episode_path

    # END

    @property
    def is_downloaded(self):
        if self.__is_downloaded is None:
            self.__is_downloaded = check_downloaded(self._episode_path)
        return self.__is_downloaded

    @property
    def _html(self):
        if self.__html is None:
            if not self.url:
                raise ValueError("Episode URL is missing for HTML fetch.")
            logger.debug(f"fetching ({self.url})...")
            resp = GLOBAL_SESSION.get(self.url)
            self.__html = resp.text
        return self.__html

    # -----------------------------
    # PRIVATE EXTRACTION FUNCTIONS
    # -----------------------------

    def __extract_episode_number(self):
        """
        https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir/staffel-1/episode-1
        """

        if not self.url:
            raise ValueError("Episode URL is missing for episode number extraction.")
        return int(self.url.rstrip("/").split("-")[-1])

    def __extract_title_de(self):
        """
        <h2 class="h4 mb-1">S01E01: Neuanfang (Pilot) </h2>

        without parantheses
        """

        pattern = r"S\d{2}E\d{2}:\s(.*?)(\s\(|</h2>)"
        html = self._html
        if not html:
            return ""
        match = re.search(pattern, html)
        if match:
            return unescape(match.group(1).strip())
        return ""

    def __extract_title_en(self):
        """
        <h2 class="h4 mb-1">S01E01: Neuanfang (Pilot) </h2>

        in parantheses
        """

        pattern = r"S\d{2}E\d{2}:\s.*\((.*?)\)"
        html = self._html
        if not html:
            return ""
        match = re.search(pattern, html)
        if match:
            return unescape(match.group(1).strip())
        return ""

    def __extract_provider_data(self):
        """
        Extract provider links grouped by (Audio, Subtitles).

        Returns:
            dict[(Audio, Subtitles)][provider_name]
        """

        pattern = r'data-play-url="(.*?)".*?data-provider-name="(.*?)".*?data-language-label="(.*?)"'

        matches = re.findall(pattern, self._html, re.DOTALL)

        provider_data = {}

        for play_url, provider_name, language_label in matches:
            if language_label == "Deutsch":
                key = (Audio.GERMAN, Subtitles.NONE)
            elif language_label == "Englisch":
                key = (Audio.ENGLISH, Subtitles.NONE)
            else:
                continue

            provider_data.setdefault(key, {})[provider_name] = (
                f"https://serienstream.to{play_url}"
            )

        return provider_data

    def _normalize_language(self, language):
        """
        Convert a string language description to a (Audio, Subtitles) tuple if necessary.
        """
        if isinstance(language, tuple) and len(language) == 2:
            return language
        if isinstance(language, tuple) and len(language) == 2:
            return language
        if language in ["German Dub", "German", "Deutsch"]:
            return (Audio.GERMAN, Subtitles.NONE)
        if language in ["English Dub", "English", "Englisch"]:
            return (Audio.ENGLISH, Subtitles.NONE)
        raise ValueError(
            f"Only 'Deutsch'/'German Dub' and 'Englisch'/'English Dub' are supported for serienstream.to (got: {language})"
        )

    def provider_link(self, language=None, provider=None):
        """
        Get the provider URL for a given language and provider name.

        Args:
            language: tuple (Audio, Subtitles) or str. Defaults to self.selected_language.
            provider: str, provider name. Defaults to self.selected_provider.

        Returns:
            str URL if found, else raises ValueError
        """

        if language is None:
            language = self.selected_language

        language = self._normalize_language(language)

        if provider is None:
            provider = self.selected_provider

        provider_dict = self.provider_data.get(language)

        if not provider_dict:
            # Try fallback (by value in tuple): sometimes enums mismatch, fallback to value match
            for key, pdict in self.provider_data.items():
                if (
                    key[0].value == language[0].value
                    and key[1].value == language[1].value
                ):
                    provider_dict = pdict
                    break

        if not provider_dict:
            raise ValueError(f"No provider data found for language: {language}")

        url = provider_dict.get(provider)

        if url:
            return url

        raise ValueError(f"Provider '{provider}' not found for language: {language}.")

    # -----------------------------
    # PUBLIC METHODS
    # -----------------------------

    # Episode actions are implemented in aniworld.models.common.common
    download = episode_download
    watch = episode_watch
    syncplay = episode_syncplay
