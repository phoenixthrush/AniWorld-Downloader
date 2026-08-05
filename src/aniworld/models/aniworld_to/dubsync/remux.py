"""Graft a dub audio track into a target video container losslessly.

Takes an archive-quality video (all its streams) plus a standalone dub audio
file and produces an output with the dub appended as a secondary,
language-tagged audio track. Everything is stream-copied (``-c copy``); the only
timing adjustment is a constant ``-itsoffset`` on the dub input, which stays
lossless. Container differences are reconciled by :func:`_finalize_episode`.
"""

from __future__ import annotations

from pathlib import Path

import ffmpeg

from ....config import logger
from ...common.common import _finalize_episode, _run_ffmpeg_with_progress


def _count_audio_streams(path: Path) -> int:
    """Number of audio streams already in *path* (probe-based).

    Used to place the appended dub at the correct output audio index for the
    ``-metadata:s:a:N`` / ``-disposition:a:N`` specifiers. Raises rather than
    guessing, since a wrong index would mis-tag an archive file.
    """

    try:
        probe = ffmpeg.probe(str(path))
    except ffmpeg.Error as exc:
        raise RuntimeError(f"Could not probe target video: {path}") from exc

    return sum(
        1 for s in probe.get("streams", []) if s.get("codec_type") == "audio"
    )


def remux_with_dub(
    target_video,
    dub_audio,
    output_path,
    offset: float = 0.0,
    audio_code: str = "deu",
    label: str = "",
):
    """Mux ``target_video`` + ``dub_audio`` -> ``output_path``.

    Stream order in the output is: all of the target's streams first, then the
    dub audio appended (``-map 0 -map 1:a``). The dub is tagged
    ``language=<audio_code>`` and has its default disposition cleared so players
    keep the original track primary. ``offset`` (seconds, may be negative)
    delays the dub via ``-itsoffset``.

    Writes to a temp MKV next to ``output_path`` then atomically finalises onto
    it, so an interrupted run never corrupts the archive file.
    """

    target_video = Path(target_video)
    dub_audio = Path(dub_audio)
    output_path = Path(output_path)

    num_audio = _count_audio_streams(target_video)

    video_in = ffmpeg.input(str(target_video))

    dub_input_kwargs = {}
    if offset:
        dub_input_kwargs["itsoffset"] = float(offset)
    dub_in = ffmpeg.input(str(dub_audio), **dub_input_kwargs)

    output_kwargs = {
        "c": "copy",
        f"metadata:s:a:{num_audio}": f"language={audio_code}",
        # Keep the original audio as the default track; the dub is secondary.
        f"disposition:a:{num_audio}": "0",
    }

    temp_path = output_path.with_name(f"{output_path.stem}.dubsync.new.mkv")
    temp_attach = output_path.with_name(f"{output_path.stem}.dubsync.attach.mkv")

    logger.debug(
        f"[DUBSYNC] muxing dub (offset={offset}s, tag={audio_code}, "
        f"stream a:{num_audio}) -> {output_path.name}"
    )

    # ffmpeg (observed on 8.1) badly mis-interleaves the second input's
    # packets in a multi-input stream copy: the dub lands hundreds of MB
    # later in the file than its timestamp peers (or entirely at the end when
    # attachments are mapped) -- players then find no dub audio in their
    # readahead window and play silence. So the mux is done in two passes:
    #
    # 1. Combine target streams (minus attachments, which worsen the skew)
    #    with the offset dub. The result is correct but poorly interleaved.
    # 2. Re-interleave in a single-input copy with -max_interleave_delta 0,
    #    which buffers until every stream is present and writes strictly by
    #    timestamp; the target's font attachments are re-added in the same
    #    pass (an attachments-only extra input carries no packets and cannot
    #    skew anything).
    node = ffmpeg.output(
        video_in["v?"],
        video_in["a?"],
        video_in["s?"],
        video_in["d?"],
        dub_in.audio,
        str(temp_path),
        **output_kwargs,
    )

    try:
        _run_ffmpeg_with_progress(node, label=label)

        logger.debug(f"[DUBSYNC] re-interleaving -> {output_path.name}")
        interleave_node = ffmpeg.output(
            ffmpeg.input(str(temp_path)),
            ffmpeg.input(str(target_video))["t?"],
            str(temp_attach),
            c="copy",
            max_interleave_delta="0",
        )
        _run_ffmpeg_with_progress(interleave_node, label=label)
        temp_path.unlink(missing_ok=True)

        _finalize_episode(temp_attach, output_path, label)
    finally:
        temp_path.unlink(missing_ok=True)
        temp_attach.unlink(missing_ok=True)

    return output_path
