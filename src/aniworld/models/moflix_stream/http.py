"""Moflix requests with browser fallback for Cloudflare challenges."""

import time

from curl_cffi import requests

from ...config import GLOBAL_SESSION

BASE_URL = "https://moflix-stream.xyz"


def get_response(url, session_cookies=None, csrf_token=None):
    headers = {}
    if csrf_token:
        headers = {
            "X-XSRF-TOKEN": csrf_token,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": BASE_URL + "/",
            "Accept": "application/json",
        }
    for attempt in range(3):
        response = requests.get(
            url,
            cookies=session_cookies,
            headers=headers,
            impersonate="chrome",
            timeout=15,
        )
        if response.headers.get("cf-mitigated") == "challenge":
            return _browser_get(url)
        if response.status_code != 429 or attempt == 2:
            return response
        time.sleep(attempt + 1)


def _browser_get(url):
    from patchright.sync_api import sync_playwright

    from ...autodeps import _ensure_xvfb
    from ...playwright.captcha import (
        _ChallengeSolver,
        _export_session_cookies,
        _inject_session_cookies,
        _is_captcha_page_dom,
        _launch_browser_context,
    )

    _ensure_xvfb()
    with sync_playwright() as runtime:
        handle = _launch_browser_context(runtime, offscreen=True)
        try:
            context = handle.context
            _inject_session_cookies(context, BASE_URL)
            page = context.new_page()
            # Direct navigation to an API URL can redirect to the login page.
            page.goto(BASE_URL + "/", wait_until="load", timeout=30000)
            solver = _ChallengeSolver()
            deadline = time.monotonic() + 30
            while _is_captcha_page_dom(page):
                if time.monotonic() >= deadline:
                    raise RuntimeError("Moflix homepage is blocked by Cloudflare")
                solver.ready_to_submit(page)
                page.wait_for_timeout(1000)
            page.wait_for_function("window.bootstrapData?.csrf_token", timeout=15000)
            result = page.evaluate(
                """async (url) => {
                    const headers = new URL(url).pathname.startsWith('/api/') ? {
                        'Accept': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-XSRF-TOKEN': window.bootstrapData.csrf_token
                    } : {};
                    const response = await fetch(url, {
                        headers,
                        credentials: 'same-origin',
                        signal: AbortSignal.timeout(15000)
                    });
                    return {
                        url: response.url,
                        status: response.status,
                        reason: response.statusText,
                        headers: Object.fromEntries(response.headers),
                        body: await response.text()
                    };
                }""",
                url,
                isolated_context=False,
            )
            _export_session_cookies(context)
            response = requests.Response()
            response.url = result["url"]
            response.status_code = result["status"]
            response.ok = 200 <= response.status_code < 400
            response.reason = result["reason"]
            response.headers = requests.Headers(result["headers"])
            response.content = result["body"].encode("utf-8")
            response.cookies = requests.Cookies(GLOBAL_SESSION.cookies)
            return response
        finally:
            handle.close()
