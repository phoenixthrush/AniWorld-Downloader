import os
import re
from pathlib import Path

from ...config import NAMING_TEMPLATE, logger
from ...extractors.provider.hanime_tv import (
    fetch_hanime_api_data,
    get_direct_link_from_hanime_tv,
)
from ..common import check_downloaded
from ..common.common import (
    download_hanime as episode_download,
)
from ..common.common import (
    syncplay as episode_syncplay,
    watch as episode_watch,
)


class HanimeTVEpisode:
    """
    Represents a single video on hanime.tv.

    Parameters:
        url:                Required. e.g. https://hanime.tv/videos/hentai/ane-yome-quartet-1
        series:             Parent HanimeTVSeries object.
        season:             Parent HanimeTVSeason object.
        episode_number:     Episode number within the franchise.
        selected_path:      Optional download path override.

    Attributes (Example):
        url:                "https://hanime.tv/videos/hentai/ane-yome-quartet-1"
        title_en:           "Ane Yome Quartet 1"
        episode_number:     1
        stream_url:         "https://streamable.cloud/hls/stream.m3u8..."
    """

    def __init__(
        self,
        url,
        series=None,
        season=None,
        episode_number=None,
        selected_path=None,
        selected_language=None,
        selected_provider=None,
    ):
        if not self._is_valid_url(url):
            raise ValueError(f"Invalid hanime.tv URL: {url}")

        self.url = url
        self._series = series
        self._season = season

        self.__episode_number = episode_number

        self.__selected_path_param = selected_path
        self.__selected_language = selected_language or "Japanese"
        self.__selected_provider = selected_provider or "HanimeTV"

        self.__title_en = None
        self.__title_de = None
        self.__description = None
        self.__poster_url = None
        self.__duration_ms = None

        self.__stream_url = None
        self.__provider_data = None

        self.__base_folder = None
        self.__folder_path = None
        self.__file_name = None
        self.__file_extension = None
        self.__episode_path = None

        self.__is_downloaded = None

        self.__api_data = None

    @staticmethod
    def _is_valid_url(url):
        return bool(
            re.match(
                r"^https?://(?:www\.)?hanime\.tv/videos/hentai/[A-Za-z0-9\-]+/?$",
                url,
            )
        )

    @staticmethod
    def _slug_from_url(url):
        return url.rstrip("/").split("/")[-1]

    # -----------------------------
    # API DATA
    # -----------------------------

    @property
    def _api_data(self):
        if self.__api_data is None:
            if self._series and hasattr(self._series, "_api_data"):
                franchise_videos = (
                    self._series._api_data.get("hentai_franchise_hentai_videos") or []
                )
                my_slug = self._slug_from_url(self.url)
                series_slug = self._slug_from_url(self._series.url)
                if my_slug == series_slug:
                    self.__api_data = self._series._api_data
                    return self.__api_data

            slug = self._slug_from_url(self.url)
            self.__api_data = fetch_hanime_api_data(slug)
        return self.__api_data

    # -----------------------------
    # PROPERTIES
    # -----------------------------

    @property
    def title_en(self):
        if self.__title_en is None:
            hv = self._api_data.get("hentai_video") or {}
            self.__title_en = hv.get("name", "")
        return self.__title_en

    @property
    def title_de(self):
        return self.__title_de or ""

    @property
    def episode_number(self):
        if self.__episode_number is None:
            match = re.search(r"-(\d+)$", self._slug_from_url(self.url))
            self.__episode_number = int(match.group(1)) if match else 1
        return self.__episode_number

    @property
    def series(self):
        if self._series is None:
            from .series import HanimeTVSeries

            self._series = HanimeTVSeries(self.url)
        return self._series

    @property
    def season(self):
        if self._season is None:
            from .season import HanimeTVSeason

            franchise_videos = self._api_data.get("hentai_franchise_hentai_videos") or []
            slugs = [v["slug"] for v in franchise_videos if v.get("slug")]
            if not slugs:
                slugs = [self._slug_from_url(self.url)]
            self._season = HanimeTVSeason(episode_slugs=slugs, series=self.series)
        return self._season

    @property
    def description(self):
        if self.__description is None:
            hv = self._api_data.get("hentai_video") or {}
            raw = hv.get("description", "")
            self.__description = re.sub(r"<[^>]+>", "", raw).strip()
        return self.__description

    @property
    def poster_url(self):
        if self.__poster_url is None:
            hv = self._api_data.get("hentai_video") or {}
            self.__poster_url = hv.get("poster_url") or hv.get("cover_url") or ""
        return self.__poster_url

    @property
    def stream_url(self):
        if self.__stream_url is None:
            self.__stream_url = get_direct_link_from_hanime_tv(self._api_data)
        return self.__stream_url

    @property
    def provider_data(self):
        if self.__provider_data is None:
            self.__provider_data = {}
        return self.__provider_data

    @property
    def selected_path(self):
        raw_path = self.__selected_path_param or os.getenv(
            "ANIWORLD_DOWNLOAD_PATH", str(Path.home() / "Downloads")
        )
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = Path.home() / path
        return str(path)

    @selected_path.setter
    def selected_path(self, value):
        self.__selected_path_param = value
        self.__base_folder = None
        self.__folder_path = None
        self.__episode_path = None

    @property
    def selected_language(self):
        return self.__selected_language

    @selected_language.setter
    def selected_language(self, value):
        self.__selected_language = value

    @property
    def selected_provider(self):
        return self.__selected_provider

    @selected_provider.setter
    def selected_provider(self, value):
        self.__selected_provider = value

    # -----------------------------
    # FILE PATHS
    # -----------------------------

    @staticmethod
    def _format_naming_part(template_part, title, year, season_num, episode_num, language):
        return template_part.format(
            title=title,
            year=year,
            imdbid="",
            season=f"{season_num:02d}",
            episode=f"{episode_num:03d}",
            language=language,
        )

    @property
    def _base_folder(self):
        if self.__base_folder is None:
            naming_template = os.getenv("ANIWORLD_NAMING_TEMPLATE", NAMING_TEMPLATE)
            parts = naming_template.split("/")
            if len(parts) <= 1:
                self.__base_folder = Path(self.selected_path)
            else:
                folder_str = self._format_naming_part(
                    parts[0],
                    self.series.title_cleaned,
                    self.series.release_year,
                    self.season.season_number,
                    self.episode_number,
                    self.selected_language,
                )
                # Strip empty imdbid markers from folder name
                folder_str = re.sub(r"\s*\[imdbid-\]\s*", "", folder_str).strip()
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
                folder_str = self._format_naming_part(
                    parts[1],
                    self.series.title_cleaned,
                    self.series.release_year,
                    self.season.season_number,
                    self.episode_number,
                    self.selected_language,
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
                file_template = "{title} S{season}E{episode}.mkv"

            if "." in file_template:
                file_template = ".".join(file_template.split(".")[:-1])

            file_template = file_template.replace("%title%", "{title}")
            file_template = file_template.replace("%year%", "{year}")
            file_template = file_template.replace("%imdbid%", "{imdbid}")
            file_template = file_template.replace("%season%", "{season}")
            file_template = file_template.replace("%episode%", "{episode}")
            file_template = file_template.replace("%language%", "{language}")

            self.__file_name = self._format_naming_part(
                file_template,
                self.series.title_cleaned,
                self.series.release_year,
                self.season.season_number,
                self.episode_number,
                self.selected_language,
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

    @property
    def is_downloaded(self):
        if self.__is_downloaded is None:
            self.__is_downloaded = check_downloaded(self._episode_path)
        return self.__is_downloaded

    # Episode actions are implemented in aniworld.models.common.common
    download = episode_download
    watch = episode_watch
    syncplay = episode_syncplay
