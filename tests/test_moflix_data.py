"""Moflix public page loaders, URL handling and failure recovery stay offline."""

import json
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest

from aniworld import search
from aniworld.models.moflix_stream import data, http, series
from aniworld.providers import normalize_url, resolve_provider


def response(*, payload=None, text=None, status=200):
    result = http.requests.Response()
    result.url = http.BASE_URL + "/"
    result.status_code = status
    result.ok = 200 <= status < 400
    result.headers["Content-Type"] = "application/json" if text is None else "text/html"
    result.content = (json.dumps(payload) if text is None else text).encode("utf-8")
    return result


def page(name, loader):
    payload = {"csrf_token": "test", "loaders": {name: loader}}
    return response(
        text="<script>window.bootstrapData = "
        + json.dumps(payload, indent=2)
        + ";</script>"
    )


def title(number=42, **extra):
    return {"id": number, "name": "Silo", "model_type": "title", **extra}


@pytest.fixture
def transport(monkeypatch):
    get = Mock()
    monkeypatch.setattr(data, "get_response", get)
    monkeypatch.setattr(
        search,
        "_moflix_json",
        Mock(side_effect=AssertionError("Legacy search/browse API must not be called")),
    )
    return get


def test_bootstrap_decodes_nested_multiline_json_without_eval():
    loader = {"results": [title(name='Nested }; "name"')], "query": "test"}
    assert (
        data.parse_bootstrap(page("searchPage", loader).text)["loaders"]["searchPage"]
        == loader
    )


@pytest.mark.parametrize(
    "text",
    ["<html></html>", "window.bootstrapData = {broken};", "window.bootstrapData = [];"],
)
def test_missing_or_invalid_bootstrap_is_not_an_empty_list(text):
    with pytest.raises(data.MoflixResponseError, match="bootstrap"):
        data.parse_bootstrap(text)


def test_keyword_search_uses_public_page_and_existing_result_shape(transport):
    transport.return_value = page(
        "searchPage",
        {
            "query": "silo",
            "results": [
                title(poster="//images.example/silo.jpg"),
                title(),
                title(model_type="person"),
                title(None),
                title(True),
                None,
            ],
        },
    )
    assert search.query_moflix("silo") == [
        {
            "title": "Silo",
            "url": http.BASE_URL + "/titles/42",
            "poster_url": "https://images.example/silo.jpg",
        }
    ]
    transport.assert_called_once_with(http.BASE_URL + "/search/silo")


def test_search_trims_and_encodes_query_and_honours_limit(transport):
    keyword = "Mädchen / A&B?#"
    transport.return_value = page(
        "searchPage", {"query": keyword, "results": [title(), title(43)]}
    )
    assert len(search.query_moflix("  " + keyword + "  ", limit=1)) == 1
    assert transport.call_args.args[0].endswith(
        "/search/M%C3%A4dchen%20%2F%20A%26B%3F%23"
    )


@pytest.mark.parametrize("kwargs", [{"keyword": " "}, {"keyword": "silo", "limit": 0}])
def test_empty_or_zero_limit_search_does_not_fetch(transport, kwargs):
    assert search.query_moflix(**kwargs) == []
    transport.assert_not_called()


@pytest.mark.parametrize(
    "loader",
    [
        {"query": "other", "results": []},
        {"query": "silo"},
        {"query": "silo", "results": {}},
    ],
)
def test_search_rejects_wrong_or_missing_page_data(transport, loader):
    transport.return_value = page("searchPage", loader)
    with pytest.raises(data.MoflixResponseError):
        search.query_moflix("silo")


def test_recent_titles_keep_order_remove_duplicates_and_limit(transport):
    items = [title(9), title(2, poster="/poster.jpg"), title(9)] + [
        title(n) for n in range(10, 40)
    ]
    transport.return_value = page(
        "channelPage", {"channel": {"slug": "now-playing", "content": {"data": items}}}
    )
    cards = search.fetch_moflix_movies()
    assert len(cards) == 24
    assert [item["url"].rsplit("/", 1)[1] for item in cards[:3]] == ["9", "2", "10"]
    assert cards[1]["poster_url"] == http.BASE_URL + "/poster.jpg"
    transport.assert_called_once_with(http.BASE_URL + "/now-playing")


@pytest.mark.parametrize(
    "channel",
    [
        {},
        {"slug": "movies", "content": {"data": []}},
        {"slug": "now-playing", "content": {}},
    ],
)
def test_recent_titles_reject_changed_structure(transport, channel):
    transport.return_value = page("channelPage", {"channel": channel})
    with pytest.raises(data.MoflixResponseError):
        search.fetch_moflix_movies()


def test_cards_preserve_legacy_genre_ids_and_reject_unsafe_posters():
    items = [
        {"id": 0, "name": "Example"},
        title(43, poster="javascript:alert(1)"),
        title(44, model_type="person"),
    ]
    assert data.title_cards(items, require_title=False) == [
        {"title": "Example", "url": http.BASE_URL + "/titles/0", "poster_url": ""},
        {"title": "Silo", "url": http.BASE_URL + "/titles/43", "poster_url": ""},
    ]


@pytest.mark.parametrize(
    "path",
    [
        "@example.com/",
        "https://example.com/",
        "//example.com/",
        "/search/silo#fragment",
    ],
)
def test_page_loader_rejects_nonlocal_paths_before_transport(transport, path):
    with pytest.raises(data.MoflixResponseError, match="path"):
        data.page_loader(path, "searchPage")
    transport.assert_not_called()


@pytest.mark.parametrize("status", [200, 403])
def test_challenge_html_never_becomes_empty_success(transport, status):
    transport.return_value = response(
        text="<title>Just a moment...</title>", status=status
    )
    with pytest.raises(data.MoflixResponseError, match="verification page"):
        search.query_moflix("silo")


def test_regular_cloudflare_precursor_script_is_not_a_challenge(transport):
    answer = page("searchPage", {"query": "silo", "results": []})
    answer.content += (
        b'<script src="/cdn-cgi/challenge-platform/scripts/precursor/main.js"></script>'
    )
    transport.return_value = answer
    assert search.query_moflix("silo") == []


@pytest.mark.parametrize(
    "answer",
    [
        response(text="<html/>"),
        response(payload=[]),
        response(payload=None),
        response(text="not-json"),
    ],
)
def test_json_requires_an_object_and_not_html(answer):
    with pytest.raises(data.MoflixResponseError):
        data.read_json(answer)


def test_episode_pagination_preserves_endpoint_and_parameters():
    get = Mock(
        side_effect=[
            response(payload={"episodes": {"data": [1], "next_page": 2}}),
            response(payload={"episodes": {"data": [2], "next_page": None}}),
        ]
    )
    url = http.BASE_URL + "/api/v1/titles/42/seasons/1?perPage=500"
    assert data.paginated_items(url, "episodes", get) == [1, 2]
    assert get.call_args.args == (url + "&page=2",)


@pytest.mark.parametrize("pointer", [1, -1, True, "https://example.com/next", "bad"])
def test_invalid_pagination_does_not_follow_external_or_repeated_pages(pointer):
    get = Mock(
        return_value=response(payload={"episodes": {"data": [], "next_page": pointer}})
    )
    with pytest.raises(data.MoflixResponseError, match="pagination"):
        data.paginated_items(
            http.BASE_URL + "/api/v1/titles/42/seasons/1", "episodes", get
        )
    assert get.call_count == 1


def test_pagination_supports_last_page():
    get = Mock(
        side_effect=[
            response(payload={"episodes": {"data": [1], "last_page": 2}}),
            response(payload={"episodes": {"data": [2], "last_page": 2}}),
        ]
    )
    assert data.paginated_items(
        http.BASE_URL + "/api/v1/titles/42/seasons/1", "episodes", get
    ) == [1, 2]


@pytest.mark.parametrize("last_page", [True, "bad", 0])
def test_pagination_rejects_invalid_last_page(last_page):
    get = Mock(
        return_value=response(
            payload={"episodes": {"data": [], "last_page": last_page}}
        )
    )
    with pytest.raises(data.MoflixResponseError, match="pagination"):
        data.paginated_items(
            http.BASE_URL + "/api/v1/titles/42/seasons/1", "episodes", get
        )


@pytest.mark.parametrize(
    "url, expected",
    [
        (
            "https://moflix-stream.xyz/titles/42/silo",
            "https://moflix-stream.xyz/titles/42",
        ),
        (
            "http://www.moflix-stream.xyz/titles/42/silo/?season=2",
            "https://moflix-stream.xyz/titles/42?season=2",
        ),
        (
            "https://moflix-stream.xyz/titles/42/silo/season/2/episodes/3",
            "https://moflix-stream.xyz/titles/42/season/2/episodes/3",
        ),
        (
            "HTTPS://MOFLIX-STREAM.XYZ/TITLES/42/SEASON/2/EPISODES/3",
            "https://moflix-stream.xyz/titles/42/season/2/episodes/3",
        ),
    ],
)
def test_browser_urls_preserve_title_and_episode_identity(url, expected):
    assert normalize_url(url) == expected
    assert resolve_provider(url).name == "Moflix"
    assert series.MoflixEpisode(url).url == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://moflix-stream.xyz.evil.test/titles/42/silo",
        "https://user:pass@moflix-stream.xyz/titles/42",
        "https://moflix-stream.xyz/titles/42/season?season=1",
        "https://moflix-stream.xyz/titles/42/silo/unexpected",
    ],
)
def test_unrelated_or_malformed_title_urls_are_rejected(url):
    with pytest.raises(ValueError, match="Invalid Moflix"):
        series.MoflixEpisode(url)


def test_browse_error_is_not_cached_and_a_retry_can_recover(
    client, transport, monkeypatch
):
    from aniworld.web.views import api_media

    monkeypatch.setattr(api_media, "_browse_cache", {})
    transport.side_effect = [
        response(status=403, text="<title>Just a moment...</title>"),
        page(
            "channelPage",
            {"channel": {"slug": "now-playing", "content": {"data": [title()]}}},
        ),
    ]
    failure = client.get("/api/moflix-movies")
    assert failure.status_code == 502
    assert "verification page" in failure.get_json()["error"]
    assert "moflix_movies" not in api_media._browse_cache
    success = client.get("/api/moflix-movies")
    assert success.status_code == 200
    assert success.get_json()["results"][0]["title"] == "Silo"
    assert transport.call_count == 2


def test_search_error_is_not_reported_as_no_results(client, transport):
    transport.return_value = response(
        status=403, text="<title>Just a moment...</title>"
    )
    result = client.post("/api/search", json={"site": "moflix", "keyword": "silo"})
    assert result.status_code == 502
    assert "verification page" in result.get_json()["error"]
    assert "results" not in result.get_json()


def test_unexpected_moflix_error_does_not_expose_exception_text(
    client, transport, caplog
):
    transport.side_effect = RuntimeError("secret-cookie-value")
    result = client.post("/api/search", json={"site": "moflix", "keyword": "silo"})
    assert result.status_code == 502
    assert "secret-cookie-value" not in result.get_data(as_text=True)
    assert "secret-cookie-value" not in caplog.text


def test_invalid_json_body_raises_a_public_error():
    answer = response(text="invalid-json")
    answer.headers["Content-Type"] = "application/json"
    with pytest.raises(data.MoflixResponseError, match="invalid JSON"):
        data.read_json(answer)


@pytest.mark.parametrize(
    "limit, expected", [(1, 1), (2, 2), (12, 12), (13, 12), (31, 12), (100, 12)]
)
def test_genre_limit_respects_native_api_scope(monkeypatch, limit, expected):
    def fetch(endpoint):
        assert parse_qs(urlsplit(endpoint).query)["limit"] == [str(expected)]
        return {"titles": [title(n) for n in range(expected)]}

    monkeypatch.setattr(search, "_moflix_json", fetch)
    assert len(search.query_moflix(genre="Action", limit=limit)) == expected


def test_web_genre_overfetch_stays_within_native_limit(client, monkeypatch):
    from aniworld.web.views import api_media

    monkeypatch.setattr(api_media, "_browse_cache", {})

    def fetch(endpoint):
        assert parse_qs(urlsplit(endpoint).query)["limit"] == ["12"]
        return {"titles": [title(n) for n in range(12)]}

    monkeypatch.setattr(search, "_moflix_json", fetch)
    result = client.get("/api/genre?site=moflix&slug=Action")
    assert result.status_code == 200
    assert len(result.get_json()["results"]) == 12
    assert result.get_json()["has_more"] is False


def test_genre_http_failures_have_public_messages(monkeypatch):
    monkeypatch.setattr(
        http,
        "get_response",
        Mock(side_effect=[page("titlePage", {}), response(status=422)]),
    )
    with pytest.raises(data.MoflixResponseError, match="HTTP 422"):
        search._moflix_json("/api/v1/moflix/recommendations?route=genre")
