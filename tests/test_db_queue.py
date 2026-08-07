"""Download queue storage: ordering, state changes, cancelling and retrying."""

import json
import time

import pytest

from aniworld.web import db


# ---------------------------------------------------------------------------
# Adding
# ---------------------------------------------------------------------------
def test_add_stores_every_field(queue_item):
    queue_id = queue_item(
        "Naruto",
        episodes=["a", "b", "c"],
        language="German Sub",
        provider="Vidoza",
        username="bob",
        source="discord",
        discord_user_id="42",
    )
    item = db.get_queue_item(queue_id)
    assert item["title"] == "Naruto"
    assert item["total_episodes"] == 3
    assert json.loads(item["episodes"]) == ["a", "b", "c"]
    assert item["language"] == "German Sub"
    assert item["provider"] == "Vidoza"
    assert item["username"] == "bob"
    assert item["source"] == "discord"
    assert item["discord_user_id"] == "42"


def test_new_item_starts_queued(queue_item):
    item = db.get_queue_item(queue_item())
    assert item["status"] == "queued"
    assert item["current_episode"] == 0
    assert item["started_at"] is None
    assert item["completed_at"] is None
    assert item["errors"] == "[]"
    assert item["cancel_requested"] == 0
    assert item["force_cancelled"] == 0


def test_episodes_can_be_dicts(queue_item):
    entries = [{"url": "https://x/ep1", "selected_pages": [1, 2]}]
    item = db.get_queue_item(queue_item(episodes=entries))
    assert json.loads(item["episodes"]) == entries


def test_position_defaults_to_insertion_order(queue_item):
    first, second, third = queue_item("A"), queue_item("B"), queue_item("C")
    order = [item["id"] for item in db.get_queue()]
    assert order == [first, second, third]


def test_unknown_item_is_none():
    assert db.get_queue_item(999) is None


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("status", db.QUEUE_STATUSES)
def test_every_documented_status_is_accepted(queue_item, status):
    queue_id = queue_item()
    db.set_queue_status(queue_id, status)
    assert db.get_queue_item(queue_id)["status"] == status


def test_invalid_status_is_rejected(queue_item):
    with pytest.raises(ValueError):
        db.set_queue_status(queue_item(), "exploded")


def test_running_stamps_the_start_time(queue_item):
    queue_id = queue_item()
    db.set_queue_status(queue_id, "running")
    item = db.get_queue_item(queue_id)
    assert item["started_at"] is not None
    assert item["completed_at"] is None


@pytest.mark.parametrize("status", ("completed", "failed", "cancelled"))
def test_finishing_stamps_the_end_time(queue_item, status):
    queue_id = queue_item()
    db.set_queue_status(queue_id, "running")
    db.set_queue_status(queue_id, status)
    assert db.get_queue_item(queue_id)["completed_at"] is not None


def test_finishing_keeps_the_start_time(queue_item):
    queue_id = queue_item()
    db.set_queue_status(queue_id, "running")
    started = db.get_queue_item(queue_id)["started_at"]
    db.set_queue_status(queue_id, "completed")
    assert db.get_queue_item(queue_id)["started_at"] == started


def test_progress_updates(queue_item):
    queue_id = queue_item(episodes=["a", "b"])
    db.update_queue_progress(queue_id, 1, "https://x/ep2")
    item = db.get_queue_item(queue_id)
    assert item["current_episode"] == 1
    assert item["current_url"] == "https://x/ep2"


def test_errors_round_trip(queue_item):
    queue_id = queue_item()
    failures = [{"url": "https://x/ep1", "error": "boom"}]
    db.update_queue_errors(queue_id, failures)
    assert json.loads(db.get_queue_item(queue_id)["errors"]) == failures


# ---------------------------------------------------------------------------
# Duration
# ---------------------------------------------------------------------------
def _duration_of(queue_id):
    return next(i["duration_seconds"] for i in db.get_queue() if i["id"] == queue_id)


def test_duration_is_none_before_it_starts(queue_item):
    assert _duration_of(queue_item()) is None


def test_duration_counts_up_while_running(queue_item):
    queue_id = queue_item()
    db.set_queue_status(queue_id, "running")
    assert _duration_of(queue_id) >= 0


def test_duration_freezes_when_finished(queue_item):
    queue_id = queue_item()
    with db.session() as conn:
        conn.execute(
            "UPDATE download_queue SET started_at = datetime('now', '-90 seconds'), "
            "completed_at = datetime('now', '-30 seconds'), status = 'completed' "
            "WHERE id = ?",
            (queue_id,),
        )
    assert _duration_of(queue_id) == 60
    time.sleep(1.1)
    assert _duration_of(queue_id) == 60


def test_duration_ignores_queue_waiting_time(queue_item):
    queue_id = queue_item()
    with db.session() as conn:
        conn.execute(
            "UPDATE download_queue SET created_at = datetime('now', '-1 hour'), "
            "started_at = datetime('now', '-10 seconds') WHERE id = ?",
            (queue_id,),
        )
    assert _duration_of(queue_id) < 60


def test_duration_never_goes_negative(queue_item):
    """A clock jump backwards must not produce a negative number."""
    queue_id = queue_item()
    with db.session() as conn:
        conn.execute(
            "UPDATE download_queue SET started_at = datetime('now', '+10 seconds'), "
            "completed_at = datetime('now') WHERE id = ?",
            (queue_id,),
        )
    assert _duration_of(queue_id) == 0


# ---------------------------------------------------------------------------
# Picking up work
# ---------------------------------------------------------------------------
def test_next_queued_follows_position(queue_item):
    first, second = queue_item("A"), queue_item("B")
    assert db.get_next_queued()["id"] == first
    db.set_queue_status(first, "completed")
    assert db.get_next_queued()["id"] == second


def test_next_queued_is_none_when_empty():
    assert db.get_next_queued() is None


def test_finished_items_are_never_picked_up(queue_item):
    for status in ("completed", "failed", "cancelled", "running"):
        db.set_queue_status(queue_item(status), status)
    assert db.get_next_queued() is None


def test_running_lookup(queue_item):
    assert db.get_running() is None
    queue_id = queue_item()
    db.set_queue_status(queue_id, "running")
    assert db.get_running()["id"] == queue_id


def test_series_already_in_the_queue_is_detected(queue_item):
    url = "https://aniworld.to/anime/stream/one-piece"
    assert not db.is_series_queued_or_running(url)
    queue_id = queue_item(series_url=url)
    assert db.is_series_queued_or_running(url)
    db.set_queue_status(queue_id, "running")
    assert db.is_series_queued_or_running(url)
    db.set_queue_status(queue_id, "completed")
    assert not db.is_series_queued_or_running(url)


# ---------------------------------------------------------------------------
# Cancelling
# ---------------------------------------------------------------------------
def test_cancelling_a_queued_item_stops_it_immediately(queue_item):
    queue_id = queue_item()
    ok, error = db.cancel_queue_item(queue_id)
    assert (ok, error) == (True, None)
    item = db.get_queue_item(queue_id)
    assert item["status"] == "cancelled"
    assert item["completed_at"] is not None


def test_cancelling_a_running_item_lets_it_finish_the_episode(queue_item):
    queue_id = queue_item()
    db.set_queue_status(queue_id, "running")
    assert db.cancel_queue_item(queue_id) == (True, None)

    item = db.get_queue_item(queue_id)
    assert item["status"] == "running", "the episode being written must finish first"
    assert item["cancel_requested"] == 1
    assert item["force_cancelled"] == 0


def test_force_cancelling_a_running_item_stops_it_now(queue_item):
    queue_id = queue_item()
    db.set_queue_status(queue_id, "running")
    assert db.cancel_queue_item(queue_id, force=True) == (True, None)

    item = db.get_queue_item(queue_id)
    assert item["status"] == "cancelled"
    assert item["force_cancelled"] == 1
    assert db.is_queue_force_cancelled(queue_id)


def test_second_cancel_escalates_to_force(queue_item):
    """The UI sends a plain cancel first and force on the second press."""
    queue_id = queue_item()
    db.set_queue_status(queue_id, "running")
    db.cancel_queue_item(queue_id)
    assert db.cancel_flags(queue_id) == (True, False)

    db.cancel_queue_item(queue_id, force=True)
    assert db.cancel_flags(queue_id) == (True, True)


@pytest.mark.parametrize("status", ("completed", "failed", "cancelled"))
def test_finished_items_cannot_be_cancelled(queue_item, status):
    queue_id = queue_item()
    db.set_queue_status(queue_id, status)
    ok, error = db.cancel_queue_item(queue_id)
    assert not ok
    assert "queued or running" in error


def test_cancelling_a_missing_item_reports_it():
    ok, error = db.cancel_queue_item(4242)
    assert not ok
    assert error == "Item not found"


def test_flags_of_a_missing_item_are_false():
    assert db.cancel_flags(4242) == (False, False)
    assert db.is_queue_force_cancelled(4242) is False


def test_cancelling_one_item_leaves_the_others_alone(queue_item):
    first, second = queue_item("A"), queue_item("B")
    db.cancel_queue_item(first)
    assert db.get_queue_item(second)["status"] == "queued"
    assert db.cancel_flags(second) == (False, False)


# ---------------------------------------------------------------------------
# Retrying
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("status", ("failed", "cancelled"))
def test_retry_resets_everything(queue_item, status):
    queue_id = queue_item()
    db.set_queue_status(queue_id, "running")
    db.update_queue_progress(queue_id, 3, "https://x/ep4")
    db.update_queue_errors(queue_id, [{"error": "boom"}])
    db.set_captcha_url(queue_id, "https://kinox.to/captcha")
    db.cancel_queue_item(queue_id, force=True)
    db.set_queue_status(queue_id, status)

    assert db.requeue_item(queue_id) is True
    item = db.get_queue_item(queue_id)
    assert item["status"] == "queued"
    assert item["current_episode"] == 0
    assert item["current_url"] is None
    assert item["errors"] == "[]"
    assert item["started_at"] is None
    assert item["completed_at"] is None
    assert item["cancel_requested"] == 0
    assert item["force_cancelled"] == 0
    assert item["captcha_url"] is None


@pytest.mark.parametrize("status", ("queued", "running", "completed"))
def test_only_failed_or_cancelled_can_be_retried(queue_item, status):
    queue_id = queue_item()
    db.set_queue_status(queue_id, status)
    assert db.requeue_item(queue_id) is False


def test_retrying_a_missing_item_is_false():
    assert db.requeue_item(4242) is False


def test_retried_item_is_picked_up_again(queue_item):
    queue_id = queue_item()
    db.set_queue_status(queue_id, "failed")
    assert db.get_next_queued() is None
    db.requeue_item(queue_id)
    assert db.get_next_queued()["id"] == queue_id


# ---------------------------------------------------------------------------
# Removing and clearing
# ---------------------------------------------------------------------------
def test_remove_deletes_the_row(queue_item):
    queue_id = queue_item()
    assert db.remove_from_queue(queue_id) == (True, None)
    assert db.get_queue_item(queue_id) is None


def test_a_running_item_must_be_cancelled_before_removal(queue_item):
    queue_id = queue_item()
    db.set_queue_status(queue_id, "running")
    ok, error = db.remove_from_queue(queue_id)
    assert not ok
    assert "Cancel" in error
    assert db.get_queue_item(queue_id) is not None


def test_removing_a_missing_item_reports_it():
    assert db.remove_from_queue(4242) == (False, "Item not found")


def test_clear_completed_keeps_active_work(queue_item):
    keep_queued = queue_item("queued")
    keep_running = queue_item("running")
    db.set_queue_status(keep_running, "running")
    for status in ("completed", "failed", "cancelled"):
        db.set_queue_status(queue_item(status), status)

    db.clear_completed()
    assert {i["id"] for i in db.get_queue()} == {keep_queued, keep_running}


# ---------------------------------------------------------------------------
# Reordering
# ---------------------------------------------------------------------------
def _order():
    return [item["title"] for item in db.get_queue()]


def test_move_up(queue_item):
    queue_item("A"), queue_item("B"), queue_item("C")
    second = db.get_queue()[1]["id"]
    assert db.move_queue_item(second, "up") == (True, None)
    assert _order() == ["B", "A", "C"]


def test_move_down(queue_item):
    queue_item("A"), queue_item("B"), queue_item("C")
    first = db.get_queue()[0]["id"]
    assert db.move_queue_item(first, "down") == (True, None)
    assert _order() == ["B", "A", "C"]


def test_move_is_reversible(queue_item):
    queue_item("A"), queue_item("B")
    first = db.get_queue()[0]["id"]
    db.move_queue_item(first, "down")
    db.move_queue_item(first, "up")
    assert _order() == ["A", "B"]


def test_cannot_move_past_the_edges(queue_item):
    first, last = queue_item("A"), queue_item("B")
    assert db.move_queue_item(first, "up")[0] is False
    assert db.move_queue_item(last, "down")[0] is False
    assert _order() == ["A", "B"]


def test_only_queued_items_can_be_moved(queue_item):
    queue_item("A")
    running = queue_item("B")
    db.set_queue_status(running, "running")
    ok, error = db.move_queue_item(running, "up")
    assert not ok
    assert "queued" in error


def test_move_skips_over_finished_items(queue_item):
    """Finished rows sit in the list but must not be swapped with."""
    queue_item("A")
    done = queue_item("done")
    db.set_queue_status(done, "completed")
    last = queue_item("C")
    db.move_queue_item(last, "up")
    assert _order() == ["C", "done", "A"]


def test_move_needs_a_real_direction(queue_item):
    ok, error = db.move_queue_item(queue_item(), "sideways")
    assert not ok
    assert "up" in error


def test_moving_a_missing_item_reports_it():
    assert db.move_queue_item(4242, "up") == (False, "Item not found")


# ---------------------------------------------------------------------------
# Crash recovery
# ---------------------------------------------------------------------------
def test_stale_running_items_are_requeued(queue_item):
    queue_id = queue_item()
    db.set_queue_status(queue_id, "running")
    db.set_captcha_url(queue_id, "https://kinox.to/captcha")
    db.cancel_queue_item(queue_id)

    db.reset_stale_running()
    item = db.get_queue_item(queue_id)
    assert item["status"] == "queued"
    assert item["started_at"] is None
    assert item["cancel_requested"] == 0
    assert item["force_cancelled"] == 0
    assert item["captcha_url"] is None


def test_recovery_leaves_finished_work_alone(queue_item):
    done = queue_item()
    db.set_queue_status(done, "completed")
    db.reset_stale_running()
    assert db.get_queue_item(done)["status"] == "completed"


def test_captcha_url_round_trip(queue_item):
    queue_id = queue_item()
    db.set_captcha_url(queue_id, "https://kinox.to/captcha")
    assert db.get_queue_item(queue_id)["captcha_url"] == "https://kinox.to/captcha"
    db.clear_captcha_url(queue_id)
    assert db.get_queue_item(queue_id)["captcha_url"] is None
