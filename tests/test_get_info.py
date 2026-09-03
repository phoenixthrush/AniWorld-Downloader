from aniworld import providers
from aniworld.config import Audio, Subtitles


class FakeEpisode:
    def __init__(self, url, episode_number, provider_data):
        self.url = url
        self.title_de = f"DE {episode_number}"
        self.title_en = f"EN {episode_number}"
        self.episode_number = episode_number
        self.provider_data = provider_data


class FakeSeason:
    def __init__(self, url, episodes):
        self.url = url
        self.episodes = episodes


class FakeSeries:
    title = "Andor"

    def __init__(self, seasons):
        self.seasons = seasons


def _patch(monkeypatch, seasons, season_cls=object):
    provider = providers.Provider(
        name="SerienStream",
        series_pattern=None,
        season_pattern=None,
        episode_pattern=None,
        series_cls=lambda url: FakeSeries(seasons),
        season_cls=season_cls,
        episode_cls=object,
    )
    monkeypatch.setattr(providers, "resolve_provider", lambda url: provider)


GERMAN = {(Audio.GERMAN, Subtitles.NONE): {"VOE": "u1", "Filemoon": "u2"}}
ENGLISH = {(Audio.JAPANESE, Subtitles.ENGLISH): {"Doodstream": "u3"}}

SERIES_URL = "https://serienstream.to/serie/andor"
SEASON_URL = f"{SERIES_URL}/staffel-1"


def _episode(number, provider_data):
    return FakeEpisode(f"{SEASON_URL}/episode-{number}", number, provider_data)


def test_uniform_streams_are_hoisted_to_the_show(monkeypatch):
    season = FakeSeason(SEASON_URL, [_episode(1, GERMAN), _episode(2, GERMAN)])
    _patch(monkeypatch, [season])

    info = providers.get_info(SERIES_URL)

    assert info["streams"] == {"German Dub": ["Filemoon", "VOE"]}
    assert info["content"][0] == SERIES_URL
    assert info["content"][1][0] == SEASON_URL
    assert info["content"][1][1] == {
        "url": f"{SEASON_URL}/episode-1",
        "title_de": "DE 1",
        "title_en": "EN 1",
        "episode_number": 1,
    }
    assert "url" not in info


def test_differing_streams_stay_on_the_episodes(monkeypatch):
    season = FakeSeason(SEASON_URL, [_episode(1, GERMAN), _episode(2, ENGLISH)])
    _patch(monkeypatch, [season])

    info = providers.get_info(SERIES_URL)

    assert "streams" not in info
    assert info["content"][1][1]["streams"] == {"German Dub": ["Filemoon", "VOE"]}
    assert info["content"][1][2]["streams"] == {"English Sub": ["Doodstream"]}


def test_movie_provider_has_no_season_nesting(monkeypatch):
    movie = FakeEpisode("https://megakino.co/film/x", 1, GERMAN)
    movie.title = "Movie"
    monkeypatch.setattr(
        providers,
        "resolve_provider",
        lambda url: providers.Provider(
            name="MegaKino",
            series_pattern=None,
            season_pattern=None,
            episode_pattern=None,
            series_cls=lambda u: movie,
            season_cls=None,
            episode_cls=object,
        ),
    )

    info = providers.get_info("https://megakino.co/film/x")

    assert info["content"][0] == "https://megakino.co/film/x"
    assert info["content"][1]["episode_number"] == 1
    assert info["streams"] == {"German Dub": ["Filemoon", "VOE"]}
