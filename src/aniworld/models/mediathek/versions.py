"""Language versions of a programme: German, English, OmU, sign language, ...

Broadcasters publish every version of a programme as its own entry:
    ZDFneo   "Die letzte Entscheidung (S03/E11)" and "... (S03/E11) (Englisch)"
    ARD      "... (S02/E08)" and "... (S02/E08) (Originalversion)"
    MDR      "... (S29/E25)" and "... (S29/E25) (Gebärdensprache)"
    Arte     one channel per language (ARTE.DE, ARTE.FR, ...), the same
             programme id in each

They are grouped per episode and labelled the way the other sites label their
languages: "<Language> Dub" is audio in that language, "<Language> Sub" the
original audio with subtitles in it. On top of those come "Original" (an
original version of unknown language), "Sign Language" and "Audio Description".
"""

import re

try:
    from ...config import DEFAULT_USER_AGENT, GLOBAL_SESSION, logger
    from . import api
except ImportError:
    from aniworld.config import DEFAULT_USER_AGENT, GLOBAL_SESSION, logger
    from aniworld.models.mediathek import api

DEFAULT_LABEL = "German Dub"
ORIGINAL = "Original"
SIGN_LANGUAGE = "Sign Language"
AUDIO_DESCRIPTION = "Audio Description"

# language name -> (ISO 639-2 for audio tags, ISO 639-1 for subtitle files)
_LANGUAGES = {
    "German": ("deu", "de"),
    "English": ("eng", "en"),
    "French": ("fra", "fr"),
    "Spanish": ("spa", "es"),
    "Italian": ("ita", "it"),
    "Polish": ("pol", "pl"),
}

# Every label in the order the language menu lists them.
LABELS = (
    *(f"{name} {kind}" for name in _LANGUAGES for kind in ("Dub", "Sub")),
    ORIGINAL,
    SIGN_LANGUAGE,
    AUDIO_DESCRIPTION,
)
_ORDER = {label: index for index, label in enumerate(LABELS)}

# Title markers of the non-Arte channels, checked in this order.
_TITLE_VERSIONS = (
    (re.compile(r"gebärdensprache|\(dgs\)", re.IGNORECASE), SIGN_LANGUAGE),
    (
        re.compile(r"audiodeskription|hörfassung|\(ad\)", re.IGNORECASE),
        AUDIO_DESCRIPTION,
    ),
    (
        re.compile(r"\bomu\b|\bomdu\b|mit deutschen untertiteln", re.IGNORECASE),
        "German Sub",
    ),
    (
        re.compile(r"\(englisch\)|english version|\(english\)", re.IGNORECASE),
        "English Dub",
    ),
    (re.compile(r"originalversion|originalfassung|\(ov\)", re.IGNORECASE), ORIGINAL),
)

# Arte's version code, see api._ARTE_VERSION:
#   VA / VOA German, VF / VOF French, VE[ANG] English (ESP, ITA, POL ...),
#   VO original of another language, AUD audio description,
#   -STA / -STF / -STE[ITA] subtitles, -STMA / -STMF subtitles for the deaf.
_ARTE_CODE = re.compile(
    r"[/_](VOA|VOF|VA|VF|VO|VE(?:%5B|\[)([A-Z]{3})(?:%5D|\]))(AUD)?"
    r"(?:-ST(M?)(A|F|E(?:%5B|\[)([A-Z]{3})(?:%5D|\])))?(?=[-_/])"
)
_ARTE_AUDIO = {"VA": "German", "VOA": "German", "VF": "French", "VOF": "French"}
_ARTE_CODES = {
    "ALL": "German",
    "ANG": "English",
    "ESP": "Spanish",
    "FRA": "French",
    "ITA": "Italian",
    "POL": "Polish",
}
_ARTE_SEGMENT = re.compile(r"/Generate/[^/]+/(de|en|es|fr|it|pl)/")
_SEGMENT_LANGUAGES = {
    "de": "German",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "it": "Italian",
    "pl": "Polish",
}
# The language an Arte channel speaks, and the one its player API answers in.
ARTE_CHANNEL_LANGUAGES = {
    "ARTE.DE": "de",
    "ARTE.EN": "en",
    "ARTE.ES": "es",
    "ARTE.FR": "fr",
    "ARTE.IT": "it",
    "ARTE.PL": "pl",
}


def label(entry):
    """The language label of one entry ("German Dub", "Italian Sub", ...)."""
    if (entry.get("channel") or "").startswith("ARTE."):
        return _arte_label(entry)
    title = entry.get("title") or ""
    for pattern, found in _TITLE_VERSIONS:
        if pattern.search(title):
            return found
    return DEFAULT_LABEL


def _arte_label(entry):
    for url in api.video_urls(entry).values():
        match = _ARTE_CODE.search(url)
        if match:
            code, dub, described, for_deaf, sub_kind, sub_code = match.groups()
            if described:
                return AUDIO_DESCRIPTION
            audio = _ARTE_CODES.get(dub) if dub else _ARTE_AUDIO.get(code)
            subtitles = None
            if sub_kind and not for_deaf:
                subtitles = {"A": "German", "F": "French"}.get(
                    sub_kind
                ) or _ARTE_CODES.get(sub_code)
            if subtitles and subtitles != audio:
                return f"{subtitles} Sub"
            return f"{audio} Dub" if audio else ORIGINAL
        match = _ARTE_SEGMENT.search(url)
        if match:
            return f"{_SEGMENT_LANGUAGES[match.group(1)]} Dub"
    return ORIGINAL


def audio_code(entry):
    """ISO 639-2 code of the entry's audio track; "und" when unknown."""
    if (entry.get("channel") or "").startswith("ARTE."):
        return api.audio_language(entry)
    found = label(entry)
    if found.endswith(" Dub"):
        return _LANGUAGES[found[: -len(" Dub")]][0]
    if found in (SIGN_LANGUAGE, AUDIO_DESCRIPTION):
        return "deu"
    return "und"


def subtitle_language(entry):
    """ISO 639-1 code for the entry's subtitle file."""
    found = label(entry)
    for name, (_, short) in _LANGUAGES.items():
        if found.startswith(f"{name} "):
            return short
    return api.CHANNEL_LANGUAGES.get(entry.get("channel"), "de")


def sort_labels(labels):
    return sorted(set(labels), key=lambda found: _ORDER.get(found, len(_ORDER)))


# -----------------------------
# Grouping versions per episode
# -----------------------------


def episode_key(entry):
    """What all versions of one episode share."""
    family = api.arte_family(entry)
    if family:
        # The programme id is the same in every language, the page isn't.
        return ("arte", family[0], family[1])
    season, episode = api.episode_marker(entry)
    if season is not None:
        return ("numbered", season, episode)
    return ("page", entry.get("url_website") or entry.get("id"))


def group(entries, preferred_channel=None):
    """[(primary entry, {label: entry})] per episode, in listing order.

    The primary entry is the version the episode is listed and named by: the
    German one where there is one, else the show's own channel's.
    """
    groups = {}
    for entry in entries:
        versions = groups.setdefault(episode_key(entry), {})
        versions.setdefault(label(entry), entry)
    result = []
    for versions in groups.values():
        # The show's own channel first (an Arte (FR) card lists the French
        # version), German where the channel has several.
        own = [e for e in versions.values() if e.get("channel") == preferred_channel]
        candidates = own or list(versions.values())
        primary = next(
            (e for e in candidates if label(e) == DEFAULT_LABEL), candidates[0]
        )
        result.append((primary, versions))
    return result


def versions_of(entry):
    """{label: entry} for every version of the episode `entry` belongs to."""
    key = episode_key(entry)
    if api.arte_family(entry):
        siblings = [entry, *arte_translations([entry])]
    else:
        siblings = api.show_entries(
            entry.get("channel") or "", entry.get("topic") or "", include_variants=True
        )
    found = {}
    for sibling in siblings:
        if episode_key(sibling) == key:
            found.setdefault(label(sibling), sibling)
    found.setdefault(label(entry), entry)
    return found


# -----------------------------
# Arte across its language channels
# -----------------------------

ARTE_PLAYER_API = "https://api.arte.tv/api/player/v2/config/{language}/{programme}"
# Results per translation search; a series' episodes fit easily.
_ARTE_SEARCH_LIMIT = 100
_ARTE_PROGRAMME_ID = re.compile(r"/videos/(\d{6}-\d{3}-[A-Z])")


def arte_translations(entries):
    """The other Arte channels' entries for the programmes in `entries`.

    MediathekView can't search by Arte's programme id, and every language
    titles a series its own way (Impulse, Déclics, Eureka!). Arte's player API
    gives the title in each language; searching that on the channel and
    keeping the matching programme ids finds the translations.
    """
    entries = [e for e in entries if api.arte_family(e)]
    if not entries:
        return []
    own = entries[0].get("channel")
    families = {api.arte_family(e)[0] for e in entries}
    sample = _ARTE_PROGRAMME_ID.search(entries[0].get("url_website") or "")
    if not sample:
        return []
    found = []
    for channel, language in ARTE_CHANNEL_LANGUAGES.items():
        if channel == own:
            continue
        # MediathekView is run by volunteers: one search per language where
        # the first name (usually the series) already finds it, and a modest
        # page of results.
        for name in _arte_titles(language, sample.group(1)):
            hits = [
                hit
                for hit in api.search(
                    name, channels=(channel,), limit=_ARTE_SEARCH_LIMIT
                )
                if (api.arte_family(hit) or (None,))[0] in families
            ]
            found += hits
            if hits:
                break
    # The same programme can turn up through both searches.
    unique = {(e.get("channel"), e.get("id") or e.get("url_website")): e for e in found}
    return list(unique.values())


def _arte_titles(language, programme):
    try:
        return api._cached(
            ("arte-titles", language, programme),
            lambda: _fetch_arte_titles(language, programme),
            ttl=24 * 3600,
        )
    except Exception as exc:
        # Not cached: the next listing tries again.
        logger.debug("Arte player API failed for %s/%s: %s", language, programme, exc)
        return ()


def _fetch_arte_titles(language, programme):
    """Title and subtitle Arte's player shows for a programme in one language.

    Series are named in one of the two ("Impulse" | "Chaostheorie: ...";
    Polish swaps them), so both are searched.
    """
    response = GLOBAL_SESSION.get(
        ARTE_PLAYER_API.format(language=language, programme=programme),
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
        },
        timeout=15,
    )
    response.raise_for_status()
    metadata = response.json()["data"]["attributes"]["metadata"]
    names = [metadata.get("title"), metadata.get("subtitle")]
    return tuple(name.strip() for name in names if name and name.strip())
