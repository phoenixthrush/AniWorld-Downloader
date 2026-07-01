import os
import re
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
    from ...extractors import provider_functions
    from ..common import ProviderData, clean_title
    from ..common.common import check_downloaded
    from ..common.common import (
        download as episode_download,
    )
    from ..common.common import (
        syncplay as episode_syncplay,
    )
    from ..common.common import (
        watch as episode_watch,
    )
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
    from aniworld.extractors import provider_functions
    from aniworld.models.common import ProviderData, check_downloaded, clean_title
    from aniworld.models.common import (
        download as episode_download,
    )
    from aniworld.models.common import (
        syncplay as episode_syncplay,
    )
    from aniworld.models.common import (
        watch as episode_watch,
    )

MEGAKINO_DOMAIN = niquests.get(
    "https://raw.githubusercontent.com/Yezun-hikari/new-domain-check/refs/heads/main/monitors/megakino/domain.txt"
).text.strip()


class MegaKinoEpisode:
    def __init__(
        self,
        url=str,
        selected_path=None,
        selected_language=None,
        selected_provider=None,
    ):
        if not self.is_valid_megakino_series_url(url):
            raise ValueError(f"Invalid MegaKino series URL: {url}")

        self.url = url

        self.__selected_path_param = selected_path
        self.__selected_language_param = selected_language
        self.__selected_provider_param = selected_provider

        self.__provider_data = None

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
        self.__original_title = None
        self.__description = None
        self.__genres = None
        self.__country = None
        self.__release_year = None
        self.__duration_minutes = None
        self.__poster_url = None
        self.__backdrop_url = None
        self.__directors = None
        self.__actors = None
        self.__producer = None
        self.__age_rating = None
        self.__quality_label = None
        self.__kinopoisk_rating = None
        self.__site_rating_score = None
        self.__site_rating_votes = None
        self.__likes = None
        self.__dislikes = None
        self.__trailer_url = None
        self.__post_id = None
        self.__canonical_url = None
        self.__og_image = None
        self.__created_at = None
        self.__published_at = None
        self.__player_sources = None
        self.__default_player = None
        self.__stream_label = None
        self.__available_hosts = None
        self.__recommended_entries = None
        self.__html = None

        logger.debug(f"Initialized {self.url}")

    # -----------------------------
    # static methods
    # -----------------------------

    @staticmethod
    def is_valid_megakino_series_url(url):
        """Checks if the URL is a valid MegaKino series URL."""

        return bool(MEGAKINO_SERIES_PATTERN.match(url))

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
    def original_title(self):
        if self.__original_title is None:
            self.__extract_original_title()
        return self.__original_title

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
    def country(self):
        if self.__country is None:
            self.__extract_country()
        return self.__country

    @property
    def release_year(self):
        if self.__release_year is None:
            self.__extract_release_year()
        return self.__release_year

    @property
    def duration_minutes(self):
        if self.__duration_minutes is None:
            self.__extract_duration_minutes()
        return self.__duration_minutes

    @property
    def poster_url(self):
        if self.__poster_url is None:
            self.__extract_poster_url()
        return self.__poster_url

    @property
    def backdrop_url(self):
        if self.__backdrop_url is None:
            self.__extract_backdrop_url()
        return self.__backdrop_url

    @property
    def directors(self):
        if self.__directors is None:
            self.__extract_directors()
        return self.__directors

    @property
    def actors(self):
        if self.__actors is None:
            self.__extract_actors()
        return self.__actors

    @property
    def producer(self):
        if self.__producer is None:
            self.__extract_producer()
        return self.__producer

    @property
    def age_rating(self):
        if self.__age_rating is None:
            self.__extract_age_rating()
        return self.__age_rating

    @property
    def quality_label(self):
        if self.__quality_label is None:
            self.__extract_quality_label()
        return self.__quality_label

    @property
    def kinopoisk_rating(self):
        if self.__kinopoisk_rating is None:
            self.__extract_kinopoisk_rating()
        return self.__kinopoisk_rating

    @property
    def site_rating_score(self):
        if self.__site_rating_score is None:
            self.__extract_site_rating_score()
        return self.__site_rating_score

    @property
    def site_rating_votes(self):
        if self.__site_rating_votes is None:
            self.__extract_site_rating_votes()
        return self.__site_rating_votes

    @property
    def likes(self):
        if self.__likes is None:
            self.__extract_likes()
        return self.__likes

    @property
    def dislikes(self):
        if self.__dislikes is None:
            self.__extract_dislikes()
        return self.__dislikes

    @property
    def trailer_url(self):
        if self.__trailer_url is None:
            self.__extract_trailer_url()
        return self.__trailer_url

    @property
    def post_id(self):
        if self.__post_id is None:
            self.__extract_post_id()
        return self.__post_id

    @property
    def canonical_url(self):
        if self.__canonical_url is None:
            self.__extract_canonical_url()
        return self.__canonical_url

    @property
    def og_image(self):
        if self.__og_image is None:
            self.__extract_og_image()
        return self.__og_image

    @property
    def created_at(self):
        if self.__created_at is None:
            self.__extract_created_at()
        return self.__created_at

    @property
    def published_at(self):
        if self.__published_at is None:
            self.__extract_published_at()
        return self.__published_at

    @property
    def player_sources(self):
        if self.__player_sources is None:
            self.__extract_player_sources()
        return self.__player_sources

    @property
    def default_player(self):
        if self.__default_player is None:
            self.__extract_default_player()
        return self.__default_player

    @property
    def stream_label(self):
        if self.__stream_label is None:
            self.__extract_stream_label()
        return self.__stream_label

    @property
    def available_hosts(self):
        if self.__available_hosts is None:
            self.__extract_available_hosts()
        return self.__available_hosts

    @property
    def recommended_entries(self):
        if self.__recommended_entries is None:
            self.__extract_recommended_entries()
        return self.__recommended_entries

    # TODO: implement html fetch
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

    def __extract_links_from_span(self, itemprop: str):
        match = re.search(
            rf'<span\s+itemprop=["\']{itemprop}["\']\s*>(.+?)</span>',
            self._html,
            re.DOTALL,
        )
        if not match:
            return None

        values = re.findall(r"<a[^>]*>(.*?)</a>", match.group(1), re.DOTALL)
        values = [value.strip() for value in values if value.strip()]
        return values or None

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
        self.__title = match.group(1).strip() if match else None

    def __extract_title_cleaned(self):
        self.__title_cleaned = clean_title(self.title) if self.title else None

    def __extract_original_title(self):
        match = re.search(
            r'<div\s+class=["\']pmovie__original-title["\']\s+itemprop=["\']alternativeHeadline["\']\s*>([^<]*)<',
            self._html,
        )
        self.__original_title = match.group(1).strip() if match else None

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

    def __extract_country(self):
        match = re.search(
            r'<span\s+itemprop=["\']countryOfOrigin["\']\s*>([^<]+)<',
            self._html,
        )
        self.__country = match.group(1).strip() if match else None

    def __extract_release_year(self):
        match = re.search(
            r'<span\s+itemprop=["\']dateCreated["\']\s*>.*?<a[^>]*>(\d{4})<',
            self._html,
            re.DOTALL,
        )
        self.__release_year = match.group(1) if match else None

    def __extract_duration_minutes(self):
        match = re.search(
            r'<div\s+class=["\']pmovie__year["\']>.*?,\s*(\d+)\s*min\s*</div>',
            self._html,
            re.DOTALL,
        )
        self.__duration_minutes = int(match.group(1)) if match else None

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

    def __extract_backdrop_url(self):
        match = re.search(
            r'<div\s+class=["\']pmovie__btn-trailer[^"\']*["\'].*?<img[^>]*data-src=["\']([^"\']+)["\']',
            self._html,
            re.DOTALL,
        )
        if not match:
            match = re.search(
                r'<div\s+class=["\']pmovie__btn-trailer[^"\']*["\'].*?<img[^>]*src=["\']([^"\']+)["\']',
                self._html,
                re.DOTALL,
            )

        self.__backdrop_url = self.__absolute_url(match.group(1)) if match else None

    def __extract_directors(self):
        self.__directors = self.__extract_links_from_span("directors")

    def __extract_actors(self):
        self.__actors = self.__extract_links_from_span("actors")

    def __extract_producer(self):
        match = re.search(
            r'<span\s+itemprop=["\']productionCompany["\']\s*>(.+?)</span>',
            self._html,
            re.DOTALL,
        )
        if not match:
            self.__producer = None
            return

        self.__producer = re.sub(r"\s+", " ", match.group(1)).strip()

    def __extract_age_rating(self):
        match = re.search(
            r'<div\s+class=["\']pmovie__age\s+order-first["\']\s*><div>([^<]+)<',
            self._html,
        )
        self.__age_rating = match.group(1).strip() if match else None

    def __extract_quality_label(self):
        match = re.search(
            r'<div\s+class=["\']poster__label["\']>([^<]+)<',
            self._html,
        )
        self.__quality_label = match.group(1).strip() if match else None

    def __extract_kinopoisk_rating(self):
        match = re.search(
            r'<div\s+class=["\'][^"\']*pmovie__subrating--kp[^"\']*["\'][^>]*>.*?([0-9]+,[0-9]+)\s*</div>',
            self._html,
            re.DOTALL,
        )
        self.__kinopoisk_rating = match.group(1).replace(",", ".") if match else None

    def __extract_site_rating_score(self):
        match = re.search(
            r'<span\s+class=["\']ratingtypeplusminus\s+ratingplus["\']\s*>\+?(\d+)<',
            self._html,
        )
        self.__site_rating_score = int(match.group(1)) if match else None

    def __extract_site_rating_votes(self):
        match = re.search(
            r'<span\s+id=["\']vote-num-id-\d+["\']>(\d+)<',
            self._html,
        )
        self.__site_rating_votes = int(match.group(1)) if match else None

    def __extract_likes(self):
        match = re.search(r'<span\s+id=["\']likes-id-\d+["\']>(\d+)<', self._html)
        self.__likes = int(match.group(1)) if match else None

    def __extract_dislikes(self):
        match = re.search(r'<span\s+id=["\']dislikes-id-\d+["\']>(\d+)<', self._html)
        self.__dislikes = int(match.group(1)) if match else None

    def __extract_trailer_url(self):
        match = re.search(
            r'<link\s+itemprop=["\']embedUrl["\']\s+href=["\']([^"\']+)["\']',
            self._html,
        )
        self.__trailer_url = match.group(1).strip() if match else None

    def __extract_post_id(self):
        match = re.search(
            r'<input\s+type=["\']hidden["\']\s+name=["\']post_id["\']\s+id=["\']post_id["\']\s+value=["\'](\d+)["\']',
            self._html,
        )
        self.__post_id = int(match.group(1)) if match else None

    def __extract_canonical_url(self):
        match = re.search(
            r'<link\s+rel=["\']canonical["\']\s+href=["\']([^"\']+)["\']',
            self._html,
        )
        self.__canonical_url = match.group(1).strip() if match else None

    def __extract_og_image(self):
        match = re.search(
            r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']',
            self._html,
        )
        self.__og_image = self.__absolute_url(match.group(1)) if match else None

    def __extract_created_at(self):
        match = re.search(
            r'<meta\s+itemprop=["\']dateCreated["\']\s+content=["\']([^"\']+)["\']',
            self._html,
        )
        self.__created_at = match.group(1).strip() if match else None

    def __extract_published_at(self):
        match = re.search(
            r'<meta\s+itemprop=["\']datePublished["\']\s+content=["\']([^"\']+)["\']',
            self._html,
        )
        self.__published_at = match.group(1).strip() if match else None

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

    def __extract_default_player(self):
        match = re.search(
            r'<div\s+class=["\']tabs-block__select[^"\']*["\'][^>]*>\s*<span>([^<]+)</span>',
            self._html,
            re.DOTALL,
        )
        self.__default_player = match.group(1).strip() if match else None

    def __extract_stream_label(self):
        spans = re.findall(
            r'<div\s+class=["\']tabs-block__select[^"\']*["\'][^>]*>.*?</div>',
            self._html,
            re.DOTALL,
        )
        if not spans:
            self.__stream_label = None
            return

        labels = re.findall(r"<span>([^<]+)</span>", spans[0], re.DOTALL)
        labels = [label.strip() for label in labels if label.strip()]
        self.__stream_label = labels[1] if len(labels) > 1 else None

    def __extract_available_hosts(self):
        if self.player_sources is None:
            self.__available_hosts = None
            return

        hosts = []
        for source in self.player_sources:
            host = source.get("host")
            if host and host not in hosts:
                hosts.append(host)

        self.__available_hosts = hosts or None

    def __extract_provider_data(self):
        if self.player_sources is None:
            return None

        providers = {}
        for source in self.player_sources:
            host = (source.get("host") or "").strip().lower()
            url = (source.get("url") or "").strip()
            if not host or not url:
                continue

            if host.endswith("voe.sx"):
                provider_name = "VOE"
            elif host.endswith("gxplayer.xyz"):
                provider_name = "MegaKino"
            else:
                provider_name = host.split(".", 1)[0].upper()

            if (
                f"get_direct_link_from_{provider_name.lower()}"
                not in provider_functions
            ):
                continue

            providers[provider_name] = url

        if not providers:
            return None

        return ProviderData({(Audio.GERMAN, Subtitles.NONE): providers})

    def __extract_recommended_entries(self):
        section_match = re.search(
            r'<section\s+class=["\']sect\s+pmovie__related["\'].*?<div\s+class=["\']sect__content\s+d-grid["\']>(.*?)</div>\s*</section>',
            self._html,
            re.DOTALL,
        )
        if not section_match:
            self.__recommended_entries = None
            return

        section_html = section_match.group(1)
        items = re.findall(
            r'<a\s+class=["\']poster[^"\']*["\']\s+href=["\']([^"\']+)["\']>(.*?)</a>',
            section_html,
            re.DOTALL,
        )

        entries = []

        for href, item_html in items:
            title_match = re.search(
                r'<h3\s+class=["\']poster__title[^"\']*["\']>([^<]+)<',
                item_html,
            )
            li_matches = re.findall(r"<li>([^<]+)</li>", item_html, re.DOTALL)
            img_match = re.search(
                r'<img[^>]*data-src=["\']([^"\']+)["\']',
                item_html,
                re.DOTALL,
            )
            if not img_match:
                img_match = re.search(
                    r'<img[^>]*src=["\']([^"\']+)["\']',
                    item_html,
                    re.DOTALL,
                )

            year = None
            genres = None

            if li_matches:
                if re.fullmatch(r"\d{4}", li_matches[0].strip()):
                    year = li_matches[0].strip()

                if len(li_matches) > 1:
                    genres = [
                        genre.strip()
                        for genre in li_matches[1].split("/")
                        if genre.strip()
                    ]

            entries.append(
                {
                    "title": title_match.group(1).strip() if title_match else None,
                    "url": self.__absolute_url(href),
                    "year": year,
                    "genres": genres,
                    "poster_url": self.__absolute_url(img_match.group(1))
                    if img_match
                    else None,
                }
            )

        self.__recommended_entries = entries or None

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
            raise ValueError(f"Unsupported MegaKino language selection: {language}")

        normalized = language.strip().lower()
        if normalized in {"german", "deutsch", "german dub"}:
            return "German Dub"
        if normalized in {"english", "englisch", "english dub"}:
            return "German Dub"

        raise ValueError(f"Unsupported MegaKino language selection: {language}")

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

        if isinstance(provider_data, ProviderData):
            provider_dict = provider_data.get((Audio.GERMAN, Subtitles.NONE))
            if language == "English Dub":
                provider_dict = (
                    provider_data.get((Audio.ENGLISH, Subtitles.NONE)) or provider_dict
                )
        else:
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
            return tuple()

        if isinstance(provider_data, ProviderData):
            provider_dict = provider_data.get((Audio.ENGLISH, Subtitles.NONE))
            if language != "English Dub":
                provider_dict = provider_data.get((Audio.GERMAN, Subtitles.NONE))
        else:
            provider_dict = provider_data.get((Audio.GERMAN, Subtitles.NONE))

        return tuple(provider_dict.keys()) if provider_dict else tuple()

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
    def _base_folder(self):
        if self.__base_folder is None:
            folder_name = f"{self.title_cleaned} ({self.release_year})"
            self.__base_folder = Path(self.selected_path) / folder_name
        return self.__base_folder

    @property
    def _folder_path(self):
        if self.__folder_path is None:
            self.__folder_path = self._base_folder
        return self.__folder_path

    @property
    def _file_name(self):
        if self.__file_name is None:
            self.__file_name = f"{self.title_cleaned} ({self.release_year})"
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

    # END

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


if __name__ == "__main__":
    test_url = "https://megakino8.com/films/205-deadpool.html"
    movie = MegaKinoEpisode(test_url)

    print("Title:", movie.title)
    print("Cleaned Title:", movie.title_cleaned)
    print("Original Title:", movie.original_title)
    print("Description:", movie.description)
    print("Genres:", movie.genres)
    print("Country:", movie.country)
    print("Release Year:", movie.release_year)
    print("Duration (minutes):", movie.duration_minutes)
    print("Poster URL:", movie.poster_url)
    print("Backdrop URL:", movie.backdrop_url)
    print("Directors:", movie.directors)
    print("Actors:", movie.actors)
    print("Producer:", movie.producer)
    print("Age Rating:", movie.age_rating)
    print("Quality Label:", movie.quality_label)
    print("Kinopoisk Rating:", movie.kinopoisk_rating)
    print("Site Rating Score:", movie.site_rating_score)
    print("Site Rating Votes:", movie.site_rating_votes)
    print("Likes:", movie.likes)
    print("Dislikes:", movie.dislikes)
    print("Trailer URL:", movie.trailer_url)
    print("Post ID:", movie.post_id)
    print("Canonical URL:", movie.canonical_url)
    print("OG Image URL:", movie.og_image)
    print("Created At:", movie.created_at)
    print("Published At:", movie.published_at)
    print("Player Sources:", movie.player_sources)
    print("Default Player:", movie.default_player)
    print("Stream Label:", movie.stream_label)
    print("Available Hosts:", movie.available_hosts)
    print("Recommended Entries:")
    for entry in movie.recommended_entries or []:
        print(entry)

    movie.download()
