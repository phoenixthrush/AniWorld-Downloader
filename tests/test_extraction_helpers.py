"""Regressions for the parsing and stream resolution shared by site backends."""

import base64
import json
from html import escape
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from aniworld.extractors import provider_functions
from aniworld.extractors.common import (
    decode_base64url,
    extract_video_metadata,
    unpack_js,
)
from aniworld.extractors.provider import filemoon
from aniworld.models import (
    AniworldEpisode,
    BurningSeriesEpisode,
    FilmoEpisode,
    FilmPalastEpisode,
    KinoxEpisode,
    MegaKinoEpisode,
    MoflixEpisode,
    SerienstreamEpisode,
)
from aniworld.models.common.extraction import resolve_stream_url
from aniworld.models.hentaihaven import HentaiHavenEpisode


@pytest.mark.parametrize(
    "model",
    [
        AniworldEpisode,
        BurningSeriesEpisode,
        FilmoEpisode,
        FilmPalastEpisode,
        KinoxEpisode,
        MegaKinoEpisode,
        MoflixEpisode,
        SerienstreamEpisode,
    ],
)
def test_models_resolve_through_the_registered_extractor(monkeypatch, model):
    calls = []

    def extract(url):
        calls.append(url)
        return "https://media.example/video.m3u8"

    monkeypatch.setitem(provider_functions, "get_direct_link_from_test", extract)
    monkeypatch.setattr(model, "selected_provider", property(lambda self: "Test"))
    monkeypatch.setattr(
        model, "provider_url", property(lambda self: "https://host.example/embed")
    )
    episode = object.__new__(model)
    assert episode.stream_url == "https://media.example/video.m3u8"
    assert calls == ["https://host.example/embed"]


def test_missing_extractor_does_not_fetch_the_provider_page():
    class Episode:
        selected_provider = "Missing"

        @property
        def provider_url(self):
            pytest.fail("An unsupported provider must not fetch a page")

    with pytest.raises(ValueError, match="provider 'Missing' is not yet implemented"):
        resolve_stream_url(Episode())


@pytest.mark.parametrize("result", [None, "", {}, 42])
def test_empty_or_invalid_extractor_result_is_rejected(monkeypatch, result):
    monkeypatch.setitem(
        provider_functions, "get_direct_link_from_test", lambda url: result
    )
    episode = SimpleNamespace(
        selected_provider="Test", provider_url="https://host.example/embed"
    )
    with pytest.raises(ValueError, match="Provider Test returned no stream URL"):
        resolve_stream_url(episode)


def test_extractor_key_error_is_not_misreported_as_a_missing_provider(monkeypatch):
    def extract(url):
        raise KeyError("sources")

    monkeypatch.setitem(provider_functions, "get_direct_link_from_test", extract)
    episode = SimpleNamespace(
        selected_provider="Test", provider_url="https://host.example/embed"
    )
    with pytest.raises(KeyError, match="sources"):
        resolve_stream_url(episode)


def test_redirect_failure_preserves_its_original_error(monkeypatch):
    called = []
    monkeypatch.setitem(
        provider_functions, "get_direct_link_from_test", lambda url: called.append(url)
    )

    class Episode:
        selected_provider = "Test"

        @property
        def provider_url(self):
            raise ValueError("Failed to resolve provider URL")

    with pytest.raises(ValueError, match="Failed to resolve provider URL"):
        resolve_stream_url(Episode())
    assert called == []


@pytest.mark.parametrize("structure", ["object", "array", "graph", "nested_graph"])
def test_video_metadata_skips_bad_scripts_and_handles_json_ld_shapes(structure):
    video = {
        "@type": "VideoObject",
        "name": "Example & Friends",
        "uploadDate": "2023-09-22",
    }
    if structure == "object":
        data = video
    elif structure == "array":
        data = [{"@type": "WebSite"}, video]
    elif structure == "graph":
        data = {"@graph": [{"@type": "WebSite"}, video]}
    else:
        data = [{"@graph": [video]}]
    html = '<script type="application/ld+json">broken JSON</script>'
    html += (
        '<SCRIPT TYPE="application/ld+json">' + escape(json.dumps(data)) + "</SCRIPT>"
    )
    assert extract_video_metadata(html) == video


@pytest.mark.parametrize(
    "html",
    [
        "",
        '<script type="application/json">{"@type":"VideoObject"}</script>',
        '<script type="application/ld+json">null</script>',
        '<script type="application/ld+json">{"@type":"WebSite"}</script>',
    ],
)
def test_absent_video_metadata_is_an_empty_mapping(html):
    assert extract_video_metadata(html) == {}


def test_haven_release_date_uses_video_metadata_in_a_graph(monkeypatch):
    html = (
        '<script type="application/ld+json">'
        + json.dumps(
            {
                "@graph": [
                    {"@type": "WebPage", "datePublished": "2020-01-01"},
                    {"@type": "VideoObject", "uploadDate": "2023-09-22"},
                ]
            }
        )
        + "</script>"
    )
    monkeypatch.setattr(HentaiHavenEpisode, "_html", property(lambda self: html))
    episode = HentaiHavenEpisode("https://hentaihaven.xxx/watch/example/episode-1/")
    assert episode.release_date == "2023-09-22"


@pytest.mark.parametrize("plain", [b"", b"f", b"fo", b"foo", b"\xfb\xff"])
@pytest.mark.parametrize("as_bytes", [False, True])
@pytest.mark.parametrize("padded", [False, True])
def test_base64url_handles_padding_and_url_safe_characters(plain, as_bytes, padded):
    encoded = base64.urlsafe_b64encode(plain)
    if not padded:
        encoded = encoded.rstrip(b"=")
    if not as_bytes:
        encoded = encoded.decode("ascii")
    assert decode_base64url(encoded) == plain


def test_filemoon_decrypts_unpadded_byse_playback_data():
    key = bytes(range(32))
    iv = bytes(range(12))
    payload = {
        "sources": [
            {"url": "https://media.example/720.m3u8", "height": 720},
            {"url": "https://media.example/1080.m3u8", "height": 1080},
        ]
    }
    ciphertext = AESGCM(key).encrypt(iv, json.dumps(payload).encode(), None)

    def encode(value):
        return base64.urlsafe_b64encode(value).decode().rstrip("=")

    playback = {
        "key_parts": [encode(key[:16]), encode(key[16:])],
        "iv": encode(iv),
        "payload": encode(ciphertext),
    }
    decrypted = filemoon._decrypt_playback_data(playback)
    assert decrypted == payload
    assert (
        filemoon._extract_best_source_url(decrypted)
        == "https://media.example/1080.m3u8"
    )


@pytest.mark.parametrize(
    "radix,token,index",
    [(2, "10", 2), (10, "10", 10), (36, "z", 35), (62, "A", 36), (62, "Z", 61)],
)
def test_packed_player_tokens_are_decoded_in_the_declared_radix(radix, token, index):
    keywords = [""] * 62
    keywords[index] = "video"
    assert unpack_js(token, radix, keywords) == "video"


def test_packed_player_preserves_unknown_or_empty_tokens():
    assert unpack_js("0 1 2 A _ café", 36, ["video", ""]) == "video 1 2 A _ café"


def test_filemoon_legacy_packed_player_uses_the_shared_unpacker():
    html = """eval(function(p,a,c,k,e,d){return p;}('0:[{1:"2"}]',36,3,'sources|file|https://media.example/video.m3u8'.split('|')))"""
    assert filemoon._try_extract_from_html(html) == "https://media.example/video.m3u8"
