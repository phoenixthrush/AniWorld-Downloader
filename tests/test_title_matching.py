"""Matching a series to its folder on disk.

A folder carries whatever the naming template added, so the match cannot be
exact. It also cannot be a plain prefix, or a series would claim the folder of
a longer named one sitting next to it, which is very common in anime:
Naruto / Naruto Shippuden, Overlord / Overlord II, Dragon Ball / Dragon Ball Z.
"""

import pytest

from aniworld.web import autosync, media
from aniworld.web.media import folder_matches_title


class Series:
    def __init__(self, title):
        self.title_cleaned = title


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "folder",
    [
        "Naruto",
        "naruto",
        "NARUTO",
        "Naruto (2002)",
        "Naruto (2002) [imdbid-tt0409591]",
        "Naruto [imdbid-tt0409591]",
        "Naruto - 2002",
        "Naruto.2002",
        "Naruto  (2002)",
    ],
)
def test_the_same_series_matches_however_it_is_decorated(folder):
    assert folder_matches_title(folder, "Naruto") is True


@pytest.mark.parametrize(
    "folder",
    [
        "Naruto Shippuden",
        "Naruto Shippuden (2007)",
        "NarutoShippuden",
        "Naruto2",
        "Narutopia",
    ],
)
def test_a_longer_named_series_is_not_claimed(folder):
    assert folder_matches_title(folder, "Naruto") is False


@pytest.mark.parametrize(
    "title,folder",
    [
        ("Overlord", "Overlord II"),
        ("Dragon Ball", "Dragon Ball Z"),
        ("Attack on Titan", "Attack on Titan Final Season"),
        ("Fairy Tail", "Fairy Tail 100 Years Quest"),
        ("One Piece", "One Piece Film Red"),
        ("Konosuba", "Konosuba 2"),
    ],
)
def test_the_pairs_this_actually_happens_with(title, folder):
    assert folder_matches_title(folder, title) is False


def test_the_longer_title_still_finds_its_own_folder():
    assert folder_matches_title("Naruto Shippuden (2007)", "Naruto Shippuden") is True


def test_an_unrelated_folder_never_matches():
    assert folder_matches_title("Bleach", "Naruto") is False


# ---------------------------------------------------------------------------
# Titles made of punctuation
#
# A sequel is very often the same name with more punctuation, so "not a letter
# or digit" is not enough to call something decoration.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "title,folder",
    [
        ("K-On!", "K-On!! (2010)"),
        ("Working!!", "Working!!! (2015)"),
        ("Yuru Yuri", "Yuru Yuri♪♪ (2012)"),
        ("Aho-Girl", "Aho-Girl! (2017)"),
        ("Steins;Gate", "Steins;Gate 0 (2018)"),
        ("Ao-chan Can't Study!", "Ao-chan Can't Study!! (2020)"),
    ],
)
def test_more_punctuation_means_a_different_series(title, folder):
    assert folder_matches_title(folder, title) is False


def test_titles_that_differ_only_by_a_stripped_character_share_a_folder():
    """ "Nisekoi" and "Nisekoi:" both become "Nisekoi" on disk, so the
    downloader already writes them into one folder. Telling them apart here
    would only disagree with where the files actually went."""
    from aniworld.models.common.common import clean_title

    assert clean_title("Nisekoi:") == clean_title("Nisekoi")
    assert folder_matches_title("Nisekoi (2014)", "Nisekoi:") is True


@pytest.mark.parametrize(
    "title,folder",
    [
        ("K-On!", "K-On! (2009)"),
        ("K-On!!", "K-On!! (2010) [imdbid-tt1663759]"),
        ("Working!!", "Working!! (2010)"),
        ("Steins;Gate", "Steins;Gate (2011)"),
        ("Ao-chan Can't Study!", "Ao-chan Can't Study! (2019)"),
        ("Ao-chan Can't Study!", "Ao-chan Can't Study!"),
    ],
)
def test_a_punctuated_title_still_finds_its_own_folder(title, folder):
    assert folder_matches_title(folder, title) is True


# ---------------------------------------------------------------------------
# Characters the downloader strips out of folder names
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "title,folder",
    [
        ("Re:Zero kara Hajimeru Isekai", "ReZero kara Hajimeru Isekai (2016)"),
        ("Kaguya-sama: Love is War", "Kaguya-sama Love is War (2019)"),
        ("Fate/Zero", "FateZero (2011)"),
        ("Is It Wrong to Try?", "Is It Wrong to Try (2015)"),
        ('The "Hero" Returns', "The Hero Returns (2024)"),
        ("Dr. Stone: New World", "Dr. Stone New World (2023)"),
    ],
)
def test_a_title_matches_the_folder_the_downloader_made_for_it(title, folder):
    """The folder went through clean_title, the title did not, so autosync
    would otherwise never recognise anything with a colon in its name."""
    assert folder_matches_title(folder, title) is True


def test_the_stripped_characters_are_the_ones_the_downloader_removes():
    """If clean_title ever changes, this matcher has to change with it."""
    from aniworld.models.common.common import FORBIDDEN_CHARS

    assert media.FOLDER_UNSAFE.pattern == FORBIDDEN_CHARS.pattern


def test_a_real_title_survives_a_round_trip_through_clean_title():
    from aniworld.models.common.common import clean_title

    title = "Ao-chan Can’t Study!"
    folder = f"{clean_title(title)} (2019) [imdbid-tt9819822]"
    assert folder_matches_title(folder, title) is True


# ---------------------------------------------------------------------------
# Quote characters
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "title,folder",
    [
        ("Ao-chan Can't Study!", "Ao-chan Can’t Study! (2019)"),
        ("Ao-chan Can’t Study!", "Ao-chan Can't Study! (2019)"),
        ("Ao-chan Can’t Study!", "Ao-chan Can’t Study! (2019)"),
        ("Ao-chan Can't Study!", "Ao-chan Can't Study! (2019)"),
    ],
)
def test_either_apostrophe_works(title, folder):
    """aniworld writes a curly apostrophe, a hand renamed folder often has a
    straight one, and they have to mean the same title."""
    assert folder_matches_title(folder, title) is True


def test_a_curly_quoted_sequel_is_still_told_apart():
    assert (
        folder_matches_title("Ao-chan Can’t Study!! (2020)", "Ao-chan Can't Study!")
        is False
    )


# ---------------------------------------------------------------------------
# Spacing
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "title,folder",
    [
        ("Naruto", "Naruto  (2002)"),
        ("Naruto", " Naruto (2002) "),
        ("A  Silent  Voice", "A Silent Voice (2016)"),
    ],
)
def test_spacing_differences_do_not_break_the_match(title, folder):
    assert folder_matches_title(folder, title) is True


def test_a_stripped_character_is_removed_not_turned_into_a_space():
    """clean_title deletes the slash outright, so the folder is "FateZero".
    Matching has to do the same or it would miss its own folder."""
    from aniworld.models.common.common import clean_title

    assert clean_title("Fate/Zero") == "FateZero"
    assert folder_matches_title("FateZero (2011)", "Fate/Zero") is True
    assert folder_matches_title("Fate Zero (2011)", "Fate/Zero") is False


# ---------------------------------------------------------------------------
# Custom naming templates
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "folder",
    ["Naruto - 2002", "Naruto.2002", "Naruto_2002", "Naruto - (2002)"],
)
def test_a_separator_before_a_number_is_still_decoration(folder):
    """Someone using "{title} - {year}" must not lose every tick."""
    assert folder_matches_title(folder, "Naruto") is True


@pytest.mark.parametrize(
    "folder",
    ["Naruto - Shippuden", "Naruto - The Movie", "Naruto.Shippuden"],
)
def test_a_separator_before_a_word_is_a_different_series(folder):
    assert folder_matches_title(folder, "Naruto") is False


@pytest.mark.parametrize("title", ["", "   "])
def test_an_empty_title_matches_nothing(title):
    assert folder_matches_title("Naruto", title) is False


def test_surrounding_whitespace_is_ignored():
    assert folder_matches_title("  Naruto  ", " Naruto ") is True


# ---------------------------------------------------------------------------
# What the download modal shows
# ---------------------------------------------------------------------------
def test_a_sequel_on_disk_does_not_tick_the_original(episode_file):
    """The ticks in the episode list come from this, so a false hit tells you
    an episode is downloaded when it is not."""
    episode_file("Naruto Shippuden", 1, 1)
    episode_file("Naruto Shippuden", 1, 2)
    assert media.downloaded_episodes(Series("Naruto")) == set()


def test_the_sequel_still_reports_its_own_episodes(episode_file):
    episode_file("Naruto Shippuden", 1, 1)
    assert media.downloaded_episodes(Series("Naruto Shippuden")) == {(1, 1)}


def test_both_series_side_by_side(episode_file):
    episode_file("Naruto (2002)", 1, 5)
    episode_file("Naruto Shippuden (2007)", 1, 9)
    assert media.downloaded_episodes(Series("Naruto")) == {(1, 5)}
    assert media.downloaded_episodes(Series("Naruto Shippuden")) == {(1, 9)}


def test_the_template_decorated_folder_is_still_found(episode_file):
    episode_file("Naruto (2002) [imdbid-tt0409591]", 1, 1)
    assert media.downloaded_episodes(Series("Naruto")) == {(1, 1)}


def test_the_card_badge_and_the_episode_ticks_agree(episode_file):
    """The badge list is filtered in the browser with the same rule, so the
    two must not contradict each other on the same library."""
    episode_file("Naruto Shippuden", 1, 1)
    assert media.downloaded_folder_names() == ["Naruto Shippuden"]
    assert media.downloaded_episodes(Series("Naruto")) == set()


# ---------------------------------------------------------------------------
# What AutoSync picks up
# ---------------------------------------------------------------------------
@pytest.fixture
def feed(monkeypatch):
    def use(title, slug):
        monkeypatch.setattr(
            autosync,
            "fetch_new_episodes",
            lambda: [
                {
                    "title": title,
                    "url": f"https://aniworld.to/anime/stream/{slug}/staffel-1/episode-9",
                    "languages": ["german"],
                }
            ],
        )

    return use


def test_a_sequel_folder_does_not_make_the_original_a_candidate(feed, downloads):
    """Otherwise AutoSync queues a series you do not own, unattended."""
    (downloads / "Naruto Shippuden").mkdir()
    feed("Naruto", "naruto")
    assert autosync.find_candidates() == []


def test_the_series_you_do_own_is_still_a_candidate(feed, downloads):
    (downloads / "Naruto Shippuden").mkdir()
    feed("Naruto Shippuden", "naruto-shippuuden")
    candidates = autosync.find_candidates()
    assert len(candidates) == 1
    assert candidates[0]["folder"].name == "Naruto Shippuden"


def test_the_decorated_folder_is_still_matched(feed, downloads):
    (downloads / "Naruto (2002) [imdbid-tt0409591]").mkdir()
    feed("Naruto", "naruto")
    assert len(autosync.find_candidates()) == 1


def test_the_right_folder_is_picked_when_both_exist(feed, downloads):
    (downloads / "Naruto (2002)").mkdir()
    (downloads / "Naruto Shippuden (2007)").mkdir()
    feed("Naruto", "naruto")
    assert autosync.find_candidates()[0]["folder"].name == "Naruto (2002)"


# ---------------------------------------------------------------------------
# HTML entities in scraped titles (issue #279)
#
# The sites serve titles HTML escaped, so "It's" arrives as "It&#039;s". Left
# undecoded it goes straight into the folder and file names, and then no longer
# matches its own folder, so the whole series gets downloaded again.
#
# These call the private extractors with canned markup rather than the network,
# so they belong in the automated suite. The live check lives in
# tests/test_providers_serienstream.py.
# ---------------------------------------------------------------------------
def _with_html(cls, markup, *empty_caches):
    """A model instance holding canned markup, with no network behind it.

    _html is a read-only property that fetches on first access, so the cache it
    writes into is primed directly. Properties that memoise into their own
    private attribute need that attribute to exist as well, hence empty_caches.
    """
    instance = cls.__new__(cls)
    setattr(instance, f"_{cls.__name__}__html", markup)
    for name in empty_caches:
        setattr(instance, f"_{cls.__name__}__{name}", None)
    return instance


def _extract(instance, name):
    """Call a name-mangled private extractor."""
    return getattr(instance, f"_{type(instance).__name__}{name}")()


def test_serienstream_decodes_entities_in_the_title():
    from aniworld.models.s_to.series import SerienstreamSeries

    series = _with_html(
        SerienstreamSeries, '<h1 class="h2 mb-1 fw-bold">It&#039;s Always Sunny</h1>'
    )
    assert _extract(series, "__extract_title") == "It's Always Sunny"


def test_megakino_decodes_entities_in_the_title():
    from aniworld.models.megakino.series import MegaKinoEpisode

    episode = _with_html(
        MegaKinoEpisode, '<meta itemprop="name" content="It&#039;s Complicated">'
    )
    _extract(episode, "__extract_title")
    assert episode._MegaKinoEpisode__title == "It's Complicated"


def test_filmpalast_decodes_entities_in_the_title():
    from aniworld.models.filmpalast_to.episode import FilmPalastEpisode

    episode = _with_html(
        FilmPalastEpisode, '<em itemprop="name">It&#039;s a Wonderful Life</em>'
    )
    _extract(episode, "__extract_title_de")
    assert episode._FilmPalastEpisode__title_de == "It's a Wonderful Life"


def test_an_apostrophe_survives_all_the_way_to_the_folder_name():
    """The whole point: a decoded title has to stay intact through clean_title."""
    from aniworld.models.common import clean_title

    assert clean_title("It's Always Sunny in Philadelphia") == (
        "It's Always Sunny in Philadelphia"
    )


def test_an_undecoded_title_would_not_match_its_own_folder():
    """Why this bug costs a re-download, not just an ugly name."""
    from aniworld.web.media import folder_matches_title

    assert folder_matches_title(
        "It's Always Sunny in Philadelphia (2005)", "It's Always Sunny in Philadelphia"
    )
    assert not folder_matches_title(
        "It&#039;s Always Sunny in Philadelphia (2005)",
        "It's Always Sunny in Philadelphia",
    )


def test_kinox_decodes_entities_in_the_title():
    from aniworld.models.kinox.series import KinoxSeries

    series = _with_html(
        KinoxSeries,
        '<meta property="og:title" content="It&#039;s Complicated (2009)">',
        "title",
        "slug",
    )
    assert series.title == "It's Complicated"


def test_burningseries_decodes_entities_in_the_title():
    from aniworld.models.burningseries.series import BurningSeriesSeries

    series = _with_html(
        BurningSeriesSeries, "<h2>It&#039;s Always Sunny</h2>", "title", "slug"
    )
    assert series.title == "It's Always Sunny"


def test_every_provider_decodes_entities_in_its_title_path():
    """Checking the file merely contains "unescape" is not enough.

    kinox and burningseries both had unescape elsewhere in the file while their
    title property did not decode, so a grep for the word passed while the bug
    was live. This drives each provider's real title extraction instead.
    """
    from aniworld.models.burningseries.series import BurningSeriesSeries
    from aniworld.models.filmpalast_to.episode import FilmPalastEpisode
    from aniworld.models.kinox.series import KinoxSeries
    from aniworld.models.megakino.series import MegaKinoEpisode
    from aniworld.models.s_to.series import SerienstreamSeries

    cases = [
        (
            SerienstreamSeries,
            '<h1 class="h2 mb-1 fw-bold">A&#039;B</h1>',
            lambda o: _extract(o, "__extract_title"),
        ),
        (
            MegaKinoEpisode,
            '<meta itemprop="name" content="A&#039;B">',
            lambda o: (_extract(o, "__extract_title"), o._MegaKinoEpisode__title)[1],
        ),
        (
            FilmPalastEpisode,
            '<em itemprop="name">A&#039;B</em>',
            lambda o: (
                _extract(o, "__extract_title_de"),
                o._FilmPalastEpisode__title_de,
            )[1],
        ),
        (
            KinoxSeries,
            '<meta property="og:title" content="A&#039;B">',
            lambda o: o.title,
        ),
        (BurningSeriesSeries, "<h2>A&#039;B</h2>", lambda o: o.title),
    ]

    still_escaped = []
    for cls, markup, read in cases:
        if read(_with_html(cls, markup, "title", "slug")) != "A'B":
            still_escaped.append(cls.__name__)
    assert not still_escaped, f"titles still HTML escaped: {still_escaped}"
