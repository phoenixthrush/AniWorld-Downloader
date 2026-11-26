"""The webhook sent when the download queue runs dry.

The HTTP request is never sent for real. niquests.request is replaced by a
recorder that answers with whatever status the test asks for.
"""

import logging

import niquests
import pytest

from aniworld.web import webhook


class FakeResponse:
    def __init__(self, status_code=204, reason="No Content", text=""):
        self.status_code = status_code
        self.reason = reason
        self.text = text


class Sent(list):
    """The requests made so far. `answer` is what the next one gets back."""

    def __init__(self):
        super().__init__()
        self.answer = {"response": FakeResponse()}


@pytest.fixture
def sent(monkeypatch):
    """Record every request instead of sending it."""
    calls = Sent()

    def fake_request(method, url, **kwargs):
        calls.append({"method": method, "url": url, **kwargs})
        result = calls.answer["response"]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(webhook.niquests, "request", fake_request)
    return calls


@pytest.fixture
def log(monkeypatch, caplog):
    """The app logger does not propagate, so swap in one caplog can see."""
    monkeypatch.setattr(webhook, "logger", logging.getLogger("test_webhook"))
    caplog.set_level(logging.INFO, logger="test_webhook")
    return caplog


JELLYFIN = "http://jellyfin:8096/Library/Refresh"


# ---------------------------------------------------------------------------
# Off unless configured
# ---------------------------------------------------------------------------
def test_nothing_is_sent_without_a_url(sent):
    webhook.queue_finished(1)
    assert sent == []


def test_a_blank_url_counts_as_off(sent, monkeypatch):
    monkeypatch.setenv("ANIWORLD_WEBHOOK_URL", "   ")
    webhook.queue_finished(1)
    assert sent == []


# ---------------------------------------------------------------------------
# The request itself
# ---------------------------------------------------------------------------
def test_the_default_is_a_plain_post(sent, monkeypatch):
    monkeypatch.setenv("ANIWORLD_WEBHOOK_URL", JELLYFIN)
    webhook.queue_finished(1)

    assert len(sent) == 1
    call = sent[0]
    assert call["method"] == "POST"
    assert call["url"] == JELLYFIN
    assert call["headers"] == {}
    assert call["data"] is None
    assert call["timeout"] == webhook.TIMEOUT_SECONDS


def test_the_jellyfin_header_keeps_its_quotes(sent, monkeypatch):
    monkeypatch.setenv("ANIWORLD_WEBHOOK_URL", JELLYFIN)
    monkeypatch.setenv(
        "ANIWORLD_WEBHOOK_HEADERS", 'Authorization: MediaBrowser Token="abc123"'
    )
    webhook.queue_finished(1)
    assert sent[0]["headers"] == {"Authorization": 'MediaBrowser Token="abc123"'}


def test_several_headers_are_split_on_the_bar(sent, monkeypatch):
    monkeypatch.setenv("ANIWORLD_WEBHOOK_URL", "https://ntfy.sh/topic")
    monkeypatch.setenv(
        "ANIWORLD_WEBHOOK_HEADERS", " Title: Downloads done | Tags: tv,anime |"
    )
    webhook.queue_finished(1)
    assert sent[0]["headers"] == {"Title": "Downloads done", "Tags": "tv,anime"}


def test_a_colon_in_the_value_survives(sent, monkeypatch):
    monkeypatch.setenv("ANIWORLD_WEBHOOK_URL", JELLYFIN)
    monkeypatch.setenv("ANIWORLD_WEBHOOK_HEADERS", "X-Target: http://host:8096")
    webhook.queue_finished(1)
    assert sent[0]["headers"] == {"X-Target": "http://host:8096"}


def test_a_broken_header_is_skipped_without_logging_it(sent, monkeypatch, log):
    monkeypatch.setenv("ANIWORLD_WEBHOOK_URL", JELLYFIN)
    monkeypatch.setenv("ANIWORLD_WEBHOOK_HEADERS", "supersecrettoken | X-Ok: 1")
    webhook.queue_finished(1)

    assert sent[0]["headers"] == {"X-Ok": "1"}, "the good one is still sent"
    assert "Ignoring a webhook header" in log.text
    assert "supersecrettoken" not in log.text


@pytest.mark.parametrize("raw, expected", [("get", "GET"), (" put ", "PUT")])
def test_the_method_is_read_case_insensitively(sent, monkeypatch, raw, expected):
    monkeypatch.setenv("ANIWORLD_WEBHOOK_URL", JELLYFIN)
    monkeypatch.setenv("ANIWORLD_WEBHOOK_METHOD", raw)
    webhook.queue_finished(1)
    assert sent[0]["method"] == expected


def test_an_unknown_method_sends_nothing(sent, monkeypatch, log):
    monkeypatch.setenv("ANIWORLD_WEBHOOK_URL", JELLYFIN)
    monkeypatch.setenv("ANIWORLD_WEBHOOK_METHOD", "DELETE")
    webhook.queue_finished(1)
    assert sent == []
    assert "Webhook skipped: The method has to be one of" in log.text


@pytest.mark.parametrize(
    "url",
    ["jellyfin:8096/Library/Refresh", "ftp://host/x", "file:///etc/passwd", "http://"],
)
def test_only_http_urls_are_called(sent, monkeypatch, log, url):
    monkeypatch.setenv("ANIWORLD_WEBHOOK_URL", url)
    webhook.queue_finished(1)
    assert sent == []
    assert "http:// or https://" in log.text


# ---------------------------------------------------------------------------
# The body
# ---------------------------------------------------------------------------
def test_a_json_body_is_sent_as_json(sent, monkeypatch):
    monkeypatch.setenv("ANIWORLD_WEBHOOK_URL", "https://discord.com/api/webhooks/1/x")
    monkeypatch.setenv("ANIWORLD_WEBHOOK_BODY", '{"content": "Neue Folgen ✓"}')
    webhook.queue_finished(1)

    call = sent[0]
    assert call["headers"]["Content-Type"] == "application/json"
    assert call["data"] == '{"content": "Neue Folgen ✓"}'.encode()


def test_a_plain_body_is_sent_as_text(sent, monkeypatch):
    monkeypatch.setenv("ANIWORLD_WEBHOOK_URL", "https://ntfy.sh/topic")
    monkeypatch.setenv("ANIWORLD_WEBHOOK_BODY", "New downloads are ready")
    webhook.queue_finished(1)

    call = sent[0]
    assert call["headers"]["Content-Type"] == "text/plain; charset=utf-8"
    assert call["data"] == b"New downloads are ready"


@pytest.mark.parametrize("body", ["42", "true", '"just a string"'])
def test_a_json_scalar_is_still_plain_text(sent, monkeypatch, body):
    monkeypatch.setenv("ANIWORLD_WEBHOOK_URL", "https://ntfy.sh/topic")
    monkeypatch.setenv("ANIWORLD_WEBHOOK_BODY", body)
    webhook.queue_finished(1)
    assert sent[0]["headers"]["Content-Type"].startswith("text/plain")


def test_a_configured_content_type_wins(sent, monkeypatch):
    monkeypatch.setenv("ANIWORLD_WEBHOOK_URL", JELLYFIN)
    monkeypatch.setenv("ANIWORLD_WEBHOOK_HEADERS", "content-type: application/xml")
    monkeypatch.setenv("ANIWORLD_WEBHOOK_BODY", "<done/>")
    webhook.queue_finished(1)
    assert sent[0]["headers"] == {"content-type": "application/xml"}


def test_no_content_type_is_added_without_a_body(sent, monkeypatch):
    monkeypatch.setenv("ANIWORLD_WEBHOOK_URL", JELLYFIN)
    webhook.queue_finished(1)
    assert "Content-Type" not in sent[0]["headers"]


# ---------------------------------------------------------------------------
# Failures stay in the log
# ---------------------------------------------------------------------------
def test_a_connection_error_is_logged_not_raised(sent, monkeypatch, log):
    monkeypatch.setenv("ANIWORLD_WEBHOOK_URL", JELLYFIN)
    sent.answer["response"] = ConnectionError("connection refused")
    webhook.queue_finished(1)
    assert "Webhook could not be sent: connection refused" in log.text


def test_an_error_status_is_logged_as_a_warning(sent, monkeypatch, log):
    monkeypatch.setenv("ANIWORLD_WEBHOOK_URL", JELLYFIN)
    sent.answer["response"] = FakeResponse(401, "Unauthorized", "bad token")
    webhook.queue_finished(1)

    warnings = [r for r in log.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "401 Unauthorized" in warnings[0].getMessage()
    assert "bad token" in warnings[0].getMessage()


def test_a_success_is_only_logged_at_info(sent, monkeypatch, log):
    monkeypatch.setenv("ANIWORLD_WEBHOOK_URL", JELLYFIN)
    webhook.queue_finished(3)

    assert all(r.levelno == logging.INFO for r in log.records)
    assert "after 3 finished download(s)" in log.text
    assert "Webhook answered 204 No Content" in log.text


def test_a_connection_error_does_not_leak_the_token(sent, monkeypatch, log):
    """urllib3 quotes the path, and a Discord webhook's path is its token."""
    monkeypatch.setenv(
        "ANIWORLD_WEBHOOK_URL", "https://discord.com/api/webhooks/123/SECRET?wait=1"
    )
    sent.answer["response"] = ConnectionError(
        "HTTPSConnectionPool(host='discord.com', port=443): Max retries exceeded "
        "with url: /api/webhooks/123/SECRET?wait=1 (Caused by NewConnectionError)"
    )
    webhook.queue_finished(1)

    assert "Max retries exceeded" in log.text, "the reason is still there"
    assert "SECRET" not in log.text
    assert "wait=1" not in log.text


@pytest.mark.parametrize("url", ["http://[::1/SECRET", "http://host:SECRET/x"])
def test_an_unparseable_url_is_logged_without_details(sent, monkeypatch, log, url):
    monkeypatch.setenv("ANIWORLD_WEBHOOK_URL", url)
    webhook.queue_finished(1)
    assert sent == []
    assert "Webhook skipped: The URL is not valid" in log.text
    assert "SECRET" not in log.text


def test_the_log_leaves_out_tokens_in_the_url(sent, monkeypatch, log):
    monkeypatch.setenv(
        "ANIWORLD_WEBHOOK_URL",
        "https://user:pw@discord.com/api/webhooks/123/SECRET?wait=SECRET2",
    )
    sent.answer["response"] = FakeResponse(400, "Bad Request")
    webhook.queue_finished(1)

    assert "https://discord.com" in log.text
    for secret in ("SECRET", "pw", "/api/webhooks"):
        assert secret not in log.text


# ---------------------------------------------------------------------------
# Header names
# ---------------------------------------------------------------------------
def test_a_header_name_with_a_space_is_skipped(sent, monkeypatch, log):
    """niquests would refuse it and with it the whole request."""
    monkeypatch.setenv("ANIWORLD_WEBHOOK_URL", JELLYFIN)
    monkeypatch.setenv("ANIWORLD_WEBHOOK_HEADERS", "My Header: 1 | X-Ok: 2")
    webhook.queue_finished(1)
    assert sent[0]["headers"] == {"X-Ok": "2"}


def test_strict_parsing_refuses_a_broken_entry():
    with pytest.raises(webhook.WebhookError, match="Name: value"):
        webhook.parse_headers("X-Ok: 1 | justatoken", strict=True)


def test_strict_parsing_accepts_what_the_docs_show():
    raw = 'Authorization: MediaBrowser Token="abc" | Title: Done'
    assert webhook.parse_headers(raw, strict=True) == {
        "Authorization": 'MediaBrowser Token="abc"',
        "Title": "Done",
    }


# ---------------------------------------------------------------------------
# Sending a test from the settings page
# ---------------------------------------------------------------------------
def test_a_test_without_a_url_says_so(sent):
    assert webhook.test() == {"ok": False, "error": "No webhook URL is set"}
    assert sent == []


def test_a_test_reports_the_answer(sent, monkeypatch):
    monkeypatch.setenv("ANIWORLD_WEBHOOK_URL", JELLYFIN)
    assert webhook.test() == {"ok": True, "status": "204 No Content", "body": ""}
    assert len(sent) == 1


def test_a_test_passes_on_what_the_service_disliked(sent, monkeypatch):
    monkeypatch.setenv("ANIWORLD_WEBHOOK_URL", "https://discord.com/api/webhooks/1/x")
    sent.answer["response"] = FakeResponse(
        400, "Bad Request", '{"message": "Cannot send an empty message"}' + "x" * 500
    )
    result = webhook.test()
    assert result["ok"] is False
    assert result["status"] == "400 Bad Request"
    assert result["body"].startswith('{"message": "Cannot send an empty message"}')
    assert len(result["body"]) == 200, "a long answer is cut short"


def test_a_test_reports_settings_that_cannot_work(sent, monkeypatch):
    monkeypatch.setenv("ANIWORLD_WEBHOOK_URL", JELLYFIN)
    monkeypatch.setenv("ANIWORLD_WEBHOOK_METHOD", "DELETE")
    result = webhook.test()
    assert result["ok"] is False
    assert "The method has to be one of" in result["error"]
    assert sent == []


@pytest.mark.parametrize(
    "error, reason",
    [
        (
            niquests.exceptions.ConnectionError,
            "Could not connect to https://discord.com",
        ),
        (
            niquests.exceptions.ConnectTimeout,
            "No answer from https://discord.com within 10 seconds",
        ),
        (
            niquests.exceptions.ReadTimeout,
            "No answer from https://discord.com within 10 seconds",
        ),
        (niquests.exceptions.SSLError, "The TLS connection to https://discord.com"),
        (RuntimeError, "The request failed"),
    ],
)
def test_a_failed_test_gives_a_short_reason_and_no_token(
    sent, monkeypatch, error, reason
):
    """The pill gets one line, the hint underneath gets the whole error."""
    monkeypatch.setenv(
        "ANIWORLD_WEBHOOK_URL", "https://discord.com/api/webhooks/1/SECRET"
    )
    sent.answer["response"] = error("Max retries with url: /api/webhooks/1/SECRET")
    result = webhook.test()

    assert result["ok"] is False
    assert result["error"].startswith(reason)
    assert "Max retries" in result["detail"]
    assert "SECRET" not in result["error"] + result["detail"]
