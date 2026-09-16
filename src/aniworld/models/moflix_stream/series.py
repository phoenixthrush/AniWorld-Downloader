import os
import re
import json
from html import unescape
from pathlib import Path
from urllib.parse import urlparse, parse_qs

try:
    from ...config import (
        MOFLIX_SERIES_PATTERN,
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
        MOFLIX_SERIES_PATTERN,
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

def _fetch_moflix(url, session_cookies=None, csrf_token=None):
    try:
        from curl_cffi import requests as _curl
        headers = {}
        if csrf_token:
            headers["X-XSRF-TOKEN"] = csrf_token
            headers["X-Requested-With"] = "XMLHttpRequest"
            headers["Referer"] = "https://moflix-stream.xyz/"
            headers["Accept"] = "application/json"
        return _curl.get(url, cookies=session_cookies, headers=headers, impersonate="chrome124", timeout=15)
    except ImportError:
        headers = {}
        if csrf_token:
            headers["X-XSRF-TOKEN"] = csrf_token
            headers["X-Requested-With"] = "XMLHttpRequest"
            headers["Referer"] = "https://moflix-stream.xyz/"
            headers["Accept"] = "application/json"
        return GLOBAL_SESSION.get(url, cookies=session_cookies, headers=headers)

class MoflixEpisode:
    def __init__(
        self,
        url: str,
        selected_path: str | None = None,
        selected_language: str | None = None,
        selected_provider: str | None = None,
    ):
        if not bool(MOFLIX_SERIES_PATTERN.match(url)):
            raise ValueError(f"Invalid Moflix episode URL: {url}")

        self.url = url
        self.__title = None
        self.__release_year = None
        self.__runtime_min = None
        self.__genres = None
        self.__description = None
        self.__poster_url = None
        self.__imdb_rating = None
        self.__title_id = None
        self.__season_id = None
        self.__episode_id = None

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

        self.__csrf_token = None
        self.__session_cookies = None
        self.__metadata = None
        self.__videos_data = None

    def __fetch_initial_data(self):
        if self.__csrf_token is None:
            resp = _fetch_moflix(self.url)
            self.__session_cookies = resp.cookies
            match = re.search(r'window\.bootstrapData\s*=\s*(\{.*?\});', resp.text)
            if match:
                try:
                    data = json.loads(match.group(1))
                    self.__csrf_token = data.get("csrf_token")
                except json.JSONDecodeError:
                    pass

    def __fetch_metadata(self):
        if self.__metadata is None:
            self.__fetch_initial_data()
            api_url = f"https://moflix-stream.xyz/api/v1/titles/{self.title_id}"
            resp = _fetch_moflix(api_url, self.__session_cookies, self.__csrf_token)
            try:
                self.__metadata = resp.json()
            except Exception:
                self.__metadata = {}
        return self.__metadata

    def __fetch_videos_data(self):
        if self.__videos_data is None:
            self.__fetch_initial_data()
            if self.is_series:
                api_url = f"https://moflix-stream.xyz/api/v1/titles/{self.title_id}/seasons/{self.season_id}/episodes/{self.episode_id}"
            else:
                api_url = f"https://moflix-stream.xyz/api/v1/titles/{self.title_id}"
                
            resp = _fetch_moflix(api_url, self.__session_cookies, self.__csrf_token)
            try:
                data = resp.json()
                if self.is_series:
                    self.__videos_data = data.get('episode', {}).get('videos', [])
                else:
                    self.__videos_data = data.get('title', {}).get('videos', [])
            except Exception:
                self.__videos_data = []
        return self.__videos_data

    @property
    def title_id(self):
        if self.__title_id is None:
            match = re.search(r'/titles/(\d+)', self.url)
            if match:
                self.__title_id = match.group(1)
        return self.__title_id

    @property
    def season_id(self):
        if self.__season_id is None:
            match = re.search(r'/season/(\d+)', self.url)
            if match:
                self.__season_id = int(match.group(1))
            else:
                qs = parse_qs(urlparse(self.url).query)
                if 'season' in qs:
                    self.__season_id = int(qs['season'][0])
                else:
                    self.__season_id = 1
        return self.__season_id

    @property
    def episode_id(self):
        if self.__episode_id is None:
            match = re.search(r'/episodes/(\d+)', self.url)
            if match:
                self.__episode_id = int(match.group(1))
            else:
                qs = parse_qs(urlparse(self.url).query)
                if 'episode' in qs:
                    self.__episode_id = int(qs['episode'][0])
                else:
                    self.__episode_id = 1
        return self.__episode_id

    @property
    def title(self):
        if self.__title is None:
            self.__title = self.__fetch_metadata().get("title", {}).get("name", "")
        return self.__title

    @property
    def title_cleaned(self):
        return clean_title(self.title or "")

    @property
    def poster_url(self):
        if self.__poster_url is None:
            self.__poster_url = self.__fetch_metadata().get("title", {}).get("poster")
        return self.__poster_url

    @property
    def description(self):
        if self.__description is None:
            self.__description = self.__fetch_metadata().get("title", {}).get("description")
        return self.__description

    @property
    def release_year(self):
        if self.__release_year is None:
            self.__release_year = self.__fetch_metadata().get("title", {}).get("year")
        return self.__release_year

    @property
    def runtime_min(self):
        if self.__runtime_min is None:
            self.__runtime_min = self.__fetch_metadata().get("title", {}).get("runtime")
        return self.__runtime_min

    @property
    def genres(self):
        if self.__genres is None:
            genres_data = self.__fetch_metadata().get("title", {}).get("genres", [])
            self.__genres = [g.get("name") for g in genres_data if isinstance(g, dict)]
        return self.__genres

    @property
    def imdb_rating(self):
        if self.__imdb_rating is None:
            self.__imdb_rating = self.__fetch_metadata().get("title", {}).get("rating")
        return self.__imdb_rating

    @property
    def provider_data(self):
        if self.__provider_data is None:
            videos = self.__fetch_videos_data()
            
            if not isinstance(videos, list):
                videos = []

            providers = {}
            for video in videos:
                src = video.get("src")
                if src:
                    name = video.get("name", "")
                    provider = host_to_provider(name, require_extractor=False) or name
                    if not provider or provider == name:
                        parsed = urlparse(src)
                        provider = host_to_provider(parsed.netloc, require_extractor=False) or parsed.netloc
                    providers[provider] = src

            if not providers:
                self.__provider_data = None
            else:
                self.__provider_data = ProviderData({(Audio.GERMAN, Subtitles.NONE): providers})
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
        self.__redirect_url = None
        self.__provider_url = None

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
            meta = self.__fetch_metadata()
            is_series = meta.get("is_series", False) or meta.get("type") == "series"
            if is_series:
                self.__folder_path = self._base_folder / f"Season {self.season_id}"
            else:
                self.__folder_path = self._base_folder
        return self.__folder_path

    @property
    def _file_name(self):
        if self.__file_name is None:
            meta = self.__fetch_metadata()
            is_series = meta.get("is_series", False) or meta.get("type") == "series"
            if is_series:
                self.__file_name = f"{self._movie_basename} S{self.season_id}E{self.episode_id}"
            else:
                self.__file_name = self._movie_basename
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
    def is_series(self):
        title_data = self.__fetch_metadata().get("title", {})
        return title_data.get("is_series", False) or title_data.get("type") == "series"

    @property
    def seasons(self):
        seasons_data = self.__fetch_metadata().get("seasons", {}).get("data", [])
        if not seasons_data:
            return [MoflixSeason(self.url, self, 1, 1)]
        
        return [
            MoflixSeason(
                url=f"https://moflix-stream.xyz/titles/{self.title_id}?season={s['number']}",
                series=self,
                season_number=s["number"],
                episode_count=s.get("episodes_count", 1)
            )
            for s in sorted(seasons_data, key=lambda x: x["number"])
        ]

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

class MoflixSeason:
    def __init__(self, url, series, season_number=None, episode_count=None):
        self.url = url
        self.series = series
        if season_number is None:
            # try to parse from url
            from urllib.parse import urlparse, parse_qs
            import re
            qs = parse_qs(urlparse(url).query)
            if 'season' in qs:
                self.season_number = int(qs['season'][0])
            else:
                match = re.search(r'/season/(\d+)', url)
                if match:
                    self.season_number = int(match.group(1))
                else:
                    self.season_number = 1
        else:
            self.season_number = season_number
        self.episode_count = episode_count if episode_count is not None else 1

    @property
    def are_movies(self):
        return not self.series.is_series

    @property
    def episodes(self):
        # Ensure session is initialized
        self.series._MoflixEpisode__fetch_initial_data()
        
        api_url = f'https://moflix-stream.xyz/api/v1/titles/{self.series.title_id}/seasons/{self.season_number}?perPage=500'
        from src.aniworld.models.moflix_stream.series import _fetch_moflix
        resp = _fetch_moflix(api_url, self.series._MoflixEpisode__session_cookies, self.series._MoflixEpisode__csrf_token)
        try:
            data = resp.json()
            eps_data = data.get('episodes', {}).get('data', [])
        except Exception:
            eps_data = []

        class MoflixEpProxy:
            def __init__(self, ep_data, season_obj):
                self.season = season_obj
                self.episode_number = ep_data.get('episode_number', 1)
                self.url = f'https://moflix-stream.xyz/titles/{season_obj.series.title_id}/season/{season_obj.season_number}/episodes/{self.episode_number}'
                self.title_de = ''
                self.title_en = ep_data.get('name', '')
                self._ep_data = ep_data

            @property
            def provider_data(self):
                # Lazy load via MoflixEpisode
                from aniworld.models.moflix_stream.series import MoflixEpisode
                ep_model = MoflixEpisode(self.url)
                return ep_model.provider_data

        return [MoflixEpProxy(ep, self) for ep in sorted(eps_data, key=lambda x: x.get('episode_number', 1))]

