import queue as _queue_module
import random as _random
import re as _re
import threading as _threading
import time as _time
from html import unescape as _html_unescape
from urllib.parse import urlparse as _urlparse

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


def _is_download_abort_requested() -> bool:
    from ..models.common.common import is_download_abort_requested

    return is_download_abort_requested()


def _ensure_network_binding_ready() -> None:
    """No-op: VPN/network binding support is not part of this branch."""
    return


_SOURCE_REDIRECT_NETLOCS = {"s.to", "www.s.to", "serienstream.to", "www.serienstream.to"}
_PROVIDER_NETLOC_HINTS = ("voe", "vidmoly", "vidoza", "dood", "d000d", "do0od")
_URL_RE = _re.compile(r"(?:https?:\\?/\\?/|\\?/\\?/)[^\s'\"<>]+")


def _is_source_redirect_url(url: str) -> bool:
    try:
        return _urlparse(url).netloc.lower() in _SOURCE_REDIRECT_NETLOCS
    except Exception:
        return False


def _is_external_provider_url(url: str) -> bool:
    try:
        parsed = _urlparse(url)
        netloc = parsed.netloc.lower()
        return (
            bool(parsed.scheme and parsed.netloc)
            and not _is_source_redirect_url(url)
            and any(hint in netloc for hint in _PROVIDER_NETLOC_HINTS)
        )
    except Exception:
        return False


def _clean_candidate_url(url: str) -> str:
    url = _html_unescape(str(url or "").strip())
    url = url.replace("\\/", "/")
    if url.startswith("//"):
        url = f"https:{url}"
    return url.rstrip(".,);]'\"")


def _extract_provider_url_from_text(text: str):
    if not text:
        return None

    for match in _URL_RE.finditer(text):
        candidate = _clean_candidate_url(match.group(0))
        if _is_external_provider_url(candidate):
            return candidate

    return None


def _extract_provider_url_from_page(page):
    urls = []
    try:
        urls.append(page.url)
    except Exception:
        pass

    try:
        urls.extend(
            page.evaluate(
                """
                () => {
                    const attrs = ["src", "href", "action", "data-src", "data-url", "data-link"];
                    const out = [];
                    for (const node of document.querySelectorAll("*")) {
                        for (const attr of attrs) {
                            const value = node.getAttribute && node.getAttribute(attr);
                            if (value) out.push(value);
                        }
                    }
                    return out;
                }
                """
            )
        )
    except Exception:
        pass

    for frame in getattr(page, "frames", []):
        try:
            urls.append(frame.url)
        except Exception:
            pass
        try:
            urls.extend(
                frame.evaluate(
                    """
                    () => Array.from(document.querySelectorAll("iframe, a, form, script"))
                        .flatMap((node) => ["src", "href", "action"].map((attr) => node.getAttribute(attr)))
                        .filter(Boolean)
                    """
                )
            )
        except Exception:
            pass

    for url in urls:
        candidate = _clean_candidate_url(url)
        if _is_external_provider_url(candidate):
            return candidate

    try:
        candidate = _extract_provider_url_from_text(page.content())
        if candidate:
            return candidate
    except Exception:
        pass

    for frame in getattr(page, "frames", []):
        try:
            candidate = _extract_provider_url_from_text(frame.content())
            if candidate:
                return candidate
        except Exception:
            pass

    return None


def _remember_provider_candidate(captured_urls, url):
    candidate = _clean_candidate_url(url)
    if _is_external_provider_url(candidate):
        captured_urls.append(candidate)
        return candidate
    return None


def _remember_provider_navigation(captured_urls, request_or_response):
    """Like _remember_provider_candidate but only for actual document navigations.

    Plain "request"/"response" events also fire for preconnect/prefetch hints to
    the provider domain that never become a real player session — those produced
    bogus VOE URLs that looked captured but immediately failed (net::ERR_ABORTED).
    """
    try:
        req = getattr(request_or_response, "request", None)
        req = req() if callable(req) else (req or request_or_response)
        if req.resource_type != "document":
            return None
    except Exception:
        return None
    return _remember_provider_candidate(captured_urls, request_or_response.url)


def _summarize_browser_urls(context):
    seen = []
    for page in getattr(context, "pages", []):
        for url in [getattr(page, "url", "")]:
            if url and url not in seen:
                seen.append(url)
        for frame in getattr(page, "frames", []):
            url = getattr(frame, "url", "")
            if url and url not in seen:
                seen.append(url)
    return seen[-8:]


_STREAM_URL_HINTS = (".m3u8", ".mp4", ".ts", "/hls/", "/stream")


def _attach_diagnostics(page, logger=None, label: str = "") -> None:
    """Log browser console errors and failed/stream-related requests for debugging."""
    if logger is None:
        return
    prefix = f"[{label}] " if label else ""

    def on_console(msg):
        try:
            if msg.type in ("error", "warning"):
                logger.warning(f"{prefix}console {msg.type}: {msg.text}")
        except Exception:
            pass

    def on_request_failed(req):
        try:
            logger.warning(
                f"{prefix}request failed: {req.url} ({req.failure})"
            )
        except Exception:
            pass

    def on_response(resp):
        try:
            url = resp.url
            if any(hint in url.lower() for hint in _STREAM_URL_HINTS):
                logger.warning(f"{prefix}stream-like response: {resp.status} {url}")
        except Exception:
            pass

    try:
        page.on("console", on_console)
        page.on("requestfailed", on_request_failed)
        page.on("response", on_response)
        page.on("pageerror", lambda exc: logger.warning(f"{prefix}page error: {exc}"))
    except Exception:
        pass


def _resolve_source_redirect_in_browser(context, redirect_url: str, logger=None):
    page = None
    captured_urls = []
    try:
        page = context.new_page()
        _attach_diagnostics(page, logger, label="redirect")
        page.on("request", lambda req: _remember_provider_navigation(captured_urls, req))
        page.on(
            "response",
            lambda resp: _remember_provider_navigation(captured_urls, resp),
        )
        page.on(
            "framenavigated",
            lambda frame: _remember_provider_candidate(captured_urls, frame.url),
        )
        page.goto(redirect_url, wait_until="domcontentloaded", timeout=15000)
        deadline = _time.time() + 30
        turnstile_clicked = False
        altcha_clicked = False

        while _time.time() < deadline:
            if _is_download_abort_requested():
                if logger:
                    logger.warning("CAPTCHA solve aborted (Ctrl+C)")
                break

            if captured_urls:
                return captured_urls[-1]

            provider_url = _extract_provider_url_from_page(page)
            if provider_url:
                return provider_url

            # The redirect endpoint may itself be gated by its own Turnstile/ALTCHA
            # challenge before forwarding to the external provider.
            token_ready = _is_turnstile_token_ready(page)
            altcha_ready = _is_altcha_token_ready(page)

            if not token_ready and not turnstile_clicked:
                if _click_turnstile(page, logger):
                    turnstile_clicked = True
                    page.wait_for_timeout(_random.randint(2000, 4000))
                    continue
            elif not token_ready and turnstile_clicked:
                turnstile_clicked = False

            if not altcha_ready and not altcha_clicked:
                if _click_altcha(page, logger):
                    altcha_clicked = True
                    page.wait_for_timeout(_random.randint(1500, 3000))
                    continue
            elif not altcha_ready and altcha_clicked:
                altcha_clicked = False

            if token_ready and altcha_ready:
                try:
                    _click_submit_button(page, logger)
                except Exception:
                    pass

            page.wait_for_timeout(500)
    except Exception as exc:
        if logger:
            logger.debug(f"Could not resolve s.to redirect in browser: {exc}")
    finally:
        if page is not None:
            try:
                page.close()
            except Exception:
                pass

    return None


def _redirect_path_with_query(redirect_url: str) -> str:
    parsed = _urlparse(redirect_url or "")
    if not parsed.path:
        return ""
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


def _click_sto_provider(page, provider_name, language_label, redirect_url=None, logger=None):
    redirect_path = _redirect_path_with_query(redirect_url)
    try:
        result = page.evaluate(
            """
            ({ providerName, languageLabel, redirectPath }) => {
                const norm = (value) => String(value || "").trim().toLowerCase();
                const wantedProvider = norm(providerName);
                const wantedLanguage = norm(languageLabel);
                const wantedPath = String(redirectPath || "");
                const nodes = Array.from(document.querySelectorAll("[data-play-url]"));

                let target = nodes.find((node) => {
                    const playUrl = node.getAttribute("data-play-url") || "";
                    return wantedPath && playUrl === wantedPath;
                });

                if (!target) {
                    target = nodes.find((node) => {
                        return norm(node.getAttribute("data-provider-name")) === wantedProvider
                            && norm(node.getAttribute("data-language-label")) === wantedLanguage;
                    });
                }

                if (!target) {
                    return { ok: false, reason: "provider element not found" };
                }

                const candidates = [
                    target,
                    target.closest("a, button, [role='button'], li"),
                ].filter((node, index, items) => node && items.indexOf(node) === index);

                for (const clickable of candidates) {
                    try {
                        clickable.click();
                        return {
                            ok: true,
                            mode: "click",
                            playUrl: target.getAttribute("data-play-url") || "",
                        };
                    } catch (err) {
                        // Try the next candidate.
                    }
                }

                const playUrl = target.getAttribute("data-play-url");
                if (playUrl) {
                    window.location.href = playUrl;
                    return { ok: true, mode: "navigate", playUrl };
                }
                return { ok: false, reason: "click failed and no play URL found" };
            }
            """,
            {
                "providerName": provider_name,
                "languageLabel": language_label,
                "redirectPath": redirect_path,
            },
        )
        if result and result.get("ok"):
            if logger:
                logger.warning(
                    "Selected s.to provider "
                    f"{provider_name}/{language_label} via {result.get('mode')}"
                )
            page.wait_for_timeout(1200)
            return True
        if logger:
            logger.debug(f"s.to provider selection failed: {result}")
    except Exception as exc:
        if logger:
            logger.debug(f"s.to provider selection error: {exc}")

    return False


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
                logger.warning("Turnstile checkbox clicked")
            return True
        except Exception as err:
            if logger:
                logger.warning(f"Turnstile click attempt failed for {selector}: {err}")
            continue
    if logger:
        logger.warning("No Turnstile iframe found to click")
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


def _is_altcha_token_ready(page) -> bool:
    """Check whether the ALTCHA widget (if present) already has a solved payload.

    Returns True when no ALTCHA widget is on the page (nothing to solve).

    Uses a Playwright locator rather than page.evaluate() + el.shadowRoot —
    ALTCHA's shadow root is closed, so plain JS from the page can't see into
    it (el.shadowRoot is null there) even though the click worked fine.
    Playwright's locator engine pierces closed shadow roots regardless.
    """
    try:
        widget = page.locator("altcha-widget").first
        if widget.count() == 0:
            return True
        input_loc = widget.locator("input[name='altcha']").first
        if input_loc.count() == 0:
            return False
        value = input_loc.input_value(timeout=500)
        return bool(value and len(value) > 10)
    except Exception:
        return False


def _click_altcha(page, logger=None) -> bool:
    """Click the ALTCHA "I'm not a robot" checkbox if the widget is present.

    Uses real mouse move + down/up (like Turnstile) instead of locator.click() —
    a plain .click() reached the element but the widget never registered it as
    a genuine interaction, so the PoW/verification never started.
    """
    try:
        widget = page.locator("altcha-widget").first
        widget.wait_for(state="visible", timeout=2500)
        checkbox = widget.locator("input[type='checkbox']").first
        checkbox.wait_for(state="visible", timeout=2000)
        box = checkbox.bounding_box()
        if not box:
            return False

        x = box["x"] + box["width"] / 2 + _random.uniform(-2, 2)
        y = box["y"] + box["height"] / 2 + _random.uniform(-2, 2)

        page.mouse.move(x, y, steps=_random.randint(8, 20))
        page.wait_for_timeout(_random.randint(80, 250))
        page.mouse.down()
        page.wait_for_timeout(_random.randint(40, 100))
        page.mouse.up()

        if logger:
            logger.warning("ALTCHA checkbox clicked")
        return True
    except Exception as err:
        if logger:
            logger.warning(f"ALTCHA click attempt failed: {err}")
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
        "button:has-text('Weiter')",
        "input[type='submit']",
        'button[type="submit"]',
    )

    for selector in selectors:
        try:
            button = page.locator(selector).first
            button.wait_for(state="visible", timeout=2000)
        except Exception:
            continue

        # Wait briefly for the button to become enabled — right after the
        # captcha resolves it's often still disabled for a moment, and a
        # force-click on a disabled button "succeeds" without doing anything.
        try:
            for _ in range(10):
                if button.is_enabled():
                    break
                page.wait_for_timeout(200)
            else:
                if logger:
                    logger.warning("Submit button stayed disabled, skipping")
                continue
        except Exception:
            pass

        try:
            button.scroll_into_view_if_needed(timeout=1000)
        except Exception:
            pass

        # Real mouse click via bounding box — more human-like than locator
        # .click(), which some bot checks distinguish from a genuine pointer
        # event sequence (move + down + up).
        try:
            box = button.bounding_box()
            if box:
                x = box["x"] + box["width"] / 2
                y = box["y"] + box["height"] / 2
                page.mouse.move(x, y, steps=5)
                page.wait_for_timeout(100)
                page.mouse.click(x, y)
                return True
        except Exception as err:
            if logger:
                logger.warning(f"Submit mouse click failed: {err}")

        try:
            button.click(timeout=2000)
            return True
        except Exception as err:
            if logger:
                logger.warning(f"Submit normal click failed: {err}")

        _neutralize_click_blockers(page)

        try:
            if button.is_enabled():
                button.click(force=True, timeout=2000)
                return True
        except Exception as err:
            if logger:
                logger.warning(f"Submit force-click failed: {err}")

        try:
            clicked = page.evaluate(
                """
                () => {
                    const enabled = (el) => el && !el.disabled;
                    const byText = Array.from(document.querySelectorAll("button"))
                        .find((b) => enabled(b) && (b.textContent || "").trim().toLowerCase() === "weiter");
                    if (byText) {
                        byText.click();
                        return true;
                    }
                    const byType = document.querySelector("button[type='submit']:not([disabled]), input[type='submit']:not([disabled])");
                    if (byType) {
                        byType.click();
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
        # serienstream.to inline Turnstile modal
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

            _ensure_network_binding_ready()
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
                    if _is_download_abort_requested():
                        logger.warning("CAPTCHA solve aborted (Ctrl+C)")
                        break

                    # Standard Cloudflare full-page challenge
                    if any(c["name"] == "cf_clearance" for c in context.cookies()):
                        solved = True
                        break

                    # serienstream.to modal: form target="player-iframe" — after Weiter the VOE URL
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

        _ensure_network_binding_ready()
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
                if _is_download_abort_requested():
                    logger.warning("CAPTCHA solve aborted (Ctrl+C)")
                    break

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

                # serienstream.to modal: poll player-iframe for the VOE URL
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


def playwright_get_iframe_url(url: str, timeout: int = 20) -> str:
    """Open `url` in a headless browser and return the first external iframe URL.

    Some sites (e.g. burning-series.io) render the hoster embed client-side, so
    the embed URL only exists after JavaScript runs. This loads the page, waits
    for a cross-origin iframe to appear, and returns it. Raises when patchright
    isn't available so callers can surface a clear message.
    """
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError(
            "patchright is not installed. Install it with: "
            "pip install patchright && patchright install chromium"
        )

    from ..logger import get_logger

    logger = get_logger(__name__)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--disable-gpu"])
            context = browser.new_context(viewport={"width": 1280, "height": 720})
            _inject_session_cookies(context, url)
            page = context.new_page()
            logger.debug(f"Opening page for iframe capture: {url}")
            page.goto(url, wait_until="domcontentloaded")

            deadline = _time.time() + timeout
            found = url
            while _time.time() < deadline:
                candidate = _extract_iframe_url(page, url)
                if candidate and candidate != url:
                    found = candidate
                    break
                page.wait_for_timeout(500)

            browser.close()
        return found
    except Exception as e:
        logger.error(f"Failed to capture iframe URL for {url}: {e}")
        raise


def playwright_get_hanime_stream_url(url: str) -> str:
    """Open a hanime page in Playwright and capture the first playable HLS URL."""
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError(
            "patchright ist nicht installiert. "
            "Bitte installieren mit: pip install patchright && patchright install chromium"
        )

    from ..logger import get_logger

    logger = get_logger(__name__)

    final_url = None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-gpu"],
            )
            context = browser.new_context(viewport={"width": 1280, "height": 720})
            _inject_session_cookies(context, url)
            page = context.new_page()

            def _capture_manifest(response):
                nonlocal final_url
                response_url = response.url
                if (
                    not final_url
                    and "m3u8s.highwinds-cdn.com" in response_url
                    and response.status in (200, 206)
                ):
                    final_url = response_url

            page.on("response", _capture_manifest)
            logger.warning(f"Opening hanime page for stream capture: {url}")
            page.goto(url, wait_until="domcontentloaded")

            deadline = _time.time() + 20
            while _time.time() < deadline and not final_url:
                page.wait_for_timeout(500)

            if not final_url:
                page.reload(wait_until="domcontentloaded")
                deadline = _time.time() + 15
                while _time.time() < deadline and not final_url:
                    page.wait_for_timeout(500)

            browser.close()

        if final_url:
            logger.info(f"Captured hanime manifest URL: {final_url}")
        return final_url

    except Exception as e:
        logger.error(f"Failed to capture hanime stream URL: {e}", exc_info=True)
        return None


def playwright_get_cineby_stream_url(url: str, timeout: int = 40) -> str:
    """Open the vidking player embed and capture the playable HLS (m3u8) URL.

    cineby embeds the vidking player (`vidking.net/embed/...`), which resolves
    the stream client-side from an encrypted source API. `url` is the vidking
    embed URL — a bare player page that autoplays, so a single click plus
    `video.play()` reliably makes it request the `index.m3u8` we capture. This
    is far more dependable than driving cineby's full SPA (Cloudflare + a finicky
    play button).
    """
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError(
            "patchright is not installed. Install it with: "
            "pip install patchright && patchright install chromium"
        )

    from ..logger import get_logger

    logger = get_logger(__name__)
    final_url = None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--disable-gpu"])
            context = browser.new_context(
                viewport={"width": 1280, "height": 720}, locale="en-US"
            )
            page = context.new_page()

            def _capture(response):
                nonlocal final_url
                u = response.url
                if not final_url and ".m3u8" in u.split("?", 1)[0].lower():
                    final_url = u

            page.on("response", _capture)
            logger.debug(f"Opening vidking embed for stream capture: {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=40000)
            except Exception:
                pass
            try:
                page.wait_for_selector("video, button", timeout=15000)
            except Exception:
                pass
            page.wait_for_timeout(1500)

            # One click in the middle to start playback (a user gesture), then
            # only ever call play() when paused so we never toggle it back off.
            try:
                page.mouse.click(640, 360)
            except Exception:
                pass
            deadline = _time.time() + timeout
            while _time.time() < deadline and not final_url:
                try:
                    page.evaluate(
                        "() => { const v = document.querySelector('video');"
                        " if (v) { v.muted = true; if (v.paused) v.play().catch(()=>{}); } }"
                    )
                except Exception:
                    pass
                page.wait_for_timeout(1200)

            browser.close()

        if final_url:
            logger.info("Captured cineby/vidking manifest URL")
        return final_url
    except Exception as e:
        logger.error(f"Failed to capture cineby stream URL: {e}")
        return None


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


def solve_sto_modal(
    episode_url: str,
    provider_name: str,
    language_label: str,
    redirect_url: str | None = None,
):
    """
    Open the serienstream.to episode page in a browser, click the provider button,
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
        import os as _os

        debug_visible = _os.environ.get("ANIWORLD_CAPTCHA_VISIBLE") == "1"
        extra_args = (
            ["--window-position=-32000,-32000", "--window-size=1280,720"]
            if queue_id is not None and not debug_visible
            else []
        )

        _ensure_network_binding_ready()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, args=extra_args)
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
            )
            _inject_session_cookies(context, episode_url)
            captured_urls = []
            captured_pages = set()

            def attach_page_capture(capture_page):
                if capture_page in captured_pages:
                    return
                captured_pages.add(capture_page)
                _attach_diagnostics(capture_page, logger, label="modal")
                capture_page.on(
                    "request",
                    lambda req: _remember_provider_navigation(captured_urls, req),
                )
                capture_page.on(
                    "response",
                    lambda resp: _remember_provider_navigation(captured_urls, resp),
                )
                capture_page.on(
                    "framenavigated",
                    lambda frame: _remember_provider_candidate(
                        captured_urls, frame.url
                    ),
                )

            context.on("page", attach_page_capture)
            page = context.new_page()
            attach_page_capture(page)
            _attach_diagnostics(page, logger, label="modal")

            with _captcha_state_lock:
                _captcha_state = {
                    "url": episode_url,
                    "started_at": _time.time(),
                    "solved": False,
                }

            logger.warning(f"Opening episode page for modal solving: {episode_url}")
            page.goto(episode_url, wait_until="domcontentloaded")
            _click_sto_provider(
                page, provider_name, language_label, redirect_url, logger
            )

            # Single poll loop: streams screenshots from the start, clicks
            # Turnstile checkbox, clicks Weiter once, then waits for result.
            final_url = None
            source_redirect_seen_at = None
            weiter_clicked = False
            turnstile_clicked = False
            altcha_clicked = False
            altcha_clicked_at = None
            both_ready_at = None
            start = _time.time()
            loop_count = 0
            last_state_logged = None

            while _time.time() - start < 90:
                loop_count += 1
                if _is_download_abort_requested():
                    logger.warning("CAPTCHA solve aborted (Ctrl+C)")
                    break

                if captured_urls:
                    final_url = captured_urls[-1]
                    logger.warning(f"Provider URL captured from browser event: {final_url}")
                    break

                provider_url = _extract_provider_url_from_page(page)
                if provider_url:
                    final_url = provider_url
                    logger.warning(f"Provider URL found in page DOM: {final_url}")
                    break

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
                    altcha_ready = _is_altcha_token_ready(page)

                    state = (token_ready, altcha_ready, turnstile_clicked, altcha_clicked)
                    if state != last_state_logged:
                        logger.warning(
                            f"[modal] state: turnstile_ready={token_ready} "
                            f"altcha_ready={altcha_ready} turnstile_clicked={turnstile_clicked} "
                            f"altcha_clicked={altcha_clicked} (loop {loop_count})"
                        )
                        last_state_logged = state

                    # Click Turnstile checkbox if token not yet filled
                    if not token_ready and not turnstile_clicked:
                        if _click_turnstile(page, logger):
                            turnstile_clicked = True
                            page.wait_for_timeout(_random.randint(2000, 4000))
                            continue
                    elif not token_ready and turnstile_clicked:
                        # Turnstile may have reset — allow re-click
                        turnstile_clicked = False
                        both_ready_at = None

                    # Click ALTCHA checkbox if widget present and not yet solved.
                    # The widget runs a client-side proof-of-work after the click,
                    # which can take several seconds — re-clicking too soon restarts
                    # that computation, so give it a grace period before retrying.
                    if not altcha_ready and not altcha_clicked:
                        if _click_altcha(page, logger):
                            altcha_clicked = True
                            altcha_clicked_at = _time.time()
                            page.wait_for_timeout(_random.randint(1500, 3000))
                            continue
                    elif not altcha_ready and altcha_clicked:
                        if altcha_clicked_at is not None and _time.time() - altcha_clicked_at < 8:
                            page.wait_for_timeout(500)
                            continue
                        # Still not solved after the grace period — allow re-click
                        altcha_clicked = False
                        altcha_clicked_at = None
                        both_ready_at = None

                    if token_ready and altcha_ready:
                        if both_ready_at is None:
                            both_ready_at = _time.time()
                            try:
                                buttons_info = page.evaluate(
                                    "() => Array.from(document.querySelectorAll('button, input[type=submit]'))"
                                    ".map(b => ({tag: b.tagName, type: b.type, text: (b.textContent||b.value||'').trim(),"
                                    " disabled: b.disabled, visible: !!(b.offsetWidth || b.offsetHeight)}))"
                                )
                                logger.warning(f"[modal] buttons on page: {buttons_info}")
                            except Exception:
                                pass
                        if _time.time() - both_ready_at < 1.5:
                            page.wait_for_timeout(300)
                            continue
                        try:
                            if _click_submit_button(page, logger):
                                logger.warning("Submit clicked (Turnstile/ALTCHA solved)")
                                weiter_clicked = True
                            else:
                                logger.warning("Submit click failed (will retry)")
                            page.wait_for_timeout(1200)
                        except Exception as e:
                            logger.warning(f"Submit button error: {e}")
                else:
                    # Weiter was clicked – poll for the VOE URL
                    for frame in page.frames:
                        fu = frame.url
                        if fu and fu not in ("about:blank", ""):
                            if _is_external_provider_url(fu):
                                final_url = fu
                                break
                            if _is_source_redirect_url(fu):
                                final_url = fu
                                if source_redirect_seen_at is None:
                                    source_redirect_seen_at = _time.time()
                    if final_url and _is_external_provider_url(final_url):
                        logger.warning(f"player frame URL found: {final_url}")
                        break

                    # Also check if a new tab was opened
                    for pg in context.pages:
                        if pg is not page:
                            attach_page_capture(pg)
                            provider_url = _extract_provider_url_from_page(pg)
                            if provider_url:
                                final_url = provider_url
                                break
                            pu = pg.url
                            if pu and pu not in ("about:blank", ""):
                                if _is_external_provider_url(pu):
                                    final_url = pu
                                    break
                                if _is_source_redirect_url(pu):
                                    final_url = pu
                                    if source_redirect_seen_at is None:
                                        source_redirect_seen_at = _time.time()
                    if final_url and _is_external_provider_url(final_url):
                        logger.warning(f"New page URL found: {final_url}")
                        break
                    if (
                        final_url
                        and _is_source_redirect_url(final_url)
                        and source_redirect_seen_at is not None
                        and _time.time() - source_redirect_seen_at > 4
                    ):
                        break

                _time.sleep(0.8)

            if final_url and _is_source_redirect_url(final_url):
                resolved_url = _resolve_source_redirect_in_browser(
                    context, final_url, logger
                )
                if resolved_url:
                    logger.warning(f"Resolved player redirect URL: {resolved_url}")
                    final_url = resolved_url

            if not final_url and redirect_url:
                resolved_url = _resolve_source_redirect_in_browser(
                    context, redirect_url, logger
                )
                if resolved_url:
                    logger.warning(f"Resolved provider redirect URL: {resolved_url}")
                    final_url = resolved_url

            if not final_url or _is_source_redirect_url(final_url):
                logger.warning(
                    "Could not resolve external provider URL. Browser URLs seen: "
                    f"{_summarize_browser_urls(context)}"
                )

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

    ep = SerienstreamEpisode("https://serienstream.to/serie/mr-pickles/staffel-1/episode-1")

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
