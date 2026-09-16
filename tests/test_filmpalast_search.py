from types import SimpleNamespace

import niquests
import pytest

from aniworld import search


def mock_page(monkeypatch, page):
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(text=page, raise_for_status=lambda: None)

    monkeypatch.setattr(search.GLOBAL_SESSION, "get", get)
    return calls


def test_genres_are_discovered_at_runtime(monkeypatch):
    calls = mock_page(
        monkeypatch,
        """<section id="genre"><ul>
        <li><a href="https://filmpalast.to/search/genre/Kom%C3%B6die"> Komödie </a></li>
        <li><a href="/search/genre/New">New label</a></li>
        <li><a href="/search/genre/New">Duplicate</a></li>
        </ul></section><a href="/search/alpha/A">A</a>""",
    )
    assert search.fetch_filmpalast_genres() == [
        {"name": "Komödie", "slug": "Komödie"},
        {"name": "New label", "slug": "New"},
    ]
    assert calls == ["https://filmpalast.to/"]


def test_genre_returns_cards_and_encodes_slug(monkeypatch):
    calls = mock_page(
        monkeypatch,
        """<article class="liste">
        <h2><a href="/stream/example" title="Example &amp; More">Example</a></h2>
        <img src="/poster.jpg" class="cover"></article>""",
    )
    assert search.query_filmpalast(genre="Komödie") == [
        {
            "title": "Example & More",
            "url": "https://filmpalast.to/stream/example",
            "poster_url": "https://filmpalast.to/poster.jpg",
        }
    ]
    assert calls == ["https://filmpalast.to/search/genre/Kom%C3%B6die"]


def test_new_genre_is_requested_without_keyword_fallback(monkeypatch):
    calls = mock_page(monkeypatch, "")
    assert search.query_filmpalast(genre="New 2026") == []
    assert calls == ["https://filmpalast.to/search/genre/New%202026"]


@pytest.mark.parametrize("discovery", [True, False])
def test_http_errors_are_not_hidden(monkeypatch, discovery):
    response = niquests.Response()
    response.status_code = 404
    monkeypatch.setattr(search.GLOBAL_SESSION, "get", lambda *a, **k: response)
    with pytest.raises(niquests.exceptions.HTTPError):
        if discovery:
            search.fetch_filmpalast_genres()
        else:
            search.query_filmpalast(genre="missing")


def test_keyword_search_keeps_cleaned_fallback(monkeypatch):
    calls = mock_page(monkeypatch, "")
    assert search.query_filmpalast("Example 2020") == []
    assert calls == [
        "https://filmpalast.to/search/title/Example%202020",
        "https://filmpalast.to/search/title/Example",
    ]


def test_keyword_and_genre_are_exclusive():
    with pytest.raises(ValueError, match="either a keyword"):
        search.query_filmpalast("example", genre="Horror")
