import os
import re
from html import unescape
from pathlib import Path
from urllib.parse import urlparse

try:
    from ...config import (
        KINOGER_EPISODE_PATTERN,
        GLOBAL_SESSION,
        NAMING_TEMPLATE,
        Audio,
        Subtitles,
        build_provider_attempt_order,
        logger,
    )
    from ...extractors import provider_functions
    from ..common import ProviderData, check_downloaded, movie_folder_enabled
    from ..common.common import clean_title
    from ..common.common import download as episode_download
    from ..common.common import syncplay as episode_syncplay
    from ..common.common import watch as episode_watch
    from ..common.provider_map import host_to_provider
except ImportError:
    from aniworld.config import (
        KINOGER_EPISODE_PATTERN,
        GLOBAL_SESSION,
        NAMING_TEMPLATE,
        Audio,
        Subtitles,
        build_provider_attempt_order,
        logger,
    )
    from aniworld.extractors import provider_functions
    from aniworld.models.common import (
        ProviderData,
        check_downloaded,
        clean_title,
        movie_folder_enabled,
    )
    from aniworld.models.common import download as episode_download
    from aniworld.models.common import syncplay as episode_syncplay
    from aniworld.models.common import watch as episode_watch
    from aniworld.models.common.provider_map import host_to_provider

def _fetch_kinoger(url):
    try:
        from curl_cffi import requests as _curl
        return _curl.get(url, impersonate="chrome124", timeout=15)
    except ImportError:
        return GLOBAL_SESSION.get(url)

class KinogerEpisode:
    def __init__(
        self,
        url: str,
        selected_path: str | None = None,
        selected_language: str | None = None,
        selected_provider: str | None = None,
    ):
        if not bool(KINOGER_EPISODE_PATTERN.match(url)):
            raise ValueError(f"Invalid Kinoger episode URL: {url}")

        self.url = url
        self.__title = None
        self.__release_year = None
        self.__runtime_min = None
        self.__genres = None
        self.__description = None
        self.__poster_url = None
        self.__imdb_rating = None
        self.__episode_index = None

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

        self.__is_downloaded = None
        self.__html = None

    @property
    def episode_index(self):
        if self.__episode_index is None:
            parsed = urlparse(self.url)
            if parsed.fragment and parsed.fragment.startswith("ep="):
                try:
                    self.__episode_index = int(parsed.fragment.split("=")[1])
                except ValueError:
                    self.__episode_index = 1
            else:
                self.__episode_index = 1
        return self.__episode_index

    @property
    def title(self):
        if self.__title is None:
            self.__extract_title()
        return self.__title

    @property
    def title_cleaned(self):
        return clean_title(self.title or "")

    @property
    def poster_url(self):
        if self.__poster_url is None:
            self.__extract_poster_url()
        return self.__poster_url

    @property
    def description(self):
        if self.__description is None:
            self.__extract_description()
        return self.__description

    @property
    def release_year(self):
        if self.__release_year is None:
            self.__extract_release_year()
        return self.__release_year

    @property
    def runtime_min(self):
        if self.__runtime_min is None:
            self.__extract_runtime_min()
        return self.__runtime_min

    @property
    def genres(self):
        if self.__genres is None:
            self.__extract_genres()
        return self.__genres

    @property
    def imdb_rating(self):
        if self.__imdb_rating is None:
            self.__extract_imdb_rating()
        return self.__imdb_rating

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
            self.__selected_language = "German Dub"
        return self.__selected_language

    @selected_language.setter
    def selected_language(self, value):
        self.__selected_language = "German Dub"

    @property
    def selected_provider(self):
        if self.__selected_provider is None:
            self.__selected_provider = self.__selected_provider_param or os.getenv(
                "ANIWORLD_PROVIDER", "VOE"
            )
        return self.__selected_provider

    @selected_provider.setter
    def selected_provider(self, value):
        self.__selected_provider_param = value
        self.__selected_provider = None
        self.__redirect_url = None
        self.__provider_url = None

    @property
    def redirect_url(self):
        if self.__redirect_url is None:
            link = self.provider_link(self.selected_language, self.selected_provider)
            if link is None:
                avail = self.available_providers()
                if avail:
                    link = self.provider_link(self.selected_language, avail[0])
            if link is None:
                raise ValueError("No valid provider link found")
            self.__redirect_url = link
        return self.__redirect_url

    @property
    def provider_url(self):
        if self.__provider_url is None:
            self.__provider_url = self.redirect_url
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

    @property
    def _movie_basename(self):
        year = self.release_year
        base = self.title_cleaned or "Movie"
        return f"{base} ({year})" if year else base

    @property
    def _base_folder(self):
        if self.__base_folder is None:
            if movie_folder_enabled():
                self.__base_folder = Path(self.selected_path) / self._movie_basename
            else:
                self.__base_folder = Path(self.selected_path)
        return self.__base_folder

    @property
    def _folder_path(self):
        if self.__folder_path is None:
            self.__folder_path = self._base_folder
        return self.__folder_path

    @property
    def _file_name(self):
        if self.__file_name is None:
            self.__file_name = f"{self._movie_basename} E{self.episode_index}"
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

    @property
    def _html(self):
        if self.__html is None:
            logger.debug(f"fetching ({self.url})...")
            resp = _fetch_kinoger(self.url)
            self.__html = resp.text
        return self.__html

    def __extract_title(self):
        match = re.search(r'<h1 id="news-title"[^>]*>(.*?)</h1>', self._html)
        if not match:
            match = re.search(r'<meta property="og:title" content="(.*?)">', self._html)
        if match:
            self.__title = unescape(match.group(1).strip())

    def __extract_poster_url(self):
        match = re.search(r'<meta property="og:image" content="(.*?)">', self._html)
        if match:
            self.__poster_url = match.group(1)

    def __extract_description(self):
        match = re.search(r'<div class="text"[^>]*>.*?<img[^>]*>([\s\S]*?)<br>', self._html)
        if match:
            self.__description = unescape(match.group(1).strip())

    def __extract_release_year(self):
        match = re.search(r"Ver&ouml;ffentlicht:\s*(\d+)|Veröffentlicht:\s*(\d+)", self._html)
        if match:
            self.__release_year = int(match.group(1) or match.group(2))

    def __extract_runtime_min(self):
        match = re.search(r"Spielzeit:\s*(\d+)\s*min", self._html)
        if match:
            self.__runtime_min = int(match.group(1))

    def __extract_genres(self):
        match = re.search(r"Kategorien, Genre:\s*(.*?)(?:<br>|</div>)", self._html)
        if match:
            genres_raw = match.group(1)
            self.__genres = [re.sub(r'<[^>]+>', '', g).strip() for g in genres_raw.split(',') if g.strip()]

    def __extract_imdb_rating(self):
        match = re.search(r"Imdb:\s*([\d.]+)/10", self._html)
        if match:
            self.__imdb_rating = float(match.group(1))

    def __extract_provider_data(self):
        providers = {}
        for func_name in ["pw", "fsst", "go", "ollhd", "v", "e", "f", "u"]:
            match = re.search(rf"{func_name}\.show\(\d+,\s*\[(.*?)\]\)", self._html)
            if match:
                arrays_str = match.group(1)
                arrays = re.findall(r"\['(.*?)'\]", arrays_str)
                idx = self.episode_index - 1
                if 0 <= idx < len(arrays):
                    urls = arrays[idx].split()
                    if urls:
                        first_url = urls[0].strip()
                        parsed_url = urlparse(first_url)
                        domain = parsed_url.netloc
                        provider = host_to_provider(domain, require_extractor=False) or domain
                        providers[provider] = first_url

        if not providers:
            return None
        return ProviderData({(Audio.GERMAN, Subtitles.NONE): providers})

    def provider_link(self, language=None, provider=None):
        if provider is None:
            provider = self.selected_provider

        provider_data = self.provider_data
        if not isinstance(provider_data, ProviderData):
            return None

        provider_dict = provider_data.get((Audio.GERMAN, Subtitles.NONE))
        if not provider_dict:
            return None

        key = str(provider).strip()
        link = provider_dict.get(key) or provider_dict.get(key.upper())
        if link:
            return link

        # Fallback if specific provider not found
        for k, v in provider_dict.items():
            if k.lower() == key.lower():
                return v

        return None

    def available_providers(self, language=None):
        provider_data = self.provider_data
        if not isinstance(provider_data, ProviderData):
            return ()
        provider_dict = provider_data.get((Audio.GERMAN, Subtitles.NONE))
        return tuple(provider_dict.keys()) if provider_dict else ()

    def provider_attempt_order(self):
        return build_provider_attempt_order(
            self.selected_provider,
            self.available_providers(),
        )

    download = episode_download
    watch = episode_watch
    syncplay = episode_syncplay
