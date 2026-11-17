"""Subtitles the broadcasters publish next to their videos, saved as SRT.

The broadcasters serve two formats:
    TTML / EBU-TT-D   ARD and its regional channels, ZDF, 3sat, KiKA, ORF, SRF
    WebVTT            Arte

Both become a sidecar "<video name>.<lang>.srt", which every player and media
server (Jellyfin, Plex, Kodi) picks up next to the video.
"""

import html
import re
from pathlib import Path
from xml.etree import ElementTree

try:
    from ...config import DEFAULT_USER_AGENT, GLOBAL_SESSION, logger
except ImportError:
    from aniworld.config import DEFAULT_USER_AGENT, GLOBAL_SESSION, logger

# Some ARD files count from a 10:00:00 tape start instead of zero.
_TAPE_START = 10 * 3600

_CLOCK = re.compile(r"^(\d+):(\d{1,2}):(\d{1,2})(?:([.:])(\d+))?$")
_OFFSET = re.compile(r"^([\d.]+)(h|m|s|ms|f|t)$")
_VTT_TIME = re.compile(
    r"((?:\d+:)?\d{1,2}:\d{2}[.,]\d{3})\s*-->\s*((?:\d+:)?\d{1,2}:\d{2}[.,]\d{3})"
)
_TAGS = re.compile(r"<[^>]+>")


class SubtitleError(ValueError):
    """The file is neither TTML nor WebVTT, or holds no cues."""


def fetch(url, timeout=30):
    response = GLOBAL_SESSION.get(
        url,
        headers={"User-Agent": DEFAULT_USER_AGENT, "Accept-Encoding": "gzip, deflate"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.content.decode("utf-8-sig", errors="replace")


def to_srt(text):
    """Convert TTML or WebVTT text to SRT."""
    stripped = text.lstrip()
    if stripped.startswith("WEBVTT"):
        cues = _vtt_cues(stripped)
    elif "<" in stripped[:200]:
        cues = _ttml_cues(stripped)
    else:
        raise SubtitleError("Unknown subtitle format")
    cues = [cue for cue in cues if cue[2].strip()]
    if not cues:
        raise SubtitleError("Subtitle file has no cues")
    if all(start >= _TAPE_START for start, _, _ in cues):
        cues = [(s - _TAPE_START, e - _TAPE_START, t) for s, e, t in cues]
    return "\n".join(
        f"{index}\n{_srt_time(start)} --> {_srt_time(end)}\n{body}\n"
        for index, (start, end, body) in enumerate(cues, 1)
    )


def save(url, video_path, language="de"):
    """Download the subtitle for `video_path` and write it beside it as SRT.

    Returns the written path, or None when the subtitle could not be read. A
    missing subtitle must never fail the video download it belongs to.
    """
    target = Path(video_path).with_suffix(f".{language}.srt")
    if target.exists():
        return target
    try:
        srt = to_srt(fetch(url))
    except Exception as exc:
        logger.warning("Subtitle for %s skipped: %s", Path(video_path).name, exc)
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(srt, encoding="utf-8")
    logger.debug("Subtitle saved: %s", target)
    return target


# -----------------------------
# TTML / EBU-TT-D
# -----------------------------


def _local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _ttml_cues(text):
    # Subtitle files come from outside; they never need a DOCTYPE or entities,
    # so refuse those outright rather than lean on the parser's limits.
    if re.search(r"<!(?:DOCTYPE|ENTITY)", text, re.IGNORECASE):
        raise SubtitleError("TTML with a DOCTYPE or entities is not accepted")
    try:
        root = ElementTree.fromstring(text.encode("utf-8"))
    except ElementTree.ParseError as exc:
        raise SubtitleError(f"Broken TTML: {exc}") from None

    params = {_local(key): value for key, value in root.attrib.items()}
    frame_rate = float(params.get("frameRate") or 25)
    tick_rate = float(params.get("tickRate") or 1)

    cues = []
    for element in root.iter():
        if _local(element.tag) != "p":
            continue
        begin, end = element.get("begin"), element.get("end")
        if begin is None or end is None:
            continue
        start = _ttml_time(begin, frame_rate, tick_rate)
        stop = _ttml_time(end, frame_rate, tick_rate)
        cues.append((start, stop, _ttml_text(element)))
    return cues


def _ttml_text(element):
    parts = []

    def walk(node):
        if node.text:
            parts.append(node.text)
        for child in node:
            if _local(child.tag) == "br":
                parts.append("\n")
            else:
                walk(child)
            if child.tail:
                parts.append(child.tail)

    walk(element)
    text = "".join(parts)
    # ORF escapes its line breaks: "Ein Aufstand, &lt;br/&gt;der ...".
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = _TAGS.sub("", text)
    lines = [" ".join(line.split()) for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def _ttml_time(value, frame_rate, tick_rate):
    value = value.strip()
    clock = _CLOCK.match(value)
    if clock:
        hours, minutes, seconds, sep, fraction = clock.groups()
        total = int(hours) * 3600 + int(minutes) * 60 + int(seconds)
        if fraction:
            if sep == ":":  # HH:MM:SS:FF counts frames
                total += int(fraction) / frame_rate
            else:
                total += float(f"0.{fraction}")
        return total
    offset = _OFFSET.match(value)
    if offset:
        number, unit = float(offset.group(1)), offset.group(2)
        return {
            "h": number * 3600,
            "m": number * 60,
            "s": number,
            "ms": number / 1000,
            "f": number / frame_rate,
            "t": number / tick_rate,
        }[unit]
    raise SubtitleError(f"Unreadable time: {value}")


# -----------------------------
# WebVTT
# -----------------------------


def _vtt_cues(text):
    cues = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        lines = block.strip().split("\n")
        for index, line in enumerate(lines):
            match = _VTT_TIME.search(line)
            if match:
                body = "\n".join(lines[index + 1 :])
                body = html.unescape(_TAGS.sub("", body))
                cues.append(
                    (_vtt_time(match.group(1)), _vtt_time(match.group(2)), body)
                )
                break
    return cues


def _vtt_time(value):
    parts = value.replace(",", ".").split(":")
    seconds = float(parts[-1])
    minutes = int(parts[-2])
    hours = int(parts[-3]) if len(parts) == 3 else 0
    return hours * 3600 + minutes * 60 + seconds


def _srt_time(seconds):
    millis = max(0, round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
