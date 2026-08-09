"""The queue and download HTTP endpoints."""

import json

import pytest

from aniworld.web import db


@pytest.fixture(autouse=True)
def no_worker(monkeypatch):
    """Queueing must not start a real download thread."""
    from aniworld.web import worker

    monkeypatch.setattr(worker, "ensure_started", lambda: None)


def episodes_of(queue_id):
    return json.loads(db.get_queue_item(queue_id)["episodes"])


# ---------------------------------------------------------------------------
# Starting a download
# ---------------------------------------------------------------------------
def test_a_download_lands_in_the_queue(client):
    response = client.post(
        "/api/download",
        json={
            "title": "Naruto",
            "series_url": "https://aniworld.to/anime/stream/naruto",
            "episodes": ["https://x/ep1", "https://x/ep2"],
            "language": "German Sub",
            "provider": "Vidoza",
        },
    )
    assert response.status_code == 200
    item = db.get_queue_item(response.get_json()["queue_id"])
    assert item["title"] == "Naruto"
    assert item["total_episodes"] == 2
    assert item["language"] == "German Sub"
    assert item["provider"] == "Vidoza"


def test_defaults_are_filled_in(client):
    queue_id = client.post("/api/download", json={"episodes": ["x"]}).get_json()[
        "queue_id"
    ]
    item = db.get_queue_item(queue_id)
    assert item["title"] == "Unknown"
    assert item["language"] == "German Dub"
    assert item["provider"] == "VOE"
    assert item["source"] == "manual"


def test_an_empty_episode_list_is_refused(client):
    response = client.post("/api/download", json={"episodes": []})
    assert response.status_code == 400
    assert "episodes" in response.get_json()["error"]
    assert db.get_queue() == []


def test_a_body_without_episodes_is_refused(client):
    assert client.post("/api/download", json={"title": "x"}).status_code == 400


def test_english_sub_is_refused_when_disabled(client, monkeypatch):
    monkeypatch.setenv("ANIWORLD_DISABLE_ENGLISH_SUB", "1")
    response = client.post(
        "/api/download", json={"episodes": ["x"], "language": "English Sub"}
    )
    assert response.status_code == 403
    assert db.get_queue() == []


def test_other_languages_still_work_when_english_sub_is_disabled(client, monkeypatch):
    monkeypatch.setenv("ANIWORLD_DISABLE_ENGLISH_SUB", "1")
    response = client.post(
        "/api/download", json={"episodes": ["x"], "language": "German Dub"}
    )
    assert response.status_code == 200


def test_english_sub_works_again_once_re_enabled(client, monkeypatch):
    monkeypatch.setenv("ANIWORLD_DISABLE_ENGLISH_SUB", "1")
    assert (
        client.post(
            "/api/download", json={"episodes": ["x"], "language": "English Sub"}
        ).status_code
        == 403
    )

    monkeypatch.setenv("ANIWORLD_DISABLE_ENGLISH_SUB", "0")
    assert (
        client.post(
            "/api/download", json={"episodes": ["x"], "language": "English Sub"}
        ).status_code
        == 200
    )


def test_a_custom_path_is_remembered(client, tmp_path):
    path_id = db.add_custom_path("Movies", str(tmp_path))
    queue_id = client.post(
        "/api/download", json={"episodes": ["x"], "custom_path_id": path_id}
    ).get_json()["queue_id"]
    assert db.get_queue_item(queue_id)["custom_path_id"] == path_id


def test_mangafire_chapters_carry_the_output_format(client):
    queue_id = client.post(
        "/api/download",
        json={
            "episodes": ["https://mangafire.to/read/x/chapter/1"],
            "provider": "MangaFire",
            "mangafire_format": "pdf",
        },
    ).get_json()["queue_id"]
    assert episodes_of(queue_id)[0]["mangafire_format"] == "pdf"


def test_mangafire_falls_back_to_the_configured_format(client, monkeypatch):
    monkeypatch.setenv("MANGAFIRE_FORMAT", "png")
    queue_id = client.post(
        "/api/download",
        json={"episodes": [{"url": "https://x/chapter/1"}], "provider": "MangaFire"},
    ).get_json()["queue_id"]
    assert episodes_of(queue_id)[0]["mangafire_format"] == "png"


def test_other_providers_are_not_tagged(client):
    queue_id = client.post(
        "/api/download", json={"episodes": ["https://x/ep1"], "provider": "VOE"}
    ).get_json()["queue_id"]
    assert episodes_of(queue_id) == ["https://x/ep1"]


def test_form_encoded_writes_are_blocked(client):
    """Otherwise a cross-origin form could post without a CSRF token."""
    response = client.post("/api/download", data={"episodes": "x"})
    assert response.status_code == 415


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------
def test_the_queue_comes_back_with_progress(client, queue_item):
    queue_item("Naruto")
    body = client.get("/api/queue").get_json()
    assert [item["title"] for item in body["items"]] == ["Naruto"]
    assert "ffmpeg_progress" in body


def test_progress_carries_the_numbers_the_queue_shows(client, queue_item):
    """The percentage and the speed under the bar come straight from here."""
    from aniworld.models.common import common

    queue_item("Naruto")
    with common._ffmpeg_progress_lock:
        common._ffmpeg_progress.update(
            percent=42.5, bandwidth="11.7 MB/s", speed="2.4x", active=True
        )
    try:
        progress = client.get("/api/queue").get_json()["ffmpeg_progress"]
    finally:
        with common._ffmpeg_progress_lock:
            common._ffmpeg_progress.update(
                percent=0.0, bandwidth="", speed="", active=False
            )

    assert progress["percent"] == 42.5
    assert progress["bandwidth"] == "11.7 MB/s"
    assert progress["speed"] == "2.4x"
    assert progress["active"] is True


def test_an_empty_queue_is_an_empty_list(client):
    assert client.get("/api/queue").get_json()["items"] == []


def test_the_duration_is_included(client, queue_item):
    queue_item()
    assert "duration_seconds" in client.get("/api/queue").get_json()["items"][0]


def test_api_responses_are_not_cached(client):
    response = client.get("/api/queue")
    assert "no-store" in response.headers["Cache-Control"]


# ---------------------------------------------------------------------------
# Acting on items
# ---------------------------------------------------------------------------
def test_cancel(client, queue_item):
    queue_id = queue_item()
    assert client.post(f"/api/queue/{queue_id}/cancel").status_code == 200
    assert db.get_queue_item(queue_id)["status"] == "cancelled"


def test_cancel_of_a_running_item_only_asks(client, queue_item):
    queue_id = queue_item()
    db.set_queue_status(queue_id, "running")
    client.post(f"/api/queue/{queue_id}/cancel")
    assert db.get_queue_item(queue_id)["status"] == "running"
    assert db.cancel_flags(queue_id) == (True, False)


def test_force_cancel_stops_a_running_item(client, queue_item):
    queue_id = queue_item()
    db.set_queue_status(queue_id, "running")
    assert client.post(f"/api/queue/{queue_id}/force-cancel").status_code == 200
    assert db.get_queue_item(queue_id)["status"] == "cancelled"
    assert db.cancel_flags(queue_id) == (True, True)


def test_cancelling_a_finished_item_is_a_client_error(client, queue_item):
    queue_id = queue_item()
    db.set_queue_status(queue_id, "completed")
    assert client.post(f"/api/queue/{queue_id}/cancel").status_code == 400


def test_cancelling_a_missing_item_is_a_client_error(client):
    assert client.post("/api/queue/4242/cancel").status_code == 400


def test_remove(client, queue_item):
    queue_id = queue_item()
    assert client.delete(f"/api/queue/{queue_id}").status_code == 200
    assert db.get_queue_item(queue_id) is None


def test_removing_a_running_item_is_refused(client, queue_item):
    queue_id = queue_item()
    db.set_queue_status(queue_id, "running")
    assert client.delete(f"/api/queue/{queue_id}").status_code == 400


def test_retry(client, queue_item):
    queue_id = queue_item()
    db.set_queue_status(queue_id, "failed")
    assert client.post(f"/api/queue/{queue_id}/retry").status_code == 200
    assert db.get_queue_item(queue_id)["status"] == "queued"


def test_retrying_something_that_did_not_fail_is_refused(client, queue_item):
    queue_id = queue_item()
    response = client.post(f"/api/queue/{queue_id}/retry")
    assert response.status_code == 400
    assert "retryable" in response.get_json()["error"]


@pytest.mark.parametrize("direction", ["up", "down"])
def test_move(client, queue_item, direction):
    first, second = queue_item("A"), queue_item("B")
    target = second if direction == "up" else first
    assert (
        client.post(
            f"/api/queue/{target}/move", json={"direction": direction}
        ).status_code
        == 200
    )
    assert [i["title"] for i in db.get_queue()] == ["B", "A"]


def test_moving_without_a_direction_is_refused(client, queue_item):
    assert client.post(f"/api/queue/{queue_item()}/move", json={}).status_code == 400


def test_clear_completed(client, queue_item):
    keep = queue_item("keep")
    done = queue_item("done")
    db.set_queue_status(done, "completed")
    assert client.delete("/api/queue/completed").status_code == 200
    assert [i["id"] for i in db.get_queue()] == [keep]


# ---------------------------------------------------------------------------
# Captcha endpoints
# ---------------------------------------------------------------------------
def test_no_captcha_session_means_inactive(client, queue_item):
    body = client.get(f"/api/captcha/{queue_item()}/status").get_json()
    assert body == {"active": False}


def test_a_screenshot_without_a_session_is_a_404(client, queue_item):
    assert client.get(f"/api/captcha/{queue_item()}/screenshot").status_code == 404


def test_clicking_without_a_session_is_a_404(client, queue_item):
    response = client.post(f"/api/captcha/{queue_item()}/click", json={"x": 1, "y": 2})
    assert response.status_code == 404


def test_a_click_needs_coordinates(client, queue_item):
    response = client.post(f"/api/captcha/{queue_item()}/click", json={"x": 1})
    assert response.status_code == 400
