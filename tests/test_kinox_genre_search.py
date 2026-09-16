from types import SimpleNamespace

import niquests
import pytest

from aniworld import search
from aniworld.models.kinox import series


def test_top_100_preserves_ranking_and_uses_configured_domain(monkeypatch):
    calls = []
    monkeypatch.setattr(series, "KINOX_DOMAIN", "kinox.example")
    rows = [
        f'<tr><td class="Title"><a href="/Stream/movie-{n}.html">Movie {n}</a></td></tr>'
        for n in range(100)
    ]

    def get(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(
            text="<table>" + "".join(rows + rows[:1]) + "</table>",
            raise_for_status=lambda: None,
        )

    monkeypatch.setattr(search.GLOBAL_SESSION, "get", get)
    results = search.query_kinox(genre="Sci-Fi")
    assert calls == ["https://kinox.example/Genre/Sci-Fi/Popular"]
    assert [r["title"] for r in results] == [f"Movie {n}" for n in range(100)]
    assert results[0]["url"] == "https://kinox.example/Stream/movie-0.html"


def test_unknown_genre_is_requested_and_http_error_propagates(monkeypatch):
    calls = []
    response = niquests.Response()
    response.status_code = 404

    def get(url, **kwargs):
        calls.append(url)
        return response

    monkeypatch.setattr(search.GLOBAL_SESSION, "get", get)
    with pytest.raises(niquests.exceptions.HTTPError):
        search.query_kinox(genre="New Genre")
    assert calls[0].endswith("/Genre/New%20Genre/Popular")


def test_keyword_and_genre_are_exclusive():
    with pytest.raises(ValueError, match="either a keyword"):
        search.query_kinox("example", genre="Action")


def test_ajax_top_100_uses_runtime_genre_and_default_headers(monkeypatch):
    import json

    page = '<input id="ListParams" value="{&quot;fGenre&quot;:&quot;new-id&quot;,&quot;Length&quot;:60,&quot;iSortCol_0&quot;:6,&quot;sSortDir_0&quot;:&quot;desc&quot;}">'
    calls = []
    monkeypatch.setattr(series, "KINOX_DOMAIN", "kinox.to")
    monkeypatch.setattr(
        search.GLOBAL_SESSION,
        "get",
        lambda *a, **k: SimpleNamespace(text=page, raise_for_status=lambda: None),
    )

    def post(url, **kwargs):
        calls.append((url, kwargs))
        content = "".join(
            f'<div class="Opt leftOpt Headlne"><a title="Movie {n}" href="/Stream/movie-{n}.html"><h1>Movie {n}</h1></a></div>'
            for n in range(100)
        )
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"Total": 500, "Content": content},
        )

    monkeypatch.setattr(search.GLOBAL_SESSION, "post", post)
    results = search.query_kinox(genre="Action")
    assert [r["title"] for r in results] == [f"Movie {n}" for n in range(100)]
    url, request = calls[0]
    assert url == "https://kinox.to/aGET/List/"
    assert json.loads(request["data"]["additional"]) == {
        "fGenre": "new-id",
        "Length": 100,
        "iSortCol_0": 6,
        "sSortDir_0": "desc",
    }
    assert request["headers"]["User-Agent"] == search.DEFAULT_USER_AGENT
    assert request["headers"]["Referer"] == "https://kinox.to/Genre/Action/Popular"
    assert "Cookie" not in request["headers"]
