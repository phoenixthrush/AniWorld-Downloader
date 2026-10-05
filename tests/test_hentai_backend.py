"""Offline regression checks for site parsing, search and CLI dispatch."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from aniworld import entry, search
from aniworld.config import Audio, Subtitles
from aniworld.models import (
    AnimeIDHentaiEpisode,
    HentaiHavenEpisode,
    HentaiHavenSeries,
    HentaiTVEpisode,
)
from aniworld.models.hentai_tv import episode as episode_module
from aniworld.models.hentai_tv import http
from aniworld.models.hentai_tv.page import page_objects
from aniworld.providers import resolve_provider

HENTAI = "https://hentai.tv/hentai/example-episode-2"
ANIMEID = "https://animeidhentai.com/641/example-episode-2-sub-eng"
HAVEN = "https://hentaihaven.xxx/watch/example/episode-2/"


def response(text="", payload=None):
    return SimpleNamespace(
        text=text, json=lambda: payload, raise_for_status=lambda: None
    )


def flight(value, split=False):
    raw = "1:" + json.dumps(value) + "\n"
    chunks = [raw[:20], raw[20:]] if split else [raw]
    return "".join(
        "<script>self.__next_f.push(" + json.dumps([1, chunk]) + ")</script>"
        for chunk in chunks
    )


@pytest.mark.parametrize(
    "url,cls,name",
    [
        (HENTAI, HentaiTVEpisode, "HentaiTV"),
        (ANIMEID, AnimeIDHentaiEpisode, "AnimeIDHentai"),
        (
            "https://animeidhentai.com/641/example",
            AnimeIDHentaiEpisode,
            "AnimeIDHentai",
        ),
        (
            "https://www.animeidhentai.com/example-episode-2",
            AnimeIDHentaiEpisode,
            "AnimeIDHentai",
        ),
        (HAVEN, HentaiHavenEpisode, "HentaiHaven"),
        (
            "https://hentaihaven.xxx/de/watch/example/episode-2/",
            HentaiHavenEpisode,
            "HentaiHaven",
        ),
        (
            "https://hentaihaven.xxx/watch/example/season-1/",
            HentaiHavenEpisode,
            "HentaiHaven",
        ),
    ],
)
def test_provider_registration(url, cls, name):
    provider = resolve_provider(url)
    assert provider.name == name
    assert provider.episode_cls is cls
    assert cls(url).selected_provider == name


@pytest.mark.parametrize(
    "url",
    [
        "https://animeidhentai.com.evil.test/641/example-episode-2-sub-eng",
        "https://animeidhentai.com/search",
        "https://animeidhentai.com/explore",
        "https://hentai.tv/hentai/",
        "https://hentaihaven.xxx/watch/example/episode-two/",
        "https://hentai.tv/hentai/example-episode-2?redirect=evil",
    ],
)
def test_unsupported_urls(url):
    with pytest.raises(ValueError, match="Unsupported URL"):
        resolve_provider(url)


@pytest.mark.parametrize(
    "cls,url", [(HentaiTVEpisode, HENTAI), (AnimeIDHentaiEpisode, ANIMEID)]
)
def test_metadata_selects_matching_episode_from_split_flight(monkeypatch, cls, url):
    slug = url.rstrip("/").split("/")[-1]
    video = {
        "slug": slug,
        "title": "Example & Friends",
        "ep": 2,
        "embedUrl": "https://nhplayer.com/v/example/",
        "tags": ["Comedy"],
        "cover": "/cover.jpg",
        "releasedAt": "2023-09-22T00:00:00Z",
        "description": 'A description with an escaped "quote".',
    }
    other = {**video, "slug": "another-episode-1", "title": "Wrong title"}
    monkeypatch.setattr(
        episode_module,
        "get_response",
        lambda *a, **k: response(
            flight({"notifications": [other], "episode": video}, split=True)
        ),
    )
    episode = cls(url)
    assert episode.title == "Example & Friends"
    assert episode.series_title == "Example & Friends"
    assert episode.episode_number == 2
    assert episode.release_year == "2023"
    assert episode.genres == ["Comedy"]
    assert episode.poster_url.endswith("/cover.jpg")
    assert episode.provider_url == "https://nhplayer.com/v/example/"
    assert "quote" in episode.description


def test_json_ld_graph_and_array_are_supported(monkeypatch):
    video = {
        "@type": "VideoObject",
        "name": "Example",
        "embedUrl": "https://nhplayer.com/v/example/",
    }
    html = (
        '<script type="application/ld+json">'
        + json.dumps([{"@graph": [{"@type": "WebSite"}, video]}])
        + "</script>"
    )
    monkeypatch.setattr(episode_module, "get_response", lambda *a, **k: response(html))
    assert HentaiTVEpisode(HENTAI).provider_url == video["embedUrl"]


def test_flight_parser_skips_non_json_records():
    assert (
        list(page_objects('<script>self.__next_f.push([1,"a:T4,Text\\n"])</script>'))
        == []
    )


def test_flight_parser_reads_records_after_a_text_record():
    """A text record ends by length, the next record can follow on its line."""
    text = '{"@type":"WebPage"}\nmore'
    stream = (
        f"2a:T{len(text.encode()):x},{text}"
        '2b:["$","div",null,{"videoId":1,"indexableSource":"https://a/m.m3u8"}]\n'
    )
    html = "<script>self.__next_f.push(" + json.dumps([1, stream]) + ")</script>"
    assert {"videoId": 1, "indexableSource": "https://a/m.m3u8"} in list(
        page_objects(html)
    )


def test_haven_extracts_hls_and_metadata(monkeypatch):
    data = {
        "videoId": 42,
        "indexableSource": "https://media.example/playlist.m3u8",
        "title": "Example — Episode 2",
        "poster": "https://media.example/cover.jpg",
    }
    monkeypatch.setattr(
        episode_module, "get_response", lambda *a, **k: response(flight(data))
    )
    episode = HentaiHavenEpisode(HAVEN)
    assert episode.stream_url == data["indexableSource"]
    assert episode.series_title == "Example"
    assert episode.episode_number == 2
    assert episode.poster_url == data["poster"]
    assert episode.provider_data[(Audio.JAPANESE, Subtitles.ENGLISH)] == {
        "HentaiHaven": HAVEN
    }


@pytest.mark.parametrize(
    "data", [{}, {"videoId": 42, "indexableSource": "javascript:alert(1)"}]
)
def test_haven_missing_or_invalid_media(monkeypatch, data):
    monkeypatch.setattr(
        episode_module, "get_response", lambda *a, **k: response(flight(data))
    )
    with pytest.raises(RuntimeError):
        assert HentaiHavenEpisode(HAVEN).stream_url


def test_haven_asks_the_stream_api_when_the_page_has_no_source(monkeypatch):
    from aniworld.models.hentaihaven import episode as haven_module

    data = {
        "videoId": 42,
        "slug": "Example-2",
        "permalink": "https://cms.hentaihaven.xxx/watch/example/",
        "title": "Example — Season 1",
        "indexableSource": "$undefined",
    }
    monkeypatch.setattr(
        episode_module, "get_response", lambda *a, **k: response(flight(data))
    )
    posted = []

    def post(url, **kwargs):
        posted.append((url, kwargs["json"]))
        source = {"src": "https://media.example/master.m3u8?hash=x"}
        return response(payload={"status": True, "data": {"sources": [source]}})

    monkeypatch.setattr(haven_module, "post_response", post)
    episode = HentaiHavenEpisode("https://hentaihaven.xxx/watch/example/season-1/")
    assert episode.stream_url == "https://media.example/master.m3u8?hash=x"
    assert posted == [
        (
            haven_module.STREAM_API,
            {"slug": "Example-2", "permalink": data["permalink"], "poster": ""},
        )
    ]
    assert episode.series_title == "Example"
    assert episode.episode_number == 1


def test_haven_series_excludes_recommendations_and_sorts(monkeypatch):
    from aniworld.models.hentaihaven import series as module

    url = "https://hentaihaven.xxx/watch/example/"
    html = "".join(
        f'<a href="{href}">Episode</a>'
        for href in [
            "/watch/example/episode-2/",
            "/watch/example/episode-1/",
            "/watch/other/episode-3/",
            "/watch/example/episode-2/",
            "/watch/other/season-1/",
        ]
    )
    monkeypatch.setattr(module, "get_response", lambda *a, **k: response(html))
    provider = resolve_provider(url)
    assert provider.series_cls is HentaiHavenSeries
    assert [
        episode.episode_number for episode in provider.series_cls(url).episodes
    ] == [1, 2]


@pytest.mark.parametrize(
    "query,base,prefix",
    [
        (search.query_hentai_tv, "https://hentai.tv", "/hentai/"),
        (search.query_animeidhentai, "https://animeidhentai.com", "/641/"),
    ],
)
def test_search_returns_downloadable_urls_and_deduplicates(
    monkeypatch, query, base, prefix
):
    calls = []
    item = {
        "slug": "example-episode-2-sub-eng",
        "wpId": 641,
        "title": "Example",
        "ep": 2,
        "cover": "/cover.jpg",
    }

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return response(
            payload={"videos": [item, item, {**item, "slug": "another-episode-1"}]}
        )

    monkeypatch.setattr(http, "get_response", get)
    results = query(" example & friends ", limit=1)
    assert len(results) == 1
    assert results[0]["url"] == base + prefix + item["slug"]
    assert results[0]["poster"] == base + "/cover.jpg"
    assert resolve_provider(results[0]["url"])
    assert calls[0][1]["params"]["q"] == "example & friends"


@pytest.mark.parametrize(
    "query",
    [search.query_hentai_tv, search.query_animeidhentai, search.query_hentaihaven],
)
def test_search_empty_and_invalid_limits(query):
    assert query("anything", limit=0) == []
    assert query(" ") == []
    with pytest.raises(ValueError):
        query("anything", limit=-1)


def test_haven_search_filters_and_paginates(monkeypatch):
    pages = iter(
        [
            {
                "data": [{"slug": "unrelated", "title": {"rendered": "Other"}}],
                "totalPages": 2,
            },
            {
                "data": [
                    {
                        "slug": "example",
                        "title": {"rendered": "Example &amp; Friends"},
                        "meta": {"vraven_remote_thumbnail": "/cover.jpg"},
                    }
                ],
                "totalPages": 2,
            },
        ]
    )
    calls = []

    def get(url, **kwargs):
        calls.append(kwargs["params"])
        return response(payload=next(pages))

    monkeypatch.setattr(http, "get_response", get)
    results = search.query_hentaihaven("example", limit=1)
    assert results[0]["title"] == "Example & Friends"
    assert results[0]["url"] == "https://hentaihaven.xxx/watch/example/"
    assert [call["page"] for call in calls] == [1, 2]


@pytest.mark.parametrize(
    "url,cls",
    [
        (HENTAI, HentaiTVEpisode),
        (ANIMEID, AnimeIDHentaiEpisode),
        (HAVEN, HentaiHavenEpisode),
    ],
)
@pytest.mark.parametrize("no_menu", [False, True])
def test_cli_download_dispatch(monkeypatch, url, cls, no_menu):
    monkeypatch.setattr(
        entry,
        "parse_args",
        lambda: SimpleNamespace(
            url=[url], action=None, web_ui=False, episode_file=None
        ),
    )
    monkeypatch.setattr(entry, "ensure_patchright_chromium", lambda: None)
    monkeypatch.setattr(entry, "set_terminal_title", lambda: None)
    monkeypatch.setenv("ANIWORLD_NO_MENU", "1" if no_menu else "0")
    calls = []
    monkeypatch.setattr(cls, "download", lambda self: calls.append(self.url))
    assert entry.aniworld() == 0
    assert calls == [url]


def test_http_fallback_preserves_request_options(monkeypatch):
    from curl_cffi import requests

    calls = []
    monkeypatch.setattr(
        http.GLOBAL_SESSION, "get", lambda *a, **k: SimpleNamespace(status_code=403)
    )

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return response(payload={"videos": []})

    monkeypatch.setattr(requests, "get", get)
    assert http.get_response(
        "https://hentai.tv/api/search", params={"q": "example"}
    ).json() == {"videos": []}
    assert calls[0][1]["impersonate"] == "chrome"
    assert calls[0][1]["params"] == {"q": "example"}


MASTER_WITH_SUBTITLES = """#EXTM3U
#EXT-X-MEDIA:URI="snd/a.m3u8",TYPE=AUDIO,GROUP-ID="audio",LANGUAGE="en",DEFAULT=YES
#EXT-X-MEDIA:URI="s/de.vtt",TYPE=SUBTITLES,GROUP-ID="subs",LANGUAGE="de",NAME="German"
#EXT-X-MEDIA:URI="s/en.vtt",TYPE=SUBTITLES,GROUP-ID="subs",LANGUAGE="en",NAME="English"
#EXT-X-STREAM-INF:BANDWIDTH=2000000,AUDIO="audio",SUBTITLES="subs"
v.m3u8
"""


@pytest.mark.parametrize("system", ["Windows", "Linux", "Darwin"])
def test_haven_download_uses_shared_hls_pipeline_and_skips_existing(
    monkeypatch, tmp_path, system
):
    import ffmpeg

    from aniworld.models.common import common
    from aniworld.models.hentaihaven import episode as haven_module

    monkeypatch.setattr(common, "platform", SimpleNamespace(system=lambda: system))
    dependencies = []
    monkeypatch.setattr(
        common.DependencyManager,
        "fetch_binary",
        lambda self, name: dependencies.append(name),
    )
    source = "https://media.example/playlist.m3u8"
    data = {
        "videoId": 42,
        "indexableSource": source,
        "title": "Example — Episode 2",
        "poster": "",
    }
    monkeypatch.setattr(
        episode_module, "get_response", lambda *a, **k: response(flight(data))
    )
    fetched = []

    def get_response(url, **kwargs):
        fetched.append(url)
        if url == source:
            return response(MASTER_WITH_SUBTITLES)
        return SimpleNamespace(content=b"WEBVTT\n", raise_for_status=lambda: None)

    monkeypatch.setattr(haven_module, "get_response", get_response)
    monkeypatch.setattr(
        common,
        "check_downloaded",
        lambda path: {
            "video_langs": ["eng"] if path.exists() else [],
            "audio_langs": ["jpn"] if path.exists() else [],
        },
    )
    calls = []

    def rendition(stream, temp_prefix, headers, audio, label):
        calls.append((stream, audio))
        video = temp_prefix.with_suffix(".hls_video.mp4")
        audio_path = temp_prefix.with_suffix(".hls_audio.mp4")
        video.touch()
        audio_path.touch()
        return video, audio_path

    def run_ffmpeg(node, label=""):
        # Stand in for FFmpeg by creating whatever file the command writes
        Path(ffmpeg.compile(node)[-1]).touch()

    muxes = []
    monkeypatch.setattr(
        ffmpeg,
        "probe",
        lambda path: {
            "streams": [{"codec_type": "subtitle", "tags": {"language": "eng"}}]
            if muxes
            else []
        },
    )

    def mux(node, label=""):
        args = ffmpeg.compile(node)
        muxes.append(args)
        Path(args[-1]).write_text("muxed")

    def finalize(temp, target, label, owner):
        temp.replace(target)

    monkeypatch.setattr(common, "_hls_rendition_download", rendition)
    monkeypatch.setattr(common, "_run_ffmpeg_with_progress", run_ffmpeg)
    monkeypatch.setattr(common, "_finalize_episode", finalize)
    monkeypatch.setattr(haven_module, "_run_ffmpeg_with_progress", mux)
    episode = HentaiHavenEpisode(HAVEN, selected_path=tmp_path)
    episode.download()
    assert episode._episode_path.read_text() == "muxed"
    episode.download()
    assert calls == [(source, "jpn")]
    assert fetched == [source, "https://media.example/s/en.vtt"]
    assert len(muxes) == 1
    assert "language=eng" in muxes[0]
    assert sorted(path.name for path in episode._folder_path.iterdir()) == [
        episode._episode_path.name
    ]
    assert dependencies == (["ffmpeg", "ffmpeg"] if system == "Windows" else [])


@pytest.mark.parametrize("extension,codec", [("mkv", "srt"), ("mp4", "mov_text")])
def test_haven_download_retries_failed_subtitles(
    monkeypatch, tmp_path, extension, codec
):
    import ffmpeg

    from aniworld.models.hentaihaven import episode as haven_module

    data = {"videoId": 42, "indexableSource": "https://media.example/m"}
    monkeypatch.setattr(
        episode_module, "get_response", lambda *a, **k: response(flight(data))
    )
    episode = HentaiHavenEpisode(HAVEN, selected_path=tmp_path)
    monkeypatch.setattr(
        HentaiHavenEpisode, "_file_extension", property(lambda self: extension)
    )
    original_subtitles = [{"codec_type": "subtitle", "tags": {"language": "deu"}}]
    monkeypatch.setattr(ffmpeg, "probe", lambda path: {"streams": original_subtitles})
    downloads = []

    def download(self):
        if not self._episode_path.exists():
            downloads.append(self.url)
            self._folder_path.mkdir(parents=True)
            self._episode_path.write_text("video")

    requests = []

    def broken(url, **kwargs):
        requests.append(url)
        if url == episode.stream_url:
            return response(MASTER_WITH_SUBTITLES)
        if requests.count(url) == 1:
            raise RuntimeError("subtitle host down")
        return SimpleNamespace(content=b"WEBVTT\n")

    muxes = []

    def mux(node, label=""):
        args = ffmpeg.compile(node)
        muxes.append(args)
        assert args[args.index("-c:s:1") + 1] == codec
        assert args[args.index("-metadata:s:s:1") + 1] == "language=eng"
        assert [args[i + 1] for i, arg in enumerate(args) if arg == "-map"] == [
            "0",
            "1",
        ]
        Path(args[-1]).write_text("subtitled video")
        original_subtitles.append(
            {"codec_type": "subtitle", "tags": {"language": "eng"}}
        )

    monkeypatch.setattr(haven_module, "episode_download", download)
    monkeypatch.setattr(haven_module, "get_response", broken)
    monkeypatch.setattr(haven_module, "_run_ffmpeg_with_progress", mux)
    episode.download()
    assert episode._episode_path.read_text() == "video"
    episode.download()
    assert episode._episode_path.read_text() == "subtitled video"
    episode.download()
    assert downloads == [HAVEN]
    assert len(muxes) == 1
    assert requests.count("https://media.example/s/en.vtt") == 2
    assert list(episode._folder_path.iterdir()) == [episode._episode_path]


@pytest.mark.parametrize("language", ["en", "eng", "ENG"])
def test_haven_existing_english_subtitles_are_preserved(
    monkeypatch, tmp_path, language
):
    from aniworld.models.hentaihaven import episode as haven_module

    episode = HentaiHavenEpisode(HAVEN, selected_path=tmp_path)
    monkeypatch.setattr(haven_module, "episode_download", lambda self: None)
    monkeypatch.setattr(HentaiHavenEpisode, "_episode_path", tmp_path / "video.mkv")
    episode._episode_path.write_text("original video")
    monkeypatch.setattr(
        haven_module.ffmpeg,
        "probe",
        lambda path: {
            "streams": [{"codec_type": "subtitle", "tags": {"language": language}}]
        },
    )
    monkeypatch.setattr(
        haven_module,
        "get_response",
        lambda *_: pytest.fail("unexpected subtitle request"),
    )

    episode.download()
    assert episode._episode_path.read_text() == "original video"


@pytest.mark.parametrize("extension", ["mkv", "mp4"])
def test_haven_without_subtitle_track_downloads_as_is(monkeypatch, tmp_path, extension):
    from aniworld.models.hentaihaven import episode as haven_module

    monkeypatch.setattr(HentaiHavenEpisode, "stream_url", "https://media.example/m")
    path = tmp_path / f"video.{extension}"
    path.write_text("original video")
    monkeypatch.setattr(HentaiHavenEpisode, "_episode_path", path)
    monkeypatch.setattr(haven_module, "episode_download", lambda self: None)
    monkeypatch.setattr(haven_module.ffmpeg, "probe", lambda path: {"streams": []})
    monkeypatch.setattr(
        haven_module,
        "_run_ffmpeg_with_progress",
        lambda *_args, **_kwargs: pytest.fail("unexpected mux"),
    )
    monkeypatch.setattr(
        haven_module,
        "get_response",
        lambda url, **k: response("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nv.m3u8\n"),
    )
    assert HentaiHavenEpisode(HAVEN).subtitle_url is None
    HentaiHavenEpisode(HAVEN).download()
    assert path.read_text() == "original video"


def test_manual_hls_fetch_leaves_fmp4_playlists_alone(monkeypatch, tmp_path):
    """Concatenating fMP4 segments without their init segment is unplayable."""
    from aniworld.models.common import common

    playlist = '#EXTM3U\n#EXT-X-MAP:URI="i.mp4"\n#EXTINF:2,\nhb1.jpg\n#EXT-X-ENDLIST\n'

    class Session:
        def get(self, url, **kwargs):
            return SimpleNamespace(text=playlist, raise_for_status=lambda: None)

    monkeypatch.setattr(common.niquests, "Session", Session)
    target = tmp_path / "out.seg.ts"
    with pytest.raises(common._HLSManualUnsupported):
        common._download_hls_manual("https://media.example/v.m3u8", {}, target)
    assert not target.exists()


@pytest.mark.parametrize(
    "url,cls,title",
    [
        (
            "https://hentai.tv/hentai/hamehara-sore-sekuhara-desu-episode-1-p83",
            HentaiTVEpisode,
            "Hamehara Sore Sekuhara Desu",
        ),
        (
            "https://animeidhentai.com/inaka-ni-wa-kore-kurai-shika-goraku-ga-nai-episode-1",
            AnimeIDHentaiEpisode,
            "Inaka Ni Wa Kore Kurai Shika Goraku Ga Nai",
        ),
    ],
)
def test_reference_episode_urls_and_slug_fallback(monkeypatch, url, cls, title):
    monkeypatch.setattr(
        episode_module.HentaiTVEpisode, "_metadata", property(lambda self: {})
    )
    assert resolve_provider(url).episode_cls is cls
    episode = cls(url)
    assert episode.episode_number == 1
    assert episode.series_title == title


def test_reference_haven_series_url():
    url = "https://hentaihaven.xxx/watch/ane-wa-yanmama-junyuu-chuu/"
    assert resolve_provider(url).series_cls is HentaiHavenSeries
