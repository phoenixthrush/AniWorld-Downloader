"""Shared machinery for the manual provider checks.

The live scripts are excluded from pytest collection. Offline tests cover
this helper, and Ruff checks the scripts without contacting providers.

One file per source site lives next to this one:

    tests/test_providers_aniworld.py       tests/test_providers_kinox.py
    tests/test_providers_serienstream.py   tests/test_providers_burningseries.py
    tests/test_providers_megakino.py
    tests/test_providers_filmo.py          tests/test_providers_moflix.py
    tests/test_providers_filmpalast.py     tests/test_providers_hanimetv.py
    tests/test_providers_mangafire.py
    tests/test_providers_hentaitv.py       tests/test_providers_animeidhentai.py
    tests/test_providers_hentaihaven.py

and one that checks the hosters on their own, independent of any site:

    tests/test_providers_hosters.py

Every one of them talks to the live internet, which is exactly why none of them
is a pytest test: they fail whenever a site changes its markup, blocks the
runner or goes down, and that must never turn a push red.
"""

import queue
import threading
import time

TIMEOUT = 45
PASS, FAIL, SKIP, NOIMPL = "PASS", "FAIL", "SKIP", "NOIMPL"

# Known embed URLs for checking a hoster on its own, used by
# test_providers_hosters.py. Nothing to do with random seeding: each is just a
# hardcoded page on that hoster so its extractor gets exercised at all.
#
# They go stale, because each points at one specific video that can be taken
# down at any time. A 404 here usually means the video is gone, not that the
# extractor broke. Replace it with any current embed URL from that hoster.
FALLBACK_EMBEDS = {
    "VOE": "https://voe.sx/e/on0cg79zre0c",
    "Doodstream": "https://playmogo.com/e/h9ifa0wgocdz",
    "Vidmoly": "https://vidmoly.net/embed-zquo82b8dm1k.html",
    "Vidoza": "https://videzz.net/embed-xneznizpludf.html",
    "Filemoon": "https://bysezejataos.com/d/1mzplk2ac3p1",
    "MegaKino": "https://watch.gxplayer.xyz/watch?v=153CJ76X",
}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
def extractors():
    """{provider key: {'direct': fn, 'preview': fn or None}} from the registry.

    Read from the registry rather than listed by hand, so a newly added hoster
    cannot be silently missed.
    """
    from aniworld.extractors import provider_functions

    found = {}
    for name, fn in provider_functions.items():
        if not name.startswith("get_direct_link_from_"):
            continue
        key = name[len("get_direct_link_from_") :]
        found[key] = {
            "direct": fn,
            "preview": provider_functions.get(f"get_preview_image_link_from_{key}"),
        }
    return found


def canonical(key):
    """The name the sites print, e.g. 'voe' -> 'VOE'. Falls back to the key."""
    from aniworld.models.common.provider_map import _ALIASES

    for _, name in _ALIASES:
        if name.lower() == key.lower():
            return name
    return key


def is_stub(fn):
    """Registered but unimplemented extractors raise NotImplementedError."""
    try:
        fn("")
    except NotImplementedError:
        return True
    except Exception:
        return False
    return False


# ---------------------------------------------------------------------------
# Running one call safely
# ---------------------------------------------------------------------------
def guarded(fn, *args):
    """Run `fn` with a wall clock limit, so one hung hoster cannot stall a run.

    Returns (value, exception). The exception itself is handed back, not a
    string, so callers can tell NotImplementedError from a real failure.
    """
    result = queue.Queue(maxsize=1)

    def call():
        try:
            result.put((fn(*args), None))
        except Exception as exc:
            result.put((None, exc))

    # A stuck request must not keep the manual-check process alive on exit.
    threading.Thread(target=call, daemon=True).start()
    try:
        return result.get(timeout=TIMEOUT)
    except queue.Empty:
        return None, TimeoutError(f"timed out after {TIMEOUT}s")


def describe(exc):
    return f"{type(exc).__name__}: {exc}"


def check(kind, fn, url):
    """Run one extractor. Not implemented is its own outcome, not a failure.

    An extractor raising NotImplementedError is saying it was never written.
    Counting that as broken buries the hosters that genuinely are.
    """
    if fn is None:
        return NOIMPL, "no extractor registered", 0.0
    started = time.monotonic()
    value, exc = guarded(fn, url)
    took = time.monotonic() - started
    if isinstance(exc, NotImplementedError):
        return NOIMPL, str(exc) or "not implemented yet", took
    if exc:
        return FAIL, describe(exc), took
    if not value:
        return FAIL, f"{kind} returned nothing", took
    return PASS, str(value)[:70], took


def line(status, label, detail, took=None):
    mark = {PASS: "PASS", FAIL: "FAIL", SKIP: "SKIP", NOIMPL: "TODO"}[status]
    timing = f" {took:5.1f}s" if took else " " * 7
    print(f"  {mark}{timing}  {label:<46} {detail}", flush=True)


# ---------------------------------------------------------------------------
# Walking a site down to real embed URLs
# ---------------------------------------------------------------------------
def first_episode(site_url):
    """An episode for `site_url`, resolving through series/season when needed."""
    from aniworld.providers import resolve_provider

    provider = resolve_provider(site_url)
    kwargs = {"url": site_url}
    if provider.name == "MegaKino":
        kwargs["selected_language"] = "German Dub"

    # Many sites are single page: the URL already is the episode.
    if provider.episode_cls:
        try:
            return provider.episode_cls(**kwargs)
        except Exception:
            pass

    if not provider.series_cls:
        raise ValueError(f"{provider.name}: no way to reach an episode")
    series = provider.series_cls(url=site_url)
    episodes = list(getattr(series, "episodes", []) or [])
    if episodes:
        return episodes[0]
    seasons = list(getattr(series, "seasons", []) or [])
    if not seasons:
        raise ValueError(f"{provider.name}: series exposed no seasons")
    episodes = list(getattr(seasons[0], "episodes", []) or [])
    if not episodes:
        raise ValueError(f"{provider.name}: season exposed no episodes")
    return episodes[0]


def hosters_of(episode):
    """[(language label, provider name)] an episode actually offers.

    Uses the app's own provider_map, so the labels are the ones the models
    accept ("German Dub", not "Japanese+German"). Building them by hand here
    produced labels the models rejected, which looked like a broken site when
    it was only this code being wrong.
    """
    from aniworld.web import media

    mapping = media.provider_map(getattr(episode, "provider_data", None))
    return [(label, name) for label, names in mapping.items() for name in names]


def embed_url(episode, language, provider_name):
    """Resolve the hoster redirect into the embed URL the extractor sees."""
    fresh = episode.__class__(
        url=episode.url,
        selected_language=language,
        selected_provider=provider_name,
    )
    return fresh.provider_url


# ---------------------------------------------------------------------------
# One site, end to end
# ---------------------------------------------------------------------------
def run_site(site_name, fetch_name, only=None):
    """Front page -> a current title -> episode -> every hoster it offers.

    The title is discovered live rather than hardcoded, so a title being taken
    down cannot quietly turn this check into a no-op.
    """
    from aniworld import search

    registry = extractors()
    stubs = {k for k, v in registry.items() if is_stub(v["direct"])}
    results = []

    print(f"\n=== {site_name} ===\n")
    fetch = getattr(search, fetch_name, None) or globals().get(fetch_name)
    if fetch is None:
        line(FAIL, site_name, f"no fetcher named {fetch_name}")
        return 1

    titles, exc = guarded(fetch)
    if exc or not titles:
        line(FAIL, f"{site_name} front page", describe(exc) if exc else "no titles")
        return 1

    site_url = titles[0].get("url") or titles[0].get("link")
    print(f"  discovered: {site_url}\n")

    episode, exc = guarded(first_episode, site_url)
    if exc:
        line(FAIL, f"{site_name} reach an episode", describe(exc))
        return 1

    pairs = hosters_of(episode)
    if only:
        pairs = [
            (language, name)
            for language, name in pairs
            if any(o in name.lower() for o in only)
        ]
    if not pairs:
        detail = (
            "episode offered no matching hosters"
            if only
            else "episode offered no hosters"
        )
        line(SKIP, site_name, detail)
        return report([SKIP])

    for language, provider_name in pairs:
        key = provider_name.lower()
        label = f"{language} {provider_name}"
        if key not in registry:
            line(SKIP, label, "no extractor for this hoster")
            continue
        if key in stubs:
            line(NOIMPL, label, "extractor registered but not implemented")
            results.append(NOIMPL)
            continue
        url, exc = guarded(embed_url, episode, language, provider_name)
        if exc:
            line(FAIL, label, f"embed: {describe(exc)}")
            results.append(FAIL)
            if site_name == "BurningSeries":
                from aniworld.models.burningseries.series import BurningSeriesVPNWarning

                if isinstance(exc, (BurningSeriesVPNWarning, TimeoutError)):
                    print(
                        "  Stopping BurningSeries check; remaining hosters were not "
                        "checked because the stream mirrors returned a VPN warning "
                        "or timed out.",
                        flush=True,
                    )
                    break
            continue

        status, detail, took = check("direct link", registry[key]["direct"], url)
        line(status, label, detail, took)
        results.append(status)

        status, detail, took = check("preview", registry[key]["preview"], url)
        line(status, f"{label} preview", detail, took)
        results.append(status)

    return report(results)


def run_stream_site(site_name, fetch_name, keyword=None):
    """For a site that owns its stream resolution instead of using a hoster.

    HanimeTV is its own extractor: the episode resolves a stream itself rather
    than pointing at VOE or Doodstream, so walking a hoster map would report
    "no hosters" and prove nothing.
    """
    from aniworld import search

    registry = extractors()
    results = []

    print(f"\n=== {site_name} ===\n")
    fetch = getattr(search, fetch_name, None) or globals().get(fetch_name)
    if fetch is None:
        line(FAIL, site_name, f"no fetcher named {fetch_name}")
        return 1
    titles, exc = guarded(lambda: fetch(keyword) if keyword is not None else fetch())
    if exc or not titles:
        source = "search" if keyword is not None else "front page"
        line(FAIL, f"{site_name} {source}", describe(exc) if exc else "no titles")
        return 1

    site_url = titles[0]["url"]
    print(f"  discovered: {site_url}\n")

    episode, exc = guarded(first_episode, site_url)
    if exc:
        line(FAIL, f"{site_name} reach an episode", describe(exc))
        return 1

    status, detail, took = check("stream", lambda _: episode.stream_url, site_url)
    line(status, f"{site_name} stream", detail, took)
    results.append(status)

    if site_name == "HanimeTV" and "hanime_tv" in registry:
        status, detail, took = check(
            "preview", registry["hanime_tv"]["preview"], site_url
        )
        line(status, f"{site_name} preview", detail, took)
        results.append(status)
    else:
        status, detail, took = check("poster", lambda _: episode.poster_url, site_url)
        line(status, f"{site_name} poster", detail, took)
        results.append(status)
    return report(results)


def run_image_site(site_name, fetch_name):
    """For a site whose download is images, not a video stream.

    MangaFire has no hoster at all, so checking it against the extractor
    registry would say nothing. What matters is that a title still resolves to
    a chapter and that chapter to real page image URLs.
    """
    from aniworld.providers import resolve_provider

    results = []
    print(f"\n=== {site_name} ===\n")

    titles, exc = guarded(globals()[fetch_name])
    if exc or not titles:
        line(FAIL, f"{site_name} sample title", describe(exc) if exc else "no titles")
        return 1

    for title in titles:
        url = title["url"]
        print(f"  discovered: {url}\n")

        provider = resolve_provider(url)
        series, exc = guarded(provider.series_cls, url)
        if exc:
            line(FAIL, f"{site_name} series", describe(exc))
            results.append(FAIL)
            continue

        chapters, exc = guarded(
            lambda s: list(
                getattr(s, "chapters", None) or getattr(s, "seasons", []) or []
            ),
            series,
        )
        if exc or not chapters:
            line(
                FAIL,
                f"{site_name} chapters",
                describe(exc) if exc else "series exposed no chapters",
            )
            results.append(FAIL)
            continue
        line(PASS, f"{site_name} chapters", f"{len(chapters)} found")
        results.append(PASS)

        pages, exc = guarded(lambda c: list(getattr(c, "pages", []) or []), chapters[0])
        if exc or not pages:
            line(FAIL, f"{site_name} pages", describe(exc) if exc else "no pages")
            results.append(FAIL)
            continue

        image = getattr(pages[0], "image_url", None) or getattr(pages[0], "url", None)
        if not image:
            line(FAIL, f"{site_name} page image", "page carried no image URL")
            results.append(FAIL)
            continue

        line(PASS, f"{site_name} pages", f"{len(pages)} pages, first {str(image)[:46]}")
        results.append(PASS)
    return report(results)


def run_hosters(only=None):
    """Every extractor on its own, against its hardcoded embed URL."""
    registry = extractors()
    results = []
    print("\n=== hosters, checked directly ===\n")

    for key in sorted(registry):
        name = canonical(key)
        if only and not any(o in key for o in only):
            continue
        if is_stub(registry[key]["direct"]):
            line(NOIMPL, name, "registered but not implemented")
            results.append(NOIMPL)
            continue
        url = FALLBACK_EMBEDS.get(name) or FALLBACK_EMBEDS.get(key)
        if not url:
            line(SKIP, name, "no embed URL here, covered by its site instead")
            results.append(SKIP)
            continue
        status, detail, took = check("direct link", registry[key]["direct"], url)
        line(status, name, detail, took)
        results.append(status)
        status, detail, took = check("preview", registry[key]["preview"], url)
        line(status, f"{name} preview", detail, took)
        results.append(status)
    return report(results)


def hanime_trending():
    """Hanime's trending feed, shaped like the other browse fetchers."""
    from aniworld.extractors.provider.hanime_tv import fetch_hanime_trending

    return [
        {"url": f"https://hanime.tv/videos/hentai/{hit['slug']}"}
        for hit in (fetch_hanime_trending() or [])
        if hit.get("slug")
    ]


def mangafire_sample():
    """Check Darling in the Franxx and Velvet Kiss chapter/page lookups."""
    return [
        {"url": "https://mangafire.to/title/zlwvm-darling-in-the-franxx"},
        {"url": "https://mangafire.to/title/z9w-velvet-kisss"},
    ]


def report(results):
    passed = results.count(PASS)
    failed = results.count(FAIL)
    skipped = results.count(SKIP)
    todo = results.count(NOIMPL)
    print("\n" + "=" * 72)
    print(
        f"  {passed} passed, {failed} failed, {skipped} skipped, {todo} not implemented"
    )
    print("=" * 72)
    return failed
