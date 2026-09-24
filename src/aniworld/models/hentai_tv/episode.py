import json
import os
import re
from html import unescape
from pathlib import Path
from urllib.parse import urljoin

from niquests.exceptions import HTTPError

from ...config import (
    DEFAULT_USER_AGENT,
    GLOBAL_SESSION,
    HENTAI_TV_EPISODE_PATTERN,
    NAMING_TEMPLATE,
    Audio,
    Subtitles,
)
from ..common import ProviderData, check_downloaded, clean_title
from ..common.common import _download_direct_http
from ..common.common import syncplay as episode_syncplay
from ..common.common import watch as episode_watch
from .player import resolve_stream_url


class HentaiTVEpisode:
    """A standalone hentai.tv episode with lazy metadata and player resolution."""

    is_movie = False
    season_number = 1

    def __init__(
        self, url, selected_path=None, selected_language=None, selected_provider=None
    ):
        if not self._is_valid_url(url):
            raise ValueError(f"Invalid hentai.tv URL: {url}")
        self.url = url
        self.__selected_path_param = selected_path
        # Hentai.tv has no language selection, so English Sub is hardcoded.
        self.__selected_language = selected_language or "English Sub"
        self.__selected_provider = selected_provider or "HentaiTV"
        self.__html = None
        self.__player_html = None
        self.__metadata = None
        self.__stream_url = None

    @staticmethod
    def _is_valid_url(url):
        return isinstance(url, str) and bool(HENTAI_TV_EPISODE_PATTERN.fullmatch(url))

    @staticmethod
    def _slug_from_url(url):
        return url.rstrip("/").split("/")[-1]

    @property
    def _html(self):
        if self.__html is None:
            response = GLOBAL_SESSION.get(
                self.url,
                headers={
                    "User-Agent": DEFAULT_USER_AGENT,
                    "Accept-Encoding": "gzip, deflate",
                },
                timeout=20,
            )
            response.raise_for_status()
            self.__html = response.text
        return self.__html

    @property
    def _metadata(self):
        if self.__metadata is None:
            self.__metadata = {}
            scripts = re.findall(
                r"<script\b[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
                self._html,
                re.IGNORECASE | re.DOTALL,
            )
            for raw in scripts:
                try:
                    value = json.loads(unescape(raw.strip()))
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(value, dict):
                    self.__metadata = value
                    break
            if not self.__metadata:
                match = re.search(
                    r'"description":(?P<description>"(?:\\.|[^"\\])*")'
                    r',"thumbnailUrl":(?P<thumbnail>\[.*?\])'
                    r',"uploadDate":(?P<date>"[^"]+")'
                    r'.*?"embedUrl":(?P<embed>"[^"]+")'
                    r'.*?"genre":(?P<genre>\[.*?\])',
                    self._html,
                    re.IGNORECASE | re.DOTALL,
                )
                if match:
                    self.__metadata = {
                        "description": json.loads(match.group("description")),
                        "thumbnailUrl": json.loads(match.group("thumbnail")),
                        "uploadDate": json.loads(match.group("date")),
                        "embedUrl": json.loads(match.group("embed")),
                        "genre": json.loads(match.group("genre")),
                    }
        return self.__metadata

    def _meta(self, key):
        match = re.search(
            rf'<meta\b[^>]*(?:property|name)=["\']{re.escape(key)}["\'][^>]*>',
            self._html,
            re.IGNORECASE,
        )
        if not match:
            return ""
        content = re.search(r'content=["\'](.*?)["\']', match.group(0), re.IGNORECASE)
        return unescape(content.group(1)) if content else ""

    @property
    def title_en(self):
        title = self._metadata.get("name") or self._meta("og:title")
        title = re.sub(r"^Watch\s+|\s+Online at Hentai\.tv.*$", "", title or "")
        return (
            unescape(title.strip())
            or self._slug_from_url(self.url).replace("-", " ").title()
        )

    @property
    def title(self):
        return self.title_en

    @property
    def title_de(self):
        return ""

    @property
    def title_cleaned(self):
        return clean_title(self.title)

    @property
    def release_year(self):
        return self.release_date[:4]

    @property
    def episode_number(self):
        match = re.search(
            r"(?:episode|ep)[- ]?(\d+)$", self._slug_from_url(self.url), re.IGNORECASE
        )
        return int(match.group(1)) if match else 1

    @property
    def series_title(self):
        return (
            re.sub(
                r"(?:-episode|-ep)-?\d+$",
                "",
                self._slug_from_url(self.url),
                flags=re.IGNORECASE,
            )
            .replace("-", " ")
            .strip()
            .title()
        )

    @property
    def description(self):
        match = re.search(
            r'<p\b[^>]*class=["\'][^"\']*watch-desc[^"\']*["\'][^>]*>(.*?)</p>',
            self._html,
            re.IGNORECASE | re.DOTALL,
        )
        if match:
            return unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip()
        return unescape(
            self._metadata.get("description") or self._meta("og:description")
        ).strip()

    @property
    def poster_url(self):
        image = self._metadata.get("thumbnailUrl") or self._meta("og:image") or ""
        if isinstance(image, list):
            image = image[0] if image else ""
        return urljoin(self.url, image) if image else ""

    @property
    def release_date(self):
        return self._metadata.get("uploadDate", "")

    @property
    def genres(self):
        genres = self._metadata.get("genre") or []
        return [genres] if isinstance(genres, str) else genres

    @property
    def redirect_url(self):
        return self.url

    @property
    def provider_url(self):
        embed_url = self._metadata.get("embedUrl")
        if not embed_url:
            raise RuntimeError("Could not find the hentai.tv player embed")
        return urljoin(self.url, embed_url)

    @property
    def _player_url(self):
        if self.__player_html is None:
            response = GLOBAL_SESSION.get(
                self.provider_url,
                headers={"Accept-Encoding": "gzip, deflate"},
                timeout=20,
            )
            response.raise_for_status()
            self.__player_html = response.text
        match = re.search(
            r'data-id=["\']([^"\']*player\.php\?[^"\']+)',
            self.__player_html,
            re.IGNORECASE,
        )
        if not match:
            raise RuntimeError("Could not find the hentai.tv player URL")
        return urljoin(self.provider_url, unescape(match.group(1)))

    @property
    def stream_url(self):
        if self.__stream_url is None:
            # The base64 vid parameter is a player input, not a valid CDN token.
            self.__stream_url = resolve_stream_url(self._player_url)
        return self.__stream_url

    def refresh_stream_url(self):
        self.__stream_url = None
        self.__player_html = None
        return self.stream_url

    def provider_link(self, language=None, provider=None):
        language = language or self.selected_language
        provider = provider or self.selected_provider
        if language not in ("English Sub", (Audio.JAPANESE, Subtitles.ENGLISH)):
            return None
        return self.url if provider == "HentaiTV" else None

    def available_providers(self, language=None):
        return ("HentaiTV",) if self.provider_link(language, "HentaiTV") else ()

    def provider_attempt_order(self):
        return self.available_providers()

    @property
    def provider_data(self):
        return ProviderData(
            {(Audio.JAPANESE, Subtitles.ENGLISH): {"HentaiTV": self.url}}
        )

    @property
    def selected_path(self):
        raw_path = self.__selected_path_param or os.getenv(
            "ANIWORLD_DOWNLOAD_PATH", str(Path.home() / "Downloads")
        )
        path = Path(raw_path).expanduser()
        return str(path if path.is_absolute() else Path.home() / path)

    @selected_path.setter
    def selected_path(self, value):
        self.__selected_path_param = value

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

    @property
    def _naming_parts(self):
        return os.getenv("ANIWORLD_NAMING_TEMPLATE", NAMING_TEMPLATE).split("/")

    def _format_naming_part(self, template):
        values = {
            "title": clean_title(self.series_title),
            "year": self.release_year,
            "imdbid": "",
            "season": f"{self.season_number:02d}",
            "episode": f"{self.episode_number:03d}",
            "language": self.selected_language,
            "resolution": "unknown",
        }
        for key in values:
            template = template.replace(f"%{key}%", "{" + key + "}")
        formatted = template.format(**values)
        return re.sub(r"\s*\[imdbid-\]\s*", "", formatted).strip()

    @property
    def _base_folder(self):
        path = Path(self.selected_path)
        if len(self._naming_parts) > 1:
            path /= self._format_naming_part(self._naming_parts[0])
        return path

    @property
    def _folder_path(self):
        path = self._base_folder
        for part in self._naming_parts[1:-1]:
            path /= self._format_naming_part(part)
        return path

    @property
    def _file_name(self):
        template = self._naming_parts[-1]
        if "." in template:
            template = template.rsplit(".", 1)[0]
        return self._format_naming_part(template)

    @property
    def _file_extension(self):
        template = self._naming_parts[-1]
        return (template.rsplit(".", 1)[-1] or "mkv") if "." in template else "mkv"

    @property
    def _episode_path(self):
        return self._folder_path / f"{self._file_name}.{self._file_extension}"

    @property
    def is_downloaded(self):
        return check_downloaded(self._episode_path)

    def download(self):
        if not self.provider_link():
            raise ValueError("hentai.tv only provides HentaiTV / English Sub")
        self._folder_path.mkdir(parents=True, exist_ok=True)
        if not self.is_downloaded["exists"]:
            try:
                _download_direct_http(
                    self._episode_path, self.stream_url, self._file_name
                )
            except HTTPError as exc:
                if exc.response is None or exc.response.status_code != 403:
                    raise
                # A cached signed URL may have expired since it was inspected.
                _download_direct_http(
                    self._episode_path, self.refresh_stream_url(), self._file_name
                )

    watch = episode_watch
    syncplay = episode_syncplay
