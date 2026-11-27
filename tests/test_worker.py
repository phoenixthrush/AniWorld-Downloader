"""The download worker, driven with a stand-in episode.

No provider is ever contacted. `_build_episode` is replaced by a fake whose
download() does exactly what each test needs: succeed, fail, or notice a
cancel halfway through.
"""

import json

import pytest

from aniworld.web import db, worker


class FakeEpisode:
    """Stands in for a real episode. Records what it was asked to download."""

    def __init__(self, url, behaviour=None, on_download=None):
        self.url = url
        self.behaviour = behaviour
        self.on_download = on_download

    def download(self):
        if self.on_download:
            self.on_download(self.url)
        if isinstance(self.behaviour, Exception):
            raise self.behaviour


class FakeProvider:
    name = "VOE"


class Calls(list):
    """What the worker did, plus the status _process ended the item with."""

    status = None


@pytest.fixture
def run_worker(monkeypatch):
    """Process one queue item with a scripted episode downloader."""
    calls = Calls()

    def factory(queue_id, behaviour=None, on_download=None):
        def build(url, extra, item, selected_path):
            calls.append({"url": url, "extra": extra, "selected_path": selected_path})
            wanted = behaviour(url) if callable(behaviour) else behaviour
            return FakeProvider(), FakeEpisode(url, wanted, on_download)

        monkeypatch.setattr(worker, "_build_episode", build)
        monkeypatch.setattr(
            worker, "_notify_discord", lambda item: calls.append("discord")
        )
        calls.status = worker._process(db.get_queue_item(queue_id))
        return calls

    return factory


# ---------------------------------------------------------------------------
# Normalising queued entries
# ---------------------------------------------------------------------------
def test_a_plain_url_entry():
    url, extra = worker._episode_request("https://x/ep1")
    assert url == "https://x/ep1"
    assert "selected_pages" not in extra


def test_a_dict_entry_keeps_its_extras():
    url, extra = worker._episode_request(
        {
            "url": "  https://mangafire.to/title/z9w-velvet-kisss/chapter/1  ",
            "selected_pages": [1, 2],
            "series_url": "https://mangafire.to/title/z9w-velvet-kisss",
            "mangafire_format": "epub",
        }
    )
    assert url == "https://mangafire.to/title/z9w-velvet-kisss/chapter/1", (
        "surrounding whitespace is trimmed"
    )
    assert extra["selected_pages"] == [1, 2]
    assert extra["_series_url"] == "https://mangafire.to/title/z9w-velvet-kisss"
    assert extra["_format"] == "epub"


def test_a_missing_format_falls_back_to_the_setting(monkeypatch):
    monkeypatch.setenv("ANIWORLD_MANGAFIRE_FORMAT", "png")
    _, extra = worker._episode_request({"url": "https://x/ep1"})
    assert extra["_format"] == "png"


def test_a_plain_mangafire_url_gets_the_configured_format(monkeypatch):
    """A bare URL string carries no extras, MangaFire still needs a format."""
    monkeypatch.setenv("ANIWORLD_MANGAFIRE_FORMAT", "png")
    built = {}

    class Provider:
        name = "MangaFire"

        @staticmethod
        def series_cls(url):
            return None

        @staticmethod
        def episode_cls(**kwargs):
            built.update(kwargs)

    monkeypatch.setattr(worker, "resolve_provider", lambda url: Provider)
    url, extra = worker._episode_request(
        "https://mangafire.to/title/z9w-velvet-kisss/chapter/1"
    )
    worker._build_episode(
        url, extra, {"language": "German Dub", "provider": "VOE"}, None
    )
    assert built["format"] == "png"


def test_page_zero_is_still_passed_along():
    _, extra = worker._episode_request({"url": "x", "selected_pages": []})
    assert extra["selected_pages"] == []


# ---------------------------------------------------------------------------
# A download that works
# ---------------------------------------------------------------------------
def test_one_episode_completes(queue_item, run_worker):
    queue_id = queue_item(episodes=["https://x/ep1"])
    db.set_queue_status(queue_id, "running")
    calls = run_worker(queue_id)

    assert [c["url"] for c in calls] == ["https://x/ep1"]
    item = db.get_queue_item(queue_id)
    assert item["status"] == "completed"
    assert item["current_episode"] == 1
    assert item["errors"] == "[]"


def test_every_episode_is_downloaded_in_order(queue_item, run_worker):
    urls = [f"https://x/ep{n}" for n in range(1, 6)]
    queue_id = queue_item(episodes=urls)
    db.set_queue_status(queue_id, "running")
    calls = run_worker(queue_id)

    assert [c["url"] for c in calls] == urls
    assert db.get_queue_item(queue_id)["current_episode"] == 5


def test_progress_is_visible_while_it_runs(queue_item, run_worker):
    seen = []
    queue_id = queue_item(episodes=["https://x/ep1", "https://x/ep2"])
    db.set_queue_status(queue_id, "running")

    def watch(url):
        item = db.get_queue_item(queue_id)
        seen.append((item["current_episode"], item["current_url"]))

    run_worker(queue_id, on_download=watch)
    assert seen == [(0, "https://x/ep1"), (1, "https://x/ep2")]


def test_a_finished_download_is_not_cancelled(queue_item, run_worker):
    queue_id = queue_item(episodes=["https://x/ep1"])
    db.set_queue_status(queue_id, "running")
    run_worker(queue_id)
    assert db.cancel_flags(queue_id) == (False, False)


# ---------------------------------------------------------------------------
# Failures
# ---------------------------------------------------------------------------
def test_a_failing_episode_is_recorded(queue_item, run_worker):
    queue_id = queue_item(episodes=["https://x/ep1"])
    db.set_queue_status(queue_id, "running")
    run_worker(queue_id, behaviour=RuntimeError("no provider worked"))

    item = db.get_queue_item(queue_id)
    assert item["status"] == "failed"
    errors = json.loads(item["errors"])
    assert errors[0]["url"] == "https://x/ep1"
    assert "no provider worked" in errors[0]["error"]


def test_one_bad_episode_does_not_stop_the_rest(queue_item, run_worker):
    queue_id = queue_item(episodes=["https://x/ep1", "https://x/ep2", "https://x/ep3"])
    db.set_queue_status(queue_id, "running")
    calls = run_worker(
        queue_id,
        behaviour=lambda url: RuntimeError("boom") if url.endswith("ep2") else None,
    )

    assert len(calls) == 3, "the third episode still gets its turn"
    item = db.get_queue_item(queue_id)
    assert item["status"] == "completed", "a partial success is not a failure"
    assert len(json.loads(item["errors"])) == 1


def test_only_an_all_round_failure_marks_the_item_failed(queue_item, run_worker):
    queue_id = queue_item(episodes=["https://x/ep1", "https://x/ep2"])
    db.set_queue_status(queue_id, "running")
    run_worker(queue_id, behaviour=RuntimeError("boom"))

    item = db.get_queue_item(queue_id)
    assert item["status"] == "failed"
    assert len(json.loads(item["errors"])) == 2


def test_a_failed_item_can_be_retried_and_then_works(queue_item, run_worker):
    queue_id = queue_item(episodes=["https://x/ep1"])
    db.set_queue_status(queue_id, "running")
    run_worker(queue_id, behaviour=RuntimeError("boom"))
    assert db.get_queue_item(queue_id)["status"] == "failed"

    assert db.requeue_item(queue_id) is True
    db.set_queue_status(queue_id, "running")
    run_worker(queue_id)

    item = db.get_queue_item(queue_id)
    assert item["status"] == "completed"
    assert item["errors"] == "[]", "the old error is gone"


# ---------------------------------------------------------------------------
# Cancelling
# ---------------------------------------------------------------------------
def test_a_cancel_lets_the_current_episode_finish(queue_item, run_worker):
    queue_id = queue_item(episodes=["https://x/ep1", "https://x/ep2", "https://x/ep3"])
    db.set_queue_status(queue_id, "running")

    def cancel_during_first(url):
        if url.endswith("ep1"):
            db.cancel_queue_item(queue_id)

    calls = run_worker(queue_id, on_download=cancel_during_first)

    assert [c["url"] for c in calls] == ["https://x/ep1"], "it stops after this one"
    item = db.get_queue_item(queue_id)
    assert item["status"] == "cancelled"
    assert item["current_episode"] == 1, "the finished episode counts"


def test_a_force_cancel_does_not_count_the_broken_episode(queue_item, run_worker):
    queue_id = queue_item(episodes=["https://x/ep1", "https://x/ep2"])
    db.set_queue_status(queue_id, "running")

    def force_during_first(url):
        db.cancel_queue_item(queue_id, force=True)
        raise RuntimeError("ffmpeg killed")

    run_worker(queue_id, on_download=force_during_first)

    item = db.get_queue_item(queue_id)
    assert item["status"] == "cancelled"
    assert item["current_episode"] == 0, "the half written episode does not count"


def test_a_force_cancel_records_no_error(queue_item, run_worker):
    """Killing ffmpeg on purpose is not a failure worth showing the user."""
    queue_id = queue_item(episodes=["https://x/ep1"])
    db.set_queue_status(queue_id, "running")

    def force(url):
        db.cancel_queue_item(queue_id, force=True)
        raise RuntimeError("ffmpeg error (rc=-9): ...huge stderr dump...")

    run_worker(queue_id, on_download=force)
    assert db.get_queue_item(queue_id)["errors"] == "[]"


def test_cancelling_after_the_last_episode_still_counts_as_done(queue_item, run_worker):
    """Asking to stop once everything is on disk should not say 'cancelled'."""
    queue_id = queue_item(episodes=["https://x/ep1"])
    db.set_queue_status(queue_id, "running")

    def cancel_at_the_end(url):
        db.cancel_queue_item(queue_id)

    run_worker(queue_id, on_download=cancel_at_the_end)
    assert db.get_queue_item(queue_id)["status"] == "completed"


def test_a_cancel_after_a_failure_stays_cancelled(queue_item, run_worker):
    queue_id = queue_item(episodes=["https://x/ep1"])
    db.set_queue_status(queue_id, "running")

    def fail_and_cancel(url):
        db.cancel_queue_item(queue_id)
        raise RuntimeError("boom")

    run_worker(queue_id, on_download=fail_and_cancel)
    assert db.get_queue_item(queue_id)["status"] == "cancelled"


# ---------------------------------------------------------------------------
# Settings reaching the downloader
# ---------------------------------------------------------------------------
def test_no_target_path_is_passed_by_default(queue_item, run_worker):
    queue_id = queue_item(episodes=["https://x/ep1"])
    db.set_queue_status(queue_id, "running")
    calls = run_worker(queue_id)
    assert calls[0]["selected_path"] is None


def test_language_separation_reaches_the_downloader(
    queue_item, run_worker, monkeypatch, downloads
):
    monkeypatch.setenv("ANIWORLD_LANG_SEPARATION", "1")
    queue_id = queue_item(episodes=["https://x/ep1"], language="German Sub")
    db.set_queue_status(queue_id, "running")
    calls = run_worker(queue_id)
    assert calls[0]["selected_path"] == str(downloads / "german-sub")


def test_a_custom_path_reaches_the_downloader(queue_item, run_worker, tmp_path):
    path_id = db.add_custom_path("Movies", str(tmp_path / "movies"))
    queue_id = queue_item(episodes=["https://x/ep1"], custom_path_id=path_id)
    db.set_queue_status(queue_id, "running")
    calls = run_worker(queue_id)
    assert calls[0]["selected_path"] == str(tmp_path / "movies")


def test_the_path_is_resolved_when_the_download_starts_not_when_queued(
    queue_item, run_worker, monkeypatch, downloads
):
    """A setting changed while the item waited in the queue still applies."""
    queue_id = queue_item(episodes=["https://x/ep1"])
    monkeypatch.setenv("ANIWORLD_LANG_SEPARATION", "1")
    db.set_queue_status(queue_id, "running")
    calls = run_worker(queue_id)
    assert calls[0]["selected_path"] == str(downloads / "german-dub")


def test_a_custom_path_deleted_while_queued_falls_back(
    queue_item, run_worker, tmp_path, downloads
):
    path_id = db.add_custom_path("Movies", str(tmp_path / "movies"))
    queue_id = queue_item(episodes=["https://x/ep1"], custom_path_id=path_id)
    db.remove_custom_path(path_id)

    db.set_queue_status(queue_id, "running")
    calls = run_worker(queue_id)
    assert calls[0]["selected_path"] == str(downloads)


# ---------------------------------------------------------------------------
# Discord notifications
# ---------------------------------------------------------------------------
def test_a_discord_request_is_announced_when_it_finishes(queue_item, run_worker):
    queue_id = queue_item(episodes=["https://x/ep1"], source="discord")
    db.set_queue_status(queue_id, "running")
    assert "discord" in run_worker(queue_id)


def test_a_manual_download_is_not_announced(queue_item, run_worker):
    queue_id = queue_item(episodes=["https://x/ep1"])
    db.set_queue_status(queue_id, "running")
    assert "discord" not in run_worker(queue_id)


def test_a_failed_discord_request_is_not_announced(queue_item, run_worker):
    queue_id = queue_item(episodes=["https://x/ep1"], source="discord")
    db.set_queue_status(queue_id, "running")
    assert "discord" not in run_worker(queue_id, behaviour=RuntimeError("boom"))


def test_a_cancelled_discord_request_is_not_announced(queue_item, run_worker):
    queue_id = queue_item(episodes=["https://x/ep1", "https://x/ep2"], source="discord")
    db.set_queue_status(queue_id, "running")

    def cancel(url):
        db.cancel_queue_item(queue_id)

    assert "discord" not in run_worker(queue_id, on_download=cancel)


# ---------------------------------------------------------------------------
# Claiming work
# ---------------------------------------------------------------------------
def test_the_next_item_is_claimed_and_marked_running(queue_item):
    queue_id = queue_item()
    claimed = worker._claim_next()
    assert claimed["id"] == queue_id
    assert db.get_queue_item(queue_id)["status"] == "running"


def test_only_one_download_runs_at_a_time(queue_item):
    queue_item("A")
    queue_item("B")
    assert worker._claim_next() is not None
    assert worker._claim_next() is None, "the second item waits its turn"


def test_the_next_item_is_claimed_once_the_first_finishes(queue_item):
    first = queue_item("A")
    second = queue_item("B")
    worker._claim_next()
    db.set_queue_status(first, "completed")
    assert worker._claim_next()["id"] == second


def test_an_empty_queue_claims_nothing():
    assert worker._claim_next() is None


def test_a_cancelled_item_is_never_claimed(queue_item):
    queue_id = queue_item()
    db.cancel_queue_item(queue_id)
    assert worker._claim_next() is None


def test_the_queue_order_decides_what_runs_next(queue_item):
    first = queue_item("A")
    second = queue_item("B")
    db.move_queue_item(second, "up")
    assert worker._claim_next()["id"] == second
    assert first is not None


# ---------------------------------------------------------------------------
# The webhook once the queue runs dry
# ---------------------------------------------------------------------------
@pytest.fixture
def webhook_calls(monkeypatch):
    """Record each call with how many items had finished."""
    calls = []
    monkeypatch.setattr(worker.webhook, "queue_finished", calls.append)
    return calls


def test_process_reports_a_completed_item(queue_item, run_worker):
    queue_id = queue_item(episodes=["https://x/ep1"])
    db.set_queue_status(queue_id, "running")
    assert run_worker(queue_id).status == "completed"


def test_process_reports_a_failed_item(queue_item, run_worker):
    queue_id = queue_item(episodes=["https://x/ep1"])
    db.set_queue_status(queue_id, "running")
    assert run_worker(queue_id, behaviour=RuntimeError("boom")).status == "failed"


def test_process_reports_a_cancelled_item(queue_item, run_worker):
    queue_id = queue_item(episodes=["https://x/ep1", "https://x/ep2"])
    db.set_queue_status(queue_id, "running")
    calls = run_worker(queue_id, on_download=lambda url: db.cancel_queue_item(queue_id))
    assert calls.status == "cancelled"


def test_process_reports_a_cancel_after_the_last_episode_as_completed(
    queue_item, run_worker
):
    queue_id = queue_item(episodes=["https://x/ep1"])
    db.set_queue_status(queue_id, "running")
    calls = run_worker(queue_id, on_download=lambda url: db.cancel_queue_item(queue_id))
    assert calls.status == "completed"


def test_the_webhook_fires_when_the_last_item_completes(webhook_calls):
    assert worker._after_item("completed", 0) == 0, "the count starts over"
    assert webhook_calls == [1]


def test_the_webhook_waits_while_items_are_still_queued(queue_item, webhook_calls):
    queue_item("Next")
    assert worker._after_item("completed", 0) == 1
    assert webhook_calls == []


def test_the_webhook_waits_while_an_item_is_running(queue_item, webhook_calls):
    db.set_queue_status(queue_item("Running"), "running")
    assert worker._after_item(None, 1) == 1
    assert webhook_calls == []


def test_the_webhook_counts_every_item_of_the_batch(webhook_calls):
    worker._after_item("completed", 2)
    assert webhook_calls == [3]


@pytest.mark.parametrize("status", ["failed", "cancelled", None])
def test_a_queue_of_nothing_finished_sends_nothing(webhook_calls, status):
    assert worker._after_item(status, 0) == 0
    assert webhook_calls == []


@pytest.mark.parametrize("status", ["failed", "cancelled", None])
def test_a_bad_last_item_still_reports_the_ones_before(webhook_calls, status):
    """Something new is on disk, so a library scan is still worth it."""
    assert worker._after_item(status, 2) == 0
    assert webhook_calls == [2]


def test_a_database_error_keeps_the_count_and_the_worker(monkeypatch, webhook_calls):
    def broken():
        raise RuntimeError("database is locked")

    monkeypatch.setattr(db, "get_next_queued", broken)
    assert worker._after_item("completed", 0) == 1, "tried again after the next item"
    assert webhook_calls == []


def test_a_webhook_that_cannot_connect_does_not_reach_the_worker(monkeypatch):
    def refused(*args, **kwargs):
        raise ConnectionError("connection refused")

    monkeypatch.setenv("ANIWORLD_WEBHOOK_URL", "http://jellyfin:8096/Library/Refresh")
    monkeypatch.setattr(worker.webhook.niquests, "request", refused)
    assert worker._after_item("completed", 0) == 0


class Idle(BaseException):
    """Raised by the patched sleep to leave the worker's endless loop.

    A BaseException, so the loop's own `except Exception` lets it through.
    """


@pytest.fixture
def run_loop(monkeypatch):
    """Run the real worker loop until the queue is empty, then stop it."""

    def sleep(seconds):
        if db.get_next_queued() is None:
            raise Idle

    def factory(behaviour=None):
        def build(url, extra, item, selected_path):
            wanted = behaviour(url) if callable(behaviour) else behaviour
            return FakeProvider(), FakeEpisode(url, wanted)

        monkeypatch.setattr(worker, "_build_episode", build)
        monkeypatch.setattr(worker.time, "sleep", sleep)
        with pytest.raises(Idle):
            worker._run()

    return factory


def test_the_loop_calls_the_webhook_once_for_the_whole_queue(
    queue_item, run_loop, webhook_calls
):
    queue_item("A", episodes=["https://x/a1"])
    queue_item("B", episodes=["https://x/b1"])
    queue_item("C", episodes=["https://x/c1"])
    run_loop()

    assert webhook_calls == [3]
    assert {item["status"] for item in db.get_queue()} == {"completed"}


def test_the_loop_reports_completed_items_after_the_last_waiting_item_is_cancelled(
    queue_item, run_loop, webhook_calls, monkeypatch
):
    completed = queue_item("First", episodes=["https://x/ep1"])
    waiting = queue_item("Second", episodes=["https://x/ep2"])
    claim_next = worker._claim_next

    def cancel_then_claim():
        if db.get_queue_item(completed)["status"] == "completed":
            assert db.cancel_queue_item(waiting) == (True, None)
        return claim_next()

    monkeypatch.setattr(worker, "_claim_next", cancel_then_claim)
    run_loop()

    assert db.get_queue_item(waiting)["status"] == "cancelled"
    assert webhook_calls == [1]


def test_the_loop_leaves_out_failed_items_from_the_count(
    queue_item, run_loop, webhook_calls
):
    queue_item("A", episodes=["https://x/a1"])
    queue_item("B", episodes=["https://x/b1"])
    run_loop(behaviour=lambda url: RuntimeError("boom") if "a1" in url else None)
    assert webhook_calls == [1]


def test_the_loop_sends_nothing_when_everything_failed(
    queue_item, run_loop, webhook_calls
):
    queue_item("A", episodes=["https://x/a1"])
    run_loop(behaviour=RuntimeError("boom"))
    assert webhook_calls == []


def test_the_loop_survives_a_crashing_item(
    queue_item, run_loop, webhook_calls, monkeypatch
):
    """An error outside the episode download still lets the batch report."""
    crashing = queue_item("A", episodes=["https://x/a1"])
    queue_item("B", episodes=["https://x/b1"])
    process = worker._process

    def crash_on_a(item):
        if item["id"] == crashing:
            raise RuntimeError("unexpected")
        return process(item)

    monkeypatch.setattr(worker, "_process", crash_on_a)
    run_loop()

    assert db.get_queue_item(crashing)["status"] == "failed"
    assert webhook_calls == [1]
