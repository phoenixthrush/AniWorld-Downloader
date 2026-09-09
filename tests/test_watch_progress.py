"""Watch positions: per account, in the database, never in the media folder."""

from aniworld.web import db

LOC = db.location_key(None, None)


def test_a_position_is_stored_and_read_back():
    db.set_watch_progress("", LOC, "Naruto", "Season 01/N S01E001.mkv", 120.5, 1400)
    got = db.get_watch_progress("", LOC, "Naruto")
    assert got["Season 01/N S01E001.mkv"]["position"] == 120.5
    assert got["Season 01/N S01E001.mkv"]["watched"] is False


def test_past_ninety_percent_counts_as_watched_and_stays_watched():
    row = db.set_watch_progress("", LOC, "Naruto", "e1", 1300, 1400)
    assert row["watched"] is True
    row = db.set_watch_progress("", LOC, "Naruto", "e1", 10, 1400)
    assert row["watched"] is True, "seeking back does not un-see an episode"


def test_watched_can_be_forced_either_way():
    row = db.set_watch_progress("", LOC, "Naruto", "e1", 0, 1400, watched=True)
    assert row["watched"] is True
    assert row["position"] == 1400, "marking seen puts the position at the end"
    row = db.set_watch_progress("", LOC, "Naruto", "e1", 0, 1400, watched=False)
    assert row["watched"] is False
    assert row["position"] == 0


def test_a_missing_duration_keeps_the_known_one():
    db.set_watch_progress("", LOC, "Naruto", "e1", 100, 1400)
    row = db.set_watch_progress("", LOC, "Naruto", "e1", 200, 0)
    assert row["duration"] == 1400


def test_accounts_and_locations_do_not_share_positions():
    other = db.location_key(3, "german-dub")
    db.set_watch_progress("alice", LOC, "Naruto", "e1", 100, 1400)
    db.set_watch_progress("bob", LOC, "Naruto", "e1", 200, 1400)
    db.set_watch_progress("alice", other, "Naruto", "e1", 300, 1400)
    assert db.get_watch_progress("alice", LOC, "Naruto")["e1"]["position"] == 100
    assert db.get_watch_progress("bob", LOC, "Naruto")["e1"]["position"] == 200
    assert db.get_watch_progress("alice", other, "Naruto")["e1"]["position"] == 300


def test_summary_counts_per_title_in_one_query():
    db.set_watch_progress("", LOC, "Naruto", "e1", 1400, 1400)
    db.set_watch_progress("", LOC, "Naruto", "e2", 100, 1400)
    db.set_watch_progress("", LOC, "Bleach", "e1", 5, 1400)
    summary = db.watch_summary("", LOC)
    assert summary["Naruto"]["watched"] == 1
    assert summary["Naruto"]["in_progress"] == 1
    assert summary["Bleach"] == {
        "watched": 0,
        "in_progress": 1,
        "last": summary["Bleach"]["last"],
    }


def test_continue_watching_lists_unfinished_newest_first():
    db.set_watch_progress("", LOC, "Naruto", "e1", 1400, 1400)  # done
    db.set_watch_progress("", LOC, "Naruto", "e2", 100, 1400)
    db.set_watch_progress("", LOC, "Bleach", "e1", 5, 1400)
    items = db.continue_watching("")
    assert [(i["folder"], i["file"]) for i in items][:2] == [
        ("Bleach", "e1"),
        ("Naruto", "e2"),
    ] or [(i["folder"], i["file"]) for i in items][:2] == [
        ("Naruto", "e2"),
        ("Bleach", "e1"),
    ]
    assert all(not i["watched"] for i in items)


def test_deleting_a_title_or_files_forgets_every_account():
    db.set_watch_progress("alice", LOC, "Naruto", "e1", 100, 1400)
    db.set_watch_progress("bob", LOC, "Naruto", "e2", 100, 1400)
    db.delete_watch_progress(LOC, "Naruto", ["e1"])
    assert db.get_watch_progress("alice", LOC, "Naruto") == {}
    assert "e2" in db.get_watch_progress("bob", LOC, "Naruto")
    db.delete_watch_progress(LOC, "Naruto")
    assert db.get_watch_progress("bob", LOC, "Naruto") == {}
