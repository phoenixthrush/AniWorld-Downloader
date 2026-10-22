"""Moflix requests with browser fallback for Cloudflare challenges."""

import json
import re
import time

from curl_cffi import requests

from ...config import GLOBAL_SESSION, MOFLIX_SERIES_PATTERN

BASE_URL = "https://moflix-stream.xyz"


class MoflixError(RuntimeError):
    """An upstream response the app cannot use, with a public error message."""


def normalize_url(url):
    match = MOFLIX_SERIES_PATTERN.fullmatch(url.strip())
    if not match:
        raise ValueError(f"Invalid Moflix episode URL: {url}")
    return (
        f"{BASE_URL}/titles/{match['title_id']}"
        + (match["episode_path"] or "").lower()
        + (match["query"] or "")
    )


def _check_response(response):
    if response.headers.get("cf-mitigated") == "challenge" or re.search(
        r"<title>\s*(?:Just a moment|Attention Required)",
        response.text[:4096],
        re.IGNORECASE,
    ):
        raise MoflixError("Moflix requires verification. Please try again later.")
    response.raise_for_status()


def parse_csrf_token(response):
    """Read the bootstrap JSON without relying on its layout or a closing `};`."""
    _check_response(response)
    assignment = re.search(r"window\.bootstrapData\s*=\s*", response.text)
    if not assignment:
        raise MoflixError("Moflix page is missing its bootstrap data.")
    try:
        data, _ = json.JSONDecoder().raw_decode(response.text[assignment.end() :])
    except ValueError:
        raise MoflixError("Moflix page contains invalid bootstrap data.") from None
    token = data.get("csrf_token") if isinstance(data, dict) else None
    if not isinstance(token, str) or not token:
        raise MoflixError("Moflix page is missing its CSRF token.")
    return token


def parse_json(response):
    _check_response(response)
    content_type = response.headers.get("Content-Type", "").lower()
    if content_type and "json" not in content_type:
        raise MoflixError("Moflix returned a page instead of JSON.")
    try:
        data = response.json()
    except ValueError:
        raise MoflixError("Moflix returned invalid JSON.") from None
    if not isinstance(data, dict):
        raise MoflixError("Moflix returned an invalid JSON object.")
    return data


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
    from ...playwright.captcha import (
        _browser,
        _captcha_timeout,
        _ChallengeSolver,
        _export_session_cookies,
        _is_captcha_page_dom,
    )

    with _browser(BASE_URL) as (context, page):
        # Direct navigation to an API URL can redirect to the login page.
        page.goto(BASE_URL + "/", wait_until="load", timeout=30000)
        solver = _ChallengeSolver()
        deadline = time.monotonic() + _captcha_timeout(30)
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
