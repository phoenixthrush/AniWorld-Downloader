"""Parallel HLS segment downloader.

FFmpeg pulls HLS segments one at a time over a single connection, which makes
hosters that serve `master.m3u8` (VOE above all) far slower than the available
bandwidth allows. This module fetches the segments concurrently and writes them
back in playlist order, producing a file FFmpeg can then remux without any
network access.

Anything the parser does not fully understand raises `HLSUnsupported` so the
caller can fall back to letting FFmpeg handle the stream directly.
"""

import os
import re
import struct
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin

import niquests

try:
    from ...config import DEFAULT_USER_AGENT, logger
except ImportError:
    from aniworld.config import DEFAULT_USER_AGENT, logger


class HLSUnsupported(Exception):
    """The playlist uses a feature this downloader cannot handle."""


DEFAULT_CONCURRENCY = 8
MAX_CONCURRENCY = 32
SEGMENT_RETRIES = 3
SEGMENT_TIMEOUT = 30

# Audio rendition LANGUAGE values seen in the wild, keyed by ffmpeg lang code
_LANG_PREFIXES = {
    "deu": ("de", "ger", "deu"),
    "eng": ("en", "eng"),
    "jpn": ("ja", "jp", "jpn"),
}

_LANG_NAME_HINTS = {
    "deu": ("german", "deutsch"),
    "eng": ("english",),
    "jpn": ("japanese", "japanisch"),
}

_ATTR_RE = re.compile(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)')


def get_concurrency():
    """Read the configured segment concurrency, clamped to a sane range."""
    raw = os.getenv("ANIWORLD_HLS_CONCURRENCY", str(DEFAULT_CONCURRENCY))
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return DEFAULT_CONCURRENCY
    return max(1, min(value, MAX_CONCURRENCY))


def _parse_attributes(line):
    """Parse the `KEY=VALUE,KEY="VALUE"` tail of an EXT-X tag."""
    attrs = {}
    for key, value in _ATTR_RE.findall(line):
        attrs[key] = value.strip('"')
    return attrs


class _Variant:
    __slots__ = ("audio_group", "bandwidth", "uri")

    def __init__(self, uri, bandwidth, audio_group):
        self.uri = uri
        self.bandwidth = bandwidth
        self.audio_group = audio_group


class _Rendition:
    __slots__ = ("group_id", "is_default", "language", "name", "uri")

    def __init__(self, uri, group_id, language, name, is_default):
        self.uri = uri
        self.group_id = group_id
        self.language = language
        self.name = name
        self.is_default = is_default


class _Key:
    __slots__ = ("iv", "method", "uri")

    def __init__(self, method, uri, iv):
        self.method = method
        self.uri = uri
        self.iv = iv


# -----------------------------------------------------------------------------
# HTTP
# -----------------------------------------------------------------------------

_thread_local = threading.local()


def _session():
    """One niquests session per worker thread."""
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = niquests.Session()
        _thread_local.session = session
    return session


def _default_headers(headers):
    merged = {"User-Agent": DEFAULT_USER_AGENT}
    if headers:
        merged.update(headers)
    return merged


def _fetch_text(url, headers):
    resp = _session().get(url, headers=headers, timeout=SEGMENT_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def _fetch_bytes(url, headers):
    """Fetch a URL, retrying transient failures."""
    last_error = None
    for attempt in range(SEGMENT_RETRIES):
        try:
            resp = _session().get(url, headers=headers, timeout=SEGMENT_TIMEOUT)
            resp.raise_for_status()
            content = resp.content
            if not content:
                raise ValueError("empty response body")
            return content
        except Exception as err:
            last_error = err
            if attempt < SEGMENT_RETRIES - 1:
                time.sleep(2**attempt)
    raise RuntimeError(f"failed to fetch {url}: {last_error}") from last_error


# -----------------------------------------------------------------------------
# Playlist parsing
# -----------------------------------------------------------------------------


def _parse_master_playlist(text, base_url):
    """Return (variants, renditions) from a master playlist."""
    variants = []
    renditions = []
    lines = [line.strip() for line in text.splitlines()]

    for index, line in enumerate(lines):
        if line.startswith("#EXT-X-MEDIA:"):
            attrs = _parse_attributes(line)
            if attrs.get("TYPE") != "AUDIO":
                continue
            uri = attrs.get("URI")
            renditions.append(
                _Rendition(
                    uri=urljoin(base_url, uri) if uri else None,
                    group_id=attrs.get("GROUP-ID", ""),
                    language=attrs.get("LANGUAGE", ""),
                    name=attrs.get("NAME", ""),
                    is_default=attrs.get("DEFAULT", "").upper() == "YES",
                )
            )
        elif line.startswith("#EXT-X-STREAM-INF:"):
            attrs = _parse_attributes(line)
            # The URI is on the next non-comment line
            uri = None
            for candidate in lines[index + 1 :]:
                if candidate and not candidate.startswith("#"):
                    uri = candidate
                    break
            if not uri:
                continue
            try:
                bandwidth = int(attrs.get("BANDWIDTH", "0"))
            except ValueError:
                bandwidth = 0
            variants.append(
                _Variant(
                    uri=urljoin(base_url, uri),
                    bandwidth=bandwidth,
                    audio_group=attrs.get("AUDIO", ""),
                )
            )

    return variants, renditions


def _select_audio_rendition(renditions, group_id, preferred_lang):
    """Pick the audio rendition matching `preferred_lang`, else the default.

    Returns None when the variant carries its audio inline, which is the case
    whenever it declares no AUDIO group — the renditions then belong to other
    variants and must not be mixed in.
    """
    if not group_id:
        return None

    candidates = [
        rendition
        for rendition in renditions
        if rendition.uri and rendition.group_id == group_id
    ]
    if not candidates:
        return None

    prefixes = _LANG_PREFIXES.get(preferred_lang, ())
    hints = _LANG_NAME_HINTS.get(preferred_lang, ())

    if prefixes:
        for rendition in candidates:
            language = (rendition.language or "").lower()
            if language and language.startswith(prefixes):
                return rendition
        for rendition in candidates:
            name = (rendition.name or "").lower()
            if any(hint in name for hint in hints):
                return rendition

    for rendition in candidates:
        if rendition.is_default:
            return rendition

    return candidates[0]


def rendition_languages(master_text, base_url=""):
    """Return the ffmpeg lang codes present as *separate* audio renditions.

    Given an HLS master playlist, report which of the languages this downloader
    can select (``_LANG_PREFIXES``) appear as their own ``#EXT-X-MEDIA:TYPE=AUDIO``
    rendition — matched the exact same way ``_select_audio_rendition`` matches
    them, so "detected as available" and "selectable at download time" never
    disagree. Used by cineby to decide whether e.g. a German dub exists before
    offering it.
    """
    _, renditions = _parse_master_playlist(master_text, base_url)
    found = set()
    for code, prefixes in _LANG_PREFIXES.items():
        hints = _LANG_NAME_HINTS.get(code, ())
        for rendition in renditions:
            language = (rendition.language or "").lower()
            name = (rendition.name or "").lower()
            if (language and language.startswith(prefixes)) or any(
                hint in name for hint in hints
            ):
                found.add(code)
                break
    return found


def _parse_media_playlist(text, base_url):
    """Return (segments, init_uri) where each segment is (uri, key, sequence)."""
    if "#EXT-X-ENDLIST" not in text:
        raise HLSUnsupported("live playlist (no EXT-X-ENDLIST)")

    segments = []
    init_uri = None
    current_key = None
    sequence = 0

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            try:
                sequence = int(line.split(":", 1)[1])
            except ValueError:
                sequence = 0

        elif line.startswith("#EXT-X-BYTERANGE"):
            raise HLSUnsupported("byte-range segments")

        elif line.startswith("#EXT-X-MAP:"):
            attrs = _parse_attributes(line)
            uri = attrs.get("URI")
            if not uri:
                raise HLSUnsupported("EXT-X-MAP without URI")
            if "BYTERANGE" in attrs:
                raise HLSUnsupported("byte-range init segment")
            init_uri = urljoin(base_url, uri)

        elif line.startswith("#EXT-X-KEY:"):
            attrs = _parse_attributes(line)
            method = attrs.get("METHOD", "NONE").upper()
            if method == "NONE":
                current_key = None
            elif method == "AES-128":
                uri = attrs.get("URI")
                if not uri:
                    raise HLSUnsupported("AES-128 key without URI")
                current_key = _Key(method, urljoin(base_url, uri), attrs.get("IV"))
            else:
                raise HLSUnsupported(f"encryption method {method}")

        elif not line.startswith("#"):
            segments.append((urljoin(base_url, line), current_key, sequence))
            sequence += 1

    if not segments:
        raise HLSUnsupported("playlist contains no segments")

    return segments, init_uri


# -----------------------------------------------------------------------------
# Decryption
# -----------------------------------------------------------------------------


def _decrypt_segment(data, key_bytes, iv_bytes):
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    decryptor = Cipher(algorithms.AES(key_bytes), modes.CBC(iv_bytes)).decryptor()
    plain = decryptor.update(data) + decryptor.finalize()

    # HLS pads each segment with PKCS7, but not every encoder does.
    if plain:
        pad = plain[-1]
        if 1 <= pad <= 16 and plain[-pad:] == bytes([pad]) * pad:
            return plain[:-pad]
    return plain


def _resolve_iv(key, sequence):
    if key.iv:
        raw = key.iv.lower().removeprefix("0x")
        return bytes.fromhex(raw.zfill(32))
    return b"\x00" * 8 + struct.pack(">Q", sequence)


# -----------------------------------------------------------------------------
# Progress reporting
# -----------------------------------------------------------------------------


def _common():
    """Resolve the sibling module lazily — it imports this one at load time."""
    from . import common

    return common


def _publish_progress(**fields):
    module = _common()
    with module._ffmpeg_progress_lock:
        module._ffmpeg_progress.update(**fields)


class _ProgressTracker:
    def __init__(self, total_segments, label):
        self.total = total_segments
        self.label = label
        self.done = 0
        self.bytes_written = 0
        self._common = _common()
        self._last_bytes = 0
        self._last_tick = time.monotonic()
        self._bandwidth = ""

    def advance(self, chunk_size):
        self.done += 1
        self.bytes_written += chunk_size

        now = time.monotonic()
        elapsed = now - self._last_tick
        if elapsed > 0.5:
            per_second = (self.bytes_written - self._last_bytes) / elapsed
            if per_second > 0:
                self._bandwidth = f"{per_second / 1024 / 1024:.1f} MB/s"
            self._last_bytes = self.bytes_written
            self._last_tick = now

        percent = round(self.done / self.total * 100, 1) if self.total else 0.0
        counter = f"{self.done}/{self.total}"

        with self._common._ffmpeg_progress_lock:
            self._common._ffmpeg_progress.update(
                percent=percent,
                time=f"{counter} segments",
                speed="",
                bandwidth=self._bandwidth,
                active=True,
            )

        self._common._print_cli_progress(percent, counter, self._bandwidth, self.label)


# -----------------------------------------------------------------------------
# Download
# -----------------------------------------------------------------------------


def _download_playlist(playlist_url, headers, temp_prefix, suffix, tracker_factory):
    """Fetch every segment of a media playlist, in order, into one file.

    Returns the path written. The extension reflects the segment container so
    FFmpeg picks the right demuxer: `.mp4` for fMP4 (an EXT-X-MAP init segment
    is present), `.ts` for MPEG-TS.
    """
    text = _fetch_text(playlist_url, headers)
    if "#EXT-X-STREAM-INF" in text:
        raise HLSUnsupported("expected a media playlist, got a master playlist")

    segments, init_uri = _parse_media_playlist(text, playlist_url)
    output_path = temp_prefix.with_suffix(f"{suffix}{'.mp4' if init_uri else '.ts'}")
    tracker = tracker_factory(len(segments))
    concurrency = get_concurrency()

    key_cache = {}
    key_cache_lock = threading.Lock()

    def _key_bytes(uri):
        with key_cache_lock:
            if uri in key_cache:
                return key_cache[uri]
        data = _fetch_bytes(uri, headers)
        if len(data) != 16:
            raise HLSUnsupported(f"AES key has {len(data)} bytes, expected 16")
        with key_cache_lock:
            key_cache[uri] = data
        return data

    def _fetch_segment(segment):
        uri, key, sequence = segment
        data = _fetch_bytes(uri, headers)
        if key is None:
            return data
        return _decrypt_segment(data, _key_bytes(key.uri), _resolve_iv(key, sequence))

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "wb") as handle:
        if init_uri:
            handle.write(_fetch_bytes(init_uri, headers))

        if concurrency == 1:
            for segment in segments:
                chunk = _fetch_segment(segment)
                handle.write(chunk)
                tracker.advance(len(chunk))
            return output_path

        # Keep a bounded window of in-flight segments so memory stays flat
        # regardless of how many segments the playlist has.
        window = concurrency * 2
        pending = deque()
        next_index = 0

        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            while next_index < len(segments) and len(pending) < window:
                pending.append(pool.submit(_fetch_segment, segments[next_index]))
                next_index += 1

            while pending:
                chunk = pending.popleft().result()
                handle.write(chunk)
                tracker.advance(len(chunk))
                if next_index < len(segments):
                    pending.append(pool.submit(_fetch_segment, segments[next_index]))
                    next_index += 1

    return output_path


def download_hls_parallel(
    stream_url,
    temp_prefix,
    headers=None,
    preferred_audio_lang=None,
    label="",
):
    """Download an HLS stream into local files ready for an FFmpeg remux.

    Returns a list of paths: `[video]` for a muxed stream, or
    `[video, audio]` when the playlist carries audio as a separate rendition.

    Raises `HLSUnsupported` when the playlist needs features this downloader
    does not implement — callers should fall back to plain FFmpeg then.
    """
    if get_concurrency() == 1:
        raise HLSUnsupported("parallel HLS download disabled")

    temp_prefix = Path(temp_prefix)
    headers = _default_headers(headers)

    master_text = _fetch_text(stream_url, headers)
    if not master_text.lstrip().startswith("#EXTM3U"):
        raise HLSUnsupported("response is not an m3u8 playlist")

    video_playlist = stream_url
    audio_playlist = None

    if "#EXT-X-STREAM-INF" in master_text:
        variants, renditions = _parse_master_playlist(master_text, stream_url)
        if not variants:
            raise HLSUnsupported("master playlist has no variants")

        variant = max(variants, key=lambda item: item.bandwidth)
        video_playlist = variant.uri

        rendition = _select_audio_rendition(
            renditions, variant.audio_group, preferred_audio_lang
        )
        if rendition is not None:
            audio_playlist = rendition.uri
            logger.debug(
                f"[HLS] separate audio rendition: {rendition.name or rendition.language}"
            )

    written = []
    try:
        _publish_progress(percent=0.0, time="", speed="", bandwidth="", active=True)

        def _video_tracker(total):
            return _ProgressTracker(total, label)

        written.append(
            _download_playlist(
                video_playlist, headers, temp_prefix, ".hls_video", _video_tracker
            )
        )

        if audio_playlist:

            def _audio_tracker(total):
                return _ProgressTracker(total, f"{label} (audio)" if label else "audio")

            written.append(
                _download_playlist(
                    audio_playlist, headers, temp_prefix, ".hls_audio", _audio_tracker
                )
            )

        return written
    except Exception:
        cleanup_temp_files(temp_prefix)
        raise
    finally:
        _publish_progress(percent=0.0, time="", speed="", bandwidth="", active=False)


def cleanup_temp_files(temp_prefix):
    """Remove any partial files a previous HLS attempt may have left behind."""
    temp_prefix = Path(temp_prefix)
    for suffix in (
        ".hls_video.ts",
        ".hls_video.mp4",
        ".hls_audio.ts",
        ".hls_audio.mp4",
    ):
        temp_prefix.with_suffix(suffix).unlink(missing_ok=True)
