"""burning-series models (series only).

Matches the current burning-series.io markup: a series page lists seasons, a
season page carries a ``<table class="episodes">`` and each episode has its own
path plus per-hoster anchors. Selecting a hoster yields a ``window.open`` to a
``/stream/<id>`` redirect that lands on the actual hoster embed. Those redirects
are rate-limited by the site, so they are serialised behind a lock with a short
delay.
"""

import os
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

try:
    from ...config import (
        Audio,
        Subtitles,
        build_provider_attempt_order,
        logger,
    )
    from ...extractors import provider_functions
    from ..common import check_downloaded
    from ..common.common import clean_title
    from ..common.common import download as episode_download
    from ..common.common import syncplay as episode_syncplay
    from ..common.common import watch as episode_watch
    from ..common.http import get_html, get_session
    from ..common.provider_map import host_to_provider
except ImportError:
    from aniworld.config import (
        Audio,
        Subtitles,
        build_provider_attempt_order,
        logger,
    )
    from aniworld.extractors import provider_functions
    from aniworld.models.common import check_downloaded
    from aniworld.models.common.common import clean_title
    from aniworld.models.common.common import download as episode_download
    from aniworld.models.common.common import syncplay as episode_syncplay
    from aniworld.models.common.common import watch as episode_watch
    from aniworld.models.common.http import get_html, get_session
    from aniworld.models.common.provider_map import host_to_provider

_DOMAINS = ["https://burning-series.io", "https://burning-series.net", "https://bs.to"]
_active_idx = 0

# burning-series rate-limits parallel redirect follows, so serialise them.
_REDIRECT_LOCK = threading.Lock()
_REDIRECT_DELAY = 1.5

_BS_HOSTS = ("burning-series.io", "burning-series.net", "bs.to")


def bs_current_base():
    return _DOMAINS[_active_idx]


def bs_get_with_fallback(path, **kwargs):
    """GET a path, rotating through the known domains on failure."""
    global _active_idx
    last_err = None
    for offset in range(len(_DOMAINS)):
        idx = (_active_idx + offset) % len(_DOMAINS)
        try:
            html = get_html(f"{_DOMAINS[idx]}{path}", **kwargs)
            _active_idx = idx
            return html
        except Exception as exc:
            logger.debug(f"burning-series domain {_DOMAINS[idx]} failed: {exc}")
            last_err = exc
    raise last_err or RuntimeError(f"all burning-series domains failed for {path}")


def bs_slug_from_url(url):
    m = re.search(r"/serie/([^/?#]+)", url)
    return m.group(1) if m else None


def _bs_lang(language):
    return "en" if str(language or "").lower().startswith("english") else "de"


def _is_bs_host(url):
    netloc = urlparse(url).netloc.lower()
    return any(netloc.endswith(host) for host in _BS_HOSTS)


def _resolve_hoster_link(hoster_path, referer):
    """Follow a per-episode hoster link to the final hoster embed URL.

    The hoster page carries a ``window.open('…/stream/<id>')`` link. That
    ``/stream/<id>`` page renders the hoster iframe client-side, so a plain HTTP
    follow stays on burning-series. We first try a server-side redirect (fast),
    then fall back to a headless browser that waits for the real hoster iframe.
    """
    base = bs_current_base()
    player_url = hoster_path if hoster_path.startswith("http") else f"{base}/{hoster_path.lstrip('/')}"

    with _REDIRECT_LOCK:
        time.sleep(_REDIRECT_DELAY)
        player_html = get_html(player_url, headers={"Referer": referer})
        m = re.search(r"window\.open\(['\"]([^'\"]+)['\"]", player_html)
        if not m:
            raise RuntimeError("burning-series: no player redirect found")

        stream_url = m.group(1)
        if stream_url.startswith("//"):
            stream_url = "https:" + stream_url
        elif stream_url.startswith("/"):
            stream_url = base + stream_url

        # Fast path: a plain redirect straight to the hoster.
        try:
            resp = get_session().get(
                stream_url, headers={"Referer": player_url}, allow_redirects=True
            )
            resp.raise_for_status()
            final = str(resp.url)
            if not _is_bs_host(final):
                return final
        except Exception as exc:
            logger.debug(f"burning-series direct redirect failed: {exc}")

        # Slow path: the /stream/<id> player renders the embed with JavaScript.
        try:
            from ...playwright.captcha import playwright_get_iframe_url

            embed = playwright_get_iframe_url(stream_url)
            if embed and not _is_bs_host(embed):
                return embed
        except Exception as exc:
            raise RuntimeError(
                "burning-series: could not resolve the hoster embed. The player "
                "renders client-side and needs the headless browser (patchright + "
                f"chromium). Details: {exc}"
            ) from exc

        raise RuntimeError("burning-series: hoster embed not found")


class _BSLanguageMixin:
    def _normalize_language(self, language):
        text = str(language or "").strip().lower()
        if text in {"english", "englisch", "english dub", "english sub"}:
            return "English Dub"
        return "German Dub"


class BurningSeriesEpisode(_BSLanguageMixin):
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
    ):
        self.url = url
        self._series = series
        self._season = season

        # URL path: /serie/<slug>/<season>/<epslug>/<lang>
        parts = urlparse(url).path.strip("/").split("/")
        self.__slug = parts[1] if len(parts) > 1 else bs_slug_from_url(url)
        self.__season_number = season_number or (
            int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
        )
        self.__epslug = parts[3] if len(parts) > 3 else ""
        if episode_number is not None:
            self.__episode_number = episode_number
        else:
            m = re.match(r"(\d+)", self.__epslug)
            self.__episode_number = int(m.group(1)) if m else 1

        self.__selected_path_param = selected_path
        self.__selected_language_param = selected_language
        self.__selected_provider_param = selected_provider

        self.__selected_path = None
        self.__selected_language = None
        self.__selected_provider = None

        self.__provider_data = None
        self.__redirect_url = None
        self.__provider_url = None

        self.__base_folder = None
        self.__folder_path = None
        self.__file_name = None
        self.__file_extension = None
        self.__episode_path = None
        self.__is_downloaded = None

    @property
    def series(self):
        if self._series is None:
            self._series = BurningSeriesSeries(
                f"{bs_current_base()}/serie/{self.__slug}"
            )
        return self._series

    @property
    def season(self):
        return self._season

    @property
    def episode_number(self):
        return self.__episode_number or 1

    @property
    def season_number(self):
        return self.__season_number or 1

    @property
    def title_de(self):
        return f"Episode {self.episode_number}"

    @property
    def title_en(self):
        return ""

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
        if self.__selected_language is None:
            self.__selected_language = self._normalize_language(
                self.__selected_language_param or os.getenv("ANIWORLD_LANGUAGE", "German Dub")
            )
        return self.__selected_language

    @selected_language.setter
    def selected_language(self, value):
        self.__selected_language_param = value
        self.__selected_language = None
        self.__provider_data = None
        self.__redirect_url = self.__provider_url = None
        self.__is_downloaded = None

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
        self.__redirect_url = self.__provider_url = None

    def _episode_page_path(self):
        lang = _bs_lang(self.selected_language)
        return f"/serie/{self.__slug}/{self.__season_number}/{self.__epslug}/{lang}"

    @property
    def provider_data(self):
        if self.__provider_data is None:
            self.__provider_data = self.__extract_provider_data()
        return self.__provider_data

    def __extract_provider_data(self):
        html = bs_get_with_fallback(self._episode_page_path())
        providers = {}
        for href, name in re.findall(
            r'href="([^"]+)"[^>]*title="([^"]+)"><i class="hoster', html
        ):
            provider = host_to_provider(name)
            if provider:
                providers.setdefault(provider, href.strip())

        if not providers:
            return {}

        audio = Audio.ENGLISH if _bs_lang(self.selected_language) == "en" else Audio.GERMAN
        return {(audio, Subtitles.NONE): providers}

    def _provider_bucket(self):
        data = self.provider_data or {}
        audio = Audio.ENGLISH if self.selected_language == "English Dub" else Audio.GERMAN
        return data.get((audio, Subtitles.NONE)) or next(iter(data.values()), {})

    def provider_link(self, language=None, provider=None):
        if provider is None:
            provider = self.selected_provider
        bucket = self._provider_bucket()
        return bucket.get(provider) or bucket.get(str(provider).upper())

    def available_providers(self, language=None):
        return tuple(self._provider_bucket().keys())

    def provider_attempt_order(self):
        return build_provider_attempt_order(
            self.selected_provider, self.available_providers()
        )

    @property
    def redirect_url(self):
        if self.__redirect_url is None:
            path = self.provider_link(self.selected_language, self.selected_provider)
            if not path:
                raise ValueError(
                    f"Provider '{self.selected_provider}' unavailable for {self.url}"
                )
            self.__redirect_url = path
        return self.__redirect_url

    @property
    def provider_url(self):
        if self.__provider_url is None:
            self.__provider_url = _resolve_hoster_link(
                self.redirect_url, f"{bs_current_base()}{self._episode_page_path()}"
            )
        return self.__provider_url

    @property
    def stream_url(self):
        try:
            return provider_functions[
                f"get_direct_link_from_{self.selected_provider.lower()}"
            ](self.provider_url)
        except KeyError:
            raise ValueError(
                f"The provider '{self.selected_provider}' is not yet implemented."
            )

    @property
    def _base_folder(self):
        if self.__base_folder is None:
            self.__base_folder = Path(self.selected_path) / self.series.title_cleaned
        return self.__base_folder

    @property
    def _folder_path(self):
        if self.__folder_path is None:
            self.__folder_path = self._base_folder / f"Season {self.season_number:02d}"
        return self.__folder_path

    @property
    def _file_name(self):
        if self.__file_name is None:
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


class BurningSeriesSeason(_BSLanguageMixin):
    def __init__(self, url, series=None, season_number=None):
        self.url = url
        self._series = series
        if season_number is None:
            # URL path: /serie/<slug>/<season>[/<lang>]
            parts = urlparse(url).path.strip("/").split("/")
            season_number = (
                int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
            )
        self.season_number = season_number
        self.are_movies = False
        self.__episodes = None

    @property
    def series(self):
        if self._series is None:
            slug = bs_slug_from_url(self.url)
            self._series = BurningSeriesSeries(f"{bs_current_base()}/serie/{slug}")
        return self._series

    def _episode_rows(self, lang):
        slug = bs_slug_from_url(self.url) or self.series.slug
        try:
            html = bs_get_with_fallback(f"/serie/{slug}/{self.season_number}/{lang}")
        except Exception:
            return []
        table = re.search(
            r'<table class="episodes">(.*?)</table>', html, re.DOTALL
        )
        if not table:
            return []
        rows = []
        for m in re.finditer(
            r'<td><a href="(serie/[^"]+?/(\d+)/([^"/]+)/[a-z]{2})"', table.group(1)
        ):
            rows.append((m.group(1), int(m.group(2)), m.group(3)))
        return rows

    @property
    def episodes(self):
        if self.__episodes is None:
            slug = bs_slug_from_url(self.url) or self.series.slug
            lang = "de"
            rows = self._episode_rows("de")
            if not rows:
                rows = self._episode_rows("en")
                lang = "en"
            base = bs_current_base()
            episodes = []
            seen = set()
            for path, season_no, epslug in rows:
                m = re.match(r"(\d+)", epslug)
                epnum = int(m.group(1)) if m else len(episodes) + 1
                if epnum in seen:
                    continue
                seen.add(epnum)
                url = f"{base}/serie/{slug}/{self.season_number}/{epslug}/{lang}"
                episodes.append(
                    BurningSeriesEpisode(
                        url,
                        season=self,
                        series=self._series,
                        episode_number=epnum,
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
        """Which dub languages have episodes this season (cheap, cached)."""
        labels = []
        if self._episode_rows("de"):
            labels.append("German Dub")
        if self._episode_rows("en"):
            labels.append("English Dub")
        return labels or ["German Dub"]

    def download(self):
        for episode in self.episodes:
            episode.download()

    def watch(self):
        for episode in self.episodes:
            episode.watch()

    def syncplay(self):
        for episode in self.episodes:
            episode.syncplay()


class BurningSeriesSeries:
    def __init__(self, url):
        self.url = url
        self.__html = None
        self.__title = None
        self.__poster_url = None
        self.__seasons = None

    @property
    def slug(self):
        return bs_slug_from_url(self.url)

    @property
    def _html(self):
        if self.__html is None:
            self.__html = bs_get_with_fallback(f"/serie/{self.slug}")
        return self.__html

    @property
    def title(self):
        if self.__title is None:
            m = re.search(r"<h2[^>]*>(.*?)</h2>", self._html, re.DOTALL | re.IGNORECASE)
            if not m:
                m = re.search(r"<h1[^>]*>(.*?)</h1>", self._html, re.DOTALL | re.IGNORECASE)
            if m:
                title = re.sub(r"<[^>]+>", " ", m.group(1))
                # The heading also carries the season nav ("… Staffel 1"); drop it.
                title = re.split(r"\bStaffel\b", title, flags=re.IGNORECASE)[0]
                title = re.sub(r"\s+", " ", title).strip()
            else:
                title = (self.slug or "").replace("-", " ").title()
            self.__title = title or self.slug
        return self.__title

    @property
    def title_cleaned(self):
        return clean_title(self.title)

    @property
    def release_year(self):
        return ""

    @property
    def description(self):
        return ""

    @property
    def genres(self):
        return []

    @property
    def poster_url(self):
        if self.__poster_url is None:
            # The series cover is served from …/images/cover/<id>.<ext>.
            m = re.search(
                r'<img[^>]*src="([^"]*/cover/[^"]+\.(?:jpg|jpeg|png|webp))"',
                self._html,
                re.IGNORECASE,
            ) or re.search(
                r'<img[^>]*class="[^"]*cover[^"]*"[^>]*src="([^"]+)"',
                self._html,
                re.IGNORECASE,
            )
            poster = m.group(1).strip() if m else ""
            if poster.startswith("//"):
                poster = "https:" + poster
            elif poster.startswith("/"):
                poster = bs_current_base() + poster
            self.__poster_url = poster
        return self.__poster_url

    @property
    def seasons(self):
        if self.__seasons is None:
            numbers = set()
            # Season tabs look like <li class="sN"><a href="serie/slug/N/lang">N</a>
            for m in re.finditer(
                r'href="/?serie/' + re.escape(self.slug) + r'/(\d+)(?:/[a-z]{2})?"',
                self._html,
                re.IGNORECASE,
            ):
                numbers.add(int(m.group(1)))
            self.__seasons = [
                BurningSeriesSeason(
                    f"{bs_current_base()}/serie/{self.slug}/{n}", series=self, season_number=n
                )
                for n in sorted(numbers) or [1]
            ]
        return self.__seasons

    def download(self):
        for season in self.seasons:
            season.download()
