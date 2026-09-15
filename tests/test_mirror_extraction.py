import pytest

from aniworld.models.burningseries import series as bs
from aniworld.models.filmpalast_to import FilmPalastEpisode


@pytest.mark.parametrize(
    "base",
    ["", "/"]
    + [
        f"{scheme}://{prefix}{host}/"
        for host in bs._BS_HOSTS
        for scheme in ("http", "https")
        for prefix in ("", "www.")
    ],
)
def test_burningseries_mirror_links(monkeypatch, base):
    show = bs.BurningSeriesSeries("https://bs.cine.to/serie/from")
    show._BurningSeriesSeries__html = f'<a href="{base}serie/from/2/de">2</a>'
    assert [season.season_number for season in show.seasons] == [2]
    page = (
        '<table class="episodes"><tr><td>'
        f'<a href="{base}serie/from/2/1-title/de">Episode</a>'
        "</td></tr></table>"
    )
    monkeypatch.setattr(bs, "bs_get_with_fallback", lambda *args: page)
    assert show.seasons[0]._episode_rows("de") == [
        ("serie/from/2/1-title/de", 2, "1-title")
    ]


@pytest.mark.parametrize(
    "base",
    [
        "",
        "/",
        "https://filmpalast.to/",
        "http://filmpalast.to/",
        "https://www.filmpalast.example/",
    ],
)
def test_filmpalast_genre_links(base):
    movie = FilmPalastEpisode("https://filmpalast.to/stream/example")
    movie._FilmPalastEpisode__html = (
        f'<a href="{base}search/genre/action" class="genre">Action</a>'
        f'<a href="{base}search/genre/drama">Drama</a>'
        '<a href="https://unrelated.example/search/genre/horror">Horror</a>'
    )
    assert movie.genres == ["Action", "Drama"]


def test_burningseries_rejects_unrelated_absolute_links(monkeypatch):
    show = bs.BurningSeriesSeries("https://bs.cine.to/serie/from")
    show._BurningSeriesSeries__html = (
        '<a href="https://example.org/serie/from/9/de">9</a>'
    )
    assert [season.season_number for season in show.seasons] == [1]
    monkeypatch.setattr(
        bs,
        "bs_get_with_fallback",
        lambda *args: (
            '<table class="episodes"><td><a href="https://example.org/serie/from/1/1-title/de">Wrong</a></td></table>'
        ),
    )
    assert show.seasons[0]._episode_rows("de") == []
