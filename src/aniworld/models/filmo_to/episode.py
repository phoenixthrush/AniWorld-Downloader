import os
import re
from functools import cached_property
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

from ...config import Audio, Subtitles, build_provider_attempt_order
from ...extractors import provider_functions
from ..common import ProviderData, check_downloaded, movie_folder_enabled
from ..common.common import clean_title
from ..common.common import download as episode_download
from ..common.common import syncplay as episode_syncplay
from ..common.common import watch as episode_watch
from ..common.http import CaptchaRequired, get_session, is_captcha_page
from ..common.provider_map import host_to_provider

FILMO_EPISODE_PATTERN = re.compile(
    r"https?://(?:www\.)?filmo\.to/movies/[\w-]+/?(?:\?[^#]*)?(?:#.*)?$"
)
_LANGUAGES = {"Deutsch": "German Dub", "German": "German Dub", "English": "English Dub"}
_AUDIO = {"German Dub": Audio.GERMAN, "English Dub": Audio.ENGLISH}


def _text(html):
    return unescape(re.sub(r"<[^>]*>", "", html)).strip()


class _MoviePage(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.meta = {}
        self.sources = {}
        self.synopsis = []
        self.reading_synopsis = False
        self.language = None
        self.reading_language = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "p" and "movie-detail-synopsis" in attrs.get("class", "").split():
            self.reading_synopsis = True
        if tag == "br" and self.reading_synopsis:
            self.synopsis.append("\n")
        if tag == "meta":
            self.meta[attrs.get("name") or attrs.get("property")] = attrs.get(
                "content", ""
            )
        if "provider-row__lang" in attrs.get("class", "").split():
            self.reading_language = True
            self.language = None
        if "data-provider-chip" in attrs and self.language:
            provider = host_to_provider(attrs.get("aria-label"))
            if provider and attrs.get("data-p"):
                self.sources.setdefault(self.language, {}).setdefault(
                    provider, attrs["data-p"]
                )

    def handle_data(self, data):
        if self.reading_synopsis:
            self.synopsis.append(data)
        if self.reading_language and data.strip():
            self.language = _LANGUAGES.get(data.strip())

    def handle_endtag(self, tag):
        if tag == "p":
            self.reading_synopsis = False
        if tag == "span":
            self.reading_language = False


class FilmoEpisode:
    """A Filmo movie with lazy metadata and language-specific hoster resolution."""

    is_movie = True

    def __init__(
        self,
        url: str,
        selected_path: str | None = None,
        selected_language: str | None = None,
        selected_provider: str | None = None,
    ):
        if not isinstance(url, str) or not FILMO_EPISODE_PATTERN.fullmatch(url):
            raise ValueError(f"Invalid Filmo movie URL: {url}")
        self.url = url
        self.__redirect_url = None
        self.__provider_url = None
        self.selected_path = (
            selected_path
            or os.getenv("ANIWORLD_DOWNLOAD_PATH")
            or str(Path.home() / "Downloads")
        )
        self.selected_language = selected_language or os.getenv(
            "ANIWORLD_LANGUAGE", "German Dub"
        )
        self.selected_provider = selected_provider or os.getenv(
            "ANIWORLD_PROVIDER", "VOE"
        )

    @cached_property
    def _html(self):
        response = get_session().get(
            self.url, headers={"Accept-Encoding": "gzip, deflate"}, timeout=20
        )
        response.raise_for_status()
        if is_captcha_page(response.text, response.status_code):
            raise CaptchaRequired(f"Filmo requires verification: {self.url}")
        return response.text

    @cached_property
    def _page(self):
        return _MoviePage(self._html)

    def _field(self, name):
        match = re.search(
            r"<h3\b[^>]*>\s*" + re.escape(name) + r"\s*</h3>.*?<dd\b[^>]*>(.*?)</dd>",
            self._html,
            re.DOTALL,
        )
        return match.group(1) if match else ""

    def _field_links(self, name):
        links = re.findall(r"<a\b[^>]*>(.*?)</a>", self._field(name), re.DOTALL)
        return [_text(link) for link in links]

    def _clear_resolution(self):
        self.__redirect_url = None
        self.__provider_url = None

    @property
    def title(self):
        match = re.search(r"<h1\b[^>]*>(.*?)</h1>", self._html, re.DOTALL)
        if not match:
            raise ValueError(f"Filmo movie title not found: {self.url}")
        return _text(match.group(1))

    @property
    def title_de(self):
        return self.title

    @property
    def title_en(self):
        return self.title

    @property
    def title_cleaned(self):
        return clean_title(self.title)

    @property
    def description(self):
        synopsis = "".join(self._page.synopsis).strip()
        return synopsis or self._page.meta.get("og:description", "")

    @property
    def release_year(self):
        match = re.search(r"\b(\d{4})\b", _text(self._field("Release date")))
        return int(match.group(1)) if match else None

    @property
    def runtime_min(self):
        match = re.search(r"\d+", _text(self._field("Runtime")))
        return int(match.group()) if match else None

    @property
    def genres(self):
        return self._field_links("Genres")

    @property
    def director(self):
        return _text(self._field("Directors"))

    @property
    def actors(self):
        return self._field_links("Cast")

    @property
    def imdb_rating(self):
        match = re.search(r"IMDb\s+([\d.]+)/10", self._html)
        return float(match.group(1)) if match else None

    @property
    def poster_url(self):
        image = self._page.meta.get("og:image")
        return urljoin(self.url, image) if image else None

    image_url = poster_url

    @property
    def selected_language(self):
        return self._language

    @selected_language.setter
    def selected_language(self, value):
        if value not in _AUDIO:
            raise ValueError(f"Unsupported Filmo language: {value}")
        self._language = value
        self._clear_resolution()

    @property
    def selected_provider(self):
        return self._provider

    @selected_provider.setter
    def selected_provider(self, value):
        self._provider = value
        self._clear_resolution()

    @property
    def provider_data(self):
        return ProviderData(
            {
                (_AUDIO[language], Subtitles.NONE): dict(sources)
                for language, sources in self._page.sources.items()
            }
        )

    def available_providers(self, language=None):
        return tuple(self._page.sources.get(language or self.selected_language, {}))

    def provider_attempt_order(self):
        return build_provider_attempt_order(
            self.selected_provider, self.available_providers()
        )

    @property
    def redirect_url(self):
        if self.__redirect_url is None:
            sources = self._page.sources.get(self.selected_language, {})
            source_token = sources.get(self.selected_provider)
            if not source_token:
                raise ValueError(
                    f"Filmo source unavailable: {self.selected_language} / {self.selected_provider}"
                )
            csrf = self._page.meta.get("csrf-token")
            if not csrf:
                raise ValueError("Filmo page is missing its CSRF token")
            endpoint = urljoin(self.url, "/n")
            response = get_session().post(
                endpoint,
                json={"p": source_token},
                headers={
                    "X-CSRF-TOKEN": csrf,
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": self.url,
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip, deflate",
                },
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            playback_token = payload.get("x") if isinstance(payload, dict) else None
            if not isinstance(playback_token, str) or not playback_token:
                raise ValueError("Filmo did not return a playback token")
            self.__redirect_url = f"{endpoint}/{quote(playback_token, safe='')}"
        return self.__redirect_url

    @property
    def provider_url(self):
        if self.__provider_url is None:
            response = get_session().get(
                self.redirect_url,
                headers={"Referer": self.url, "Accept-Encoding": "gzip, deflate"},
                timeout=20,
            )
            response.raise_for_status()
            target = str(response.url)
            parsed = urlparse(target)
            if (
                parsed.scheme not in ("http", "https")
                or not parsed.hostname
                or parsed.hostname in ("filmo.to", "www.filmo.to")
            ):
                raise ValueError("Filmo did not redirect to a stream provider")
            self.__provider_url = target
        return self.__provider_url

    @property
    def stream_url(self):
        extractor = provider_functions.get(
            f"get_direct_link_from_{self.selected_provider.lower()}"
        )
        if extractor is None:
            raise ValueError(f"Unsupported Filmo provider: {self.selected_provider}")
        result = extractor(self.provider_url)
        if not result:
            raise ValueError("Filmo provider returned no stream URL")
        return result

    @property
    def _file_name(self):
        title = self.title_cleaned
        year = self.release_year
        return f"{title} ({year})" if year else title

    @property
    def _base_folder(self):
        path = Path(self.selected_path).expanduser()
        if not path.is_absolute():
            path = Path.home() / path
        return path / self._file_name if movie_folder_enabled() else path

    @property
    def _folder_path(self):
        return self._base_folder

    @property
    def _file_extension(self):
        return (
            Path(os.getenv("ANIWORLD_NAMING_TEMPLATE", "movie.mkv")).suffix.lstrip(".")
            or "mkv"
        )

    @property
    def _episode_path(self):
        return self._folder_path / f"{self._file_name}.{self._file_extension}"

    @property
    def is_downloaded(self):
        return check_downloaded(self._episode_path)

    download = episode_download
    watch = episode_watch
    syncplay = episode_syncplay
