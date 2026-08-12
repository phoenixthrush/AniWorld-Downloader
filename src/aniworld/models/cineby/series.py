"""cineby.at models (movies + TV).

cineby is a TMDB-based Next.js app that resolves its streams client-side
(encrypted source API behind Cloudflare), so metadata comes from the TMDB proxy
it uses (`db.wingsdatabase.com/3`, no API key needed) and the playable HLS URL
is captured with the headless browser — the same approach already used for
hanime. URLs are `/movie/<tmdb_id>` and `/tv/<tmdb_id>/<season>/<episode>`.
"""

import os
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from ...config import (
        Audio,
        Subtitles,
        logger,
    )
    from ..common import check_downloaded, movie_folder_enabled, run_each
    from ..common.common import clean_title
    from ..common.common import download as episode_download
    from ..common.common import syncplay as episode_syncplay
    from ..common.common import watch as episode_watch
    from ..common.http import get_session
except ImportError:
    from aniworld.config import (
        Audio,
        Subtitles,
        logger,
    )
    from aniworld.models.common import (
        check_downloaded,
        movie_folder_enabled,
        run_each,
    )
    from aniworld.models.common.common import clean_title
    from aniworld.models.common.common import download as episode_download
    from aniworld.models.common.common import syncplay as episode_syncplay
    from aniworld.models.common.common import watch as episode_watch
    from aniworld.models.common.http import get_session

CINEBY_BASE = "https://www.cineby.at"
TMDB_PROXY = "https://db.wingsdatabase.com/3"
TMDB_IMG = "https://image.tmdb.org/t/p/w500"
# cineby plays through the vidking embed; capturing the stream from the bare
# embed page is far more reliable than driving cineby's full SPA.
VIDKING_BASE = "https://www.vidking.net"


def vidking_embed_url(is_movie, tmdb_id, season=None, episode=None):
    """The vidking player embed URL cineby loads to resolve a stream."""
    if is_movie:
        return f"{VIDKING_BASE}/embed/movie/{tmdb_id}"
    return f"{VIDKING_BASE}/embed/tv/{tmdb_id}/{season or 1}/{episode or 1}"


# cineby's playable sources come from this API (encrypted with enc=2). Resolving
# it directly is browser-free and reliable; the headless capture is the fallback.
WINGS_API = "https://api.wingsdatabase.com"


def _fetch(url, params=None, timeout=15):
    """GET a wingsdatabase URL, returning the response object.

    Prefers curl_cffi with a real Chrome TLS fingerprint: api/db.wingsdatabase.com
    sit behind Cloudflare (it hands out ``error code: 1200`` / 503 to clients it
    doesn't like — the same gate VOE needed impersonation for), and curl_cffi
    also resolves DNS itself instead of the shared session's DoH resolver, which
    can be unreachable inside a container. Falls back to the shared niquests
    session when curl_cffi isn't installed or errors.
    """
    try:
        from curl_cffi import requests as _curl_requests

        return _curl_requests.get(
            url,
            params=params,
            headers=_TMDB_HEADERS,
            impersonate="chrome124",
            timeout=timeout,
        )
    except ImportError:
        pass
    except Exception as exc:
        logger.debug(f"cineby curl_cffi fetch failed ({exc}); using niquests")

    return get_session().get(url, params=params, headers=_TMDB_HEADERS, timeout=timeout)


def _best_source(sources):
    """Pick the highest-quality m3u8 from a decrypted sources list."""

    def quality(src):
        m = re.match(r"(\d+)", str(src.get("quality", "")))
        return int(m.group(1)) if m else 0

    for src in sorted(sources or [], key=quality, reverse=True):
        url = src.get("url")
        if url and ".m3u8" in url:
            return url
    return None


def resolve_stream_via_api(
    media_type, tmdb_id, title, year, imdb_id, season, episode, attempts=3
):
    """Resolve the playable m3u8 straight from cineby's source API (no browser).

    Fetches the short-lived seed, then the ``enc=2`` sources blob, decrypts it
    (STREAMCRYPTO) and returns the highest-quality playlist. The API is behind
    Cloudflare and rate-limits per IP, so a single request fails often enough to
    be unreliable; we retry a few times (fresh seed each time — it has a 30 s TTL)
    with a short backoff before giving up. Returns None on total failure so the
    caller can fall back to the headless capture, and logs *why* at WARNING so a
    persistent failure is diagnosable instead of silently blamed on the browser.
    """
    from .streamcrypto import decrypt_sources

    last_err = None
    for attempt in range(attempts):
        try:
            seed_resp = _fetch(f"{WINGS_API}/seed", params={"mediaId": tmdb_id})
            if seed_resp.status_code != 200:
                raise RuntimeError(
                    f"seed HTTP {seed_resp.status_code}: {seed_resp.text[:80]!r}"
                )
            seed = (seed_resp.json() or {}).get("seed")
            if not seed:
                raise RuntimeError(f"no seed in response: {seed_resp.text[:80]!r}")

            params = {
                "title": title or "",
                "mediaType": media_type,
                "year": year or "",
                "episodeId": episode or 1,
                "seasonId": season or 1,
                "tmdbId": tmdb_id,
                "imdbId": imdb_id or "",
                "enc": "2",
                "seed": seed,
            }
            src_resp = _fetch(f"{WINGS_API}/cdn/sources-with-title", params=params)
            if src_resp.status_code != 200:
                raise RuntimeError(
                    f"sources HTTP {src_resp.status_code}: {src_resp.text[:80]!r}"
                )
            # A rate-limit / error comes back as a JSON body ({"error": ...}); the
            # real payload is base64url and never starts with a brace.
            if src_resp.text.lstrip().startswith("{"):
                raise RuntimeError(f"sources error: {src_resp.text[:80]!r}")

            data = decrypt_sources(src_resp.text, seed, int(tmdb_id))
            url = _best_source(data.get("sources"))
            if url:
                return url
            raise RuntimeError("no playable m3u8 in decrypted sources")
        except Exception as exc:
            last_err = exc
            logger.debug(
                f"cineby API resolve attempt {attempt + 1}/{attempts} failed: {exc}"
            )
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))

    logger.warning(
        f"cineby API stream resolve failed for tmdb {tmdb_id} after "
        f"{attempts} attempts: {last_err}"
    )
    return None


# cineby's language labels line up with the rest of the app's dub labels so the
# download pipeline's LANG maps ("German Dub" -> deu, "English Dub" -> eng) work
# unchanged.
ENGLISH_LABEL = "English Dub"
GERMAN_LABEL = "German Dub"

# The source API is mirrored across several "servers" (path prefixes). The first
# (cdn) carries the original audio muxed into the stream — what cineby plays by
# default. The others sometimes expose extra dub tracks (German among them) as a
# separate audio rendition inside an HLS master, which is what the player's
# "server" list surfaces. We scan the extras only to find a German rendition.
CINEBY_DEFAULT_SERVER = "cdn/sources-with-title"
CINEBY_EXTRA_SERVERS = (
    "neon2/sources-with-title",
    "downloader2/sources-with-title",
    "tejo/sources-with-title",
    "1movies/sources-with-title",
)

# Availability is stable per title but costs several requests to probe, so cache
# it per (media_type, tmdb, season, episode). Stores the label list plus which
# server carried German — never a stream URL, since those hold short-lived tokens
# and must be re-resolved fresh at download time.
_LANG_DETECT_CACHE = {}


def _fetch_decrypted_sources(
    endpoint, media_type, tmdb_id, title, year, imdb_id, season, episode, attempts=2
):
    """Fetch + decrypt one server's ``enc=2`` sources blob. Returns dict or None.

    Same seed/decrypt dance as ``resolve_stream_via_api`` but for an arbitrary
    server endpoint and returning the whole payload (``{sources, subtitles}``)
    instead of a single URL, so callers can inspect audio renditions.
    """
    from .streamcrypto import decrypt_sources

    last_err = None
    for attempt in range(attempts):
        try:
            seed_resp = _fetch(f"{WINGS_API}/seed", params={"mediaId": tmdb_id})
            if seed_resp.status_code != 200:
                raise RuntimeError(f"seed HTTP {seed_resp.status_code}")
            seed = (seed_resp.json() or {}).get("seed")
            if not seed:
                raise RuntimeError("no seed in response")
            params = {
                "title": title or "",
                "mediaType": media_type,
                "year": year or "",
                "episodeId": episode or 1,
                "seasonId": season or 1,
                "tmdbId": tmdb_id,
                "imdbId": imdb_id or "",
                "enc": "2",
                "seed": seed,
            }
            src_resp = _fetch(f"{WINGS_API}/{endpoint}", params=params)
            if src_resp.status_code != 200:
                raise RuntimeError(f"sources HTTP {src_resp.status_code}")
            if src_resp.text.lstrip().startswith("{"):
                raise RuntimeError(f"sources error: {src_resp.text[:80]!r}")
            return decrypt_sources(src_resp.text, seed, int(tmdb_id))
        except Exception as exc:
            last_err = exc
            logger.debug(
                f"cineby {endpoint} fetch attempt {attempt + 1}/{attempts} failed: {exc}"
            )
            if attempt + 1 < attempts:
                time.sleep(1.0 * (attempt + 1))
    logger.debug(
        f"cineby {endpoint} sources unavailable for tmdb {tmdb_id}: {last_err}"
    )
    return None


def _hls_master_from_sources(sources):
    """Return the HLS master URL from a decrypted sources list, or None.

    Prefers an explicit ``type == "hls"`` source (the multi-audio servers tag
    them); falls back to any ``.m3u8`` URL. DASH (``.mpd``) is skipped — the
    downloader only speaks HLS.
    """
    for src in sources or []:
        if (src.get("type") or "").lower() == "hls" and src.get("url"):
            return src["url"]
    for src in sources or []:
        url = src.get("url") or ""
        if ".m3u8" in url:
            return url
    return None


def _german_master_url(
    media_type, tmdb_id, title, year, imdb_id, season, episode, endpoint
):
    """Freshly resolve the German-carrying server's HLS master URL (or None)."""
    data = _fetch_decrypted_sources(
        endpoint, media_type, tmdb_id, title, year, imdb_id, season, episode
    )
    if not data:
        return None
    return _hls_master_from_sources(data.get("sources"))


def detect_audio_languages(
    media_type, tmdb_id, title, year, imdb_id, season, episode, probe=True
):
    """Probe cineby's servers for the audio languages available for a title.

    English (the original, muxed audio) is always offered — that's how cineby
    plays by default. The extra servers are scanned for a German audio rendition
    (matched exactly as the HLS downloader will match it); the first server that
    has one is remembered so the download can go straight to it. Result is cached
    per episode. Returns ``{"labels": [...], "german_server": <endpoint|None>}``.

    ``probe=False`` returns the cached result if present, otherwise an
    English-only answer *without* touching the network or caching it — used on
    the episode-listing hot path so the several-request scan never blocks the
    list from rendering (the language dropdown probes for real separately).
    """
    # Availability (and which server carries German) is a title-level property,
    # stable across episodes, so cache it per title — the season/episode passed
    # only pick which episode gets probed. The German URL itself is never cached;
    # stream_url re-resolves it fresh per episode (its token expires).
    key = (media_type, str(tmdb_id))
    if key in _LANG_DETECT_CACHE:
        return _LANG_DETECT_CACHE[key]
    if not probe:
        return {"labels": [ENGLISH_LABEL], "german_server": None}

    from ..common.hls import rendition_languages

    labels = [ENGLISH_LABEL]
    german_server = None
    for endpoint in CINEBY_EXTRA_SERVERS:
        data = _fetch_decrypted_sources(
            endpoint, media_type, tmdb_id, title, year, imdb_id, season, episode
        )
        if not data:
            continue
        master = _hls_master_from_sources(data.get("sources"))
        if not master:
            continue
        try:
            text = _fetch(master).text
        except Exception as exc:
            logger.debug(f"cineby manifest fetch failed for {endpoint}: {exc}")
            continue
        if not text.lstrip().startswith("#EXTM3U"):
            continue
        if "deu" in rendition_languages(text, master):
            labels.append(GERMAN_LABEL)
            german_server = endpoint
            break

    result = {"labels": labels, "german_server": german_server}
    _LANG_DETECT_CACHE[key] = result
    return result


_TMDB_HEADERS = {
    "Accept-Encoding": "gzip, deflate",
    "Origin": CINEBY_BASE,
    "Referer": f"{CINEBY_BASE}/",
}


def tmdb_get(path):
    """GET a TMDB proxy path and return parsed JSON (or {}).

    Uses the same curl_cffi path as the source API: db.wingsdatabase.com is
    behind the same Cloudflare gate, so a plain session can come back empty in a
    container and leave the stream lookup with no title/year to send.
    """
    sep = "&" if "?" in path else "?"
    url = f"{TMDB_PROXY}{path}{sep}language=en-US"
    try:
        resp = _fetch(url)
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
    path = re.sub(r"^https?://[^/]+", "", url)
    # Drop any query string / fragment before splitting: season URLs carry the
    # number as ``?s=<n>`` (see cineby_season_url), and leaving it attached would
    # glue it onto the tmdb id (e.g. ``125988?s=2``), making every downstream
    # TMDB path malformed so no episodes come back.
    path = path.split("#", 1)[0].split("?", 1)[0].strip("/")
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
        self.__lang_detect = None

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
            base = (
                cineby_movie_url(self.tmdb_id)
                if self.is_movie
                else cineby_tv_url(self.tmdb_id)
            )
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
        # cineby's default (cdn) stream carries the original audio, labelled
        # "English Dub"; German is offered only for titles that actually have a
        # German audio rendition (see available_language_labels).
        return self.__selected_language_param or ENGLISH_LABEL

    @selected_language.setter
    def selected_language(self, value):
        self.__selected_language_param = value or None
        self.__stream_url = None  # re-resolve for the newly selected language

    # ---- language detection -------------------------------------------------
    def _detect_languages(self):
        """Cached per-episode probe of which dub languages cineby has."""
        if self.__lang_detect is None:
            meta = self._meta or {}
            title = meta.get("title") or meta.get("name") or self.title
            year = _year(meta.get("release_date") or meta.get("first_air_date"))
            imdb = meta.get("imdb_id") or ""
            season = 1 if self.is_movie else self.season_number
            episode = 1 if self.is_movie else self.episode_number
            try:
                self.__lang_detect = detect_audio_languages(
                    self.media_type, self.tmdb_id, title, year, imdb, season, episode
                )
            except Exception as exc:
                logger.debug(f"cineby language detection failed: {exc}")
                self.__lang_detect = {"labels": [ENGLISH_LABEL], "german_server": None}
        return self.__lang_detect

    @property
    def available_language_labels(self):
        return self._detect_languages().get("labels", [ENGLISH_LABEL])

    @property
    def _wants_german(self):
        return self.selected_language == GERMAN_LABEL

    @property
    def _separate_audio_rendition(self):
        # German audio lives as a standalone rendition inside a multi-audio HLS
        # master, so the shared download() must select it rather than take the
        # muxed default. English (the default) never needs this.
        return self._wants_german

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
        labels = self.available_language_labels
        data = {(Audio.ENGLISH, Subtitles.NONE): {"Cineby": self.url}}
        if GERMAN_LABEL in labels:
            data[(Audio.GERMAN, Subtitles.NONE)] = {"Cineby": self.url}
        return data

    def provider_link(self, language=None, provider=None):
        return self.url

    def available_providers(self, language=None):
        return ("Cineby",)

    @property
    def stream_url(self):
        if self.__stream_url is None:
            meta = self._meta or {}
            title = meta.get("title") or meta.get("name") or self.title
            year = _year(meta.get("release_date") or meta.get("first_air_date"))
            imdb = meta.get("imdb_id") or ""
            season = 1 if self.is_movie else self.season_number
            episode = 1 if self.is_movie else self.episode_number

            # German audio comes from a different server than the default one,
            # as a separate rendition inside its HLS master. Resolve that master
            # fresh (its URL carries a short-lived token) from the server that
            # detection found German on; fail clearly if none has it.
            if self._wants_german:
                german_server = self._detect_languages().get("german_server")
                if not german_server:
                    raise RuntimeError(
                        f"cineby: no German audio available for '{self.title}'."
                    )
                master = _german_master_url(
                    self.media_type,
                    self.tmdb_id,
                    title,
                    year,
                    imdb,
                    season,
                    episode,
                    german_server,
                )
                if not master:
                    raise RuntimeError(
                        f"cineby: could not resolve the German stream for "
                        f"'{self.title}' (server {german_server} unreachable)."
                    )
                self.__stream_url = master
                return self.__stream_url

            m3u8 = None

            # Preferred: resolve straight from cineby's source API and decrypt
            # it — no browser, so it can't be defeated by a flaky headless run.
            try:
                m3u8 = resolve_stream_via_api(
                    self.media_type, self.tmdb_id, title, year, imdb, season, episode
                )
            except Exception as exc:
                logger.debug(f"cineby API resolve error: {exc}")

            # Fallback: capture the m3u8 from the headless vidking player.
            if not m3u8:
                from ...playwright.captcha import playwright_get_cineby_stream_url

                embed = vidking_embed_url(
                    self.is_movie, self.tmdb_id, self.season_number, self.episode_number
                )
                m3u8 = playwright_get_cineby_stream_url(embed)

            if not m3u8:
                # A common reason there's no playlist is simply that the title
                # isn't out yet — say so instead of blaming the browser.
                meta = self._meta or {}
                status = (meta.get("status") or "").lower()
                release = meta.get("release_date") or meta.get("first_air_date") or ""
                if status and status != "released":
                    raise RuntimeError(
                        f"cineby: no stream yet for '{self.title}' — it isn't "
                        f"released ({status}, {release or 'date unknown'})."
                    )
                raise RuntimeError(
                    f"cineby: could not resolve a stream for {self.url} "
                    "(source API and headless browser both failed)."
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


class CinebySeason:
    def __init__(
        self, url, series=None, season_number=None, are_movies=None, tmdb_id=None
    ):
        self.url = url
        self._series = series
        media_type, url_tmdb, _, _ = parse_cineby_url(url)
        self.tmdb_id = tmdb_id or url_tmdb
        self.are_movies = (
            are_movies if are_movies is not None else (media_type == "movie")
        )
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
        # Availability is a per-title property (German either exists for the show
        # or it doesn't), so defer to the series-level probe instead of testing
        # every season — see CinebySeries.available_language_labels.
        try:
            return list(self.series.available_language_labels)
        except Exception as exc:
            logger.debug(f"cineby season language labels failed: {exc}")
            return [ENGLISH_LABEL]

    def download(self):
        # One failed episode must not abandon the rest of the batch.
        run_each(self.episodes, "download")

    def watch(self):
        # One failed episode must not abandon the rest of the batch.
        run_each(self.episodes, "watch")

    def syncplay(self):
        # One failed episode must not abandon the rest of the batch.
        run_each(self.episodes, "syncplay")


class CinebySeries:
    def __init__(self, url):
        self.url = url
        media_type, tmdb_id, _, _ = parse_cineby_url(url)
        self.media_type = media_type or "movie"
        self.tmdb_id = tmdb_id
        self.is_movie = self.media_type == "movie"
        self.__meta = None
        self.__seasons = None
        self.__lang_labels = None

    @property
    def _meta(self):
        if self.__meta is None:
            if self.is_movie:
                self.__meta = tmdb_get(f"/movie/{self.tmdb_id}") or {}
            else:
                self.__meta = tmdb_get(f"/tv/{self.tmdb_id}") or {}
        return self.__meta

    @property
    def available_language_labels(self):
        """Dub labels offered for this title (English always; German if present).

        Cache-only: reports German once the per-title probe (run by the language
        dropdown via ``/api/providers``) has cached its result, but never probes
        itself — it feeds the episode-listing badges, which must not block on a
        multi-request server scan. So on a series' first open the badges read
        English-only and gain German after the dropdown loads.
        """
        if self.__lang_labels is None:
            meta = self._meta or {}
            title = meta.get("title") or meta.get("name") or self.title
            year = _year(meta.get("release_date") or meta.get("first_air_date"))
            imdb = meta.get("imdb_id") or ""
            detected = detect_audio_languages(
                self.media_type, self.tmdb_id, title, year, imdb, 1, 1, probe=False
            )
            self.__lang_labels = detected.get("labels", [ENGLISH_LABEL])
        return self.__lang_labels

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
