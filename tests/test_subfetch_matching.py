"""Unit tests for the external subtitle fetcher's release matching.

Picking the wrong release is worse than finding nothing: sequel seasons share
almost all of their title words, so a naive similarity score happily returns
season 1's subtitles for a season 2 episode. These tests pin the matching rules
down without touching the network -- only the pure scoring/parsing helpers are
exercised.
"""

import pytest

from aniworld.models.aniworld_to.dubsync.subfetch import (
    LANG_ALIASES,
    MIN_TITLE_SCORE,
    _episode_re,
    _title_score,
    _tokens,
)

FRIEREN_S1 = "Sousou no Frieren"
FRIEREN_S2 = "Sousou no Frieren 2nd Season"


def _release(title: str, episode: int, tags: str = "[1080p CR WEB-DL AVC AAC]") -> str:
    return f"[Erai-raws] {title} - {episode:02d} {tags}[MultiSub][DEADBEEF]"


@pytest.mark.parametrize(
    "release_episode, wanted_episode, should_match",
    [
        (1, 1, True),
        (13, 13, True),
        (1, 11, False),  # "- 01" must not satisfy a search for episode 11
        (11, 1, False),  # ...nor the reverse
        (5, 15, False),
    ],
)
def test_episode_number_must_match_exactly(
    release_episode, wanted_episode, should_match
):
    matched = _episode_re(wanted_episode).search(_release(FRIEREN_S1, release_episode))
    assert bool(matched) is should_match


def test_versioned_release_still_matches():
    """Scene re-releases append a version suffix ("- 05v2")."""

    assert _episode_re(5).search("[Erai-raws] Sousou no Frieren - 05v2 [1080p]")


def test_romanization_difference_is_folded():
    """"Yume wo Minai" and "Yume o Minai" name the same show."""

    assert _tokens("Yume wo Minai") == _tokens("Yume o Minai")


def test_exact_title_scores_full_marks():
    score = _title_score(_release(FRIEREN_S1, 1), FRIEREN_S1, 1)
    assert score == pytest.approx(1.0)


def test_sequel_season_is_rejected_for_season_one():
    """The regression behind "no German subs for Frieren S2": a season 2
    release must not be accepted when season 1 was asked for."""

    score = _title_score(_release(FRIEREN_S2, 1), FRIEREN_S1, 1)
    assert score < MIN_TITLE_SCORE


def test_season_one_is_rejected_for_sequel_season():
    score = _title_score(_release(FRIEREN_S1, 1), FRIEREN_S2, 1)
    assert score < MIN_TITLE_SCORE


def test_sequel_season_matches_its_own_title():
    score = _title_score(_release(FRIEREN_S2, 1), FRIEREN_S2, 1)
    assert score >= MIN_TITLE_SCORE


def test_unrelated_show_scores_far_below_threshold():
    score = _title_score(_release("Kimetsu no Yaiba", 1), FRIEREN_S1, 1)
    assert score < MIN_TITLE_SCORE


def test_release_tags_do_not_inflate_the_score():
    """Quality/codec tags are noise and must not count as title words."""

    verbose = _release(FRIEREN_S1, 1, tags="[1080p CR WEBRip HEVC EAC3 Multi Sub]")
    assert _title_score(verbose, FRIEREN_S1, 1) == pytest.approx(1.0)


@pytest.mark.parametrize(
    "spelling, expected",
    [
        ("german", "ger"),
        ("de", "ger"),
        ("deu", "ger"),
        ("1", "ger"),  # bare --fetch-subs with no argument
        ("english", "eng"),
        ("fr", "fre"),
    ],
)
def test_language_spellings_map_to_release_codes(spelling, expected):
    assert LANG_ALIASES[spelling] == expected


def test_unknown_language_is_not_silently_accepted():
    assert "klingon" not in LANG_ALIASES
