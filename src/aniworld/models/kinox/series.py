"""kinox.to models (movies + series).

Mirrors the resolution strategy of the PlexDownloader kinox scraper but fits
it into the AniWorld model surface (series -> seasons -> episodes, each episode
exposing provider_data / redirect_url / provider_url / stream_url and the
shared download/watch/syncplay actions).
"""

import html as html_lib
import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from ...config import (
        Audio,
        Subtitles,
        build_provider_attempt_order,
    )
    from ...extractors import provider_functions
    from ..common import check_downloaded, movie_folder_enabled, run_each
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
    )
    from aniworld.extractors import provider_functions
    from aniworld.models.common import (
        check_downloaded,
        movie_folder_enabled,
        run_each,
    )
    from aniworld.models.common.common import clean_title
    from aniworld.models.common.common import download as episode_download
    from aniworld.models.common.common import syncplay as episode_syncplay
    from aniworld.models.common.common import watch as episode_watch
    from aniworld.models.common.http import get_html, get_session
    from aniworld.models.common.provider_map import host_to_provider

KINOX_DOMAIN = os.getenv("ANIWORLD_KINOX_DOMAIN", "kinox.to")

# Stable marker embedded in the error message when kinox's captcha blocks a
# download, so the web queue can recognise it and offer a "solve on kinox"
# button (only for kinox — no other site uses this).
KINOX_CAPTCHA_MARKER = "[kinox-captcha]"


def _base():
    return f"https://{KINOX_DOMAIN}"


def kinox_slug_from_url(url):
    m = re.search(r"/Stream/([^/.?#]+)(?:\.html)?", url)
    return m.group(1) if m else None


def kinox_captcha_page_url(url):
    """The kinox page a user should open to solve the verification captcha."""
    slug = kinox_slug_from_url(url)
    return f"{_base()}/Stream/{slug}.html" if slug else _base()


def kinox_episode_url(slug, season, episode):
    """Build the per-episode URL that carries S/E through the download queue."""
    return f"{_base()}/Stream/{slug}.html?s={season}&e={episode}"


def _parse_se(url):
    """Return (season, episode) from an episode URL query, or (None, None)."""
    qs = parse_qs(urlparse(url).query)
    season = qs.get("s", [None])[0]
    episode = qs.get("e", [None])[0]
    return (
        int(season) if season and season.isdigit() else None,
        int(episode) if episode and episode.isdigit() else None,
    )


def _detect_language(html, url, title=""):
    m = re.search(
        r'class="[^"]*Flag"[^>]*>\s*<img[^>]*src="/gr/sys/lng/(\d+)\.png"',
        html,
        re.IGNORECASE,
    )
    if m and m.group(1) == "2":
        return "English Dub"
    if "-english" in url.lower() or "english" in (title or "").lower():
        return "English Dub"
    return "German Dub"


def _parse_mirrors(html):
    """Return [(provider_key, rel), …] from a KinoX mirror listing."""
    mirrors = []
    for m in re.finditer(
        r'<li[^>]*class="[^"]*MirBtn[^"]*"[^>]*rel="([^"]+)"[^>]*>.*?<div class="Named">([^<]+)</div>',
        html,
        re.DOTALL | re.IGNORECASE,
    ):
        rel = html_lib.unescape(m.group(1).strip())
        provider = host_to_provider(m.group(2))
        if provider:
            mirrors.append((provider, rel))
    return mirrors


def _stayed_on_kinox(url):
    return KINOX_DOMAIN.split(".")[0] in urlparse(url).netloc.lower()


def _resolve_embed(rel, referer):
    """Turn a mirror rel handle into the hoster embed URL.

    The mirror API returns a ``/redirect/<hash>`` URL. For a plain hoster that
    page 302s straight to the embed. kinox also guards some redirects with a JS
    "Verifizierung" wall that only reveals the hoster iframe after JavaScript
    runs, so when a direct follow stays on kinox we fall back to the headless
    browser (the same approach burning-series uses for its client-side player).
    """
    api_url = f"{_base()}/aGET/Mirror/{rel}"
    raw = get_html(api_url, headers={"Referer": referer}, check_captcha=False)
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise RuntimeError(f"kinox: mirror API returned invalid JSON: {exc}") from exc

    iframe = data.get("Stream", "")
    m = re.search(r'src="(/redirect/[^"\s]+)"', iframe) or re.search(
        r'src="(https?://[^"\s]+)"', iframe
    )
    if not m:
        raise RuntimeError("kinox: no stream iframe in mirror response")

    target = m.group(1)
    if target.startswith("/"):
        target = _base() + target

    # A plain hoster 302s straight to the embed. Force gzip/deflate so the body
    # is decodable (kinox/Cloudflare serve Brotli, which niquests can't decode
    # without the optional package) instead of undecodable bytes. Do NOT
    # raise_for_status here: kinox's bot-check answers the redirect with a 403
    # (or a 200 "Verifizierung" page), and both mean "captcha required".
    resp = get_session().get(
        target,
        headers={"Referer": referer, "Accept-Encoding": "gzip, deflate"},
        allow_redirects=True,
    )
    final = str(resp.url)
    if resp.status_code < 400 and not _stayed_on_kinox(final):
        return final

    # Blocked: a 403/429/503, or a redirect that stayed on kinox serving the JS
    # "Verifizierung" bot-check. Every visitor gets it and it never resolves
    # without a real browser solving it once, so fail with a marker the web UI
    # turns into a "solve the captcha on kinox, then retry" button.
    body = ""
    try:
        body = resp.text[:4000].lower()
    except Exception:
        pass
    if (
        resp.status_code in (403, 429, 503)
        or _stayed_on_kinox(final)
        or "verifizierung" in body
    ):
        raise RuntimeError(
            "kinox: verification captcha required — open the title on kinox, "
            f"solve the captcha there, then retry the download {KINOX_CAPTCHA_MARKER}"
        )
    raise RuntimeError(f"kinox: redirect failed (status {resp.status_code}, {final})")


class _KinoxLanguageMixin:
    def _normalize_language(self, language):
        text = str(language or "").strip().lower()
        if text in {"english", "englisch", "english dub", "english sub"}:
            return "English Dub"
        return "German Dub"


class KinoxEpisode(_KinoxLanguageMixin):
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
        is_movie=None,
    ):
        self.url = url
        self._series = series
        self._season = season

        # Season / episode ride along in the URL query so an episode survives
        # the download-queue round-trip (which only keeps the URL string).
        url_season, url_episode = _parse_se(url)
        self.__episode_number = episode_number or url_episode
        self.__season_number = season_number or url_season
        if is_movie is None:
            is_movie = url_episode is None
        self.is_movie = is_movie

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

    # ---- identity -----------------------------------------------------------
    @property
    def series(self):
        if self._series is None:
            self._series = KinoxSeries(self.url)
        return self._series

    @property
    def season(self):
        return self._season

    @property
    def episode_number(self):
        return self.__episode_number or 1

    @property
    def season_number(self):
        if self.__season_number is not None:
            return self.__season_number
        if self._season is not None:
            return self._season.season_number
        return 1

    @property
    def title_de(self):
        return "" if self.is_movie else f"Episode {self.episode_number}"

    @property
    def title_en(self):
        return ""

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
        if self.__selected_language is None:
            self.__selected_language = self._normalize_language(
                self.__selected_language_param
                or os.getenv("ANIWORLD_LANGUAGE", "German Dub")
            )
        return self.__selected_language

    @selected_language.setter
    def selected_language(self, value):
        self.__selected_language_param = value
        self.__selected_language = None
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

    # ---- provider resolution ------------------------------------------------
    @property
    def provider_data(self):
        if self.__provider_data is None:
            self.__provider_data = self.__extract_provider_data()
        return self.__provider_data

    def __extract_provider_data(self):
        slug = kinox_slug_from_url(self.url)
        html = get_html(f"{_base()}/Stream/{slug}.html")

        if self.is_movie:
            mirrors = _parse_mirrors(html)
            language = _detect_language(html, self.url)
        else:
            m_id = re.search(r'id="EntryID"[^>]*value="(\d+)"', html, re.IGNORECASE)
            series_id = m_id.group(1) if m_id else None
            if not series_id:
                raise RuntimeError("kinox: could not read SeriesID")
            mir_url = (
                f"{_base()}/aGET/MirrorByEpisode/?Addr={slug}"
                f"&SeriesID={series_id}&Season={self.season_number}"
                f"&Episode={self.episode_number}"
            )
            mirror_html = get_html(mir_url)
            mirrors = _parse_mirrors(mirror_html)
            language = _detect_language(html, self.url)

        providers = {}
        for provider, rel in mirrors:
            providers.setdefault(provider, rel)

        if not providers:
            return {}

        audio = Audio.ENGLISH if language == "English Dub" else Audio.GERMAN
        return {(audio, Subtitles.NONE): providers}

    def _provider_bucket(self):
        data = self.provider_data or {}
        audio = (
            Audio.ENGLISH if self.selected_language == "English Dub" else Audio.GERMAN
        )
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
            rel = self.provider_link(self.selected_language, self.selected_provider)
            if not rel:
                raise ValueError(
                    f"Provider '{self.selected_provider}' unavailable for {self.url}"
                )
            self.__redirect_url = rel
        return self.__redirect_url

    @property
    def provider_url(self):
        if self.__provider_url is None:
            self.__provider_url = _resolve_embed(self.redirect_url, self.url)
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

    # ---- filesystem ---------------------------------------------------------
    @property
    def _movie_basename(self):
        year = getattr(self.series, "release_year", "") or ""
        base = self.series.title_cleaned or "Movie"
        return f"{base} ({year})" if year else base

    @property
    def _base_folder(self):
        if self.__base_folder is None:
            if self.is_movie and not movie_folder_enabled():
                self.__base_folder = Path(self.selected_path)
            elif self.is_movie:
                self.__base_folder = Path(self.selected_path) / self._movie_basename
            else:
                self.__base_folder = (
                    Path(self.selected_path) / self.series.title_cleaned
                )
        return self.__base_folder

    @property
    def _folder_path(self):
        if self.__folder_path is None:
            if self.is_movie:
                self.__folder_path = self._base_folder
            else:
                self.__folder_path = (
                    self._base_folder / f"Season {self.season_number:02d}"
                )
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


def kinox_season_url(slug, season):
    """Season URL carrying its number so api/episodes can tell seasons apart."""
    return f"{_base()}/Stream/{slug}.html?s={season}"


class KinoxSeason(_KinoxLanguageMixin):
    def __init__(self, url, series=None, season_number=None, are_movies=None):
        self.url = url
        self._series = series
        url_season, _ = _parse_se(url)
        self.season_number = season_number or url_season or 1
        # A movie has no season selector on its page; detect lazily unless told.
        self._are_movies = are_movies
        self.__episodes = None

    @property
    def are_movies(self):
        if self._are_movies is None:
            self._are_movies = self.series.is_movie
        return self._are_movies

    @property
    def series(self):
        if self._series is None:
            self._series = KinoxSeries(self.url)
        return self._series

    @property
    def episodes(self):
        if self.__episodes is None:
            self.__episodes = self.__build_episodes()
        return self.__episodes

    @property
    def episode_count(self):
        return len(self.episodes)

    def __build_episodes(self):
        if self.are_movies:
            return [
                KinoxEpisode(
                    self.url,
                    season=self,
                    series=self.series,
                    episode_number=1,
                    is_movie=True,
                )
            ]
        numbers = self.series.episode_numbers(self.season_number)
        slug = kinox_slug_from_url(self.url)
        return [
            KinoxEpisode(
                kinox_episode_url(slug, self.season_number, n),
                season=self,
                series=self.series,
                episode_number=n,
                season_number=self.season_number,
                is_movie=False,
            )
            for n in numbers
        ]

    def download(self):
        # One failed episode must not abandon the rest of the batch.
        run_each(self.episodes, "download")

    def watch(self):
        # One failed episode must not abandon the rest of the batch.
        run_each(self.episodes, "watch")

    def syncplay(self):
        # One failed episode must not abandon the rest of the batch.
        run_each(self.episodes, "syncplay")


class KinoxSeries:
    def __init__(self, url):
        self.url = url
        self.__html = None
        self.__title = None
        self.__poster_url = None
        self.__release_year = None
        self.__seasons = None
        self.__is_movie = None

    @property
    def slug(self):
        return kinox_slug_from_url(self.url)

    @property
    def _html(self):
        if self.__html is None:
            self.__html = get_html(f"{_base()}/Stream/{self.slug}.html")
        return self.__html

    @property
    def title(self):
        if self.__title is None:
            m = re.search(
                r'<meta property="og:title" content="([^"]+)"',
                self._html,
                re.IGNORECASE,
            )
            title = m.group(1) if m else (self.slug or "").replace("_", " ")
            # The og:title meta content arrives HTML escaped.
            title = html_lib.unescape(title)
            # og:title reads "Title (Year) Stream online anschauen …" — trim it.
            title = re.split(r"\bStream\b", title, flags=re.IGNORECASE)[0]
            title = re.sub(r"\s*\(\d{4}\)\s*$", "", title).strip()
            self.__title = title or self.slug
        return self.__title

    @property
    def title_cleaned(self):
        return clean_title(self.title)

    @property
    def release_year(self):
        if self.__release_year is None:
            m = re.search(
                r'class="Year"[^>]*>\s*\(?(\d{4})\)?', self._html, re.IGNORECASE
            )
            if not m:
                m = re.search(
                    r'<meta property="og:title" content="[^"]*\((\d{4})\)',
                    self._html,
                    re.IGNORECASE,
                )
            self.__release_year = m.group(1) if m else ""
        return self.__release_year

    @property
    def poster_url(self):
        if self.__poster_url is None:
            # KinoX serves the cover from /statics/thumbs/…; the container class
            # is the site's own misspelling "Grahpics", which is why the old
            # "Gfx" selector matched nothing and the poster stayed blank.
            m = re.search(
                r'<img[^>]*src="(/statics/[^"]+\.(?:jpg|jpeg|png|webp|gif))"',
                self._html,
                re.IGNORECASE,
            ) or re.search(
                r'class="[^"]*Gra?h?pics[^"]*"[^>]*>\s*(?:<a[^>]*>\s*)?<img[^>]*src="([^"]+)"',
                self._html,
                re.IGNORECASE,
            )
            poster = m.group(1).strip() if m else ""
            if poster.startswith("//"):
                poster = "https:" + poster
            elif poster.startswith("/"):
                poster = _base() + poster
            self.__poster_url = poster
        return self.__poster_url

    @property
    def description(self):
        # Plot text lives in <div class="Descriptore">…</div>.
        m = re.search(
            r'<div class="Descriptore">(.*?)</div>',
            self._html,
            re.DOTALL | re.IGNORECASE,
        )
        if not m:
            return ""
        text = re.sub(r"<[^>]+>", " ", m.group(1))
        return re.sub(r"\s+", " ", html_lib.unescape(text)).strip()

    @property
    def genres(self):
        # <li … title="Genre"><span class="Genre"></span>Science Fiction</li>
        m = re.search(
            r'title="Genre"><span class="Genre"></span>([^<]+)',
            self._html,
            re.IGNORECASE,
        )
        if not m:
            return []
        return [
            g.strip() for g in html_lib.unescape(m.group(1)).split(",") if g.strip()
        ]

    @property
    def language_labels(self):
        """Cheap, page-level language detection (kinox entries are single-lang)."""
        return [_detect_language(self._html, self.url, self.title)]

    def _season_selection(self):
        return re.search(r'id="SeasonSelection".*?</select>', self._html, re.DOTALL)

    @property
    def is_movie(self):
        if self.__is_movie is None:
            self.__is_movie = self._season_selection() is None
        return self.__is_movie

    def episode_numbers(self, season_number):
        sel = self._season_selection()
        if not sel:
            return []
        m = re.search(
            rf'<option\s+value="{season_number}"\s+rel="([^"]+)"',
            sel.group(0),
            re.IGNORECASE,
        )
        if not m:
            return []
        return [int(e) for e in m.group(1).split(",") if e.strip().isdigit()]

    @property
    def seasons(self):
        if self.__seasons is None:
            slug = kinox_slug_from_url(self.url)
            if self.is_movie:
                self.__seasons = [
                    KinoxSeason(self.url, series=self, season_number=1, are_movies=True)
                ]
            else:
                sel = self._season_selection()
                numbers = sorted(
                    {
                        int(m.group(1))
                        for m in re.finditer(r'<option\s+value="(\d+)"', sel.group(0))
                    }
                )
                self.__seasons = [
                    KinoxSeason(kinox_season_url(slug, n), series=self, season_number=n)
                    for n in numbers or [1]
                ]
        return self.__seasons

    def download(self):
        for season in self.seasons:
            season.download()
