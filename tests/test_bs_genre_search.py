import pytest

from aniworld import search
from aniworld.models.burningseries import series as bs


def group(name, *titles):
    links = "".join(f'<li><a href="serie/{t}">{t}</a></li>' for t in titles)
    return (
        f'<div class="genre"><span><strong>{name}</strong></span><ul>{links}</ul></div>'
    )


@pytest.fixture
def index(monkeypatch):
    titles = [f"Horror-{i:02}" for i in range(40)]
    html = group("Horror", *titles, titles[0]) + group("Science-Fiction", "Star-Trek")
    monkeypatch.setattr(search, "_bs_index_cache", html)
    monkeypatch.setattr(bs, "bs_current_base", lambda: "https://burningseries.cx")
    return titles


def test_genre_returns_all_matches_without_duplicates(index):
    results = search.query_burningseries(genre=" horror ")
    assert [r["title"] for r in results] == index
    assert results[0]["url"] == "https://burningseries.cx/serie/Horror-00"


def test_genre_and_keyword(index):
    assert search.query_burningseries("star", genre="Horror") == []
    assert (
        search.query_burningseries("star", genre="science-fiction")[0]["title"]
        == "Star-Trek"
    )


def test_keyword_search_still_limits_results(index):
    assert len(search.query_burningseries("horror")) == 30


def test_unavailable_genre(index):
    with pytest.raises(ValueError, match="genre not available"):
        search.query_burningseries(genre="missing")


def test_genres_come_from_index(monkeypatch):
    monkeypatch.setattr(
        search, "_bs_index_cache", group("New &amp; Unusual", "Example")
    )
    assert search.query_burningseries(genre="new & unusual")[0]["title"] == "Example"


def test_fetch_is_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(search, "_bs_index_cache", None)

    def fetch(path):
        calls.append(path)
        return group("Horror", "Example")

    monkeypatch.setattr(bs, "bs_get_with_fallback", fetch)
    search.query_burningseries(genre="Horror")
    search.query_burningseries("Example", genre="Horror")
    assert calls == ["/andere-serien"]


def test_genre_fetch_failure_is_not_hidden(monkeypatch):
    monkeypatch.setattr(search, "_bs_index_cache", None)

    def fetch(path):
        raise RuntimeError("Site unavailable")

    monkeypatch.setattr(bs, "bs_get_with_fallback", fetch)
    with pytest.raises(RuntimeError, match="Site unavailable"):
        search.query_burningseries(genre="Horror")
