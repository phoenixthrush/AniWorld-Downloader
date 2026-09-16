from types import SimpleNamespace

import niquests
import pytest

from aniworld import search
from aniworld.models.megakino import series


@pytest.fixture
def page_session(monkeypatch):
    calls = []
    pages = []
    monkeypatch.setattr(series, "get_megakino_domain", lambda: "megakino.example")

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url, **kwargs):
            calls.append(url)
            if url.endswith("?yg=token"):
                return SimpleNamespace(text="")
            return SimpleNamespace(text=pages.pop(0), raise_for_status=lambda: None)

    monkeypatch.setattr(search.niquests, "Session", Session)
    return calls, pages


def test_genres_use_runtime_names_and_slugs(page_session):
    calls, pages = page_session
    pages.append("""<div class="side-block__title">Genres</div>
        <ul class="side-block__content side-block__menu">
        <li><a href="/multfilm/">Animation</a><span>321</span></li>
        <li><a href="/new-category/">New &amp; Changed</a></li>
        <li><a href="/multfilm/">Duplicate</a></li></ul>
        <a href="/unrelated/">Outside</a>""")
    assert search.fetch_megakino_genres() == [
        {"name": "Animation", "slug": "multfilm"},
        {"name": "New & Changed", "slug": "new-category"},
    ]
    assert calls == [
        "https://megakino.example/index.php?yg=token",
        "https://megakino.example/",
    ]


def test_genre_results_use_current_domain(page_session):
    calls, pages = page_session
    pages.append("""<a class="poster" href="/films/123-example.html">
        <img src="/poster.jpg" alt="Example">
        <h3 class="poster__title">Example &amp; More</h3></a>""")
    results = search.query_megakino(genre="new genre")
    assert calls[-1] == "https://megakino.example/new%20genre/"
    assert results[0]["title"] == "Example & More"
    assert results[0]["url"] == "https://megakino.example/films/123-example.html"


def test_token_redirect_is_retried(page_session):
    calls, pages = page_session
    pages.extend(["location.replace('/index.php?yg=token')", ""])
    assert search.query_megakino(genre="horror") == []
    assert calls[-2:] == ["https://megakino.example/horror/"] * 2


def test_request_errors_propagate(monkeypatch):
    def fetch(path):
        response = niquests.Response()
        response.status_code = 404
        response.raise_for_status()

    monkeypatch.setattr(search, "_fetch_megakino_page", fetch)
    with pytest.raises(niquests.exceptions.HTTPError):
        search.query_megakino(genre="missing")


def test_keyword_and_genre_are_exclusive():
    with pytest.raises(ValueError, match="either a keyword"):
        search.query_megakino("example", genre="horror")
