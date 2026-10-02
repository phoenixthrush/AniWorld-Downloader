"""Common public imports and search options work across site backends."""

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

import aniworld
from aniworld import models, search
from aniworld.extractors.provider import hanime_tv
from aniworld.models.mangafire_to import series as mangafire
from aniworld.web import sitesearch


def test_every_public_model_is_available_at_the_package_root():
    for name in models.__all__:
        assert getattr(aniworld, name) is getattr(models, name)


def test_genre_discovery_uses_name_and_slug_for_every_site(monkeypatch):
    monkeypatch.setattr(hanime_tv, "fetch_hanime_genres", lambda: ["New Tag"])
    monkeypatch.setattr(
        mangafire, "fetch_mangafire_genres", lambda: [{"id": 987, "name": "New Tag"}]
    )
    assert sitesearch.genres("htv") == [{"name": "New Tag", "slug": "New Tag"}]
    assert sitesearch.genres("mangafire") == [
        {"id": 987, "name": "New Tag", "slug": "987"}
    ]


def test_aniworld_genre_query_follows_pages_and_stops_at_limit(monkeypatch):
    calls = []

    def fetch(slug, page=1):
        calls.append((slug, page))
        return {"results": [{"title": str(page)}], "has_more": True}

    monkeypatch.setattr(search, "fetch_genre_animes", fetch)
    assert search.query_aniworld(genre="action", limit=2) == [
        {"title": "1"},
        {"title": "2"},
    ]
    assert calls == [("action", 1), ("action", 2)]


def test_mangafire_common_query_preserves_filters(monkeypatch):
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(
            json=lambda: {"items": [{"id": 1}], "meta": {"hasNext": False}}
        )

    monkeypatch.setattr(mangafire, "_get", get)
    monkeypatch.setattr(
        mangafire, "fetch_mangafire_genres", lambda: [{"id": 987, "name": "New Tag"}]
    )
    assert search.query_mangafire(
        "dragon", genre="New Tag", sort="score:desc", limit=1
    ) == [{"id": 1}]
    params = parse_qs(urlparse(calls[0]).query)
    assert params["genres_in[]"] == ["987"]
    assert params["keyword"] == ["dragon"]
    assert params["order[score]"] == ["desc"]


def test_filmo_common_genre_argument_uses_its_numeric_filter(monkeypatch):
    calls = []

    def get(url, **kwargs):
        calls.append(kwargs["params"])
        return SimpleNamespace(text="", raise_for_status=lambda: None)

    monkeypatch.setattr(search.GLOBAL_SESSION, "get", get)
    assert search.query_filmo(genre="11") == []
    assert calls == [{"genre_id": "11"}]
    with pytest.raises(ValueError, match="same Filmo genre"):
        search.query_filmo(genre=11, genre_id=12)


@pytest.fixture
def moflix_api(monkeypatch):
    calls = []

    def fetch(endpoint):
        calls.append(endpoint)
        return {
            "genres": ["Action", "Komödie"],
            "titles": [
                {"id": n, "name": f"Title {n}", "poster": "/poster.jpg"}
                for n in range(3)
            ],
        }

    monkeypatch.setattr(search, "_moflix_json", fetch)
    return calls


def test_moflix_genres_and_results_share_the_web_api(moflix_api):
    assert sitesearch.genres("moflix") == [
        {"name": name, "slug": name} for name in ("Action", "Komödie")
    ]
    results, more = sitesearch.genre_results("moflix", "Komödie", 2)
    assert [item["title"] for item in results] == ["Title 0", "Title 1"]
    assert more
    assert results[0]["url"] == "https://moflix-stream.xyz/titles/0"
    assert results[0]["poster"] == "https://moflix-stream.xyz/poster.jpg"
    assert parse_qs(urlparse(moflix_api[-1]).query)["genres"] == ["Komödie"]


def test_moflix_does_not_combine_keyword_and_genre(moflix_api):
    with pytest.raises(ValueError, match="either a keyword"):
        search.query_moflix("silo", genre="Action")
    assert moflix_api == []
