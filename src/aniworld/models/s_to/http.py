"""Domain-fallback fetching for serienstream.

serienstream.to goes down from time to time, so requests are transparently
retried against the alternate domain (serienstream.cx) and, as a last resort,
the raw IP with a Host header. The first host that answers is remembered and
reused, and any serienstream URL is rewritten to it so pages, redirect links
and stream resolution all stay on the same working host.
"""

import threading
import warnings
from urllib.parse import urlsplit, urlunsplit

from niquests import Session
from urllib3.exceptions import InsecureRequestWarning

try:
    from ...config import GLOBAL_SESSION, STO_DOMAINS, STO_HOST_RE, STO_IP
except ImportError:
    from aniworld.config import GLOBAL_SESSION, STO_DOMAINS, STO_HOST_RE, STO_IP

warnings.simplefilter("ignore", InsecureRequestWarning)

# Host list lives in config.py, add a mirror there
_HOST_RE = STO_HOST_RE

_active_idx = 0
_state_lock = threading.Lock()
_thread_local = threading.local()


class SerienstreamResponseError(RuntimeError):
    """A serienstream host answered, but did not return usable page HTML."""


def _global_headers():
    """Copy browser-compatible headers without optional Brotli encoding."""
    headers = dict(GLOBAL_SESSION.headers)
    headers["Accept-Encoding"] = "gzip, deflate"
    return headers


def _sync_global_state(session):
    """Refresh state that the captcha solver may have changed globally."""
    try:
        session.headers.update(_global_headers())
    except Exception:
        pass
    try:
        session.cookies.update(GLOBAL_SESSION.cookies)
    except Exception:
        pass


def _safe_url(url):
    """Keep diagnostics useful without leaking signed redirect query strings."""
    try:
        parsed = urlsplit(str(url or ""))
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    except Exception:
        return "serienstream request"


def _new_session():
    """Build a niquests session owned by the current thread."""
    # Brotli support is optional. Asking only for encodings every supported
    # installation can decode keeps ``response.text`` deterministic.
    session = Session(
        resolver=["doh+cloudflare://"],
        disable_http3=True,
        multiplexed=False,
        headers=_global_headers(),
    )
    session.verify = GLOBAL_SESSION.verify
    _sync_global_state(session)
    return session


def _session():
    """Return the current thread's session and copy in fresh captcha cookies."""
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = _new_session()
        _thread_local.session = session
    else:
        _sync_global_state(session)
    return session


def reset_sto_session():
    """Discard only the calling thread's HTTP state after a bad response."""
    session = getattr(_thread_local, "session", None)
    if session is not None:
        try:
            session.close()
        except Exception:
            pass
        delattr(_thread_local, "session")


def response_text(response, url):
    """Return validated response text or raise a descriptive error."""
    text = getattr(response, "text", None)
    if not isinstance(text, str):
        raise SerienstreamResponseError(
            f"SerienStream returned an invalid response body for {_safe_url(url)}"
        )
    return text


def _validate_response(response, requested_url):
    response.raise_for_status()
    final_url = str(getattr(response, "url", "") or requested_url)

    # /r can redirect to the selected video host. Its body belongs to another
    # provider and callers only need the final URL, so do not validate it here.
    if not _HOST_RE.match(final_url):
        return response

    text = response_text(response, requested_url)
    lower = text[:20000].lower()
    if (
        "<title>just a moment" in lower
        or "<title>attention required" in lower
        or "cdn-cgi/challenge-platform" in lower
        or "cf_chl_" in lower
    ):
        raise SerienstreamResponseError(
            f"SerienStream returned a challenge page for {_safe_url(requested_url)}"
        )
    return response


def sto_host():
    """The currently preferred serienstream host."""
    with _state_lock:
        return STO_DOMAINS[_active_idx]


def sto_rewrite(url):
    """Rewrite any serienstream URL onto the active host."""
    if not url:
        return url
    return _HOST_RE.sub(r"\1" + sto_host(), url, count=1)


def _path_of(url):
    return _HOST_RE.sub("", url, count=1) or "/"


def sto_get(url, session=None, timeout=10, **kwargs):
    """GET a serienstream URL, falling back across domains then the IP.

    Returns the response of the first host that answers; remembers it.
    """
    global _active_idx
    path = _path_of(url)
    last_err = None

    with _state_lock:
        start_idx = _active_idx

    def fetch(target, request_kwargs, *, extra_headers=None):
        nonlocal last_err
        for attempt in range(2):
            current = session or _session()
            options = dict(request_kwargs)
            headers = dict(options.pop("headers", {}) or {})
            headers.setdefault("Accept-Encoding", "gzip, deflate")
            if extra_headers:
                headers.update(extra_headers)
            try:
                response = current.get(
                    target,
                    timeout=timeout,
                    headers=headers,
                    **options,
                )
                return _validate_response(response, target)
            except Exception as exc:
                last_err = exc
                if session is None and attempt == 0:
                    reset_sto_session()
                    continue
                break
        return None

    # Try the configured domains, starting at the last known-good one.
    for offset in range(len(STO_DOMAINS)):
        idx = (start_idx + offset) % len(STO_DOMAINS)
        response = fetch(f"https://{STO_DOMAINS[idx]}{path}", kwargs)
        if response is not None:
            with _state_lock:
                _active_idx = idx
            return response

    # Last resort: the raw IP with a Host header.
    ip_kwargs = dict(kwargs)
    ip_kwargs["verify"] = False
    response = fetch(
        f"https://{STO_IP}{path}",
        ip_kwargs,
        extra_headers={"Host": STO_DOMAINS[0]},
    )
    if response is not None:
        return response

    raise last_err or RuntimeError(f"all serienstream hosts failed for {url}")
