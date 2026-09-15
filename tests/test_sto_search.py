from types import SimpleNamespace

import niquests
import pytest

from aniworld.models.s_to import http
from aniworld.search import query_s_to


def search_page(*slugs, next_url=None):
    cards = "".join(
        f'<div class="card"><a href="/serie/{slug}"></a>'
        f'<h6 class="show-title">{slug}</h6></div>'
        for slug in slugs
    )
    pager = f'<a href="{next_url}" rel="next">Weiter</a>' if next_url else ""
    return f'<div data-group="shows">{cards}{pager}</div>'


def mock_pages(monkeypatch, *pages):
    responses = iter(pages)
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(text=next(responses), raise_for_status=lambda: None)

    monkeypatch.setattr(http, "sto_get", get)
    return calls


def test_full_search_follows_pages_and_deduplicates(monkeypatch):
    slugs = [f"series-{n}" for n in range(24)]
    calls = mock_pages(
        monkeypatch,
        search_page(*slugs, next_url="/suche?term=from&amp;page=2"),
        search_page(slugs[-1], "from", next_url="/suche?term=from&amp;page=3"),
        search_page("last-series"),
    )
    results = query_s_to("from")
    assert [r["link"] for r in results] == [
        f"/serie/{slug}" for slug in [*slugs, "from", "last-series"]
    ]
    assert calls == [
        ("https://serienstream.to/suche", {"params": {"term": "from"}}),
        ("https://serienstream.to/suche?term=from&page=2", {"params": None}),
        ("https://serienstream.to/suche?term=from&page=3", {"params": None}),
    ]


def test_only_series_group_is_parsed(monkeypatch):
    page = search_page("ignored").replace('data-group="shows"', 'data-group="all"')
    page += """<div data-group="shows"><div class="card">
        <a href="/serie/from" class="show-cover"><picture>
        <img alt="Poster" src="poster.jpg"></picture></a>
        <div class="card-body"><h6 class="show-title mb-0">
        From &amp; <em>Beyond</em></h6></div></div></div>"""
    page += search_page("episode").replace(
        'data-group="shows"', 'data-group="episodes"'
    )
    mock_pages(monkeypatch, page)
    assert query_s_to("from") == [{"title": "From & Beyond", "link": "/serie/from"}]


def test_empty_search(monkeypatch):
    mock_pages(monkeypatch, search_page())
    assert query_s_to("missing") == []


def test_repeated_page_stops(monkeypatch):
    page = search_page("from", next_url="/suche?term=from&amp;page=2")
    calls = mock_pages(monkeypatch, page, page)
    assert query_s_to("from") == [{"title": "from", "link": "/serie/from"}]
    assert len(calls) == 2


def test_genre_filters_and_pagination(monkeypatch):
    page = """<a href="/serie/from" class="show-card"><img src="poster.jpg"></a>
    <h6 class="text-truncate" title="From"><a href="/serie/from">From</a></h6>
    <a rel="next" href="/genre/horror?fsk=0&amp;prod_start=2000&amp;prod_end=2026&amp;sort=ratings_desc&amp;page=2">Next</a>"""
    calls = mock_pages(monkeypatch, page, page.replace("/serie/from", "/serie/other"))
    results = query_s_to(
        genre="horror", fsk=0, prod_start=2000, prod_end=2026, sort="ratings_desc"
    )
    assert [r["link"] for r in results] == ["/serie/from", "/serie/other"]
    assert calls[0] == (
        "https://serienstream.to/genre/horror",
        {
            "params": {
                "fsk": 0,
                "prod_start": 2000,
                "prod_end": 2026,
                "sort": "ratings_desc",
            }
        },
    )
    assert (
        calls[1][0]
        == "https://serienstream.to/genre/horror?fsk=0&prod_start=2000&prod_end=2026&sort=ratings_desc&page=2"
    )


def test_genre_empty_filters(monkeypatch):
    calls = mock_pages(monkeypatch, "")
    assert query_s_to(genre="science-fiction", prod_start="", prod_end="") == []
    assert calls == [("https://serienstream.to/genre/science-fiction", {"params": {}})]


def test_genre_filters_require_genre():
    with pytest.raises(ValueError, match="require a genre"):
        query_s_to("from", fsk=18)
    with pytest.raises(ValueError, match="either a keyword or a genre"):
        query_s_to("from", genre="horror")


def test_genre_is_not_restricted_to_known_tags(monkeypatch):
    calls = mock_pages(monkeypatch, "")
    assert query_s_to(genre="new-genre") == []
    assert calls == [("https://serienstream.to/genre/new-genre", {"params": {}})]


@pytest.mark.parametrize("raised_by_fetch", [False, True])
def test_unavailable_genre_raises_http_error(monkeypatch, raised_by_fetch):
    response = niquests.Response()
    response.status_code = 404
    response.url = "https://serienstream.to/genre/missing"

    def get(*args, **kwargs):
        if raised_by_fetch:
            response.raise_for_status()
        return response

    monkeypatch.setattr(http, "sto_get", get)
    with pytest.raises(niquests.exceptions.HTTPError) as error:
        query_s_to(genre="missing")
    assert error.value.response.status_code == 404


@pytest.mark.parametrize("value", [None, ""])
def test_optional_genre_filters(monkeypatch, value):
    calls = mock_pages(monkeypatch, "")
    assert (
        query_s_to(
            genre="horror", fsk=value, prod_start=value, prod_end=value, sort=value
        )
        == []
    )
    assert calls == [("https://serienstream.to/genre/horror", {"params": {}})]
