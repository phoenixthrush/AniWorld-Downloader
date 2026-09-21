from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import niquests
import pytest

from aniworld.models.mangafire_to import series


@pytest.fixture
def api(monkeypatch):
    calls = []
    pages = []

    def get(url, **kwargs):
        calls.append(url)
        if url == series.FILTER_OPTIONS_API:
            data = {"data": {"genres": [{"id": 987, "name": "New Genre"}]}}
        else:
            data = pages.pop(0)
        return SimpleNamespace(json=lambda: data)

    monkeypatch.setattr(series, "_get", get)
    return calls, pages


def test_current_genres_are_fetched(api):
    calls, _ = api
    assert series.fetch_mangafire_genres() == [{"id": 987, "name": "New Genre"}]
    assert calls == [series.FILTER_OPTIONS_API]


@pytest.mark.parametrize("genre", ["new genre", 987, "987"])
def test_genre_keyword_sort_and_limit(api, genre):
    calls, pages = api
    pages.append({"items": [{"id": n} for n in range(3)], "meta": {"hasNext": True}})
    assert series.search_series(
        "some title", genre=genre, sort="score:desc", limit=2
    ) == [{"id": 0}, {"id": 1}]
    params = parse_qs(urlparse(calls[1]).query)
    assert params == {
        "keyword": ["some title"],
        "genres_in[]": ["987"],
        "order[score]": ["desc"],
        "page": ["1"],
        "limit": ["2"],
    }
    assert len(calls) == 2


def test_pagination_preserves_filters_and_deduplicates(api):
    calls, pages = api
    pages.extend(
        [
            {"items": [{"id": 1}, {"id": 2}], "meta": {"hasNext": True}},
            {"items": [{"id": 2}, {"id": 3}], "meta": {"hasNext": False}},
        ]
    )
    assert series.search_series(genre=987, limit=None) == [
        {"id": 1},
        {"id": 2},
        {"id": 3},
    ]
    for page, url in enumerate(calls[1:], 1):
        params = parse_qs(urlparse(url).query)
        assert params["genres_in[]"] == ["987"]
        assert params["page"] == [str(page)]


def test_repeated_page_stops(api):
    calls, pages = api
    pages.extend([{"items": [{"id": 1}], "meta": {"hasNext": True}}] * 2)
    assert series.search_series(limit=None) == [{"id": 1}]
    assert len(calls) == 2


def test_keyword_search_default_stays_twenty(api):
    calls, pages = api
    pages.append({"items": [{"id": n} for n in range(20)], "meta": {"hasNext": True}})
    assert len(series.search_series("example")) == 20
    assert len(calls) == 1
    assert parse_qs(urlparse(calls[0]).query)["limit"] == ["20"]


def test_unknown_genre_fails_against_runtime_list(api):
    calls, _ = api
    with pytest.raises(ValueError, match="genre not available"):
        series.search_series(genre="missing")
    assert calls == [series.FILTER_OPTIONS_API]


@pytest.mark.parametrize("limit", [-1, True, 1.5, "10"])
def test_invalid_limit_skips_requests(api, limit):
    calls, _ = api
    with pytest.raises(ValueError, match="limit must"):
        series.search_series(genre="Action", limit=limit)
    assert calls == []


def test_zero_limit_skips_requests(api):
    calls, _ = api
    assert series.search_series(genre="Action", limit=0) == []
    assert calls == []


def test_http_errors_propagate(monkeypatch):
    def get(*args, **kwargs):
        response = niquests.Response()
        response.status_code = 404
        response.raise_for_status()

    monkeypatch.setattr(series, "_get", get)
    with pytest.raises(niquests.exceptions.HTTPError):
        series.search_series(genre="Action")
