from unittest.mock import Mock

import pytest

from aniworld.models.burningseries import series as bs
from aniworld.models.filmpalast_to import FilmPalastEpisode


@pytest.mark.parametrize("warning_at_redirect", [False, True])
def test_burningseries_vpn_warning_does_not_launch_browser(
    monkeypatch, warning_at_redirect
):
    from aniworld.playwright import captcha

    warning = (
        "<style>" + "x" * 7000 + "</style>"
        "<h3>Burning Series Streams via VPN abrufbar!</h3>"
    )

    def fetch(url, referer):
        if warning_at_redirect and "/stream/" not in url:
            return "<script>window.open('/stream/123')</script>", url
        return warning, url

    browser = Mock(side_effect=AssertionError("warning pages must not open a browser"))
    monkeypatch.setattr(captcha, "playwright_get_iframe_url", browser)
    monkeypatch.setattr(bs, "_bs_curl_get", fetch)
    monkeypatch.setattr(bs.time, "sleep", lambda seconds: None)
    with pytest.raises(bs.BurningSeriesVPNWarning, match="VPN warning page"):
        bs._resolve_hoster_link(
            "serie/example/1/1-example/de/VOE", "https://bs.cine.to/"
        )
    browser.assert_not_called()


def test_burningseries_tries_other_mirror_after_vpn_warning(monkeypatch):
    calls = []

    def fetch(url, referer):
        calls.append(url)
        if url.startswith(bs._STREAM_DOMAINS[0]):
            return "<h3>Burning Series via VPN!</h3>", url
        if "/stream/" in url:
            return "", "https://voe.sx/e/example"
        return "<script>window.open('/stream/123')</script>", url

    monkeypatch.setattr(bs, "_bs_curl_get", fetch)
    monkeypatch.setattr(bs.time, "sleep", lambda seconds: None)
    assert (
        bs._resolve_hoster_link(
            "serie/example/1/1-example/de/VOE", "https://bs.cine.to/"
        )
        == "https://voe.sx/e/example"
    )
    assert len(calls) == 3


def test_burningseries_warning_detection_ignores_scripts_and_styles():
    assert not bs._is_vpn_warning(
        "<script>const ad = 'Burning Series VPN';</script>"
        "<style>/* Burning Series VPN */</style><h3>Episode player</h3>"
    )


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
