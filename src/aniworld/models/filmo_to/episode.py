import os
import re
from html import unescape
from pathlib import Path

try:
    from ...config import (
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
        movie_folder_enabled,
    )
    from aniworld.models.common.common import clean_title
    from aniworld.models.common.common import download as episode_download
    from aniworld.models.common.common import syncplay as episode_syncplay
    from aniworld.models.common.common import watch as episode_watch
    from aniworld.models.common.provider_map import host_to_provider

FILMO_EPISODE_PATTERN = re.compile(
    r"^https?://(?:www\.)?filmo\.to/movies/[a-zA-Z0-9\-]+/?$",
    re.IGNORECASE,
)

_CHIP_LANG_RE = re.compile(r'class="provider-row__lang"[^>]*>\s*([^<]+?)\s*<')
_CHIP_RE = re.compile(r'data-provider-chip[^>]*?aria-label="([^"]+)"[^>]*?data-p="([^"]+)"')
_CHIP_RE_ALT = re.compile(r'data-p="([^"]+)"[^>]*?aria-label="([^"]+)"')


class FilmoEpisode:
    """
    Represents a movie on filmo.to.

    Parameters:
        url:                Required. filmo.to movie URL, e.g.
                            https://filmo.to/movies/spider-man-brand-new-day
        selected_path:      Optional download path.
        selected_language:  Optional language ("German Dub" / "English Dub").
        selected_provider:  Optional provider name ("VOE", "Filemoon", …).

    Provider links are resolved via a two-step API:
      POST /n  {"p": <data-p payload>}  → {"x": "<token>"}
      GET  /n/<token>                   → 302 to embed URL (VOE)
                                          or 200 interstitial page (Byse/Filemoon)
    """

    def __init__(
        self,
        url: str,
        selected_path: str | None = None,
        selected_language: str | None = None,
        selected_provider: str | None = None,
    ):
        if not FILMO_EPISODE_PATTERN.match(url):
            raise ValueError(f"Invalid filmo.to movie URL: {url}")

        self.url = url.rstrip("/")

        self.__title_de = None
        self.__release_year = None
        self.__runtime_min = None
        self.__genres = None
        self.__description = None
        self.__image_url = None
        self.__imdb_rating = None
        self.__age_rating = None

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
        self.__csrf_token = None

        logger.debug(f"Initialized FilmoEpisode({self.url})")

    # ---- HTML + CSRF ----

    @property
    def _html(self):
        if self.__html is None:
            logger.debug(f"fetching ({self.url})...")
            resp = GLOBAL_SESSION.get(
                self.url,
                headers={
                    "Referer": "https://filmo.to/",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate",
                },
            )
            html = resp.text
            # filmo.to may serve a Cloudflare Turnstile challenge; solve it
            # with the browser and retry the plain HTTP request once the
            # cf_clearance cookie is in GLOBAL_SESSION.
            try:
                from ...playwright.captcha import is_captcha_page, solve_captcha
            except ImportError:
                from aniworld.playwright.captcha import is_captcha_page, solve_captcha
            if is_captcha_page(html, resp.status_code):
                logger.warning(
                    f"filmo: Cloudflare challenge on {self.url} — solving..."
                )
                solve_captcha(self.url)
                resp = GLOBAL_SESSION.get(
                    self.url,
                    headers={
                        "Referer": "https://filmo.to/",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept-Encoding": "gzip, deflate",
                    },
                )
                html = resp.text
            self.__html = html
        return self.__html

    @property
    def _csrf_token(self):
        if self.__csrf_token is None:
            self.__csrf_token = self.__extract_csrf()
        return self.__csrf_token

    def __extract_csrf(self):
        html = self._html
        needle = 'name="csrf-token" content="'
        idx = html.find(needle)
        if idx != -1:
            start = idx + len(needle)
            end = html.find('"', start)
            if end != -1:
                return html[start:end]
        return ""

    # ---- metadata properties ----

    @property
    def title_de(self):
        if self.__title_de is None:
            self.__title_de = self.__extract_title()
        return self.__title_de

    @property
    def title(self):
        return self.title_de or ""

    @property
    def title_cleaned(self):
        return clean_title(self.title_de or "")

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
            self.__genres = self.__extract_genres()
        return self.__genres

    @property
    def description(self):
        if self.__description is None:
            self.__description = self.__extract_description()
        return self.__description

    @property
    def image_url(self):
        if self.__image_url is None:
            self.__image_url = self.__extract_image_url()
        return self.__image_url

    @property
    def poster_url(self):
        return self.image_url

    @property
    def imdb_rating(self):
        if self.__imdb_rating is None:
            self.__extract_imdb_rating()
        return self.__imdb_rating

    @property
    def age_rating(self):
        if self.__age_rating is None:
            self.__extract_age_rating()
        return self.__age_rating

    # ---- metadata extractors ----

    def __extract_title(self):
        m = re.search(r'<h1[^>]*>\s*([^<]+?)\s*</h1>', self._html)
        return unescape(m.group(1).strip()) if m else None

    def __extract_description(self):
        m = re.search(
            r'<p[^>]*movie-detail-synopsis[^>]*>\s*(.*?)\s*</p>',
            self._html,
            re.DOTALL,
        )
        return unescape(m.group(1).strip()) if m else None

    def __extract_genres(self):
        # Genres are <a href="/genres/<slug>" ...>Genre Name</a> links.
        # Use dict.fromkeys to preserve order while deduplicating.
        return list(dict.fromkeys(
            unescape(m.group(1).strip())
            for m in re.finditer(
                r'href="https?://filmo\.to/genres/[^"]+"\s+class="[^"]*">\s*([^<]+?)\s*</a>',
                self._html,
            )
        ))

    def __extract_imdb_rating(self):
        m = re.search(r"IMDb\s+([\d.]+)/10", self._html)
        self.__imdb_rating = float(m.group(1)) if m else None

    def __extract_release_year(self):
        m = re.search(r"Release date:\s*(\d{4})", self._html)
        if m:
            self.__release_year = int(m.group(1))
            return
        # Fallback: year appearing shortly after "IMDb" in the meta bar
        m = re.search(r"IMDb.{0,200}\b(19\d\d|20\d\d)\b", self._html, re.DOTALL)
        if m:
            self.__release_year = int(m.group(1))

    def __extract_runtime_min(self):
        # Prefer "X h Y min" (e.g. "2 h 25 min" → 145) to avoid matching the
        # minutes component alone ("25 min") before the full expression.
        m = re.search(r"(\d+)\s*h\s+(\d+)\s*min\b", self._html)
        if m:
            self.__runtime_min = int(m.group(1)) * 60 + int(m.group(2))
            return
        # Fallback: standalone "NNN min" block (3-digit standalone runtime)
        m = re.search(r"\b(\d{3})\s*min\b", self._html)
        if m:
            self.__runtime_min = int(m.group(1))

    def __extract_image_url(self):
        m = re.search(r"(/img/poster/[^\"'>\s]+)", self._html)
        return "https://filmo.to" + m.group(1) if m else None

    def __extract_age_rating(self):
        m = re.search(r"\b(\d{1,2}\+)\b", self._html)
        self.__age_rating = m.group(1) if m else None

    # ---- provider data ----

    @property
    def provider_data(self):
        if self.__provider_data is None:
            self.__provider_data = self.__extract_provider_data()
        return self.__provider_data

    def __extract_chips(self):
        """Parse (lang, provider_name, data_p) triples from all provider-row blocks."""
        chips = []
        # Split on provider-row class boundaries to get one block per language group
        parts = self._html.split('class="provider-row"')
        for part in parts[1:]:
            lang_m = _CHIP_LANG_RE.search(part)
            lang = unescape(lang_m.group(1).strip()) if lang_m else ""

            found = _CHIP_RE.findall(part)
            if found:
                for provider_name, data_p in found:
                    chips.append((lang, provider_name, data_p))
            else:
                for data_p, provider_name in _CHIP_RE_ALT.findall(part):
                    chips.append((lang, provider_name, data_p))

        # Fallback: grab all chips without language grouping
        if not chips:
            for provider_name, data_p in _CHIP_RE.findall(self._html):
                chips.append(("", provider_name, data_p))

        return chips

    def __extract_provider_data(self):
        chips = self.__extract_chips()
        if not chips:
            logger.debug(f"filmo: no provider chips found on {self.url}")
            return None

        by_lang: dict = {}
        for lang, provider_name, data_p in chips:
            provider_key = host_to_provider(provider_name, require_extractor=True)
            if not provider_key:
                logger.debug(f"filmo: skipping unknown/unimplemented provider {provider_name!r}")
                continue
            audio = self.__lang_to_audio(lang)
            lang_key = (audio, Subtitles.NONE)
            by_lang.setdefault(lang_key, {})[provider_key] = data_p

        return ProviderData(by_lang) if by_lang else None

    @staticmethod
    def __lang_to_audio(label: str) -> Audio:
        label_lower = label.strip().lower()
        if label_lower in ("english", "en"):
            return Audio.ENGLISH
        if label_lower in ("deutsch", "german", "de"):
            return Audio.GERMAN
        # Unlabelled chips default to English (filmo.to default)
        return Audio.ENGLISH

    # ---- embed resolution ----

    def __resolve_embed(self, data_p: str) -> str:
        """POST /n {p} → token, then GET /n/<token> → embed URL."""
        try:
            from ...playwright.captcha import is_captcha_page, solve_captcha
        except ImportError:
            from aniworld.playwright.captcha import is_captcha_page, solve_captcha

        csrf = self._csrf_token
        if not csrf:
            raise ValueError("filmo: no CSRF token found; cannot resolve embed")

        resp = GLOBAL_SESSION.post(
            "https://filmo.to/n",
            json={"p": data_p},
            headers={
                "X-CSRF-TOKEN": csrf,
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json",
                "Referer": self.url,
            },
        )
        # The /n endpoint can 403/503 with a challenge page if cf_clearance
        # has expired; solve it and retry once.
        if is_captcha_page(resp.text, resp.status_code):
            logger.warning("filmo: challenge on /n — solving captcha and retrying")
            solve_captcha(self.url)
            # Re-fetch the page to refresh the CSRF token (the old one is tied
            # to the previous session that got challenged).
            self.__html = None
            self.__csrf_token = None
            csrf = self._csrf_token
            resp = GLOBAL_SESSION.post(
                "https://filmo.to/n",
                json={"p": data_p},
                headers={
                    "X-CSRF-TOKEN": csrf,
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json",
                    "Referer": self.url,
                },
            )
        try:
            token = resp.json().get("x", "")
        except Exception:
            raise ValueError(f"filmo: /n POST returned non-JSON: {resp.text[:200]}")
        if not token:
            raise ValueError(f"filmo: /n returned empty token (body: {resp.text[:200]})")

        # Follow redirect to the embed URL
        embed_resp = GLOBAL_SESSION.get(
            f"https://filmo.to/n/{token}",
            headers={"Referer": self.url},
        )
        final_url = embed_resp.url
        if "filmo.to" not in str(final_url):
            return str(final_url)

        # Interstitial page — extract first external link
        body = embed_resp.text
        for href in re.findall(r'href=["\']?(https?://[^"\'>\s]+)', body):
            if "filmo.to" not in href:
                return href
        for pattern in [
            r'content=["\']0;\s*url=(https?://[^"\']+)',
            r'<iframe[^>]+src=["\']?(https?://[^"\'>\s]+)',
            r'window\.location(?:\.href)?\s*=\s*["\']?(https?://[^"\']+)',
        ]:
            m = re.search(pattern, body, re.IGNORECASE)
            if m:
                return m.group(1)

        raise ValueError(
            f"filmo: /n/{token} (status {embed_resp.status_code}) contained no embed URL"
        )

    # ---- language/provider helpers ----

    def _normalize_language(self, language):
        text = str(language or "").strip().lower()
        if text in {"english", "englisch", "english dub"}:
            return (Audio.ENGLISH, Subtitles.NONE)
        return (Audio.GERMAN, Subtitles.NONE)

    def provider_link(self, language=None, provider=None):
        """Return the data-p payload string for the given language+provider."""
        if language is None:
            language = self.selected_language
        if isinstance(language, str):
            language = self._normalize_language(language)
        if provider is None:
            provider = self.selected_provider

        pd = self.provider_data
        if not isinstance(pd, ProviderData):
            return None

        provider_dict = pd.get(language)
        if not provider_dict:
            # Fall back to the first available language group
            for d in pd._data.values():
                provider_dict = d
                break
        if not provider_dict:
            return None

        return provider_dict.get(provider) or provider_dict.get(str(provider).upper())

    def available_providers(self, language=None):
        pd = self.provider_data
        if not isinstance(pd, ProviderData):
            return ()
        if language is None:
            language = self.selected_language
        if isinstance(language, str):
            language = self._normalize_language(language)
        provider_dict = pd.get(language)
        if not provider_dict:
            for d in pd._data.values():
                provider_dict = d
                break
        return tuple(provider_dict.keys()) if provider_dict else ()

    def provider_attempt_order(self):
        return build_provider_attempt_order(
            self.selected_provider,
            self.available_providers(),
        )

    # ---- selected_* properties ----

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
            self.__selected_language = self._normalize_language(
                self.__selected_language_param
                or os.getenv("ANIWORLD_LANGUAGE", "German Dub")
            )
        return self.__selected_language

    @selected_language.setter
    def selected_language(self, value):
        self.__selected_language_param = value
        self.__selected_language = None
        self.__redirect_url = None
        self.__provider_url = None
        self.__is_downloaded = None
        self.__base_folder = None
        self.__folder_path = None
        self.__episode_path = None
        self.__file_name = None

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

    # ---- redirect / provider / stream URLs ----

    @property
    def redirect_url(self):
        """The embed URL resolved from the data-p chip via POST /n."""
        if self.__redirect_url is None:
            data_p = self.provider_link(self.selected_language, self.selected_provider)
            if data_p is None:
                raise ValueError(
                    f"Language '{self.selected_language}' with provider "
                    f"'{self.selected_provider}' is not available for {self.url}"
                )
            self.__redirect_url = self.__resolve_embed(data_p)
        return self.__redirect_url

    @property
    def provider_url(self):
        if self.__provider_url is None:
            self.__provider_url = self.redirect_url
        return self.__provider_url

    @property
    def stream_url(self):
        key = f"get_direct_link_from_{self.selected_provider.lower()}"
        if key not in provider_functions:
            raise ValueError(
                f"The provider '{self.selected_provider}' is not yet implemented."
            )
        return provider_functions[key](self.provider_url)

    # ---- file path properties ----

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
            self.__file_name = self._movie_basename
        return self.__file_name

    @property
    def _file_extension(self):
        if self.__file_extension is None:
            naming_template = os.getenv("ANIWORLD_NAMING_TEMPLATE", NAMING_TEMPLATE)
            try:
                file_part = naming_template.split("/")[-1]
                ext = file_part.rsplit(".", 1)[-1] if "." in file_part else "mkv"
                self.__file_extension = ext or "mkv"
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

    # ---- actions ----

    download = episode_download
    watch = episode_watch
    syncplay = episode_syncplay
