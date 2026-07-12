"""cineby.at models (movies + TV).

cineby is a TMDB-based Next.js app that resolves its streams client-side
(encrypted source API behind Cloudflare), so metadata comes from the TMDB proxy
it uses (`db.wingsdatabase.com/3`, no API key needed) and the playable HLS URL
is captured with the headless browser — the same approach already used for
hanime. URLs are `/movie/<tmdb_id>` and `/tv/<tmdb_id>/<season>/<episode>`.
"""

import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from ...config import (
        Audio,
        Subtitles,
        logger,
    )
    from ..common import check_downloaded, movie_folder_enabled
    from ..common.common import clean_title
    from ..common.common import download as episode_download
    from ..common.common import syncplay as episode_syncplay
    from ..common.common import watch as episode_watch
    from ..common.http import get_html, get_session
except ImportError:
    from aniworld.config import (
        Audio,
        Subtitles,
        logger,
    )
    from aniworld.models.common import check_downloaded, movie_folder_enabled
    from aniworld.models.common.common import clean_title
    from aniworld.models.common.common import download as episode_download
    from aniworld.models.common.common import syncplay as episode_syncplay
    from aniworld.models.common.common import watch as episode_watch
    from aniworld.models.common.http import get_html, get_session

CINEBY_BASE = "https://www.cineby.at"
TMDB_PROXY = "https://db.wingsdatabase.com/3"
TMDB_IMG = "https://image.tmdb.org/t/p/w500"

_TMDB_HEADERS = {
    "Accept-Encoding": "gzip, deflate",
    "Origin": CINEBY_BASE,
    "Referer": f"{CINEBY_BASE}/",
}


def tmdb_get(path):
    """GET a TMDB proxy path and return parsed JSON (or {})."""
    sep = "&" if "?" in path else "?"
    url = f"{TMDB_PROXY}{path}{sep}language=en-US"
    try:
        resp = get_session().get(url, headers=_TMDB_HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.debug(f"cineby TMDB fetch failed for {path}: {exc}")
        return {}


def _year(date_str):
    return (date_str or "")[:4]


def _poster(path):
    return f"{TMDB_IMG}{path}" if path else ""


def cineby_movie_url(tmdb_id):
    return f"{CINEBY_BASE}/movie/{tmdb_id}"


def cineby_tv_url(tmdb_id):
    return f"{CINEBY_BASE}/tv/{tmdb_id}"


def cineby_episode_url(tmdb_id, season, episode):
    return f"{CINEBY_BASE}/tv/{tmdb_id}/{season}/{episode}"


def cineby_season_url(media_type, tmdb_id, season):
    """Season URL carrying its number so api/episodes can tell seasons apart."""
    if media_type == "movie":
        return cineby_movie_url(tmdb_id)
    return f"{CINEBY_BASE}/tv/{tmdb_id}?s={season}"


def parse_cineby_url(url):
    """Return (media_type, tmdb_id, season, episode) from a cineby URL."""
    path = re.sub(r"^https?://[^/]+", "", url).strip("/")
    parts = path.split("/")
    if len(parts) >= 2 and parts[0] == "movie":
        return "movie", parts[1], None, None
    if len(parts) >= 2 and parts[0] == "tv":
        season = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        episode = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else None
        return "tv", parts[1], season, episode
    return None, None, None, None


class CinebyEpisode:
    def __init__(
        self,
        url,
        selected_path=None,
        selected_language=None,
        selected_provider=None,
        season=None,
        series=None,
        episode_number=None,
        season_number=None,
        title=None,
    ):
        self.url = url
        self._series = series
        self._season = season
        self.__title = title

        media_type, tmdb_id, url_season, url_episode = parse_cineby_url(url)
        self.media_type = media_type or "movie"
        self.tmdb_id = tmdb_id
        self.is_movie = self.media_type == "movie"
        self.__episode_number = episode_number or url_episode or 1
        self.__season_number = season_number or url_season or 1

        self.__selected_path_param = selected_path
        self.__selected_language_param = selected_language
        self.__selected_provider_param = selected_provider

        self.__selected_path = None
        self.__stream_url = None

        self.__base_folder = None
        self.__folder_path = None
        self.__file_name = None
        self.__file_extension = None
        self.__episode_path = None
        self.__is_downloaded = None
        self.__meta = None

    # ---- metadata -----------------------------------------------------------
    @property
    def _meta(self):
        if self.__meta is None:
            if self.is_movie:
                self.__meta = tmdb_get(f"/movie/{self.tmdb_id}") or {}
            else:
                self.__meta = tmdb_get(f"/tv/{self.tmdb_id}") or {}
        return self.__meta

    @property
    def title(self):
        if self.__title:
            return self.__title
        m = self._meta
        return m.get("title") or m.get("name") or f"cineby-{self.tmdb_id}"

    @property
    def title_cleaned(self):
        return clean_title(self.title)

    @property
    def release_year(self):
        m = self._meta
        return _year(m.get("release_date") or m.get("first_air_date"))

    @property
    def title_de(self):
        return "" if self.is_movie else f"Episode {self.episode_number}"

    @property
    def title_en(self):
        return self.title if self.is_movie else ""

    @property
    def episode_number(self):
        return self.__episode_number or 1

    @property
    def season_number(self):
        if self.is_movie:
            return 1
        if self._season is not None:
            return self._season.season_number
        return self.__season_number or 1

    @property
    def series(self):
        if self._series is None:
            base = cineby_movie_url(self.tmdb_id) if self.is_movie else cineby_tv_url(self.tmdb_id)
            self._series = CinebySeries(base)
        return self._series

    @property
    def season(self):
        return self._season

    # ---- selection ----------------------------------------------------------
    @property
    def selected_path(self):
        if self.__selected_path is None:
            raw = self.__selected_path_param or os.getenv(
                "ANIWORLD_DOWNLOAD_PATH", str(Path.home() / "Downloads")
            )
            path = Path(raw).expanduser()
            if not path.is_absolute():
                path = Path.home() / path
            self.__selected_path = str(path)
        return self.__selected_path

    @selected_path.setter
    def selected_path(self, value):
        self.__selected_path_param = value
        self.__selected_path = None
        self.__base_folder = self.__folder_path = self.__episode_path = None

    @property
    def selected_language(self):
        # cineby streams carry the original (mostly English) audio.
        return "English Dub"

    @selected_language.setter
    def selected_language(self, value):
        pass  # single language; ignore

    @property
    def selected_provider(self):
        return "Cineby"

    @selected_provider.setter
    def selected_provider(self, value):
        pass

    def provider_attempt_order(self):
        return ("Cineby",)

    # ---- provider surface (single implicit provider) ------------------------
    @property
    def provider_data(self):
        return {(Audio.ENGLISH, Subtitles.NONE): {"Cineby": self.url}}

    def provider_link(self, language=None, provider=None):
        return self.url

    def available_providers(self, language=None):
        return ("Cineby",)

    @property
    def stream_url(self):
        if self.__stream_url is None:
            from ...playwright.captcha import playwright_get_cineby_stream_url

            m3u8 = playwright_get_cineby_stream_url(self.url)
            if not m3u8:
                raise RuntimeError(
                    f"cineby: could not capture a stream for {self.url}. "
                    "The player resolves client-side and needs the headless "
                    "browser (patchright + chromium)."
                )
            self.__stream_url = m3u8
        return self.__stream_url

    # ---- filesystem ---------------------------------------------------------
    @property
    def _movie_basename(self):
        year = self.release_year
        base = self.title_cleaned or "Movie"
        return f"{base} ({year})" if year else base

    @property
    def _base_folder(self):
        if self.__base_folder is None:
            if self.is_movie and not movie_folder_enabled():
                self.__base_folder = Path(self.selected_path)
            elif self.is_movie:
                self.__base_folder = Path(self.selected_path) / self._movie_basename
            else:
                self.__base_folder = Path(self.selected_path) / self.series.title_cleaned
        return self.__base_folder

    @property
    def _folder_path(self):
        if self.__folder_path is None:
            if self.is_movie:
                self.__folder_path = self._base_folder
            else:
                self.__folder_path = self._base_folder / f"Season {self.season_number:02d}"
        return self.__folder_path

    @property
    def _file_name(self):
        if self.__file_name is None:
            if self.is_movie:
                self.__file_name = self._movie_basename
            else:
                self.__file_name = (
                    f"{self.series.title_cleaned} "
                    f"S{self.season_number:02d}E{self.episode_number:02d}"
                )
        return self.__file_name

    @property
    def _file_extension(self):
        if self.__file_extension is None:
            from ...config import NAMING_TEMPLATE

            template = os.getenv("ANIWORLD_NAMING_TEMPLATE", NAMING_TEMPLATE)
            tail = template.rstrip('"').split("/")[-1]
            self.__file_extension = (
                tail.rsplit(".", 1)[-1] if "." in tail else "mkv"
            ) or "mkv"
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

    download = episode_download
    watch = episode_watch
    syncplay = episode_syncplay


class CinebySeason:
    def __init__(self, url, series=None, season_number=None, are_movies=None, tmdb_id=None):
        self.url = url
        self._series = series
        media_type, url_tmdb, _, _ = parse_cineby_url(url)
        self.tmdb_id = tmdb_id or url_tmdb
        self.are_movies = are_movies if are_movies is not None else (media_type == "movie")
        if season_number is None:
            qs = parse_qs(urlparse(url).query)
            s = qs.get("s", [None])[0]
            season_number = int(s) if s and s.isdigit() else 1
        self.season_number = season_number
        self.__episodes = None

    @property
    def series(self):
        if self._series is None:
            self._series = CinebySeries(self.url)
        return self._series

    @property
    def episodes(self):
        if self.__episodes is None:
            if self.are_movies:
                self.__episodes = [
                    CinebyEpisode(
                        cineby_movie_url(self.tmdb_id),
                        season=self,
                        series=self._series,
                        episode_number=1,
                    )
                ]
            else:
                data = tmdb_get(f"/tv/{self.tmdb_id}/season/{self.season_number}")
                episodes = []
                for ep in data.get("episodes", []):
                    n = ep.get("episode_number")
                    if not n:
                        continue
                    episodes.append(
                        CinebyEpisode(
                            cineby_episode_url(self.tmdb_id, self.season_number, n),
                            season=self,
                            series=self._series,
                            episode_number=n,
                            season_number=self.season_number,
                        )
                    )
                self.__episodes = episodes
        return self.__episodes

    @property
    def episode_count(self):
        return len(self.episodes)

    @property
    def language_labels(self):
        return ["English Dub"]

    def download(self):
        for episode in self.episodes:
            episode.download()

    def watch(self):
        for episode in self.episodes:
            episode.watch()

    def syncplay(self):
        for episode in self.episodes:
            episode.syncplay()


class CinebySeries:
    def __init__(self, url):
        self.url = url
        media_type, tmdb_id, _, _ = parse_cineby_url(url)
        self.media_type = media_type or "movie"
        self.tmdb_id = tmdb_id
        self.is_movie = self.media_type == "movie"
        self.__meta = None
        self.__seasons = None

    @property
    def _meta(self):
        if self.__meta is None:
            if self.is_movie:
                self.__meta = tmdb_get(f"/movie/{self.tmdb_id}") or {}
            else:
                self.__meta = tmdb_get(f"/tv/{self.tmdb_id}") or {}
        return self.__meta

    @property
    def title(self):
        m = self._meta
        return m.get("title") or m.get("name") or f"cineby-{self.tmdb_id}"

    @property
    def title_cleaned(self):
        return clean_title(self.title)

    @property
    def release_year(self):
        m = self._meta
        return _year(m.get("release_date") or m.get("first_air_date"))

    @property
    def poster_url(self):
        return _poster(self._meta.get("poster_path"))

    @property
    def description(self):
        return self._meta.get("overview", "")

    @property
    def genres(self):
        return [g.get("name") for g in self._meta.get("genres", []) if g.get("name")]

    @property
    def seasons(self):
        if self.__seasons is None:
            if self.is_movie:
                self.__seasons = [
                    CinebySeason(
                        self.url,
                        series=self,
                        season_number=1,
                        are_movies=True,
                        tmdb_id=self.tmdb_id,
                    )
                ]
            else:
                seasons = []
                for s in self._meta.get("seasons", []):
                    n = s.get("season_number")
                    if n is None or (n == 0 and not s.get("episode_count")):
                        continue
                    seasons.append(
                        CinebySeason(
                            cineby_season_url("tv", self.tmdb_id, n),
                            series=self,
                            season_number=n,
                            tmdb_id=self.tmdb_id,
                        )
                    )
                self.__seasons = seasons or [
                    CinebySeason(
                        cineby_season_url("tv", self.tmdb_id, 1),
                        series=self,
                        season_number=1,
                        tmdb_id=self.tmdb_id,
                    )
                ]
        return self.__seasons

    def download(self):
        for season in self.seasons:
            season.download()
