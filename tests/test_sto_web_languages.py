from types import SimpleNamespace

from aniworld.web.views import api_media


class FakeEpisode:
    def __init__(self, number, provider_calls):
        self.url = f"https://serienstream.to/serie/from/staffel-1/episode-{number}"
        self.episode_number = number
        self.title_de = ""
        self.title_en = f"Episode {number}"
        self.season = SimpleNamespace(season_number=1)
        self._provider_calls = provider_calls

    @property
    def provider_data(self):
        self._provider_calls.append(self.episode_number)
        return {"German Dub": ["VOE"]}


def _provider(season):
    return SimpleNamespace(
        name="SerienStream",
        season_cls=lambda **kwargs: season,
    )


def test_season_rows_avoid_all_episode_page_probes(monkeypatch):
    provider_calls = []
    season = SimpleNamespace(
        episodes=[FakeEpisode(1, provider_calls), FakeEpisode(2, provider_calls)],
        episode_languages={
            1: ("German Dub", "English Dub"),
            2: ("German Dub",),
        },
    )
    found = object()
    monkeypatch.setattr(api_media, "_resolve_series", lambda *args: found)
    monkeypatch.setattr(api_media.media, "downloaded_episodes", lambda series: set())

    results = api_media._season_episodes(_provider(season), "season-url", None)

    assert provider_calls == []
    assert [result["available_languages"] for result in results] == [
        ["German Dub", "English Dub"],
        ["German Dub"],
    ]


def test_missing_season_flags_probe_only_one_episode(monkeypatch):
    provider_calls = []
    season = SimpleNamespace(
        episodes=[FakeEpisode(1, provider_calls), FakeEpisode(2, provider_calls)],
        episode_languages={},
    )
    found = object()
    monkeypatch.setattr(api_media, "_resolve_series", lambda *args: found)
    monkeypatch.setattr(api_media.media, "downloaded_episodes", lambda series: set())
    monkeypatch.setattr(
        api_media.media,
        "language_labels",
        lambda provider_data: list(provider_data),
    )

    results = api_media._season_episodes(_provider(season), "season-url", None)

    assert provider_calls == [1]
    assert all(result["available_languages"] == ["German Dub"] for result in results)
