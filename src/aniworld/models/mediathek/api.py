"""Client for the MediathekViewWeb API (https://mediathekviewweb.de).

MediathekView indexes the public-service broadcasters' own media libraries
(ARD, ZDF, Arte, 3sat, ORF, SRF, ...) and lists the broadcasters' direct
download links for each programme. Nothing is scraped or re-hosted here: every
stream comes straight from the broadcaster's CDN.

API reference: https://github.com/mediathekview/mediathekviewweb/blob/master/README.md
"""

import json
import re
import subprocess
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from html import unescape
from urllib.parse import parse_qs, quote, unquote, urldefrag, urlencode

try:
    from ...config import DEFAULT_USER_AGENT, GLOBAL_SESSION, logger
except ImportError:
    from aniworld.config import DEFAULT_USER_AGENT, GLOBAL_SESSION, logger

try:
    from zoneinfo import ZoneInfo

    _BROADCAST_TZ = ZoneInfo("Europe/Berlin")
except Exception:  # no tz database (bare Windows without tzdata)
    _BROADCAST_TZ = UTC

API_URL = "https://mediathekviewweb.de/api/query"
# The API returns at most this many results per query.
_API_MAX_SIZE = 1000
SITE_URL = "https://mediathekviewweb.de/"

# Every channel MediathekView indexes, by its own channel name. Matched
# exactly: its full-text search would otherwise let "ARD" pull in "ARD-alpha"
# and "SR" pull in "SRF".
CHANNELS = (
    # ARD and its regional broadcasters
    "ARD",
    "ARD-alpha",
    "ONE",
    "tagesschau24",
    "BR",
    "HR",
    "MDR",
    "NDR",
    "Radio Bremen TV",
    "RBB",
    "SR",
    "SWR",
    "WDR",
    # ZDF family
    "ZDF",
    "ZDFinfo",
    "ZDFneo",
    "ZDF-tivi",
    # Joint and international channels
    "3Sat",
    "ARTE.DE",
    "ARTE.EN",
    "ARTE.ES",
    "ARTE.FR",
    "ARTE.IT",
    "ARTE.PL",
    "KiKA",
    "PHOENIX",
    "Funk.net",
    "DW",
    "ORF",
    "SRF",
)

# The language a channel broadcasts in, where it isn't German (ISO 639-1).
CHANNEL_LANGUAGES = {
    "ARTE.EN": "en",
    "ARTE.ES": "es",
    "ARTE.FR": "fr",
    "ARTE.IT": "it",
    "ARTE.PL": "pl",
}

# Arte names the version of a programme in every stream link:
#   VA / VF      German / French version          VOA / VOF   original German / French
#   VE[ANG]      version in English (ESP, ITA, POL likewise)
#   VO           original in another language     AUD suffix  audio description
#   -STA, -STE[ITA] ...  subtitles burnt into the picture
# so Arte (IT) mostly carries French audio with Italian subtitles.
_ARTE_VERSION = re.compile(
    r"[/_](VOA|VOF|VA|VF|VO|VE(?:%5B|\[)([A-Z]{3})(?:%5D|\]))(?:AUD)?(?=[-_/])"
)
_ARTE_AUDIO = {"VA": "deu", "VOA": "deu", "VF": "fra", "VOF": "fra", "VO": "und"}
_ISO_639_2 = {
    "de": "deu",
    "fr": "fra",
    "en": "eng",
    "es": "spa",
    "it": "ita",
    "pl": "pol",
}
_ARTE_LANGUAGE_SEGMENT = re.compile(r"/Generate/[^/]+/(de|fr|en|es|it|pl)/")
_ARTE_LANGUAGES = {
    "ALL": "deu",
    "ANG": "eng",
    "ESP": "spa",
    "FRA": "fra",
    "ITA": "ita",
    "POL": "pol",
}
# ISO 639-2 code -> the short label shown on an episode.
AUDIO_BADGES = {
    "deu": "DE",
    "fra": "FR",
    "eng": "EN",
    "spa": "ES",
    "ita": "IT",
    "pol": "PL",
    "und": "OV",
}


def audio_language(entry):
    """ISO 639-2 code of a programme's audio ("deu", "fra", ... "und").

    Arte's links name the version; every other channel broadcasts in German.
    """
    channel = entry.get("channel") or ""
    if not channel.startswith("ARTE."):
        return "deu"
    for url in video_urls(entry).values():
        match = _ARTE_VERSION.search(url)
        if match:
            code, language = match.groups()
            if language:
                return _ARTE_LANGUAGES.get(language, "und")
            return _ARTE_AUDIO[code]
        # Some manifests name just the language: ".../Generate/<id>/de/..."
        match = _ARTE_LANGUAGE_SEGMENT.search(url)
        if match:
            return _ISO_639_2[match.group(1)]
    return "und"


# Pages the broadcasters host their programmes on, i.e. every `url_website`
# the channels above report. ARD's regional broadcasters, ONE, ARD-alpha and
# funk all publish through ardmediathek.de.
WEBSITE_HOST_PATTERN = (
    r"(?:www\.)?(?:ardmediathek\.de|zdf\.de|zdfheute\.de|arte\.tv|3sat\.de"
    r"|on\.orf\.at|srf\.ch|kika\.de|phoenix\.de|sr-mediathek\.de|p\.dw\.com)"
)
MEDIATHEK_EPISODE_PATTERN = re.compile(rf"^https?://{WEBSITE_HOST_PATTERN}/.+")

# A show (one topic on one channel) lives at a mediathekviewweb.de search URL,
# which opens the same search on the site itself. The channel and topic ride
# along verbatim so nothing depends on parsing the site's query syntax.
_SHOW_BASE = r"^https?://(?:www\.)?mediathekviewweb\.de/?#"
# The lookaheads start right after the "#": a parameter is either the first
# one there, or follows an "&". Order doesn't matter.
_PARAM = r"(?:.*&)?"
MEDIATHEK_SERIES_PATTERN = re.compile(
    rf"{_SHOW_BASE}(?!{_PARAM}season=)(?={_PARAM}topic=)(?={_PARAM}channel=).+"
)
MEDIATHEK_SEASON_PATTERN = re.compile(
    rf"{_SHOW_BASE}(?={_PARAM}topic=)(?={_PARAM}channel=)(?={_PARAM}season=\d+).+"
)

# Fragment that pins one MediathekView entry when a page carries several
# (e.g. a regular cut and an audio-described one share one url_website).
_ID_FRAGMENT = "mvid="

# Alternative versions get their own entry under the same page and episode
# number. A page URL or a show listing means the regular version.
_VARIANT_MARKERS = (
    "audiodeskription",
    "hörfassung",
    "gebärdensprache",
    "originalversion",
    "(ad)",
    "(dgs)",
    "(ov)",
)

# Season/episode markers the broadcasters put into titles:
#   "Folge 1009: Mein freier Wille (S26/E04)"           (ARD, ZDF, 3sat)
#   "S Geburtstagsfescht – (Staffel 1, Folge 12)"       (SRF)
_EPISODE_MARKERS = (
    re.compile(r"\(\s*S\s*(\d{1,4})\s*/\s*E\s*(\d{1,4})\s*\)", re.IGNORECASE),
    re.compile(r"\(\s*Staffel\s*(\d{1,4})\s*,\s*Folge\s*(\d{1,4})\s*\)", re.IGNORECASE),
)

# ORF files each season as a topic of its own and numbers the episode within
# it: topic "Soko Kitzbühel Staffel 2", title "Soko Kitzbühel (7/12): Farben
# des Todes" is S02E07. "(n/m)" only counts under such a topic; elsewhere it
# numbers the parts of a mini-series.
_TOPIC_SEASON = re.compile(r"^(.*?)\s*[-–]?\s*Staffel\s+(\d{1,3})\s*$", re.IGNORECASE)
_PART_OF = re.compile(r"\(\s*(\d{1,3})\s*/\s*\d{1,3}\s*\)")


def show_name(topic):
    """The show a topic belongs to: "Soko Donau Staffel 11" -> "Soko Donau"."""
    topic = (topic or "").strip()
    match = _TOPIC_SEASON.match(topic)
    return match.group(1).strip() if match and match.group(1).strip() else topic


def topic_season(topic):
    """The season a topic names ("... Staffel 11" -> 11), else None."""
    match = _TOPIC_SEASON.match((topic or "").strip())
    return int(match.group(2)) if match and match.group(1).strip() else None


QUALITIES = ("hd", "sd", "low")
_QUALITY_FIELDS = {"hd": "url_video_hd", "sd": "url_video", "low": "url_video_low"}

# Listing a show and loading its cover hit the same queries within seconds
# (search card, then the opened dialog, then the download). Keep answers for a
# few minutes instead of asking again.
_CACHE_TTL = 300
_CACHE_SIZE = 256
_cache = {}
_cache_lock = threading.Lock()


class MediathekError(RuntimeError):
    """The API refused the query or answered with something unreadable."""


def _cached(key, fetch, ttl=_CACHE_TTL):
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < hit[2]:
            return hit[1]
    value = fetch()
    with _cache_lock:
        if len(_cache) >= _CACHE_SIZE:
            _cache.pop(next(iter(_cache)))
        _cache[key] = (now, value, ttl)
    return value


def clear_cache():
    with _cache_lock:
        _cache.clear()


def _post(body, timeout=20):
    response = GLOBAL_SESSION.post(
        API_URL,
        # The API reads a JSON body but expects it as text/plain.
        data=json.dumps(body),
        headers={
            "Content-Type": "text/plain",
            "Accept": "application/json",
            # niquests can't decode Brotli without the optional package.
            "Accept-Encoding": "gzip, deflate",
            "Referer": SITE_URL,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as exc:
        raise MediathekError("MediathekView returned invalid JSON") from exc
    if payload.get("err"):
        raise MediathekError(f"MediathekView query failed: {payload['err']}")
    return (payload.get("result") or {}).get("results") or []


def _query(body):
    key = json.dumps(body, sort_keys=True)
    return list(_cached(("query", key), lambda: _post(body)))


def _allowed(entry, channels):
    return entry.get("channel") in channels


# -----------------------------
# Searching
# -----------------------------


def search(keyword, *, channels=CHANNELS, limit=50):
    """Newest programmes whose topic or title matches `keyword`."""
    keyword = (keyword or "").strip()
    if not keyword or limit == 0:
        return []
    # The API cannot OR channels together, so over-fetch and filter here.
    results = _query(
        {
            "queries": [{"fields": ["title", "topic"], "query": keyword}],
            "sortBy": "timestamp",
            "sortOrder": "desc",
            "future": False,
            "offset": 0,
            "size": _API_MAX_SIZE
            if limit is None
            else min(max(limit * 3, 50), _API_MAX_SIZE),
        }
    )
    hits = [entry for entry in results if _allowed(entry, channels)]
    return hits[:limit] if limit is not None else hits


def search_shows(keyword, *, channels=CHANNELS, limit=30):
    """Shows (topic on a channel) with programmes matching `keyword`.

    Each show comes with its newest matching entry. Shows named after the
    keyword come first, then those where only an episode title matched, each
    group newest first.

    Arte files everything under category topics, so there an Arte series is
    the show ("name"), or the programme itself when it stands alone ("family").
    """
    shows = _shows_from(search(keyword, channels=channels, limit=300), limit)
    wanted = _normalize_name(keyword)
    return sorted(
        shows,
        key=lambda show: (
            wanted not in _normalize_name(show.get("name") or show["topic"])
        ),
    )


def _shows_from(entries, limit):
    """Group entries into shows, each with its first (newest) entry."""
    shows = {}
    for entry in entries:
        family = arte_family(entry)
        if family:
            category = (entry.get("topic") or "").strip()
            name = arte_series_name(entry)
            standalone = family[1] == 0
            key = (entry["channel"], "arte", family[0] if standalone else name.lower())
            if key not in shows:
                shows[key] = {
                    "channel": entry["channel"],
                    "topic": category,
                    "family": family[0] if standalone else None,
                    "name": name,
                    "newest": entry,
                }
        else:
            # Season topics ("... Staffel 2") join their show.
            topic = show_name(entry.get("topic"))
            if not topic:
                continue
            key = (entry["channel"], topic.lower())
            if key not in shows:
                shows[key] = {
                    "channel": entry["channel"],
                    "topic": topic,
                    "newest": entry,
                }
        if limit is not None and len(shows) >= limit:
            break
    return list(shows.values())


# -----------------------------
# Browsing
# -----------------------------

# Rows on the home page. MediathekView knows no popularity, but it knows
# what is new: the latest page of programmes, all channels.
_NEW_EPISODE_MIN = 15 * 60  # series episodes, not their clips
_NEW_PROGRAMME_MIN = 40 * 60  # films, documentaries, features; not the news


def newest_shows(kind, *, channels=CHANNELS, limit=18):
    """Shows with something new: "episodes" or "programmes".

    episodes:    series whose newest numbered episode just aired
    programmes:  new programmes of 40 minutes and more without episode
                 numbers (films, documentaries, features)

    Only German versions count, so a show isn't listed for its sign language
    edition alone, nor an Arte programme once per language; the others are
    a pick in the series dialog's language menu.
    """
    from . import versions

    results = _query(
        {
            "queries": [],
            "sortBy": "timestamp",
            "sortOrder": "desc",
            "future": False,
            "offset": 0,
            "size": _API_MAX_SIZE,
        }
    )
    wanted = []
    for entry in results:
        if not _allowed(entry, channels) or is_trailer(entry):
            continue
        if versions.label(entry) != versions.DEFAULT_LABEL:
            continue
        duration = int(entry.get("duration") or 0)
        numbered = episode_marker(entry)[0] is not None
        if kind == "episodes":
            fits = numbered and duration >= _NEW_EPISODE_MIN
        else:
            fits = not numbered and duration >= _NEW_PROGRAMME_MIN
        if fits:
            wanted.append(entry)
    return _shows_from(wanted, limit)


def show_entries(channel, topic, *, family=None, series=None, include_variants=False):
    """Every programme of one show that MediathekView currently lists.

    Includes its season topics ("Soko Kitzbühel Staffel 1", "... Staffel 2").
    Out of an Arte category topic, `family` keeps one standalone programme
    and `series` the episodes of one named series, every season of it.
    """
    results = _query(
        {
            "queries": [
                {"fields": ["topic"], "query": topic},
                {"fields": ["channel"], "query": channel},
            ],
            "sortBy": "timestamp",
            "sortOrder": "desc",
            "future": False,
            "offset": 0,
            "size": 1000,
        }
    )
    wanted = show_name(topic).lower()
    entries = [
        entry
        for entry in results
        if entry.get("channel") == channel
        and show_name(entry.get("topic")).lower() == wanted
        and video_urls(entry)
        and not is_trailer(entry)
        and (family is None or (arte_family(entry) or (None,))[0] == family)
        and (series is None or _in_arte_series(entry, series))
    ]
    return entries if include_variants else _drop_duplicate_variants(entries)


def _in_arte_series(entry, name):
    family = arte_family(entry)
    return bool(family and family[1]) and arte_series_name(entry) == name


# -----------------------------
# Arte series
# -----------------------------

# Arte numbers programmes "<family>-<episode>-<version>", e.g. 094414-008-A is
# episode 8 of the series 094414; a standalone programme is episode 000.
_ARTE_PROGRAMME = re.compile(r"arte\.tv/[a-z]{2}/videos/(\d{6})-(\d{3})-[A-Z]")


def arte_family(entry):
    """(family id, episode number) of an Arte programme, else None."""
    if not (entry.get("channel") or "").startswith("ARTE."):
        return None
    match = _ARTE_PROGRAMME.search(entry.get("url_website") or "")
    if not match:
        return None
    return match.group(1), int(match.group(2))


def arte_series_name(entry):
    """The series an Arte programme belongs to, named as Arte titles it.

    The name is the part every episode title shares: "Impulse - Chaostheorie"
    and "Impulse - Vererbung" are "Impulse"; Arte (IT) puts it last
    ("Eredità: è tutta genetica - Eureka!") and that works the same. A
    standalone programme is named by its own title.
    """
    family = arte_family(entry)
    title = _strip_version_note(entry.get("title") or "")
    if not family or family[1] == 0:
        return title
    names = _arte_families(entry["channel"], entry.get("topic") or "")
    return names.get(family[0]) or title


def arte_season(entry):
    """The season of an Arte series episode.

    Arte gives every season of a series its own family id ("Impulse" is
    094414 and 111706); the families sharing a name count up in id order.
    """
    family = arte_family(entry)
    if not family or family[1] == 0:
        return None
    names = _arte_families(entry["channel"], entry.get("topic") or "")
    name = names.get(family[0])
    if not name:
        return 1
    seasons = sorted(fid for fid, other in names.items() if other == name)
    return seasons.index(family[0]) + 1


def _arte_families(channel, category):
    """{family id: series name} for the Arte series in one category topic."""
    return _cached(
        ("arte-families", channel, category),
        lambda: _name_arte_families(channel, category),
    )


def _name_arte_families(channel, category):
    titles = {}
    for entry in show_entries(channel, category, include_variants=True):
        family = arte_family(entry)
        if family and family[1]:
            title = _strip_version_note(entry.get("title") or "")
            titles.setdefault(family[0], []).append(title)
    return {fid: _common_series_name(found) for fid, found in titles.items()}


def _strip_version_note(title):
    # "... (Originalversion mit Untertitel)", "... (mit Untertitel)" and the like
    return re.sub(
        r"\s*\((?:Originalversion\s+)?mit\s+Untertitel\)\s*$", "", title
    ).strip()


def _common_series_name(titles):
    titles = [t for t in dict.fromkeys(titles) if t]
    if len(titles) < 2:
        return None
    # A " - " segment every title carries, wherever it sits.
    segments = [{part.strip() for part in t.split(" - ")} for t in titles]
    shared = set.intersection(*segments)
    if shared:
        return min(shared, key=len)
    # Otherwise the words they all start with ("Bitte nicht anfassen! ...").
    words = [t.split() for t in titles]
    common = []
    for column in zip(*words):
        if len(set(column)) != 1:
            break
        common.append(column[0])
    name = " ".join(common).rstrip(" :-–")
    return name if len(name) >= 3 else None


def is_trailer(entry):
    # Previews of upcoming episodes, listed under the show like an episode.
    return "trailer" in (entry.get("title") or "").lower()


def _drop_duplicate_variants(entries):
    """Keep one version per episode, the regular one where there is one."""
    chosen = {}
    for entry in entries:
        key = _episode_key(entry)
        current = chosen.get(key)
        if current is None or (is_variant(current) and not is_variant(entry)):
            chosen[key] = entry
    kept = {id(entry) for entry in chosen.values()}
    return [entry for entry in entries if id(entry) in kept]


def _episode_key(entry):
    season, episode = episode_marker(entry)
    if season is not None:
        return ("numbered", season, episode)
    return ("page", entry.get("url_website") or entry.get("id"))


def lookup(page_url, *, channels=CHANNELS):
    """Every entry MediathekView lists for one broadcaster page."""
    page, entry_id = split_url(page_url)
    # The query only matches the page exactly as the broadcaster wrote it, and
    # URL normalising drops a trailing slash Arte keeps: try both spellings.
    other = page[:-1] if page.endswith("/") else page + "/"
    entries = []
    for candidate in (page, other):
        results = _query(
            {
                "queries": [{"fields": ["url_website"], "query": candidate}],
                "future": True,
                "offset": 0,
                "size": 50,
            }
        )
        # The field is full-text indexed, so similar pages come back too.
        entries = [
            entry
            for entry in results
            if _same_page(entry.get("url_website"), page) and _allowed(entry, channels)
        ]
        if entries:
            break
    logger.debug("MediathekView lookup %s -> %d entries", page, len(entries))
    return entries, entry_id


def pick_entry(entries, entry_id=None):
    """The entry a URL refers to: the pinned one, else the regular version."""
    if not entries:
        return None
    if entry_id:
        for entry in entries:
            if entry.get("id") == entry_id:
                return entry
    regular = [entry for entry in entries if not is_variant(entry)]
    return (regular or entries)[0]


def is_variant(entry):
    title = (entry.get("title") or "").lower()
    return any(marker in title for marker in _VARIANT_MARKERS)


# -----------------------------
# URLs
# -----------------------------


def entry_url(entry):
    """Stable URL for one entry: the broadcaster page plus the entry id."""
    page = entry.get("url_website") or ""
    entry_id = entry.get("id")
    if not entry_id:
        return page
    return f"{page}#{_ID_FRAGMENT}{quote(entry_id, safe='')}"


def split_url(url):
    page, fragment = urldefrag(url or "")
    entry_id = None
    if fragment.startswith(_ID_FRAGMENT):
        entry_id = unquote(fragment[len(_ID_FRAGMENT) :]) or None
    return page, entry_id


def show_url(channel, topic, season=None, *, family=None, name=None):
    """mediathekviewweb.de link for a show, optionally narrowed to a season.

    An Arte series also carries its family id and name: Arte files it under a
    category topic ("Wissenschaft - Technik und Innovation") shared with
    everything else of that kind.
    """
    # The site's own search syntax: "!channel #topic" or "+title", words
    # joined by commas.
    if name:
        site_query = f"!{channel.lower()} +{','.join(name.lower().split())}"
    else:
        site_query = f"!{channel.lower()} #{','.join(topic.lower().split())}"
    params = {"query": site_query, "channel": channel, "topic": topic}
    if family:
        params["family"] = family
    if name:
        params["name"] = name
    if season is not None:
        params["season"] = str(season)
    return SITE_URL + "#" + urlencode(params, quote_via=quote)


def _show_params(url):
    _, fragment = urldefrag(url or "")
    return parse_qs(fragment, keep_blank_values=True)


def parse_show_url(url):
    """(channel, topic, season or None) from a show_url() link."""
    params = _show_params(url)
    channel = (params.get("channel") or [""])[0].strip()
    topic = (params.get("topic") or [""])[0].strip()
    if not channel or not topic:
        raise ValueError(f"Not a Mediathek show URL: {url}")
    season = (params.get("season") or [""])[0].strip()
    return channel, topic, int(season) if season.isdigit() else None


def show_series(url):
    """(family id, name) of an Arte series link, else (None, None)."""
    params = _show_params(url)
    family = (params.get("family") or [""])[0].strip() or None
    name = (params.get("name") or [""])[0].strip() or None
    return family, name


def _same_page(candidate, page):
    def norm(value):
        value = (value or "").strip().rstrip("/")
        return re.sub(r"^https?://(?:www\.)?", "", value).lower()

    return bool(candidate) and norm(candidate) == norm(page)


# -----------------------------
# Entry details
# -----------------------------


def episode_marker(entry):
    """(season, episode) when the title carries a marker, else (None, None)."""
    title = entry.get("title") or ""
    for pattern in _EPISODE_MARKERS:
        match = pattern.search(title)
        if match:
            season, episode = int(match.group(1)), int(match.group(2))
            if episode > 0:
                return season, episode
    season = topic_season(entry.get("topic"))
    if season is not None:
        match = _PART_OF.search(title)
        if match and int(match.group(1)) > 0:
            return season, int(match.group(1))
    # Arte series number their episodes in the programme id.
    family = arte_family(entry)
    if family and family[1] > 0:
        return arte_season(entry), family[1]
    return None, None


def show_label(entry):
    """The show an entry belongs to, as listed and as its folder is named."""
    if arte_family(entry):
        return arte_series_name(entry)
    return show_name(entry.get("topic"))


def episode_title(entry):
    """The title without the show name and the season/episode marker."""
    title = (entry.get("title") or "").strip()
    for pattern in _EPISODE_MARKERS:
        title = pattern.sub("", title)
    if topic_season(entry.get("topic")) is not None:
        title = _PART_OF.sub("", title, count=1)
    family = arte_family(entry)
    if family and family[1] > 0:
        # "Impulse - Chaostheorie: ..." lists as "Chaostheorie: ..."
        name = arte_series_name(entry)
        title = _strip_version_note(title)
        parts = [p for p in title.split(" - ") if p.strip() != name]
        title = " - ".join(parts) or title
    topic = show_name(entry.get("topic"))
    if topic and title.lower().startswith(topic.lower()):
        rest = title[len(topic) :].lstrip(" :–-·|")
        title = rest or title
    title = re.sub(r"\s+", " ", title).strip(" –-·|:")
    return title or topic


# -----------------------------
# Geo restrictions
# -----------------------------

# ORF marks programmes it may only show in Austria in their links, and outside
# Austria redirects their playlists to a notice ("Dieses Video darf aus
# rechtlichen Gründen nur in Österreich wiedergegeben werden").
_GEO_MARKERS = {"cms-austria": "AT"}
_GEO_NOTICE = "geoprotection"


def geo_restriction(entry):
    """The one country a programme is licensed for ("AT"), else None."""
    for url in video_urls(entry).values():
        for marker, country in _GEO_MARKERS.items():
            if marker in url:
                return country
    return None


def geo_blocked(url):
    """Whether the broadcaster answers `url` with its geo-block notice here."""
    try:
        response = GLOBAL_SESSION.get(
            url,
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept-Encoding": "gzip, deflate",
            },
            timeout=15,
            stream=True,
        )
        final = str(response.url or "")
        response.close()
    except Exception as exc:
        logger.debug("Geo check failed for %s: %s", url, exc)
        return False
    return _GEO_NOTICE in final.lower()


def video_urls(entry):
    """{quality: url} for the qualities this entry actually offers."""
    return {
        quality: entry[field]
        for quality, field in _QUALITY_FIELDS.items()
        if isinstance(entry.get(field), str) and entry[field].startswith("http")
    }


def best_video_url(entry, preferred="hd"):
    """The preferred quality, falling back to the next lower, then any."""
    urls = video_urls(entry)
    preferred = preferred if preferred in QUALITIES else "hd"
    order = QUALITIES[QUALITIES.index(preferred) :] + QUALITIES
    for quality in order:
        if quality in urls:
            return urls[quality]
    return None


# -----------------------------
# Resolutions
# -----------------------------

# The links name their resolution in a dozen ways ("1920x1080", "_HD",
# "p37", "chunklist_b6100000"), and "hd" is 720p on some channels, so the
# streams are asked directly. FFmpeg only reads the header, about a second.
_VIDEO_HEIGHT = re.compile(r"Video:.*?\b\d{2,5}x(\d{2,5})\b")
_RESOLUTION_TTL = 24 * 3600
# A stream header comes back in about a second; a hanging CDN shouldn't hold
# the series dialog's request for long.
_PROBE_TIMEOUT = 10


def stream_height(url):
    """The video height of a stream (1080 for 1080p).

    0 when the broadcaster no longer serves it, None when it can't be told.
    """
    if not url:
        return None
    try:
        return _cached(("height", url), lambda: _known_height(url), ttl=_RESOLUTION_TTL)
    except _UnknownHeight:
        # Not cached: a slow or failed probe may well work next time.
        return None


class _UnknownHeight(Exception):
    pass


def _known_height(url):
    height = _probe_height(url)
    if height is None:
        raise _UnknownHeight(url)
    return height


def _probe_height(url):
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-user_agent", DEFAULT_USER_AGENT, "-i", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_PROBE_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.debug("Resolution probe failed for %s: %s", url, exc)
        return None
    heights = [int(h) for h in _VIDEO_HEIGHT.findall(result.stderr or "")]
    if heights:
        # A master playlist lists every rendition; FFmpeg takes the best.
        return max(heights)
    if re.search(r"\b(?:403|404|410)\b", result.stderr or ""):
        return 0
    return None


def quality_options(entry):
    """[{"value": "hd", "height": 1080, "label": "1080p"}, ...] for one entry.

    Qualities the broadcaster no longer serves are left out; ones whose
    resolution can't be read keep a generic label. Two qualities of the same
    resolution are listed once, as the better one. A programme that is
    geo-blocked here gives no options: its streams are the block notice.
    """
    urls = video_urls(entry)
    if geo_restriction(entry) and urls and geo_blocked(next(iter(urls.values()))):
        return []
    with ThreadPoolExecutor(max_workers=3) as pool:
        heights = dict(zip(urls, pool.map(stream_height, urls.values())))
    options = []
    seen = set()
    for quality in QUALITIES:
        if quality not in urls or heights[quality] == 0:
            continue
        height = heights[quality]
        if height and height in seen:
            continue
        seen.add(height)
        options.append(
            {
                "value": quality,
                "height": height,
                "label": f"{height}p" if height else _GENERIC_LABELS[quality],
            }
        )
    return options


_GENERIC_LABELS = {"hd": "Highest", "sd": "Medium", "low": "Lowest"}


def broadcast_date(entry):
    timestamp = entry.get("timestamp")
    if not timestamp:
        return None
    return datetime.fromtimestamp(int(timestamp), tz=_BROADCAST_TZ).date()


def result_title(entry):
    """The programme's name: its title, led by the show when that is missing."""
    topic = (entry.get("topic") or "").strip()
    title = (entry.get("title") or "").strip()
    if not topic or title.lower().startswith(topic.lower()):
        return title or topic
    return f"{topic} – {title}"


def result_details(entry, channel_label=None):
    """Channel, broadcast date and length, e.g. "WDR · 15.11.2026 · 89 min"."""
    channel = entry.get("channel") or ""
    details = [channel_label(channel) if channel_label else channel]
    date = broadcast_date(entry)
    if date:
        details.append(date.strftime("%d.%m.%Y"))
    duration = entry.get("duration")
    if duration:
        # A 45-second clip still reads as "1 min", not "0 min".
        details.append(f"{max(1, round(int(duration) / 60))} min")
    return " · ".join(part for part in details if part)


# -----------------------------
# Covers
# -----------------------------

_OG_IMAGE = (
    re.compile(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        re.IGNORECASE,
    ),
    re.compile(
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
        re.IGNORECASE,
    ),
)
# The preview image sits in the page head; no need to load whole SPAs.
_HEAD_LIMIT = 256 * 1024


def cover_url(page_url):
    """The broadcaster's preview image (og:image) for one programme page."""
    if not page_url:
        return ""
    return _cached(("cover", page_url), lambda: _fetch_cover(page_url))


def _fetch_cover(page_url):
    try:
        response = GLOBAL_SESSION.get(
            page_url,
            headers={"Accept-Encoding": "gzip, deflate", "Referer": ""},
            timeout=15,
            stream=True,
        )
        response.raise_for_status()
        head = b""
        for chunk in response.iter_content(32 * 1024):
            head += chunk
            if b"</head>" in head or len(head) >= _HEAD_LIMIT:
                break
        response.close()
    except Exception as exc:
        logger.debug("Mediathek cover fetch failed for %s: %s", page_url, exc)
        return ""
    text = head.decode("utf-8", errors="replace")
    for pattern in _OG_IMAGE:
        match = pattern.search(text)
        if match:
            return unescape(match.group(1)).strip()
    return ""


# Show posters (portrait, with the show's title art) come from TVmaze, a free
# TV database: https://www.tvmaze.com/api. Its data is CC BY-SA licensed.
TVMAZE_SEARCH_URL = "https://api.tvmaze.com/search/shows"
# Shows from the broadcasters' own countries; keeps "Tatort" from matching a
# foreign show of the same name.
_TVMAZE_COUNTRIES = {"DE", "AT", "CH"}
# TVmaze allows about 20 calls per 10 seconds; a page of search cards asks for
# all of its posters at once.
_TVMAZE_INTERVAL = 0.55
_tvmaze_lock = threading.Lock()
_tvmaze_last = 0.0
# Posters don't change; a day keeps repeat searches off the API.
_POSTER_TTL = 24 * 3600


def show_poster(topic):
    """TVmaze's poster for a show, or "" when it has no matching show."""
    # ORF names each season as its own topic: "Soko Donau Staffel 11".
    topic = show_name(topic)
    if not topic:
        return ""
    try:
        return _cached(
            ("poster", _normalize_name(topic)),
            lambda: _fetch_show_poster(topic),
            ttl=_POSTER_TTL,
        )
    except Exception as exc:
        # Not cached: a network hiccup shouldn't hide the poster for a day.
        logger.debug("TVmaze lookup failed for %s: %s", topic, exc)
        return ""


def _fetch_show_poster(topic):
    global _tvmaze_last
    with _tvmaze_lock:
        wait = _tvmaze_last + _TVMAZE_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _tvmaze_last = time.monotonic()
    response = GLOBAL_SESSION.get(
        TVMAZE_SEARCH_URL,
        params={"q": topic},
        headers={"Accept": "application/json", "Accept-Encoding": "gzip, deflate"},
        timeout=15,
    )
    response.raise_for_status()
    wanted = _normalize_name(topic)
    for hit in response.json() or []:
        show = hit.get("show") or {}
        if _normalize_name(show.get("name")) != wanted:
            continue
        if _show_country(show) not in _TVMAZE_COUNTRIES:
            continue
        image = show.get("image") or {}
        return image.get("original") or image.get("medium") or ""
    return ""


def _show_country(show):
    for outlet in (show.get("network"), show.get("webChannel")):
        country = ((outlet or {}).get("country") or {}).get("code")
        if country:
            return country
    return None


def _normalize_name(value):
    # "In aller Freundschaft - Die jungen Ärzte" (MediathekView) and
    # "In aller Freundschaft – Die jungen Ärzte" (TVmaze) are the same show,
    # and so are "Soko Kitzbühel" and TVmaze's "SOKO Kitzbuhel".
    text = unicodedata.normalize("NFKD", (value or "").casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.replace("–", "-").replace("—", "-")
    return " ".join(re.sub(r"[^\w-]+", " ", text).split())
