"""Tell another service that the download queue has run dry.

One HTTP request to a URL the user set, sent once the queue has nothing left
to download. It can start a Jellyfin or Plex library scan, or post a message to
ntfy or Discord. Sending it is best effort: a webhook that is down, slow or
misconfigured is logged and never touches the queue.

The settings page can also send it on demand, to try a setup out.
"""

import json
import os
import re
from urllib.parse import urlsplit

import niquests

from ..logger import get_logger

logger = get_logger(__name__)

METHODS = ("POST", "GET", "PUT", "PATCH")
TIMEOUT_SECONDS = 10

# Several headers share one setting. A "|" is very unlikely inside a header.
HEADER_SEPARATOR = "|"

# The characters RFC 9110 allows in a header name
_HEADER_NAME_RE = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")


class WebhookError(ValueError):
    """The webhook settings cannot work, so nothing is sent."""


def webhook_url():
    return os.environ.get("ANIWORLD_WEBHOOK_URL", "").strip()


def webhook_method():
    return os.environ.get("ANIWORLD_WEBHOOK_METHOD", "").strip().upper() or "POST"


def webhook_body():
    return os.environ.get("ANIWORLD_WEBHOOK_BODY", "").strip()


def webhook_headers():
    return parse_headers(os.environ.get("ANIWORLD_WEBHOOK_HEADERS", ""))


def parse_headers(raw, strict=False):
    """Parse "Name: value | Name: value" into a dict.

    A broken entry raises WebhookError when strict, which is how the settings
    page refuses it. Otherwise it is skipped with a warning, so one typo in the
    .env does not stop the rest from being sent.
    """
    headers = {}
    for entry in raw.split(HEADER_SEPARATOR):
        if not entry.strip():
            continue
        name, colon, value = entry.partition(":")
        name = name.strip()
        if colon and _HEADER_NAME_RE.fullmatch(name):
            headers[name] = value.strip()
            continue
        # The entry may well be a bare token, so it is never quoted back
        if strict:
            raise WebhookError('Every header has to look like "Name: value"')
        logger.warning("Ignoring a webhook header that is not 'Name: value'")
    return headers


def check_url(url):
    """Raise WebhookError unless this is a URL the webhook can call."""
    try:
        parts = urlsplit(url)
        _ = parts.port  # raises ValueError for a port that is not a number
    except ValueError:
        raise WebhookError("The URL is not valid") from None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise WebhookError("The URL has to start with http:// or https://")


def check_method(method):
    if method not in METHODS:
        raise WebhookError(f"The method has to be one of {', '.join(METHODS)}")


def _is_json(body):
    try:
        return isinstance(json.loads(body), (dict, list))
    except ValueError:
        return False


def where(url):
    """The URL without its path and query, which can hold a token."""
    parts = urlsplit(url)
    host = parts.netloc.rpartition("@")[2]
    return f"{parts.scheme}://{host}"


def redact(text, url):
    """Cut the URL parts that can hold a token out of an error message.

    Connection errors quote the path, and a Discord webhook's path is its token.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return "invalid URL"
    path = parts.path if parts.path not in ("", "/") else ""
    secrets = (parts.query, path, parts.netloc.rpartition("@")[0])
    for secret in sorted(filter(None, secrets), key=len, reverse=True):
        text = text.replace(secret, "...")
    return text


def send():
    """Send the request the settings describe and return the response.

    Raises WebhookError for settings that cannot work and lets network errors
    through, the callers decide how to report either.
    """
    url = webhook_url()
    if not url:
        raise WebhookError("No webhook URL is set")
    check_url(url)
    method = webhook_method()
    check_method(method)

    headers = webhook_headers()
    body = webhook_body()
    if body and not any(name.lower() == "content-type" for name in headers):
        headers["Content-Type"] = (
            "application/json" if _is_json(body) else "text/plain; charset=utf-8"
        )

    return niquests.request(
        method,
        url,
        headers=headers,
        data=body.encode("utf-8") if body else None,
        timeout=TIMEOUT_SECONDS,
    )


def _status(response):
    return f"{response.status_code} {response.reason or ''}".strip()


def queue_finished(finished):
    """Send the webhook, if one is set, for a queue that just ran dry.

    `finished` is how many queue items finished since the queue was last
    empty. It only goes into the log. Never raises.
    """
    url = webhook_url()
    if not url:
        return
    try:
        check_url(url)
        logger.info(
            "Queue is empty after %s finished download(s), calling webhook %s %s",
            finished,
            webhook_method(),
            where(url),
        )
        response = send()
    except WebhookError as exc:
        logger.warning("Webhook skipped: %s", exc)
        return
    except Exception as exc:
        logger.warning("Webhook could not be sent: %s", redact(str(exc), url))
        return

    if response.status_code >= 400:
        logger.warning(
            "Webhook %s %s answered %s: %s",
            webhook_method(),
            where(url),
            _status(response),
            (response.text or "")[:200],
        )
    else:
        logger.info("Webhook answered %s", _status(response))


def _short_reason(exc, url):
    """One line for the status pill. The full error goes underneath it."""
    target = where(url)
    if isinstance(exc, niquests.exceptions.Timeout):
        return f"No answer from {target} within {TIMEOUT_SECONDS} seconds"
    if isinstance(exc, niquests.exceptions.SSLError):
        return f"The TLS connection to {target} failed"
    if isinstance(exc, niquests.exceptions.ConnectionError):
        return f"Could not connect to {target}"
    return "The request failed"


def test():
    """Send the webhook right now and say how it went, for the settings page.

    Never raises. The answer's body is passed along shortened, it is often the
    only place a service says what it did not like.
    """
    url = webhook_url()
    try:
        response = send()
    except WebhookError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        return {
            "ok": False,
            "error": _short_reason(exc, url),
            "detail": redact(str(exc), url),
        }
    return {
        "ok": response.status_code < 400,
        "status": _status(response),
        "body": (response.text or "")[:200],
    }
