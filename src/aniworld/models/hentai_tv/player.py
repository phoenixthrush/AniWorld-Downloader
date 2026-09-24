"""Resolve nhplayer's signed media URL through its JavaScript player."""

import time
from pathlib import Path
from urllib.parse import urlparse


def resolve_stream_url(player_url, timeout=45):
    from patchright.sync_api import sync_playwright

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
