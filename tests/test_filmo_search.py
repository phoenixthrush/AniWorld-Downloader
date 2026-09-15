from types import SimpleNamespace

import niquests
import pytest

from aniworld import search


def cards(*slugs):
    return "".join(
        f'<a href="/movies/{slug}"><img src="/poster.jpg">'
        f'<h3 class="movie-poster-grid-card__title">{slug}</h3></a>'
        for slug in slugs
    )


def mock_pages(monkeypatch, *pages):
    pages = iter(pages)
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(text=next(pages), raise_for_status=lambda: None)

    monkeypatch.setattr(search.GLOBAL_SESSION, "get", get)
    return calls


def test_browse_filters_follow_pagination(monkeypatch):
    titles = [f"movie-{n}" for n in range(42)]
    next_url = "/movies?genre_id=11&amp;sort=release_desc&amp;page=2"
    calls = mock_pages(
        monkeypatch,
        cards(*titles) + f'<a href="{next_url}" rel="next">Next</a>',
        cards(titles[-1], "last"),
    )
    results = search.query_filmo(
        genre_id=11,
        sort="release_desc",
        year=2020,
        runtime_min=0,
        runtime_max=120,
        country="DE",
    )
    assert [r["title"] for r in results] == [*titles, "last"]
    assert calls[0][0] == "https://filmo.to/movies"
    assert calls[0][1]["params"] == {
        "genre_id": 11,
        "sort": "release_desc",
        "year": 2020,
        "runtime_min": 0,
        "runtime_max": 120,
        "country": "DE",
    }
    assert calls[1][0] == "https://filmo.to/movies?genre_id=11&sort=release_desc&page=2"
    assert calls[1][1]["params"] is None


def test_empty_filters_use_site_defaults(monkeypatch):
    calls = mock_pages(monkeypatch, "")
    assert (
        search.query_filmo(genre_id="", year=None, runtime_min="", country="", sort="")
        == []
    )
    assert calls[0][1]["params"] == {}


def test_keyword_search_preserves_limit(monkeypatch):
    calls = mock_pages(monkeypatch, cards(*(f"movie-{n}" for n in range(40))))
    assert len(search.query_filmo("resident evil")) == 30
    assert calls[0][0] == "https://filmo.to/search?q=resident+evil"


def test_keyword_and_filters_cannot_be_combined():
    with pytest.raises(ValueError, match="either a keyword"):
        search.query_filmo("alien", genre_id=11)


def test_browse_http_errors_propagate(monkeypatch):
    response = niquests.Response()
    response.status_code = 404
    monkeypatch.setattr(search.GLOBAL_SESSION, "get", lambda *args, **kwargs: response)
    with pytest.raises(niquests.exceptions.HTTPError):
        search.query_filmo(genre_id=999)
