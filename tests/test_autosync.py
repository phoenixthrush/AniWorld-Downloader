"""AutoSync matching and its exclusion list.

aniworld.to is never contacted: the "newest episodes" feed is replaced with a
fixed list and series objects are stand-ins.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from aniworld.web import autosync, db


# ---------------------------------------------------------------------------
# Exclusions
# ---------------------------------------------------------------------------
def test_a_series_can_be_excluded():
    url = "https://aniworld.to/anime/stream/naruto"
    db.add_autosync_exclusion(url, "Naruto")
    assert db.is_autosync_excluded(url) is True
    assert db.excluded_series_urls() == {url}


def test_nothing_is_excluded_to_begin_with():
    assert db.excluded_series_urls() == set()
    assert db.is_autosync_excluded("https://x") is False


def test_excluding_twice_keeps_one_row():
    db.add_autosync_exclusion("https://x", "One")
    db.add_autosync_exclusion("https://x", "Two")
    rows = db.get_autosync_exclusions()
    assert len(rows) == 1
    assert rows[0]["title"] == "One", "the first title is kept"


def test_an_exclusion_can_be_lifted_by_url():
    db.add_autosync_exclusion("https://x", "One")
    db.remove_autosync_exclusion(series_url="https://x")
    assert db.excluded_series_urls() == set()


def test_an_exclusion_can_be_lifted_by_id():
    db.add_autosync_exclusion("https://x", "One")
    row_id = db.get_autosync_exclusions()[0]["id"]
    db.remove_autosync_exclusion(exclusion_id=row_id)
    assert db.get_autosync_exclusions() == []


def test_lifting_a_missing_exclusion_is_harmless():
    db.remove_autosync_exclusion(series_url="https://nope")
    db.remove_autosync_exclusion(exclusion_id=4242)


def test_exclusions_are_listed_alphabetically():
    db.add_autosync_exclusion("https://b", "Zebra")
    db.add_autosync_exclusion("https://a", "apple")
    assert [row["title"] for row in db.get_autosync_exclusions()] == ["apple", "Zebra"]


# ---------------------------------------------------------------------------
# Remembering the last run
# ---------------------------------------------------------------------------
def test_state_starts_empty():
    assert db.get_autosync_state() == {}


def test_state_round_trips():
    db.set_autosync_state(last_run="2026-01-01T00:00:00", last_report='{"queued": 1}')
    state = db.get_autosync_state()
    assert state["last_run"] == "2026-01-01T00:00:00"
    assert state["last_report"] == '{"queued": 1}'


def test_state_is_overwritten_not_appended():
    db.set_autosync_state(last_run="first")
    db.set_autosync_state(last_run="second")
    assert db.get_autosync_state()["last_run"] == "second"


def test_state_values_are_stored_as_text():
    db.set_autosync_state(count=5, missing=None)
    state = db.get_autosync_state()
    assert state["count"] == "5"
    assert state["missing"] is None


# ---------------------------------------------------------------------------
# URL handling
# ---------------------------------------------------------------------------
def test_an_episode_url_is_cut_back_to_its_series():
    assert (
        autosync._series_url(
            "https://aniworld.to/anime/stream/naruto/staffel-1/episode-5"
        )
        == "https://aniworld.to/anime/stream/naruto"
    )


def test_a_series_url_is_left_alone():
    url = "https://aniworld.to/anime/stream/naruto"
    assert autosync._series_url(url) == url


# ---------------------------------------------------------------------------
# Finding candidates
# ---------------------------------------------------------------------------
@pytest.fixture
def feed(monkeypatch):
    """Replace the newest-episodes feed with a fixed list."""

    def use(entries):
        monkeypatch.setattr(autosync, "fetch_new_episodes", lambda: entries)

    return use


def entry(title, slug, languages=("german",), episode=5):
    return {
        "title": title,
        "url": f"https://aniworld.to/anime/stream/{slug}/staffel-1/episode-{episode}",
        "languages": list(languages),
    }


def test_a_new_episode_of_a_series_on_disk_is_a_candidate(feed, downloads):
    (downloads / "Naruto").mkdir()
    feed([entry("Naruto", "naruto")])
    candidates = autosync.find_candidates()
    assert len(candidates) == 1
    assert candidates[0]["series_url"] == "https://aniworld.to/anime/stream/naruto"


def test_a_series_that_is_not_on_disk_is_ignored(feed, downloads):
    feed([entry("Naruto", "naruto")])
    assert autosync.find_candidates() == []


def test_matching_ignores_case_and_a_year_suffix(feed, downloads):
    (downloads / "naruto (2002)").mkdir()
    feed([entry("Naruto", "naruto")])
    assert len(autosync.find_candidates()) == 1


def test_an_excluded_series_is_skipped(feed, downloads):
    (downloads / "Naruto").mkdir()
    db.add_autosync_exclusion("https://aniworld.to/anime/stream/naruto", "Naruto")
    feed([entry("Naruto", "naruto")])
    assert autosync.find_candidates() == []


def test_lifting_the_exclusion_brings_it_back(feed, downloads):
    (downloads / "Naruto").mkdir()
    url = "https://aniworld.to/anime/stream/naruto"
    feed([entry("Naruto", "naruto")])
    db.add_autosync_exclusion(url, "Naruto")
    assert autosync.find_candidates() == []

    db.remove_autosync_exclusion(series_url=url)
    assert len(autosync.find_candidates()) == 1


def test_several_new_episodes_of_one_series_count_once(feed, downloads):
    (downloads / "Naruto").mkdir()
    feed([entry("Naruto", "naruto", episode=5), entry("Naruto", "naruto", episode=6)])
    assert len(autosync.find_candidates()) == 1


def test_every_announced_episode_is_kept(feed, downloads):
    """One row per series, but all of its new episode URLs come along."""
    (downloads / "Naruto").mkdir()
    feed([entry("Naruto", "naruto", episode=5), entry("Naruto", "naruto", episode=6)])
    urls = autosync.find_candidates()[0]["new_episode_urls"]
    assert [url.rsplit("-", 1)[1] for url in urls] == ["5", "6"]


def test_the_languages_of_every_announced_episode_are_merged(feed, downloads):
    """Episode 5 out as a dub and 6 as a sub means the series has both."""
    (downloads / "Naruto").mkdir()
    feed(
        [
            entry("Naruto", "naruto", languages=("german",), episode=5),
            entry("Naruto", "naruto", languages=("japanese-german",), episode=6),
        ]
    )
    assert autosync.find_candidates()[0]["new_languages"] == {
        "German Dub",
        "German Sub",
    }


def test_entries_without_a_title_are_skipped(feed, downloads):
    (downloads / "Naruto").mkdir()
    feed([entry("", "naruto")])
    assert autosync.find_candidates() == []


def test_the_languages_of_the_new_episode_are_carried_over(feed, downloads):
    (downloads / "Naruto").mkdir()
    feed([entry("Naruto", "naruto", languages=("german", "japanese-german"))])
    assert autosync.find_candidates()[0]["new_languages"] == {
        "German Dub",
        "German Sub",
    }


def test_unknown_language_flags_are_dropped(feed, downloads):
    (downloads / "Naruto").mkdir()
    feed([entry("Naruto", "naruto", languages=("klingon",))])
    assert autosync.find_candidates()[0]["new_languages"] == set()


def test_titles_in_a_custom_path_are_matched(feed, tmp_path):
    other = tmp_path / "other"
    (other / "Naruto").mkdir(parents=True)
    path_id = db.add_custom_path("Other", str(other))
    feed([entry("Naruto", "naruto")])
    assert autosync.find_candidates()[0]["custom_path_id"] == path_id


def test_language_folders_are_searched_when_separation_is_on(
    feed, monkeypatch, downloads
):
    monkeypatch.setenv("ANIWORLD_LANG_SEPARATION", "1")
    (downloads / "german-dub" / "Naruto").mkdir(parents=True)
    feed([entry("Naruto", "naruto")])
    candidate = autosync.find_candidates()[0]
    assert candidate["lang_folder"] == "german-dub"


def test_hidden_folders_are_not_matched(feed, downloads):
    (downloads / ".Naruto").mkdir()
    feed([entry(".Naruto", "naruto")])
    assert autosync.find_candidates() == []


def test_a_feed_that_cannot_be_fetched_raises(feed, downloads):
    feed(None)
    with pytest.raises(RuntimeError):
        autosync.find_candidates()


# ---------------------------------------------------------------------------
# Handling one candidate
# ---------------------------------------------------------------------------
def candidate(
    folder,
    languages,
    path_id=None,
    lang_folder=None,
    new_urls=None,
    root_name="Default",
):
    return {
        "title": "Naruto",
        "series_url": "https://aniworld.to/anime/stream/naruto",
        "folder": folder,
        "custom_path_id": path_id,
        "lang_folder": lang_folder,
        "root_name": root_name,
        "new_languages": set(languages),
        "new_episode_urls": new_urls or [],
    }


def test_a_copy_already_in_the_queue_is_skipped(downloads, queue_item):
    folder = downloads / "german-dub" / "Naruto"
    folder.mkdir(parents=True)
    queue_item(
        series_url="https://aniworld.to/anime/stream/naruto", language="German Dub"
    )
    row = autosync._handle(
        candidate(folder, {"German Dub"}, lang_folder="german-dub"), "VOE"
    )
    assert row["status"] == "skipped"
    assert row["reason"] == "This copy is already in the queue."


def test_another_copy_of_a_queued_series_is_not_blocked(
    monkeypatch, downloads, queue_item
):
    """The German copy being queued must not silence the English one."""
    folder = downloads / "english-dub" / "Naruto"
    folder.mkdir(parents=True)
    queue_item(
        series_url="https://aniworld.to/anime/stream/naruto", language="German Dub"
    )
    monkeypatch.setattr(
        autosync, "_missing_episodes", lambda series, have: ["https://x/ep5"]
    )
    monkeypatch.setattr(
        autosync, "resolve_provider", lambda url: _FakeProvider("Naruto")
    )

    row = autosync._handle(
        candidate(folder, {"English Dub"}, lang_folder="english-dub"), "VOE"
    )
    assert row["status"] == "queued"
    assert db.get_queue_item(row["queue_id"])["language"] == "English Dub"


def test_an_undetectable_language_is_skipped_rather_than_guessed(downloads):
    """Guessing could pull a whole series in a language you never watch."""
    (downloads / "Naruto").mkdir()
    row = autosync._handle(candidate(downloads / "Naruto", {"German Dub"}), "VOE")
    assert row["status"] == "skipped"
    assert row["reason"].startswith("Could not detect")


def test_a_new_episode_in_the_wrong_language_is_skipped(downloads):
    folder = downloads / "german-dub" / "Naruto"
    folder.mkdir(parents=True)
    row = autosync._handle(
        candidate(folder, {"English Dub"}, lang_folder="german-dub"), "VOE"
    )
    assert row["status"] == "skipped"
    assert "This copy is in German Dub" in row["reason"]
    assert "only out in English Dub" in row["reason"]


def test_a_series_with_nothing_missing_is_up_to_date(monkeypatch, downloads):
    folder = downloads / "german-dub" / "Naruto"
    folder.mkdir(parents=True)
    monkeypatch.setattr(autosync, "_missing_episodes", lambda series, have: [])
    monkeypatch.setattr(
        autosync, "resolve_provider", lambda url: _FakeProvider("Naruto")
    )

    row = autosync._handle(
        candidate(folder, {"German Dub"}, lang_folder="german-dub"), "VOE"
    )
    assert row["status"] == "up-to-date"
    assert db.get_queue() == []


def test_missing_episodes_are_queued(monkeypatch, downloads):
    folder = downloads / "german-dub" / "Naruto"
    folder.mkdir(parents=True)
    monkeypatch.setattr(
        autosync,
        "_missing_episodes",
        lambda series, have: ["https://x/ep5", "https://x/ep6"],
    )
    monkeypatch.setattr(
        autosync, "resolve_provider", lambda url: _FakeProvider("Naruto Shippuden")
    )

    row = autosync._handle(
        candidate(folder, {"German Dub"}, lang_folder="german-dub"), "Vidoza"
    )
    assert row["status"] == "queued"
    assert row["episodes"] == 2

    item = db.get_queue_item(row["queue_id"])
    assert item["title"] == "Naruto Shippuden"
    assert item["provider"] == "Vidoza"
    assert item["language"] == "German Dub"
    assert item["source"] == "autosync"


def test_a_queued_sync_lands_in_the_custom_path_it_came_from(monkeypatch, tmp_path):
    other = tmp_path / "other"
    folder = other / "german-dub" / "Naruto"
    folder.mkdir(parents=True)
    path_id = db.add_custom_path("Other", str(other))
    monkeypatch.setattr(
        autosync, "_missing_episodes", lambda series, have: ["https://x/ep5"]
    )
    monkeypatch.setattr(
        autosync, "resolve_provider", lambda url: _FakeProvider("Naruto")
    )

    row = autosync._handle(
        candidate(folder, {"German Dub"}, path_id=path_id, lang_folder="german-dub"),
        "VOE",
    )
    assert db.get_queue_item(row["queue_id"])["custom_path_id"] == path_id


def test_the_preferred_language_is_picked_when_several_match(monkeypatch, downloads):
    folder = downloads / "german-dub" / "Naruto"
    folder.mkdir(parents=True)
    monkeypatch.setattr(
        autosync, "_missing_episodes", lambda series, have: ["https://x/ep5"]
    )
    monkeypatch.setattr(
        autosync, "resolve_provider", lambda url: _FakeProvider("Naruto")
    )

    row = autosync._handle(
        candidate(folder, {"German Dub", "English Sub"}, lang_folder="german-dub"),
        "VOE",
    )
    assert row["language"] == "German Dub"


# ---------------------------------------------------------------------------
# Only the new episodes
#
# The default fills every gap in a series, which is wrong for people who skip
# episodes on purpose. With the setting on, only what the feed announced and is
# not on disk gets queued.
# ---------------------------------------------------------------------------
EP = "https://aniworld.to/anime/stream/naruto/staffel-1/episode-"


@pytest.fixture
def new_only(monkeypatch):
    monkeypatch.setenv("ANIWORLD_AUTOSYNC_NEW_ONLY", "1")


@pytest.fixture
def german_folder(monkeypatch, downloads):
    """A Naruto folder that reads as German Dub, with the series page faked out."""
    folder = downloads / "german-dub" / "Naruto"
    folder.mkdir(parents=True)
    monkeypatch.setattr(
        autosync, "resolve_provider", lambda url: _FakeProvider("Naruto")
    )
    return folder


def _on_disk(monkeypatch, *pairs):
    """What this one copy already holds. Scoped per folder, not per library."""
    monkeypatch.setattr(autosync, "episodes_in_folder", lambda folder: set(pairs))


def test_parsing_the_numbers_out_of_an_episode_url():
    assert autosync._numbers(f"{EP}12") == (1, 12)
    assert (
        autosync._numbers("https://aniworld.to/anime/stream/naruto/filme/film-2")
        is None
    )


def test_only_the_announced_episode_is_queued(monkeypatch, new_only, german_folder):
    _on_disk(monkeypatch)
    row = autosync._handle(
        candidate(
            german_folder,
            {"German Dub"},
            lang_folder="german-dub",
            new_urls=[f"{EP}12"],
        ),
        "VOE",
    )
    assert row["status"] == "queued"
    queued = json.loads(db.get_queue_item(row["queue_id"])["episodes"])
    assert queued == [f"{EP}12"]


def test_the_gaps_are_left_alone(monkeypatch, new_only, german_folder):
    """Episodes 2 to 11 are missing on purpose and must stay missing."""
    _on_disk(monkeypatch, (1, 1))
    row = autosync._handle(
        candidate(
            german_folder,
            {"German Dub"},
            lang_folder="german-dub",
            new_urls=[f"{EP}12"],
        ),
        "VOE",
    )
    assert row["episodes"] == 1


def test_all_announced_episodes_are_queued(monkeypatch, new_only, german_folder):
    _on_disk(monkeypatch)
    row = autosync._handle(
        candidate(
            german_folder,
            {"German Dub"},
            lang_folder="german-dub",
            new_urls=[f"{EP}12", f"{EP}13"],
        ),
        "VOE",
    )
    assert row["episodes"] == 2


def test_an_announced_episode_already_on_disk_is_not_requeued(
    monkeypatch, new_only, german_folder
):
    _on_disk(monkeypatch, (1, 12))
    row = autosync._handle(
        candidate(
            german_folder,
            {"German Dub"},
            lang_folder="german-dub",
            new_urls=[f"{EP}12"],
        ),
        "VOE",
    )
    assert row["status"] == "up-to-date"
    assert db.get_queue() == []


def test_new_only_never_walks_the_series_page(monkeypatch, new_only, german_folder):
    """The whole point of reading the numbers off the URL: no extra requests."""
    _on_disk(monkeypatch)

    def explode(series):
        raise AssertionError("_missing_episodes must not run in new-only mode")

    monkeypatch.setattr(autosync, "_missing_episodes", explode)
    row = autosync._handle(
        candidate(
            german_folder,
            {"German Dub"},
            lang_folder="german-dub",
            new_urls=[f"{EP}12"],
        ),
        "VOE",
    )
    assert row["status"] == "queued"


def test_the_setting_off_still_fills_the_series(monkeypatch, german_folder):
    """Default behaviour is untouched."""
    monkeypatch.setattr(
        autosync,
        "_missing_episodes",
        lambda series, have: [f"{EP}2", f"{EP}3", f"{EP}12"],
    )
    row = autosync._handle(
        candidate(
            german_folder,
            {"German Dub"},
            lang_folder="german-dub",
            new_urls=[f"{EP}12"],
        ),
        "VOE",
    )
    assert row["episodes"] == 3


def test_a_whole_cycle_in_new_only_mode(feed, monkeypatch, new_only, downloads):
    """Feed to queue, with find_candidates and _handle joined up."""
    monkeypatch.setenv("ANIWORLD_LANG_SEPARATION", "1")
    (downloads / "german-dub" / "Naruto").mkdir(parents=True)
    monkeypatch.setattr(
        autosync, "resolve_provider", lambda url: _FakeProvider("Naruto")
    )
    _on_disk(monkeypatch, (1, 1))
    feed([entry("Naruto", "naruto", episode=12), entry("Naruto", "naruto", episode=13)])

    report = autosync.run_cycle()
    assert report["queued"] == 1

    queued = json.loads(db.get_queue()[0]["episodes"])
    assert queued == [f"{EP}12", f"{EP}13"], "only the two that just came out"


def test_new_only_is_off_by_default():
    from aniworld.web.settings_store import autosync_new_only, read_settings

    assert autosync_new_only() is False
    assert read_settings()["autosync_new_only"] is False


def test_the_setting_shows_up_in_the_status(monkeypatch):
    assert autosync.status()["new_only"] is False
    monkeypatch.setenv("ANIWORLD_AUTOSYNC_NEW_ONLY", "1")
    assert autosync.status()["new_only"] is True


class _FakeSeries:
    def __init__(self, title):
        self.title = title
        self.title_cleaned = title
        self.seasons = []


class _FakeProvider:
    def __init__(self, title):
        self._title = title

    def series_cls(self, url):
        return _FakeSeries(self._title)


# ---------------------------------------------------------------------------
# Language preference order
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "labels,expected",
    [
        ({"German Dub", "German Sub"}, "German Dub"),
        ({"German Sub", "English Dub"}, "German Sub"),
        ({"English Sub", "English Dub"}, "English Dub"),
        ({"English Sub"}, "English Sub"),
    ],
)
def test_language_preference(labels, expected):
    assert autosync._preferred(labels) == expected


def test_a_language_folder_names_its_own_language(downloads):
    assert autosync.detect_languages(downloads, "german-sub") == {"German Sub"}


def test_an_unknown_language_folder_falls_through_to_probing(downloads):
    assert autosync.detect_languages(downloads, "klingon-dub") == set()


# ---------------------------------------------------------------------------
# When it runs
#
# The schedule itself is tested in test_schedule.py, this is about what
# Auto-Sync does with it.
# ---------------------------------------------------------------------------
def _ran(hours_ago):
    db.set_autosync_state(
        last_run=(datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    )


def test_an_install_that_never_ran_is_due_right_away():
    """The behaviour from before the schedule was configurable."""
    assert autosync._due() is True


def test_the_default_interval_is_a_day():
    _ran(hours_ago=2)
    assert autosync._due() is False
    _ran(hours_ago=25)
    assert autosync._due() is True


def test_the_interval_can_be_shortened(monkeypatch):
    monkeypatch.setenv("ANIWORLD_AUTOSYNC_INTERVAL", "90m")
    _ran(hours_ago=2)
    assert autosync._due() is True


def test_the_interval_can_be_lengthened(monkeypatch):
    monkeypatch.setenv("ANIWORLD_AUTOSYNC_INTERVAL", "7d")
    _ran(hours_ago=48)
    assert autosync._due() is False


def test_a_broken_interval_falls_back_to_a_day(monkeypatch):
    """A hand-edited .env must not take the worker down with it."""
    monkeypatch.setenv("ANIWORLD_AUTOSYNC_INTERVAL", "whenever")
    _ran(hours_ago=2)
    assert autosync._due() is False
    _ran(hours_ago=25)
    assert autosync._due() is True


@pytest.fixture
def fixed_times(monkeypatch):
    """Switch Auto-Sync over to a cron schedule."""

    def use(expression):
        monkeypatch.setenv("ANIWORLD_AUTOSYNC_MODE", "cron")
        monkeypatch.setenv("ANIWORLD_AUTOSYNC_CRON", expression)

    return use


def test_a_fixed_time_is_read_as_local_time(fixed_times):
    """A cron line means 22:00 on the wall, whatever the machine's timezone."""
    fixed_times("0 22 * * *")
    _ran(hours_ago=2)
    upcoming = autosync._local(autosync.next_run_at())
    assert (upcoming.hour, upcoming.minute) == (22, 0)


def test_the_next_fixed_time_follows_the_last_run(fixed_times):
    fixed_times("every day at 08:00, 22:30")
    _ran(hours_ago=2)
    upcoming = autosync._local(autosync.next_run_at())
    assert (upcoming.hour, upcoming.minute) in {(8, 0), (22, 30)}


def test_a_fixed_time_does_not_fire_the_moment_it_is_turned_on(fixed_times):
    """Counted from now, so enabling it never sets a download going at once."""
    fixed_times("* * * * *")
    assert autosync._due() is False
    assert autosync.next_run_at() > autosync._now()


def test_a_missed_fixed_time_is_caught_up_on(fixed_times):
    """The machine was off at 22:00, so it runs as soon as it is back."""
    fixed_times("0 22 * * *")
    _ran(hours_ago=24 * 7)
    assert autosync._due() is True


def test_a_last_run_without_a_timezone_does_not_stall_the_worker():
    """One of these in the database raised on every tick, and Auto-Sync then
    never ran again: the error was caught and logged, so nothing said why."""
    db.set_autosync_state(last_run="2026-01-01T00:00:00")
    assert autosync._due() is True, "a year ago, so it is due"
    assert autosync.next_run_at() is not None


def test_switching_it_on_is_what_starts_the_clock(monkeypatch, fixed_times):
    """The worker keeps the anchor fresh while Auto-Sync is off.

    Without that, a server up since Monday would count Friday's switch-on from
    Monday, find a fixed time long past, and queue downloads on the spot.
    """
    fixed_times("0 3 * * *")
    monkeypatch.setattr(
        autosync, "_anchored_at", datetime.now(timezone.utc) - timedelta(days=4)
    )
    assert autosync._due() is True, "the stale anchor is what causes it"

    autosync._reset_anchor()
    assert autosync._due() is False
    assert autosync._local(autosync.next_run_at()).hour == 3


def test_a_last_run_from_a_wrong_clock_is_ignored():
    """A box whose clock was years ahead once would otherwise never run again."""
    db.set_autosync_state(
        last_run=(datetime.now(timezone.utc) + timedelta(days=900)).isoformat()
    )
    assert autosync._due() is True, "back to a fresh install, not parked in 2028"


def test_a_run_a_minute_ahead_is_left_alone():
    """Clocks drift, and a cycle stamps its start before it stamps anything."""
    db.set_autosync_state(
        last_run=(datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
    )
    assert autosync._due() is False


def test_a_broken_cron_line_falls_back_to_the_default(fixed_times):
    fixed_times("every blursday at half past nonsense")
    assert autosync.status()["cron"] == "0 3 * * *"


def test_the_nap_never_outlasts_a_tick(monkeypatch, fixed_times):
    """However far off the next run is, settings changes still get picked up."""
    monkeypatch.setenv("ANIWORLD_ENABLE_AUTOSYNC", "1")
    fixed_times("0 4 1 1 *")
    assert autosync._nap_seconds() == autosync.TICK_SECONDS


def test_the_nap_shrinks_to_hit_a_fixed_time(monkeypatch, fixed_times):
    """A five minute tick would otherwise make 22:00 mean "22:00 give or take"."""
    monkeypatch.setenv("ANIWORLD_ENABLE_AUTOSYNC", "1")
    fixed_times("* * * * *")
    assert autosync.MIN_TICK_SECONDS <= autosync._nap_seconds() <= 60


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def test_status_of_a_fresh_install():
    report = autosync.status()
    assert report["running"] is False
    assert report["last_run"] is None


def test_status_reports_the_last_run():
    db.set_autosync_state(
        last_run="2026-01-01T00:00:00+00:00", last_report='{"queued": 2}'
    )
    report = autosync.status()
    assert report["last_run"] == "2026-01-01T00:00:00+00:00"
    assert report["last_report"]["queued"] == 2


def test_status_describes_an_interval_schedule(monkeypatch):
    monkeypatch.setenv("ANIWORLD_AUTOSYNC_INTERVAL", "6h")
    report = autosync.status()
    assert report["mode"] == "interval"
    assert report["interval"] == "6h"
    assert report["interval_seconds"] == 6 * 3600
    assert report["interval_hours"] == 6
    assert report["cron"] is None
    assert report["schedule"] == "Every 6 hours"


def test_a_sub_hour_interval_is_still_reported_in_hours(monkeypatch):
    """It used to floor to 0, which read as "no interval at all"."""
    monkeypatch.setenv("ANIWORLD_AUTOSYNC_INTERVAL", "90m")
    assert autosync.status()["interval_hours"] == 1.5


def test_status_describes_fixed_times(monkeypatch):
    monkeypatch.setenv("ANIWORLD_AUTOSYNC_MODE", "cron")
    monkeypatch.setenv("ANIWORLD_AUTOSYNC_CRON", "every monday and friday at 10pm")
    report = autosync.status()
    assert report["mode"] == "cron"
    assert report["cron"] == "0 22 * * 1,5"
    assert report["schedule"] == "On Monday and Friday at 22:00"


def test_status_describes_the_schedule_in_the_ui_language(monkeypatch):
    monkeypatch.setenv("ANIWORLD_UI_LANGUAGE", "de")
    monkeypatch.setenv("ANIWORLD_AUTOSYNC_MODE", "cron")
    monkeypatch.setenv("ANIWORLD_AUTOSYNC_CRON", "0 22 * * 1")
    assert autosync.status()["schedule"] == "Jeden Montag um 22:00"


def test_a_full_cycle_with_nothing_to_do(feed, downloads):
    feed([])
    report = autosync.run_cycle()
    assert report["checked"] == 0
    assert report["queued"] == 0
    assert db.get_autosync_state()["last_run"]


def test_a_cycle_records_a_failed_fetch(feed):
    feed(None)
    report = autosync.run_cycle()
    assert "error" in report
    assert report["queued"] == 0


def test_a_cycle_queues_what_it_finds(feed, monkeypatch, downloads):
    (downloads / "german-dub" / "Naruto").mkdir(parents=True)
    monkeypatch.setenv("ANIWORLD_LANG_SEPARATION", "1")
    monkeypatch.setattr(
        autosync, "_missing_episodes", lambda series, have: ["https://x/ep5"]
    )
    monkeypatch.setattr(
        autosync, "resolve_provider", lambda url: _FakeProvider("Naruto")
    )
    feed([entry("Naruto", "naruto")])

    report = autosync.run_cycle()
    assert report["checked"] == 1
    assert report["queued"] == 1
    assert len(db.get_queue()) == 1


def test_one_broken_candidate_does_not_sink_the_cycle(feed, monkeypatch, downloads):
    (downloads / "german-dub" / "Naruto").mkdir(parents=True)
    monkeypatch.setenv("ANIWORLD_LANG_SEPARATION", "1")

    def explode(url):
        raise RuntimeError("series page is down")

    monkeypatch.setattr(autosync, "resolve_provider", explode)
    feed([entry("Naruto", "naruto")])

    report = autosync.run_cycle()
    assert report["results"][0]["status"] == "error"
    assert "series page is down" in report["results"][0]["reason"]


# ---------------------------------------------------------------------------
# The same show held more than once
#
# Two languages side by side, or the same title in two libraries. Each copy is
# its own download, so each has to be looked at on its own.
# ---------------------------------------------------------------------------
def test_every_copy_of_a_series_becomes_its_own_candidate(feed, downloads, monkeypatch):
    monkeypatch.setenv("ANIWORLD_LANG_SEPARATION", "1")
    (downloads / "german-dub" / "Naruto").mkdir(parents=True)
    (downloads / "english-sub" / "Naruto").mkdir(parents=True)
    feed([entry("Naruto", "naruto", languages=("german", "japanese-english"))])

    candidates = autosync.find_candidates()
    assert len(candidates) == 2, "one per copy, not one per series"
    assert {c["lang_folder"] for c in candidates} == {"german-dub", "english-sub"}


def test_a_copy_in_a_second_library_is_its_own_candidate(feed, downloads, tmp_path):
    other = tmp_path / "second-library"
    other.mkdir()
    db.add_custom_path("Second", str(other))
    (downloads / "Naruto").mkdir()
    (other / "Naruto").mkdir()
    feed([entry("Naruto", "naruto")])

    candidates = autosync.find_candidates()
    assert len(candidates) == 2
    assert {c["root_name"] for c in candidates} == {"Default", "Second"}
    assert {c["custom_path_id"] for c in candidates} != {None}, (
        "one carries the path id"
    )


def test_a_report_row_says_which_copy_it_is_about(downloads):
    folder = downloads / "german-dub" / "Naruto"
    folder.mkdir(parents=True)
    row = autosync._handle(
        candidate(folder, {"English Dub"}, lang_folder="german-dub"), "VOE"
    )
    assert row["where"] == "Default / german-dub"


# ---------------------------------------------------------------------------
# What one copy already holds
# ---------------------------------------------------------------------------
def test_only_this_copy_counts_as_downloaded(downloads):
    """The other copy having the episode must not mark this one complete."""
    german = downloads / "german-dub" / "Naruto"
    english = downloads / "english-dub" / "Naruto"
    german.mkdir(parents=True)
    english.mkdir(parents=True)
    (german / "Naruto S01E05.mkv").write_bytes(b"x")

    assert autosync.episodes_in_folder(german) == {(1, 5)}
    assert autosync.episodes_in_folder(english) == set(), "counted per copy"


def test_the_second_copy_still_gets_the_episode(monkeypatch, downloads, feed):
    """The bug this replaced: one copy having it hid it from every other copy."""
    monkeypatch.setenv("ANIWORLD_LANG_SEPARATION", "1")
    german = downloads / "german-dub" / "Naruto"
    english = downloads / "english-dub" / "Naruto"
    german.mkdir(parents=True)
    english.mkdir(parents=True)
    (german / "Naruto S01E05.mkv").write_bytes(b"x")

    monkeypatch.setattr(
        autosync, "resolve_provider", lambda url: _FakeProvider("Naruto")
    )
    monkeypatch.setenv("ANIWORLD_AUTOSYNC_NEW_ONLY", "1")
    urls = [f"{EP}5"]

    german_row = autosync._handle(
        candidate(german, {"German Dub"}, lang_folder="german-dub", new_urls=urls),
        "VOE",
    )
    english_row = autosync._handle(
        candidate(english, {"English Dub"}, lang_folder="english-dub", new_urls=urls),
        "VOE",
    )

    assert german_row["status"] == "up-to-date", "this copy already has episode 5"
    assert english_row["status"] == "queued", "this one does not, and must still get it"
    assert db.get_queue_item(english_row["queue_id"])["language"] == "English Dub"


def test_a_skip_reason_names_both_languages(downloads):
    folder = downloads / "german-dub" / "Naruto"
    folder.mkdir(parents=True)
    row = autosync._handle(
        candidate(folder, {"English Sub"}, lang_folder="german-dub"), "VOE"
    )
    assert row["reason"] == (
        "This copy is in German Dub, and the new episode is only out in English Sub."
    )


def test_every_reason_reads_as_a_sentence(downloads):
    """They are printed verbatim on the page, so they start with a capital."""
    folder = downloads / "german-dub" / "Naruto"
    folder.mkdir(parents=True)
    reasons = [
        autosync._handle(candidate(downloads / "Nope", {"German Dub"}), "VOE")[
            "reason"
        ],
        autosync._handle(
            candidate(folder, {"English Dub"}, lang_folder="german-dub"), "VOE"
        )["reason"],
    ]
    for reason in reasons:
        assert reason[0].isupper(), reason
        assert reason.endswith("."), reason


# ---------------------------------------------------------------------------
# The mixed-language warning on the page
# ---------------------------------------------------------------------------
def test_the_mixed_language_notice_is_shown_without_separation(client, monkeypatch):
    """One file decides a whole title's language, so mixing them silently breaks."""
    monkeypatch.setenv("ANIWORLD_ENABLE_AUTOSYNC", "1")
    body = client.get("/autosync").get_data(as_text=True)
    assert "autosync.mixed_languages" in body
    assert "autosync.turn_on_separation" in body


def test_the_notice_disappears_once_separation_is_on(client, monkeypatch):
    monkeypatch.setenv("ANIWORLD_ENABLE_AUTOSYNC", "1")
    monkeypatch.setenv("ANIWORLD_LANG_SEPARATION", "1")
    body = client.get("/autosync").get_data(as_text=True)
    assert "autosync.mixed_languages" not in body
