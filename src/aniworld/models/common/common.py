import getpass
import hashlib
import os
import platform
import queue
import re
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path

import ffmpeg
import niquests

from ...autodeps import DependencyManager

try:
    from ...autodeps import get_player_path, get_syncplay_path
    from ...config import (
        INVERSE_LANG_LABELS,
        LANG_CODE_MAP,
        LANG_KEY_MAP,
        PROVIDER_HEADERS_D,
        PROVIDER_HEADERS_W,
        Audio,
        Subtitles,
        get_video_codec,
        is_sto_host,
        logger,
    )
except ImportError:
    from aniworld.autodeps import get_player_path, get_syncplay_path
    from aniworld.config import (
        INVERSE_LANG_LABELS,
        LANG_CODE_MAP,
        LANG_KEY_MAP,
        PROVIDER_HEADERS_D,
        PROVIDER_HEADERS_W,
        Audio,
        Subtitles,
        get_video_codec,
        is_sto_host,
        logger,
    )

# Precompile regex for forbidden filename characters
FORBIDDEN_CHARS = re.compile(r'[<>:"/\\|?*]')


def clean_title(title: str) -> str:
    """Clean a string to make it safe for use as a filename."""
    return FORBIDDEN_CHARS.sub("", title).strip()


def _quote_windows_cmd_arg(arg) -> str:
    """Quote one argument for safe cmd.exe copy/paste."""
    arg = str(arg)
    if not arg:
        return '""'

    escaped = ['"']
    backslashes = 0

    for char in arg:
        if char == "\\":
            backslashes += 1
            continue

        if char == '"':
            escaped.append("\\" * (backslashes * 2 + 1))
            escaped.append('"')
            backslashes = 0
            continue

        if backslashes:
            escaped.append("\\" * backslashes)
            backslashes = 0

        escaped.append(char)

    if backslashes:
        escaped.append("\\" * (backslashes * 2))

    escaped.append('"')
    return "".join(escaped)


def format_command_for_shell(cmd, windows: bool | None = None) -> str:
    """Format a subprocess argv list as a shell-safe copy/paste command."""
    if windows is None:
        windows = os.name == "nt"

    if windows:
        return " ".join(_quote_windows_cmd_arg(part) for part in cmd)

    return shlex.join([str(part) for part in cmd])


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
    def get(self, lang_tuple: tuple[Audio, Subtitles]):
        return self._data.get(lang_tuple, {})

    # Behave like a dictionary
    def __getitem__(self, lang_tuple: tuple[Audio, Subtitles]):
        return self._data[lang_tuple]


# -----------------------------------------------------------------------------
# Episode actions (moved from models/*/episode.py)
# -----------------------------------------------------------------------------


def _remove_empty_dirs(folder_path, base_folder, protected=None):
    """Remove folder_path and base_folder if they are empty directories.

    `protected` is never removed. With ANIWORLD_MOVIE_FOLDER=0 a movie's
    "folder" *is* the download root, and a failed download must not delete it.
    """
    try:
        protected = Path(protected).resolve() if protected else None
    except OSError:
        protected = None

    for candidate in (folder_path, base_folder):
        try:
            if not candidate.is_dir():
                continue
            if protected is not None and candidate.resolve() == protected:
                continue
            if not any(candidate.iterdir()):
                candidate.rmdir()
        except OSError:
            pass


def _cleanup_episode_download(self):
    """Remove partial files left by an interrupted or failed episode download."""
    for suffix in (
        ".temp_full.mkv",
        ".temp_audio.mkv",
        ".temp_video.mkv",
        ".temp_full.seg.ts",
        ".new.mkv",
        ".convert.mkv",
        ".convert.mp4",
    ):
        try:
            self._episode_path.with_suffix(suffix).unlink(missing_ok=True)
        except OSError:
            pass

    try:
        from .hls import cleanup_temp_files

        for suffix in (".temp_full.mkv", ".temp_audio.mkv"):
            temp_path = self._episode_path.with_suffix(suffix)
            cleanup_temp_files(temp_path.with_suffix(".hlswork"))
    except (ImportError, OSError):
        pass


def _reset_provider_resolution_cache(self):
    for attr in list(vars(self)):
        if attr.endswith(("__redirect_url", "__provider_url")):
            setattr(self, attr, None)


def _set_selected_provider(self, provider_name):
    descriptor = getattr(type(self), "selected_provider", None)
    if isinstance(descriptor, property) and descriptor.fset is not None:
        descriptor.fset(self, provider_name)
        return
    if getattr(self, "selected_provider", None) == provider_name:
        return
    raise AttributeError("selected_provider cannot be updated for fallback handling")


def _get_provider_attempt_order(self):
    provider_order = []
    provider_method = getattr(self, "provider_attempt_order", None)
    if callable(provider_method):
        provider_order.extend(
            provider for provider in provider_method() if str(provider).strip()
        )

    if not provider_order:
        current_provider = getattr(self, "selected_provider", None)
        if current_provider:
            provider_order.append(current_provider)

    return tuple(dict.fromkeys(provider_order))


def _build_provider_failure_message(action_name, provider_errors):
    details = "; ".join(
        f"{provider}: {error}" for provider, error in provider_errors.items()
    )
    return f"{action_name} failed for all providers. {details}"


def _build_player_header_args(headers):
    # mpv parses --http-header-fields as a comma-separated list, so values
    # containing commas (User-Agent's "(KHTML, like Gecko)", Accept-Language's
    # "en-US,en;q=0.5") get split into malformed header lines and CDNs reply
    # with "400 Bad Request" (issue #200). Use the dedicated single-value
    # options where they exist and append the rest one at a time, which
    # bypasses list splitting entirely.
    args = []
    for key, value in headers.items():
        key_lower = key.lower()
        if key_lower == "user-agent":
            args.append(f"--user-agent={value}")
        elif key_lower == "referer":
            args.append(f"--referrer={value}")
        else:
            args.append(f"--http-header-fields-append={key}: {value}")
    return args


def _build_blocking_player_command(player_path, stream_url):
    player_name = os.path.basename(str(player_path)).lower()
    if player_name.startswith("iina"):
        return [player_path, "--keep-running", stream_url]
    return [player_path, stream_url]


def _resolve_stream_url_with_fallback(self, action_name):
    provider_errors = {}

    for provider_name in _get_provider_attempt_order(self):
        try:
            _set_selected_provider(self, provider_name)
            _reset_provider_resolution_cache(self)
            return self.stream_url, provider_name
        except Exception as exc:
            provider_errors[provider_name] = exc
            logger.warning(
                f"{action_name} setup failed for provider {provider_name}: {exc}"
            )

    if provider_errors:
        raise RuntimeError(
            _build_provider_failure_message(action_name, provider_errors)
        ) from list(provider_errors.values())[-1]

    raise RuntimeError(f"{action_name} failed: no providers available")


# Thread-safe global for current ffmpeg download progress (used by web UI)
_ffmpeg_progress_lock = threading.Lock()
_ffmpeg_progress = {
    "percent": 0.0,
    "time": "",
    "speed": "",
    "bandwidth": "",
    "active": False,
}


def get_ffmpeg_progress():
    """Return a snapshot of the current ffmpeg download progress."""
    with _ffmpeg_progress_lock:
        return dict(_ffmpeg_progress)


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
    if not sys.stderr.isatty():
        return
    bar_width = 30
    filled = int(bar_width * percent / 100)
    bar = "#" * filled + "-" * (bar_width - filled)
    prefix = f"{label} - " if label else ""
    line = f"\r{prefix}[{bar}] {percent:5.1f}% | {time_str} | {speed_str}  "
    sys.stderr.write(line)
    sys.stderr.flush()


class DownloadCancelled(Exception):
    """Raised when we killed the download ourselves, not when it failed."""


def _run_ffmpeg_with_progress(node, overwrite_output=True, label=""):
    """Run an ffmpeg node and stream its progress output cleanly.

    Includes stall detection: if FFmpeg stops making progress (same frame/time
    values) for STALL_TIMEOUT seconds the process is killed so the caller's
    retry logic can kick in.
    """

    STALL_TIMEOUT = (
        60  # 60 seconds without progress → kill (must exceed reconnect_delay_max=30)
    )

    debug_mode = os.getenv("ANIWORLD_DEBUG_MODE", "0") == "1"
    is_tty = sys.stderr.isatty()

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
    cancelled = False

    with _ffmpeg_progress_lock:
        _ffmpeg_progress.update(
            percent=0.0, time="", speed="", bandwidth="", active=True
        )

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
            if line_str.startswith(("frame=", "size=")):
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

                # Update global progress for web UI
                with _ffmpeg_progress_lock:
                    prev_bw = _ffmpeg_progress.get("bandwidth", "")
                    _ffmpeg_progress.update(
                        percent=round(percent, 1),
                        time=cur_time_str,
                        speed=cur_speed_str,
                        bandwidth=cur_bw_str or prev_bw,
                        active=True,
                    )

                if debug_mode:
                    logger.info(f"[FFmpeg Progress] {line_str}")
                elif is_tty:
                    _print_cli_progress(percent, cur_time_str, cur_speed_str, label)

                # --- stall and force cancel detection ---
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

                try:
                    from ...playwright.captcha import _local
                    from ...web.db import is_queue_force_cancelled

                    qid = getattr(_local, "queue_id", None)
                    if qid is not None and is_queue_force_cancelled(qid):
                        logger.info("[FFmpeg] Force cancel requested, stopping.")
                        cancelled = True
                        process.kill()
                        break
                except Exception:
                    pass
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

    except KeyboardInterrupt:
        try:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        except OSError:
            pass
        reader_thread.join(timeout=5)
        raise
    finally:
        with _ffmpeg_progress_lock:
            _ffmpeg_progress.update(
                percent=0.0, time="", speed="", bandwidth="", active=False
            )

    reader_thread.join(timeout=5)
    process.wait()
    # We killed it on purpose, so the non-zero exit code and whatever ffmpeg
    # printed on its way out are not worth reporting.
    if cancelled:
        raise DownloadCancelled("Download cancelled")
    if process.returncode != 0:
        detail = (
            "\n".join(stderr_lines[-20:])
            if stderr_lines
            else f"exit code {process.returncode}"
        )
        logger.warning(f"[FFmpeg] Process failed (rc={process.returncode}):\n{detail}")
        raise RuntimeError(f"ffmpeg error (rc={process.returncode}): {detail}")


def movie_folder_enabled():
    """Whether movies get their own folder instead of landing in the root."""
    return os.getenv("ANIWORLD_MOVIE_FOLDER", "1") != "0"


def _finalize_episode(temp_path, episode_path, label=""):
    """Move `temp_path` onto `episode_path`, remuxing when containers differ.

    The muxer always writes Matroska, so a naming template ending in `.mp4`
    used to produce MKV data inside an `.mp4` file. Remuxing here keeps the
    file honest. Stream copy is tried first; only a codec the target container
    cannot hold forces a re-encode.
    """
    source_ext = temp_path.suffix.lower().lstrip(".")
    target_ext = episode_path.suffix.lower().lstrip(".")

    if target_ext == source_ext or target_ext not in ("mkv", "mp4"):
        os.replace(temp_path, episode_path)
        return

    converted = episode_path.with_suffix(f".convert.{target_ext}")
    output_kwargs = {"c": "copy"}
    if target_ext == "mp4":
        output_kwargs["movflags"] = "+faststart"

    try:
        logger.debug(f"[REMUXING] {source_ext} -> {target_ext}")
        _run_ffmpeg_with_progress(
            ffmpeg.input(str(temp_path)).output(str(converted), **output_kwargs),
            label=label,
        )
    except RuntimeError:
        if target_ext != "mp4":
            raise
        logger.warning(
            "[REMUXING] stream copy into MP4 failed, re-encoding to H.264/AAC"
        )
        converted.unlink(missing_ok=True)
        _run_ffmpeg_with_progress(
            ffmpeg.input(str(temp_path)).output(
                str(converted),
                vcodec="libx264",
                preset="veryfast",
                crf=20,
                acodec="aac",
                audio_bitrate="192k",
                movflags="+faststart",
            ),
            label=label,
        )

    os.replace(converted, episode_path)
    temp_path.unlink(missing_ok=True)


def _download_direct_http(episode_path, stream_url, file_name):
    """Download a video via direct HTTP (e.g. pixeldrain). Shared helper."""
    temp_file = episode_path.with_suffix(".temp_dl.mp4")
    ep_label = os.path.splitext(file_name)[0] if file_name else ""

    try:
        logger.debug(f"[DOWNLOADING] {ep_label} via direct download")
        from ...config import DEFAULT_USER_AGENT

        resp = niquests.get(
            stream_url,
            headers={"User-Agent": DEFAULT_USER_AGENT},
            stream=True,
            timeout=30,
        )
        resp.raise_for_status()

        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        last_ts = time.monotonic()
        last_bytes = 0

        with _ffmpeg_progress_lock:
            _ffmpeg_progress.update(
                percent=0.0, time="", speed="", bandwidth="", active=True
            )

        with open(temp_file, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
                downloaded += len(chunk)

                if total:
                    pct = downloaded / total * 100
                    mb = downloaded / 1024 / 1024
                    total_mb = total / 1024 / 1024

                    now = time.monotonic()
                    dt = now - last_ts
                    bw_str = ""
                    if dt > 0.5:
                        bw = (downloaded - last_bytes) / dt / 1024 / 1024
                        bw_str = f"{bw:.1f} MB/s"
                        last_ts = now
                        last_bytes = downloaded

                    with _ffmpeg_progress_lock:
                        prev_bw = _ffmpeg_progress.get("bandwidth", "")
                        _ffmpeg_progress.update(
                            percent=round(pct, 1),
                            time=f"{mb:.1f}/{total_mb:.1f} MB",
                            speed="",
                            bandwidth=bw_str or prev_bw,
                            active=True,
                        )

                    if sys.stderr.isatty():
                        sys.stderr.write(
                            f"\r{ep_label} - [{int(pct):3d}%] {mb:.1f}/{total_mb:.1f} MB  "
                        )
                        sys.stderr.flush()

        if sys.stderr.isatty():
            sys.stderr.write("\r" + " " * 80 + "\r")
            sys.stderr.flush()

        _finalize_episode(temp_file, episode_path, ep_label)
    except Exception:
        if temp_file.exists():
            temp_file.unlink()
        raise
    finally:
        with _ffmpeg_progress_lock:
            _ffmpeg_progress.update(
                percent=0.0, time="", speed="", bandwidth="", active=False
            )


def _download_hls_stream(episode_path, stream_url, file_name, audio_lang="jpn"):
    """Download a Hanime HLS stream with per-segment retries."""
    ep_label = os.path.splitext(file_name)[0] if file_name else ""
    temp_full = episode_path.with_suffix(".temp_full.mkv")
    temp_prefix = episode_path.with_suffix(".hanime_hls")

    try:
        logger.debug(f"[DOWNLOADING] {ep_label} via HLS stream")
        video_codec = get_video_codec()
        from ...config import DEFAULT_USER_AGENT
        from .hls import HLSUnsupported, cleanup_temp_files, download_hls_parallel

        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Referer": "https://hanime.tv/",
            "Origin": "https://hanime.tv",
        }
        try:
            written = download_hls_parallel(
                stream_url,
                temp_prefix,
                headers=headers,
                preferred_audio_lang=audio_lang,
                label=ep_label,
            )
        except HLSUnsupported as exc:
            logger.debug(
                f"[HLS] parallel Hanime download unsupported ({exc}); using FFmpeg"
            )
            written = []

        if written:
            if len(written) > 1:
                node = ffmpeg.output(
                    ffmpeg.input(str(written[0])).video,
                    ffmpeg.input(str(written[1])).audio,
                    str(temp_full),
                    vcodec=video_codec,
                    acodec="copy",
                    **{"metadata:s:a:0": f"language={audio_lang}"},
                )
            else:
                node = ffmpeg.input(str(written[0])).output(
                    str(temp_full),
                    vcodec=video_codec,
                    acodec="copy",
                    **{"metadata:s:a:0": f"language={audio_lang}"},
                )
            _run_ffmpeg_with_progress(node, label=ep_label)
        else:
            _download_full_stream(
                stream_url,
                temp_full,
                {
                    "reconnect": 1,
                    "reconnect_streamed": 1,
                    "reconnect_delay_max": 30,
                    "allowed_extensions": "ALL",
                },
                headers,
                {"metadata:s:a:0": f"language={audio_lang}"},
                video_codec,
                ep_label,
                audio_lang,
            )

        _finalize_episode(temp_full, episode_path, ep_label)
    except Exception:
        if temp_full.exists():
            temp_full.unlink()
        raise
    finally:
        try:
            cleanup_temp_files(temp_prefix)
        except (ImportError, NameError, UnboundLocalError):
            pass


def download_hanime(self):
    """Download through Hanime only, refreshing expired streams on failure."""
    if platform.system() == "Windows":
        manager = DependencyManager()
        manager.fetch_binary("ffmpeg")

    if self._episode_path.exists():
        logger.debug(f"[SKIPPED] {self._file_name} (already downloaded)")
        return

    os.makedirs(self._folder_path, exist_ok=True)
    last_error = None
    for attempt in range(1, 4):
        try:
            if attempt == 1:
                stream_url = self.stream_url
            else:
                stream_url = self.refresh_stream_url()
            _download_hls_stream(self._episode_path, stream_url, self._file_name)
            return
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                logger.warning(
                    f"Hanime download attempt {attempt}/3 failed: {exc}; retrying with a fresh stream"
                )
                time.sleep(attempt)

    raise RuntimeError(
        f"Hanime download failed after 3 attempts: {last_error}"
    ) from last_error


class _HLSManualUnsupported(Exception):
    """Raised when the manual HLS segment fetcher can't handle a playlist."""


_HLS_MEDIA_EXTS = (".ts", ".m4s", ".mp4", ".m4a", ".m4v", ".aac", ".mp3", ".mov")


def _fetch_hls_segment(session, seg_url, headers, hosts, timeout=90):
    """Download one HLS segment, failing over across mirror hosts.

    cineby serves every segment from a rotating pool of mirror hosts that all
    return byte-identical content, so a single host's transient failure (e.g. a
    Cloudflare 522 origin timeout) no longer has to abort the whole download — we
    retry the same path on the other mirrors (two passes, short backoff) before
    giving up. Segments on a single host still just retry that host.
    """
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(seg_url)
    ordered = [parsed.netloc] + [h for h in hosts if h and h != parsed.netloc]
    last_exc = None
    for attempt in range(2):
        for host in ordered:
            url = urlunparse(parsed._replace(netloc=host))
            try:
                resp = session.get(url, headers=headers, timeout=timeout)
                resp.raise_for_status()
                return resp.content
            except Exception as exc:
                last_exc = exc
        if attempt == 0:
            time.sleep(1.0)
    raise last_exc


def _hls_uris(playlist, base_url):
    from urllib.parse import urljoin

    return [
        urljoin(base_url, line.strip())
        for line in playlist.splitlines()
        if line.strip() and not line.startswith("#")
    ]


def _download_hls_manual(m3u8_url, headers, temp_ts, label=""):
    """Fetch an HLS media playlist's segments over plain HTTP into `temp_ts`.

    Some hosters (cineby) disguise their segments with non-media extensions
    (`.jpg`, `.css`, `.txt`) served from rotating hosts. Strict FFmpeg builds
    refuse those through the HLS demuxer even with `-allowed_extensions ALL`, so
    we bypass the demuxer entirely: download each segment ourselves (they are
    plain MPEG-TS) and concatenate them, then let FFmpeg remux the local file.

    Raises `_HLSManualUnsupported` for playlists this simple path shouldn't take
    over (a master with no usable variant, AES-encrypted segments, or ordinary
    `.ts` segments that FFmpeg already handles well).
    """
    session = niquests.Session()
    req_headers = {"Accept-Encoding": "identity"}
    req_headers.update(headers or {})

    resp = session.get(m3u8_url, headers=req_headers, timeout=30)
    resp.raise_for_status()
    playlist = resp.text
    if "#EXTM3U" not in playlist:
        raise _HLSManualUnsupported("not an m3u8 playlist")

    # Master playlist → follow the last (usually highest-quality) variant.
    if "#EXT-X-STREAM-INF" in playlist:
        variants = _hls_uris(playlist, m3u8_url)
        if not variants:
            raise _HLSManualUnsupported("master playlist with no variants")
        m3u8_url = variants[-1]
        resp = session.get(m3u8_url, headers=req_headers, timeout=30)
        resp.raise_for_status()
        playlist = resp.text

    if "#EXT-X-KEY" in playlist:
        raise _HLSManualUnsupported("encrypted playlist")

    segments = _hls_uris(playlist, m3u8_url)
    if not segments:
        raise _HLSManualUnsupported("no segments")

    def _is_standard(url):
        path = url.split("?", 1)[0].lower()
        return path.endswith(_HLS_MEDIA_EXTS)

    if all(_is_standard(url) for url in segments):
        raise _HLSManualUnsupported("standard segments (leave to ffmpeg)")

    # Pool of interchangeable mirror hosts to fail a segment over to (see
    # _fetch_hls_segment): every host the playlist uses, plus the playlist's own.
    from urllib.parse import urlparse

    seg_hosts = list(
        dict.fromkeys(
            [urlparse(u).netloc for u in segments] + [urlparse(m3u8_url).netloc]
        )
    )

    total = len(segments)
    ep = os.path.splitext(label)[0] if label else ""
    logger.debug(f"[DOWNLOADING] {ep} via manual HLS ({total} segments)")
    try:
        with open(temp_ts, "wb") as out:
            for index, seg_url in enumerate(segments, start=1):
                out.write(_fetch_hls_segment(session, seg_url, req_headers, seg_hosts))
                percent = round(index / total * 100, 1)
                with _ffmpeg_progress_lock:
                    _ffmpeg_progress.update(
                        percent=percent,
                        time=f"{index}/{total} segments",
                        speed="",
                        bandwidth="",
                        active=True,
                    )
    except Exception:
        try:
            temp_ts.unlink(missing_ok=True)
        except Exception:
            pass
        raise
    finally:
        with _ffmpeg_progress_lock:
            _ffmpeg_progress.update(
                percent=0.0, time="", speed="", bandwidth="", active=False
            )


def _hls_rendition_download(stream_url, temp_prefix, headers, audio_code, ep_label):
    """Fetch an HLS stream, selecting the ``audio_code`` audio rendition.

    Used when the wanted audio (e.g. a German dub on cineby) is a *separate*
    ``#EXT-X-MEDIA:TYPE=AUDIO`` rendition inside a multi-audio master rather than
    the muxed default — the plain FFmpeg/manual paths would grab the default
    track instead. Returns ``(video_path, audio_path)`` (``audio_path`` is None
    when the stream turned out to be muxed after all), or None when the parallel
    downloader can't handle the playlist and the caller should fall back.
    """
    from .hls import HLSUnsupported, download_hls_parallel

    try:
        written = download_hls_parallel(
            stream_url,
            temp_prefix,
            headers=headers,
            preferred_audio_lang=audio_code,
            label=ep_label,
        )
    except HLSUnsupported as exc:
        logger.debug(f"[HLS] rendition download unsupported ({exc}); falling back")
        return None
    if not written:
        return None
    video = written[0]
    audio = written[1] if len(written) >= 2 else None
    return video, audio


def _download_full_stream(
    stream_url,
    temp_full,
    input_kwargs,
    headers,
    stream_metadata,
    video_codec,
    ep_label,
    audio_code,
):
    """Fetch audio+video into `temp_full`.

    For an HLS playlist we first try the manual segment fetcher (needed for
    hosters that disguise segments with non-media extensions); it opts out for
    normal/encrypted playlists, which then take the FFmpeg path.
    """
    if ".m3u8" in stream_url.split("?", 1)[0].lower():
        temp_ts = temp_full.with_suffix(".seg.ts")
        try:
            _download_hls_manual(stream_url, headers, temp_ts, ep_label)
        except _HLSManualUnsupported as exc:
            logger.debug(f"[HLS] manual fetch not used ({exc}); using FFmpeg")
        else:
            try:
                _run_ffmpeg_with_progress(
                    ffmpeg.input(str(temp_ts)).output(
                        str(temp_full),
                        vcodec=video_codec,
                        acodec="copy",
                        **stream_metadata,
                    ),
                    label=ep_label,
                )
                return
            finally:
                temp_ts.unlink(missing_ok=True)

    _run_ffmpeg_with_progress(
        ffmpeg.input(stream_url, **input_kwargs).output(
            str(temp_full),
            vcodec=video_codec,
            acodec="copy",
            **stream_metadata,
        ),
        label=ep_label,
    )


def download(self):
    """Download required audio/video streams for an episode (AniWorld + serienstream.to) with retry logic."""
    if platform.system() == "Windows":
        manager = DependencyManager()
        manager.fetch_binary("ffmpeg")

    max_retries = 3
    provider_order = _get_provider_attempt_order(self)
    provider_errors = {}

    for provider_index, provider_name in enumerate(provider_order):
        _set_selected_provider(self, provider_name)

        for attempt in range(1, max_retries + 1):
            try:
                _reset_provider_resolution_cache(self)
                stream_url = self.stream_url
                check = check_downloaded(self._episode_path)

                headers = PROVIDER_HEADERS_D.get(provider_name, {})
                input_kwargs = {
                    "reconnect": 1,
                    "reconnect_streamed": 1,
                    "reconnect_delay_max": 30,  # wait up to 30s for connection recovery
                }
                # Cineby (and some other hosters) disguise their HLS segments with
                # non-.ts extensions like .jpg; ffmpeg 7+ refuses those by default
                # ("not in allowed_segment_extensions"), so allow every segment
                # extension for m3u8 inputs.
                if ".m3u8" in (stream_url or "").split("?", 1)[0].lower():
                    input_kwargs["allowed_extensions"] = "ALL"
                if headers:
                    header_list = [f"{k}: {v}" for k, v in headers.items()]
                    input_kwargs["headers"] = "\r\n".join(header_list) + "\r\n"

                # Covers every host in config.STO_DOMAINS/STO_IP
                is_serienstream = is_sto_host(getattr(self, "url", "") or "")

                if is_serienstream and hasattr(self, "_normalize_language"):
                    audio_enum, sub_enum = self._normalize_language(
                        self.selected_language
                    )
                    audio_code = {"German": "deu", "English": "eng"}.get(
                        getattr(audio_enum, "value", None)
                    )
                    if not audio_code:
                        raise ValueError(
                            f"Unsupported audio language for serienstream.to: {audio_enum}"
                        )
                    wants_clean_video = True
                    sub_video_code = None
                else:
                    selected_key = INVERSE_LANG_LABELS[self.selected_language]
                    audio_enum, sub_enum = LANG_KEY_MAP[selected_key]

                    audio_code = LANG_CODE_MAP[audio_enum]
                    wants_clean_video = sub_enum == Subtitles.NONE
                    sub_video_code = (
                        None if wants_clean_video else LANG_CODE_MAP[sub_enum]
                    )

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

                ep_label = (
                    os.path.splitext(self._file_name)[0] if self._file_name else ""
                )

                full_stream_needed = need_audio and need_video

                # Some providers (cineby's German dub) serve the wanted audio as
                # a separate HLS rendition rather than the muxed default; the
                # episode opts into rendition-aware fetching so we pick the right
                # track instead of the default one.
                select_rendition = getattr(self, "_separate_audio_rendition", False)

                temp_audio = self._episode_path.with_suffix(".temp_audio.mkv")
                temp_video = self._episode_path.with_suffix(".temp_video.mkv")
                temp_full = self._episode_path.with_suffix(".temp_full.mkv")

                if full_stream_needed:
                    logger.debug(
                        f"[DOWNLOADING] full preset (audio + video together) via {provider_name}"
                    )

                    stream_metadata = {"metadata:s:a:0": f"language={audio_code}"}
                    if (not wants_clean_video) and sub_video_code:
                        stream_metadata["metadata:s:v:0"] = f"language={sub_video_code}"

                    video_codec = get_video_codec()
                    rendition_done = False
                    if select_rendition:
                        from .hls import cleanup_temp_files

                        temp_prefix = temp_full.with_suffix(".hlswork")
                        result = _hls_rendition_download(
                            stream_url, temp_prefix, headers, audio_code, ep_label
                        )
                        if result is not None:
                            video_path, audio_path = result
                            try:
                                if audio_path is not None:
                                    node = ffmpeg.output(
                                        ffmpeg.input(str(video_path)).video,
                                        ffmpeg.input(str(audio_path)).audio,
                                        str(temp_full),
                                        vcodec=video_codec,
                                        acodec=video_codec,
                                        **stream_metadata,
                                    )
                                else:
                                    node = ffmpeg.input(str(video_path)).output(
                                        str(temp_full),
                                        vcodec=video_codec,
                                        acodec=video_codec,
                                        **stream_metadata,
                                    )
                                _run_ffmpeg_with_progress(node, label=ep_label)
                                rendition_done = True
                            finally:
                                cleanup_temp_files(temp_prefix)

                    if not rendition_done:
                        _download_full_stream(
                            stream_url,
                            temp_full,
                            input_kwargs,
                            headers,
                            stream_metadata,
                            video_codec,
                            ep_label,
                            audio_code,
                        )

                    if self._episode_path.exists():
                        inputs = [
                            ffmpeg.input(str(self._episode_path)),
                            ffmpeg.input(str(temp_full)),
                        ]
                        output_path = self._episode_path.with_suffix(".new.mkv")
                        _run_ffmpeg_with_progress(
                            ffmpeg.output(*inputs, str(output_path), c="copy")
                        )
                        _finalize_episode(output_path, self._episode_path, ep_label)
                    else:
                        _finalize_episode(temp_full, self._episode_path, ep_label)

                    if temp_full.exists():
                        temp_full.unlink()
                    return

                if need_audio:
                    logger.debug(f"[DOWNLOADING] audio stream via {provider_name}")
                    video_codec = get_video_codec()
                    audio_done = False
                    if select_rendition:
                        # Pull just the wanted audio rendition (e.g. the German
                        # dub) rather than the master's default track.
                        from .hls import cleanup_temp_files

                        temp_prefix = temp_audio.with_suffix(".hlswork")
                        result = _hls_rendition_download(
                            stream_url, temp_prefix, headers, audio_code, ep_label
                        )
                        if result is not None:
                            _, audio_path = result
                            audio_src = audio_path or result[0]
                            try:
                                _run_ffmpeg_with_progress(
                                    ffmpeg.input(str(audio_src)).output(
                                        str(temp_audio),
                                        acodec=video_codec,
                                        map="0:a:0?",
                                        **{"metadata:s:a:0": f"language={audio_code}"},
                                    ),
                                    label=ep_label,
                                )
                                audio_done = True
                            finally:
                                cleanup_temp_files(temp_prefix)
                    if not audio_done:
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
                    logger.debug(f"[DOWNLOADING] video stream via {provider_name}")
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
                _run_ffmpeg_with_progress(
                    ffmpeg.output(*inputs, str(output_path), c="copy")
                )
                _finalize_episode(output_path, self._episode_path, ep_label)

                for f in (temp_audio, temp_video):
                    if f.exists():
                        f.unlink()

                return

            except KeyboardInterrupt:
                _cleanup_episode_download(self)
                _remove_empty_dirs(
                    self._folder_path,
                    self._base_folder,
                    protected=getattr(self, "selected_path", None),
                )
                raise

            except DownloadCancelled:
                # The user stopped this, so clean up and get out instead of
                # logging a failure and trying the next provider.
                _cleanup_episode_download(self)
                if self._episode_path.exists():
                    self._episode_path.unlink()
                _remove_empty_dirs(
                    self._folder_path,
                    self._base_folder,
                    protected=getattr(self, "selected_path", None),
                )
                raise

            except Exception as e:
                _cleanup_episode_download(self)

                try:
                    from ...playwright.captcha import _local
                    from ...web.db import is_queue_force_cancelled

                    qid = getattr(_local, "queue_id", None)
                    if qid is not None and is_queue_force_cancelled(qid):
                        if self._episode_path.exists():
                            self._episode_path.unlink()
                        _remove_empty_dirs(
                            self._folder_path,
                            self._base_folder,
                            protected=getattr(self, "selected_path", None),
                        )
                        raise
                except Exception as inner_e:
                    if inner_e is e:
                        raise

                provider_errors[provider_name] = e
                logger.warning(
                    f"Download attempt {attempt}/{max_retries} failed for provider "
                    f"{provider_name}: {e}"
                )
                if attempt < max_retries:
                    logger.debug(f"Retrying download with provider {provider_name}...")
                    continue

                next_provider = None
                if provider_index + 1 < len(provider_order):
                    next_provider = provider_order[provider_index + 1]
                if next_provider:
                    logger.warning(
                        f"Falling back from provider {provider_name} to "
                        f"{next_provider} for {getattr(self, 'url', 'episode')}"
                    )

    _remove_empty_dirs(
        self._folder_path,
        self._base_folder,
        protected=getattr(self, "selected_path", None),
    )
    if provider_errors:
        raise RuntimeError(
            _build_provider_failure_message("Download", provider_errors)
        ) from list(provider_errors.values())[-1]
    raise RuntimeError("Download failed: no providers available")


def watch(self):
    """Watch the current episode with provider headers."""

    print(f"[WATCHING] {self._file_name}")

    player_path = str(get_player_path())
    provider_order = _get_provider_attempt_order(self)
    provider_errors = {}

    # AniSkip: AniWorld only; ignore for serienstream.to
    aniskip_enabled = os.getenv("ANIWORLD_ANISKIP", "0") == "1"
    if aniskip_enabled and hasattr(self, "skip_times"):
        skip_times = self.skip_times
    else:
        skip_times = None

    if skip_times:
        from ...aniskip import build_mpv_flags, setup_aniskip

        setup_aniskip()
        skip_flags = build_mpv_flags(skip_times).split()
        logger.debug(f"[SKIP TIMES FOUND]: {skip_flags}")
    else:
        skip_flags = []

    base_args = [
        "--no-ytdl",
        "--fs",
        "--quiet",
        f"--force-media-title={self._file_name}",
    ]

    for provider_index, provider_name in enumerate(provider_order):
        _set_selected_provider(self, provider_name)
        max_retries = 3

        for attempt in range(1, max_retries + 1):
            try:
                _reset_provider_resolution_cache(self)
                stream_url = self.stream_url
                headers = PROVIDER_HEADERS_W.get(provider_name, {})
                cmd = _build_blocking_player_command(player_path, stream_url)

                if skip_flags:
                    cmd.extend(skip_flags)

                cmd.extend(base_args)

                if headers:
                    cmd.extend(_build_player_header_args(headers))

                print(format_command_for_shell(cmd))
                process = subprocess.run(cmd, check=False)
                if process.returncode != 0:
                    raise RuntimeError(f"player exited with code {process.returncode}")
                return
            except Exception as e:
                provider_errors[provider_name] = e
                logger.warning(
                    f"Watch attempt {attempt}/{max_retries} failed for provider "
                    f"{provider_name}: {e}"
                )
                if attempt < max_retries:
                    logger.debug(f"Retrying watch with provider {provider_name}...")
                    continue

                next_provider = None
                if provider_index + 1 < len(provider_order):
                    next_provider = provider_order[provider_index + 1]
                if next_provider:
                    logger.warning(
                        f"Falling back from provider {provider_name} to "
                        f"{next_provider} for {getattr(self, 'url', 'episode')}"
                    )

    if provider_errors:
        raise RuntimeError(
            _build_provider_failure_message("Watch", provider_errors)
        ) from list(provider_errors.values())[-1]
    raise RuntimeError("Watch failed: no providers available")


def syncplay(self):
    """Syncplay an episode (AniWorld + serienstream.to)."""

    print(f"[Syncplaying] {self._file_name}")

    # TODO: implement IINA support for syncplay (Syncplay may not detect IINA binary reliably)
    # Force mpv for now (get_player_path() reads this env var)
    os.environ["ANIWORLD_USE_IINA"] = "0"

    stream_url, provider_name = _resolve_stream_url_with_fallback(self, "Syncplay")

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
            + hashlib.sha256(f"-{file_name}-{syncplay_password}".encode()).hexdigest()
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
        stream_url,
        # "/Users/phoenixthrush/Downloads/Caramelldansen.webm",
    ]

    # MPV flags come after this
    cmd.append("--")

    aniskip_enabled = os.getenv("ANIWORLD_ANISKIP", "0") == "1"
    skip_times = None
    if aniskip_enabled and hasattr(self, "skip_times"):
        skip_times = self.skip_times

    if skip_times:
        from ...aniskip import build_mpv_flags, setup_aniskip

        setup_aniskip()
        skip_flags = build_mpv_flags(skip_times).split()
        cmd.extend(skip_flags)
        logger.debug(f"[SKIP TIMES FOUND]: {skip_flags}")

    cmd.extend(
        ["--no-ytdl", "--fs", "--quiet", f"--force-media-title={self._file_name}"]
    )

    headers = PROVIDER_HEADERS_W.get(provider_name, {})

    if headers:
        cmd.extend(_build_player_header_args(headers))

    print(format_command_for_shell(cmd))
    logger.debug("\n" + format_command_for_shell(cmd))
    subprocess.run(cmd, check=False)


if __name__ == "__main__":
    from aniworld.models import AniworldEpisode

    ep = AniworldEpisode(
        "https://aniworld.to/anime/stream/highschool-dxd/staffel-1/episode-1"
    )

    ep.syncplay()
