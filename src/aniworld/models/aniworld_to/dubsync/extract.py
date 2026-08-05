"""Lossless extraction of a dub audio track from an AniWorld/SerienStream episode.

Given an episode model object, resolve its stream (with provider fallback) for
the requested language and copy just the audio into a standalone file with
``-c:a copy`` -- no re-encode, so the dub stays bit-exact. The result is later
grafted into the archive-quality target video by :mod:`remux`.
"""

from __future__ import annotations

from pathlib import Path

import ffmpeg

from ....config import PROVIDER_HEADERS_D, logger
from ...common.common import (
    _resolve_stream_url_with_fallback,
    _run_ffmpeg_with_progress,
)


def _build_input_kwargs(stream_url: str, provider_name: str) -> dict:
    """Mirror ``download()``'s ffmpeg input options: reconnect handling, HLS
    segment-extension allowance, and provider request headers."""

    input_kwargs = {
        "reconnect": 1,
        "reconnect_streamed": 1,
        "reconnect_delay_max": 30,
    }
    if ".m3u8" in (stream_url or "").split("?", 1)[0].lower():
        input_kwargs["allowed_extensions"] = "ALL"

    headers = PROVIDER_HEADERS_D.get(provider_name, {})
    if headers:
        header_list = [f"{k}: {v}" for k, v in headers.items()]
        input_kwargs["headers"] = "\r\n".join(header_list) + "\r\n"

    return input_kwargs


def extract_dub_audio(
    episode,
    dest_path,
    audio_language: str = "German Dub",
    label: str = "",
):
    """Extract *episode*'s ``audio_language`` audio track to ``dest_path``.

    Sets the episode's selected language, resolves the stream URL via provider
    fallback, then copies the first audio stream losslessly. Returns
    ``(dest_path, provider_name)``. Raises on resolution/ffmpeg failure so the
    caller can report the episode as failed.
    """

    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    episode.selected_language = audio_language

    stream_url, provider_name = _resolve_stream_url_with_fallback(episode, "DubSync")
    input_kwargs = _build_input_kwargs(stream_url, provider_name)

    logger.debug(
        f"[DUBSYNC] extracting '{audio_language}' audio via {provider_name} "
        f"-> {dest_path.name}"
    )

    node = ffmpeg.input(stream_url, **input_kwargs).output(
        str(dest_path),
        map="0:a:0?",
        acodec="copy",
    )
    _run_ffmpeg_with_progress(node, label=label)

    return dest_path, provider_name
