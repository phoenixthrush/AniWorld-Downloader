"""Mediathek channels, subtitles and the per-download options, offline."""

import json
from pathlib import Path

import pytest

from aniworld.models.mediathek import MediathekEpisode, api, subtitles
from aniworld.models.mediathek import episode as episode_module
from aniworld.providers import resolve_provider

ARD_PAGE = "https://www.ardmediathek.de/video/Y3JpZDovL3dkci5kZS9CZWl0cmFn"


def _entry(**overrides):
    entry = {
        "channel": "WDR",
        "topic": "Tatort",
        "title": "Tatort: Narrentanz",
        "timestamp": 1794780000,
        "duration": 5340,
        "url_website": ARD_PAGE,
        "url_subtitle": "https://example.invalid/sub.xml",
        "url_video": "https://cdn.example.invalid/sd.mp4",
        "url_video_low": "https://cdn.example.invalid/low.mp4",
        "url_video_hd": "https://cdn.example.invalid/hd.mp4",
        "id": "abc",
    }
    entry.update(overrides)
    return entry


def _episode(tmp_path, **kwargs):
    entry = kwargs.pop("entry", _entry())
    return MediathekEpisode(
        api.entry_url(entry), selected_path=str(tmp_path), entry=entry, **kwargs
    )


# -----------------------------
# Channels
# -----------------------------


def test_every_mediathekview_channel_is_offered():
    assert len(api.CHANNELS) == 30
    for channel in ("ARD-alpha", "ZDFneo", "KiKA", "PHOENIX", "DW", "ARTE.FR", "SR"):
        assert channel in api.CHANNELS


@pytest.mark.parametrize(
    "url",
    [
        "https://www.kika.de/verrueckt-nach-tiktok/videos/folge-102",
        "https://www.phoenix.de/sendungen/dokumentationen/x-a-123.html",
        "https://p.dw.com/p/4abcd",
        "https://www.zdfheute.de/video/politik/x-100.html",
        "https://www.sr-mediathek.de/index.php?seite=7&id=1",
    ],
)
def test_new_channel_pages_resolve(url):
    assert resolve_provider(url).name == "Mediathek"


@pytest.mark.parametrize(
    ("channel", "label", "language"),
    [
        ("ARTE.FR", "Arte (FR)", "fr"),
        ("ZDF-tivi", "ZDFtivi", "de"),
        ("Funk.net", "funk", "de"),
        ("KiKA", "KiKA", "de"),
    ],
)
def test_channel_labels_and_languages(tmp_path, channel, label, language):
    episode = _episode(tmp_path, entry=_entry(channel=channel))
    assert episode.channel == label
    assert episode.language_code == language
    assert label in episode_module.MEDIATHEK_CHANNELS


# -----------------------------
# Subtitle conversion
# -----------------------------

EBU_TT = """<?xml version="1.0" encoding="UTF-8"?>
<tt:tt xmlns:tt="http://www.w3.org/ns/ttml" xmlns:ttp="http://www.w3.org/ns/ttml#parameter"
       ttp:timeBase="media" xml:lang="de-DE">
  <tt:body><tt:div>
    <tt:p begin="00:00:00.000" end="00:00:00.200"><tt:span/></tt:p>
    <tt:p begin="00:00:04.200" end="00:00:07.240">
      <tt:span style="a">Gib ihn mir!</tt:span>
      <tt:br />
      <tt:span style="b">Gib ihn   ihm doch!</tt:span>
    </tt:p>
  </tt:div></tt:body>
</tt:tt>"""

ORF_TTML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="no"?>'
    '<tt xmlns="http://www.w3.org/ns/ttml"><head>TTML</head><body><div>'
    '<p begin="5.30s" end="8.70s">Ein Aufstand,  &lt;br/&gt;der zur Revolution ausartet.</p>'
    "</div></body></tt>"
)

VTT = """WEBVTT

STYLE
::cue(.red) {
 color: red;
}

00:00:13.000 --> 00:00:16.000 line:91% align:right
<c.red>U/T</c>

01:02:35.680 --> 01:02:39.760 line:83% align:center
Ich hatte das Porträt einer
Freundin &amp; Ton gefertigt.
"""


def test_ebu_tt_becomes_srt():
    assert subtitles.to_srt(EBU_TT) == (
        "1\n00:00:04,200 --> 00:00:07,240\nGib ihn mir!\nGib ihn ihm doch!\n"
    )


def test_orf_escaped_line_breaks_and_second_offsets():
    assert subtitles.to_srt(ORF_TTML) == (
        "1\n00:00:05,300 --> 00:00:08,700\n"
        "Ein Aufstand,\nder zur Revolution ausartet.\n"
    )


@pytest.mark.parametrize(
    ("value", "seconds"),
    [
        ("00:00:10.08", 10.08),
        ("00:01:02:05", 62.2),  # 5 frames at 25 fps
        ("2500ms", 2.5),
        ("1.5m", 90.0),
        ("50000t", 5.0),  # with tickRate 10000
    ],
)
def test_ttml_time_forms(value, seconds):
    assert subtitles._ttml_time(value, 25, 10000) == pytest.approx(seconds)


def test_tape_start_offset_is_removed():
    ttml = EBU_TT.replace("00:00:00.000", "10:00:00.000").replace(
        "00:00:00.200", "10:00:00.200"
    )
    ttml = ttml.replace("00:00:04.200", "10:00:04.200").replace(
        "00:00:07.240", "10:00:07.240"
    )
    assert subtitles.to_srt(ttml).startswith("1\n00:00:04,200 --> 00:00:07,240")


def test_webvtt_drops_styles_settings_and_tags():
    assert subtitles.to_srt(VTT) == (
        "1\n00:00:13,000 --> 00:00:16,000\nU/T\n\n"
        "2\n01:02:35,680 --> 01:02:39,760\n"
        "Ich hatte das Porträt einer\nFreundin & Ton gefertigt.\n"
    )


@pytest.mark.parametrize("text", ["", "just text", "<tt><body/></tt>", "<broken"])
def test_unusable_files_are_rejected(text):
    with pytest.raises(subtitles.SubtitleError):
        subtitles.to_srt(text)


def test_save_writes_a_sidecar_once(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(subtitles, "fetch", lambda url: calls.append(url) or VTT)
    video = tmp_path / "Show S01E001.mkv"

    written = subtitles.save("https://x/sub.vtt", video, "de")
    assert written == tmp_path / "Show S01E001.de.srt"
    assert written.read_text(encoding="utf-8").startswith("1\n00:00:13,000")

    subtitles.save("https://x/sub.vtt", video, "de")
    assert calls == ["https://x/sub.vtt"]


def test_a_broken_subtitle_never_raises(tmp_path, monkeypatch):
    def broken(url):
        raise ConnectionError("offline")

    monkeypatch.setattr(subtitles, "fetch", broken)
    folder = tmp_path / "show"
    assert subtitles.save("https://x/sub.xml", folder / "a.mkv") is None
    assert not folder.exists()


# -----------------------------
# Per-download options
# -----------------------------


def test_quality_and_subtitles_default_to_the_settings(tmp_path, monkeypatch):
    monkeypatch.delenv("ANIWORLD_MEDIATHEK_QUALITY", raising=False)
    monkeypatch.delenv("ANIWORLD_MEDIATHEK_SUBTITLES", raising=False)
    episode = _episode(tmp_path)
    assert (episode.quality, episode.subtitles) == ("hd", True)

    monkeypatch.setenv("ANIWORLD_MEDIATHEK_QUALITY", "low")
    monkeypatch.setenv("ANIWORLD_MEDIATHEK_SUBTITLES", "0")
    assert (episode.quality, episode.subtitles) == ("low", False)
    assert episode.stream_url.endswith("low.mp4")


def test_a_download_overrides_the_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("ANIWORLD_MEDIATHEK_QUALITY", "low")
    episode = _episode(tmp_path, quality="sd", subtitles=False)
    assert (episode.quality, episode.subtitles) == ("sd", False)
    assert episode.stream_url.endswith("sd.mp4")
    # An unknown choice falls back to the setting rather than failing.
    assert _episode(tmp_path, quality="4k").quality == "low"


def _fake_video_download(episode):
    episode._episode_path.parent.mkdir(parents=True, exist_ok=True)
    episode._episode_path.write_bytes(b"video")


def test_download_saves_subtitles_after_the_video(tmp_path, monkeypatch):
    monkeypatch.setattr(episode_module, "episode_download", _fake_video_download)
    monkeypatch.setattr(subtitles, "fetch", lambda url: VTT)
    episode = _episode(tmp_path, entry=_entry(channel="ARTE.FR"), subtitles=True)

    episode.download()
    assert episode._episode_path.with_suffix(".fr.srt").exists()


def test_download_without_subtitles(tmp_path, monkeypatch):
    monkeypatch.setattr(episode_module, "episode_download", _fake_video_download)
    monkeypatch.setattr(subtitles, "fetch", lambda url: pytest.fail("fetched"))
    episode = _episode(tmp_path, subtitles=False)

    episode.download()
    assert sorted(p.suffix for p in episode._episode_path.parent.iterdir()) == [".mkv"]


def test_programmes_without_subtitles_download_fine(tmp_path, monkeypatch):
    monkeypatch.setattr(episode_module, "episode_download", _fake_video_download)
    episode = _episode(tmp_path, entry=_entry(url_subtitle=""), subtitles=True)
    episode.download()
    assert episode.download_subtitles() is None


# -----------------------------
# Queue, worker and settings
# -----------------------------


def test_queue_keeps_the_options_per_episode(client):
    from aniworld.web import db

    response = client.post(
        "/api/download",
        json={
            "title": "Tatort",
            "episodes": [f"{ARD_PAGE}#mvid=a"],
            "provider": "WDR",
            "mediathek_quality": "SD",
            "mediathek_subtitles": False,
        },
    )
    assert response.status_code == 200
    item = db.get_queue_item(response.get_json()["queue_id"])
    assert json.loads(item["episodes"]) == [
        {
            "url": f"{ARD_PAGE}#mvid=a",
            "mediathek_quality": "sd",
            "mediathek_subtitles": False,
        }
    ]


def test_queue_rejects_an_unknown_quality(client):
    response = client.post(
        "/api/download",
        json={"episodes": [ARD_PAGE], "mediathek_quality": "4k"},
    )
    assert response.status_code == 400


def test_other_sites_queue_plain_urls(client):
    from aniworld.web import db

    response = client.post("/api/download", json={"episodes": ["https://x/ep1"]})
    item = db.get_queue_item(response.get_json()["queue_id"])
    assert json.loads(item["episodes"]) == ["https://x/ep1"]


def test_worker_builds_the_episode_with_the_options(tmp_path):
    from aniworld.web import worker

    url, extra = worker._episode_request(
        {
            "url": f"{ARD_PAGE}#mvid=a",
            "mediathek_quality": "low",
            "mediathek_subtitles": True,
        }
    )
    provider, episode = worker._build_episode(
        url,
        extra,
        {"language": "German Dub", "provider": "WDR"},
        str(tmp_path),
    )
    assert provider.name == "Mediathek"
    assert (episode.quality, episode.subtitles) == ("low", True)


def test_settings_hold_the_defaults(monkeypatch):
    import os

    from aniworld.web import settings_store
    from aniworld.web.settings_store import SettingsError, update_settings

    settings = settings_store.read_settings()
    assert settings["mediathek_quality"] == "hd"
    assert settings["mediathek_subtitles"] is True
    assert settings["available_mediathek_qualities"] == ["hd", "sd", "low"]

    update_settings({"mediathek_quality": "SD", "mediathek_subtitles": False})
    assert os.environ["ANIWORLD_MEDIATHEK_QUALITY"] == "sd"
    assert os.environ["ANIWORLD_MEDIATHEK_SUBTITLES"] == "0"

    with pytest.raises(SettingsError):
        update_settings({"mediathek_quality": "4k"})


# -----------------------------
# Incomplete downloads
# -----------------------------


def _record_downloads(monkeypatch, lengths):
    """Fake downloads whose file length depends on the quality fetched."""
    fetched = []

    def fake_download(episode):
        fetched.append(episode.quality)
        _fake_video_download(episode)

    monkeypatch.setattr(episode_module, "episode_download", fake_download)
    monkeypatch.setattr(
        episode_module,
        "_container_duration",
        lambda path: lengths[fetched[-1]],
    )
    return fetched


def test_a_short_file_is_retried_lower_first(tmp_path, monkeypatch):
    # SRF's CDN drops segments of single renditions now and then.
    fetched = _record_downloads(monkeypatch, {"sd": 120.0, "low": 5340.0})
    episode = _episode(tmp_path, quality="sd", subtitles=False)

    episode.download()
    assert fetched == ["sd", "low"], "lower qualities before higher ones"
    assert episode._episode_path.exists()
    assert episode.quality == "sd", "the choice itself stays as it was"
    assert [p.name for p in episode._episode_path.parent.iterdir()] == [
        episode._episode_path.name
    ], "set-aside files are cleaned up"


def test_higher_qualities_come_after_the_lower_ones(tmp_path, monkeypatch):
    fetched = _record_downloads(monkeypatch, {"sd": 120.0, "low": 120.0, "hd": 5340.0})
    _episode(tmp_path, quality="sd", subtitles=False).download()
    assert fetched == ["sd", "low", "hd"]


def test_a_missing_quality_isnt_downloaded_twice(tmp_path, monkeypatch):
    # No HD: "hd" falls back to the SD stream, which is then not fetched again.
    fetched = _record_downloads(monkeypatch, {"hd": 120.0, "sd": 120.0, "low": 5340.0})
    entry = _entry(url_video_hd="")
    _episode(tmp_path, entry=entry, quality="hd", subtitles=False).download()
    assert fetched == ["hd", "low"]


def test_when_every_quality_is_short_the_longest_file_stays(tmp_path, monkeypatch):
    # MediathekView's listed length can be off: nothing must end up deleted.
    fetched = _record_downloads(monkeypatch, {"sd": 100.0, "low": 300.0, "hd": 200.0})
    episode = _episode(tmp_path, quality="sd", subtitles=False)

    with pytest.raises(ValueError, match="Kept the low file"):
        episode.download()
    assert fetched == ["sd", "low", "hd"]
    assert episode._episode_path.exists()
    assert [p.name for p in episode._episode_path.parent.iterdir()] == [
        episode._episode_path.name
    ]


def test_a_short_file_already_on_disk_is_not_lost(tmp_path, monkeypatch):
    episode = _episode(tmp_path, quality="hd", subtitles=False)
    _fake_video_download(episode)
    episode._episode_path.write_bytes(b"old copy")
    lengths = {"old": 100.0}
    calls = []

    def skip_existing(ep):
        # The shared download skips a file that is already there.
        calls.append(ep.quality)
        if not ep._episode_path.exists():
            _fake_video_download(ep)

    monkeypatch.setattr(episode_module, "episode_download", skip_existing)
    monkeypatch.setattr(
        episode_module,
        "_container_duration",
        lambda path: lengths["old"] if path.read_bytes() == b"old copy" else 50.0,
    )
    with pytest.raises(ValueError, match="shorter than listed"):
        episode.download()
    # The old copy was the longest, so it is what stays.
    assert episode._episode_path.read_bytes() == b"old copy"


def test_a_failing_later_attempt_keeps_the_earlier_file(tmp_path, monkeypatch):
    # hd comes out short and is set aside, then the network drops during sd.
    episode = _episode(tmp_path, quality="hd", subtitles=False)
    attempts = []

    def download(ep):
        attempts.append(ep.quality)
        if ep.quality == "hd":
            _fake_video_download(ep)
        else:
            raise ConnectionError("network gone")

    monkeypatch.setattr(episode_module, "episode_download", download)
    monkeypatch.setattr(episode_module, "_container_duration", lambda path: 120.0)
    with pytest.raises(ConnectionError):
        episode.download()
    assert attempts == ["hd", "sd"]
    assert [p.name for p in episode._episode_path.parent.iterdir()] == [
        episode._episode_path.name
    ], "the short hd file is back in place, nothing else left over"


def test_a_programme_without_streams_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(
        episode_module, "episode_download", lambda ep: pytest.fail("downloaded")
    )
    entry = _entry(url_video="", url_video_hd="", url_video_low="")
    with pytest.raises(ValueError, match="No video stream"):
        _episode(tmp_path, entry=entry, subtitles=False).download()


def test_a_complete_file_is_kept(tmp_path, monkeypatch):
    # A few seconds off the listed length is normal.
    fetched = _record_downloads(monkeypatch, {"hd": 5334.5})
    episode = _episode(tmp_path, subtitles=False)
    episode.download()
    assert fetched == ["hd"]


def test_unknown_lengths_are_not_second_guessed(tmp_path, monkeypatch):
    fetched = _record_downloads(monkeypatch, {"hd": None})
    episode = _episode(tmp_path, subtitles=False)
    episode.download()
    assert fetched == ["hd"]


# -----------------------------
# Resolutions
# -----------------------------


def _fake_ffmpeg(monkeypatch, banners):
    """Answer FFmpeg probes per URL with the stderr a real probe prints."""
    calls = []

    class Result:
        def __init__(self, stderr):
            self.stderr = stderr

    def fake_run(cmd, **kwargs):
        url = cmd[-1]
        calls.append(url)
        return Result(banners[url])

    api.clear_cache()
    monkeypatch.setattr(api.subprocess, "run", fake_run)
    return calls


def _banner(height):
    width = height * 16 // 9
    return f"  Stream #0:0: Video: h264 (High), yuv420p, {width}x{height}, 25 fps\n"


def test_options_carry_the_real_resolutions(monkeypatch):
    # KiKA's "hd" is 720p, which is why the labels come from the streams.
    entry = _entry(channel="KiKA")
    _fake_ffmpeg(
        monkeypatch,
        {
            entry["url_video_hd"]: _banner(720),
            entry["url_video"]: _banner(576),
            entry["url_video_low"]: _banner(360),
        },
    )
    assert api.quality_options(entry) == [
        {"value": "hd", "height": 720, "label": "720p"},
        {"value": "sd", "height": 576, "label": "576p"},
        {"value": "low", "height": 360, "label": "360p"},
    ]
    api.clear_cache()


def test_a_master_playlist_counts_its_best_rendition(monkeypatch):
    entry = _entry(url_video_hd="", url_video_low="")
    _fake_ffmpeg(
        monkeypatch, {entry["url_video"]: _banner(360) + _banner(1080) + _banner(720)}
    )
    assert api.quality_options(entry) == [
        {"value": "sd", "height": 1080, "label": "1080p"}
    ]
    api.clear_cache()


def test_gone_streams_are_dropped_and_unreadable_ones_stay(monkeypatch):
    entry = _entry()
    calls = _fake_ffmpeg(
        monkeypatch,
        {
            entry["url_video_hd"]: "HTTP error 404 Not Found\n",
            entry["url_video"]: "something odd\n",
            entry["url_video_low"]: _banner(360),
        },
    )
    assert api.quality_options(entry) == [
        {"value": "sd", "height": None, "label": "Medium"},
        {"value": "low", "height": 360, "label": "360p"},
    ]
    # Known answers are cached, the unreadable one is asked again.
    api.quality_options(entry)
    assert calls.count(entry["url_video"]) == 2
    assert calls.count(entry["url_video_low"]) == 1
    api.clear_cache()


def test_qualities_endpoint_reads_the_newest_episode(client, monkeypatch):
    from aniworld.web.views import api_media  # noqa: F401  (route registered)

    newest = _entry(id="new", url_website=ARD_PAGE + "new")
    older = _entry(id="old", url_website=ARD_PAGE + "old", timestamp=1794000000)
    monkeypatch.setattr(
        api, "show_entries", lambda channel, topic, **_: [newest, older]
    )
    monkeypatch.setattr(
        api,
        "quality_options",
        lambda entry: (
            [{"value": "hd", "height": 1080, "label": "1080p"}]
            if entry is older
            else []
        ),
    )
    response = client.get(
        "/api/mediathek/qualities",
        query_string={"url": api.show_url("WDR", "Tatort")},
    )
    assert response.get_json() == {
        "qualities": [{"value": "hd", "height": 1080, "label": "1080p"}]
    }


# -----------------------------
# Audio language
# -----------------------------

ARTE_HLS = "https://manifest-arte.akamaized.net/api/manifest/v1/Generate/x/{}/XQ+KS+CHEV1/1-A.m3u8"
ARTE_MP4 = (
    "https://arteptweb-a.akamaihd.net/am/ptweb/1-A_EQ_0_{}_11402214_MP4-1500_X.mp4"
)


@pytest.mark.parametrize(
    ("channel", "url", "code", "badge"),
    [
        ("ARTE.DE", ARTE_HLS.format("VA-STA"), "deu", "DE"),
        ("ARTE.DE", ARTE_HLS.format("VOA"), "deu", "DE"),
        ("ARTE.FR", ARTE_HLS.format("VOF-STMF"), "fra", "FR"),
        ("ARTE.FR", ARTE_HLS.format("VFAUD"), "fra", "FR"),
        # Arte (IT) is mostly the French original with Italian subtitles.
        ("ARTE.IT", ARTE_HLS.format("VOF-STE%5BITA%5D"), "fra", "FR"),
        ("ARTE.EN", ARTE_HLS.format("VE%5BANG%5D-STE%5BANG%5D"), "eng", "EN"),
        ("ARTE.PL", ARTE_MP4.format("VE%5BPOL%5D"), "pol", "PL"),
        ("ARTE.EN", ARTE_MP4.format("VO-STE%5BANG%5D"), "und", "OV"),
        # Some manifests carry only the language in the path.
        ("ARTE.DE", ARTE_HLS.format("de"), "deu", "DE"),
        ("ARTE.FR", ARTE_HLS.format("fr"), "fra", "FR"),
        ("ARTE.ES", "https://example.invalid/plain.mp4", "und", "OV"),
        ("ZDF", "https://example.invalid/plain.mp4", "deu", "DE"),
    ],
)
def test_audio_language(tmp_path, channel, url, code, badge):
    entry = _entry(channel=channel, url_video=url, url_video_hd="", url_video_low="")
    assert api.audio_language(entry) == code
    episode = _episode(tmp_path, entry=entry)
    assert (episode.audio_language, episode.audio_badge) == (code, badge)


def test_episode_rows_show_the_audio_badge(client, monkeypatch):
    french = _entry(
        channel="ARTE.IT",
        topic="Cultura - Arte",
        title="Émile Zola, fotografo (Originalversion mit Untertitel)",
        url_website="https://www.arte.tv/it/videos/131023-000-A/emile-zola/",
        url_video=ARTE_HLS.format("VOF-STE%5BITA%5D"),
        url_video_hd="",
        url_video_low="",
    )
    monkeypatch.setattr(api, "show_entries", lambda channel, topic, **_: [french])
    season = api.show_url("ARTE.IT", "Cultura - Arte", season=0)
    response = client.get("/api/episodes", query_string={"url": season})
    [row] = response.get_json()["episodes"]
    assert row["available_languages"] == ["Italian Sub"]


# -----------------------------
# Geo restrictions
# -----------------------------

ORF_AT = "https://apasfiis.sf.apa.at/ipad/cms-austria/2026/11/x_QXA.mp4/chunklist_b620000.m3u8"
ORF_WORLD = "https://apasfiis.sf.apa.at/ipad/cms-worldwide/2026/11/x_QXA.mp4/chunklist_b620000.m3u8"


def _orf_entry(url):
    return _entry(
        channel="ORF",
        topic="Soko Kitzbühel Staffel 2",
        title="Soko Kitzbühel (7/12): Farben des Todes",
        url_website="https://on.orf.at/video/14347686/soko",
        url_video=url,
        url_video_hd=url,
        url_video_low=url,
        url_subtitle="",
    )


def _fake_redirect(monkeypatch, final_url):
    class Response:
        url = final_url

        def close(self):
            pass

    monkeypatch.setattr(api.GLOBAL_SESSION, "get", lambda *a, **k: Response())


def test_austria_only_programmes_are_marked():
    assert api.geo_restriction(_orf_entry(ORF_AT)) == "AT"
    assert api.geo_restriction(_orf_entry(ORF_WORLD)) is None


def test_a_blocked_programme_fails_before_downloading(tmp_path, monkeypatch):
    monkeypatch.setattr(
        episode_module, "episode_download", lambda ep: pytest.fail("downloaded")
    )
    _fake_redirect(
        monkeypatch,
        "https://apasfiis.sf.apa.at/gp_nas/_definst_/nas/gp/online/"
        "insert_geoprotection_hr.smil/playlist.m3u8",
    )
    episode = _episode(tmp_path, entry=_orf_entry(ORF_AT))
    with pytest.raises(ValueError, match="only be shown in Austria"):
        episode.download()


def test_an_austria_only_programme_downloads_in_austria(tmp_path, monkeypatch):
    monkeypatch.setattr(episode_module, "episode_download", _fake_video_download)
    monkeypatch.setattr(episode_module, "_container_duration", lambda path: None)
    _fake_redirect(monkeypatch, ORF_AT)
    episode = _episode(tmp_path, entry=_orf_entry(ORF_AT))
    episode.download()
    assert episode._episode_path.exists()


def test_worldwide_programmes_skip_the_check(tmp_path, monkeypatch):
    monkeypatch.setattr(episode_module, "episode_download", _fake_video_download)
    monkeypatch.setattr(episode_module, "_container_duration", lambda path: None)
    monkeypatch.setattr(api, "geo_blocked", lambda url: pytest.fail("checked"))
    _episode(tmp_path, entry=_orf_entry(ORF_WORLD)).download()


def test_episode_rows_flag_austria_only(client, monkeypatch):
    monkeypatch.setattr(
        api, "show_entries", lambda channel, topic, **_: [_orf_entry(ORF_AT)]
    )
    season = api.show_url("ORF", "Soko Kitzbühel", season=2)
    response = client.get("/api/episodes", query_string={"url": season})
    [row] = response.get_json()["episodes"]
    assert row["available_languages"] == ["German Dub", "AT only"]


def test_lookup_finds_pages_stored_with_a_trailing_slash(monkeypatch):
    # Arte keeps the slash, URL normalising drops it, the API wants it exact.
    page = "https://www.arte.tv/fr/videos/106684-012-A/50-nuances-de-grecs/"
    stored = _entry(channel="ARTE.FR", url_website=page)
    queries = []

    def fake_post(body, timeout=20):
        query = body["queries"][0]["query"]
        queries.append(query)
        return [stored] if query == page else []

    api.clear_cache()
    monkeypatch.setattr(api, "_post", fake_post)
    try:
        entries, _ = api.lookup(page.rstrip("/") + "#mvid=abc")
        assert entries == [stored]
        assert queries == [page.rstrip("/"), page]
    finally:
        api.clear_cache()


def test_equal_resolutions_are_listed_once(monkeypatch):
    entry = _entry()
    _fake_ffmpeg(
        monkeypatch,
        {
            entry["url_video_hd"]: _banner(720),
            entry["url_video"]: _banner(720),
            entry["url_video_low"]: _banner(360),
        },
    )
    assert [o["label"] for o in api.quality_options(entry)] == ["720p", "360p"]
    assert api.quality_options(entry)[0]["value"] == "hd"
    api.clear_cache()


def test_a_geo_blocked_programme_offers_no_resolutions(monkeypatch):
    # Its streams are ORF's block notice, 540p in every quality.
    monkeypatch.setattr(api, "geo_blocked", lambda url: True)
    monkeypatch.setattr(api, "stream_height", lambda url: pytest.fail("probed"))
    assert api.quality_options(_orf_entry(ORF_AT)) == []


def test_qualities_prefer_episodes_without_a_geo_restriction(client, monkeypatch):
    blocked = _orf_entry(ORF_AT)
    free = _orf_entry(ORF_WORLD)
    probed = []
    monkeypatch.setattr(
        api, "show_entries", lambda channel, topic, **_: [blocked, free]
    )
    monkeypatch.setattr(
        api,
        "quality_options",
        lambda entry: (
            probed.append(entry) or [{"value": "hd", "height": 1080, "label": "1080p"}]
        ),
    )
    response = client.get(
        "/api/mediathek/qualities",
        query_string={"url": api.show_url("ORF", "Soko Kitzbühel")},
    )
    assert response.get_json()["qualities"][0]["label"] == "1080p"
    assert probed == [free]


# -----------------------------
# Arte series and search order
# -----------------------------

CATEGORY = "Wissenschaft - Technik und Innovation"


def _arte(programme, title, timestamp=1794000000, channel="ARTE.DE", topic=CATEGORY):
    return _entry(
        channel=channel,
        topic=topic,
        title=title,
        timestamp=timestamp,
        url_website=f"https://www.arte.tv/de/videos/{programme}/x/",
        url_video=ARTE_HLS.format("VA"),
        url_video_hd="",
        url_video_low="",
        id=programme,
    )


ARTE_CATEGORY = [
    _arte("094414-008-A", "Impulse - Chaostheorie: Kleine Ursache", 1794900000),
    _arte("094414-007-A", "Impulse - Vererbung: Was die Gene uns verraten", 1794800000),
    _arte("111706-001-A", "Impulse - Nanotechnologien", 1790000000),
    _arte(
        "111706-002-A",
        "Impulse - Dunkle Energie (Originalversion mit Untertitel)",
        1790100000,
    ),
    _arte("128097-000-A", "Tanz als Befreiung: Alvin Ailey", 1794700000),
    _arte("092036-001-A", "Bitte nicht anfassen! Aphrodites Kind", 1794600000),
    _arte("092036-002-A", "Bitte nicht anfassen! Die Mona Lisa", 1794500000),
]


@pytest.fixture
def arte_api(monkeypatch):
    def fake_post(body, timeout=20):
        return list(ARTE_CATEGORY)

    api.clear_cache()
    monkeypatch.setattr(api, "_post", fake_post)
    monkeypatch.setattr(api, "_fetch_cover", lambda page: "")
    monkeypatch.setattr(api, "_fetch_show_poster", lambda topic: "")
    yield
    api.clear_cache()


@pytest.mark.parametrize(
    ("titles", "name"),
    [
        (["Impulse - Chaostheorie", "Impulse - Vererbung"], "Impulse"),
        (
            ["Eureka! - La teoria del caos", "Eredità: è tutta genetica - Eureka!"],
            "Eureka!",
        ),
        (
            [
                "Bitte nicht anfassen! Aphrodites Kind",
                "Bitte nicht anfassen! Die Mona Lisa",
            ],
            "Bitte nicht anfassen!",
        ),
        (["Re: Truppenabzug", "Re: Irlands tote Kinder"], None),
        (["Nur eine Folge"], None),
    ],
)
def test_common_series_name(titles, name):
    assert api._common_series_name(titles) == name


def test_arte_series_are_shows_and_seasons(arte_api):
    from aniworld.models.mediathek import MediathekSeries

    shows = api.search_shows("impulse")
    impulse = next(s for s in shows if s["name"] == "Impulse")
    assert (impulse["family"], impulse["topic"]) == (None, CATEGORY)

    series = MediathekSeries(api.show_url("ARTE.DE", CATEGORY, name="Impulse"))
    assert series.title == "Impulse"
    seasons = {season.season_number: season for season in series.seasons}
    # The older family id is the first season.
    assert sorted(seasons) == [1, 2]
    assert [e.episode_number for e in seasons[1].episodes] == [7, 8]
    assert seasons[2].episodes[1].title_de == "Dunkle Energie"


def test_arte_episode_files_by_series(arte_api, tmp_path, monkeypatch):
    monkeypatch.delenv("ANIWORLD_NAMING_TEMPLATE", raising=False)
    episode = MediathekEpisode(
        api.entry_url(ARTE_CATEGORY[3]), selected_path=str(tmp_path)
    )
    assert episode._episode_path == Path(
        tmp_path, "Impulse", "Season 02", "Impulse S02E002.mkv"
    )


def test_standalone_arte_programmes_are_their_own_show(arte_api, tmp_path):
    from aniworld.models.mediathek import MediathekSeries

    [show] = [s for s in api.search_shows("ailey") if s.get("family")]
    assert (show["family"], show["name"]) == (
        "128097",
        "Tanz als Befreiung: Alvin Ailey",
    )
    url = api.show_url("ARTE.DE", CATEGORY, family=show["family"], name=show["name"])
    series = MediathekSeries(url)
    assert [e["id"] for e in series.entries] == ["128097-000-A"]
    episode = series.seasons[0].episodes[0]
    episode.selected_path = str(tmp_path)
    assert episode._episode_path.parent.name == "Tanz als Befreiung Alvin Ailey"


def test_shows_named_after_the_keyword_come_first(stub_post):
    stub_post.extend(
        [
            _entry(topic="Tagesgespräch", title="Neue Impulse für die Pflege", id="a"),
            _entry(topic="Impulse", title="Folge 3", id="b", timestamp=1700000000),
        ]
    )
    assert [s["topic"] for s in api.search_shows("impulse")] == [
        "Impulse",
        "Tagesgespräch",
    ]


@pytest.fixture
def stub_post(monkeypatch):
    results = []
    api.clear_cache()
    monkeypatch.setattr(api, "_post", lambda body, timeout=20: list(results))
    yield results
    api.clear_cache()
