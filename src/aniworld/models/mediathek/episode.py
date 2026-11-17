import os
import re
import subprocess
from pathlib import Path

try:
    from ...config import (
        DEFAULT_USER_AGENT,
        NAMING_TEMPLATE,
        PROVIDER_HEADERS_D,
        PROVIDER_HEADERS_W,
        Audio,
        Subtitles,
        logger,
    )
    from ..common import ProviderData, check_downloaded, clean_title
    from ..common.common import download as episode_download
    from ..common.common import syncplay as episode_syncplay
    from ..common.common import watch as episode_watch
    from ..common.naming import template_path
    from ..common.paths import resolve_download_path
    from . import api
    from . import subtitles as subtitle_files
    from . import versions as language_versions
except ImportError:
    from aniworld.config import (
        DEFAULT_USER_AGENT,
        NAMING_TEMPLATE,
        PROVIDER_HEADERS_D,
        PROVIDER_HEADERS_W,
        Audio,
        Subtitles,
        logger,
    )
    from aniworld.models.common import (
        ProviderData,
        check_downloaded,
        clean_title,
    )
    from aniworld.models.common import download as episode_download
    from aniworld.models.common import syncplay as episode_syncplay
    from aniworld.models.common import watch as episode_watch
    from aniworld.models.common.naming import template_path
    from aniworld.models.common.paths import resolve_download_path
    from aniworld.models.mediathek import api
    from aniworld.models.mediathek import subtitles as subtitle_files
    from aniworld.models.mediathek import versions as language_versions

# How MediathekView names a channel -> how the broadcaster writes its name.
CHANNEL_LABELS = {
    "3Sat": "3sat",
    "ARTE.DE": "Arte",
    "ARTE.EN": "Arte (EN)",
    "ARTE.ES": "Arte (ES)",
    "ARTE.FR": "Arte (FR)",
    "ARTE.IT": "Arte (IT)",
    "ARTE.PL": "Arte (PL)",
    "Funk.net": "funk",
    "PHOENIX": "phoenix",
    "ZDF-tivi": "ZDFtivi",
}

# Defaults for the per-download options; the web UI's settings set these.
QUALITY_ENV = "ANIWORLD_MEDIATHEK_QUALITY"
SUBTITLES_ENV = "ANIWORLD_MEDIATHEK_SUBTITLES"


def default_quality():
    value = os.getenv(QUALITY_ENV, "hd").strip().lower()
    return value if value in api.QUALITIES else "hd"


def default_subtitles():
    return os.getenv(SUBTITLES_ENV, "1").strip() == "1"


# Every channel label, the names the Mediathek shows where other sites show
# their hoster ("provider").
MEDIATHEK_CHANNELS = tuple(CHANNEL_LABELS.get(c, c) for c in api.CHANNELS)

# Some broadcaster CDNs (ORF's, for one) answer FFmpeg's own "Lavf" user agent
# with 403, so downloads and players identify as a browser instead. This runs
# on import and fills the shared header tables for the channel names; setdefault
# keeps whatever another site may have put there.
for _channel in MEDIATHEK_CHANNELS:
    for _table in (PROVIDER_HEADERS_D, PROVIDER_HEADERS_W):
        _table.setdefault(_channel, {"User-Agent": DEFAULT_USER_AGENT})


def channel_label(channel):
    return CHANNEL_LABELS.get(channel, channel or "")


_COUNTRY_NAMES = {"AT": "Austria", "CH": "Switzerland", "DE": "Germany"}

_DURATION = re.compile(r"Duration:\s*(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")


def _container_duration(path):
    """Seconds of a local video, read from FFmpeg's banner; None if unknown."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError:
        return None
    match = _DURATION.search(result.stderr or "")
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _fallback_qualities(chosen):
    """The chosen quality, then the lower ones, then the higher ones."""
    index = api.QUALITIES.index(chosen)
    return [*api.QUALITIES[index:], *reversed(api.QUALITIES[:index])]


def clean_name(value):
    # "Alles finster (6/6)" would otherwise end up as "(66)" on disk.
    return " ".join(clean_title((value or "").replace("/", "-")).split())


class MediathekEpisode:
    """
    One programme from a public broadcaster's media library, found through
    MediathekView.

    Parameters:
        url:                Required. The broadcaster's page for the programme,
                            e.g. https://www.ardmediathek.de/video/Y3JpZDov...
                            Listings append ``#mvid=<id>`` to pin one entry
                            when a page carries several versions.
        selected_path:      Optional. Download folder.
        selected_language:  Optional. Which version to download, labelled like
                            the other sites' languages: "German Dub",
                            "English Dub", "French Sub" (original audio,
                            French subtitles), "Original", "Sign Language",
                            "Audio Description". Defaults to the version the
                            URL points at.
        selected_provider:  Optional. Accepted for interface parity; the
                            channel follows the version (Arte's languages are
                            channels of their own).
        entry:              Optional. The MediathekView entry, when a show
                            listing already has it (saves a lookup).
        versions:           Optional. {label: entry} of every version, when
                            the listing already grouped them.
        season, series:     Optional. The listing this episode came from.
        quality:            Optional. "hd", "sd" or "low"; defaults to
                            ANIWORLD_MEDIATHEK_QUALITY (hd).
        subtitles:          Optional. Save the broadcaster's subtitles as an
                            SRT beside the video; defaults to
                            ANIWORLD_MEDIATHEK_SUBTITLES (on).

    Attributes (Example):
        title:          "Folge 1009: Mein freier Wille (S26/E04)"
        title_de:       "Folge 1009: Mein freier Wille"
        topic:          "In aller Freundschaft"
        channel:        "MDR"
        season_number:  26      (None when the title carries no marker)
        episode_number: 4
        broadcast_date: date(2026, 11, 17)
        video_urls:     {"hd": "https://...1920x1080...mp4", "sd": ..., "low": ...}

    Files follow the naming template like any series when the broadcaster
    numbers the episode ("In aller Freundschaft/Season 26/In aller
    Freundschaft S26E004.mkv"); unnumbered programmes are saved as
    "<topic>/<title> (<date>).mkv". Versions other than the one the episode
    is listed by get their label added ("... S26E004 (Sign Language).mkv").

    A quality the programme lacks falls back to the next lower one on offer.

    Methods:
        download()
        watch()
        syncplay()
    """

    def __init__(
        self,
        url: str,
        selected_path: str | None = None,
        selected_language: str | None = None,
        selected_provider: str | None = None,
        entry: dict | None = None,
        season=None,
        series=None,
        episode_number: int | None = None,
        quality: str | None = None,
        subtitles: bool | None = None,
        versions: dict | None = None,
    ):
        if not api.MEDIATHEK_EPISODE_PATTERN.match(url or ""):
            raise ValueError(f"Invalid Mediathek URL: {url}")

        self.url = url
        self.__quality_param = quality
        self.__subtitles_param = subtitles
        self.season = season
        self.series = series
        self.__primary = entry
        self.__versions = versions
        self.__listed_number = episode_number
        self.__selected_path_param = selected_path
        self.__selected_path = None
        self.__base_folder = None
        self.__folder_path = None
        self.__file_name = None
        self.__file_extension = None
        self.__episode_path = None
        self.__is_downloaded = None
        self.__selected_language = selected_language
        self.__selected_provider_param = selected_provider

    # -----------------------------
    # MediathekView entry
    # -----------------------------

    @property
    def _primary(self):
        """The entry the URL points at: what the episode is listed and named by."""
        if self.__primary is None:
            entries, entry_id = api.lookup(self.url)
            entry = api.pick_entry(entries, entry_id)
            if entry is None:
                raise ValueError(
                    f"MediathekView lists no programme for {self.url}. It may "
                    "have left the broadcaster's media library."
                )
            self.__primary = entry
        return self.__primary

    @property
    def versions(self):
        """{label: entry} for every version of this episode."""
        if self.__versions is None:
            self.__versions = language_versions.versions_of(self._primary)
        return self.__versions

    @property
    def languages(self):
        """The version labels on offer, in menu order."""
        return language_versions.sort_labels(self.versions)

    @property
    def primary_language(self):
        return language_versions.label(self._primary)

    @property
    def selected_language(self):
        return self.__selected_language or self.primary_language

    @selected_language.setter
    def selected_language(self, value):
        self.__selected_language = value
        self.__episode_path = None
        self.__file_name = None
        self.__folder_path = None
        self.__is_downloaded = None

    @property
    def _entry(self):
        """The entry of the selected version, which is what gets downloaded."""
        wanted = self.selected_language
        if wanted == self.primary_language:
            return self._primary
        entry = self.versions.get(wanted)
        if entry is None:
            raise ValueError(
                f"{self.title} has no {wanted} version; it comes as "
                + ", ".join(self.languages)
            )
        return entry

    @property
    def language_providers(self):
        """{label: [channel]} the way the other sites list languages and hosters."""
        return {
            found: [channel_label(self.versions[found].get("channel"))]
            for found in self.languages
        }

    @property
    def title(self):
        return (self._primary.get("title") or "").strip()

    @property
    def title_cleaned(self):
        return clean_name(self.title)

    @property
    def title_de(self):
        """Episode title for listings: no show name, no S/E marker.

        Unnumbered programmes add their broadcast date, which is what tells
        "Folge 4675" from "Folge 4676" at a glance.
        """
        title = api.episode_title(self._primary)
        date = self.broadcast_date
        if not self.is_numbered and date:
            return f"{title} · {date.strftime('%d.%m.%Y')}"
        return title

    @property
    def title_en(self):
        return ""

    @property
    def topic(self):
        return (self._primary.get("topic") or "").strip()

    @property
    def channel(self):
        return channel_label(self._entry.get("channel"))

    @property
    def description(self):
        return (self._primary.get("description") or "").strip()

    @property
    def broadcast_date(self):
        return api.broadcast_date(self._primary)

    @property
    def release_year(self):
        date = self.broadcast_date
        return date.year if date else None

    @property
    def duration_min(self):
        duration = self._entry.get("duration")
        return int(duration) // 60 if duration else None

    @property
    def genres(self):
        return [self.topic] if self.topic else []

    @property
    def poster_url(self):
        return api.cover_url(self._primary.get("url_website"))

    @property
    def video_urls(self):
        return api.video_urls(self._entry)

    @property
    def subtitle_url(self):
        return self._entry.get("url_subtitle") or None

    @property
    def quality(self):
        value = str(self.__quality_param or "").strip().lower()
        return value if value in api.QUALITIES else default_quality()

    @property
    def subtitles(self):
        """Whether a download also saves the subtitles (when there are any)."""
        if self.__subtitles_param is None:
            return default_subtitles()
        return bool(self.__subtitles_param)

    @property
    def language_code(self):
        """ISO 639-1 code of the selected version's subtitles, for the file."""
        return language_versions.subtitle_language(self._entry)

    @property
    def audio_language(self):
        """ISO 639-2 code written into the file's audio track ("fra", ...).

        The shared download reads this instead of the four language labels the
        anime sites use, which have no French, Spanish, Italian or Polish.
        """
        return language_versions.audio_code(self._entry)

    @property
    def audio_badge(self):
        """Short label for the episode list: DE, FR, EN, ... or OV."""
        return api.AUDIO_BADGES.get(self.audio_language, "OV")

    # -----------------------------
    # Numbering
    # -----------------------------

    @property
    def season_number(self):
        """The broadcaster's season, or None for unnumbered programmes."""
        return api.episode_marker(self._primary)[0]

    @property
    def is_numbered(self):
        return self.season_number is not None

    @property
    def episode_number(self):
        episode = api.episode_marker(self._primary)[1]
        if episode is not None:
            return episode
        # Unnumbered programmes count up in their listing's order.
        return self.__listed_number or 1

    # -----------------------------
    # Provider interface: the channel stands where a hoster would
    # -----------------------------

    @property
    def provider_data(self):
        """The selected version's stream under its channel.

        The web UI lists every version through language_providers; this keeps
        the shared download and player code working on the one picked.
        """
        stream = api.best_video_url(self._entry, self.quality)
        if not stream:
            return None
        return ProviderData({(Audio.GERMAN, Subtitles.NONE): {self.channel: stream}})

    @property
    def selected_provider(self):
        return self.channel

    @selected_provider.setter
    def selected_provider(self, value):
        # A programme airs on one channel; there is nothing to switch to.
        self.__selected_provider_param = value

    def available_providers(self, language=None):
        return (self.channel,) if self.provider_data else ()

    def provider_attempt_order(self):
        return self.available_providers()

    def provider_link(self, language=None, provider=None):
        data = self.provider_data
        if data is None:
            return None
        return data.get((Audio.GERMAN, Subtitles.NONE)).get(self.channel)

    @property
    def provider_url(self):
        return self.provider_link()

    @property
    def stream_url(self):
        # The broadcasters publish direct MP4/HLS links, no hoster to resolve.
        stream = self.provider_link()
        if not stream:
            raise ValueError(f"No video stream listed for {self.url}")
        logger.debug("Mediathek stream (%s): %s", self.quality, stream)
        return stream

    def _normalize_language(self, language):
        return language

    # -----------------------------
    # Paths
    # -----------------------------

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
        self.__is_downloaded = None

    @property
    def _show_folder_name(self):
        # "Soko Kitzbühel Staffel 2" files under "Soko Kitzbühel" with its
        # other seasons, an Arte episode under its series ("Impulse").
        return (
            clean_name(api.show_label(self._primary))
            or channel_label(self._primary.get("channel"))
            or "Mediathek"
        )

    @property
    def _episode_path(self):
        if self.__episode_path is None:
            if self.is_numbered:
                self.__episode_path = self._numbered_path()
            else:
                self.__episode_path = (
                    Path(self.selected_path)
                    / self._show_folder_name
                    / f"{self._dated_name()}.{self._file_extension}"
                )
        return self.__episode_path

    def _numbered_path(self):
        """The naming template, filled like any other site's series."""
        template = os.getenv("ANIWORLD_NAMING_TEMPLATE", NAMING_TEMPLATE)
        values = {
            "title": self._show_folder_name,
            "year": "",
            "imdbid": "",
            "season": f"{self.season_number:02d}",
            "episode": f"{self.episode_number:03d}",
            "language": self.selected_language,
            "resolution": getattr(self, "_resolution", "unknown"),
        }
        path = template_path(self.selected_path, template, values, is_series=True)
        return path.with_name(
            f"{path.stem}{self._version_suffix}.{self._file_extension}"
        )

    @property
    def _version_suffix(self):
        """ " (English Dub)" for a version other than the listed one."""
        if self.selected_language == self.primary_language:
            return ""
        return f" ({self.selected_language})"

    def _dated_name(self):
        # The whole title: the file has to make sense outside its folder too.
        name = self.title_cleaned or self._show_folder_name
        date = self.broadcast_date
        if date:
            # Daily and weekly shows reuse titles ("Folge 12", "Sendung vom
            # ..."), the broadcast date keeps their files apart.
            name = f"{name} ({date.isoformat()})"
        return name + self._version_suffix

    @property
    def _base_folder(self):
        if self.__base_folder is None:
            self.__base_folder = Path(self.selected_path) / self._show_folder_name
        return self.__base_folder

    @property
    def _folder_path(self):
        if self.__folder_path is None:
            self.__folder_path = self._episode_path.parent
        return self.__folder_path

    @property
    def _file_name(self):
        if self.__file_name is None:
            self.__file_name = self._episode_path.stem
        return self.__file_name

    @property
    def _file_extension(self):
        if self.__file_extension is None:
            template = os.getenv("ANIWORLD_NAMING_TEMPLATE", NAMING_TEMPLATE)
            file_part = template.split("/")[-1]
            ext = file_part.rsplit(".", 1)[-1] if "." in file_part else ""
            self.__file_extension = ext or "mkv"
        return self.__file_extension

    @property
    def is_downloaded(self):
        if self.__is_downloaded is None:
            self.__is_downloaded = check_downloaded(self._episode_path)
        return self.__is_downloaded

    # -----------------------------
    # PUBLIC METHODS
    # -----------------------------

    def download(self):
        """Download the video, then its subtitles.

        Broadcaster CDNs sometimes drop segments of one rendition (SRF's
        answers 404 for parts of a quality now and then). FFmpeg skips those
        and finishes with a shortened file, so the length is checked against
        what MediathekView lists, and a short file is retried in the next
        quality on offer: the lower ones first, then the higher.

        A short file is set aside, never deleted: when no quality comes out
        whole (MediathekView's listed length can be off, too), the longest
        one is kept and the download reports what fell short.
        """
        self._check_geo_restriction()
        chosen = self.quality
        path = self._episode_path
        tried = set()
        short = []  # (seconds, set-aside file, quality)
        complete = False
        kept = False
        try:
            for quality in _fallback_qualities(chosen):
                stream = api.best_video_url(self._entry, quality)
                if not stream or stream in tried:
                    # A missing quality falls back to one already tried.
                    continue
                tried.add(stream)
                self.__quality_param = quality
                episode_download(self)
                shortfall = self._shortfall()
                if shortfall is None:
                    complete = True
                    break
                actual, expected = shortfall
                logger.warning(
                    "%s is incomplete in %s (%.0fs of %ss)",
                    path.name,
                    quality,
                    actual,
                    expected,
                )
                aside = path.with_name(f"{path.stem}.temp_short_{quality}{path.suffix}")
                os.replace(path, aside)
                short.append((actual, aside, quality))
                self.__is_downloaded = None
            if not tried:
                raise ValueError(f"No video stream listed for {self.url}")
            if not complete and short:
                actual, quality = self._keep_longest(short)
                kept = True
                expected = int(self._entry.get("duration") or 0)
                raise ValueError(
                    f"{self.title} came out shorter than listed in every quality "
                    f"({actual:.0f}s of {expected}s at best). Kept the {quality} "
                    f"file at {path}; the listing may be off, or the broadcaster "
                    "dropped parts of the stream."
                )
        except Exception:
            # A later attempt failing outright (network gone, ...) must not
            # cost the file an earlier attempt already brought home.
            if short and not kept:
                self._keep_longest(short)
            raise
        finally:
            self.__quality_param = chosen
            for _, aside, _ in short:
                aside.unlink(missing_ok=True)
        if self.subtitles:
            self.download_subtitles()

    @property
    def geo_restriction(self):
        """The one country the programme is licensed for ("AT"), else None."""
        return api.geo_restriction(self._entry)

    def _check_geo_restriction(self):
        """Refuse up front instead of saving the broadcaster's block notice."""
        country = self.geo_restriction
        if country and api.geo_blocked(self.stream_url):
            raise ValueError(
                f"{self.title} may only be shown in {_COUNTRY_NAMES.get(country, country)}; "
                f"{self.channel} serves a notice instead of the video here."
            )

    def _keep_longest(self, short):
        """Put the longest of the set-aside files (or what's already at the
        target, if longer) at the episode path. Returns (seconds, quality).

        Called once, at the end: the set-aside list is emptied so the cleanup
        afterwards only removes the shorter ones.
        """
        path = self._episode_path
        candidates = list(short)
        if path.exists():
            # Whatever the last, failed attempt left behind.
            current = _container_duration(path)
            if current is not None:
                candidates.append((current, path, self.quality))
        actual, best, quality = max(candidates, key=lambda c: c[0])
        if best != path:
            os.replace(best, path)
        short[:] = [entry for entry in short if entry[1] != best]
        self.__is_downloaded = None
        return actual, quality

    def _shortfall(self):
        """(seconds on disk, seconds listed) when the file falls short, else None."""
        expected = int(self._entry.get("duration") or 0)
        path = self._episode_path
        if not expected or not path.exists():
            return None
        actual = _container_duration(path)
        if actual is None:
            return None
        # Rounding and leading/trailing frames differ by a few seconds.
        if actual >= expected - max(10, expected * 0.03):
            return None
        return actual, expected

    def download_subtitles(self):
        """Save the subtitles as "<video>.<lang>.srt"; None when there are none.

        Runs after the video, so a programme that already sat on disk gets
        subtitles added on a second try. A broken subtitle file is logged and
        skipped, never failing the video it belongs to.
        """
        url = self.subtitle_url
        video = self._episode_path
        if not url or not video.exists():
            return None
        return subtitle_files.save(url, video, self.language_code)

    watch = episode_watch
    syncplay = episode_syncplay


if __name__ == "__main__":
    import sys

    episode = MediathekEpisode(sys.argv[1])
    print(episode.title, "|", episode.topic, "|", episode.channel)
    print(episode.season_number, episode.episode_number, episode._episode_path)
    print(episode.video_urls)
