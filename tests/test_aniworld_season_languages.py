"""AniWorld season views read language flags from the season page rows."""

from types import SimpleNamespace

import pytest

from aniworld.models import AniworldSeason
from aniworld.web.views import api_media

BASE = "https://aniworld.to/anime/stream/example"


def row(path, *flags):
    images = "".join(
        f'<img class="flag" src="/public/img/{flag}.svg">' for flag in flags
    )
    return f"""
        <tr data-episode-id="1" itemprop="episode" itemscope="" itemtype="http://schema.org/Episode">
          <td><meta itemprop="episodeNumber" content="1"><a itemprop="url" href="{path}"> Folge </a></td>
          <td class="editFunctions"><a href="{path}">{images}</a></td>
        </tr>"""


def test_each_row_keeps_its_own_languages():
    season = AniworldSeason(f"{BASE}/staffel-1")
    season._AniworldSeason__html = (
        row(
            "/anime/stream/example/staffel-1/episode-1",
            "german",
            "japanese-german",
            "japanese-english",
        )
        + row("/anime/stream/example/staffel-1/episode-2", "japanese-german")
        + row(
            "/anime/stream/example/staffel-1/episode-3",
            "japanese-english",
            "japanese-german",
        )
    )
    assert season.episode_languages == {
        f"{BASE}/staffel-1/episode-1": ("German Dub", "German Sub", "English Sub"),
        f"{BASE}/staffel-1/episode-2": ("German Sub",),
        f"{BASE}/staffel-1/episode-3": ("German Sub", "English Sub"),
    }


def test_movie_rows_are_keyed_by_their_film_url():
    season = AniworldSeason(f"{BASE}/filme")
    season._AniworldSeason__html = row("/anime/stream/example/filme/film-1", "german")
    assert season.episode_languages == {f"{BASE}/filme/film-1": ("German Dub",)}


class Episode:
    def __init__(self, url, number):
        self.url = url
        self.episode_number = number
        self.season = SimpleNamespace(season_number=1)

    @property
    def provider_data(self):
        raise AssertionError("an episode page must not be fetched")


@pytest.fixture
def season_view(monkeypatch):
    def view(episodes, languages):
        season = SimpleNamespace(episodes=episodes, episode_languages=languages)
        provider = SimpleNamespace(name="AniWorld", season_cls=lambda **kwargs: season)
        monkeypatch.setattr(api_media, "_resolve_series", lambda *args: None)
        return api_media._season_episodes(provider, f"{BASE}/staffel-1", BASE)

    return view


def test_the_season_view_uses_row_languages_without_episode_requests(season_view):
    episodes = [Episode(f"{BASE}/staffel-1/episode-{n}", n) for n in (1, 2)]
    rows = season_view(
        episodes,
        {
            f"{BASE}/staffel-1/episode-1": ("German Dub", "German Sub"),
            f"{BASE}/staffel-1/episode-2": ("German Sub",),
        },
    )
    assert [r["available_languages"] for r in rows] == [
        ["German Dub", "German Sub"],
        ["German Sub"],
    ]


def test_an_episode_missing_from_the_rows_is_still_looked_up(season_view, monkeypatch):
    episode = Episode(f"{BASE}/staffel-1/episode-1", 1)
    monkeypatch.setattr(type(episode), "provider_data", property(lambda self: "page"))
    monkeypatch.setattr(api_media.media, "language_labels", lambda data: ["German Sub"])
    rows = season_view([episode], {})
    assert rows[0]["available_languages"] == ["German Sub"]
