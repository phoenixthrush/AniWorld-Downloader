import json
import os
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from ...config import (
        GLOBAL_SESSION,
        MOFLIX_SERIES_PATTERN,
        NAMING_TEMPLATE,
        Audio,
        Subtitles,
        build_provider_attempt_order,
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
        GLOBAL_SESSION,
        MOFLIX_SERIES_PATTERN,
        NAMING_TEMPLATE,
        Audio,
        Subtitles,
        build_provider_attempt_order,
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
        for attempt in range(3):
            response = _curl.get(
                url,
                cookies=session_cookies,
                headers=headers,
                impersonate="chrome124",
                timeout=15,
            )
            if response.status_code != 429 or attempt == 2:
                return response
            time.sleep(attempt + 1)
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
        season=None,
        series=None,
        episode_number: int | None = None,
        title_en: str = "",
    ):
        if not bool(MOFLIX_SERIES_PATTERN.match(url)):
            raise ValueError(f"Invalid Moflix episode URL: {url}")

        self.url = url
        self._season = season
        self._series = series
        self.__episode_number = episode_number
        self.__title_en = title_en
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
        if (
            self.__csrf_token is None
            and self._series is not None
            and self._series is not self
        ):
            self._series.__fetch_initial_data()
            self.__session_cookies = self._series.__session_cookies
            self.__csrf_token = self._series.__csrf_token

        if self.__csrf_token is None:
            resp = _fetch_moflix(self.url)
            resp.raise_for_status()
            self.__session_cookies = resp.cookies
            match = re.search(r"window\.bootstrapData\s*=\s*(\{.*?\});", resp.text)
            if not match:
                raise ValueError("Moflix bootstrap data not found")
            data = json.loads(match.group(1))
            self.__csrf_token = data.get("csrf_token")
            if not self.__csrf_token:
                raise ValueError("Moflix CSRF token not found")

    def __fetch_metadata(self):
        if (
            self.__metadata is None
            and self._series is not None
            and self._series is not self
        ):
            self.__metadata = self._series.__fetch_metadata()

        if self.__metadata is None:
            api_url = f"https://moflix-stream.xyz/api/v1/titles/{self.title_id}"
            resp = self._api_get(api_url)
            resp.raise_for_status()
            self.__metadata = resp.json()
            if not isinstance(self.__metadata, dict):
                raise ValueError("Moflix title API returned invalid data")
        return self.__metadata

    def _api_get(self, url):
        """Fetch an API URL with this title's authenticated browser context."""
        self.__fetch_initial_data()
        return _fetch_moflix(url, self.__session_cookies, self.__csrf_token)

    def __fetch_videos_data(self):
        if self.__videos_data is None:
            if self.is_series:
                api_url = f"https://moflix-stream.xyz/api/v1/titles/{self.title_id}/seasons/{self.season_id}/episodes/{self.episode_id}"
                resp = self._api_get(api_url)
                resp.raise_for_status()
                data = resp.json()
                item = data.get("episode")
            else:
                item = self._title_data
            if not isinstance(item, dict):
                raise ValueError("Moflix video API returned invalid data")
            videos = item.get("videos") or []
            if not isinstance(videos, list):
                raise ValueError("Moflix video list has an invalid format")
            self.__videos_data = videos
        return self.__videos_data

    @property
    def title_id(self):
        if self.__title_id is None:
            match = re.search(r"/titles/(\d+)", self.url)
            if match:
                self.__title_id = match.group(1)
        return self.__title_id

    @property
    def season_id(self):
        if self.__season_id is None:
            match = re.search(r"/season/(\d+)", self.url)
            if match:
                self.__season_id = int(match.group(1))
            else:
                qs = parse_qs(urlparse(self.url).query)
                if "season" in qs:
                    self.__season_id = int(qs["season"][0])
                else:
                    self.__season_id = 1
        return self.__season_id

    @property
    def episode_id(self):
        if self.__episode_id is None:
            match = re.search(r"/episodes/(\d+)", self.url)
            if match:
                self.__episode_id = int(match.group(1))
            else:
                qs = parse_qs(urlparse(self.url).query)
                if "episode" in qs:
                    self.__episode_id = int(qs["episode"][0])
                else:
                    self.__episode_id = 1
        return self.__episode_id

    @property
    def series(self):
        return self._series or self

    @property
    def season(self):
        return self._season

    @property
    def season_number(self):
        if self._season is not None:
            return self._season.season_number
        return self.season_id

    @property
    def episode_number(self):
        return self.__episode_number or self.episode_id

    @property
    def title_de(self):
        return ""

    @property
    def title_en(self):
        return self.__title_en

    @property
    def title(self):
        if self.__title is None:
            self.__title = self._title_data.get("name", "")
        return self.__title

    @property
    def title_cleaned(self):
        return clean_title(self.title or "")

    @property
    def release_year(self):
        if self.__release_year is None:
            self.__release_year = self._title_data.get("year")
        return self.__release_year

    @property
    def runtime_min(self):
        if self.__runtime_min is None:
            self.__runtime_min = self._title_data.get("runtime")
        return self.__runtime_min

    @property
    def genres(self):
        if self.__genres is None:
            self.__genres = [
                g.get("name")
                for g in self._title_data.get("genres", [])
                if g.get("name")
            ]
        return self.__genres

    @property
    def description(self):
        if self.__description is None:
            self.__description = self._title_data.get("description", "")
        return self.__description

    @property
    def poster_url(self):
        if self.__poster_url is None:
            self.__poster_url = self._title_data.get("poster", "")
            if self.__poster_url and not self.__poster_url.startswith("http"):
                self.__poster_url = (
                    "https://moflix-stream.xyz/" + self.__poster_url.lstrip("/")
                )
        return self.__poster_url

    @property
    def imdb_rating(self):
        if self.__imdb_rating is None:
            self.__imdb_rating = self._title_data.get("rating", 0.0)
        return self.__imdb_rating

    @property
    def provider_data(self):
        if self.__provider_data is None:
            videos = self.__fetch_videos_data()

            if not isinstance(videos, list):
                videos = []

            providers = {}
            for video in videos:
                if not isinstance(video, dict):
                    continue
                src = video.get("src")
                if not isinstance(src, str) or urlparse(src).scheme != "https":
                    continue
                # The API labels these "Mirror 1", "Mirror 2", etc. Their URL,
                # not the label, determines which extractor can handle them.
                provider = host_to_provider(urlparse(src).netloc)
                if provider:
                    providers[provider] = src

            if not providers:
                self.__provider_data = None
            else:
                self.__provider_data = ProviderData(
                    {(Audio.GERMAN, Subtitles.NONE): providers}
                )
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
                raise ValueError(
                    f"No Moflix link for provider {self.selected_provider}"
                )
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
        if not isinstance(stream_url, str) or not stream_url:
            raise ValueError(
                f"Provider {self.selected_provider} returned no stream URL"
            )
        return stream_url

    @property
    def _separate_audio_rendition(self):
        # Moflix HLS masters can default to English while carrying German as
        # a separate rendition. The shared HLS downloader selects the dub.
        return True

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
            if self.is_series:
                self.__folder_path = self._base_folder / f"Season {self.season_id}"
            else:
                self.__folder_path = self._base_folder
        return self.__folder_path

    @property
    def _file_name(self):
        if self.__file_name is None:
            if self.is_series:
                self.__file_name = (
                    f"{self._movie_basename} S{self.season_id}E{self.episode_id}"
                )
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
    def _title_data(self):
        data = self.__fetch_metadata().get("title", {})
        if not isinstance(data, dict):
            raise TypeError("Moflix title data has an invalid format")
        return data

    @property
    def is_series(self):
        return (
            self._title_data.get("is_series", False)
            or self._title_data.get("type") == "series"
        )

    @property
    def seasons(self):
        seasons = self.__fetch_metadata().get("seasons") or {}
        seasons_data = seasons.get("data", []) if isinstance(seasons, dict) else []
        if not seasons_data:
            return [MoflixSeason(self.url, self, 1, 1)]

        return [
            MoflixSeason(
                url=f"https://moflix-stream.xyz/titles/{self.title_id}?season={s['number']}",
                series=self,
                season_number=s["number"],
                episode_count=s.get("episodes_count", 1),
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
    def __init__(self, url, series=None, season_number=None, episode_count=None):
        self.url = url
        self._series = series
        if season_number is None:
            # try to parse from url
            qs = parse_qs(urlparse(url).query)
            if "season" in qs:
                self.season_number = int(qs["season"][0])
            else:
                match = re.search(r"/season/(\d+)", url)
                if match:
                    self.season_number = int(match.group(1))
                else:
                    self.season_number = 1
        else:
            self.season_number = season_number
        self.episode_count = episode_count if episode_count is not None else 1
        self.__episodes = None

    @property
    def series(self):
        if self._series is None:
            self._series = MoflixEpisode(self.url)
        return self._series

    @property
    def are_movies(self):
        return not self.series.is_series

    @property
    def episodes(self):
        if self.__episodes is None:
            self.__episodes = self.__build_episodes()
        return self.__episodes

    def __build_episodes(self):
        if not self.series.is_series:
            return [
                MoflixEpisode(
                    url=self.series.url,
                    season=self,
                    series=self.series,
                    episode_number=1,
                    title_en=self.series.title,
                )
            ]

        api_url = (
            f"https://moflix-stream.xyz/api/v1/titles/{self.series.title_id}"
            f"/seasons/{self.season_number}?perPage=500"
        )
        resp = self.series._api_get(api_url)
        resp.raise_for_status()
        data = resp.json()
        episodes = data.get("episodes") or {}
        eps_data = episodes.get("data", []) if isinstance(episodes, dict) else []
        if not isinstance(eps_data, list):
            raise TypeError("Moflix episode list has an invalid format")

        results = []
        for ep_data in sorted(eps_data, key=lambda x: x.get("episode_number", 1)):
            episode_number = ep_data.get("episode_number", 1)
            ep_url = (
                f"https://moflix-stream.xyz/titles/{self.series.title_id}"
                f"/season/{self.season_number}/episodes/{episode_number}"
            )
            results.append(
                MoflixEpisode(
                    url=ep_url,
                    season=self,
                    series=self.series,
                    episode_number=episode_number,
                    title_en=ep_data.get("name", ""),
                )
            )
        return results
