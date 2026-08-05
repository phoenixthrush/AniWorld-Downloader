"""Fetch real (soft) subtitle tracks for anime episodes from Animetosho.

AniWorld's "Sub" variants are hardsubbed video encodes, so a togglable
subtitle track can never come from the streaming hosters themselves. It can,
however, come from the fansub scene: Erai-raws MultiSub releases carry the
official Crunchyroll subtitles in many languages (German included), and
Animetosho extracts every subtitle stream from those releases and serves each
one individually - no API key, no rate-limited account.

Flow: resolve the episode's season to its MAL id (AniWorld already maps
seasons to MAL for AniSkip) -> Jikan gives the romaji title Erai-raws names
its files after -> Animetosho JSON search for that title + episode number ->
pick the subtitle attachment in the wanted language -> download + un-xz ->
optionally time-align with ffsubsync -> mux as a non-default subtitle track
(MKV) or drop a sidecar file next to the video (other containers).
"""

from __future__ import annotations

import lzma
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import ffmpeg
import niquests

from ....aniskip.jikan import get_anime_titles
from ....config import DEFAULT_USER_AGENT, logger

# Plain requests instead of GLOBAL_SESSION: the shared session advertises
# compression encodings Animetosho answers with but niquests then fails to
# decode, yielding undecodable JSON bodies.
_HEADERS = {"User-Agent": DEFAULT_USER_AGENT, "Accept-Encoding": "gzip"}

FEED_URL = "https://feed.animetosho.org/json"
# Attachment ids from the JSON API map to storage URLs with the id in hex;
# the filename part is free-form, only the extension chain matters.
ATTACH_URL = "https://animetosho.org/storage/attach/{aid:08x}/subtitle.{lang}.{ext}.xz"

MIN_TITLE_SCORE = 0.85

# Accepted spellings for --fetch-subs values -> Animetosho's ISO 639-2/B codes.
LANG_ALIASES = {
    "1": "ger",
    "true": "ger",
    "yes": "ger",
    "on": "ger",
    "de": "ger",
    "deu": "ger",
    "ger": "ger",
    "german": "ger",
    "en": "eng",
    "eng": "eng",
    "english": "eng",
    "fr": "fre",
    "fra": "fre",
    "fre": "fre",
    "french": "fre",
    "es": "spa",
    "spa": "spa",
    "spanish": "spa",
    "it": "ita",
    "ita": "ita",
    "italian": "ita",
    "pt": "por",
    "por": "por",
    "portuguese": "por",
    "ru": "rus",
    "rus": "rus",
    "russian": "rus",
    "ar": "ara",
    "ara": "ara",
    "arabic": "ara",
}

_SUB_EXTENSIONS = {"ass": "ass", "ssa": "ssa", "srt": "srt", "subrip": "srt"}


def _tokens(text):
    # "wo" vs "o" is the most common romanization difference in release names
    # (e.g. "Yume wo Minai" vs "Yume o Minai") - fold it away.
    return {
        "o" if t == "wo" else t
        for t in re.split(r"[^a-z0-9]+", text.lower())
        if t
    }


def _episode_re(episode_number):
    return re.compile(rf"\s-\s0*{episode_number}(?:v\d+)?\b")


def _title_score(release_title, wanted_title, episode_number):
    """Similarity in [0, 1]; strict enough to reject sibling seasons.

    Uses the *minimum* directional token containment: sequel seasons share
    most of their tokens ("Seishun Buta Yarou wa ... no Yume o Minai"), so a
    symmetric Dice score would happily match the wrong season. Requiring both
    titles to be nearly covered by the other keeps only the actual season.
    """
    clean = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", release_title)
    clean = re.split(rf"\s-\s0*{episode_number}\b", clean)[0]
    release_tokens = _tokens(clean)
    wanted_tokens = _tokens(wanted_title)
    if not release_tokens or not wanted_tokens:
        return 0.0
    shared = len(release_tokens & wanted_tokens)
    return min(shared / len(wanted_tokens), shared / len(release_tokens))


def _get_json(params):
    res = niquests.get(FEED_URL, params=params, headers=_HEADERS, timeout=30)
    res.raise_for_status()
    return res.json()


def _pick_attachment(tosho_id, episode_number, lang3):
    """Return (attachment_id, extension) of the wanted subtitle, or None."""
    detail = _get_json({"show": "torrent", "id": tosho_id})
    files = detail.get("files") or []
    ep_re = _episode_re(episode_number)
    for file_entry in files:
        # Batch torrents hold many episodes; match ours by filename then.
        if len(files) > 1 and not ep_re.search(file_entry.get("filename") or ""):
            continue
        for attachment in file_entry.get("attachments") or []:
            info = attachment.get("info") or {}
            if attachment.get("type") != "subtitle":
                continue
            if info.get("lang") != lang3 or info.get("forced"):
                continue
            ext = _SUB_EXTENSIONS.get((info.get("codec") or "ass").lower())
            if ext and attachment.get("id"):
                return attachment["id"], ext
    return None


def _find_subtitle(titles, episode_number, lang3):
    """Search Animetosho for the episode; return (attachment_id, ext, release)."""
    ep_re = _episode_re(episode_number)
    seen_ids = set()
    for title in titles:
        for query in (
            f"Erai-raws {title} - {episode_number:02d}",
            f"Erai-raws {title}",
        ):
            try:
                results = _get_json({"q": query})
            except Exception as exc:
                logger.debug(f"[SUBS] Animetosho search failed ({exc})")
                continue
            if not isinstance(results, list):
                continue

            candidates = []
            for entry in results:
                release_title = entry.get("title") or ""
                if not release_title.lower().startswith("[erai-raws]"):
                    continue
                if not ep_re.search(release_title):
                    continue
                score = _title_score(release_title, title, episode_number)
                if score >= MIN_TITLE_SCORE:
                    candidates.append((score, entry))

            candidates.sort(key=lambda item: item[0], reverse=True)
            for _score, entry in candidates[:5]:
                tosho_id = entry.get("id")
                if not tosho_id or tosho_id in seen_ids:
                    continue
                seen_ids.add(tosho_id)
                try:
                    picked = _pick_attachment(tosho_id, episode_number, lang3)
                except Exception as exc:
                    logger.debug(f"[SUBS] torrent detail failed ({exc})")
                    continue
                if picked:
                    return picked[0], picked[1], entry.get("title") or ""
            if candidates:
                # Right releases found but none carries the language; other
                # queries for the same series will hit the same releases.
                return None
    return None


def _download_attachment(attachment_id, lang3, ext, dest):
    url = ATTACH_URL.format(aid=attachment_id, lang=lang3, ext=ext)
    res = niquests.get(url, headers=_HEADERS, timeout=60)
    res.raise_for_status()
    dest.write_bytes(lzma.decompress(res.content))


def _align_subtitle(video_path, sub_path, label=""):
    """Time-align the subtitle to the video via ffsubsync when available."""
    ffsubsync_bin = shutil.which("ffsubsync")
    if ffsubsync_bin:
        cmd = [ffsubsync_bin]
    else:
        try:
            import ffsubsync  # noqa: F401
        except ImportError:
            logger.info(
                "[SUBS] ffsubsync not installed - muxing subtitle with its "
                "original timing (pip install ffsubsync to auto-sync it)"
            )
            return sub_path
        cmd = [sys.executable, "-m", "ffsubsync"]

    synced = sub_path.with_name(f"{sub_path.stem}.synced{sub_path.suffix}")
    cmd += [str(video_path), "-i", str(sub_path), "-o", str(synced)]
    try:
        proc = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=600,
            check=False,
        )
        if proc.returncode == 0 and synced.exists() and synced.stat().st_size:
            logger.debug(f"[SUBS] ffsubsync aligned subtitle for {label}")
            return synced
        logger.warning(
            f"[SUBS] ffsubsync failed (rc={proc.returncode}); "
            "keeping original subtitle timing"
        )
    except Exception as exc:
        logger.warning(
            f"[SUBS] ffsubsync error ({exc}); keeping original subtitle timing"
        )
    synced.unlink(missing_ok=True)
    return sub_path


def _has_subtitle_lang(path, lang3):
    try:
        probe = ffmpeg.probe(str(path))
    except ffmpeg.Error:
        return False
    for stream in probe.get("streams", []):
        if stream.get("codec_type") != "subtitle":
            continue
        if stream.get("tags", {}).get("language") == lang3:
            return True
    return False


def _mux_subtitle_track(target_path, sub_path, lang3, label=""):
    """Stream-copy *sub_path* into the MKV as a non-default subtitle track."""
    from ...common.common import _finalize_episode, _run_ffmpeg_with_progress

    try:
        probe = ffmpeg.probe(str(target_path))
        num_subs = sum(
            1
            for s in probe.get("streams", [])
            if s.get("codec_type") == "subtitle"
        )
    except ffmpeg.Error as exc:
        raise RuntimeError(f"Could not probe {target_path}") from exc

    inp = ffmpeg.input(str(target_path))
    sub_in = ffmpeg.input(str(sub_path))
    output_kwargs = {
        "c": "copy",
        f"metadata:s:s:{num_subs}": f"language={lang3}",
        f"disposition:s:{num_subs}": "0",
    }

    temp_path = target_path.with_name(f"{target_path.stem}.subfetch.new.mkv")
    node = ffmpeg.output(
        inp["v?"],
        inp["a?"],
        inp["s?"],
        inp["d?"],
        inp["t?"],
        sub_in["s?"],
        str(temp_path),
        **output_kwargs,
    )
    try:
        _run_ffmpeg_with_progress(node, label=label)
        _finalize_episode(temp_path, target_path, label)
    finally:
        temp_path.unlink(missing_ok=True)


def fetch_and_mux_subtitle(episode, target_path, lang="ger", label=""):
    """Fetch a soft subtitle for *episode* and attach it to *target_path*.

    Returns the path that received the subtitle (the video itself for MKV, a
    sidecar file otherwise) or None when no subtitle could be added. Raises
    only for programmer errors; expected misses just log and return None.
    """
    target_path = Path(target_path)
    lang3 = LANG_ALIASES.get((lang or "").strip().lower())
    if not lang3:
        logger.warning(f"[SUBS] unknown subtitle language {lang!r}")
        return None

    url = (getattr(episode, "url", "") or "").lower()
    if "aniworld.to" not in url:
        logger.info(
            f"[SUBS] skipping {label or target_path.name}: subtitle fetching "
            "covers anime only (Erai-raws/Animetosho)"
        )
        return None
    if not target_path.exists():
        return None

    is_mkv = target_path.suffix.lower() == ".mkv"
    if is_mkv and _has_subtitle_lang(target_path, lang3):
        logger.debug(f"[SUBS] {label} already has a '{lang3}' subtitle track")
        return None
    if not is_mkv and any(
        target_path.with_name(f"{target_path.stem}.{lang3}.{ext}").exists()
        for ext in ("ass", "ssa", "srt")
    ):
        logger.debug(f"[SUBS] {label} already has a '{lang3}' subtitle sidecar")
        return None

    try:
        season_number = episode.season.season_number
        episode_number = episode.episode_number
    except Exception:
        season_number, episode_number = None, None
    if not episode_number or not season_number or season_number < 1:
        logger.info(
            f"[SUBS] skipping {label or target_path.name}: "
            "no season/episode numbering (movies are not supported yet)"
        )
        return None

    # Per-season MAL titles are the most reliable (scene releases are named
    # after them), but Jikan is flaky — the AniWorld page's own alternative
    # titles (which include the romaji name) work as a fallback.
    titles = []
    try:
        mal_ids = episode.series.mal_id or []
        if season_number <= len(mal_ids):
            titles = get_anime_titles(mal_ids[season_number - 1])
    except Exception as exc:
        logger.debug(f"[SUBS] MAL title lookup failed ({exc})")

    series = getattr(episode, "series", None)
    base_titles = []
    try:
        for alt in series.alternative_titles or []:
            if alt not in base_titles:
                base_titles.append(alt)
    except Exception as exc:
        logger.debug(f"[SUBS] alternative titles unavailable ({exc})")
    series_title = getattr(series, "title", None)
    if series_title and series_title not in base_titles:
        base_titles.append(series_title)

    if season_number == 1:
        for base in base_titles:
            if base not in titles:
                titles.append(base)
    elif not titles:
        # Sequel season without a MAL name: guess the scene naming, which
        # follows MAL's "<title> 2nd Season" / "<title> Season 2" style.
        ordinal = {1: "1st", 2: "2nd", 3: "3rd"}.get(
            season_number, f"{season_number}th"
        )
        for base in base_titles:
            for suffix in (f"{ordinal} Season", f"Season {season_number}"):
                candidate = f"{base} {suffix}"
                if candidate not in titles:
                    titles.append(candidate)

    titles = titles[:8]
    if not titles:
        logger.info(f"[SUBS] no searchable titles for {label}")
        return None

    found = _find_subtitle(titles, episode_number, lang3)
    if not found:
        logger.info(
            f"[SUBS] no '{lang3}' subtitle found for {label or target_path.name} "
            "(older shows often predate Erai-raws MultiSub releases)"
        )
        return None
    attachment_id, ext, release_title = found

    raw_sub = target_path.with_name(f"{target_path.stem}.{lang3}.{ext}")
    _download_attachment(attachment_id, lang3, ext, raw_sub)
    logger.info(f"[SUBS] fetched '{lang3}' subtitle from {release_title}")

    try:
        synced_sub = _align_subtitle(target_path, raw_sub, label)

        if is_mkv:
            _mux_subtitle_track(target_path, synced_sub, lang3, label)
            logger.info(
                f"[SUBS] added '{lang3}' subtitle track to {target_path.name}"
            )
            return target_path

        # Non-MKV containers can't hold ASS; leave an aligned sidecar file
        # that players pick up automatically.
        if synced_sub != raw_sub:
            os.replace(synced_sub, raw_sub)
        logger.info(f"[SUBS] wrote subtitle sidecar {raw_sub.name}")
        return raw_sub
    finally:
        if is_mkv:
            raw_sub.unlink(missing_ok=True)
            synced = raw_sub.with_name(f"{raw_sub.stem}.synced{raw_sub.suffix}")
            synced.unlink(missing_ok=True)
