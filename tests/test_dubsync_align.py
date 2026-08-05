"""Unit tests for the DubSync alignment engine (synthetic signals).

The correlation math is tested directly on synthesized envelopes/PCM: two
tracks sharing an impulse "music bed" but carrying different "dialogue" noise
must align at the known shift with high confidence, while unrelated noise must
come back low-confidence. The full decode path is exercised through real WAV
files when ffmpeg is available.
"""

import shutil
import wave
from pathlib import Path

import numpy as np
import pytest

from aniworld.models.aniworld_to.dubsync.align import (
    _DECODE_RATE,
    _ENVELOPE_RATE,
    DEFAULT_MIN_CONFIDENCE,
    _onset_envelope,
    _xcorr_peak,
    detect_offset,
)

def _impulse_bed(rng, duration_s: float, n_events: int = 60) -> np.ndarray:
    """Silent track with short loud noise bursts at random times -- a stand-in
    for the shared music/SFX bed."""

    samples = np.zeros(int(duration_s * _DECODE_RATE), dtype=np.float32)
    burst_len = _DECODE_RATE // 10  # 100 ms
    positions = rng.integers(0, len(samples) - burst_len, n_events)
    for pos in positions:
        samples[pos : pos + burst_len] += 0.7 * rng.standard_normal(burst_len).astype(
            np.float32
        )
    return samples


def _dialogue(rng, duration_s: float, level: float = 0.08) -> np.ndarray:
    """Continuous low-level noise -- a stand-in for (language-specific) speech."""

    return level * rng.standard_normal(int(duration_s * _DECODE_RATE)).astype(
        np.float32
    )


def _write_wav(path: Path, samples: np.ndarray) -> None:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(_DECODE_RATE)
        wav.writeframes(pcm.tobytes())


def test_xcorr_recovers_known_shift():
    rng = np.random.default_rng(42)
    bed = _impulse_bed(rng, 120.0)
    ref_env = _onset_envelope(bed + _dialogue(rng, 120.0))

    shift_s = 2.5
    pad = np.zeros(int(shift_s * _DECODE_RATE), dtype=np.float32)
    dub_env = _onset_envelope(np.concatenate([pad, bed]) + _dialogue(rng, 122.5))

    max_lag = 30 * _ENVELOPE_RATE
    lag, confidence = _xcorr_peak(ref_env, dub_env, -max_lag, max_lag)

    # Dub content occurs later, so it must be advanced: negative lag.
    assert lag / _ENVELOPE_RATE == pytest.approx(-shift_s, abs=0.05)
    assert confidence >= DEFAULT_MIN_CONFIDENCE


def test_uncorrelated_noise_is_low_confidence():
    rng = np.random.default_rng(43)
    env_a = _onset_envelope(_dialogue(rng, 120.0, level=0.3))
    env_b = _onset_envelope(_dialogue(rng, 120.0, level=0.3))

    max_lag = 30 * _ENVELOPE_RATE
    _, confidence = _xcorr_peak(env_a, env_b, -max_lag, max_lag)

    assert confidence < DEFAULT_MIN_CONFIDENCE


def test_silence_yields_zero_confidence():
    silent = _onset_envelope(np.zeros(60 * _DECODE_RATE, dtype=np.float32))
    lag, confidence = _xcorr_peak(silent, silent, -100, 100)
    assert lag == 0.0
    assert confidence == 0.0


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
def test_detect_offset_end_to_end(tmp_path):
    rng = np.random.default_rng(44)
    bed = _impulse_bed(rng, 90.0)
    ref = bed + _dialogue(rng, 90.0)

    shift_s = 1.5
    pad = np.zeros(int(shift_s * _DECODE_RATE), dtype=np.float32)
    dub = np.concatenate([pad, bed]) + _dialogue(rng, 91.5)

    ref_path = tmp_path / "ref.wav"
    dub_path = tmp_path / "dub.wav"
    _write_wav(ref_path, ref)
    _write_wav(dub_path, dub)

    result = detect_offset(dub_path, ref_path, max_offset=30.0)

    assert result.offset == pytest.approx(-shift_s, abs=0.05)
    assert result.confidence >= DEFAULT_MIN_CONFIDENCE
    # 90 s is far below the drift-check minimum, so no drift is reported.
    assert result.drift == 0.0
    assert result.tempo_ratio == 1.0


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
def test_detect_offset_finds_pal_drift(tmp_path):
    rng = np.random.default_rng(45)
    speed = 25 / 23.976  # PAL speed-up: the classic German-dub drift case
    bed = _impulse_bed(rng, 600.0, n_events=300)
    ref = bed + _dialogue(rng, 600.0)

    # Dub plays `speed` times too fast: dub[i] = bed[i * speed].
    idx = np.arange(int(len(bed) / speed)) * speed
    dub = np.interp(idx, np.arange(len(bed)), bed).astype(np.float32)
    dub += _dialogue(rng, len(dub) / _DECODE_RATE)

    ref_path = tmp_path / "ref.wav"
    dub_path = tmp_path / "dub.wav"
    _write_wav(ref_path, ref)
    _write_wav(dub_path, dub)

    result = detect_offset(dub_path, ref_path, max_offset=60.0)

    assert result.has_drift
    assert result.tempo_ratio == pytest.approx(1 / speed, abs=1e-4)
    assert result.drift_confidence >= DEFAULT_MIN_CONFIDENCE
    assert result.post_tempo_offset == pytest.approx(0.0, abs=0.1)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
def test_no_false_drift_on_clean_alignment(tmp_path):
    rng = np.random.default_rng(46)
    bed = _impulse_bed(rng, 600.0, n_events=300)
    ref = bed + _dialogue(rng, 600.0)
    dub = bed + _dialogue(rng, 600.0)

    ref_path = tmp_path / "ref.wav"
    dub_path = tmp_path / "dub.wav"
    _write_wav(ref_path, ref)
    _write_wav(dub_path, dub)

    result = detect_offset(dub_path, ref_path, max_offset=60.0)

    assert result.offset == pytest.approx(0.0, abs=0.05)
    assert not result.has_drift
    assert result.tempo_ratio == 1.0
