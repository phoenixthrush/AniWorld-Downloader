"""Moflix movie/series routes and the hosters they actually expose."""

import base64
import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from aniworld import search
from aniworld.extractors.provider import gupload, moflixclick, vidara
from aniworld.models.common.provider_map import host_to_provider
from aniworld.models.moflix_stream import series as moflix
from aniworld.providers import normalize_url, resolve_provider
from aniworld.search import fetch_moflix_movies, query_moflix


def _response(*, payload=None, text=""):
    return SimpleNamespace(
        status_code=200,
        headers={},
        cookies={},
        text=text,
        json=lambda: payload,
        raise_for_status=lambda: None,
    )


def _moflix_api(monkeypatch, *, series=False):
    calls = []
    title = {
        "name": "Sample",
        "year": 2026,
        "poster": "/poster.jpg",
        "is_series": series,
    }
    videos = [
        {"name": "Mirror 1", "src": "https://gupload.xyz/e/first"},
        {"name": "Mirror 2", "src": "https://moflix-stream.click/embed/second"},
        {"name": "Mirror 3", "src": "https://moflix.upns.xyz/e/not-voe"},
        {"name": "Mirror 4", "src": "https://unsupported.example/e/unimplemented"},
    ]

    def fetch(url, *args, **kwargs):
        calls.append(url)
        if "/api/v1/titles/42/seasons/1/episodes/" in url:
            return _response(payload={"episode": {"videos": videos}})
        if "/api/v1/titles/42/seasons/1?" in url:
            return _response(
                payload={
                    "episodes": {
                        "data": [
                            {"episode_number": 1, "name": "One"},
                            {"episode_number": 2, "name": "Two"},
                        ]
                    }
                }
            )
        if url.endswith("/api/v1/titles/42"):
            return _response(
                payload={
                    "title": {**title, "videos": [] if series else videos},
                    "seasons": {"data": [{"number": 1, "episodes_count": 2}]}
                    if series
                    else {},
                }
            )
        return _response(text='window.bootstrapData = {"csrf_token":"test"};')

    monkeypatch.setattr(moflix, "_fetch_moflix", fetch)
    return calls


def test_movie_routes_include_only_implemented_hosters(client, monkeypatch):
    _moflix_api(monkeypatch)
    url = "https://moflix-stream.xyz/titles/42"
    title = client.get("/api/series", query_string={"url": url}).get_json()
    assert title["title"] == "Sample"
    assert title["poster_url"]

    seasons = client.get("/api/seasons", query_string={"url": url}).get_json()[
        "seasons"
    ]
    assert len(seasons) == 1 and seasons[0]["are_movies"] is True
    episodes = client.get("/api/episodes", query_string={"url": url}).get_json()[
        "episodes"
    ]
    assert len(episodes) == 1 and episodes[0]["episode_number"] == 1
    providers = client.get("/api/providers", query_string={"url": url}).get_json()[
        "providers"
    ]
    assert providers == {"German Dub": ["Gupload", "MoflixClick"]}

    movie = moflix.MoflixEpisode(url)
    season = movie.seasons[0]
    episode = season.episodes[0]
    assert isinstance(episode, moflix.MoflixEpisode)
    assert episode.series is movie
    assert episode.season is season
    assert episode.episode_number == 1


def test_series_listing_does_not_probe_every_episode(client, monkeypatch):
    calls = _moflix_api(monkeypatch, series=True)
    url = "https://moflix-stream.xyz/titles/42?season=1"
    response = client.get("/api/episodes", query_string={"url": url})
    assert response.status_code == 200
    episodes = response.get_json()["episodes"]
    assert [episode["episode_number"] for episode in episodes] == [1, 2]
    assert all(episode["available_languages"] == ["German Dub"] for episode in episodes)
    assert not any("/episodes/" in call for call in calls)

    series = moflix.MoflixEpisode(url)
    season = series.seasons[0]
    episode_models = season.episodes
    assert season.episodes is episode_models
    assert all(isinstance(episode, moflix.MoflixEpisode) for episode in episode_models)
    assert all(episode.series is series for episode in episode_models)
    assert all(episode.season is season for episode in episode_models)
    assert [episode.title_en for episode in episode_models] == ["One", "Two"]
    assert not any("/episodes/" in call for call in calls)

    providers = client.get("/api/providers", query_string={"url": episodes[0]["url"]})
    assert providers.get_json()["providers"] == {
        "German Dub": ["Gupload", "MoflixClick"]
    }
    download = moflix.MoflixEpisode(episodes[1]["url"])
    assert download._folder_path.name == "Season 01"
    assert "S01E002" in download._file_name


def test_mirror_names_are_not_mistaken_for_other_hosters():
    assert host_to_provider("gupload.xyz") == "Gupload"
    assert host_to_provider("moflix-stream.click") == "MoflixClick"
    assert host_to_provider("vidara.to") == "Vidara"
    assert host_to_provider("moflix.upns.xyz") is None
    assert host_to_provider("unsupported.example") is None
    assert host_to_provider("unsupported.example", require_extractor=False) is None


def test_moflix_fallback_uses_the_matching_extractor(monkeypatch):
    _moflix_api(monkeypatch)
    episode = moflix.MoflixEpisode(
        "https://moflix-stream.xyz/titles/42", selected_provider="MoflixClick"
    )
    assert episode.provider_attempt_order() == ("MoflixClick", "Gupload")
    assert episode.provider_url == "https://moflix-stream.click/embed/second"
    episode.selected_provider = "Gupload"
    assert episode.provider_url == "https://gupload.xyz/e/first"
    episode.selected_provider = "VOE"
    with pytest.raises(ValueError, match="No Moflix link for provider VOE"):
        _ = episode.provider_url


def test_gupload_decodes_player_configuration(monkeypatch):
    key = b"G7#kP!2qZxV9mRwL"
    stream = "https://gupload.xyz/data/e/hls/sample/720p.m3u8"
    plain = json.dumps({"videoUrl": stream}).encode()
    encoded = base64.b64encode(
        bytes(value ^ key[i % len(key)] for i, value in enumerate(plain))
    ).decode()
    html = (
        "var _k=(function(){var _p=['G7#k','P!2q','ZxV9','mRwL'];"
        "return _p[0]+_p[1]+_p[2]+_p[3];})();"
        f"var _cfg = _dp('abc~{encoded}');"
    )
    monkeypatch.setattr(gupload.requests, "get", lambda *a, **k: _response(text=html))
    assert (
        gupload.get_direct_link_from_gupload("https://gupload.xyz/e/sample") == stream
    )


def test_moflixclick_unpacks_hls_links(monkeypatch):
    stream = "https://cdn.example/master.m3u8"
    html = (
        "eval(function(p,a,c,k,e,d){return p}('"
        f'1 0={{"2":"{stream}"}};'
        "',3,3,'links|var|hls2'.split('|')))"
    )

    def get(url, **kwargs):
        return _response(text=html if "moflix-stream.click" in url else "#EXTM3U\n")

    monkeypatch.setattr(moflixclick.requests, "get", get)
    assert (
        moflixclick.get_direct_link_from_moflixclick(
            "https://moflix-stream.click/embed/sample"
        )
        == stream
    )


def test_moflixclick_tries_the_next_reachable_playlist(monkeypatch):
    first = "https://cdn.example/first.txt"
    second = "https://cdn.example/second.m3u8"
    html = (
        "eval(function(p,a,c,k,e,d){return p}('"
        f'1 0={{"2":"{first}","3":"{second}"}};'
        "',4,4,'links|var|hls3|hls2'.split('|')))"
    )
    requested = []

    def get(url, **kwargs):
        requested.append(url)
        if "moflix-stream.click" in url:
            return _response(text=html)
        if url == first:
            raise TimeoutError("playlist timed out")
        return _response(text="#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nvideo.m3u8")

    monkeypatch.setattr(moflixclick.requests, "get", get)
    assert (
        moflixclick.get_direct_link_from_moflixclick(
            "https://moflix-stream.click/embed/example"
        )
        == second
    )
    assert requested == ["https://moflix-stream.click/embed/example", first, second]


def test_moflix_search_excludes_people_and_invalid_ids(monkeypatch):
    import curl_cffi.requests

    def get(url, **kwargs):
        if url.endswith("/api/v1/search/silo"):
            return _response(
                payload={
                    "results": [
                        {
                            "id": 42,
                            "name": "Silo",
                            "model_type": "title",
                            "poster": "https://image.example/silo.jpg",
                        },
                        {
                            "id": 101,
                            "name": "Silo Septiadi",
                            "model_type": "person",
                            "poster": None,
                        },
                        {
                            "id": None,
                            "name": "Broken",
                            "model_type": "title",
                            "poster": None,
                        },
                    ]
                }
            )
        return _response(text='window.bootstrapData = {"csrf_token":"test"};')

    monkeypatch.setattr(curl_cffi.requests, "get", get)
    assert query_moflix("silo") == [
        {
            "title": "Silo",
            "url": "https://moflix-stream.xyz/titles/42",
            "poster_url": "https://image.example/silo.jpg",
        }
    ]


def test_moflix_search_and_browse_propagate_request_errors(monkeypatch):
    import curl_cffi.requests

    def fail(*args, **kwargs):
        raise TimeoutError("moflix timed out")

    monkeypatch.setattr(curl_cffi.requests, "get", fail)

    with pytest.raises(TimeoutError, match="moflix timed out"):
        query_moflix("silo")
    with pytest.raises(TimeoutError, match="moflix timed out"):
        fetch_moflix_movies()


@pytest.mark.parametrize("limit", [1, 12, 31, 61, None])
def test_moflix_genre_respects_recommendation_limit(monkeypatch, limit):
    def fetch(endpoint):
        params = parse_qs(urlsplit(endpoint).query)
        assert params["genres"] == ["Krieg & Politik"]
        assert params["route"] == ["genre"]
        assert params["mediaType"] == ["all"]
        requested = int(params["limit"][0])
        assert 1 <= requested <= 12
        return {"titles": [{"id": n, "name": f"Title {n}"} for n in range(requested)]}

    monkeypatch.setattr(search, "_moflix_json", fetch)
    results = query_moflix(genre="Krieg & Politik", limit=limit)
    assert len(results) == (min(limit, 12) if limit is not None else 12)


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/titles/42/silo", "/titles/42"),
        ("/titles/42/silo/?season=2&episode=3", "/titles/42?season=2&episode=3"),
        ("/titles/42/silo/season/2/episodes/3", "/titles/42/season/2/episodes/3"),
        ("/TITLES/42/SEASON/2/EPISODES/3/", "/titles/42/season/2/episodes/3"),
    ],
)
def test_browser_urls_are_normalized_before_resolving_or_loading(path, expected):
    url = "http://www.moflix-stream.xyz" + path
    canonical = "https://moflix-stream.xyz" + expected
    assert normalize_url(url) == canonical
    assert resolve_provider(url).name == "Moflix"
    episode = moflix.MoflixEpisode(" " + url + " ")
    assert episode.url == canonical
    if "season" in expected:
        assert (episode.season_id, episode.episode_id) == (2, 3)


@pytest.mark.parametrize(
    "url",
    [
        "https://moflix-stream.xyz.evil.test/titles/42/silo",
        "https://user@moflix-stream.xyz/titles/42/silo",
        "https://moflix-stream.xyz/titles/42/silo/unknown",
        "https://moflix-stream.xyz/titles/42/season",
        "https://moflix-stream.xyz/titles/42/episodes/3",
    ],
)
def test_invalid_browser_urls_are_rejected(url):
    with pytest.raises(ValueError):
        resolve_provider(url)
    with pytest.raises(ValueError, match="Invalid Moflix"):
        moflix.MoflixEpisode(url)


@pytest.mark.parametrize("pagination", [{"next_page": "2"}, {"last_page": 2}])
def test_seasons_follow_pages_deduplicate_and_remain_lazy(monkeypatch, pagination):
    _moflix_api(monkeypatch, series=True)
    original = moflix.MoflixEpisode._api_get
    calls = []

    def fetch(self, url):
        calls.append(url)
        if "/seasons/1?" not in url:
            return original(self, url)
        first = {"episode_number": 1, "name": "One"}
        second = {"episode_number": 2, "name": "Two"}
        if "page=2" in url:
            return _response(payload={"episodes": {"data": [second, first]}})
        return _response(payload={"episodes": {"data": [second], **pagination}})

    monkeypatch.setattr(moflix.MoflixEpisode, "_api_get", fetch)
    season = moflix.MoflixEpisode("https://moflix-stream.xyz/titles/42").seasons[0]
    assert [episode.episode_number for episode in season.episodes] == [1, 2]
    assert [episode.title_en for episode in season.episodes] == ["One", "Two"]
    assert sum("/seasons/1?" in url for url in calls) == 2
    assert not any("/episodes/" in url for url in calls)


@pytest.mark.parametrize("pointer", [1, 0, True, "https://example.com/next"])
def test_invalid_pagination_is_rejected_before_another_fetch(monkeypatch, pointer):
    _moflix_api(monkeypatch, series=True)
    title = moflix.MoflixEpisode("https://moflix-stream.xyz/titles/42")
    season = title.seasons[0]
    calls = []

    def fetch(url):
        calls.append(url)
        return _response(payload={"episodes": {"data": [], "next_page": pointer}})

    monkeypatch.setattr(title, "_api_get", fetch)
    with pytest.raises(moflix.MoflixError, match="page"):
        _ = season.episodes
    assert len(calls) == 1


def test_season_pagination_is_bounded(monkeypatch):
    _moflix_api(monkeypatch, series=True)
    title = moflix.MoflixEpisode("https://moflix-stream.xyz/titles/42")
    season = title.seasons[0]
    calls = []

    def fetch(url):
        calls.append(url)
        page = int(parse_qs(urlsplit(url).query).get("page", [1])[0])
        return _response(payload={"episodes": {"data": [], "next_page": page + 1}})

    monkeypatch.setattr(title, "_api_get", fetch)
    with pytest.raises(moflix.MoflixError, match="100 pages"):
        _ = season.episodes
    assert len(calls) == 100


@pytest.mark.parametrize("data", [{}, {"pagination": {}}, {"pagination": {"data": {}}}])
def test_invalid_browse_data_is_not_an_empty_success(monkeypatch, data):
    monkeypatch.setattr(search, "_moflix_json", lambda endpoint: data)
    with pytest.raises(moflix.MoflixError, match="title list"):
        fetch_moflix_movies()


def test_vidara_uses_its_stream_api(monkeypatch):
    class Session:
        def get(self, url, **kwargs):
            assert url == "https://vidara.to/e/sample123"
            return _response(text="<html></html>")

        def post(self, url, *, json, headers, **kwargs):
            assert url == "https://vidara.to/api/stream"
            assert json == {"filecode": "sample123", "device": "web"}
            assert headers["Referer"] == "https://vidara.to/e/sample123"
            return _response(
                payload={"streaming_url": "https://cdn.example/master.m3u8"}
            )

    monkeypatch.setattr(vidara.requests, "Session", lambda **kwargs: Session())
    assert (
        vidara.get_direct_link_from_vidara("https://vidara.to/e/sample123")
        == "https://cdn.example/master.m3u8"
    )


@pytest.mark.parametrize("provider", ["Gupload", "MoflixClick", "Vidara"])
def test_moflix_provider_headers_avoid_encoded_playlists(provider):
    from aniworld.config import PROVIDER_HEADERS_D

    if provider in {"Gupload", "MoflixClick"}:
        assert PROVIDER_HEADERS_D[provider]["Accept-Encoding"] == "identity"
