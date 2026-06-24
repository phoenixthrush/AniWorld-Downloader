import os
import platform
import re
import subprocess
import sys
from pathlib import Path

import ffmpeg
import requests

from ...config import NAMING_TEMPLATE, get_video_codec, logger
from ..common import check_downloaded
from ..common.common import _run_ffmpeg_with_progress, format_command_for_shell

HANIME_VIDEO_API = "https://hanime.tv/api/v8/video?id={slug}"
_HANIME_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


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
                (self._series._api_data.get("hentai_franchise_hentai_videos") or [])
                my_slug = self._slug_from_url(self.url)
                series_slug = self._slug_from_url(self._series.url)
                if my_slug == series_slug:
                    self.__api_data = self._series._api_data
                    return self.__api_data

            slug = self._slug_from_url(self.url)
            api_url = HANIME_VIDEO_API.format(slug=slug)
            logger.debug(f"fetching hanime API ({api_url})...")
            resp = requests.get(api_url, headers=_HANIME_HEADERS, timeout=15)
            resp.raise_for_status()
            self.__api_data = resp.json()
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

            franchise_videos = (
                self._api_data.get("hentai_franchise_hentai_videos") or []
            )
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
            self.__stream_url = self._extract_stream_url()
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
                    imdbid="",
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
                    imdbid="",
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
                file_template = "{title} S{season}E{episode}.mkv"

            if "." in file_template:
                file_template = ".".join(file_template.split(".")[:-1])

            file_template = file_template.replace("%title%", "{title}")
            file_template = file_template.replace("%year%", "{year}")
            file_template = file_template.replace("%imdbid%", "{imdbid}")
            file_template = file_template.replace("%season%", "{season}")
            file_template = file_template.replace("%episode%", "{episode}")
            file_template = file_template.replace("%language%", "{language}")

            self.__file_name = file_template.format(
                title=self.series.title_cleaned,
                year=self.series.release_year,
                imdbid="",
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

    @property
    def is_downloaded(self):
        if self.__is_downloaded is None:
            self.__is_downloaded = check_downloaded(self._episode_path)
        return self.__is_downloaded

    # -----------------------------
    # EXTRACTION
    # -----------------------------

    def _extract_stream_url(self):
        manifest = self._api_data.get("videos_manifest") or {}
        servers = manifest.get("servers") or []

        best_url = None
        best_height = 0

        for server in servers:
            for stream in server.get("streams") or []:
                url = stream.get("signed_url") or stream.get("url") or ""
                if not url:
                    continue
                height = int(stream.get("height") or 0)
                if height > best_height:
                    best_height = height
                    best_url = url

        if not best_url:
            raise ValueError(f"No stream URL found for {self.url}")

        return best_url

    def _get_download_url(self):
        dl_url = self._api_data.get("dl_url") or ""
        if not dl_url:
            return None
        if "pixeldrain.com/d/" in dl_url:
            file_id = dl_url.rstrip("/").split("/")[-1]
            return f"https://pixeldrain.com/api/filesystem/{file_id}"
        return dl_url

    # -----------------------------
    # PUBLIC METHODS
    # -----------------------------

    def download(self):
        from ...autodeps import DependencyManager

        if platform.system() == "Windows":
            manager = DependencyManager()
            manager.fetch_binary("ffmpeg")

        if self._episode_path.exists():
            logger.debug(f"[SKIPPED] {self._file_name} (already downloaded)")
            return

        os.makedirs(self._folder_path, exist_ok=True)

        dl_url = self._get_download_url()

        if dl_url:
            self._download_direct(dl_url)
        else:
            self._download_hls(self.stream_url)

    def _download_direct(self, url):
        import time as _time

        from ..common.common import _ffmpeg_progress, _ffmpeg_progress_lock

        temp_file = self._episode_path.with_suffix(".temp_dl.mp4")
        ep_label = os.path.splitext(self._file_name)[0] if self._file_name else ""

        try:
            logger.debug(f"[DOWNLOADING] {ep_label} via direct download")
            resp = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                stream=True,
                timeout=30,
            )
            resp.raise_for_status()

            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            last_ts = _time.monotonic()
            last_bytes = 0

            with _ffmpeg_progress_lock:
                _ffmpeg_progress.update(
                    percent=0.0, time="", speed="", bandwidth="", active=True
                )

            with open(temp_file, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)
                    downloaded += len(chunk)

                    if total:
                        pct = downloaded / total * 100
                        mb = downloaded / 1024 / 1024
                        total_mb = total / 1024 / 1024

                        now = _time.monotonic()
                        dt = now - last_ts
                        bw_str = ""
                        if dt > 0.5:
                            bw = (downloaded - last_bytes) / dt / 1024 / 1024
                            bw_str = f"{bw:.1f} MB/s"
                            last_ts = now
                            last_bytes = downloaded

                        with _ffmpeg_progress_lock:
                            prev_bw = _ffmpeg_progress.get("bandwidth", "")
                            _ffmpeg_progress.update(
                                percent=round(pct, 1),
                                time=f"{mb:.1f}/{total_mb:.1f} MB",
                                speed="",
                                bandwidth=bw_str or prev_bw,
                                active=True,
                            )

                        if sys.stderr.isatty():
                            sys.stderr.write(
                                f"\r{ep_label} - [{int(pct):3d}%] {mb:.1f}/{total_mb:.1f} MB  "
                            )
                            sys.stderr.flush()

            if sys.stderr.isatty():
                sys.stderr.write("\r" + " " * 80 + "\r")
                sys.stderr.flush()

            os.replace(temp_file, self._episode_path)
        except Exception:
            if temp_file.exists():
                temp_file.unlink()
            raise
        finally:
            with _ffmpeg_progress_lock:
                _ffmpeg_progress.update(
                    percent=0.0, time="", speed="", bandwidth="", active=False
                )

    def _download_hls(self, stream_url):
        ep_label = os.path.splitext(self._file_name)[0] if self._file_name else ""
        temp_full = self._episode_path.with_suffix(".temp_full.mkv")

        try:
            logger.debug(f"[DOWNLOADING] {ep_label} via HLS stream")
            video_codec = get_video_codec()

            input_kwargs = {
                "reconnect": 1,
                "reconnect_streamed": 1,
                "reconnect_delay_max": 300,
            }

            _run_ffmpeg_with_progress(
                ffmpeg.input(stream_url, **input_kwargs).output(
                    str(temp_full),
                    vcodec=video_codec,
                    acodec=video_codec,
                    **{"metadata:s:a:0": "language=jpn"},
                ),
                label=ep_label,
            )

            os.replace(temp_full, self._episode_path)
        except Exception:
            if temp_full.exists():
                temp_full.unlink()
            raise

    def watch(self):
        from ...autodeps import get_player_path

        print(f"[WATCHING] {self._file_name}")

        player_path = str(get_player_path())
        stream_url = self.stream_url

        cmd = [player_path, stream_url]
        cmd.extend(
            [
                "--no-ytdl",
                "--fs",
                "--quiet",
                f"--force-media-title={self._file_name}",
            ]
        )

        print(format_command_for_shell(cmd))
        subprocess.run(cmd)

    def syncplay(self):
        import getpass
        import hashlib

        from ...autodeps import get_player_path, get_syncplay_path

        print(f"[Syncplaying] {self._file_name}")

        os.environ["ANIWORLD_USE_IINA"] = "0"

        stream_url = self.stream_url

        syncplay_host = os.getenv("ANIWORLD_SYNCPLAY_HOST") or "syncplay.pl:8998"
        syncplay_password = os.getenv("ANIWORLD_SYNCPLAY_PASSWORD")
        syncplay_username = os.getenv("ANIWORLD_SYNCPLAY_USERNAME")

        if not syncplay_username:
            try:
                syncplay_username = getpass.getuser()
            except Exception:
                syncplay_username = "AniWorld-Downloader"

        room = "AniWorld"
        file_name = self._file_name.replace(" ", "_")

        if syncplay_password:
            room += (
                "-"
                + hashlib.sha256(
                    f"-{file_name}-{syncplay_password}".encode("utf-8")
                ).hexdigest()
            )
        else:
            room += f"-{file_name}"

        syncplay_room = os.getenv("ANIWORLD_SYNCPLAY_ROOM") or room

        cmd = [
            str(get_syncplay_path()),
            "--no-gui",
            "--no-store",
            "--host",
            syncplay_host,
            "--room",
            syncplay_room,
            "--name",
            syncplay_username,
            "--player-path",
            str(get_player_path()),
            stream_url,
            "--",
            "--no-ytdl",
            "--fs",
            "--quiet",
            f"--force-media-title={self._file_name}",
        ]

        print(format_command_for_shell(cmd))
        subprocess.run(cmd)
