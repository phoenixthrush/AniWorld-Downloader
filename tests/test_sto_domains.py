from urllib.parse import urljoin

import pytest

from aniworld.config import STO_ALL_HOSTS, STO_IP
from aniworld.models.s_to import SerienstreamSeason, SerienstreamSeries

BASES = [""] + [
    f"{scheme}://{prefix}{host}"
    for host in STO_ALL_HOSTS
    for scheme in ("http", "https")
    for prefix in ("", "www.")
]


@pytest.mark.parametrize("base", BASES)
def test_season_and_metadata_extraction(base):
    series = SerienstreamSeries("https://serienstream.to/serie/from")
    season_url = f"{base}/serie/from/staffel-1"
    series._SerienstreamSeries__html = (
        f'<a href="{season_url}">Season 1</a>'
        f'<a class="small text-muted" href="{base}/jahr/2022">2022</a>'
        f'<img data-src="{base}/media/images/channel/desktop/from.jpg">'
    )
    assert series.season_count == 1
    assert [season.url for season in series.seasons] == [
        urljoin(series.url, season_url)
    ]
    assert series.release_year == "2022"
    assert series.poster_url == f"http://{STO_IP}/media/images/channel/desktop/from.jpg"


@pytest.mark.parametrize("base", BASES)
def test_episode_extraction(base):
    series = SerienstreamSeries("https://serienstream.to/serie/from")
    season = SerienstreamSeason(f"{series.url}/staffel-1", series=series)
    episode_url = f"{base}/serie/from/staffel-1/episode-1"
    season._SerienstreamSeason__html = f'<a href="{episode_url}">Episode 1</a>'
    assert season.episode_count == 1
    assert [episode.url for episode in season.episodes] == [
        urljoin(season.url, episode_url)
    ]


def test_unrelated_domains_are_not_extracted():
    series = SerienstreamSeries("https://serienstream.to/serie/from")
    season = SerienstreamSeason(f"{series.url}/staffel-1", series=series)
    series._SerienstreamSeries__html = (
        '<a href="https://serienstream.to.example.org/serie/from/staffel-1">Wrong</a>'
    )
    season._SerienstreamSeason__html = (
        '<a href="https://example.org/serie/from/staffel-1/episode-1">Wrong</a>'
    )
    assert series.seasons == []
    assert series.season_count == 0
    assert season.episodes == []
    assert season.episode_count == 0


def test_episode_languages_are_read_from_season_rows():
    series = SerienstreamSeries("https://serienstream.to/serie/from")
    season = SerienstreamSeason(f"{series.url}/staffel-1", series=series)
    season._SerienstreamSeason__html = """
        <tr class="episode-row">
          <td><a href="/serie/from/staffel-1/episode-1">Episode 1</a></td>
          <td><i class="svg-flag-german"></i><i class="svg-flag-english"></i></td>
        </tr>
        <tr class="episode-row active">
          <td><a href="/serie/from/staffel-1/episode-2">Episode 2</a></td>
          <td><i class="svg-flag-german"></i></td>
        </tr>
    """

    assert season.episode_languages == {
        1: ("German Dub", "English Dub"),
        2: ("German Dub",),
    }
