"""DubSync file matcher.

Pairs local high-quality video files (e.g. Blu-ray/Nyaa rips) with the
corresponding AniWorld episodes so a German dub track can later be grafted in.

Two responsibilities, kept independent so the parsing half is unit-testable
without any network access:

1. Parse a directory of video filenames into ``(season, episode)`` keys,
   handling common scene/BD naming (``S01E01``, ``Show - 01``, ``01v2``,
   ``1x01``, ``- 12 (1080p)``, absolute numbering).
2. Enumerate the AniWorld source (series / season / episode URL or object) and
   pair each parsed file with its matching :class:`AniworldEpisode`, reporting
   whatever could not be paired in either direction.

Only :func:`match_directory` touches the network (it fetches the source
episode list). Everything under "Filename parsing" is pure stdlib.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Tuple

# Extensions we treat as remuxable video containers.
VIDEO_EXTENSIONS = {
    ".mkv",
    ".mp4",
    ".m4v",
    ".avi",
    ".mov",
    ".ts",
    ".m2ts",
    ".webm",
    ".wmv",
    ".flv",
    ".mpg",
    ".mpeg",
    ".ogm",
}

# Release noise that contains digits and would otherwise be mistaken for an
# episode number. Stripped (case-insensitively) before the episode-only search.
_NOISE_PATTERNS = [
    r"\d{3,4}x\d{3,4}",            # resolution: 1920x1080
    r"\b\d{3,4}[pi]\b",           # 1080p, 720p, 1080i
    r"\b(?:x|h)\.?26[45]\b",      # x264 / x265 / h264 / h265
    r"\bhevc\b",
    r"\bavc\b",
    r"\b(?:8|10|12)\s?bit\b",
    r"\b(?:aac|ac3|eac3|dts|flac|opus|mp3|truehd)\b",
    r"\b(?:blu-?ray|bd(?:rip)?|web-?dl|web-?rip|hdtv|dvd-?rip|remux)\b",
    r"\b(?:dual|multi)(?:-?audio)?\b",
    r"\b(?:19|20)\d{2}\b",        # years
    r"\b[0-9a-f]{8}\b",           # crc32 tag
]
_NOISE_RE = re.compile("|".join(_NOISE_PATTERNS), re.IGNORECASE)

_BRACKET_RE = re.compile(r"\[[^\]]*\]|\([^)]*\)|\{[^}]*\}")

# Explicit season+episode, e.g. S01E02, s1.e2, 1x02.
_SxxExx_RE = re.compile(r"(?i)s(\d{1,2})[\s._-]*e(\d{1,4})")
_NxNN_RE = re.compile(r"(?i)\b(\d{1,2})x(\d{1,3})\b")

# Season detected in a folder / filename ("S04", "Staffel 4", "Season 4",
# "Re_Zero_S4"). Underscores are word chars, so use an explicit non-alnum
# lookbehind instead of \b to catch "_S4".
_SEASON_RE = re.compile(
    r"(?i)(?<![a-z0-9])(?:s|staffel|season)[\s._-]*(\d{1,2})(?![0-9])"
)

# Episode-only markers, tried in order of confidence.
_EPISODE_PATTERNS = [
    re.compile(r"(?i)\b(?:e|ep|episode|folge)[\s._-]*(\d{1,4})"),
    re.compile(r"(?:^|[\s._-])-[\s._-]*(\d{1,4})(?:v\d+)?(?=[\s._-]|$)"),  # " - 01", "-01v2"
    re.compile(r"(?:^|[\s._-])#?(\d{1,4})(?:v\d+)?(?=[\s._-]|$)"),          # standalone
]


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------


@dataclass
class ParsedFile:
    """A local video file whose ``(season, episode)`` could be parsed."""

    path: Path
    season: Optional[int]  # None when the filename carried no season hint
    episode: int


@dataclass
class MatchReport:
    """Outcome of pairing a directory against an AniWorld source."""

    # (local file, matching AniWorld episode)
    pairs: List[Tuple[ParsedFile, "object"]] = field(default_factory=list)
    # files whose season/episode could not be parsed at all
    unmatched_files: List[Path] = field(default_factory=list)
    # files that parsed but had no corresponding source episode
    unpaired_files: List[ParsedFile] = field(default_factory=list)
    # source episodes (season, number) with no local file
    missing_sources: List[Tuple[Optional[int], int]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Filename parsing (pure, no network)
# ---------------------------------------------------------------------------


def _strip_noise(stem: str) -> str:
    """Remove bracketed groups and release metadata so only the title/number
    survives for the episode-only heuristics."""

    text = _BRACKET_RE.sub(" ", stem)
    text = _NOISE_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _find_episode_number(text: str) -> Optional[int]:
    for pattern in _EPISODE_PATTERNS:
        matches = list(pattern.finditer(text))
        if matches:
            # Prefer the last hit: the episode number sits near the end,
            # after the show title.
            return int(matches[-1].group(1))
    return None


def parse_filename(name: str) -> Optional[Tuple[Optional[int], int]]:
    """Parse a filename into ``(season, episode)``.

    ``season`` is ``None`` when the name carried no season marker (common with
    single-season anime named ``Show - 01``); the caller resolves it from the
    folder or the source. Returns ``None`` when no episode number is found.
    """

    stem = os.path.splitext(name)[0]

    m = _SxxExx_RE.search(stem)
    if m:
        return int(m.group(1)), int(m.group(2))

    cleaned = _strip_noise(stem)

    m = _NxNN_RE.search(cleaned)
    if m:
        return int(m.group(1)), int(m.group(2))

    episode = _find_episode_number(cleaned)
    if episode is not None:
        return None, episode

    return None


def parse_season_from_text(text: str) -> Optional[int]:
    """Extract a season number from a folder or file name, if present."""

    m = _SEASON_RE.search(text)
    return int(m.group(1)) if m else None


def _iter_video_files(target: Path, recursive: bool) -> Iterator[Path]:
    walker = target.rglob("*") if recursive else target.iterdir()
    for path in sorted(walker):
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            yield path


def scan_directory(
    target_dir: os.PathLike | str, recursive: bool = False
) -> Tuple[List[ParsedFile], List[Path]]:
    """Scan ``target_dir`` for video files and parse each into a season/episode.

    Returns ``(parsed, unmatched)`` where *unmatched* holds files whose
    episode number could not be determined. Season is inferred from the folder
    name when the filename itself lacks one; it may still be ``None`` here and
    is finalised during pairing.
    """

    target = Path(target_dir)
    if not target.is_dir():
        raise NotADirectoryError(f"Not a directory: {target}")

    folder_season = parse_season_from_text(target.name)

    parsed: List[ParsedFile] = []
    unmatched: List[Path] = []

    for path in _iter_video_files(target, recursive):
        result = parse_filename(path.name)
        if result is None:
            unmatched.append(path)
            continue
        season, episode = result
        if season is None:
            season = folder_season
        parsed.append(ParsedFile(path=path, season=season, episode=episode))

    return parsed, unmatched


# ---------------------------------------------------------------------------
# Source enumeration + pairing (touches the network)
# ---------------------------------------------------------------------------


def _build_source_from_url(source_url: str):
    """Resolve a URL string to a series / season / episode model object."""

    from ....providers import normalize_url, resolve_provider

    url = normalize_url(source_url)
    provider = resolve_provider(url)

    if provider.season_pattern and provider.season_pattern.fullmatch(url):
        return provider.season_cls(url)
    if provider.series_pattern and provider.series_pattern.fullmatch(url):
        return provider.series_cls(url)
    if provider.episode_pattern and provider.episode_pattern.fullmatch(url):
        return provider.episode_cls(url)

    raise ValueError(f"Unsupported DubSync source URL: {source_url}")


def _iter_source_episodes(source) -> Iterator[Tuple[Optional[int], object]]:
    """Yield ``(season_number, episode)`` for every episode in *source*.

    *source* may be a URL string, a series object (has ``.seasons``), a season
    object (has ``.episodes``), or a single episode object.
    """

    if isinstance(source, str):
        source = _build_source_from_url(source)

    if hasattr(source, "seasons"):  # series
        for season in source.seasons:
            for episode in season.episodes:
                yield season.season_number, episode
    elif hasattr(source, "episodes"):  # season
        season_number = getattr(source, "season_number", None)
        for episode in source.episodes:
            yield season_number, episode
    else:  # single episode
        season_number = None
        try:
            season_number = source.season.season_number
        except Exception:  # noqa: BLE001 - season lookup is best-effort
            pass
        yield season_number, source


def build_source_index(source):
    """Index a source into lookup maps used for pairing.

    Returns ``(by_key, by_abs, season_numbers)``:
      * ``by_key``  -- ``{(season, episode): episode_obj}``
      * ``by_abs``  -- ``{episode_number: (season, episode_obj)}`` for numbers
        that are unique across all seasons (enables absolute-numbering fallback)
      * ``season_numbers`` -- the set of distinct season numbers seen
    """

    by_key: dict = {}
    abs_seen: dict = {}
    abs_dupes: set = set()
    season_numbers: set = set()
    numberless: list = []

    for season_number, episode in _iter_source_episodes(source):
        number = getattr(episode, "episode_number", None)
        if number is None:
            numberless.append((season_number, episode))
            continue
        season_numbers.add(season_number)
        by_key[(season_number, number)] = episode
        if number in abs_seen:
            abs_dupes.add(number)
        else:
            abs_seen[number] = (season_number, episode)

    # Movie-site sources (MegaKino/FilmPalast) resolve to a single episode
    # object without an episode_number; treat a lone numberless episode as
    # episode 1 so it stays addressable via (None, 1).
    if not by_key and len(numberless) == 1:
        season_number, episode = numberless[0]
        by_key[(season_number, 1)] = episode
        season_numbers.add(season_number)
        abs_seen[1] = (season_number, episode)

    by_abs = {n: v for n, v in abs_seen.items() if n not in abs_dupes}
    return by_key, by_abs, season_numbers


def match_directory(
    target_dir: os.PathLike | str,
    source,
    recursive: bool = False,
    selected: Optional[Iterable[Tuple[Optional[int], int]]] = None,
    explicit: Optional[Iterable[Tuple[Optional[int], int, str]]] = None,
) -> MatchReport:
    """Pair the video files in ``target_dir`` with *source*'s episodes.

    *source* is anything :func:`_iter_source_episodes` accepts (a URL string or
    a series/season/episode object). Season is resolved as: the filename's own
    season if present, else the source's single season number when the source
    has exactly one, else ``1``. Unmatched local files fall back to absolute
    numbering when the source has globally-unique episode numbers.

    ``selected`` optionally restricts pairing to the given
    ``(season, episode)`` keys (e.g. the user's checklist in the web UI);
    everything else in the source is treated as if it did not exist.

    ``explicit`` provides user-confirmed ``(season, episode, filename)``
    triples -- used for movies, whose filenames carry no season/episode
    pattern. The filename may be a bare name, a path relative to
    ``target_dir``, or absolute. Explicit pairs bypass filename parsing and
    the ``selected`` filter; a triple whose source episode or local file
    cannot be found lands in ``missing_sources``.
    """

    parsed, unmatched = scan_directory(target_dir, recursive=recursive)
    by_key, by_abs, season_numbers = build_source_index(source)

    explicit_pairs: List[Tuple[ParsedFile, object]] = []
    explicit_missing: List[Tuple[Optional[int], int]] = []
    if explicit:
        target = Path(target_dir)
        all_paths = [pf.path for pf in parsed] + list(unmatched)

        def _find_file(name: str) -> Optional[Path]:
            for p in all_paths:
                try:
                    rel = str(p.relative_to(target))
                except ValueError:
                    rel = p.name
                if name in (p.name, rel, str(p)):
                    return p
            return None

        used_paths: set = set()
        for s, e, fname in explicit:
            key = (int(s) if s is not None else None, int(e))
            matched_key = key
            episode = by_key.get(key)
            # Movie-site sources index their single film as (None, 1) while
            # the web UI labels it season 1; fall back on episode number.
            if episode is None and (None, key[1]) in by_key:
                matched_key = (None, key[1])
                episode = by_key[matched_key]
            path = _find_file(fname)
            if episode is None or path is None or path in used_paths:
                explicit_missing.append(key)
                continue
            used_paths.add(path)
            explicit_pairs.append(
                (ParsedFile(path=path, season=key[0], episode=key[1]), episode)
            )
            by_key.pop(matched_key, None)
            by_abs = {n: v for n, v in by_abs.items() if v[1] is not episode}

        parsed = [pf for pf in parsed if pf.path not in used_paths]
        unmatched = [p for p in unmatched if p not in used_paths]
        season_numbers = {k[0] for k in by_key}

    if selected is not None:
        sel = {(s, int(e)) for s, e in selected}
        by_key = {k: v for k, v in by_key.items() if k in sel}
        by_abs = {n: v for n, v in by_abs.items() if (v[0], n) in sel}
        season_numbers = {k[0] for k in by_key}

    single_season = next(iter(season_numbers)) if len(season_numbers) == 1 else None

    report = MatchReport(unmatched_files=list(unmatched))
    report.pairs.extend(explicit_pairs)
    used_keys: set = set()

    for pf in parsed:
        season = pf.season
        if season is None:
            season = single_season if single_season is not None else 1

        episode = by_key.get((season, pf.episode))
        matched_key = (season, pf.episode)

        # Absolute-numbering fallback: only when the file gave no explicit
        # season and the source numbers are globally unique.
        if episode is None and pf.season is None and pf.episode in by_abs:
            matched_key, episode = by_abs[pf.episode]

        if episode is None:
            report.unpaired_files.append(pf)
            continue

        report.pairs.append((pf, episode))
        used_keys.add(matched_key)

    report.missing_sources = [
        key for key in by_key if key not in used_keys
    ] + explicit_missing
    return report
