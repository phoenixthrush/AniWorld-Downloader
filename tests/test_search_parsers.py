"""HTML parsing, run against saved pages instead of the live site.

The fixtures in tests/fixtures are trimmed copies of real aniworld.to markup.
Parsing them offline keeps CI green when the site changes; if the layout moves,
these still pass and only the app notices, which is the intended split.
"""

from pathlib import Path

import pytest

from aniworld import search

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def genre_list_page(monkeypatch):
    monkeypatch.setattr(
        search, "_fetch_homepage", lambda: fixture("aniworld_genre_list.html")
    )


@pytest.fixture
def genre_page(monkeypatch):
    """Serve the saved genre page for any slug and page number."""
    calls = []

    class Response:
        text = fixture("aniworld_genre_page.html")

        def raise_for_status(self):
            return None

    def get(url, *args, **kwargs):
        calls.append(url)
        return Response()

    monkeypatch.setattr(search.GLOBAL_SESSION, "get", get)
    return calls


# ---------------------------------------------------------------------------
# The genre list
# ---------------------------------------------------------------------------
def test_every_genre_is_read_off_the_homepage(genre_list_page):
    genres = search.fetch_genres()
    assert len(genres) == 34
    assert genres[0] == {"name": "Abenteuer", "slug": "abenteuer"}


def test_genre_names_are_unescaped(genre_list_page):
    names = [genre["name"] for genre in search.fetch_genres()]
    assert "Übermäßige Gewaltdarstellung" in names
    assert not any("&" in name for name in names)


def test_slugs_are_url_safe(genre_list_page):
    for genre in search.fetch_genres():
        assert "/" not in genre["slug"]
        assert " " not in genre["slug"]


def test_umlauts_map_to_transliterated_slugs(genre_list_page):
    by_name = {genre["name"]: genre["slug"] for genre in search.fetch_genres()}
    assert by_name["Komödie"] == "komoedie"
    assert by_name["Actionkomödie"] == "actionkomoedie"


def test_a_homepage_that_cannot_be_fetched_falls_back(monkeypatch):
    monkeypatch.setattr(search, "_fetch_homepage", lambda: None)
    genres = search.fetch_genres()
    assert len(genres) == len(search.GENRE_FALLBACK)
    assert genres[0]["slug"] == "abenteuer"


def test_a_homepage_without_the_list_falls_back(monkeypatch):
    monkeypatch.setattr(search, "_fetch_homepage", lambda: "<html>redesigned</html>")
    assert len(search.fetch_genres()) == len(search.GENRE_FALLBACK)


def test_the_fallback_list_is_self_consistent():
    names = [name for name, _ in search.GENRE_FALLBACK]
    slugs = [slug for _, slug in search.GENRE_FALLBACK]
    assert len(set(slugs)) == len(slugs), "no duplicate slugs"
    assert all(names) and all(slugs)


def test_the_fallback_matches_the_live_list(genre_list_page):
    parsed = [(genre["name"], genre["slug"]) for genre in search.fetch_genres()]
    assert parsed == list(search.GENRE_FALLBACK)


# ---------------------------------------------------------------------------
# A genre page
# ---------------------------------------------------------------------------
def test_the_cards_are_parsed(genre_page):
    result = search.fetch_genre_animes("mecha")
    assert len(result["results"]) == 4
    first = result["results"][0]
    assert first["title"] == "BULLBUSTER"
    assert first["url"] == "https://aniworld.to/anime/stream/bullbuster"
    assert first["genre"] == "Mecha"
    assert first["poster_url"].startswith("https://aniworld.to/public/img/cover/")


def test_titles_are_unescaped(genre_page):
    titles = [item["title"] for item in search.fetch_genre_animes("mecha")["results"]]
    assert "I'm the Evil Lord of an Intergalactic Empire!" in titles
    assert not any("&#" in title for title in titles)


def test_page_one_has_no_suffix(genre_page):
    search.fetch_genre_animes("mecha")
    assert genre_page == ["https://aniworld.to/genre/mecha"]


def test_later_pages_are_numbered(genre_page):
    search.fetch_genre_animes("mecha", page=3)
    assert genre_page == ["https://aniworld.to/genre/mecha/3"]


def test_a_slug_is_url_encoded(genre_page):
    search.fetch_genre_animes("boys-love")
    assert genre_page == ["https://aniworld.to/genre/boys-love"]


def test_more_pages_are_detected_from_the_pager(genre_page):
    assert search.fetch_genre_animes("mecha", page=1)["has_more"] is True
    assert search.fetch_genre_animes("mecha", page=2)["has_more"] is True


def test_the_last_page_reports_no_more(genre_page):
    """The pager stops linking forward once there is nothing after it."""
    assert search.fetch_genre_animes("mecha", page=4)["has_more"] is False


def test_a_failed_fetch_returns_nothing(monkeypatch):
    def explode(url, *args, **kwargs):
        raise RuntimeError("503")

    monkeypatch.setattr(search.GLOBAL_SESSION, "get", explode)
    assert search.fetch_genre_animes("mecha") is None


def test_a_page_without_cards_is_empty_not_an_error(monkeypatch):
    class Response:
        text = "<html><body>nothing here</body></html>"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(search.GLOBAL_SESSION, "get", lambda *a, **k: Response())
    result = search.fetch_genre_animes("mecha")
    assert result == {"results": [], "has_more": False}


def test_no_duplicate_urls_on_a_page(genre_page):
    urls = [item["url"] for item in search.fetch_genre_animes("mecha")["results"]]
    assert len(set(urls)) == len(urls)


def test_every_card_has_the_fields_the_ui_needs(genre_page):
    for item in search.fetch_genre_animes("mecha")["results"]:
        assert set(item) == {"title", "url", "genre", "poster_url"}
        assert item["title"] and item["url"]
