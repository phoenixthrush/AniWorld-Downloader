"""AutoSync matching and its exclusion list.

aniworld.to is never contacted: the "newest episodes" feed is replaced with a
fixed list and series objects are stand-ins.
"""

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
def candidate(folder, languages, path_id=None, lang_folder=None):
    return {
        "title": "Naruto",
        "series_url": "https://aniworld.to/anime/stream/naruto",
        "folder": folder,
        "custom_path_id": path_id,
        "lang_folder": lang_folder,
        "new_languages": set(languages),
    }


def test_a_series_already_in_the_queue_is_skipped(downloads, queue_item):
    queue_item(series_url="https://aniworld.to/anime/stream/naruto")
    row = autosync._handle(candidate(downloads, {"German Dub"}), "VOE")
    assert row["status"] == "skipped"
    assert "already in the queue" in row["reason"]


def test_an_undetectable_language_is_skipped_rather_than_guessed(downloads):
    """Guessing could pull a whole series in a language you never watch."""
    (downloads / "Naruto").mkdir()
    row = autosync._handle(candidate(downloads / "Naruto", {"German Dub"}), "VOE")
    assert row["status"] == "skipped"
    assert "could not detect" in row["reason"]


def test_a_new_episode_in_the_wrong_language_is_skipped(downloads):
    folder = downloads / "german-dub" / "Naruto"
    folder.mkdir(parents=True)
    row = autosync._handle(
        candidate(folder, {"English Dub"}, lang_folder="german-dub"), "VOE"
    )
    assert row["status"] == "skipped"
    assert "not out in German Dub" in row["reason"]


def test_a_series_with_nothing_missing_is_up_to_date(monkeypatch, downloads):
    folder = downloads / "german-dub" / "Naruto"
    folder.mkdir(parents=True)
    monkeypatch.setattr(autosync, "_missing_episodes", lambda series: [])
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
        autosync, "_missing_episodes", lambda series: ["https://x/ep5", "https://x/ep6"]
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
    monkeypatch.setattr(autosync, "_missing_episodes", lambda series: ["https://x/ep5"])
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
    monkeypatch.setattr(autosync, "_missing_episodes", lambda series: ["https://x/ep5"])
    monkeypatch.setattr(
        autosync, "resolve_provider", lambda url: _FakeProvider("Naruto")
    )

    row = autosync._handle(
        candidate(folder, {"German Dub", "English Sub"}, lang_folder="german-dub"),
        "VOE",
    )
    assert row["language"] == "German Dub"


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
    monkeypatch.setattr(autosync, "_missing_episodes", lambda series: ["https://x/ep5"])
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
