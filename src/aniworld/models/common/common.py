import getpass
import hashlib
import os
import platform
import re
import shlex
import subprocess
import sys
import threading as _threading
from typing import Tuple

import ffmpeg

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
        logger,
    )

# Precompile regex for forbidden filename characters
FORBIDDEN_CHARS = re.compile(r'[<>:"/\\|?*]')


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


# Thread-safe global for current ffmpeg download progress (used by web UI)
_ffmpeg_progress_lock = _threading.Lock()
_ffmpeg_progress = {"percent": 0.0, "time": "", "speed": "", "active": False}


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


def _run_ffmpeg_with_progress(node, overwrite_output=True, label=""):
    """Run an ffmpeg node and stream its progress output cleanly.

    Includes stall detection: if FFmpeg stops making progress (same frame/time
    values) for STALL_TIMEOUT seconds the process is killed so the caller's
    retry logic can kick in.
    """
    import queue
    import threading
    import time

    STALL_TIMEOUT = 600  # 10 minutes without progress → kill (must exceed reconnect_delay_max=300)

    debug_mode = os.getenv("ANIWORLD_DEBUG_MODE", "0") == "1"
    is_tty = sys.stderr.isatty()

    # Regex to extract progress indicators from ffmpeg status lines
    _RE_FRAME = re.compile(r"frame=\s*(\d+)")
    _RE_TIME = re.compile(r"time=(\S+)")
    _RE_SPEED = re.compile(r"speed=\s*(\S+)")
    _RE_DURATION = re.compile(r"Duration:\s*(\d+:\d+:\d+\.\d+)")

    # Use shorter stats_period for smoother progress (1s in non-debug, 10s in debug)
    stats_period = "10" if debug_mode else "1"

    args = ffmpeg.compile(node, overwrite_output=overwrite_output)
    if "-stats_period" not in args:
        args.insert(-1, "-stats_period")
        args.insert(-1, stats_period)

    process = subprocess.Popen(
        args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, universal_newlines=False
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
    last_change = time.monotonic()
    total_duration = 0.0

    with _ffmpeg_progress_lock:
        _ffmpeg_progress.update(percent=0.0, time="", speed="", active=True)

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

                # Compute percentage
                percent = 0.0
                if total_duration > 0 and cur_time_str:
                    elapsed = _parse_ffmpeg_time(cur_time_str)
                    percent = min((elapsed / total_duration) * 100, 100.0)

                # Update global progress for web UI
                with _ffmpeg_progress_lock:
                    _ffmpeg_progress.update(
                        percent=round(percent, 1),
                        time=cur_time_str,
                        speed=cur_speed_str,
                        active=True,
                    )

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
            _ffmpeg_progress.update(percent=0.0, time="", speed="", active=False)

    reader_thread.join(timeout=5)
    process.wait()
    if process.returncode != 0:
        detail = "\n".join(stderr_lines[-20:]) if stderr_lines else f"exit code {process.returncode}"
        logger.error(f"[FFmpeg] Process failed (rc={process.returncode}):\n{detail}")
        raise RuntimeError(f"ffmpeg error (rc={process.returncode}): {detail}")


def download(self):
    """Download required audio/video streams for an episode (AniWorld + s.to) with retry logic."""
    if platform.system() == "Windows":
        manager = DependencyManager()
        manager.fetch_binary("ffmpeg")

    max_retries = 3
    attempt = 0

    while attempt < max_retries:
        try:
            attempt += 1
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

            # Label for CLI progress bar (e.g. "Title S01E001")
            ep_label = os.path.splitext(self._file_name)[0] if self._file_name else ""

            full_stream_needed = need_audio and need_video

            temp_audio = self._episode_path.with_suffix(".temp_audio.mkv")
            temp_video = self._episode_path.with_suffix(".temp_video.mkv")
            temp_full = self._episode_path.with_suffix(".temp_full.mkv")

            if full_stream_needed:
                logger.debug("[DOWNLOADING] full preset (audio + video together)")

                stream_metadata = {"metadata:s:a:0": f"language={audio_code}"}
                if (not wants_clean_video) and sub_video_code:
                    stream_metadata["metadata:s:v:0"] = f"language={sub_video_code}"

                video_codec = get_video_codec()
                _run_ffmpeg_with_progress(
                    ffmpeg.input(self.stream_url, **input_kwargs).output(
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
                    _run_ffmpeg_with_progress(
                        ffmpeg.output(*inputs, str(output_path), c="copy")
                    )
                    os.replace(output_path, self._episode_path)
                else:
                    os.replace(temp_full, self._episode_path)

                if temp_full.exists():
                    temp_full.unlink()
                return

            if need_audio:
                logger.debug("[DOWNLOADING] audio stream")
                video_codec = get_video_codec()
                _run_ffmpeg_with_progress(
                    ffmpeg.input(self.stream_url, **input_kwargs).output(
                        str(temp_audio),
                        acodec=video_codec,
                        map="0:a:0?",
                        **{"metadata:s:a:0": f"language={audio_code}"},
                    ),
                    label=ep_label,
                )

            if need_video:
                logger.debug("[DOWNLOADING] video stream")
                video_codec = get_video_codec()
                _run_ffmpeg_with_progress(
                    ffmpeg.input(self.stream_url, **input_kwargs).output(
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
            os.replace(output_path, self._episode_path)

            for f in (temp_audio, temp_video):
                if f.exists():
                    f.unlink()

            # If download succeeds, exit loop
            break

        except Exception as e:
            # Clean up temp files from failed attempt
            for suffix in (".temp_full.mkv", ".temp_audio.mkv", ".temp_video.mkv", ".new.mkv"):
                temp = self._episode_path.with_suffix(suffix)
                if temp.exists():
                    temp.unlink()

            logger.error(f"Download attempt {attempt}/{max_retries} failed: {e}")
            if attempt >= max_retries:
                _remove_empty_dirs(self._folder_path, self._base_folder)
                raise
            else:
                # Reset cached URL properties so retry resolves fresh URLs
                for attr in list(vars(self)):
                    if attr.endswith("__redirect_url") or attr.endswith(
                        "__provider_url"
                    ):
                        setattr(self, attr, None)
                logger.debug("Retrying download...")


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
