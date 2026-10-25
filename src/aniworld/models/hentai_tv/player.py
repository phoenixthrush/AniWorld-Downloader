"""Resolve nhplayer's signed media URL, using Chromium only as a fallback."""

import base64
import hashlib
import json
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

from curl_cffi import requests

from ...logger import get_logger

logger = get_logger(__name__)


class _PlayerMarkup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = {}
        self.scripts = []
        self.template = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        element_id = attrs.get("id")
        if element_id:
            self.elements[element_id] = {"attrs": attrs, "text": ""}
        if tag == "template":
            self.template = element_id
        if tag == "script" and attrs.get("src"):
            self.scripts.append(attrs["src"])

    def handle_endtag(self, tag):
        if tag == "template":
            self.template = None

    def handle_data(self, data):
        if self.template:
            self.elements[self.template]["text"] += data


def _challenge_fields(markup, script):
    """Read each fresh challenge's randomized selectors and server values."""
    selectors = re.findall(r"getElementById\(\s*['\"]([^'\"]+)", script)[:5]
    attributes = re.findall(r"getAttribute\(\s*['\"](data-[^'\"]+)", script)
    if len(selectors) != 5 or len(attributes) != 3:
        raise ValueError("Unsupported nhplayer challenge layout")
    elements = [markup.elements[selector] for selector in selectors]
    parts = [
        elements[0]["attrs"][attributes[0]],
        elements[1]["attrs"]["value"],
        elements[2]["attrs"][attributes[1]],
        elements[3]["text"].strip(),
    ]
    if any(len(part) != 8 for part in parts):
        raise ValueError("Invalid nhplayer challenge parts")
    fields = dict(zip(("p1", "p2", "p3", "p4"), parts, strict=True))
    fields["t"] = elements[4]["attrs"][attributes[2]]
    parameters = re.search(r"new URLSearchParams\(\s*\{(.*?)\}\)", script, re.DOTALL)[1]
    for name in ("sc", "rid"):
        variable = re.search(rf"\b{name}:\s*(\w+)", parameters)[1]
        fields[name] = re.search(rf"\b{variable}\s*=\s*['\"]([^'\"]+)", script)[1]
    return fields


def _solve_work(challenge, deadline):
    for number in range(10_000_000):
        proof = format(number, "x")
        if hashlib.sha256((challenge + proof).encode()).digest()[0] == 0:
            return proof
        if number % 4096 == 0 and time.monotonic() >= deadline:
            break
    raise TimeoutError("Timed out solving the nhplayer challenge")


def _resolve_http(player_url, timeout):
    started = time.monotonic()
    deadline = started + timeout

    def remaining():
        seconds = deadline - time.monotonic()
        if seconds <= 0:
            raise TimeoutError("Timed out resolving the nhplayer media URL")
        return min(seconds, 15)

    with requests.Session(impersonate="chrome") as session:
        page = session.get(player_url, timeout=remaining())
        page.raise_for_status()
        markup = _PlayerMarkup()
        markup.feed(page.text)
        challenge_url = next(
            urljoin(player_url, source)
            for source in markup.scripts
            if urlparse(source).path.endswith("/player-core-v2.php")
            or urlparse(source).path == "player-core-v2.php"
        )
        if urlparse(challenge_url).netloc != urlparse(player_url).netloc:
            raise ValueError("The nhplayer challenge has an unexpected origin")
        challenge = session.get(challenge_url, timeout=remaining())
        challenge.raise_for_status()
        fields = _challenge_fields(markup, challenge.text)

        settings = re.search(r"window\._pV\s*=\s*(\{.*?\});", page.text, re.DOTALL)[1]
        settings = json.loads(re.sub(r"([,{]\s*)(\w+)\s*:", r'\1"\2":', settings))
        fields.update(
            vid=settings["vid"],
            c=settings["ct"],
            pid=settings.get("pid", ""),
            st=settings.get("st", ""),
        )
        fields["pow"] = _solve_work(
            "".join(fields[key] for key in ("p1", "p2", "p3", "p4", "t")),
            deadline,
        )
        # The player waits at least 700 ms; allow a small scheduling margin.
        pause = max(0, 0.8 - (time.monotonic() - started))
        if pause >= remaining():
            raise TimeoutError("Timed out resolving the nhplayer media URL")
        time.sleep(pause)
        # Fixed viewport profile accepted by the live player API.
        client = {
            "t": int((time.monotonic() - started) * 1000),
            "b": {"sw": 1280, "sh": 720, "ww": 1280, "wh": 720},
        }
        fields["fp"] = base64.b64encode(json.dumps(client).encode()).decode()
        fields["df"] = ""
        response = session.get(
            urljoin(player_url, "/get-video-url-v2.php"),
            params=fields,
            headers={"X-Requested-With": "XMLHttpRequest", "Referer": player_url},
            timeout=remaining(),
        )
        response.raise_for_status()
        media_url = response.json().get("url")
        if (
            not isinstance(media_url, str)
            or urlparse(media_url).scheme not in ("http", "https")
            or not urlparse(media_url).netloc
        ):
            raise ValueError("The nhplayer server returned an invalid media URL")
        return media_url


def resolve_stream_url(player_url, timeout=45):
    try:
        return _resolve_http(player_url, timeout)
    except Exception as exc:
        logger.debug("nhplayer HTTP resolution failed: %s", type(exc).__name__)
    return _resolve_browser(player_url, timeout)


def _resolve_browser(player_url, timeout):
    from patchright.sync_api import sync_playwright

    from ...autodeps import ensure_patchright_chromium

    ensure_patchright_chromium()
    with sync_playwright() as playwright:
        executable = playwright.chromium.executable_path
        if not Path(executable).is_file():
            raise RuntimeError(
                "Patchright's Chromium browser is missing. "
                "Run 'python -m patchright install chromium', then try again."
            )
        # Use full Chromium: a separate headless-shell installation isn't needed.
        browser = playwright.chromium.launch(headless=True, executable_path=executable)
        try:
            page = browser.new_page()
            page.goto(player_url, wait_until="domcontentloaded", timeout=timeout * 1000)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                # Patchright's isolated world cannot see the player's globals.
                result = page.evaluate(
                    "({url: window.videoReady, error: window.videoError ? "
                    "String(window.videoError) : null})",
                    isolated_context=False,
                )
                if result.get("url"):
                    url = result["url"]
                    if urlparse(url).scheme not in ("http", "https"):
                        raise RuntimeError(
                            "The hentai.tv player returned an invalid media URL"
                        )
                    return url
                if result.get("error"):
                    raise RuntimeError(
                        f"The hentai.tv player failed: {result['error']}"
                    )
                page.wait_for_timeout(250)
            raise RuntimeError("Timed out waiting for the hentai.tv media URL")
        finally:
            browser.close()
