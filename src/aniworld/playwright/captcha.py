"""Browser-assisted CAPTCHA solving and provider URL capture."""

import queue
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

from niquests.cookies import create_cookie
from patchright.sync_api import Error

from ..logger import get_logger

logger = get_logger(__name__)
_local = threading.local()
_active_sessions = {}
_active_sessions_lock = threading.Lock()
_captcha_lock = threading.Lock()
_captcha_state_lock = threading.Lock()
_captcha_state = None
_on_captcha_start = None
_on_captcha_end = None

_CHALLENGE_HOSTS = ("challenges.cloudflare.com", "hcaptcha.com", "recaptcha.net")
_PROVIDER_HOSTS = (
    "voe.sx",
    "vidoza.net",
    "vidoza.to",
    "doodstream.com",
    "dood.to",
    "dood.watch",
    "filemoon.sx",
    "filemoon.to",
    "vidmoly.to",
    "vidmoly.net",
    "vidmoly.biz",
    "vidara.to",
)
_WIDGETS_JS = """() => {
    const widgets = [];
    const types = {
        turnstile: ['cf-turnstile-response', 'cloudflare.com', 'cf-turnstile'],
        hcaptcha: ['h-captcha-response', 'hcaptcha.com', 'h-captcha'],
        recaptcha: ['g-recaptcha-response', '/recaptcha/', 'g-recaptcha']
    };
    for (const [kind, [name, source, css]] of Object.entries(types)) {
        const inputs = [...document.querySelectorAll(`[name="${name}"]`)];
        const present = inputs.length || document.querySelector(
            `iframe[src*="${source}"], .${css}`
        );
        if (present) widgets.push({kind, ready: inputs.length > 0 &&
            inputs.every(input => Boolean(input.value.trim()))});
    }
    for (const input of document.querySelectorAll('input[type="checkbox"]')) {
        const label = [...(input.labels || [])].map(el => el.textContent).join(' ');
        if (!input.disabled && /robot|roboter|human|mensch|captcha/i.test(label)) {
            widgets.push({kind: 'checkbox', ready: input.checked});
        }
    }
    for (const widget of document.querySelectorAll('altcha-widget')) {
        const payload = widget.querySelector('[name="altcha"]') || document.querySelector('[name="altcha"]');
        widgets.push({kind: 'altcha', ready: widget.getState?.() === 'verified' ||
            Boolean(payload?.value)});
    }
    return widgets;
}"""


def is_captcha_page(html: str, status_code: int = 200) -> bool:
    """Recognize challenge responses before falling back to Chromium."""
    markers = (
        "just a moment",
        "checking your browser",
        "enable javascript and cookies",
        "attention required",
        "cf-turnstile",
        "cf_chl_",
        "challenge-running",
        "cdn-cgi/challenge-platform",
        "challenges.cloudflare.com",
        "hcaptcha.com",
        "g-recaptcha",
        "altcha-widget",
        "player-prepare-turnstile",
        "<title>stream wird vorbereitet...</title>",
        "jschl-answer",
        "ddos protection by cloudflare",
    )
    return status_code in (403, 503) or any(x in html.lower() for x in markers)


def _challenge_kind(url):
    for kind, markers in {
        "turnstile": ("challenges.cloudflare.com", "cdn-cgi/challenge-platform"),
        "hcaptcha": ("hcaptcha.com",),
        "recaptcha": ("/recaptcha/", "recaptcha.net"),
    }.items():
        if any(marker in url.lower() for marker in markers):
            return kind
    return None


def _widgets(frame):
    widgets = frame.evaluate(_WIDGETS_JS, isolated_context=False)
    kinds = {widget["kind"] for widget in widgets}
    # Chromium exposes frames inside closed shadow roots through child_frames.
    for child in frame.child_frames:
        if child.is_detached():
            continue
        kind = _challenge_kind(child.url)
        if kind and kind not in kinds:
            widgets.append({"kind": kind, "ready": False})
            kinds.add(kind)
    return widgets


def _is_captcha_page_dom(page) -> bool:
    """Wait for the challenge to disappear, even with existing clearance cookies."""
    try:
        if page.evaluate("""() => /just a moment|attention required|checking your browser/i
            .test(document.title) || Boolean(document.querySelector(
                '#challenge-running, #cf-challenge-running, #challenge-form'))"""):
            return True
        return any(_widgets(frame) for frame in page.frames)
    except Error:
        # Navigation can replace the document while it is being inspected.
        return True


class _ChallengeSolver:
    """Click checkbox widgets and leave image challenges available to the user."""

    def __init__(self):
        self.clicked = set()

    def ready_to_submit(self, page) -> bool:
        widgets = []
        for frame in page.frames:
            try:
                current = _widgets(frame)
                widgets.extend(current)
                for widget in current:
                    kind = widget["kind"]
                    key = (frame, kind)
                    if widget["ready"]:
                        self.clicked.discard(key)
                        continue
                    if key in self.clicked:
                        continue
                    clicked = False
                    if kind == "altcha":
                        clicked = frame.evaluate(
                            """() => {
                            let started = false;
                            for (const widget of document.querySelectorAll('altcha-widget')) {
                                if (typeof widget.verify !== 'function') continue;
                                if (widget.getState?.() !== 'verifying' &&
                                    widget.getState?.() !== 'verified') widget.verify();
                                started = true;
                            }
                            return started;
                        }""",
                            isolated_context=False,
                        )
                    elif kind == "checkbox":
                        for checkbox in frame.get_by_role("checkbox").all():
                            if checkbox.is_visible() and not checkbox.is_checked():
                                label = checkbox.get_attribute("aria-label") or ""
                                labels = checkbox.evaluate(
                                    "el => [...(el.labels || [])].map(x => x.textContent).join(' ')"
                                )
                                if any(
                                    word in (label + labels).lower()
                                    for word in (
                                        "robot",
                                        "roboter",
                                        "human",
                                        "mensch",
                                        "captcha",
                                    )
                                ):
                                    checkbox.check(timeout=1000)
                                    clicked = True
                    else:
                        for child in frame.child_frames:
                            if (
                                child.is_detached()
                                or _challenge_kind(child.url) != kind
                            ):
                                continue
                            element = child.frame_element()
                            element.scroll_into_view_if_needed(timeout=1000)
                            box = element.bounding_box()
                            # Larger frames contain image tasks, which need a user.
                            if (
                                box
                                and 40 <= box["height"] <= 100
                                and box["width"] >= 100
                            ):
                                page.mouse.click(
                                    box["x"] + 28, box["y"] + box["height"] / 2
                                )
                                clicked = True
                    if clicked:
                        self.clicked.add(key)
            except Error as exc:
                logger.debug("CAPTCHA widget changed during inspection: %s", exc)
                return False
        return bool(widgets) and all(widget["ready"] for widget in widgets)


class _BrowserHandle:
    def __init__(self, browser, context):
        self.browser = browser
        self.context = context

    def close(self):
        self.browser.close()


def _launch_browser_context(runtime, offscreen=False):
    """Use a fresh headed Chromium context with a fixed screenshot size."""
    if not Path(runtime.chromium.executable_path).is_file():
        raise RuntimeError(
            "Patchright's Chromium browser is missing. "
            "Run 'python -m patchright install chromium', then try again."
        )
    args = ["--window-size=1280,720", "--disable-dev-shm-usage"]
    if offscreen:
        args.append("--window-position=-32000,-32000")
    browser = runtime.chromium.launch(headless=False, args=args)
    try:
        context = browser.new_context(viewport={"width": 1280, "height": 720})
    except Exception:
        browser.close()
        raise
    return _BrowserHandle(browser, context)


def _sync_session_user_agent(page):
    from ..config import GLOBAL_SESSION

    GLOBAL_SESSION.headers["User-Agent"] = page.evaluate("navigator.userAgent")


@contextmanager
def _browser(url, offscreen=True):
    from patchright.sync_api import sync_playwright

    from ..autodeps import _ensure_xvfb

    _ensure_xvfb()
    with sync_playwright() as runtime:
        handle = _launch_browser_context(runtime, offscreen=offscreen)
        try:
            _inject_session_cookies(handle.context, url)
            page = handle.context.new_page()
            _sync_session_user_agent(page)
            yield handle.context, page
        finally:
            handle.close()


def _export_session_cookies(context):
    """Copy browser cookies with their domain, path and expiry intact."""
    from ..config import GLOBAL_SESSION

    for item in context.cookies():
        expires = item.get("expires", -1)
        cookie = create_cookie(
            item["name"],
            item["value"],
            domain=item["domain"],
            path=item.get("path", "/"),
            secure=item.get("secure", False),
            expires=int(expires) if expires > 0 else None,
            discard=expires <= 0,
            rest={"HttpOnly": item.get("httpOnly", False)},
        )
        cookie.domain_specified = cookie.domain_initial_dot
        GLOBAL_SESSION.cookies.set_cookie(cookie)


def _inject_session_cookies(context, url):
    """Copy only unexpired cookies belonging to the requested host."""
    from ..config import GLOBAL_SESSION

    host = urlparse(url).hostname
    existing = {(c["domain"], c.get("path", "/"), c["name"]) for c in context.cookies()}
    cookies = []
    for item in GLOBAL_SESSION.cookies:
        domain = item.domain.lstrip(".")
        if not domain or item.is_expired() or not host:
            continue
        if host != domain and not (
            item.domain_specified and host.endswith("." + domain)
        ):
            continue
        browser_domain = "." + domain if item.domain_specified else domain
        if (browser_domain, item.path or "/", item.name) in existing:
            continue
        cookie = {
            "name": item.name,
            "value": item.value,
            "domain": browser_domain,
            "path": item.path or "/",
            "secure": item.secure,
        }
        if item.expires is not None:
            cookie["expires"] = item.expires
        cookies.append(cookie)
    if cookies:
        context.add_cookies(cookies)


class CaptchaSession:
    """Exchange screenshots and clicks with the queue page."""

    def __init__(self):
        self.screenshot = b""
        self.lock = threading.Lock()
        self.clicks = queue.Queue()
        self.done = False
        self.result_url = None

    def get_screenshot(self):
        with self.lock:
            return self.screenshot

    def enqueue_click(self, x, y):
        self.clicks.put((x, y))

    def update(self, page):
        while True:
            try:
                x, y = self.clicks.get_nowait()
            except queue.Empty:
                break
            page.mouse.click(x, y)
        try:
            screenshot = page.screenshot(type="jpeg", quality=65, timeout=3000)
            with self.lock:
                self.screenshot = screenshot
        except Error as exc:
            logger.debug("CAPTCHA screenshot unavailable: %s", exc)


def get_captcha_status():
    with _captcha_state_lock:
        return dict(_captcha_state) if _captcha_state else None


def _notify(callback, *args):
    if callback:
        try:
            callback(*args)
        except Exception:
            logger.exception("Could not update CAPTCHA queue status")


@contextmanager
def _solving(url):
    global _captcha_state

    with _captcha_lock:
        queue_id = getattr(_local, "queue_id", None)
        session = CaptchaSession() if queue_id is not None else None
        with _captcha_state_lock:
            _captcha_state = {"url": url, "started_at": time.time(), "solved": False}
        if session:
            with _active_sessions_lock:
                _active_sessions[queue_id] = session
            _notify(_on_captcha_start, queue_id, url)
        logger.info("Opening CAPTCHA browser for %s", url)
        try:
            yield session
        finally:
            if session:
                session.done = True
                _notify(_on_captcha_end, queue_id)
                with _active_sessions_lock:
                    _active_sessions.pop(queue_id, None)
            with _captcha_state_lock:
                _captcha_state = None


def _is_provider_url(candidate, source):
    from ..config import STO_ALL_HOSTS

    parsed = urlparse(candidate)
    host = (parsed.hostname or "").removeprefix("www.")
    source_host = (urlparse(source).hostname or "").removeprefix("www.")
    if source_host in STO_ALL_HOSTS and host in STO_ALL_HOSTS:
        return False
    return (
        parsed.scheme in ("http", "https")
        and bool(host)
        and host != source_host
        and not any(host == x or host.endswith("." + x) for x in _CHALLENGE_HOSTS)
        and "recaptcha" not in parsed.path
        and "cdn-cgi/challenge-platform" not in parsed.path
    )


def _extract_iframe_url(page, current_url):
    frames = sorted(page.frames, key=lambda frame: frame.name != "player-iframe")
    for frame in frames:
        if _is_provider_url(frame.url, current_url):
            return frame.url
    return current_url


def _provider_result(context, source, submitted, existing_frames):
    for tab in context.pages:
        if _is_provider_url(tab.url, source):
            host = urlparse(tab.url).hostname
            if submitted or any(
                host == x or host.endswith("." + x) for x in _PROVIDER_HOSTS
            ):
                return tab.url
        for frame in tab.frames:
            if _is_provider_url(frame.url, source):
                host = urlparse(frame.url).hostname
                if (
                    frame.name == "player-iframe"
                    or (submitted and frame.url not in existing_frames)
                    or any(host == x or host.endswith("." + x) for x in _PROVIDER_HOSTS)
                ):
                    return frame.url
    return None


def _click_submit_button(page):
    for frame in page.frames:
        buttons = frame.locator(
            'button[type="submit"], input[type="submit"], button:has-text("Weiter")'
        )
        for button in buttons.all():
            if button.is_visible() and button.is_enabled():
                # Dispatch the site's click handler without hitting ad overlays.
                button.evaluate("button => button.click()")
                return True
    return False


def _solve(url, prepare=None, timeout=300):
    with (
        _solving(url) as session,
        _browser(url, offscreen=session is not None) as (context, page),
    ):
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        submitted = False
        existing_frames = set()

        def close_popup(tab):
            if not submitted:
                tab.close()

        if prepare:
            context.on("page", close_popup)
            prepare(page)
        deadline = time.monotonic() + timeout
        solver = _ChallengeSolver()
        while time.monotonic() < deadline:
            if session:
                session.update(page)
            result = _provider_result(context, url, submitted, existing_frames)
            if not result and not prepare and not _is_captcha_page_dom(page):
                result = page.url
            if result:
                _export_session_cookies(context)
                if session:
                    session.result_url = result
                return result
            try:
                if not submitted and (prepare or solver.ready_to_submit(page)):
                    existing_frames = {frame.url for frame in page.frames}
                    # A popup may open synchronously inside the click handler.
                    submitted = True
                    try:
                        submitted = _click_submit_button(page)
                    except Error:
                        submitted = False
                        raise
            except Error as exc:
                logger.debug("CAPTCHA document changed during interaction: %s", exc)
            page.wait_for_timeout(500)
        logger.warning("CAPTCHA timed out after %ss: %s", timeout, url)
        return None


def solve_captcha(url: str):
    """Solve checkbox challenges, with a visible browser or queue interaction."""
    return _solve(url)


def solve_sto_modal(episode_url, provider_name, language_label, redirect_url=None):
    """Open the selected S.to player and click Weiter without solving its widgets."""

    def prepare(page):
        clicked = page.evaluate(
            """({redirect, provider, language}) => {
            const target = redirect ? new URL(redirect).pathname + new URL(redirect).search : null;
            for (const button of document.querySelectorAll('[data-play-url]')) {
                const matches = target ? button.dataset.playUrl === target :
                    button.dataset.providerName === provider && button.dataset.languageLabel === language;
                if (matches) { button.click(); return true; }
            }
            return false;
        }""",
            {
                "redirect": redirect_url,
                "provider": provider_name,
                "language": language_label,
            },
        )
        if not clicked and redirect_url:
            page.goto(redirect_url, wait_until="domcontentloaded", timeout=30000)
        elif not clicked:
            raise RuntimeError(
                f"S.to player button not found for {provider_name} ({language_label})"
            )

    return _solve(episode_url, prepare=prepare, timeout=90)


def playwright_get_page_url(url: str) -> str:
    result = solve_captcha(url)
    if result is None:
        raise TimeoutError(f"CAPTCHA did not finish for {url}")
    return result


def playwright_get_iframe_url(url: str, timeout: int = 20) -> str:
    with _browser(url) as (context, page):
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = _extract_iframe_url(page, url)
            if result != url:
                _export_session_cookies(context)
                return result
            page.wait_for_timeout(500)
    return url


def playwright_get_hanime_manifest_token(url: str, timeout: int = 15) -> str:
    """Capture the token returned by Hanime's player authentication request."""
    token = None
    with (
        _solving(url) as session,
        _browser(url, offscreen=session is not None) as (context, page),
    ):

        def capture(response):
            nonlocal token
            if (
                response.status == 200
                and urlparse(response.url).hostname == "auth.hanime.tv"
            ):
                token = response.header_value("x-token") or token

        page.on("response", capture)
        try:
            page.goto(
                url, wait_until="domcontentloaded", timeout=max(1, timeout) * 1000
            )
        except Error:
            if not token:
                raise
        deadline = time.monotonic() + 300
        solver = _ChallengeSolver()
        while not token and time.monotonic() < deadline:
            if session:
                session.update(page)
            if _is_captcha_page_dom(page) and solver.ready_to_submit(page):
                _click_submit_button(page)
            page.wait_for_timeout(500)
        if not token:
            raise TimeoutError("Hanime player handshake timed out after 300s")
        _export_session_cookies(context)
    return token
