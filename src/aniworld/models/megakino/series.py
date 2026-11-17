import os
import re
from functools import lru_cache
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse

import niquests

try:
    from ...config import (
        GLOBAL_SESSION,
        MEGAKINO_SERIES_PATTERN,
        NAMING_TEMPLATE,
        Audio,
        Subtitles,
        build_provider_attempt_order,
        logger,
    )
    from ..common import ProviderData, clean_title
    from ..common.common import check_downloaded, movie_folder_enabled
    from ..common.common import (
        download as episode_download,
    )
    from ..common.common import (
        syncplay as episode_syncplay,
    )
    from ..common.common import (
        watch as episode_watch,
    )
    from ..common.extraction import resolve_stream_url
    from ..common.naming import template_path
    from ..common.paths import resolve_download_path
    from ..common.provider_map import host_to_provider
except ImportError:
    from aniworld.config import (
        GLOBAL_SESSION,
        MEGAKINO_SERIES_PATTERN,
        NAMING_TEMPLATE,
        Audio,
        Subtitles,
        build_provider_attempt_order,
        logger,
    )
    from aniworld.models.common import (
        ProviderData,
        check_downloaded,
        clean_title,
        movie_folder_enabled,
    )
    from aniworld.models.common import (
        download as episode_download,
    )
    from aniworld.models.common import (
        syncplay as episode_syncplay,
    )
    from aniworld.models.common import (
        watch as episode_watch,
    )
    from aniworld.models.common.extraction import resolve_stream_url
    from aniworld.models.common.naming import template_path
    from aniworld.models.common.paths import resolve_download_path
    from aniworld.models.common.provider_map import host_to_provider

MEGAKINO_DOMAIN_SOURCE = "https://raw.githubusercontent.com/Yezun-hikari/new-domain-check/refs/heads/main/monitors/megakino/domain.txt"


@lru_cache(maxsize=1)
def get_megakino_domain():
    """Fetch the current MegaKino domain only when MegaKino browsing needs it."""
    response = niquests.get(MEGAKINO_DOMAIN_SOURCE, timeout=15)
    response.raise_for_status()

    domain = response.text.strip().lower()
    domain = re.sub(r"^https?://", "", domain).split("/", 1)[0]
    if not re.fullmatch(r"(?:[a-z0-9-]+\.)+[a-z]{2,}", domain):
        raise RuntimeError("MegaKino domain tracker returned an invalid domain")
    return domain


class MegaKinoEpisode:
    def __init__(
        self,
        url=str,
        selected_path=None,
        selected_language=None,
        selected_provider=None,
    ):
        url, episode_index = self.__parse_episode_selector(url)

        if not self.is_valid_megakino_series_url(url):
            raise ValueError(f"Invalid MegaKino series URL: {url}")

        self.url = url
        # 1-based index of the serial episode this instance targets (None for
        # movies / when no '#mkep=<n>' marker was given -> first episode).
        self.__episode_index = episode_index

        self.__selected_path_param = selected_path
        self.__selected_language_param = selected_language
        self.__selected_provider_param = selected_provider

        self.__provider_data = None
        self.__series_episodes = None

        self.__selected_path = None
        self.__selected_language = None
        self.__selected_provider = None

        self.__redirect_url = None
        self.__provider_url = None

        # https://jellyfin.org/docs/general/server/media/shows/#organization
        self.__base_folder = None
        self.__folder_path = None
        self.__file_name = None
        self.__file_extension = None
        self.__episode_path = None

        self.__is_downloaded = None

        ### Site extraction stuff below ###

        self.__title = None
        self.__title_cleaned = None
        self.__description = None
        self.__genres = None
        self.__release_year = None
        self.__poster_url = None
        self.__player_sources = None
        self.__html = None

        logger.debug(f"Initialized {self.url}")

    # -----------------------------
    # static methods
    # -----------------------------

    @staticmethod
    def is_valid_megakino_series_url(url):
        """Checks if the URL is a valid MegaKino series URL."""

        return bool(MEGAKINO_SERIES_PATTERN.match(url))

    @staticmethod
    def __parse_episode_selector(url):
        """Split an optional '#mkep=<n>' episode marker off a MegaKino URL.

        Serials list every episode on a single page; the web UI addresses one
        episode by appending '#mkep=<n>' to the series URL. HTTP never sends the
        fragment, so it is stripped here and remembered for provider extraction
        and per-episode file naming.
        """
        if not isinstance(url, str):
            return url, None
        match = re.search(r"#mkep=(\d+)$", url)
        if not match:
            return url, None
        return url[: match.start()], int(match.group(1))

    # -----------------------------
    # public properties
    # -----------------------------

    @property
    def title(self):
        if self.__title is None:
            self.__extract_title()
        return self.__title

    @property
    def title_cleaned(self):
        if self.__title_cleaned is None:
            self.__extract_title_cleaned()
        return self.__title_cleaned

    @property
    def description(self):
        if self.__description is None:
            self.__extract_description()
        return self.__description

    @property
    def genres(self):
        if self.__genres is None:
            self.__extract_genres()
        return self.__genres

    @property
    def release_year(self):
        if self.__release_year is None:
            self.__extract_release_year()
        return self.__release_year

    @property
    def poster_url(self):
        if self.__poster_url is None:
            self.__extract_poster_url()
        return self.__poster_url

    @property
    def player_sources(self):
        if self.__player_sources is None:
            self.__extract_player_sources()
        return self.__player_sources

    @property
    def _html(self):
        if self.__html is None:
            parsed_url = urlparse(self.url)
            token_url = f"{parsed_url.scheme}://{parsed_url.netloc}/index.php?yg=token"

            try:
                token_response = niquests.get(token_url, timeout=15)
                cookies = token_response.cookies
            except Exception:
                cookies = None

            response = niquests.get(self.url, timeout=30, cookies=cookies)
            response.raise_for_status()
            self.__html = response.text
        return self.__html

    # -----------------------------
    # private helpers
    # -----------------------------

    def __absolute_url(self, value: str):
        if not value:
            return None
        return urljoin(self.url, value.strip())

    @staticmethod
    def __format_naming_part(
        template_part,
        *,
        title,
        year,
        language,
        imdbid="",
        season="",
        episode="",
    ):
        formatted = template_part.format(
            title=title,
            year=year,
            imdbid=imdbid,
            season=season,
            episode=episode,
            language=language,
        )

        if not imdbid:
            formatted = re.sub(r"\s*\[imdbid-\]\s*", " ", formatted)

        formatted = re.sub(r"\bS\s*E\b", " ", formatted)
        formatted = re.sub(r"\s+", " ", formatted).strip()
        return formatted

    # -----------------------------
    # private extractors
    # -----------------------------

    def __extract_title(self):
        match = re.search(
            r'<meta\s+itemprop=["\']name["\']\s+content=["\']([^"\']+)["\']',
            self._html,
        )
        # Escaped in the markup, and this feeds the folder and file names.
        self.__title = unescape(match.group(1).strip()) if match else None

    def __extract_title_cleaned(self):
        self.__title_cleaned = clean_title(self.title) if self.title else None

    def __extract_description(self):
        match = re.search(
            r'<div\s+class=["\']page__text[^"\']*["\']\s+itemprop=["\']description["\']\s+[^>]*>(.*?)</div>',
            self._html,
            re.DOTALL,
        )
        if not match:
            self.__description = None
            return

        text = re.sub(r"<[^>]+>", "", match.group(1))
        text = re.sub(r"\s+", " ", text).strip()
        self.__description = text or None

    def __extract_genres(self):
        match = re.search(
            r'<div\s+class=["\']pmovie__genres["\']\s+itemprop=["\']genre["\']\s*>([^<]+)<',
            self._html,
        )
        if not match:
            self.__genres = None
            return

        genres = [genre.strip() for genre in match.group(1).split("/")]
        self.__genres = [
            genre for genre in genres if genre and genre.lower() != "filme"
        ]

    def __extract_release_year(self):
        match = re.search(
            r'<span\s+itemprop=["\']dateCreated["\']\s*>.*?<a[^>]*>(\d{4})<',
            self._html,
            re.DOTALL,
        )
        self.__release_year = match.group(1) if match else None

    def __extract_poster_url(self):
        match = re.search(
            r'<img\s+itemprop=["\']image["\'][^>]*data-src=["\']([^"\']+)["\']',
            self._html,
            re.DOTALL,
        )
        if not match:
            match = re.search(
                r'<img\s+itemprop=["\']image["\'][^>]*src=["\']([^"\']+)["\']',
                self._html,
                re.DOTALL,
            )

        self.__poster_url = self.__absolute_url(match.group(1)) if match else None

    def __extract_player_sources(self):
        blocks = re.findall(
            r'<div\s+class=["\']tabs-block__content[^"\']*["\'][^>]*>(.*?)</div>',
            self._html,
            re.DOTALL,
        )

        sources = []

        for index, block in enumerate(blocks):
            iframe_match = re.search(
                r'<iframe[^>]*src=["\']([^"\']+)["\']', block, re.DOTALL
            )
            if not iframe_match:
                iframe_match = re.search(
                    r'<iframe[^>]*data-src=["\']([^"\']+)["\']',
                    block,
                    re.DOTALL,
                )

            if not iframe_match:
                continue

            source_url = iframe_match.group(1).strip()
            host = urlparse(source_url).netloc

            sources.append(
                {
                    "host": host,
                    "url": source_url,
                    "primary": index == 0,
                }
            )

        logger.debug(
            f"MegaKino stream URLs found: {[source['url'] for source in sources]}"
        )
        self.__player_sources = sources or None

    @property
    def is_series(self):
        """True when the page is a serial (per-episode player selects)."""
        return bool(self.series_episodes)

    @property
    def series_episodes(self):
        """List of serial episodes: {number, id, label, providers}.

        Empty for movie pages, which use the tabs-block iframe layout instead.
        """
        if self.__series_episodes is None:
            self.__series_episodes = self.__extract_series_episodes()
        return self.__series_episodes

    def __extract_series_episodes(self):
        # Serials render an episode picker (<select class="... se-select">) whose
        # option values (ep1, ep2, ...) each map to a provider <select> carrying
        # that episode's hoster links. Movies have no such picker.
        select_match = re.search(
            r"<select\b(?=[^>]*se-select)[^>]*>(.*?)</select>",
            self._html,
            re.DOTALL,
        )
        if not select_match:
            return []

        episodes = []
        for index, option in enumerate(
            re.finditer(
                r'<option\s+value=["\']([^"\']+)["\']\s*>(.*?)</option>',
                select_match.group(1),
                re.DOTALL,
            ),
            start=1,
        ):
            episode_id = option.group(1).strip()
            label = re.sub(r"\s+", " ", option.group(2)).strip() or f"Episode {index}"
            episodes.append(
                {
                    "number": index,
                    "id": episode_id,
                    "label": label,
                    "providers": self.__extract_series_episode_providers(episode_id),
                }
            )
        return episodes

    def __extract_series_episode_providers(self, episode_id):
        block = re.search(
            r'<select\b(?=[^>]*id=["\']' + re.escape(episode_id) + r'["\'])'
            r"(?=[^>]*mr-select)[^>]*>(.*?)</select>",
            self._html,
            re.DOTALL,
        )
        providers = {}
        if not block:
            return providers

        for option in re.finditer(
            r'<option\s+value=["\']([^"\']+)["\']\s*>(.*?)</option>',
            block.group(1),
            re.DOTALL,
        ):
            url = option.group(1).strip()
            provider_name = host_to_provider(urlparse(url).hostname)
            if not provider_name:
                continue
            providers.setdefault(provider_name, url)
        return providers

    def __selected_series_providers(self):
        episodes = self.series_episodes
        if not episodes:
            return {}
        index = self.__episode_index or 1
        episode = next((ep for ep in episodes if ep["number"] == index), None)
        return episode["providers"] if episode else {}

    def __extract_provider_data(self):
        # Serials expose every episode on one page; target the selected episode.
        if self.is_series:
            providers = self.__selected_series_providers()
            if not providers:
                return None
            return ProviderData({(Audio.GERMAN, Subtitles.NONE): providers})

        if self.player_sources is None:
            return None

        providers = {}
        for source in self.player_sources:
            url = (source.get("url") or "").strip()
            provider_name = host_to_provider(urlparse(url).hostname)
            if not provider_name:
                continue

            providers[provider_name] = url

        if not providers:
            return None

        return ProviderData({(Audio.GERMAN, Subtitles.NONE): providers})

    ### metadata stuff

    @property
    def provider_data(self):
        if self.__provider_data is None:
            self.__provider_data = self.__extract_provider_data()
        return self.__provider_data

    def _normalize_language(self, language):
        if isinstance(language, tuple) and len(language) == 2:
            return language

        if not isinstance(language, str):
            raise TypeError(f"Unsupported MegaKino language selection: {language}")

        normalized = language.strip().lower()
        if normalized in {"german", "deutsch", "german dub"}:
            return "German Dub"
        # MegaKino only serves German audio; English requests map to it on purpose (27acb93).
        if normalized in {"english", "englisch", "english dub"}:
            return "German Dub"

        raise ValueError(f"Unsupported MegaKino language selection: {language}")

    @property
    def selected_path(self):
        if self.__selected_path is None:
            self.__selected_path = str(
                resolve_download_path(self.__selected_path_param)
            )
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
        self.__selected_language_param = self._normalize_language(value)
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

    @property
    def redirect_url(self):
        if self.__redirect_url is None:
            link = self.provider_link(self.selected_language, self.selected_provider)
            if link is None:
                raise ValueError(
                    f"Language '{self.selected_language}' with provider "
                    f"'{self.selected_provider}' is not available for "
                    f"episode: {self.url}"
                )
            self.__redirect_url = link
        return self.__redirect_url

    def provider_link(self, language=None, provider=None):
        if language is None:
            language = self.selected_language

        language = self._normalize_language(language)

        if provider is None:
            provider = self.selected_provider

        provider_data = self.provider_data
        if provider_data is None:
            return None

        provider_dict = provider_data.get((Audio.GERMAN, Subtitles.NONE))

        if not provider_dict:
            return None

        provider_key = str(provider).strip()
        return provider_dict.get(provider_key) or provider_dict.get(
            provider_key.upper()
        )

    def available_providers(self, language=None):
        if language is None:
            language = self.selected_language

        language = self._normalize_language(language)
        provider_data = self.provider_data
        if provider_data is None:
            return ()

        provider_dict = provider_data.get((Audio.GERMAN, Subtitles.NONE))

        return tuple(provider_dict.keys()) if provider_dict else ()

    def provider_attempt_order(self):
        return build_provider_attempt_order(
            self.selected_provider,
            self.available_providers(),
        )

    @property
    def provider_url(self):
        if self.__provider_url is None:
            self.__provider_url = GLOBAL_SESSION.get(self.redirect_url).url
        return self.__provider_url

    @property
    def stream_url(self):
        return resolve_stream_url(self)

    @property
    def _legacy_base_folder(self):
        if self.__base_folder is None:
            if self.is_series:
                # Keep a serial's episodes together in a title folder; the year
                # is often absent on serial pages, so it is left out.
                folder_name = clean_title(
                    self.title_cleaned or self.title or "MegaKino"
                )
                self.__base_folder = Path(self.selected_path) / folder_name
            elif movie_folder_enabled():
                folder_name = f"{self.title_cleaned} ({self.release_year})"
                self.__base_folder = Path(self.selected_path) / folder_name
            else:
                self.__base_folder = Path(self.selected_path)
        return self.__base_folder

    @property
    def _base_folder(self):
        root = Path(self.selected_path)
        relative = self._episode_path.relative_to(root)
        return root / relative.parts[0] if len(relative.parts) > 1 else root

    @property
    def _folder_path(self):
        return self._episode_path.parent

    @property
    def _file_name(self):
        return self._episode_path.stem

    @property
    def _file_extension(self):
        return self._episode_path.suffix.lstrip(".")

    @property
    def _episode_path(self):
        if self.__episode_path is None:
            template = os.getenv("ANIWORLD_NAMING_TEMPLATE", NAMING_TEMPLATE)
            path = template_path(
                self.selected_path,
                template,
                {
                    "title": self.title_cleaned,
                    "year": self.release_year,
                    "imdbid": "",
                    "season": "01" if self.is_series else "",
                    "episode": f"{(self.__episode_index or 1):03d}"
                    if self.is_series
                    else "",
                    "language": self.selected_language,
                    "resolution": getattr(self, "_resolution", "unknown"),
                },
                is_series=self.is_series,
                movie_folder=movie_folder_enabled(),
            )
            extension = path.suffix.lstrip(".")
            if self.is_series:
                legacy = (
                    self._legacy_base_folder
                    / f"{self.title_cleaned} - E{self.__episode_index or 1:02d}.{extension}"
                )
            else:
                legacy = (
                    self._legacy_base_folder
                    / f"{self.title_cleaned} ({self.release_year}).{extension}"
                )
            # Keep old downloads in place; new downloads use the full template.
            self.__episode_path = (
                path if path.exists() or not legacy.exists() else legacy
            )
        return self.__episode_path

    @property
    def is_downloaded(self):
        if self.__is_downloaded is None:
            self.__is_downloaded = check_downloaded(self._episode_path)
        return self.__is_downloaded

    # -----------------------------
    # PUBLIC METHODS
    # -----------------------------

    # Episode actions are implemented in aniworld.models.common.common
    download = episode_download
    watch = episode_watch
    syncplay = episode_syncplay
