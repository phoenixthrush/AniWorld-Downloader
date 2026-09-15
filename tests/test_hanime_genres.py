from types import SimpleNamespace

import pytest

from aniworld.extractors.provider import hanime_tv


def test_genres_are_fetched_and_decoded(monkeypatch):
    calls = []

    def request(url):
        calls.append(url)
        return SimpleNamespace(
            text="""
            <a href="/browse/tags/fantasy">Fantasy</a>
            <a href="/browse/tags/new%20tag">New tag</a>
            <a href="/browse/tags/new tag">Duplicate</a>
            <a href="/tags/action%20%26%20comedy">Action &amp; comedy</a>
            <a href="/browse/trending">Trending</a>
        """
        )

    monkeypatch.setattr(hanime_tv, "_request_hanime", request)
    assert hanime_tv.fetch_hanime_genres() == ["fantasy", "new tag", "action & comedy"]
    assert calls == ["https://hanime.tv"]


def test_missing_tag_menu(monkeypatch):
    monkeypatch.setattr(
        hanime_tv, "_request_hanime", lambda url: SimpleNamespace(text="")
    )
    assert hanime_tv.fetch_hanime_genres() == []


def test_fetch_error_is_propagated(monkeypatch):
    def request(url):
        raise RuntimeError("Site unavailable")

    monkeypatch.setattr(hanime_tv, "_request_hanime", request)
    with pytest.raises(RuntimeError, match="Site unavailable"):
        hanime_tv.fetch_hanime_genres()


def test_genre_search_fetches_results(monkeypatch):
    calls = []

    def request(url):
        calls.append(url)
        return SimpleNamespace(
            text="""
            <a href="/videos/hentai/example-1"><img src="poster.jpg" alt="Example 1 thumbnail"></a>
            <a href="/videos/hentai/another-1"><img src="other.jpg" alt="Another 1 thumbnail"></a>
        """
        )

    monkeypatch.setattr(hanime_tv, "_request_hanime", request)
    results = hanime_tv.search_hanime(genre="new tag", limit=None)
    assert calls == ["https://hanime.tv/browse/tags/new%20tag"]
    assert [r["slug"] for r in results] == ["example-1", "another-1"]
    assert results[0]["name"] == "Example 1"
    assert results[0]["poster_url"] == "poster.jpg"
    assert len(hanime_tv.search_hanime(genre="new tag", limit=1)) == 1
    assert hanime_tv.search_hanime("ANOTHER", genre="new tag") == results[1:]


def test_genre_search_propagates_fetch_failure(monkeypatch):
    def request(url):
        raise RuntimeError("404 Not Found")

    monkeypatch.setattr(hanime_tv, "_request_hanime", request)
    with pytest.raises(RuntimeError, match="404"):
        hanime_tv.search_hanime(genre="missing")


@pytest.mark.parametrize(
    "sort",
    [
        None,
        "",
        "created_at_asc",
        "released_at_desc",
        "released_at_asc",
        "views_desc",
        "views_asc",
        "likes_desc",
        "name_asc",
        "name_desc",
    ],
)
def test_genre_sort_is_passed_to_site(monkeypatch, sort):
    calls = []

    def request(url):
        calls.append(url)
        return SimpleNamespace(text="")

    monkeypatch.setattr(hanime_tv, "_request_hanime", request)
    assert hanime_tv.search_hanime(genre="fantasy", sort=sort) == []
    suffix = f"?order={sort}" if sort else ""
    assert calls == ["https://hanime.tv/browse/tags/fantasy" + suffix]


def test_sort_requires_genre():
    with pytest.raises(ValueError, match="sorting requires a genre"):
        hanime_tv.search_hanime("example", sort="name_asc")
