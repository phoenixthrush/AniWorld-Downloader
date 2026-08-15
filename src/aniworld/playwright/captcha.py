"""Cloudflare Turnstile / CAPTCHA solving via a real (patchright) browser.

Ported/merged from MediaForge (https://github.com/PD-Codes/MediaForge) by
PD-Codes — the hardened detection/solving logic below (ad-overlay defence,
network ad-blocking, fingerprint hardening, multi-widget challenge solver)
originates there and was adapted to this project (env vars renamed
MEDIAFORGE_* -> ANIWORLD_*, DNS-routing dropped, AniWorld-Downloader-only
helpers such as the hanime/cineby stream sniffers kept as-is).

Streaming sites fronted by Cloudflare (serienstream.to, aniworld.to,
filmpalast.to, ...) occasionally serve a Turnstile challenge instead of the
requested page. This module opens a hardened, fingerprint-resistant Chromium
context to solve it:

  - is_captcha_page(): cheap HTML/status-code sniff, called by extractors
    (e.g. aniworld.extractors.provider.voe) before falling back to a
    browser-based solve.
  - solve_captcha(): generic solver for a standalone CAPTCHA page. Runs
    headed in CLI mode, or streams screenshots/accepts clicks from the Web UI
    when a queue_id is set (interactive mode).
  - solve_sto_modal(): serienstream.to-specific flow that clicks a provider's
    play button to trigger its in-page Turnstile modal, then extracts the
    resulting player-iframe URL (e.g. voe.sx/e/...).
  - playwright_get_iframe_url() / playwright_get_hanime_stream_url() /
    playwright_get_cineby_stream_url(): background stream-URL sniffers for
    providers whose embed only exists after client-side JS runs. Not part of
    the captcha solver proper, kept here for historical reasons.

Also implements ad-overlay removal, network ad-blocking during the solve,
and fingerprint hardening (WebGL renderer spoof, persistent profile) to keep
Cloudflare's bot score low. Every behavior toggle below reads a plain
ANIWORLD_* environment variable (set it in your .env) — there is no
Web-UI settings screen for this, unlike the ad-overlay/adblock/timeout knobs
which all have sane defaults already.
"""

import queue as _queue_module
import random as _random
import threading as _threading
import time as _time

# Threading-local: set queue_id from the web worker to enable interactive mode
_local = _threading.local()

# Active captcha sessions keyed by queue_id (int).
# Used by: aniworld.web.app (polls status, forwards user clicks from the Web UI).
_active_sessions = {}
_active_sessions_lock = _threading.Lock()

# Optional hooks set by aniworld.web.app to avoid circular imports
_on_captcha_start = None  # callable(queue_id: int, url: str)
_on_captcha_end = None  # callable(queue_id: int)

# Global captcha state for status polling (CLI / non-queue callers)
_captcha_state_lock = _threading.Lock()
_captcha_state = None  # None or {"url": ..., "started_at": ..., "solved": bool}

# Serialise concurrent solve attempts
_captcha_lock = _threading.Lock()

# ---------------------------------------------------------------------------
# Ad-overlay defence
# ---------------------------------------------------------------------------

# Known video-provider netlocs — new browser tabs on these domains are the
# actual player; any other new tab is treated as an ad and closed immediately.
_KNOWN_PROVIDER_NETLOCS = {
    "voe.sx",
    "vidoza.net",
    "vidoza.to",
    "streamtape.com",
    "streamtape.to",
    "doodstream.com",
    "dood.to",
    "dood.watch",
    "filemoon.sx",
    "filemoon.to",
    "vidmoly.to",
    "vidmoly.net",
    "vidmoly.biz",
    "luluvdo.com",
    "vidara.to",
    "veev.to",
}

# JavaScript that removes transparent full-viewport overlay <a> elements.
# serienstream.to sometimes injects an invisible <a target="_blank"> that
# covers the entire page so that any click opens an ad tab.
_REMOVE_AD_OVERLAYS_JS = """
() => {
  try {
    document.querySelectorAll('a').forEach(el => {
      const r  = el.getBoundingClientRect();
      const cs = window.getComputedStyle(el);
      const bigEnough  = r.width  > window.innerWidth  * 0.4
                      && r.height > window.innerHeight * 0.4;
      const invisible  = parseFloat(cs.opacity) < 0.05
                      || cs.visibility === 'hidden'
                      || cs.pointerEvents === 'none';
      const positioned = cs.position === 'fixed' || cs.position === 'absolute';
      if (bigEnough && positioned && (invisible || el.getAttribute('target') === '_blank')) {
        el.remove();
      }
    });
  } catch(e) {}
}
"""


def _remove_ad_overlays(page) -> None:
    """Remove invisible full-page ad-overlay <a> elements before clicking."""
    if _env_flag("ANIWORLD_CAPTCHA_NO_OVERLAY_REMOVAL"):
        return
    try:
        page.evaluate(_REMOVE_AD_OVERLAYS_JS)
    except Exception:
        pass


def _is_known_provider_url(url: str) -> bool:
    """Return True when *url* belongs to a known video-provider domain."""
    try:
        from urllib.parse import urlparse as _up

        netloc = _up(url).netloc.lower().removeprefix("www.")
        return any(
            netloc == p or netloc.endswith("." + p) for p in _KNOWN_PROVIDER_NETLOCS
        )
    except Exception:
        return False


def _is_captcha_infra_url(url: str) -> bool:
    """True for Cloudflare / Turnstile / captcha iframe URLs.

    These must never be mistaken for the provider result: after the modal is
    submitted the Turnstile iframe (challenges.cloudflare.com/...) is still on
    the page, and the foreign-iframe detection would otherwise grab it and hand
    it to the VOE extractor (→ 403, "Keine VOE-Videoquelle gefunden").
    """
    u = (url or "").lower()
    return (
        "challenges.cloudflare.com" in u
        or "cdn-cgi/challenge-platform" in u
        or "/turnstile/" in u
        or "hcaptcha.com" in u
        or "recaptcha" in u
    )


# JavaScript injected at document start: a MutationObserver that continuously
# removes full-page overlay <a> elements, so an ad overlay injected *after* our
# one-off cleanup still can't hijack a click.
_AD_OVERLAY_OBSERVER_JS = """
(() => {
  const clean = () => {
    try {
      document.querySelectorAll('a').forEach(el => {
        const r  = el.getBoundingClientRect();
        const cs = window.getComputedStyle(el);
        const bigEnough  = r.width  > window.innerWidth  * 0.4
                        && r.height > window.innerHeight * 0.4;
        const invisible  = parseFloat(cs.opacity) < 0.05
                        || cs.visibility === 'hidden'
                        || cs.pointerEvents === 'none';
        const positioned = cs.position === 'fixed' || cs.position === 'absolute';
        if (bigEnough && positioned && (invisible || el.getAttribute('target') === '_blank')) {
          el.remove();
        }
      });
    } catch (e) {}
  };
  const start = () => {
    clean();
    try {
      const obs = new MutationObserver(() => clean());
      obs.observe(document.documentElement || document, {childList: true, subtree: true});
    } catch (e) {}
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
"""

# Third-party hosts that must stay reachable during captcha solving: Cloudflare
# (Turnstile), common safe CDNs and hCaptcha/reCAPTCHA fallback infrastructure.
_AD_SAFE_HOST_SUFFIXES = (
    "cloudflare.com",
    "cloudflareinsights.com",
    "jsdelivr.net",
    "unpkg.com",
    "googleapis.com",
    "gstatic.com",
    "google.com",
    "hcaptcha.com",
    "recaptcha.net",
    "s.to",
    "serienstream.to",
    "aniworld.to",
    "filmpalast.to",
)


def _ad_host_allowed(host: str, home_netloc: str) -> bool:
    """True when *host* may load during captcha solving (i.e. is not an ad)."""
    if not host:
        return True
    home = home_netloc.lower()
    home = home.removeprefix("www.")
    if host == home or host.endswith("." + home):
        return True
    if _is_known_provider_url("https://" + host):
        return True
    return any(host == s or host.endswith("." + s) for s in _AD_SAFE_HOST_SUFFIXES)


def _install_network_adblock(context, home_netloc: str, weiter_event=None) -> None:
    """Register a network route handler that aborts requests to third-party (ad)
    hosts — popunders, ad iframes and their scripts never load. The episode
    site, Cloudflare Turnstile and known providers stay reachable. Once the
    Turnstile form has been submitted, third-party navigations/frames are
    allowed again so the provider result (which may sit on an unpredictable
    alias domain) can still be captured.
    """
    from urllib.parse import urlparse as _up

    def _route(route):
        try:
            req = route.request
            host = _up(req.url).netloc.lower()
            host = host.removeprefix("www.")
            if _ad_host_allowed(host, home_netloc):
                route.continue_()
                return
            rtype = req.resource_type
            # After submit the provider result may navigate to an unknown alias
            # domain — allow its top-level navigation / iframe so we can read it.
            if (
                weiter_event is not None
                and weiter_event.is_set()
                and rtype in ("document", "sub_frame")
            ):
                route.continue_()
                return
            if rtype in (
                "document",
                "sub_frame",
                "script",
                "xhr",
                "fetch",
                "media",
                "websocket",
            ):
                if _env_flag("ANIWORLD_CAPTCHA_DEBUG_LOG"):
                    try:
                        from ..logger import get_logger

                        get_logger(__name__).warning(
                            f"[captcha adblock] aborted {rtype} {req.url}"
                        )
                    except Exception:
                        pass
                route.abort()
                return
            route.continue_()
        except Exception:
            try:
                route.continue_()
            except Exception:
                pass

    try:
        context.route("**/*", _route)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Fingerprint hardening
# ---------------------------------------------------------------------------

# WebGL renderer spoof.  Under Xvfb (Docker) Chromium reports a SwiftShader
# renderer ("ANGLE (Google, SwiftShader ...)") — one of the strongest bot
# signals Turnstile evaluates.  This replaces only the UNMASKED vendor/renderer
# strings with a plausible *Linux* Intel/Mesa GPU, keeping the function looking
# native.  Enabled by default in Docker only (see _webgl_spoof_enabled); on a
# real desktop GPU it stays off so we don't fake a worse fingerprint.
_WEBGL_SPOOF_JS = """
(() => {
  const VENDOR   = 'Google Inc. (Intel)';
  const RENDERER = 'ANGLE (Intel, Mesa Intel(R) UHD Graphics (CML GT2), OpenGL 4.6 (Core Profile) Mesa 23.2.1)';
  const patch = (proto) => {
    if (!proto || !proto.getParameter || proto.getParameter.__aniworld) return;
    const orig = proto.getParameter;
    const wrapped = function (p) {
      if (p === 37445) return VENDOR;    // UNMASKED_VENDOR_WEBGL
      if (p === 37446) return RENDERER;  // UNMASKED_RENDERER_WEBGL
      return orig.apply(this, arguments);
    };
    try {
      wrapped.toString = orig.toString.bind(orig);
      Object.defineProperty(wrapped, 'name', {value: 'getParameter', configurable: true});
    } catch (e) {}
    wrapped.__aniworld = true;
    proto.getParameter = wrapped;
  };
  try { patch(self.WebGLRenderingContext && WebGLRenderingContext.prototype); } catch (e) {}
  try { patch(self.WebGL2RenderingContext && WebGL2RenderingContext.prototype); } catch (e) {}
})();
"""


def _in_docker() -> bool:
    import os

    return os.path.exists("/.dockerenv") or os.environ.get("ANIWORLD_DOCKER") == "1"


def _webgl_spoof_enabled() -> bool:
    """WebGL renderer spoof — OFF by default.

    Spoofing only the renderer *string* while the actual rendering stays
    SwiftShader produces an inconsistent fingerprint: getShaderPrecisionFormat,
    the MAX_* parameters, the supported extensions and the canvas/WebGL render
    hash all still report SwiftShader.  Cloudflare is trained on exactly that
    inconsistency, so a string that says "Intel" on top of SwiftShader is a
    *stronger* bot signal than an honest SwiftShader string.  Enable only to
    A/B test with ANIWORLD_SPOOF_WEBGL=1; the real fix is a GPU or Mesa llvmpipe.
    """
    import os

    return os.environ.get("ANIWORLD_SPOOF_WEBGL", "0") == "1"


def _persistent_profile_enabled() -> bool:
    """Persistent Chromium profile.

    Default: ON only inside Docker (a clean, volume-mounted profile keeps
    cf_clearance warm).  On a real desktop a stale/flagged profile causes
    *persistent* "verification failed" loops, so a fresh context is used each
    time.  Force with ANIWORLD_PERSISTENT_PROFILE=1, disable with
    ANIWORLD_NO_PERSISTENT_PROFILE=1.
    """
    import os

    if os.environ.get("ANIWORLD_NO_PERSISTENT_PROFILE", "0") == "1":
        return False
    if os.environ.get("ANIWORLD_PERSISTENT_PROFILE") == "1":
        return True
    return _in_docker()


_PROFILE_DIR_CACHE = None
_PROFILE_LOCK = _threading.Lock()


def _resolve_profile_dir() -> str:
    """Directory for the persistent Chromium profile.  Defaults to
    ~/.aniworld/browser-profile (a mounted volume in the Docker setup, so the
    fingerprint and cf_clearance survive container restarts)."""
    global _PROFILE_DIR_CACHE
    if _PROFILE_DIR_CACHE:
        return _PROFILE_DIR_CACHE
    import os
    import tempfile

    candidate = os.environ.get("ANIWORLD_BROWSER_PROFILE")
    if not candidate:
        try:
            from ..config import ANIWORLD_CONFIG_DIR

            candidate = str(ANIWORLD_CONFIG_DIR / "browser-profile")
        except Exception:
            candidate = os.path.join(
                os.path.expanduser("~"), ".aniworld", "browser-profile"
            )
    try:
        os.makedirs(candidate, exist_ok=True)
        _PROFILE_DIR_CACHE = candidate
    except Exception:
        _PROFILE_DIR_CACHE = tempfile.mkdtemp(prefix="aniworld-bp-")
    return _PROFILE_DIR_CACHE


def _stealth_context_kwargs() -> dict:
    kw = {"ignore_https_errors": True}
    if _in_docker():
        # Under Xvfb a headed window renders at full size regardless of its
        # (off-screen) position, so no_viewport gives a correct render area and
        # click coordinates that match what Playwright measures.  The container
        # is otherwise UTC / C-locale, so give it a realistic identity here.
        kw["no_viewport"] = True
        kw["locale"] = "de-DE"
        kw["timezone_id"] = "Europe/Berlin"
    else:
        # Real desktop: do NOT force locale/timezone — the machine already has
        # consistent, real ones, and overriding them can contradict other
        # signals and trip Cloudflare.  Fixed viewport matching the window so an
        # off-screen WebUI window still renders (no_viewport would be degenerate
        # off-screen on Windows).
        kw["viewport"] = {"width": 1920, "height": 1080}
    return kw


def _stealth_launch_args(offscreen: bool) -> list:
    # --disable-dev-shm-usage: the default 64 MB /dev/shm in Docker is too small,
    #   so the Chromium renderer crashes on larger pages — which shows up as a
    #   captcha that won't render, a blank popup or random scrolling.  Harmless
    #   outside Docker.
    args = [
        "--window-size=1920,1080",
        "--lang=de-DE,de",
        "--disable-dev-shm-usage",
    ]
    if _in_docker():
        # Chromium refuses to build its sandbox when running as root in a
        # capability-stripped container; --no-sandbox is the standard Docker
        # workaround and is NOT observable from the page (no JS fingerprint).
        args.append("--no-sandbox")
    if offscreen:
        args.insert(0, "--window-position=-32000,-32000")
    return args


def _network_adblock_enabled() -> bool:
    """Network ad-blocking is on by default; kill-switch via ANIWORLD_NO_ADBLOCK=1
    (use it to rule the ad-blocker out when the captcha won't load)."""
    import os

    return os.environ.get("ANIWORLD_NO_ADBLOCK", "0") != "1"


def _env_flag(name: str) -> bool:
    """True when the given environment variable is set to "1"."""
    import os

    return os.environ.get(name, "0") == "1"


def _focus_page(page) -> None:
    """Bring the solving page/window to the front before interacting with it
    — but ONLY in visible/manual mode.

    Cloudflare Turnstile's risk engine treats an unfocused/backgrounded
    window as a bot signal (confirmed: Cloudflare's own error-code docs list
    600xxx as "Generic challenge failure — Bot behavior detected", and losing
    OS focus mid-challenge reproducibly triggers it). Real users can't click
    a widget in a window that isn't focused, so a synthetic click delivered
    to a backgrounded window is itself suspicious.

    BUT: in the default background/off-screen mode (the normal WebUI/queue
    path) this must never actually steal OS focus — bring_to_front() can
    yank foreground focus away from whatever the user is doing (e.g. kicking
    them out of a fullscreen game) just because a queued download hit a
    captcha in the background. Only when the user explicitly opted into a
    visible window (ANIWORLD_CAPTCHA_VISIBLE=1 / manual solving) are they
    already looking at and expecting to interact with this window, so
    focus-stealing there is intentional, not a surprise interruption.
    Off-screen mode instead relies on _stealth_launch_args() keeping the
    window at a plausible (not physically-impossible) off-screen position
    so Turnstile's screenX/screenY check doesn't fail regardless of focus."""
    if not _env_flag("ANIWORLD_CAPTCHA_VISIBLE"):
        return
    try:
        page.bring_to_front()
    except Exception:
        pass


# Turnstile-relevant hosts worth logging network responses for — keeps this
# noise-free instead of dumping every image/CSS/analytics request.
_DEBUG_LOG_HOST_MARKERS = (
    "cloudflare.com",
    "challenges.cloudflare.com",
    "cdn-cgi/challenge-platform",
    "turnstile",
)


def _attach_debug_listeners(page, logger) -> None:
    """Mirror the browser's console/network/page errors into our own logger.

    Reproduces what a human would see by opening DevTools — but doing that
    manually is exactly what triggers Cloudflare Turnstile error 600010
    (Turnstile has a debugger; statement that fires when DevTools is open and
    fails the challenge as a side effect, independent of any real bot
    signal). Hooking page.on(...) from Playwright gets the same information
    without a human ever opening DevTools, so a real failure can be told
    apart from that observer-effect artifact. Only active when
    ANIWORLD_CAPTCHA_DEBUG_LOG=1 — noisy, opt-in for troubleshooting."""
    if not _env_flag("ANIWORLD_CAPTCHA_DEBUG_LOG"):
        return

    def _on_console(msg):
        try:
            if msg.type in ("error", "warning"):
                logger.warning(f"[captcha browser console:{msg.type}] {msg.text}")
        except Exception:
            pass

    def _on_pageerror(err):
        try:
            logger.warning(f"[captcha browser pageerror] {err}")
        except Exception:
            pass

    def _on_response(resp):
        try:
            u = resp.url
            if resp.status >= 400 and any(m in u for m in _DEBUG_LOG_HOST_MARKERS):
                logger.warning(f"[captcha browser response] {resp.status} {u}")
        except Exception:
            pass

    def _on_requestfailed(req):
        try:
            if any(m in req.url for m in _DEBUG_LOG_HOST_MARKERS):
                failure = req.failure
                logger.warning(
                    f"[captcha browser requestfailed] {req.url} -> {failure}"
                )
        except Exception:
            pass

    try:
        page.on("console", _on_console)
        page.on("pageerror", _on_pageerror)
        page.on("response", _on_response)
        page.on("requestfailed", _on_requestfailed)
    except Exception:
        pass


def _captcha_timeout(default_seconds: int) -> int:
    """Captcha solve timeout in seconds; overridable via ANIWORLD_CAPTCHA_TIMEOUT
    (falls back to *default_seconds* when unset or invalid)."""
    import os

    raw = os.environ.get("ANIWORLD_CAPTCHA_TIMEOUT", "")
    try:
        v = int(raw)
        return v if v > 0 else default_seconds
    except (ValueError, TypeError):
        return default_seconds


def _install_stealth(context, ad_home=None, weiter_event=None) -> None:
    """Install ad + fingerprint defences on a patchright context: continuous
    overlay removal, optional WebGL spoof, and (when *ad_home* is given) the
    network ad-blocker."""
    if not _env_flag("ANIWORLD_CAPTCHA_NO_OVERLAY_REMOVAL"):
        try:
            context.add_init_script(_AD_OVERLAY_OBSERVER_JS)
        except Exception:
            pass
    if _webgl_spoof_enabled():
        try:
            context.add_init_script(_WEBGL_SPOOF_JS)
        except Exception:
            pass
    if ad_home and _network_adblock_enabled():
        _install_network_adblock(context, ad_home, weiter_event)


def _sync_session_user_agent(page) -> None:
    """Align GLOBAL_SESSION's User-Agent with the real browser UA.

    cf_clearance is bound to the UA that solved the challenge; if later HTTP
    requests use a different UA the cookie is rejected.  In Docker the browser is
    a Linux Chromium while the session UA defaults to a random Windows string —
    a guaranteed mismatch — so copy the browser UA onto the session.
    """
    if _env_flag("ANIWORLD_CAPTCHA_NO_UA_SYNC"):
        return
    try:
        ua = page.evaluate("() => navigator.userAgent")
    except Exception:
        return
    if ua and isinstance(ua, str):
        try:
            from ..config import GLOBAL_SESSION

            GLOBAL_SESSION.headers["User-Agent"] = ua
        except Exception:
            pass


class _BrowserHandle:
    """Wraps a patchright context (persistent or ephemeral) + its browser and
    the profile lock, so callers close everything with one call."""

    def __init__(self, context, browser, got_lock):
        self.context = context
        self._browser = browser
        self._got_lock = got_lock

    def close(self):
        try:
            self.context.close()
        except Exception:
            pass
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
        if self._got_lock:
            try:
                _PROFILE_LOCK.release()
            except Exception:
                pass


def _launch_browser_context(
    p, offscreen=False, ad_home=None, weiter_event=None
) -> "_BrowserHandle":
    """Launch a hardened patchright context.

    Prefers a persistent profile (stable fingerprint + warm cf_clearance, which
    raises the Turnstile trust score).  Only one solve may use the profile at a
    time; concurrent solves — or any failure to open it — fall back to an
    ephemeral context, so the worst case equals the previous behaviour.
    """
    args = _stealth_launch_args(offscreen)
    ctx_kwargs = _stealth_context_kwargs()
    browser = None
    context = None
    got_lock = False
    if _persistent_profile_enabled() and _PROFILE_LOCK.acquire(blocking=False):
        got_lock = True
        try:
            context = p.chromium.launch_persistent_context(
                _resolve_profile_dir(), headless=False, args=args, **ctx_kwargs
            )
        except Exception:
            context = None
            try:
                _PROFILE_LOCK.release()
            except Exception:
                pass
            got_lock = False
    if context is None:
        browser = p.chromium.launch(headless=False, args=args)
        context = browser.new_context(**ctx_kwargs)
    _install_stealth(context, ad_home=ad_home, weiter_event=weiter_event)
    return _BrowserHandle(context, browser, got_lock)


def _click_turnstile(page, logger=None) -> bool:
    """Locate the Cloudflare Turnstile iframe and click its checkbox.

    Uses human-like mouse movement (random offsets + step-based move) so that
    Turnstile does not flag the click as automated.

    Removes invisible full-page ad-overlay elements first so that the mouse
    events reach the Turnstile iframe and don't accidentally open an ad tab.

    Returns True if a click was performed.
    """
    if _env_flag("ANIWORLD_CAPTCHA_MANUAL"):
        # Manual mode: never synthesise a click.  Report success so the caller
        # stops auto-clicking and simply polls for the token that the user's own
        # click (CLI window / streamed WebUI) will produce.
        if logger:
            logger.debug("Captcha manual mode — auto-click skipped, waiting for user")
        return True

    def _looks_like_turnstile(u):
        u = (u or "").lower()
        return (
            "challenges.cloudflare.com" in u
            or "cdn-cgi/challenge-platform" in u
            or "turnstile" in u
            or "hcaptcha.com" in u
        )

    # Locate the Turnstile iframe ELEMENT.  It is frequently nested inside
    # another iframe (the serienstream.to modal / player-iframe), so a
    # top-level page.locator("iframe[...]") can't see it.  Walking page.frames
    # finds the challenge frame at any depth; frame.frame_element() returns the
    # hosting <iframe> whose bounding box is already mapped into top-level page
    # coords.
    iframe_el = None
    try:
        for fr in page.frames:
            if _looks_like_turnstile(fr.url):
                try:
                    el = fr.frame_element()
                except Exception:
                    el = None
                if el:
                    iframe_el = el
                    break
    except Exception:
        pass

    # Fallback: top-frame locator (covers the non-nested case).
    if iframe_el is None:
        for selector in (
            "iframe[src*='challenges.cloudflare.com']",
            "iframe[src*='turnstile']",
            "iframe[src*='cdn-cgi/challenge-platform']",
        ):
            try:
                loc = page.locator(selector).first
                loc.wait_for(state="visible", timeout=1500)
                iframe_el = loc.element_handle()
                if iframe_el:
                    break
            except Exception:
                continue

    if iframe_el is None:
        if logger:
            try:
                urls = [f.url for f in page.frames]
            except Exception:
                urls = []
            logger.warning(f"No Turnstile iframe found to click; frames={urls}")
        return False

    try:
        try:
            iframe_el.scroll_into_view_if_needed(timeout=1500)
        except Exception:
            pass

        # Let the widget settle, but accept any usable box.
        box = None
        for _ in range(8):
            b = iframe_el.bounding_box()
            if b and b["width"] > 0 and b["height"] > 0:
                box = b
                if b["width"] > 40:  # fully laid out — good to click
                    break
            page.wait_for_timeout(150)
        if not box:
            if logger:
                logger.warning("Turnstile iframe found but has no bounding box yet")
            return False

        _remove_ad_overlays(page)
        _focus_page(page)

        # Checkbox sits on the left of the widget, vertically centred.
        if box["width"] > 40:
            inset = min(30.0, box["width"] * 0.12)
        else:
            inset = box["width"] / 2
        x = box["x"] + inset + _random.uniform(-2, 2)
        y = box["y"] + box["height"] / 2 + _random.uniform(-2, 2)

        page.mouse.move(x, y, steps=_random.randint(8, 20))
        page.wait_for_timeout(_random.randint(80, 220))
        page.mouse.down()
        page.wait_for_timeout(_random.randint(40, 100))
        page.mouse.up()

        if logger:
            logger.warning(
                f"Turnstile checkbox clicked at ({int(x)},{int(y)}) "
                f"[box {int(box['width'])}x{int(box['height'])}]"
            )
        return True
    except Exception as e:
        if logger:
            logger.warning(f"Turnstile click failed: {e}")
        return False


def _is_turnstile_token_ready(page) -> bool:
    """Check whether the Turnstile hidden input already carries a token.

    Searches the main document *and* every sub-frame, because serienstream.to
    renders the Turnstile widget inside a modal that may live in a nested
    frame.
    """
    js = (
        "() => { const el = document.querySelector"
        "('input[name=\"cf-turnstile-response\"]');"
        " return !!(el && el.value && el.value.length > 20); }"
    )
    try:
        if page.evaluate(js):
            return True
        for fr in page.frames:
            try:
                if fr.evaluate(js):
                    return True
            except Exception:
                continue
        return False
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
    """Click the modal submit button with robust fallbacks for intercepted clicks.

    Tries a plain click, then a forced click after neutralizing known
    ad/overlay blockers, then a direct JS click as a last resort. Used instead
    of a bare ``page.locator(...).click()`` everywhere the Weiter/submit
    button is pressed, since serienstream.to occasionally layers an
    (invisible) ad element on top of it.
    """
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


# ---------------------------------------------------------------------------
# Second-widget support (reCAPTCHA / hCaptcha stacked below Turnstile)
# ---------------------------------------------------------------------------
# Some VOE modals ("Video wird vorbereitet...") stack a second checkbox
# captcha *underneath* the Cloudflare Turnstile widget in the same form.
# Turns out this second "I'm not a robot ☺" box is NOT real Google reCAPTCHA
# (the icon is a plain smiley, not the reCAPTCHA robot glyph, and there is no
# google.com/recaptcha iframe on the page at all) — it's VOE's own fake
# checkbox: a plain <input type="checkbox"> + label with client-side JS that
# blocks submit ("Please tick this box if you want to proceed.") until it's
# ticked. Only Turnstile was being auto-solved, so "Weiter" got clicked while
# this plain checkbox was still unticked. The helpers below detect *all*
# checkbox-style challenge widgets present on the page — both real iframe
# captchas (Turnstile/reCAPTCHA/hCaptcha) and this kind of plain in-page
# checkbox — click whichever ones aren't solved yet, and only report "ready"
# once every widget actually present has a token / is checked.

_HUMAN_CHECKBOX_KEYWORDS = ("robot", "roboter", "human", "mensch", "captcha", "bot")

# Scans every checkbox <input> on the page/frame for one whose label/parent
# text mentions "robot"/"human"/etc. Returns 'checked' | 'unchecked' | null.
_HUMAN_CHECKBOX_SCAN_JS = """
(kws) => {
  const boxes = Array.from(document.querySelectorAll('input[type="checkbox"]'));
  for (const cb of boxes) {
    if (cb.disabled) continue;
    let text = '';
    if (cb.id) {
      try {
        const lbl = document.querySelector(`label[for="${CSS.escape(cb.id)}"]`);
        if (lbl) text += ' ' + lbl.textContent;
      } catch (e) {}
    }
    const pl = cb.closest('label');
    if (pl) text += ' ' + pl.textContent;
    if (cb.parentElement) text += ' ' + cb.parentElement.textContent;
    text = text.toLowerCase();
    if (kws.some(k => text.includes(k))) {
      return cb.checked ? 'checked' : 'unchecked';
    }
  }
  return null;
}
"""

# Same scan, but marks the matching unchecked box with a data attribute so
# Playwright can locate + click it as a real element (native click, not a
# simulated mouse-move — it's a normal form control, not an iframe overlay).
_HUMAN_CHECKBOX_MARK_JS = """
(kws) => {
  const boxes = Array.from(document.querySelectorAll('input[type="checkbox"]'));
  for (const cb of boxes) {
    if (cb.checked || cb.disabled) continue;
    let text = '';
    if (cb.id) {
      try {
        const lbl = document.querySelector(`label[for="${CSS.escape(cb.id)}"]`);
        if (lbl) text += ' ' + lbl.textContent;
      } catch (e) {}
    }
    const pl = cb.closest('label');
    if (pl) text += ' ' + pl.textContent;
    if (cb.parentElement) text += ' ' + cb.parentElement.textContent;
    text = text.toLowerCase();
    if (kws.some(k => text.includes(k))) {
      cb.setAttribute('data-aw-human-cb', '1');
      return true;
    }
  }
  return false;
}
"""


def _human_checkbox_state(page):
    """Return 'checked' / 'unchecked' if a plain "I'm not a robot"-style
    checkbox is found anywhere on the page (main document or any frame),
    else None."""
    for ctx in [page] + list(page.frames):
        try:
            r = ctx.evaluate(_HUMAN_CHECKBOX_SCAN_JS, list(_HUMAN_CHECKBOX_KEYWORDS))
        except Exception:
            r = None
        if r:
            return r
    return None


def _click_human_checkbox(page, logger=None) -> bool:
    """Find and click a plain (non-iframe) "I'm not a robot"-style checkbox."""
    if _env_flag("ANIWORLD_CAPTCHA_MANUAL"):
        if logger:
            logger.debug("Captcha manual mode — auto-click skipped (checkbox)")
        return True
    for ctx in [page] + list(page.frames):
        try:
            found = ctx.evaluate(
                _HUMAN_CHECKBOX_MARK_JS, list(_HUMAN_CHECKBOX_KEYWORDS)
            )
        except Exception:
            found = False
        if not found:
            continue
        try:
            loc = ctx.locator('[data-aw-human-cb="1"]').first
            loc.wait_for(state="attached", timeout=1000)
            loc.scroll_into_view_if_needed(timeout=1500)
            _focus_page(page)
            loc.click(timeout=2000)
            if logger:
                logger.warning("Clicked plain 'not a robot' checkbox")
            return True
        except Exception as e:
            if logger:
                logger.warning(f"Human-checkbox click failed: {e}")
            return False
    return False


# ---------------------------------------------------------------------------
# ALTCHA support (proof-of-work widget, seen stacked next to Turnstile on
# some serienstream.to modals)
# ---------------------------------------------------------------------------
# ALTCHA (https://altcha.org) is not an iframe challenge and not a plain
# checkbox — it's a <altcha-widget> custom element that runs a client-side
# proof-of-work computation and exposes a small JS API: el.getState() reports
# 'unverified' | 'verifying' | 'verified' | 'error' | 'expired' | 'code', and
# el.verify() starts the computation. Driving it through simulated mouse
# clicks would mean reaching into its (often closed) Shadow DOM for whatever
# internal checkbox its 'checkbox'/'switch' display type renders — the
# documented .verify() method does exactly what that click would trigger, so
# we call it directly instead. Searches every frame, same as the other
# challenge kinds, since a modal can embed the widget in a sub-frame.

_ALTCHA_STATE_JS = """
() => {
  const el = document.querySelector('altcha-widget');
  if (!el) return null;
  // Preferred: the widget's JS API (works in normal browser contexts).
  try {
    if (typeof el.getState === 'function') return el.getState();
  } catch (e) {}
  // Fallback for automation contexts where the custom element's methods are
  // not visible to page.evaluate (seen with patchright: window.customElements
  // is null in the evaluate context even though the widget works fine in the
  // page's main world). The widget mirrors its state onto the inner .altcha
  // container's data-state attribute and, once solved, fills a hidden
  // <input name="altcha"> with the signed payload — plain DOM, always readable.
  try {
    const box = el.querySelector('.altcha');
    if (box) {
      const ds = box.getAttribute('data-state');
      if (ds) return ds;
    }
  } catch (e) {}
  try {
    const payload = document.querySelector('input[name="altcha"]');
    if (payload && payload.value && payload.value.length > 20) return 'verified';
  } catch (e) {}
  return 'unverified';
}
"""

_ALTCHA_VERIFY_JS = """
() => {
  const el = document.querySelector('altcha-widget');
  if (!el) return false;
  // Read current state via the JS API, falling back to the data-state
  // attribute (see _ALTCHA_STATE_JS for why the API can be unreachable).
  let state = null;
  try { if (typeof el.getState === 'function') state = el.getState(); } catch (e) {}
  if (!state) {
    try {
      const box = el.querySelector('.altcha');
      state = box ? box.getAttribute('data-state') : null;
    } catch (e) {}
  }
  // Already done or already computing — don't restart a running PoW.
  if (state === 'verified' || state === 'verifying') return true;
  // Preferred: the widget's own verify() method (normal browser contexts).
  try {
    if (typeof el.verify === 'function') {
      el.verify();
      return true;
    }
  } catch (e) {}
  // Fallback: click the widget's light-DOM checkbox. The click event reaches
  // the widget's change listener in the page's main world and starts the
  // proof-of-work exactly like a real user click.
  try {
    const cb = el.querySelector('input[type="checkbox"]');
    if (cb && !cb.checked && !cb.disabled) {
      cb.click();
      return true;
    }
  } catch (e) {}
  return false;
}
"""


def _altcha_widget_state(page):
    """Return the ALTCHA widget's state ('unverified'/'verifying'/'verified'/
    'error'/'expired'/'code'), or None if no <altcha-widget> is present on the
    page or in any frame."""
    for ctx in [page] + list(page.frames):
        try:
            r = ctx.evaluate(_ALTCHA_STATE_JS)
        except Exception:
            r = None
        if r:
            return r
    return None


def _trigger_altcha_widget(page, logger=None) -> bool:
    """Start (or confirm already-running) ALTCHA proof-of-work verification by
    calling the widget's own .verify() method, rather than trying to click
    through its Shadow-DOM internals."""
    if _env_flag("ANIWORLD_CAPTCHA_MANUAL"):
        if logger:
            logger.debug("Captcha manual mode — auto-verify skipped (altcha)")
        return True
    _focus_page(page)
    for ctx in [page] + list(page.frames):
        try:
            ok = ctx.evaluate(_ALTCHA_VERIFY_JS)
        except Exception:
            ok = False
        if ok:
            if logger:
                logger.warning("Triggered ALTCHA proof-of-work verification")
            return True
    if logger:
        logger.debug("No altcha-widget found to verify")
    return False


_CHALLENGE_IFRAME_SELECTORS = {
    "turnstile": (
        "iframe[src*='challenges.cloudflare.com']",
        "iframe[src*='turnstile']",
        "iframe[src*='cdn-cgi/challenge-platform']",
    ),
    "recaptcha": (
        "iframe[src*='google.com/recaptcha']",
        "iframe[src*='recaptcha.net']",
    ),
    "hcaptcha": ("iframe[src*='hcaptcha.com']",),
}

_TOKEN_READY_JS = {
    "turnstile": (
        "() => { const el = document.querySelector"
        "('input[name=\"cf-turnstile-response\"]');"
        " return !!(el && el.value && el.value.length > 20); }"
    ),
    "recaptcha": (
        "() => { const el = document.querySelector"
        "('#g-recaptcha-response, textarea[name=\"g-recaptcha-response\"]');"
        " return !!(el && el.value && el.value.length > 20); }"
    ),
    "hcaptcha": (
        "() => { const el = document.querySelector"
        "('textarea[name=\"h-captcha-response\"]');"
        " return !!(el && el.value && el.value.length > 20); }"
    ),
}


def _looks_like_challenge_iframe(u: str, kind: str) -> bool:
    u = (u or "").lower()
    if kind == "turnstile":
        return (
            "challenges.cloudflare.com" in u
            or "cdn-cgi/challenge-platform" in u
            or "turnstile" in u
        )
    if kind == "recaptcha":
        return "google.com/recaptcha" in u or "recaptcha.net" in u
    if kind == "hcaptcha":
        return "hcaptcha.com" in u
    return False


def _present_challenge_kinds(page) -> set:
    """Which challenge kinds currently need attention on the page: the iframe
    captchas ('turnstile' / 'recaptcha' / 'hcaptcha') plus 'checkbox' for a
    plain in-page "I'm not a robot" checkbox (VOE's fake-captcha pattern) plus
    'altcha' for a proof-of-work <altcha-widget>. A modal can show more than
    one at once (e.g. Turnstile + a plain checkbox stacked below it, or
    Turnstile + ALTCHA), so this returns a set."""
    kinds = set()
    try:
        for fr in page.frames:
            for kind in ("turnstile", "recaptcha", "hcaptcha"):
                if kind not in kinds and _looks_like_challenge_iframe(fr.url, kind):
                    kinds.add(kind)
    except Exception:
        pass
    if _human_checkbox_state(page) is not None:
        kinds.add("checkbox")
    if _altcha_widget_state(page) is not None:
        kinds.add("altcha")
    return kinds


def _is_challenge_token_ready(page, kind: str) -> bool:
    """Like _is_turnstile_token_ready(), generalised to reCAPTCHA/hCaptcha and
    to the plain 'checkbox' kind (ready == the box is ticked)."""
    if kind == "checkbox":
        return _human_checkbox_state(page) == "checked"
    if kind == "altcha":
        return _altcha_widget_state(page) == "verified"
    js = _TOKEN_READY_JS.get(kind)
    if not js:
        return False
    try:
        if page.evaluate(js):
            return True
        for fr in page.frames:
            try:
                if fr.evaluate(js):
                    return True
            except Exception:
                continue
        return False
    except Exception:
        return False


def _click_challenge_checkbox(page, kind: str, logger=None) -> bool:
    """Locate a checkbox-captcha iframe of *kind* and click it.

    Same human-like-mouse-move approach as _click_turnstile(), generalised so
    it also works for reCAPTCHA's / hCaptcha's checkbox iframe. The plain
    'checkbox' kind (no iframe involved) is delegated to
    _click_human_checkbox().
    """
    if kind == "checkbox":
        return _click_human_checkbox(page, logger)
    if kind == "altcha":
        return _trigger_altcha_widget(page, logger)

    if _env_flag("ANIWORLD_CAPTCHA_MANUAL"):
        if logger:
            logger.debug(f"Captcha manual mode — auto-click skipped ({kind})")
        return True

    iframe_el = None
    try:
        for fr in page.frames:
            if _looks_like_challenge_iframe(fr.url, kind):
                try:
                    el = fr.frame_element()
                except Exception:
                    el = None
                if el:
                    iframe_el = el
                    break
    except Exception:
        pass

    if iframe_el is None:
        for selector in _CHALLENGE_IFRAME_SELECTORS.get(kind, ()):
            try:
                loc = page.locator(selector).first
                loc.wait_for(state="visible", timeout=1500)
                iframe_el = loc.element_handle()
                if iframe_el:
                    break
            except Exception:
                continue

    if iframe_el is None:
        if logger:
            logger.debug(f"No {kind} iframe found to click")
        return False

    try:
        try:
            iframe_el.scroll_into_view_if_needed(timeout=1500)
        except Exception:
            pass

        box = None
        for _ in range(8):
            b = iframe_el.bounding_box()
            if b and b["width"] > 0 and b["height"] > 0:
                box = b
                if b["width"] > 40:
                    break
            page.wait_for_timeout(150)
        if not box:
            if logger:
                logger.warning(f"{kind} iframe found but has no bounding box yet")
            return False

        _remove_ad_overlays(page)
        _focus_page(page)

        if box["width"] > 40:
            inset = min(30.0, box["width"] * 0.12)
        else:
            inset = box["width"] / 2
        x = box["x"] + inset + _random.uniform(-2, 2)
        y = box["y"] + box["height"] / 2 + _random.uniform(-2, 2)

        page.mouse.move(x, y, steps=_random.randint(8, 20))
        page.wait_for_timeout(_random.randint(80, 220))
        page.mouse.down()
        page.wait_for_timeout(_random.randint(40, 100))
        page.mouse.up()

        if logger:
            logger.warning(
                f"{kind} checkbox clicked at (%d,%d) [box %dx%d]"
                % (int(x), int(y), int(box["width"]), int(box["height"]))
            )
        return True
    except Exception as e:
        if logger:
            logger.warning(f"{kind} click failed: {e}")
        return False


class _ChallengeSolver:
    """Drives *all* checkbox-captcha widgets present in a modal (not just
    Turnstile) across a polling loop.

    Clicks each unsolved widget (with an 8s grace period before re-clicking
    one that still has no token — a checkbox mid-validation resets if
    clicked again), and reports "ready" only once every widget currently on
    the page has a token, so the caller doesn't submit the form while a
    second, stacked captcha (e.g. a reCAPTCHA "I'm not a robot" box under
    Turnstile) is still unticked.
    """

    def __init__(self):
        self._clicked = {}
        self._last_click = {}
        self._first_seen = {}

    def ready_to_submit(self, page, logger=None) -> bool:
        kinds = _present_challenge_kinds(page)
        if not kinds:
            return False
        all_ready = True
        now = _time.time()
        for kind in kinds:
            if _is_challenge_token_ready(page, kind):
                continue
            all_ready = False
            if kind not in self._first_seen:
                self._first_seen[kind] = now
            if not self._clicked.get(kind):
                # Give a freshly-rendered widget 3-4s to finish settling
                # before the very first click. Clicking the instant its
                # iframe/element appears in the DOM lands before Cloudflare's
                # own JS has finished wiring up its listeners and risk
                # assessment for that widget — an interaction that arrives
                # "too early" reads as invalid/scripted and fails the
                # challenge outright, independent of how human the click
                # itself looks. Only the first click per kind waits; retries
                # after the 8s grace period below click immediately.
                if now - self._first_seen[kind] < _random.uniform(3.0, 4.0):
                    continue
                if _click_challenge_checkbox(page, kind, logger):
                    self._clicked[kind] = True
                    self._last_click[kind] = now
                    page.wait_for_timeout(_random.randint(1500, 2500))
            elif now - self._last_click.get(kind, 0) > 8:
                self._clicked[kind] = False
        return all_ready


def _is_captcha_page_dom(page) -> bool:
    """Lightweight DOM query to detect an active CF challenge — avoids full page.content() serialization."""
    try:
        return page.evaluate(
            """() => {
              const t = (document.title || '').toLowerCase();
              if (t.includes('just a moment') || t.includes('attention required')) return true;
              return !!document.querySelector(
                '#challenge-running, #cf-challenge-running, .cf-turnstile,'
                + ' [class*="challenge-"], [id*="challenge-"]'
              );
            }"""
        )
    except Exception:
        return True  # assume still on captcha page if evaluation fails


def is_captcha_page(html: str, status_code: int = 200) -> bool:
    """Detect Cloudflare challenge / CAPTCHA pages.

    Used by: aniworld.extractors.provider.voe, to decide when to fall back
    to solve_captcha().
    """
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
        # ALTCHA proof-of-work widget, sometimes stacked next to Turnstile
        "altcha-widget",
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
    - CLI mode: runs the same browser-assisted solver without Web UI streaming.

    After a successful solve all browser cookies are injected into GLOBAL_SESSION
    so subsequent requests work without re-solving.

    Returns the final URL (str) on success — for redirect-based captchas this is
    the provider URL captured from an iframe.  Returns None on timeout / error.
    Callers that don't need the URL can ignore the return value.

    Used by: aniworld.extractors.provider.voe, after is_captcha_page()
    detects a Cloudflare challenge on a VOE response.
    """
    queue_id = getattr(_local, "queue_id", None)
    if queue_id is not None:
        return _solve_captcha_interactive(url, queue_id)
    return _solve_captcha_cli(url)


def _solve_captcha_cli(url: str):
    """CLI mode captcha solver — injects browser cookies into the HTTP session."""
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

        logger.warning(f"CAPTCHA detected for {url} — opening browser solver")

        try:
            from ..autodeps import _ensure_xvfb

            _ensure_xvfb()
            with sync_playwright() as p:
                handle = _launch_browser_context(
                    p, offscreen=not _env_flag("ANIWORLD_CAPTCHA_VISIBLE")
                )
                context = handle.context
                page = context.new_page()
                _attach_debug_listeners(page, logger)
                page.goto(url, wait_until="domcontentloaded")
                _focus_page(page)
                _sync_session_user_agent(page)

                timeout = _captcha_timeout(300)  # default 5 minutes
                start = _time.time()
                solved = False
                final_url = url
                challenge_solver = _ChallengeSolver()

                while _time.time() - start < timeout:
                    # Standard Cloudflare full-page challenge
                    if any(c["name"] == "cf_clearance" for c in context.cookies()):
                        solved = True
                        break

                    # serienstream.to modal: form target="player-iframe" — after
                    # Weiter the VOE URL loads into that iframe. The modal HTML
                    # stays on the page, so is_captcha_page() would never
                    # become False. Instead poll the frame.
                    for frame in page.frames:
                        if frame.name == "player-iframe":
                            fu = frame.url
                            if fu and fu not in ("about:blank", "", url):
                                final_url = fu
                                solved = True
                                break
                    if solved:
                        break

                    # Check for classic full-page solve using lightweight DOM query
                    if not _is_captcha_page_dom(page):
                        final_url = page.url
                        solved = True
                        break

                    # Click any unsolved captcha checkbox (Turnstile, plus a
                    # second stacked reCAPTCHA/hCaptcha widget if present) and
                    # only submit once every widget on the page has a token.
                    if challenge_solver.ready_to_submit(page, logger):
                        try:
                            _focus_page(page)
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

                handle.close()

            with _captcha_state_lock:
                _captcha_state = None

            return final_url if solved else None

        except Exception:
            logger.exception("Error while solving CAPTCHA")
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
        """Return the most recent JPEG screenshot of the solving browser.

        Used by: aniworld.web.app (streams this to the Web UI).
        """
        with self._screenshot_lock:
            return self._screenshot

    def _store_screenshot(self, data: bytes):
        """Store the latest screenshot (called from the solve loop)."""
        with self._screenshot_lock:
            self._screenshot = data

    def enqueue_click(self, x: int, y: int):
        """Queue a user click (page coordinates) to be replayed on the page.

        Used by: aniworld.web.app, forwarding clicks the user makes on the
        streamed screenshot in the Web UI.
        """
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
            # Hardened context: persistent profile, realistic locale/timezone/
            # viewport, overlay + WebGL defences.  No network ad-block here — this
            # generic solver must let foreign provider iframes load.
            _handle = _launch_browser_context(
                p, offscreen=not _env_flag("ANIWORLD_CAPTCHA_VISIBLE")
            )
            context = _handle.context
            page = context.new_page()
            _attach_debug_listeners(page, logger)
            page.goto(url)
            _focus_page(page)
            _sync_session_user_agent(page)

            with _captcha_state_lock:
                _captcha_state = {
                    "url": url,
                    "started_at": _time.time(),
                    "solved": False,
                }

            solved = False
            challenge_solver = _ChallengeSolver()
            for _ in range(_captcha_timeout(300)):  # ~1s per iteration
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

                # Classic full-page solve (no modal) — lightweight DOM query
                if not _is_captcha_page_dom(page):
                    solved = True
                    break

                # Click any unsolved captcha checkbox (Turnstile, plus a
                # second stacked reCAPTCHA/hCaptcha widget if present) and
                # only submit once every widget on the page has a token.
                if challenge_solver.ready_to_submit(page, logger):
                    try:
                        _focus_page(page)
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
            _handle.close()

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

        current_netloc = urlparse(current_url).netloc.removeprefix("www.")
        for frame in page.frames:
            u = frame.url
            if not u or u in ("about:blank", current_url):
                continue
            nl = urlparse(u).netloc.removeprefix("www.")
            if nl and nl != current_netloc:
                return u
    except Exception:
        pass
    return current_url


def playwright_get_page_url(url: str) -> str:
    """Solve any CAPTCHA on *url*, then return the final resolved URL for it
    (following redirects) using the shared GLOBAL_SESSION."""
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


def playwright_get_iframe_url(url: str, timeout: int = 20) -> str:
    """Open `url` in a background browser and return the first external iframe URL.

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
            _handle = _launch_browser_context(p, offscreen=True)
            context = _handle.context
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

            _handle.close()
        return found
    except Exception as e:
        logger.error(f"Failed to capture iframe URL for {url}: {e}")
        raise


def playwright_get_hanime_manifest_token(url: str, timeout: int = 15) -> str:
    """Capture Hanime's official player-handshake token.

    Uses the same full Chromium context and challenge solver as the other
    browser-assisted extractors, including under Docker's Xvfb display.
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
    token = None
    timeout = max(1, int(timeout))

    try:
        from ..autodeps import _ensure_xvfb

        _ensure_xvfb()
        with sync_playwright() as p:
            _handle = _launch_browser_context(
                p, offscreen=not _env_flag("ANIWORLD_CAPTCHA_VISIBLE")
            )
            context = _handle.context
            _inject_session_cookies(context, url)
            page = context.new_page()
            _attach_debug_listeners(page, logger)
            _sync_session_user_agent(page)

            def _capture_handshake(response):
                nonlocal token
                if token or response.status != 200:
                    return
                try:
                    token = response.header_value("x-token")
                except Exception:
                    token = None

            page.on("response", _capture_handshake)
            logger.debug(f"Opening Hanime page for player handshake: {url}")
            try:
                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=timeout * 1000,
                )
            except Exception:
                # A slow secondary resource must not discard a handshake that
                # was already captured while the document was loading.
                if not token:
                    raise

            deadline = _time.monotonic() + _captcha_timeout(timeout)
            challenge_solver = _ChallengeSolver()
            while _time.monotonic() < deadline and not token:
                if _is_captcha_page_dom(page):
                    challenge_solver.ready_to_submit(page, logger)
                page.wait_for_timeout(100)

            _handle.close()

    except Exception as e:
        logger.exception("Failed to capture Hanime handshake")
        raise RuntimeError(f"Failed to capture Hanime handshake: {e}") from e

    if not token:
        raise TimeoutError(f"Hanime player handshake timed out after {timeout}s")
    return token


def playwright_get_hanime_stream_url(url: str) -> str:
    """Compatibility wrapper returning the best URL from the new handshake."""
    from ..extractors.provider.hanime_tv import (
        _parse_hanime_manifest_token,
        get_direct_link_from_hanime_tv,
    )

    token = playwright_get_hanime_manifest_token(url)
    slug = url.rstrip("/").split("/")[-1]
    api_data = {
        "hentai_video": {"slug": slug},
        "videos_manifest": _parse_hanime_manifest_token(token),
    }
    return get_direct_link_from_hanime_tv(api_data)


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
            _handle = _launch_browser_context(p, offscreen=True)
            context = _handle.context
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

            _handle.close()

        if final_url:
            logger.info("Captured cineby/vidking manifest URL")
        return final_url
    except Exception as e:
        logger.error(f"Failed to capture cineby stream URL: {e}")
        return None


def solve_sto_modal(
    episode_url: str,
    provider_name: str,
    language_label: str,
    redirect_url: str | None = None,
):
    """
    Navigate to the provider redirect URL (or fall back to the episode page),
    solve any Turnstile modal that appears, and return the player-iframe URL
    (e.g. voe.sx/e/...).  Works in CLI and WebUI mode.

    redirect_url — the provider-specific /r?t=... link; when supplied the
    browser navigates there directly so the Turnstile modal is triggered
    immediately without needing to click a provider button first.

    Returns the provider URL on success, None on timeout.

    Used by: aniworld.models.s_to.episode.SerienstreamEpisode, to resolve
    the player-iframe URL for an episode's chosen provider.
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
        from ..autodeps import _ensure_xvfb

        _ensure_xvfb()

        # The Turnstile captcha modal lives on the episode page itself. It is
        # shown by the in-page player JS when the provider's play button (the
        # element carrying the matching data-play-url) is clicked. Navigating
        # to the /r?t=... redirect URL directly bounces to the site's
        # homepage, because the token is consumed by the in-page player JS
        # and not by a top-level GET — so we open the episode page and click.
        start_url = episode_url

        with sync_playwright() as p:
            from urllib.parse import urlparse as _urlparse

            # Episode-page netloc — the "home" domain.  Any other netloc is
            # either an ad (blocked) or the provider result (allowed post-submit).
            sto_netloc = _urlparse(episode_url).netloc

            # Created before the context so the ad-blocker can read it:
            # navigations after submit are the provider result, not ads.
            _weiter_submitted = _threading.Event()  # set when submit is clicked

            # Hardened, ad-blocked context: persistent profile, realistic
            # locale/timezone/viewport, overlay + WebGL fingerprint defences.
            _handle = _launch_browser_context(
                p,
                offscreen=(queue_id is not None)
                and not _env_flag("ANIWORLD_CAPTCHA_VISIBLE"),
                ad_home=sto_netloc,
                weiter_event=_weiter_submitted,
            )
            context = _handle.context

            _inject_session_cookies(context, episode_url)
            page = context.new_page()
            _attach_debug_listeners(page, logger)

            with _captcha_state_lock:
                _captcha_state = {
                    "url": episode_url,
                    "started_at": _time.time(),
                    "solved": False,
                }

            # New-tab guard: the site has invisible full-page <a target="_blank">
            # ad overlays that open an ad tab on any click.
            #
            # Strategy: use *timing* rather than a domain whitelist.
            # - A tab that opens BEFORE the Weiter/submit button is clicked is
            #   an ad (overlay click during Turnstile mouse movement) → close it.
            # - A tab that opens AFTER Weiter is clicked is the provider result
            #   (the site opened it as the player) → keep it, regardless of domain.
            #   This correctly handles VOE alias domains like jeanprofessorcentral.com
            #   that we can't predict in advance.
            # - As a fallback, tabs on known provider domains are always kept even
            #   if they somehow open before Weiter.
            _ad_tab_lock = _threading.Lock()
            _provider_tab_urls: list = []

            def _on_new_page(new_pg):
                try:
                    new_pg.wait_for_load_state("commit", timeout=4000)
                    pu = new_pg.url
                    if not pu or pu in ("about:blank", ""):
                        return
                    from urllib.parse import urlparse as _up2

                    if _up2(pu).netloc == sto_netloc:
                        return  # still on the episode site — not a provider result
                    # Keep if: Weiter was already submitted, OR it's a known provider
                    if _weiter_submitted.is_set() or _is_known_provider_url(pu):
                        with _ad_tab_lock:
                            _provider_tab_urls.append(pu)
                    else:
                        # Ad tab from overlay click — close immediately, unless
                        # the ad-tab guard has been disabled.
                        if not _env_flag("ANIWORLD_CAPTCHA_NO_ADTAB_GUARD"):
                            try:
                                new_pg.close()
                            except Exception:
                                pass
                except Exception:
                    try:
                        new_pg.close()
                    except Exception:
                        pass

            context.on("page", _on_new_page)

            logger.debug(f"Opening episode page for modal solving: {start_url}")
            page.goto(start_url, wait_until="domcontentloaded")
            _focus_page(page)
            _sync_session_user_agent(page)

            # The captcha modal is triggered by clicking the provider's play
            # button on the episode page.  Derive the data-play-url value from
            # the redirect URL (it is exactly the path+query of /r?t=...) and
            # click the matching element via JS so invisible ad overlays can't
            # intercept the click.
            _remove_ad_overlays(page)

            play_path = None
            if redirect_url:
                _sp = _urlparse(redirect_url)
                play_path = _sp.path + (("?" + _sp.query) if _sp.query else "")

            clicked = False
            if play_path:
                try:
                    clicked = page.evaluate(
                        """(playPath) => {
                            const els = document.querySelectorAll('[data-play-url]');
                            for (const el of els) {
                                if (el.getAttribute('data-play-url') === playPath) {
                                    el.scrollIntoView({block: 'center'});
                                    el.click();
                                    return true;
                                }
                            }
                            return false;
                        }""",
                        play_path,
                    )
                except Exception as _e:
                    logger.debug(f"Provider-button click failed: {_e}")

            if clicked:
                logger.debug(
                    f"Clicked provider button ({play_path}) — waiting for Turnstile modal"
                )
                page.wait_for_timeout(1500)
                _remove_ad_overlays(page)
            else:
                # Fallback (legacy behaviour): the matching play button was not
                # found on the episode page — navigate to the redirect URL
                # directly and hope the modal appears there.
                logger.warning(
                    "Provider play button not found on episode page — "
                    "falling back to direct redirect navigation"
                )
                if redirect_url:
                    page.goto(redirect_url, wait_until="domcontentloaded")

            final_url = None
            weiter_clicked = False
            challenge_solver = _ChallengeSolver()
            start = _time.time()

            while _time.time() - start < _captcha_timeout(90):
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

                # ── Provider-URL detection (runs every iteration) ────────────
                # This must run before the Turnstile logic so that a successful
                # cookie-based redirect (no Turnstile at all) is captured
                # immediately without waiting for the timeout.

                # 1. player-iframe by name (classic site behaviour).
                #    IMPORTANT: the form POST to /r first loads an intermediate
                #    redirect page into the iframe before the final provider
                #    URL arrives.  We must skip any URL still on sto_netloc so
                #    we don't hand a serienstream.to URL to the VOE extractor.
                for frame in page.frames:
                    if frame.name == "player-iframe":
                        fu = frame.url
                        if (
                            fu
                            and fu != "about:blank"
                            and _urlparse(fu).netloc not in ("", sto_netloc)
                            and not _is_captcha_infra_url(fu)
                        ):
                            final_url = fu
                            break
                if final_url:
                    logger.debug(f"player-iframe URL found: {final_url}")
                    break

                # 2. Any iframe whose netloc differs from the episode site —
                #    only trusted AFTER the Turnstile modal was submitted.
                #    Before that, the episode page is full of third-party ad
                #    iframes whose netloc differs from it; without this gate
                #    the solver would grab an ad iframe, set final_url and
                #    close the browser immediately (captcha never solved).
                #    Known provider domains are always accepted as a safety net.
                if not final_url:
                    for frame in page.frames:
                        fu = frame.url
                        if not fu or fu in ("about:blank", "", start_url, episode_url):
                            continue
                        if _urlparse(fu).netloc in ("", sto_netloc):
                            continue
                        if _is_captcha_infra_url(fu):
                            continue  # Turnstile widget, not the provider
                        if weiter_clicked or _is_known_provider_url(fu):
                            final_url = fu
                            logger.warning(f"Foreign iframe URL found: {final_url}")
                            break
                if final_url:
                    break

                # 3. Main page navigated to a different domain (direct redirect).
                #    Only trusted after submit / for known providers, so an ad
                #    that hijacks the top frame can't end the solve early.
                if not final_url:
                    try:
                        pu = page.url
                        if (
                            pu
                            and _urlparse(pu).netloc not in ("", sto_netloc)
                            and not _is_captcha_infra_url(pu)
                        ) and (weiter_clicked or _is_known_provider_url(pu)):
                            final_url = pu
                            logger.warning(f"Page navigated to provider: {final_url}")
                    except Exception:
                        pass
                if final_url:
                    break

                # 4. New tab opened by the site — only accept known provider
                #    domains. Non-provider tabs (ads) are closed by the context
                #    handler above; here we just check if any provider tab was
                #    captured.
                with _ad_tab_lock:
                    for _u in reversed(_provider_tab_urls):
                        if not _is_captcha_infra_url(_u):
                            final_url = _u
                            break
                if final_url:
                    logger.debug(f"Provider tab URL found: {final_url}")
                    break

                # ── Captcha solving ──────────────────────────────────────────
                # Clicks every checkbox-style widget present in the modal —
                # not just Turnstile.  VOE's "Video wird vorbereitet..." modal
                # sometimes stacks a second widget (Google reCAPTCHA v2's
                # "I'm not a robot" checkbox) directly underneath Turnstile;
                # submitting while it's still unticked gets the form rejected
                # ("Please tick this box if you want to proceed."), so Weiter
                # is only clicked once *every* widget on the page has a token.
                if not weiter_clicked and challenge_solver.ready_to_submit(
                    page, logger
                ):
                    try:
                        # Remove ad overlays before clicking Weiter so the
                        # submit button click isn't hijacked by the overlay.
                        _remove_ad_overlays(page)
                        _focus_page(page)
                        # Signal BEFORE the click so the new-tab handler
                        # never races ahead of the flag being set.
                        _weiter_submitted.set()
                        if _click_submit_button(page, logger):
                            logger.warning("Submit clicked (all captcha tokens ready)")
                            weiter_clicked = True
                        page.wait_for_timeout(1200)
                    except Exception as e:
                        logger.warning(f"Submit button error: {e}")

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

            _handle.close()

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
