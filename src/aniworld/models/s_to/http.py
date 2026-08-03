"""Domain-fallback fetching for serienstream.

serienstream.to goes down from time to time, so requests are transparently
retried against the alternate domain (serienstream.cx) and, as a last resort,
the raw IP with a Host header. The first host that answers is remembered and
reused, and any serienstream URL is rewritten to it so pages, redirect links
and stream resolution all stay on the same working host.
"""

import warnings

from urllib3.exceptions import InsecureRequestWarning

try:
    from ...config import GLOBAL_SESSION, STO_DOMAINS, STO_HOST_RE, STO_IP
except ImportError:
    from aniworld.config import GLOBAL_SESSION, STO_DOMAINS, STO_HOST_RE, STO_IP

warnings.simplefilter("ignore", InsecureRequestWarning)

# Host list lives in config.py, add a mirror there
_HOST_RE = STO_HOST_RE

_active_idx = 0


def sto_host():
    """The currently preferred serienstream host."""
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
    session = session or GLOBAL_SESSION
    path = _path_of(url)
    last_err = None

    # Try the configured domains, starting at the last known-good one.
    for offset in range(len(STO_DOMAINS)):
        idx = (_active_idx + offset) % len(STO_DOMAINS)
        try:
            resp = session.get(
                f"https://{STO_DOMAINS[idx]}{path}", timeout=timeout, **kwargs
            )
            resp.raise_for_status()
            _active_idx = idx
            return resp
        except Exception as exc:
            last_err = exc

    # Last resort: the raw IP with a Host header.
    try:
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("Host", STO_DOMAINS[0])
        return session.get(
            f"https://{STO_IP}{path}",
            timeout=timeout,
            headers=headers,
            verify=False,
            **kwargs,
        )
    except Exception as exc:
        last_err = exc

    raise last_err or RuntimeError(f"all serienstream hosts failed for {url}")
