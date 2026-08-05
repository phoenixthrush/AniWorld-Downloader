"""Automatic audio alignment between a dub track and a target's own audio.

The dub and the target carry *different dialogue* (German vs JP/EN), so speech
cannot be correlated directly. What both share is the music/SFX bed: loud
musical hits and effects dominate an onset-energy envelope regardless of the
spoken language. Cross-correlating those envelopes (via FFT) locks onto the
shared bed and yields the constant offset between the two tracks; the peak's
sharpness (a z-score against the rest of the correlation) is the confidence.

Linear drift (e.g. PAL-sourced dubs running ~4% fast) smears the correlation
peak, so a hierarchical tempo scan time-stretches the dub envelope over a grid
of speed factors (couple of percent around 1.0, refined in stages down to
1e-5) and keeps the factor whose correlation peak is sharpest -- the correct
tempo un-smears the peak dramatically, and a wrong one never beats the
identity baseline by the required margin. A detected factor can be corrected
with :func:`resample_dub` via ``atempo`` -- which re-encodes the dub audio, so
the pipeline only takes that path when the user opts in.

Only :mod:`numpy` is needed (FFT correlation), no scipy.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import ffmpeg
import numpy as np

from ....config import logger
from ...common.common import _run_ffmpeg_with_progress

# Decode/analysis parameters. 8 kHz mono is plenty for an energy envelope; the
# envelope itself is sampled at 100 Hz (10 ms resolution, refined below by
# parabolic peak interpolation).
_DECODE_RATE = 8000
_ENVELOPE_RATE = 100

#: Largest constant offset (seconds) the global search considers.
DEFAULT_MAX_OFFSET = 600.0

#: Peak z-score below which a detected offset should not be trusted. A true
#: match gives a needle-sharp peak (z >> 10); uncorrelated tracks stay ~3-5.
DEFAULT_MIN_CONFIDENCE = 8.0

#: Offset change across the whole episode (seconds) beyond which drift is
#: reported (and correctable via resample).
DRIFT_THRESHOLD = 0.2

# Tempo scan: stretch factors 1.0 +/- _TEMPO_SPAN are searched at the first
# step size, then the best factor is refined at each finer step. The final
# step bounds the tempo error at 1e-5 (~14 ms residual drift over 24 min).
_TEMPO_SPAN = 0.06  # covers PAL <-> film (~4.3%) with headroom
_TEMPO_STEPS = (2e-3, 2e-4, 2e-5)

# Shortest dub (seconds) for which drift analysis is attempted at all.
_DRIFT_MIN_DURATION = 300.0

# A non-identity tempo must beat the identity peak by this much z-score (and
# clear DEFAULT_MIN_CONFIDENCE) before drift is claimed -- otherwise noise
# could pick a wrong speed. A genuinely drifted dub un-smears dramatically.
_TEMPO_MARGIN = 5.0

# Seconds around the peak excluded when estimating the correlation noise floor.
_PEAK_EXCLUDE = 1.0

# Japanese language tags used to pick the preferred reference audio stream.
_JP_TAGS = {"jpn", "ja", "jp", "japanese"}


@dataclass
class AlignResult:
    """Outcome of aligning one dub against one reference track.

    ``offset`` is the best *constant* delay (seconds, may be negative) to apply
    to the dub via ``-itsoffset``; ``confidence`` is the correlation peak
    z-score. When drift was detected, ``drift`` is how much the offset changes
    across the whole episode, ``tempo_ratio`` the ``atempo`` factor that
    corrects it, and ``post_tempo_offset`` the residual constant offset to use
    *after* the dub has been retimed with that factor.
    """

    offset: float
    confidence: float
    drift: float = 0.0
    drift_confidence: float = 0.0
    tempo_ratio: float = 1.0
    post_tempo_offset: float = 0.0

    @property
    def has_drift(self) -> bool:
        return abs(self.drift) > DRIFT_THRESHOLD


def _pick_reference_stream(path: Path) -> int:
    """Audio-stream index (``0:a:N``) to correlate against: JP if tagged, else
    the first audio stream. Raises if the file has no audio at all."""

    try:
        probe = ffmpeg.probe(str(path))
    except ffmpeg.Error as exc:
        raise RuntimeError(f"Could not probe reference audio: {path}") from exc

    audio_streams = [
        s for s in probe.get("streams", []) if s.get("codec_type") == "audio"
    ]
    if not audio_streams:
        raise RuntimeError(f"No audio stream in reference file: {path}")

    for idx, stream in enumerate(audio_streams):
        lang = (stream.get("tags", {}).get("language") or "").lower()
        if lang in _JP_TAGS:
            return idx
    return 0


def _decode_mono(path: Path, stream_index: int = 0) -> np.ndarray:
    """Decode one audio stream of *path* to mono float32 at ``_DECODE_RATE``."""

    try:
        out, _ = (
            ffmpeg.input(str(path))
            .output(
                "pipe:",
                format="s16le",
                acodec="pcm_s16le",
                ac=1,
                ar=_DECODE_RATE,
                map=f"0:a:{stream_index}",
            )
            .run(capture_stdout=True, capture_stderr=True)
        )
    except ffmpeg.Error as exc:
        tail = (exc.stderr or b"").decode(errors="replace").strip().splitlines()
        raise RuntimeError(
            f"ffmpeg failed decoding {Path(path).name}: "
            + (tail[-1] if tail else "unknown error")
        ) from exc

    return np.frombuffer(out, np.int16).astype(np.float32) / 32768.0


def _onset_envelope(samples: np.ndarray) -> np.ndarray:
    """Half-wave-rectified log-energy onset envelope at ``_ENVELOPE_RATE`` Hz,
    z-normalised. Loud transient events (music hits, SFX) dominate it, which is
    exactly the language-independent signal shared between dub and original."""

    hop = _DECODE_RATE // _ENVELOPE_RATE
    n_frames = len(samples) // hop
    if n_frames == 0:
        return np.zeros(0, dtype=np.float32)

    frames = samples[: n_frames * hop].reshape(n_frames, hop)
    rms = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1))
    env = np.log1p(rms * 100.0)

    onset = np.diff(env, prepend=env[:1])
    np.maximum(onset, 0.0, out=onset)

    std = onset.std()
    if std < 1e-8:
        return np.zeros_like(onset)
    return (onset - onset.mean()) / std


def _xcorr_peak_fft(
    ref_fft: np.ndarray,
    n: int,
    qry_env: np.ndarray,
    min_lag: int,
    max_lag: int,
) -> tuple[float, float]:
    """Correlation-peak search against a precomputed reference spectrum, so a
    tempo scan pays for the reference FFT only once."""

    if len(qry_env) == 0:
        return 0.0, 0.0

    corr = np.fft.irfft(ref_fft * np.conj(np.fft.rfft(qry_env, n)), n)

    # corr[k] = sum(ref[m + k] * qry[m]); negative lags wrap to the array end.
    lags = np.arange(n)
    lags[lags > n // 2] -= n

    valid = (lags >= min_lag) & (lags <= max_lag)
    if not valid.any():
        return 0.0, 0.0

    valid_idx = np.flatnonzero(valid)
    seg = corr[valid_idx]
    best = int(valid_idx[np.argmax(seg)])
    peak_lag = int(lags[best])
    peak_val = corr[best]

    # Confidence: peak z-score against the searched range, excluding the
    # immediate neighbourhood of the peak itself.
    exclude = int(_PEAK_EXCLUDE * _ENVELOPE_RATE)
    noise = seg[np.abs(lags[valid_idx] - peak_lag) > exclude]
    if len(noise) < 8:
        return float(peak_lag), 0.0
    noise_std = noise.std()
    confidence = (
        float((peak_val - noise.mean()) / noise_std) if noise_std > 1e-12 else 0.0
    )

    # Parabolic interpolation for sub-envelope-sample lag precision.
    refined = float(peak_lag)
    prev_i, next_i = (best - 1) % n, (best + 1) % n
    y0, y1, y2 = corr[prev_i], peak_val, corr[next_i]
    denom = y0 - 2.0 * y1 + y2
    if abs(denom) > 1e-12:
        delta = 0.5 * (y0 - y2) / denom
        if abs(delta) <= 1.0:
            refined += float(delta)

    return refined, confidence


def _xcorr_peak(
    ref_env: np.ndarray,
    qry_env: np.ndarray,
    min_lag: int,
    max_lag: int,
) -> tuple[float, float]:
    """FFT cross-correlation peak of *qry_env* against *ref_env*.

    Returns ``(lag, confidence)`` where ``lag`` (envelope samples, may be
    fractional after parabolic refinement) is how far *qry* must be delayed to
    line up with *ref*, and ``confidence`` is the peak's z-score against the
    rest of the searched correlation range.
    """

    if len(ref_env) == 0 or len(qry_env) == 0:
        return 0.0, 0.0

    n = 1 << int(len(ref_env) + len(qry_env) - 1).bit_length()
    return _xcorr_peak_fft(np.fft.rfft(ref_env, n), n, qry_env, min_lag, max_lag)


def _stretch(env: np.ndarray, factor: float) -> np.ndarray:
    """Time-stretch an envelope by *factor* (linear interpolation). A dub that
    plays ``factor`` times too fast lines up with the reference after its
    envelope is stretched by ``factor``."""

    if factor == 1.0 or len(env) == 0:
        return env
    idx = np.arange(int(len(env) * factor)) / factor
    return np.interp(idx, np.arange(len(env)), env).astype(env.dtype)


def _tempo_scan(
    ref_env: np.ndarray,
    dub_env: np.ndarray,
    max_lag: int,
) -> tuple[float, float, float]:
    """Find the tempo factor whose stretched-dub correlation peak is sharpest.

    Coarse-to-fine grid search: the full ``1 +/- _TEMPO_SPAN`` range at the
    first step size, then successively finer grids around the running best.
    Returns ``(factor, lag, confidence)``.
    """

    n = 1 << int(len(ref_env) + len(dub_env) * (1 + _TEMPO_SPAN)).bit_length()
    ref_fft = np.fft.rfft(ref_env, n)

    best_factor, best_lag, best_conf = 1.0, 0.0, -np.inf
    span = _TEMPO_SPAN
    center = 1.0
    for step in _TEMPO_STEPS:
        for factor in np.arange(center - span, center + span + step / 2, step):
            lag, conf = _xcorr_peak_fft(
                ref_fft, n, _stretch(dub_env, float(factor)), -max_lag, max_lag
            )
            if conf > best_conf:
                best_factor, best_lag, best_conf = float(factor), lag, conf
        center = best_factor
        span = step  # next pass zooms into the winning grid cell
    return best_factor, best_lag, best_conf


def detect_offset(
    dub_path,
    ref_path,
    max_offset: float = DEFAULT_MAX_OFFSET,
    check_drift: bool = True,
) -> AlignResult:
    """Detect the offset between *dub_path* and *ref_path*'s audio.

    *ref_path* may be a full video container; its JP audio stream is preferred
    as the reference (falling back to the first audio stream). The returned
    :class:`AlignResult` always carries the best constant offset; drift fields
    are populated when the tracks are long enough for the two-window check.
    """

    dub_path = Path(dub_path)
    ref_path = Path(ref_path)

    ref_stream = _pick_reference_stream(ref_path)
    ref_env = _onset_envelope(_decode_mono(ref_path, ref_stream))
    dub_env = _onset_envelope(_decode_mono(dub_path))

    rate = _ENVELOPE_RATE
    max_lag = int(max_offset * rate)
    lag, confidence = _xcorr_peak(ref_env, dub_env, -max_lag, max_lag)
    offset = lag / rate

    result = AlignResult(
        offset=offset, confidence=confidence, post_tempo_offset=offset
    )
    logger.debug(
        f"[DUBSYNC] global offset {offset:+.3f}s (confidence z={confidence:.1f}) "
        f"for {dub_path.name}"
    )

    dub_duration = len(dub_env) / rate
    if not check_drift or dub_duration < _DRIFT_MIN_DURATION:
        return result

    # Linear drift smears the identity-tempo peak; scanning stretch factors
    # un-smears it at the true speed ratio. A non-identity factor must beat
    # the identity peak by a clear margin so noise can't pick a wrong speed.
    factor, t_lag, t_conf = _tempo_scan(ref_env, dub_env, max_lag)
    logger.debug(
        f"[DUBSYNC] tempo scan: x{factor:.6f} z={t_conf:.1f} "
        f"(identity z={confidence:.1f})"
    )
    if (
        factor == 1.0
        or t_conf < DEFAULT_MIN_CONFIDENCE
        or t_conf < confidence + _TEMPO_MARGIN
    ):
        return result

    result.confidence = t_conf
    result.drift = (factor - 1.0) * dub_duration
    result.drift_confidence = t_conf
    if result.has_drift:
        # Slowing the dub by the detected factor (atempo = 1/factor) removes
        # the drift; the scan's peak lag is the remaining constant offset.
        result.tempo_ratio = 1.0 / factor
        result.post_tempo_offset = t_lag / rate

    return result


def resample_dub(
    dub_path, dest_path, tempo_ratio: float, label: str = "", acodec: str = "flac"
) -> Path:
    """Retime *dub_path* by *tempo_ratio* (``atempo``) to correct linear drift.

    This is the one lossy step in DubSync: ``atempo`` requires decoding, so the
    result is re-encoded. FLAC by default, so no further generational loss
    after the decode; callers retiming an already-lossy stream rip (where a
    lossless track would balloon the file) can ask for a lossy *acodec*
    instead. Only called when the user opted in to resampling.
    """

    dub_path = Path(dub_path)
    dest_path = Path(dest_path)

    logger.debug(
        f"[DUBSYNC] retiming dub with atempo={tempo_ratio:.6f} -> {dest_path.name}"
    )

    encode_kwargs = {"acodec": acodec}
    if acodec == "aac":
        encode_kwargs["audio_bitrate"] = "192k"

    node = ffmpeg.input(str(dub_path)).output(
        str(dest_path),
        af=f"atempo={tempo_ratio:.8f}",
        map="0:a:0",
        **encode_kwargs,
    )
    _run_ffmpeg_with_progress(node, label=label)
    return dest_path
