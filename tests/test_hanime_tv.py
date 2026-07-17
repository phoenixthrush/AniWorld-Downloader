import base64
import json

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from aniworld.extractors.provider import hanime_tv
from aniworld.models.common import common
from aniworld.models.common import hls
from aniworld.models.hanime_tv.episode import HanimeTVEpisode
from aniworld.models.hanime_tv.series import HanimeTVSeries


def _urlsafe(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _manifest_token(manifest):
    iv = bytes(range(12))
    encrypted = AESGCM(hanime_tv._HANIME_AES_KEY).encrypt(
        iv,
        json.dumps(manifest).encode("utf-8"),
        hanime_tv._HANIME_AES_HEADER,
    )
    envelope = {
        "v": 1,
        "alg": "AES-256-GCM",
        "iv": _urlsafe(iv),
        "tag": _urlsafe(encrypted[-16:]),
        "data": _urlsafe(encrypted[:-16]),
    }
    return _urlsafe(json.dumps(envelope).encode("utf-8"))


def test_page_parser_scopes_episodes_to_more_from_section():
    html = """
    <meta content="Watch Test Show 1 Hentai Video in HD - hanime.tv" property="og:title">
    <meta property="og:description" content="Description">
    <meta property="og:image" content="https://hanime-cdn.com/images/covers/test-show-1.jpg">
    <script type="application/ld+json">
      {"@type":"VideoObject","name":"Test Show 1","uploadDate":"2025-01-02T03:04:05Z"}
    </script>
    <a href="/browse/tags/vanilla">vanilla</a>
    <a href="/browse/brands/test-studio">Studio <strong>Test Studio</strong></a>
    <section><h2>More from Test Show</h2>
      <a href="/videos/hentai/test-show-2"><img src="https://hanime-cdn.com/2.jpg" alt="Test Show 2 thumbnail"></a>
      <a href="/videos/hentai/test-show-1"><img src="https://hanime-cdn.com/1.jpg" alt="Test Show 1 thumbnail"></a>
    </section>
    <section><h2>Recommended</h2>
      <a href="/videos/hentai/unrelated-1"><img src="https://hanime-cdn.com/x.jpg" alt="Unrelated 1 thumbnail"></a>
    </section>
    """

    payload = hanime_tv._build_synthetic_payload("test-show-1", html)

    assert payload["hentai_franchise"]["title"] == "Test Show"
    assert payload["brand"]["title"] == "Test Studio"
    assert payload["hentai_video"]["hentai_tags"][0]["text"] == "vanilla"
    assert payload["hentai_franchise_hentai_videos"] == [
        {"slug": "test-show-1", "name": "Test Show 1"},
        {"slug": "test-show-2", "name": "Test Show 2"},
    ]


def test_manifest_token_decryption_and_best_normal_source():
    manifest = {
        "sources": [
            {"src": "/premium", "height": 1080, "kind": "promotion"},
            {"src": "/hls/480", "height": 480, "kind": "normal"},
            {"src": "/hls/720", "height": 720, "kind": "normal"},
        ]
    }
    parsed = hanime_tv._parse_hanime_manifest_token(_manifest_token(manifest))
    api_data = {
        "hentai_video": {"slug": "test-show-1"},
        "videos_manifest": parsed,
    }

    assert parsed == manifest
    assert (
        hanime_tv.get_direct_link_from_hanime_tv(api_data)
        == "https://hanime.tv/hls/720"
    )


def test_manifest_is_fetched_from_hanime_handshake(monkeypatch):
    manifest = {
        "sources": [{"src": "/hls/720", "height": 720, "kind": "normal"}]
    }
    calls = []

    def fake_handshake(url, timeout):
        calls.append((url, timeout))
        return _manifest_token(manifest)

    monkeypatch.setattr(hanime_tv, "playwright_get_hanime_manifest_token", fake_handshake)

    assert hanime_tv.fetch_hanime_manifest("test-show-1") == manifest
    assert calls == [("https://hanime.tv/videos/hentai/test-show-1", 15)]


def test_sitemap_search_uses_only_hanime_video_urls():
    sitemap = """
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://hanime.tv/videos/hentai/another-title-1</loc></url>
      <url><loc>https://hanime.tv/videos/hentai/test-show-2</loc></url>
      <url><loc>https://hanime.tv/videos/hentai/test-show-1</loc></url>
      <url><loc>https://example.com/videos/hentai/test-show-3</loc></url>
      <url><loc>https://hanime.tv/browse/trending</loc></url>
    </urlset>
    """
    slugs = hanime_tv._parse_sitemap_slugs(sitemap)

    assert slugs == ("another-title-1", "test-show-2", "test-show-1")
    assert hanime_tv._rank_hanime_slugs(slugs, "test show") == ["test-show-1"]


def test_search_enrichment_never_calls_a_non_hanime_api(monkeypatch):
    requested = []

    class Response:
        text = ""

        @staticmethod
        def raise_for_status():
            raise TimeoutError("optional enrichment timed out")

    def fake_get(url, **kwargs):
        requested.append(url)
        return Response()

    monkeypatch.setattr(hanime_tv, "_get_sitemap_slugs", lambda: ("test-show-1",))
    monkeypatch.setattr(hanime_tv.niquests, "get", fake_get)

    results = hanime_tv.search_hanime("test show")

    assert requested == ["https://hanime.tv/videos/hentai/test-show-1"]
    assert results[0]["slug"] == "test-show-1"


def test_hanime_style_encrypted_html_segment_can_be_decrypted():
    playlist_url = "https://hanime.tv/hls/test"
    playlist = """#EXTM3U
#EXT-X-MEDIA-SEQUENCE:7
#EXT-X-KEY:METHOD=AES-128,URI="https://ct.htv-services.com/sign.bin"
#EXTINF:10,
https://p01.htv-absolute-virtue.com/video/0007.html
#EXT-X-ENDLIST
"""
    segments, init_uri = hls._parse_media_playlist(playlist, playlist_url)
    _, key, sequence = segments[0]
    key_bytes = b"0123456789abcdef"
    plain = b"\x47\x40\x00\x10" + b"test transport stream"
    padding = 16 - (len(plain) % 16)
    padded = plain + bytes([padding]) * padding
    encryptor = Cipher(
        algorithms.AES(key_bytes), modes.CBC(hls._resolve_iv(key, sequence))
    ).encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()

    assert init_uri is None
    assert key.uri == "https://ct.htv-services.com/sign.bin"
    assert hls._decrypt_segment(
        encrypted, key_bytes, hls._resolve_iv(key, sequence)
    ) == plain


def test_hanime_download_retries_with_fresh_manifest(monkeypatch, tmp_path):
    calls = []

    class Episode:
        _episode_path = tmp_path / "episode.mkv"
        _folder_path = tmp_path / "series"
        _file_name = "Test Show 1"
        stream_url = "https://hanime.tv/hls/old"

        def refresh_stream_url(self):
            return "https://hanime.tv/hls/fresh"

    def fake_download(path, url, name):
        calls.append(url)
        if len(calls) == 1:
            raise TimeoutError("segment timed out")

    monkeypatch.setattr(common.platform, "system", lambda: "Linux")
    monkeypatch.setattr(common, "_download_hls_stream", fake_download)
    monkeypatch.setattr(common.time, "sleep", lambda _: None)

    common.download_hanime(Episode())

    assert calls == ["https://hanime.tv/hls/old", "https://hanime.tv/hls/fresh"]


@pytest.mark.parametrize(
    "url",
    [
        "https://hanime.tv/videos/hentai/test-show-1",
        "https://hanime.tv/hentai/video/test-show-1",
        "https://hanime.tv/playlists/abc123/video/test-show-1",
    ],
)
def test_supported_hanime_url_forms(url):
    assert HanimeTVSeries.is_valid_url(url)
    assert HanimeTVEpisode._is_valid_url(url)
