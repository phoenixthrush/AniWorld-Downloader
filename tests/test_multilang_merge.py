"""Regression tests for merging a second language into an existing download.

Downloading the same episode again in another language used to concatenate the
new stream with a plain ``-c copy``, so the added track played out of sync with
the video (upstream issue: "the audio track from the language downloaded second
was noticeably late"). The merge now detects the offset and applies it, which
is what these tests pin down:

* the appended track ends up aligned with the one already in the file,
* it is tagged and marked non-default so players keep the original primary,
* everything stays in ONE file (extra dub -> audio track, hardsubbed "Sub"
  variant -> additional video+audio pair).

Media is synthesised with ffmpeg; no network access is involved.
"""

import json
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest

from aniworld.models.aniworld_to.dubsync.align import _DECODE_RATE, detect_offset
from aniworld.models.common.common import (
    _detect_merge_offset,
    _merge_audio_aligned,
    _merge_full_stream_aligned,
)

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not on PATH",
)

DURATION_S = 40.0
LEAD_IN_S = 1.5


def _shared_bed(seed: int, duration_s: float = DURATION_S) -> np.ndarray:
    """Noise bursts with a random envelope -- the music/SFX bed both language
    versions share, and the only thing the aligner can lock onto."""

    rng = np.random.default_rng(seed)
    frames = int(duration_s * 10)
    envelope = np.repeat(rng.random(frames) > 0.5, _DECODE_RATE // 10)
    noise = rng.standard_normal(len(envelope)).astype(np.float32)
    return 0.3 * noise * envelope.astype(np.float32)


def _write_wav(path: Path, samples: np.ndarray) -> None:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(_DECODE_RATE)
        wav.writeframes(pcm.tobytes())


def _ffmpeg(*args: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", *args],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def _make_video(dest: Path, audio: Path, lang: str, pattern: str = "testsrc") -> Path:
    """Tiny video file carrying `audio` as its single, language-tagged track."""

    _ffmpeg(
        "-f", "lavfi", "-i", f"{pattern}=size=160x90:rate=10:duration={DURATION_S + 5}",
        "-i", str(audio),
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
        "-metadata:s:a:0", f"language={lang}",
        "-shortest", str(dest),
    )
    return dest


def _streams(path: Path) -> list[dict]:
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(probe.stdout)["streams"]


def _residual_offset(path: Path, first: int = 0, second: int = 1) -> float:
    """Seconds the second audio track is still out of sync with the first.

    Extracting a track to WAV re-bases it at zero, discarding the container
    start_time that carries the applied ``-itsoffset``; the delta between the
    two start times has to be added back or a perfectly aligned file looks
    misaligned by exactly the offset that fixed it.
    """

    audio = [s for s in _streams(path) if s["codec_type"] == "audio"]
    start_delta = float(audio[second].get("start_time") or 0) - float(
        audio[first].get("start_time") or 0
    )

    extracted = []
    for index in (first, second):
        out = path.with_name(f"{path.stem}.a{index}.wav")
        _ffmpeg("-i", str(path), "-map", f"0:a:{index}", str(out))
        extracted.append(out)

    content_offset = detect_offset(extracted[1], extracted[0], max_offset=30.0).offset
    return start_delta - content_offset


@pytest.fixture
def episode_with_delayed_second_language(tmp_path):
    """An existing download plus a second-language stream that starts late.

    The second stream carries the same bed behind `LEAD_IN_S` of extra silence,
    i.e. exactly the situation that used to produce a late audio track.
    """

    bed = _shared_bed(seed=7)
    lead_in = np.zeros(int(LEAD_IN_S * _DECODE_RATE), dtype=np.float32)

    original_wav = tmp_path / "original.wav"
    delayed_wav = tmp_path / "delayed.wav"
    _write_wav(original_wav, bed)
    _write_wav(delayed_wav, np.concatenate([lead_in, bed]))

    episode = _make_video(tmp_path / "episode.mkv", original_wav, "deu")
    return episode, original_wav, delayed_wav


def test_second_dub_is_merged_in_sync(episode_with_delayed_second_language, tmp_path):
    """The reported bug: a second dub must not end up playing late."""

    episode, _, delayed_wav = episode_with_delayed_second_language
    extra_audio = tmp_path / "extra_audio.mkv"
    _ffmpeg(
        "-i", str(delayed_wav), "-c:a", "aac",
        "-metadata:s:a:0", "language=eng", str(extra_audio),
    )

    _merge_audio_aligned(episode, extra_audio, "eng", "test-episode")

    audio = [s for s in _streams(episode) if s["codec_type"] == "audio"]
    assert len(audio) == 2, "the second language must land in the same file"
    assert audio[1]["tags"]["language"] == "eng"
    assert audio[1]["disposition"]["default"] == 0, "original stays the default track"
    assert _residual_offset(episode) == pytest.approx(0.0, abs=0.1)


def test_sub_variant_merges_as_extra_video_and_audio(
    episode_with_delayed_second_language, tmp_path
):
    """Hardsubbed "Sub" variants bring their own video; both streams are
    appended to the same file, shifted together and left non-default."""

    episode, _, delayed_wav = episode_with_delayed_second_language
    # testsrc2 so the appended video is visibly a different encode.
    sub_variant = _make_video(
        tmp_path / "sub_variant.mkv", delayed_wav, "jpn", pattern="testsrc2"
    )

    _merge_full_stream_aligned(episode, sub_variant, "test-episode")

    streams = _streams(episode)
    video = [s for s in streams if s["codec_type"] == "video"]
    audio = [s for s in streams if s["codec_type"] == "audio"]
    assert len(video) == 2 and len(audio) == 2
    assert video[1]["disposition"]["default"] == 0
    assert audio[1]["disposition"]["default"] == 0
    assert _residual_offset(episode) == pytest.approx(0.0, abs=0.1)
    # The appended video must keep the same shift as the audio it came with,
    # otherwise the sub variant would be internally out of sync.
    assert float(video[1]["start_time"]) == pytest.approx(
        float(audio[1]["start_time"]), abs=0.15
    )


def test_alignment_can_be_disabled(episode_with_delayed_second_language, monkeypatch):
    """--no-merge-align / ANIWORLD_MERGE_ALIGN=0 restores the unshifted merge."""

    episode, _, delayed_wav = episode_with_delayed_second_language
    monkeypatch.setenv("ANIWORLD_MERGE_ALIGN", "0")

    assert _detect_merge_offset(delayed_wav, episode, "second track") == (0.0, None)


def test_unrelated_audio_is_not_shifted_on_a_guess(tmp_path):
    """Below the confidence threshold the merge must fall back to no shift
    rather than trusting a spurious correlation peak."""

    reference = tmp_path / "reference.wav"
    unrelated = tmp_path / "unrelated.wav"
    _write_wav(reference, _shared_bed(seed=1))
    _write_wav(unrelated, _shared_bed(seed=99))

    assert _detect_merge_offset(unrelated, reference, "unrelated track") == (0.0, None)


def _pal_speed_pair(seed: int, duration_s: float = 700.0):
    """A reference bed plus the same bed running at PAL speed (~4 % fast).

    German TV dubs are 25 fps where the original-language encode is 23.976,
    which is exactly the case that broke live: no constant shift can align
    them, and the shift measured while pretending otherwise is noise.
    """

    speed = 25 / 23.976
    bed = _shared_bed(seed, duration_s)
    index = np.arange(int(len(bed) / speed)) * speed
    fast = np.interp(index, np.arange(len(bed)), bed).astype(np.float32)
    return bed, fast


def test_speed_mismatched_audio_is_retimed_not_shifted(tmp_path):
    """The live failure: a PAL-speed dub must never be "aligned" with a
    constant offset, because the offset measured under that assumption is
    meaningless (it landed 95 s out on real Family Guy audio)."""

    bed, fast = _pal_speed_pair(seed=3)
    reference = tmp_path / "reference.wav"
    faster = tmp_path / "faster.wav"
    _write_wav(reference, bed)
    _write_wav(faster, fast)

    retime_to = tmp_path / "retimed.mka"
    offset, retimed = _detect_merge_offset(
        faster, reference, "pal dub", retime_to=retime_to
    )

    assert retimed == retime_to and retimed.exists(), "drift must be retimed"
    # Post-retime the tracks start together, so only a small residual remains.
    assert offset == pytest.approx(0.0, abs=1.0)


def test_speed_mismatch_without_a_retime_target_is_not_shifted(tmp_path):
    """A "Sub" variant brings its own video, so its audio cannot be retimed
    independently — it must be merged unshifted rather than mis-shifted."""

    bed, fast = _pal_speed_pair(seed=4)
    reference = tmp_path / "reference.wav"
    faster = tmp_path / "faster.wav"
    _write_wav(reference, bed)
    _write_wav(faster, fast)

    assert _detect_merge_offset(faster, reference, "pal variant") == (0.0, None)


def test_retiming_can_be_disabled(tmp_path, monkeypatch):
    bed, fast = _pal_speed_pair(seed=5)
    reference = tmp_path / "reference.wav"
    faster = tmp_path / "faster.wav"
    _write_wav(reference, bed)
    _write_wav(faster, fast)
    monkeypatch.setenv("ANIWORLD_MERGE_RESAMPLE", "0")

    offset, retimed = _detect_merge_offset(
        faster, reference, "pal dub", retime_to=tmp_path / "retimed.mka"
    )
    assert (offset, retimed) == (0.0, None)
