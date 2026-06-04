import queue as _queue_module
import random as _random
import threading as _threading
import time as _time

# Threading-local: set queue_id from the web worker to enable interactive mode
_local = _threading.local()

# Active captcha sessions keyed by queue_id (int)
_active_sessions = {}
_active_sessions_lock = _threading.Lock()

# Optional hooks set by app.py to avoid circular imports
_on_captcha_start = None  # callable(queue_id: int, url: str)
_on_captcha_end = None  # callable(queue_id: int)

# Global captcha state for status polling
_captcha_state_lock = _threading.Lock()
_captcha_state = None  # None or {"url": ..., "started_at": ..., "solved": bool}

# Serialise concurrent solve attempts
_captcha_lock = _threading.Lock()


def _click_turnstile(page, logger=None) -> bool:
    """Locate the Cloudflare Turnstile iframe and click its checkbox.

    Uses human-like mouse movement (random offsets + step-based move) so that
    Turnstile does not flag the click as automated.
    Returns True if a click was performed.
    """
    selectors = (
        "iframe[src*='challenges.cloudflare.com']",
        "iframe[src*='cdn-cgi/challenge-platform']",
    )
    for selector in selectors:
        try:
            iframe_el = page.locator(selector).first
            iframe_el.wait_for(state="visible", timeout=2500)
            box = iframe_el.bounding_box()
            if not box:
                continue

            # The checkbox sits on the left side of the widget (~28px in).
            x = box["x"] + 28 + _random.uniform(-4, 4)
            y = box["y"] + box["height"] / 2 + _random.uniform(-3, 3)

            # Move in several steps, pause briefly, then mouse-down/up.
            page.mouse.move(x, y, steps=_random.randint(8, 20))
            page.wait_for_timeout(_random.randint(80, 250))
            page.mouse.down()
            page.wait_for_timeout(_random.randint(40, 100))
            page.mouse.up()

            if logger:
                logger.info("Turnstile checkbox clicked")
            return True
        except Exception:
            continue
    return False


def _is_turnstile_token_ready(page) -> bool:
    """Check whether the Turnstile hidden input already carries a token."""
    try:
        return page.evaluate(
            "() => { const el = document.querySelector"
            "('input[name=\"cf-turnstile-response\"]');"
            " return !!(el && el.value && el.value.length > 20); }"
        )
    except Exception:
        return False


def _neutralize_click_blockers(page) -> None:
    """Disable common ad/overlay blockers that intercept submit clicks."""
    try:
        page.evaluate(
            """
            () => {
                const selectors = [
                    "iframe[id^='container-']",
                    "a[id^='lk']",
                    "div[id^='b'] iframe",
                ];

                for (const sel of selectors) {
                    for (const el of document.querySelectorAll(sel)) {
                        el.style.pointerEvents = "none";
                        el.style.display = "none";
                        el.setAttribute("aria-hidden", "true");
                    }
                }

                for (const iframe of document.querySelectorAll("iframe")) {
                    const r = iframe.getBoundingClientRect();
                    if (r.width >= 700 && r.height >= 500) {
                        iframe.style.pointerEvents = "none";
                        iframe.style.display = "none";
                        iframe.setAttribute("aria-hidden", "true");
                    }
                }
            }
            """
        )
    except Exception:
        pass


def _click_submit_button(page, logger=None) -> bool:
    """Click the modal submit button with robust fallbacks for intercepted clicks."""
    selectors = (
        'button[type="submit"]',
        "button:has-text('Weiter')",
    )

    for selector in selectors:
        try:
            button = page.locator(selector).first
            button.wait_for(state="visible", timeout=2000)
        except Exception:
            continue

        try:
            button.click(timeout=2000)
            return True
        except Exception as err:
            if logger:
                logger.warning(f"Submit normal click failed: {err}")

        _neutralize_click_blockers(page)

        try:
            button.click(force=True, timeout=2000)
            return True
        except Exception as err:
            if logger:
                logger.warning(f"Submit force-click failed: {err}")

        try:
            clicked = page.evaluate(
                """
                () => {
                    const byType = document.querySelector("button[type='submit']");
                    if (byType) {
                        byType.click();
                        return true;
                    }
                    const byText = Array.from(document.querySelectorAll("button"))
                        .find((b) => (b.textContent || "").trim().toLowerCase() === "weiter");
                    if (byText) {
                        byText.click();
                        return true;
                    }
                    return false;
                }
                """
            )
            if clicked:
                return True
        except Exception as err:
            if logger:
                logger.warning(f"Submit JS click failed: {err}")

    return False


def is_captcha_page(html: str, status_code: int = 200) -> bool:
    """Detect Cloudflare challenge / CAPTCHA pages."""
    if status_code in (403, 503):
        return True

    lower = html.lower()
    indicators = [
        "just a moment",
        "cf-turnstile",
        "checking your browser",
        "enable javascript and cookies",
        "ddos protection by cloudflare",
        "<title>attention required",
        "cdn-cgi/challenge-platform",
        "challenges.cloudflare.com",
        "challenge-running",
        "cf_chl_",
        "jschl-answer",
        "<title>just a moment",
        "hcaptcha.com",
        "newassets.hcaptcha",
        "g-recaptcha",
        # legacy aniworld check kept for safety
        "<title>stream wird vorbereitet...</title>",
        # s.to inline Turnstile modal
        "player-prepare-turnstile",
    ]
    return any(ind in lower for ind in indicators)


def get_captcha_status():
    """Return current captcha state dict for the web UI, or None."""
    with _captcha_state_lock:
        return dict(_captcha_state) if _captcha_state else None


def solve_captcha(url: str):
    """
    Solve a CAPTCHA for *url*.

    - WebUI mode  (queue_id set in threading-local): streams screenshots to the
      Web UI so the user can click inside the browser; injects cookies afterwards.
    - CLI mode: opens a visible browser window and waits for the user to solve.

    After a successful solve all browser cookies are injected into GLOBAL_SESSION
    so subsequent requests work without re-solving.

    Returns the final URL (str) on success — for redirect-based captchas this is
    the provider URL captured from an iframe.  Returns None on timeout / error.
    Callers that don't need the URL can ignore the return value.
    """
    queue_id = getattr(_local, "queue_id", None)
    if queue_id is not None:
        return _solve_captcha_interactive(url, queue_id)
    return _solve_captcha_cli(url)


def _solve_captcha_cli(url: str) -> bool:
    """CLI mode captcha solver — opens a visible browser, injects cookies on success."""
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError(
            "patchright ist nicht installiert. "
            "Bitte installieren mit: pip install patchright && patchright install chromium"
        )

    from ..config import GLOBAL_SESSION
    from ..logger import get_logger

    logger = get_logger(__name__)

    with _captcha_lock:
        global _captcha_state
        with _captcha_state_lock:
            _captcha_state = {"url": url, "started_at": _time.time(), "solved": False}

        logger.warning(
            f"CAPTCHA detected for {url} — opening browser for manual solving"
        )

        try:
            from ..autodeps import _ensure_xvfb

            _ensure_xvfb()
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                context = browser.new_context()
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded")

                timeout = 300  # 5 minutes
                start = _time.time()
                solved = False
                turnstile_clicked = False

                while _time.time() - start < timeout:
                    # Standard Cloudflare full-page challenge
                    if any(c["name"] == "cf_clearance" for c in context.cookies()):
                        solved = True
                        break

                    # s.to modal: form target="player-iframe" — after Weiter the VOE URL
                    # loads into that iframe. The modal HTML stays on the page, so
                    # is_captcha_page() would never become False. Instead poll the frame.
                    for frame in page.frames:
                        if frame.name == "player-iframe":
                            fu = frame.url
                            if fu and fu not in ("about:blank", "", url):
                                final_url = fu
                                solved = True
                                break
                    if solved:
                        break

                    # Also check page content for classic full-page solve
                    try:
                        if not is_captcha_page(page.content()):
                            solved = True
                            break
                    except Exception:
                        pass

                    # Click Turnstile checkbox if not yet clicked
                    if not turnstile_clicked and not _is_turnstile_token_ready(page):
                        if _click_turnstile(page, logger):
                            turnstile_clicked = True
                            page.wait_for_timeout(_random.randint(2000, 4000))
                            continue
                    elif turnstile_clicked and not _is_turnstile_token_ready(page):
                        # Turnstile may have reset — allow re-click
                        turnstile_clicked = False

                    # Auto-click Weiter once Turnstile token is present
                    if _is_turnstile_token_ready(page):
                        try:
                            if _click_submit_button(page, logger):
                                page.wait_for_timeout(2000)
                        except Exception:
                            pass

                    _time.sleep(1.5)

                if solved:
                    for cookie in context.cookies():
                        GLOBAL_SESSION.cookies.set(
                            cookie["name"],
                            cookie["value"],
                            domain=cookie.get("domain", "").lstrip("."),
                        )
                    logger.info("CAPTCHA solved — cookies injected into session")
                else:
                    logger.warning("CAPTCHA timeout after 5 minutes")

                browser.close()

            with _captcha_state_lock:
                _captcha_state = None

            return final_url if solved else None

        except Exception as e:
            logger.error(f"Error while solving CAPTCHA: {e}", exc_info=True)
            with _captcha_state_lock:
                _captcha_state = None
            return None


class CaptchaSession:
    """Holds state for an in-progress interactive captcha solve (web UI mode)."""

    def __init__(self):
        self._screenshot = b""
        self._screenshot_lock = _threading.Lock()
        self._click_queue = _queue_module.Queue()
        self.done = False
        self.result_url = None

    def get_screenshot(self) -> bytes:
        with self._screenshot_lock:
            return self._screenshot

    def _store_screenshot(self, data: bytes):
        with self._screenshot_lock:
            self._screenshot = data

    def enqueue_click(self, x: int, y: int):
        self._click_queue.put_nowait((x, y))


def _solve_captcha_interactive(url: str, queue_id: int) -> bool:
    """WebUI mode: stream screenshots, accept clicks, inject cookies on success."""
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError(
            "patchright ist nicht installiert. "
            "Bitte installieren mit: pip install patchright && patchright install chromium"
        )

    from ..config import GLOBAL_SESSION
    from ..logger import get_logger

    logger = get_logger(__name__)

    session = CaptchaSession()
    with _active_sessions_lock:
        _active_sessions[queue_id] = session

    if _on_captcha_start is not None:
        try:
            _on_captcha_start(queue_id, url)
        except Exception:
            pass

    global _captcha_state
    try:
        from ..autodeps import _ensure_xvfb

        _ensure_xvfb()
        with sync_playwright() as p:
            # headless=False required for Cloudflare/Turnstile to work.
            # Window pushed off-screen to avoid visible popup on server desktops.
            browser = p.chromium.launch(
                headless=False,
                args=["--window-position=-32000,-32000", "--window-size=1280,720"],
            )
            context = browser.new_context(viewport={"width": 1280, "height": 720})
            page = context.new_page()
            page.goto(url)

            with _captcha_state_lock:
                _captcha_state = {
                    "url": url,
                    "started_at": _time.time(),
                    "solved": False,
                }

            solved = False
            turnstile_clicked = False
            for _ in range(300):  # up to ~5 minutes
                # Stream screenshot to Web UI
                try:
                    shot = page.screenshot(type="jpeg", quality=65)
                    session._store_screenshot(shot)
                except Exception:
                    pass

                # Forward pending click events from Web UI
                while not session._click_queue.empty():
                    try:
                        cx, cy = session._click_queue.get_nowait()
                        page.mouse.click(cx, cy)
                        page.wait_for_timeout(400)
                    except Exception:
                        pass

                # Check for cf_clearance cookie (classic Cloudflare challenge)
                if any(c["name"] == "cf_clearance" for c in context.cookies()):
                    solved = True
                    break

                # s.to modal: poll player-iframe for the VOE URL
                for frame in page.frames:
                    if frame.name == "player-iframe":
                        fu = frame.url
                        if fu and fu not in ("about:blank", "", url):
                            result_url = fu
                            solved = True
                            break
                if solved:
                    break

                # Classic full-page solve (no modal)
                try:
                    if not is_captcha_page(page.content()):
                        solved = True
                        break
                except Exception:
                    pass

                # Click Turnstile checkbox if not yet clicked
                if not turnstile_clicked and not _is_turnstile_token_ready(page):
                    if _click_turnstile(page):
                        turnstile_clicked = True
                        page.wait_for_timeout(_random.randint(2000, 4000))
                        continue
                elif turnstile_clicked and not _is_turnstile_token_ready(page):
                    turnstile_clicked = False

                # Auto-click Weiter button once Turnstile token is present
                if _is_turnstile_token_ready(page):
                    try:
                        if _click_submit_button(page, logger):
                            page.wait_for_timeout(2000)
                    except Exception:
                        pass

                page.wait_for_timeout(1000)

            # Final screenshot
            try:
                shot = page.screenshot(type="jpeg", quality=65)
                session._store_screenshot(shot)
            except Exception:
                pass

            if solved:
                for cookie in context.cookies():
                    GLOBAL_SESSION.cookies.set(
                        cookie["name"],
                        cookie["value"],
                        domain=cookie.get("domain", "").lstrip("."),
                    )
                logger.info("CAPTCHA solved — cookies injected into session")
            else:
                logger.warning("CAPTCHA timeout after 5 minutes")

            final_url = page.url
            page.wait_for_timeout(400)
            browser.close()

        # Use the player-iframe URL if captured, otherwise fall back to page URL
        result_url = locals().get("result_url") or _extract_iframe_url(page, url)
        if result_url == url:
            result_url = final_url

        session.result_url = result_url or final_url
        session.done = True

        with _captcha_state_lock:
            _captcha_state = None

        return result_url if solved else None

    finally:
        if _on_captcha_end is not None:
            try:
                _on_captcha_end(queue_id)
            except Exception:
                pass
        with _active_sessions_lock:
            _active_sessions.pop(queue_id, None)


def _extract_iframe_url(page, current_url: str) -> str:
    """
    After a modal is dismissed the provider player loads as an iframe on the same
    page (URL never changes).  Scan all frames for the first external URL.
    Returns the iframe URL if found, otherwise *current_url*.
    """
    try:
        from urllib.parse import urlparse

        current_netloc = urlparse(current_url).netloc.lstrip("www.")
        for frame in page.frames:
            u = frame.url
            if not u or u in ("about:blank", current_url):
                continue
            nl = urlparse(u).netloc.lstrip("www.")
            if nl and nl != current_netloc:
                return u
    except Exception:
        pass
    return current_url


def playwright_get_page_url(url: str) -> str:
    solve_captcha(url)
    from ..config import GLOBAL_SESSION

    return GLOBAL_SESSION.get(url).url


def _inject_session_cookies(context, url: str) -> None:
    """Copy GLOBAL_SESSION cookies into a patchright browser context."""
    try:
        from urllib.parse import urlparse

        from ..config import GLOBAL_SESSION

        base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        cookies = [
            {"name": c.name, "value": c.value, "url": base}
            for c in GLOBAL_SESSION.cookies
        ]
        if cookies:
            context.add_cookies(cookies)
    except Exception:
        pass


def solve_sto_modal(episode_url: str, provider_name: str, language_label: str):
    """
    Open the s.to episode page in a browser, click the provider button,
    solve the Turnstile modal, click Weiter, and return the player-iframe
    URL (e.g. voe.sx/e/...).  Works in CLI and WebUI mode.
    Returns the iframe URL on success, None on timeout.
    """
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError(
            "patchright ist nicht installiert. "
            "Bitte installieren mit: pip install patchright && patchright install chromium"
        )

    from ..config import GLOBAL_SESSION
    from ..logger import get_logger

    logger = get_logger(__name__)

    queue_id = getattr(_local, "queue_id", None)
    session_obj = None
    if queue_id is not None:
        session_obj = CaptchaSession()
        with _active_sessions_lock:
            _active_sessions[queue_id] = session_obj
        if _on_captcha_start is not None:
            try:
                _on_captcha_start(queue_id, episode_url)
            except Exception:
                pass

    global _captcha_state
    try:
        extra_args = (
            ["--window-position=-32000,-32000", "--window-size=1280,720"]
            if queue_id is not None
            else []
        )

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, args=extra_args)
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
            )
            _inject_session_cookies(context, episode_url)
            page = context.new_page()

            with _captcha_state_lock:
                _captcha_state = {
                    "url": episode_url,
                    "started_at": _time.time(),
                    "solved": False,
                }

            logger.warning(f"Opening episode page for modal solving: {episode_url}")
            page.goto(episode_url, wait_until="domcontentloaded")

            # Single poll loop: streams screenshots from the start, clicks
            # Turnstile checkbox, clicks Weiter once, then waits for result.
            from urllib.parse import urlparse as _urlparse

            final_url = None
            weiter_clicked = False
            turnstile_clicked = False
            start = _time.time()

            while _time.time() - start < 90:
                # WebUI: stream screenshots + forward user clicks
                if session_obj is not None:
                    try:
                        session_obj._store_screenshot(
                            page.screenshot(type="jpeg", quality=65)
                        )
                    except Exception:
                        pass
                    while not session_obj._click_queue.empty():
                        try:
                            cx, cy = session_obj._click_queue.get_nowait()
                            page.mouse.click(cx, cy)
                            page.wait_for_timeout(300)
                        except Exception:
                            pass

                if not weiter_clicked:
                    token_ready = _is_turnstile_token_ready(page)

                    # Click Turnstile checkbox if token not yet filled
                    if not token_ready and not turnstile_clicked:
                        if _click_turnstile(page, logger):
                            turnstile_clicked = True
                            page.wait_for_timeout(_random.randint(2000, 4000))
                            continue
                    elif not token_ready and turnstile_clicked:
                        # Turnstile may have reset — allow re-click
                        turnstile_clicked = False

                    if token_ready:
                        try:
                            if _click_submit_button(page, logger):
                                logger.warning("Submit clicked (Turnstile solved)")
                                weiter_clicked = True
                            else:
                                logger.warning("Submit click failed (will retry)")
                            page.wait_for_timeout(1200)
                        except Exception as e:
                            logger.warning(f"Submit button error: {e}")
                else:
                    # Weiter was clicked – poll for the VOE URL
                    for frame in page.frames:
                        if frame.name == "player-iframe":
                            fu = frame.url
                            if fu and fu not in ("about:blank", ""):
                                final_url = fu
                                break
                    if final_url:
                        logger.warning(f"player-iframe URL found: {final_url}")
                        break

                    # Also check if a new tab was opened
                    for pg in context.pages:
                        if pg is not page:
                            pu = pg.url
                            if pu and pu not in ("about:blank", ""):
                                if (
                                    _urlparse(pu).netloc
                                    != _urlparse(episode_url).netloc
                                ):
                                    final_url = pu
                                    break
                    if final_url:
                        logger.warning(f"New page URL found: {final_url}")
                        break

                _time.sleep(0.8)

            if final_url:
                for cookie in context.cookies():
                    GLOBAL_SESSION.cookies.set(
                        cookie["name"],
                        cookie["value"],
                        domain=cookie.get("domain", "").lstrip("."),
                    )

            if session_obj is not None:
                try:
                    session_obj._store_screenshot(
                        page.screenshot(type="jpeg", quality=65)
                    )
                except Exception:
                    pass

            browser.close()

        with _captcha_state_lock:
            _captcha_state = None

        if session_obj is not None:
            session_obj.result_url = final_url
            session_obj.done = True

        return final_url

    except Exception as e:
        from ..logger import get_logger

        get_logger(__name__).error(f"Fehler in solve_sto_modal: {e}", exc_info=True)
        with _captcha_state_lock:
            _captcha_state = None
        return None

    finally:
        if queue_id is not None:
            if _on_captcha_end is not None:
                try:
                    _on_captcha_end(queue_id)
                except Exception:
                    pass
            with _active_sessions_lock:
                _active_sessions.pop(queue_id, None)


if __name__ == "__main__":
    # Use test.py instead :)

    """
    import niquests

    from aniworld.config import Audio, Subtitles
    from aniworld.models import SerienstreamEpisode

    ep = SerienstreamEpisode("https://s.to/serie/mr-pickles/staffel-1/episode-1")

    language = (Audio.GERMAN, Subtitles.NONE)
    provider = "VOE"

    provider_link = ep.provider_link(language=language, provider=provider)

    print(f"Redirect Link: {provider_link}")

    final_url = niquests.get(provider_link)

    if "<title>Stream wird vorbereitet...</title>" in final_url.text:
        print("Captcha detected, solving with Playwright...")
        url = playwright_get_page_url(provider_link)
    else:
        url = final_url.url

    print(f"Final URL: {url}")
    """
