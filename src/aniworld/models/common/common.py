import getpass
import hashlib
import json
import os
import platform
import re
import shlex
import subprocess
import sys
import threading as _threading
from pathlib import Path
from typing import Tuple
from urllib.parse import urljoin, urlparse, urlsplit, urlunsplit

import ffmpeg

from ...autodeps import DependencyManager

try:
    from ...autodeps import get_aria2c_path, get_player_path, get_syncplay_path
    from ...extractors import provider_functions
    from ...config import (
        AUTO_PROVIDER,
        INVERSE_LANG_LABELS,
        LANG_CODE_MAP,
        LANG_KEY_MAP,
        GLOBAL_SESSION,
        PROVIDER_HEADERS_D,
        PROVIDER_HEADERS_W,
        SUPPORTED_PROVIDERS,
        Audio,
        Subtitles,
        get_provider_order,
        get_video_codec,
        logger,
    )
except ImportError:
    from aniworld.autodeps import get_aria2c_path, get_player_path, get_syncplay_path
    from aniworld.extractors import provider_functions
    from aniworld.config import (
        AUTO_PROVIDER,
        INVERSE_LANG_LABELS,
        LANG_CODE_MAP,
        LANG_KEY_MAP,
        GLOBAL_SESSION,
        PROVIDER_HEADERS_D,
        PROVIDER_HEADERS_W,
        SUPPORTED_PROVIDERS,
        Audio,
        Subtitles,
        get_provider_order,
        get_video_codec,
        logger,
    )

# Precompile regex for forbidden filename characters
FORBIDDEN_CHARS = re.compile(r'[<>:"/\\|?*]')

# ---------------------------------------------------------------------------
# Provider cache — remembers the last working provider per anime series
# ---------------------------------------------------------------------------
_PROVIDER_CACHE_PATH = Path.home() / ".aniworld" / "provider_cache.json"
_provider_cache: dict[str, str] = {}
_provider_cache_lock = _threading.Lock()

try:
    if _PROVIDER_CACHE_PATH.exists():
        with _PROVIDER_CACHE_PATH.open("r", encoding="utf-8") as _f:
            _provider_cache = json.load(_f)
except Exception:
    _provider_cache = {}


def _series_key(episode) -> str:
    url = getattr(episode, "url", "") or ""
    parsed = urlparse(url)
    _STOP = {"staffel-", "episode-", "filme", "film-", "season-"}
    parts = []
    for part in parsed.path.split("/"):
        if not part:
            continue
        if any(part.startswith(sw) or part == sw for sw in _STOP):
            break
        parts.append(part)
    return f"{parsed.netloc}:{'/'.join(parts)}"


def _save_provider_cache() -> None:
    try:
        _PROVIDER_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _PROVIDER_CACHE_PATH.open("w", encoding="utf-8") as f:
            json.dump(_provider_cache, f, indent=2)
    except Exception:
        pass


def clean_title(title: str) -> str:
    """Clean a string to make it safe for use as a filename."""
    return FORBIDDEN_CHARS.sub("", title).strip()


def check_downloaded(episode_path):
    result = {
        "exists": False,
        "video_langs": set(),
        "audio_langs": set(),
    }

    if not episode_path.exists():
        return result

    result["exists"] = True

    try:
        probe = ffmpeg.probe(episode_path)
    except ffmpeg.Error:
        return result

    streams = probe.get("streams", [])

    for s in streams:
        lang = s.get("tags", {}).get("language", "und")
        if s.get("codec_type") == "video":
            result["video_langs"].add(lang)
        elif s.get("codec_type") == "audio":
            result["audio_langs"].add(lang)

    return result


class ProviderData:
    """
    Container for provider URLs grouped by language settings.

    The internal structure is:

        dict[(Audio, Subtitles)][provider_name]

    Meaning:
    - The key is a tuple of (Audio, Subtitles)
    - The value is a dictionary mapping provider names to their URLs
    """

    def __init__(self, data):
        self._data = data

    def __str__(self):
        # return f"{self.__class__.__name__}({self._data!r})"
        lines = []

        for (audio, subtitles), providers in sorted(
            self._data.items(), key=lambda item: (item[0][0].value, item[0][1].value)
        ):
            header = f"{audio.value} audio"
            if subtitles != Subtitles.NONE:
                header += f" + {subtitles.value} subtitles"

            lines.append(header)

            for provider, url in providers.items():
                lines.append(f"  - {provider:<8} -> {url}")

            lines.append("")

        return "\n".join(lines).rstrip()

    def __repr__(self):
        return f"{self.__class__.__name__}({self._data!r})"

    # Accept a tuple directly
    def get(self, lang_tuple: Tuple[Audio, Subtitles]):
        return self._data.get(lang_tuple, {})

    # Behave like a dictionary
    def __getitem__(self, lang_tuple: Tuple[Audio, Subtitles]):
        return self._data[lang_tuple]


# -----------------------------------------------------------------------------
# Episode actions (moved from models/*/episode.py)
# -----------------------------------------------------------------------------


def _remove_empty_dirs(folder_path, base_folder):
    """Remove folder_path and base_folder if they are empty directories."""
    try:
        if folder_path.is_dir() and not any(folder_path.iterdir()):
            folder_path.rmdir()
        if base_folder.is_dir() and not any(base_folder.iterdir()):
            base_folder.rmdir()
    except OSError:
        pass


def _reset_provider_cache(episode):
    for attr in list(vars(episode)):
        if attr.endswith("__redirect_url") or attr.endswith("__provider_url"):
            setattr(episode, attr, None)


def _set_selected_provider(episode, provider):
    """Set the selected provider on episode classes with name-mangled fields."""
    for attr in list(vars(episode)):
        if attr.endswith("__selected_provider_param"):
            setattr(episode, attr, provider)
        elif attr.endswith("__selected_provider"):
            setattr(episode, attr, None)
    _reset_provider_cache(episode)


def _language_values(language):
    try:
        return tuple(part.value for part in language)
    except (TypeError, AttributeError):
        return language


def _language_matches(left, right):
    return left == right or _language_values(left) == _language_values(right)


def _language_for_provider_lookup(episode):
    if hasattr(episode, "_normalize_language"):
        return episode._normalize_language(episode.selected_language)

    key = INVERSE_LANG_LABELS.get(episode.selected_language)
    if key is not None:
        return LANG_KEY_MAP[key]

    return episode.selected_language


def _provider_map_for_language(episode):
    language = _language_for_provider_lookup(episode)
    provider_data = episode.provider_data
    data = provider_data._data if hasattr(provider_data, "_data") else provider_data

    for key, providers in data.items():
        if _language_matches(key, language):
            return providers or {}

    try:
        return provider_data.get(language) or {}
    except AttributeError:
        return {}


def _is_implemented_provider(provider):
    return f"get_direct_link_from_{provider.lower()}" in provider_functions


def _auto_provider_candidates(episode):
    available = _provider_map_for_language(episode)
    ordered = get_provider_order()

    candidates = [
        provider
        for provider in ordered
        if provider in available and _is_implemented_provider(provider)
    ]

    if not candidates:
        candidates = [
            provider
            for provider in available
            if provider in SUPPORTED_PROVIDERS and _is_implemented_provider(provider)
        ]

    if not candidates:
        raise ValueError(
            f"No implemented providers are available for {episode.selected_language}"
        )

    return candidates


def _provider_candidates_for_download(episode):
    requested = episode.selected_provider
    if requested == AUTO_PROVIDER:
        return _auto_provider_candidates(episode)
    return [requested]


def _safe_unlink(path, retries=6, delay=0.5):
    for i in range(retries):
        try:
            path.unlink()
            return
        except OSError:
            if i < retries - 1:
                import time
                time.sleep(delay)


def _cleanup_temp_files(episode):
    for suffix in (
        ".temp_full.mkv",
        ".temp_audio.mkv",
        ".temp_video.mkv",
        ".new.mkv",
        ".vidmoly_master.m3u8",
        ".temp_dood.mp4",
    ):
        temp = episode._episode_path.with_suffix(suffix)
        if temp.exists():
            _safe_unlink(temp)

    for temp in episode._episode_path.parent.glob(
        f"{episode._episode_path.stem}.vidmoly_*.m3u8"
    ):
        _safe_unlink(temp)


def _try_aria2c_download(url, output_path, headers) -> bool:
    """Download url with aria2c (16 connections) and stream progress. Returns True on success."""
    try:
        aria2c = str(get_aria2c_path())
    except Exception:
        return False

    cmd = [
        aria2c,
        "--max-connection-per-server=16",
        "--split=16",
        "--allow-overwrite=true",
        "--auto-file-renaming=false",
        "--console-log-level=warn",
        "--summary-interval=1",
        "--out", output_path.name,
        "--dir", str(output_path.parent),
    ]
    for k, v in headers.items():
        cmd += ["--header", f"{k}: {v}"]
    cmd.append(url)

    progress_key = str(getattr(_ffmpeg_local, "queue_id", None) or "global")
    _RE_PCT = re.compile(r"\((\d+)%\)")
    _RE_DL = re.compile(r"DL:([0-9.]+)(GiB|MiB|KiB|B)")

    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        universal_newlines=False,
    )

    with _ffmpeg_progress_lock:
        _ffmpeg_progress[progress_key] = _empty_ffmpeg_progress(active=True)

    buf = bytearray()
    try:
        while True:
            char = process.stdout.read(1)
            if not char:
                break
            if char in (b"\r", b"\n"):
                if buf:
                    line = buf.decode("utf-8", errors="replace")
                    buf.clear()
                    pct_m = _RE_PCT.search(line)
                    if pct_m:
                        pct = float(pct_m.group(1))
                        bw = ""
                        dl_m = _RE_DL.search(line)
                        if dl_m:
                            val, unit = float(dl_m.group(1)), dl_m.group(2)
                            mb = val * 1024 if unit == "GiB" else val if unit == "MiB" else val / 1024
                            bw = f"{mb:.1f} MB/s"
                        with _ffmpeg_progress_lock:
                            _ffmpeg_progress[progress_key] = {
                                "percent": round(pct, 1),
                                "time": "",
                                "speed": "",
                                "bandwidth": bw,
                                "active": True,
                            }
            else:
                buf.extend(char)
    finally:
        with _ffmpeg_progress_lock:
            _ffmpeg_progress[progress_key] = _empty_ffmpeg_progress(active=False)

    process.wait()
    return process.returncode == 0 and output_path.exists()


def _append_query_if_missing(url, query):
    if not query:
        return url

    parsed = urlsplit(url)
    if parsed.query:
        return url

    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment)
    )


def _materialize_vidmoly_variant_playlist(playlist_url, playlist_path, headers, query):
    """Write a local Vidmoly variant playlist with signed segment URLs."""
    resp = GLOBAL_SESSION.get(playlist_url, headers=headers, timeout=30)
    resp.raise_for_status()
    playlist = resp.text
    if "#EXTM3U" not in playlist[:100]:
        return playlist_url

    parsed = urlsplit(playlist_url)
    query = parsed.query or query
    lines = []
    for line in playlist.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            lines.append(line)
            continue

        segment_url = urljoin(playlist_url, stripped)
        lines.append(_append_query_if_missing(segment_url, query))

    playlist_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return playlist_path.name


def _materialize_vidmoly_master_playlist(stream_url, playlist_path, headers):
    """Write local Vidmoly playlists so FFmpeg keeps signed child/segment URLs."""
    parsed_master = urlsplit(stream_url)
    if parsed_master.scheme not in ("http", "https") or ".m3u8" not in parsed_master.path:
        return stream_url

    resp = GLOBAL_SESSION.get(stream_url, headers=headers, timeout=30)
    resp.raise_for_status()
    playlist = resp.text
    if "#EXTM3U" not in playlist[:100]:
        return stream_url

    lines = []
    variant_index = 0
    for line in playlist.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            lines.append(line)
            continue

        child_url = urljoin(stream_url, stripped)
        child_url = _append_query_if_missing(child_url, parsed_master.query)

        if ".m3u8" in urlsplit(child_url).path:
            variant_path = playlist_path.with_name(
                f"{playlist_path.stem}_variant_{variant_index}.m3u8"
            )
            lines.append(
                _materialize_vidmoly_variant_playlist(
                    child_url, variant_path, headers, parsed_master.query
                )
            )
            variant_index += 1
        else:
            lines.append(_append_query_if_missing(child_url, parsed_master.query))

    playlist_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(playlist_path)


# Thread-safe FFmpeg progress by queue item (used by web UI)
_ffmpeg_progress_lock = _threading.Lock()
_ffmpeg_progress = {}
_ffmpeg_local = _threading.local()


def _empty_ffmpeg_progress(active=False):
    return {"percent": 0.0, "time": "", "speed": "", "bandwidth": "", "active": active}


def set_ffmpeg_progress_queue_id(queue_id):
    """Associate FFmpeg progress in the current thread with a queue item."""
    _ffmpeg_local.queue_id = queue_id


def clear_ffmpeg_progress_queue_id():
    """Clear queue association for FFmpeg progress in the current thread."""
    queue_id = getattr(_ffmpeg_local, "queue_id", None)
    _ffmpeg_local.queue_id = None
    if queue_id is not None:
        with _ffmpeg_progress_lock:
            _ffmpeg_progress[str(queue_id)] = _empty_ffmpeg_progress(active=False)


def get_ffmpeg_progress():
    """Return a snapshot of FFmpeg progress keyed by queue item id."""
    with _ffmpeg_progress_lock:
        return {key: dict(value) for key, value in _ffmpeg_progress.items()}


def _parse_ffmpeg_time(time_str):
    """Parse ffmpeg time string (HH:MM:SS.xx) to seconds."""
    try:
        parts = time_str.split(":")
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    except (ValueError, IndexError):
        pass
    return 0.0


def _print_cli_progress(percent, time_str, speed_str, label=""):
    """Print a simple CLI progress bar without ANSI colors."""
    if not sys.stderr.isatty() or _threading.current_thread() is not _threading.main_thread():
        return
    bar_width = 30
    filled = int(bar_width * percent / 100)
    bar = "#" * filled + "-" * (bar_width - filled)
    prefix = f"{label} - " if label else ""
    line = f"\r{prefix}[{bar}] {percent:5.1f}% | {time_str} | {speed_str}  "
    sys.stderr.write(line)
    sys.stderr.flush()


def _run_ffmpeg_with_progress(node, overwrite_output=True, label=""):
    """Run an ffmpeg node and stream its progress output cleanly.

    Includes stall detection: if FFmpeg stops making progress (same frame/time
    values) for STALL_TIMEOUT seconds the process is killed so the caller's
    retry logic can kick in.
    """
    import queue
    import threading
    import time

    STALL_TIMEOUT = (
        600  # 10 minutes without progress → kill (must exceed reconnect_delay_max=300)
    )

    debug_mode = os.getenv("ANIWORLD_DEBUG_MODE", "0") == "1"
    is_tty = (
        sys.stderr.isatty()
        and _threading.current_thread() is _threading.main_thread()
    )

    # Regex to extract progress indicators from ffmpeg status lines
    _RE_FRAME = re.compile(r"frame=\s*(\d+)")
    _RE_TIME = re.compile(r"time=(\S+)")
    _RE_SPEED = re.compile(r"speed=\s*(\S+)")
    _RE_BITRATE = re.compile(r"bitrate=\s*(\S+)")
    _RE_SIZE = re.compile(r"size=\s*(\d+(?:\.\d+)?)\s*([kKmM])(?:i)?B", re.IGNORECASE)
    _RE_DURATION = re.compile(r"Duration:\s*(\d+:\d+:\d+\.\d+)")

    # Use shorter stats_period for smoother progress (1s in non-debug, 10s in debug)
    stats_period = "10" if debug_mode else "1"

    args = ffmpeg.compile(node, overwrite_output=overwrite_output)
    if "-stats_period" not in args:
        args.insert(-1, "-stats_period")
        args.insert(-1, stats_period)

    process = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        universal_newlines=False,
    )

    # --- reader thread: reads stderr byte-by-byte and pushes complete lines ---
    line_queue = queue.Queue()

    def _reader():
        buf = bytearray()
        while True:
            char = process.stderr.read(1)
            if not char:
                # EOF – push whatever is left
                if buf:
                    line_queue.put(buf.decode("utf-8", errors="replace").strip())
                line_queue.put(None)  # sentinel
                return
            if char in (b"\r", b"\n"):
                if buf:
                    line_queue.put(buf.decode("utf-8", errors="replace").strip())
                    buf.clear()
            else:
                buf.extend(char)

    reader_thread = threading.Thread(target=_reader, daemon=True)
    reader_thread.start()

    # --- main loop: consume lines, log them, and watch for stalls ---
    stderr_lines = []  # collect non-progress stderr lines for error reporting
    last_frame = None
    last_time = None
    last_size_kb = None
    last_size_ts = None
    last_change = time.monotonic()
    total_duration = 0.0
    progress_key = str(getattr(_ffmpeg_local, "queue_id", None) or "global")

    with _ffmpeg_progress_lock:
        _ffmpeg_progress[progress_key] = _empty_ffmpeg_progress(active=True)

    try:
        while True:
            try:
                line_str = line_queue.get(timeout=1.0)
            except queue.Empty:
                # No new line within 1 s – just check the stall timer
                if time.monotonic() - last_change > STALL_TIMEOUT:
                    logger.warning(
                        "[FFmpeg] Stall detected – no progress for "
                        f"{STALL_TIMEOUT}s. Killing process."
                    )
                    process.kill()
                    break
                continue

            if line_str is None:
                # Reader thread finished (EOF)
                break

            # Log the line
            if line_str.startswith("frame=") or line_str.startswith("size="):
                # --- extract progress values ---
                cur_frame = None
                cur_time = None
                cur_time_str = ""
                cur_speed_str = ""
                cur_bitrate_str = ""
                cur_bw_str = ""
                m = _RE_FRAME.search(line_str)
                if m:
                    cur_frame = m.group(1)
                m = _RE_TIME.search(line_str)
                if m:
                    cur_time = m.group(1)
                    cur_time_str = m.group(1)
                m = _RE_SPEED.search(line_str)
                if m:
                    cur_speed_str = m.group(1)
                m = _RE_BITRATE.search(line_str)
                if m:
                    cur_bitrate_str = m.group(1)
                    if cur_bitrate_str.lower() == "n/a":
                        cur_bitrate_str = ""
                m = _RE_SIZE.search(line_str)
                if m:
                    size_val = float(m.group(1))
                    size_unit = m.group(2).lower()
                    size_kb = size_val * (1024 if size_unit == "m" else 1)
                    now = time.monotonic()
                    if last_size_kb is not None and last_size_ts is not None:
                        dt = now - last_size_ts
                        if dt > 0:
                            kb_per_sec = (size_kb - last_size_kb) / dt
                            if kb_per_sec > 0:
                                mb_per_sec = kb_per_sec / 1024
                                cur_bw_str = f"{mb_per_sec:.1f} MB/s"
                    last_size_kb = size_kb
                    last_size_ts = now

                # Compute percentage
                percent = 0.0
                if total_duration > 0 and cur_time_str:
                    elapsed = _parse_ffmpeg_time(cur_time_str)
                    percent = min((elapsed / total_duration) * 100, 100.0)

                # Update this queue item's progress for the Web UI.
                with _ffmpeg_progress_lock:
                    current_progress = _ffmpeg_progress.get(
                        progress_key, _empty_ffmpeg_progress(active=True)
                    )
                    current_progress.update(
                        percent=round(percent, 1),
                        time=cur_time_str,
                        speed=cur_speed_str,
                        bandwidth=cur_bw_str or current_progress.get("bandwidth", ""),
                        active=True,
                    )
                    _ffmpeg_progress[progress_key] = current_progress

                if debug_mode:
                    logger.info(f"[FFmpeg Progress] {line_str}")
                elif is_tty:
                    _print_cli_progress(percent, cur_time_str, cur_speed_str, label)

                # --- stall detection ---
                if cur_frame != last_frame or cur_time != last_time:
                    last_frame = cur_frame
                    last_time = cur_time
                    last_change = time.monotonic()
                elif time.monotonic() - last_change > STALL_TIMEOUT:
                    logger.warning(
                        "[FFmpeg] Stall detected – no progress for "
                        f"{STALL_TIMEOUT}s. Killing process."
                    )
                    process.kill()
                    break
            elif line_str:
                # Try to capture total duration from ffmpeg header
                if total_duration == 0.0:
                    dm = _RE_DURATION.search(line_str)
                    if dm:
                        total_duration = _parse_ffmpeg_time(dm.group(1))

                logger.debug(f"[FFmpeg] {line_str}")
                stderr_lines.append(line_str)

        # Clear the progress line in CLI
        if not debug_mode and is_tty:
            sys.stderr.write("\r" + " " * 120 + "\r")
            sys.stderr.flush()

    finally:
        with _ffmpeg_progress_lock:
            _ffmpeg_progress[progress_key] = _empty_ffmpeg_progress(active=False)

    reader_thread.join(timeout=5)
    process.wait()
    if process.returncode != 0:
        detail = (
            "\n".join(stderr_lines[-20:])
            if stderr_lines
            else f"exit code {process.returncode}"
        )
        logger.error(f"[FFmpeg] Process failed (rc={process.returncode}):\n{detail}")
        raise RuntimeError(f"ffmpeg error (rc={process.returncode}): {detail}")


def _download_once_with_current_provider(self):
    check = check_downloaded(self._episode_path)

    headers = PROVIDER_HEADERS_D.get(self.selected_provider, {})
    input_kwargs = {
        "reconnect": 1,
        "reconnect_streamed": 1,
        "reconnect_delay_max": 300,  # wait up to 5 min for connection recovery
    }
    if headers:
        header_list = [f"{k}: {v}" for k, v in headers.items()]
        input_kwargs["headers"] = "\r\n".join(header_list) + "\r\n"

    url = (getattr(self, "url", "") or "").lower()
    is_serienstream = ("serienstream.to" in url) or ("s.to" in url)

    if is_serienstream and hasattr(self, "_normalize_language"):
        audio_enum, sub_enum = self._normalize_language(self.selected_language)
        audio_code = {"German": "deu", "English": "eng"}.get(
            getattr(audio_enum, "value", None)
        )
        if not audio_code:
            raise ValueError(f"Unsupported audio language for serienstream.to: {audio_enum}")
        wants_clean_video = True
        sub_video_code = None
    else:
        selected_key = INVERSE_LANG_LABELS[self.selected_language]
        audio_enum, sub_enum = LANG_KEY_MAP[selected_key]

        audio_code = LANG_CODE_MAP[audio_enum]
        wants_clean_video = sub_enum == Subtitles.NONE
        sub_video_code = None if wants_clean_video else LANG_CODE_MAP[sub_enum]

    has_video = bool(check["video_langs"])
    has_audio = audio_code in check["audio_langs"]

    need_audio = not has_audio
    if not has_video:
        need_video = True
    elif not wants_clean_video:
        need_video = sub_video_code not in check["video_langs"]
    else:
        need_video = False

    if not need_audio and not need_video:
        logger.debug(f"[SKIPPED] {self._file_name}")
        return

    os.makedirs(self._folder_path, exist_ok=True)
    _cleanup_temp_files(self)

    stream_url = self.stream_url
    aria2c_temp = None
    if self.selected_provider == "Doodstream":
        temp_dl = self._episode_path.with_suffix(".temp_dood.mp4")
        if _try_aria2c_download(stream_url, temp_dl, headers):
            logger.debug("[Doodstream] aria2c download complete — using local file")
            aria2c_temp = temp_dl
            stream_url = str(temp_dl)
            input_kwargs = {}
        else:
            logger.debug("[Doodstream] aria2c not available — falling back to ffmpeg")

    if self.selected_provider == "Vidmoly":
        stream_url = _materialize_vidmoly_master_playlist(
            stream_url,
            self._episode_path.with_suffix(".vidmoly_master.m3u8"),
            headers,
        )
        if stream_url.endswith(".vidmoly_master.m3u8"):
            for option in (
                "headers",
                "reconnect",
                "reconnect_streamed",
                "reconnect_delay_max",
            ):
                input_kwargs.pop(option, None)
            input_kwargs["protocol_whitelist"] = "file,http,https,tcp,tls,crypto,data"

    # Label for CLI progress bar (e.g. "Title S01E001")
    ep_label = os.path.splitext(self._file_name)[0] if self._file_name else ""

    full_stream_needed = need_audio and need_video

    temp_audio = self._episode_path.with_suffix(".temp_audio.mkv")
    temp_video = self._episode_path.with_suffix(".temp_video.mkv")
    temp_full = self._episode_path.with_suffix(".temp_full.mkv")

    if full_stream_needed:
        logger.debug(
            f"[DOWNLOADING] full preset with {self.selected_provider} "
            "(audio + video together)"
        )

        stream_metadata = {"metadata:s:a:0": f"language={audio_code}"}
        if (not wants_clean_video) and sub_video_code:
            stream_metadata["metadata:s:v:0"] = f"language={sub_video_code}"

        video_codec = get_video_codec()
        _run_ffmpeg_with_progress(
            ffmpeg.input(stream_url, **input_kwargs).output(
                str(temp_full),
                vcodec=video_codec,
                acodec=video_codec,
                **stream_metadata,
            ),
            label=ep_label,
        )

        if self._episode_path.exists():
            inputs = [
                ffmpeg.input(str(self._episode_path)),
                ffmpeg.input(str(temp_full)),
            ]
            output_path = self._episode_path.with_suffix(".new.mkv")
            _run_ffmpeg_with_progress(ffmpeg.output(*inputs, str(output_path), c="copy"))
            os.replace(output_path, self._episode_path)
        else:
            os.replace(temp_full, self._episode_path)

        if temp_full.exists():
            temp_full.unlink()
        _cleanup_temp_files(self)
        return

    if need_audio:
        logger.debug(f"[DOWNLOADING] audio stream with {self.selected_provider}")
        video_codec = get_video_codec()
        _run_ffmpeg_with_progress(
            ffmpeg.input(stream_url, **input_kwargs).output(
                str(temp_audio),
                acodec=video_codec,
                map="0:a:0?",
                **{"metadata:s:a:0": f"language={audio_code}"},
            ),
            label=ep_label,
        )

    if need_video:
        logger.debug(f"[DOWNLOADING] video stream with {self.selected_provider}")
        video_codec = get_video_codec()
        _run_ffmpeg_with_progress(
            ffmpeg.input(stream_url, **input_kwargs).output(
                str(temp_video),
                vcodec=video_codec,
                map="0:v:0?",
                **(
                    {}
                    if wants_clean_video
                    else {"metadata:s:v:0": f"language={sub_video_code}"}
                ),
            ),
            label=ep_label,
        )

    logger.debug("[MUXING] combining streams")
    inputs = (
        [ffmpeg.input(str(self._episode_path))]
        if self._episode_path.exists()
        else []
    )

    if need_audio:
        inputs.append(ffmpeg.input(str(temp_audio)))
    if need_video:
        inputs.append(ffmpeg.input(str(temp_video)))

    output_path = self._episode_path.with_suffix(".new.mkv")
    _run_ffmpeg_with_progress(ffmpeg.output(*inputs, str(output_path), c="copy"))
    os.replace(output_path, self._episode_path)

    _cleanup_temp_files(self)


def download(self):
    """Download required audio/video streams with retry and optional provider fallback."""
    if platform.system() == "Windows":
        manager = DependencyManager()
        manager.fetch_binary("ffmpeg")

    requested_provider = self.selected_provider
    auto_provider = requested_provider == AUTO_PROVIDER
    provider_candidates = _provider_candidates_for_download(self)
    max_retries = 3
    last_error = None

    if auto_provider:
        series_key = _series_key(self)
        with _provider_cache_lock:
            cached = _provider_cache.get(series_key)
        if cached and cached in provider_candidates:
            provider_candidates = [cached] + [p for p in provider_candidates if p != cached]
            logger.info(f"[AUTO PROVIDER] Cached provider for this anime: {cached}")
    else:
        series_key = None
        cached = None

    for provider in provider_candidates:
        _set_selected_provider(self, provider)
        if auto_provider:
            logger.info(f"[AUTO PROVIDER] Trying {provider}")

        for attempt in range(1, max_retries + 1):
            try:
                _download_once_with_current_provider(self)
                if auto_provider:
                    logger.info(f"[AUTO PROVIDER] Using {provider}")
                    if series_key and _provider_cache.get(series_key) != provider:
                        with _provider_cache_lock:
                            _provider_cache[series_key] = provider
                        _save_provider_cache()
                return
            except Exception as e:
                last_error = e
                _cleanup_temp_files(self)
                logger.error(
                    f"Download attempt {attempt}/{max_retries} with "
                    f"{self.selected_provider} failed: {e}"
                )
                if attempt >= max_retries:
                    break
                _reset_provider_cache(self)
                logger.debug("Retrying download...")

        if auto_provider:
            logger.warning(f"[AUTO PROVIDER] {provider} failed, trying next provider")
            if series_key and cached == provider:
                with _provider_cache_lock:
                    _provider_cache.pop(series_key, None)
                _save_provider_cache()
                logger.info(f"[AUTO PROVIDER] Cleared cached provider for this anime")

    _remove_empty_dirs(self._folder_path, self._base_folder)
    if last_error:
        raise last_error
    raise RuntimeError("Download failed: no provider candidates available")


def watch(self):
    """Watch the current episode with provider headers."""

    print(f"[WATCHING] {self._file_name}")

    headers = PROVIDER_HEADERS_W.get(self.selected_provider, {})
    cmd = [str(get_player_path()), self.stream_url]

    # AniSkip: AniWorld only; ignore for s.to
    aniskip_enabled = os.getenv("ANIWORLD_ANISKIP", "0") == "1"
    if aniskip_enabled and hasattr(self, "skip_times"):
        skip_times = self.skip_times
    else:
        skip_times = None

    if skip_times:
        from ...aniskip import build_mpv_flags, setup_aniskip

        setup_aniskip()
        skip_flags = build_mpv_flags(skip_times).split()
        cmd.extend(skip_flags)
        logger.debug(f"[SKIP TIMES FOUND]: {skip_flags}")

    cmd.extend(
        ["--no-ytdl", "--fs", "--quiet", f"--force-media-title={self._file_name}"]
    )

    if headers:
        header_args = [f"{k}: {v}" for k, v in headers.items()]
        cmd.append("--http-header-fields=" + ",".join(header_args))

    print(" ".join(cmd))
    subprocess.run(cmd)


def syncplay(self):
    """Syncplay an episode (AniWorld + s.to)."""

    print(f"[Syncplaying] {self._file_name}")

    # TODO: implement IINA support for syncplay (Syncplay may not detect IINA binary reliably)
    # Force mpv for now (get_player_path() reads this env var)
    os.environ["ANIWORLD_USE_IINA"] = "0"

    syncplay_host = os.getenv("ANIWORLD_SYNCPLAY_HOST") or "syncplay.pl:8998"
    syncplay_password = os.getenv("ANIWORLD_SYNCPLAY_PASSWORD")

    # getpass.getuser() is usually fine, but can fail in some environments
    syncplay_username = os.getenv("ANIWORLD_SYNCPLAY_USERNAME")

    if not syncplay_username:
        try:
            syncplay_username = getpass.getuser()
        except Exception:
            syncplay_username = "AniWorld-Downloader"

    room = "AniWorld"
    file_name = self._file_name.replace(" ", "_")

    if syncplay_password:
        # Log what we're using to derive the room (helps debugging)
        logger.debug(f"{room}-{file_name}-{syncplay_password}")
        room += (
            "-"
            + hashlib.sha256(
                f"-{file_name}-{syncplay_password}".encode("utf-8")
            ).hexdigest()
        )
    else:
        logger.debug(f"{room}-{file_name}")
        room += f"-{file_name}"

    syncplay_room = os.getenv("ANIWORLD_SYNCPLAY_ROOM") or room

    logger.debug(room)

    cmd = [
        str(get_syncplay_path()),
        "--no-gui",
        "--no-store",
        "--host",
        syncplay_host,
        "--room",
        syncplay_room,
        "--name",
        syncplay_username,
        "--player-path",
        str(get_player_path()),
        self.stream_url,
        # "/Users/phoenixthrush/Downloads/Caramelldansen.webm",
    ]

    # MPV flags come after this
    cmd.append("--")

    aniskip_enabled = os.getenv("ANIWORLD_ANISKIP", "0") == "1"
    skip_times = self.skip_times if aniskip_enabled else None

    if skip_times:
        from ...aniskip import build_mpv_flags, setup_aniskip

        setup_aniskip()
        skip_flags = build_mpv_flags(skip_times).split()
        cmd.extend(skip_flags)
        logger.debug(f"[SKIP TIMES FOUND]: {skip_flags}")

    cmd.extend(
        ["--no-ytdl", "--fs", "--quiet", f"--force-media-title={self._file_name}"]
    )

    headers = PROVIDER_HEADERS_W.get(self.selected_provider, {})

    if headers:
        header_args = [f"{k}: {v}" for k, v in headers.items()]
        cmd.append("--http-header-fields=" + ",".join(header_args))

    logger.debug("\n" + shlex.join(cmd))
    subprocess.run(cmd)


if __name__ == "__main__":
    from aniworld.models import AniworldEpisode

    ep = AniworldEpisode(
        "https://aniworld.to/anime/stream/highschool-dxd/staffel-1/episode-1"
    )

    ep.syncplay()
