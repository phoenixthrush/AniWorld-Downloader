"""Language versions of Mediathek programmes, offline."""

from pathlib import Path

import pytest

from aniworld.models.mediathek import MediathekEpisode, MediathekSeries, api, versions

ZDF = "https://www.zdf.de/serien/the-summer-i-turned-pretty/folge-11-100.html"
ARTE_HLS = "https://manifest-arte.akamaized.net/api/manifest/v1/Generate/x/{}/XQ+KS+CHEV1/1-A.m3u8"


def _entry(**overrides):
    entry = {
        "channel": "ZDFneo",
        "topic": "The Summer I Turned Pretty",
        "title": "Die letzte Entscheidung (S03/E11)",
        "timestamp": 1794780000,
        "duration": 2700,
        "url_website": ZDF,
        "url_subtitle": "",
        "url_video": "https://cdn.example.invalid/de-sd.mp4",
        "url_video_low": "",
        "url_video_hd": "https://cdn.example.invalid/de-hd.mp4",
        "id": "de",
    }
    entry.update(overrides)
    return entry


GERMAN = _entry()
ENGLISH = _entry(
    title="Die letzte Entscheidung (S03/E11) (Englisch)",
    url_website=ZDF.replace("folge-11", "folge-11-englisch"),
    url_video_hd="https://cdn.example.invalid/en-hd.mp4",
    id="en",
)
SIGNED = _entry(
    title="Die letzte Entscheidung (S03/E11) (Gebärdensprache)",
    url_video_hd="https://cdn.example.invalid/dgs-hd.mp4",
    id="dgs",
)
EPISODE_10 = _entry(
    title="Der Abschied (S03/E10) (Englisch)",
    url_website=ZDF.replace("folge-11", "folge-10-englisch"),
    id="e10-en",
)


def _arte(channel, code, title, programme="094414-008-A"):
    language = channel.split(".")[1].lower()
    return _entry(
        channel=channel,
        topic="Kategorie",
        title=title,
        url_website=f"https://www.arte.tv/{language}/videos/{programme}/x/",
        url_video=ARTE_HLS.format(code),
        url_video_hd="",
        id=f"{channel}-{programme}",
    )


@pytest.fixture
def mvw(monkeypatch):
    results = []
    api.clear_cache()
    monkeypatch.setattr(api, "_post", lambda body, timeout=20: list(results))
    monkeypatch.setattr(api, "_fetch_cover", lambda page: "")
    monkeypatch.setattr(api, "_fetch_show_poster", lambda topic: "")
    yield results
    api.clear_cache()


# -----------------------------
# Labels
# -----------------------------


@pytest.mark.parametrize(
    ("title", "found"),
    [
        ("Folge 3 (S01/E03)", "German Dub"),
        ("Folge 3 (S01/E03) (Englisch)", "English Dub"),
        ("Jeff Bridges' Analog Adventure (English Version)", "English Dub"),
        ("Der Nachtmann (S02/E08) (Originalversion)", "Original"),
        ("Böhmermann trifft Selenskyj – OmU", "German Sub"),
        ("Folge 1156 (S29/E25) (Gebärdensprache)", "Sign Language"),
        ("Tatort: Narrentanz (Audiodeskription)", "Audio Description"),
    ],
)
def test_title_labels(title, found):
    assert versions.label(_entry(title=title)) == found


@pytest.mark.parametrize(
    ("channel", "code", "found", "audio", "subs"),
    [
        ("ARTE.DE", "VA-STA", "German Dub", "deu", "de"),
        ("ARTE.DE", "VOA-STMA", "German Dub", "deu", "de"),
        ("ARTE.DE", "VOF-STA", "German Sub", "fra", "de"),
        ("ARTE.DE", "VAAUD", "Audio Description", "deu", "de"),
        ("ARTE.FR", "VOF", "French Dub", "fra", "fr"),
        ("ARTE.EN", "VOF-STE%5BANG%5D", "English Sub", "fra", "en"),
        ("ARTE.EN", "VE%5BANG%5D-STE%5BANG%5D", "English Dub", "eng", "en"),
        ("ARTE.IT", "VO-STE%5BITA%5D", "Italian Sub", "und", "it"),
        ("ARTE.PL", "VE%5BPOL%5D", "Polish Dub", "pol", "pl"),
        ("ARTE.ES", "VO", "Original", "und", "es"),
        ("ARTE.DE", "de", "German Dub", "deu", "de"),
    ],
)
def test_arte_labels(channel, code, found, audio, subs):
    entry = _arte(channel, code, "x")
    assert versions.label(entry) == found
    assert versions.audio_code(entry) == audio
    assert versions.subtitle_language(entry) == subs


def test_labels_sort_like_the_menu():
    assert versions.sort_labels(
        ["Sign Language", "French Sub", "German Dub", "English Dub"]
    ) == ["German Dub", "English Dub", "French Sub", "Sign Language"]


# -----------------------------
# Grouping
# -----------------------------


def test_versions_of_one_episode_are_grouped():
    groups = versions.group([ENGLISH, GERMAN, SIGNED, EPISODE_10])
    assert len(groups) == 2
    primary, found = groups[0]
    # German is the version the episode is listed and named by.
    assert primary is GERMAN
    assert found == {
        "English Dub": ENGLISH,
        "German Dub": GERMAN,
        "Sign Language": SIGNED,
    }
    # An episode only offered in English is listed by that.
    assert groups[1] == (EPISODE_10, {"English Dub": EPISODE_10})


def test_an_arte_card_lists_its_own_channel_first():
    de = _arte("ARTE.DE", "VA", "Impulse - Chaos")
    fr = _arte("ARTE.FR", "VOF", "Déclics - Chaos")
    [(primary, found)] = versions.group([de, fr], preferred_channel="ARTE.FR")
    assert primary is fr
    assert set(found) == {"German Dub", "French Dub"}


def test_arte_translations_are_found_through_the_player_api(monkeypatch, mvw):
    de = _arte("ARTE.DE", "VA", "Impulse - Chaos")
    fr = _arte("ARTE.FR", "VOF", "Déclics - Chaos")
    other = _arte("ARTE.FR", "VOF", "Déclics - Autre", programme="555555-001-A")
    searched = []

    def fake_search(keyword, *, channels, limit):
        searched.append((keyword, channels))
        return [fr, other] if channels == ("ARTE.FR",) else []

    monkeypatch.setattr(
        versions, "_fetch_arte_titles", lambda lang, pid: (f"T-{lang}",)
    )
    monkeypatch.setattr(api, "search", fake_search)
    assert versions.arte_translations([de]) == [fr]
    assert ("T-fr", ("ARTE.FR",)) in searched
    assert all(channels != ("ARTE.DE",) for _, channels in searched)


def test_a_failed_player_api_call_is_not_cached(monkeypatch, mvw):
    calls = []

    def broken(language, programme):
        calls.append(language)
        raise ConnectionError("offline")

    monkeypatch.setattr(versions, "_fetch_arte_titles", broken)
    assert versions._arte_titles("fr", "094414-008-A") == ()
    assert versions._arte_titles("fr", "094414-008-A") == ()
    assert calls == ["fr", "fr"]


# -----------------------------
# Episodes and shows
# -----------------------------


def test_episode_downloads_the_selected_version(mvw, tmp_path, monkeypatch):
    monkeypatch.delenv("ANIWORLD_NAMING_TEMPLATE", raising=False)
    mvw.extend([GERMAN, ENGLISH, SIGNED])
    episode = MediathekEpisode(api.entry_url(GERMAN), selected_path=str(tmp_path))

    assert episode.selected_language == "German Dub"
    assert episode.languages == ["German Dub", "English Dub", "Sign Language"]
    assert episode.language_providers == {
        "German Dub": ["ZDFneo"],
        "English Dub": ["ZDFneo"],
        "Sign Language": ["ZDFneo"],
    }
    german_path = episode._episode_path

    episode.selected_language = "English Dub"
    assert episode.stream_url.endswith("en-hd.mp4")
    assert episode.audio_language == "eng"
    assert episode.title_de == "Die letzte Entscheidung"
    # Same folder and number, the version named in the file.
    assert episode._episode_path == german_path.with_name(
        german_path.stem + " (English Dub).mkv"
    )
    assert german_path == Path(
        tmp_path,
        "The Summer I Turned Pretty",
        "Season 03",
        "The Summer I Turned Pretty S03E011.mkv",
    )


def test_asking_for_a_missing_version_says_what_there_is(mvw, tmp_path):
    mvw.extend([GERMAN, ENGLISH])
    episode = MediathekEpisode(
        api.entry_url(GERMAN),
        selected_path=str(tmp_path),
        selected_language="French Dub",
    )
    with pytest.raises(ValueError, match="German Dub, English Dub"):
        _ = episode.stream_url


def test_show_lists_each_episode_once_with_its_versions(mvw):
    mvw.extend([GERMAN, ENGLISH, SIGNED, EPISODE_10])
    show = MediathekSeries(api.show_url("ZDFneo", "The Summer I Turned Pretty"))
    [season] = show.seasons
    assert [e.episode_number for e in season.episodes] == [10, 11]
    assert season.episodes[1].languages == [
        "German Dub",
        "English Dub",
        "Sign Language",
    ]
    assert season.episodes[0].languages == ["English Dub"]


def test_shared_download_takes_the_versions_audio(mvw, tmp_path, monkeypatch):
    """ "French Dub" isn't an anime label; the shared download must not look it up."""
    from aniworld.models.common import common

    french = _arte("ARTE.FR", "VOF", "Déclics - Chaos")
    episode = MediathekEpisode(
        api.entry_url(french), selected_path=str(tmp_path), entry=french, versions={}
    )
    assert episode.selected_language == "French Dub"
    # A French copy already on disk: the download recognises it and stops.
    monkeypatch.setattr(
        common,
        "check_downloaded",
        lambda path: {"exists": True, "video_langs": {"und"}, "audio_langs": {"fra"}},
    )
    monkeypatch.setattr(common.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        common, "_get_provider_attempt_order", lambda ep: ("Arte (FR)",)
    )
    assert common.download(episode) is None


def test_web_lists_versions_and_their_channels(client, mvw):
    mvw.extend([GERMAN, ENGLISH])
    season = api.show_url("ZDFneo", "The Summer I Turned Pretty", season=3)
    [row] = client.get("/api/episodes", query_string={"url": season}).get_json()[
        "episodes"
    ]
    assert row["available_languages"] == ["German Dub", "English Dub"]

    providers = client.get("/api/providers", query_string={"url": row["url"]})
    assert providers.get_json() == {
        "providers": {"German Dub": ["ZDFneo"], "English Dub": ["ZDFneo"]}
    }


def test_the_menu_offers_every_mediathek_language(client):
    page = client.get("/").get_data(as_text=True)
    for found in ("French Sub", "Polish Dub", "Sign Language", "Audio Description"):
        assert found in page


# -----------------------------
# Review fixes
# -----------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://mediathekviewweb.de/#channel=MDR&topic=In%20aller%20Freundschaft",
        "https://mediathekviewweb.de/#topic=X&query=y&channel=MDR",
    ],
)
def test_show_urls_resolve_in_any_parameter_order(url):
    assert api.MEDIATHEK_SERIES_PATTERN.fullmatch(url)
    assert not api.MEDIATHEK_SEASON_PATTERN.fullmatch(url)
    season = url + "&season=3"
    assert api.MEDIATHEK_SEASON_PATTERN.fullmatch(season)
    assert not api.MEDIATHEK_SERIES_PATTERN.fullmatch(season)
    assert api.MEDIATHEK_SEASON_PATTERN.fullmatch(url.replace("#", "#season=3&"))


def test_search_without_a_limit_asks_for_a_full_page(monkeypatch):
    bodies = []
    api.clear_cache()
    monkeypatch.setattr(
        api, "_post", lambda body, timeout=20: bodies.append(body) or []
    )
    try:
        assert api.search("tatort", limit=None) == []
        assert bodies[0]["size"] == 1000
    finally:
        api.clear_cache()


def test_ttml_with_a_doctype_is_refused():
    from aniworld.models.mediathek import subtitles

    evil = (
        '<?xml version="1.0"?><!DOCTYPE tt [<!ENTITY a "aaaa">]>'
        '<tt xmlns="http://www.w3.org/ns/ttml"><body><div>'
        '<p begin="1s" end="2s">&a;</p></div></body></tt>'
    )
    with pytest.raises(subtitles.SubtitleError, match="DOCTYPE"):
        subtitles.to_srt(evil)


def test_one_translation_search_per_language_when_the_name_hits(monkeypatch, mvw):
    de = _arte("ARTE.DE", "VA", "Impulse - Chaos")
    fr = _arte("ARTE.FR", "VOF", "Déclics - Chaos")
    searched = []

    def fake_search(keyword, *, channels, limit):
        searched.append((keyword, channels, limit))
        return [fr] if channels == ("ARTE.FR",) else []

    monkeypatch.setattr(
        versions,
        "_fetch_arte_titles",
        lambda lang, pid: (f"Series-{lang}", f"Ep-{lang}"),
    )
    monkeypatch.setattr(api, "search", fake_search)
    versions.arte_translations([de])
    french = [call for call in searched if call[1] == ("ARTE.FR",)]
    assert french == [("Series-fr", ("ARTE.FR",), 100)]


# -----------------------------
# Browse rows
# -----------------------------


def _newest(**overrides):
    return _entry(timestamp=1794900000, **overrides)


def test_newest_shows_split_series_from_long_programmes(mvw):
    mvw.extend(
        [
            _newest(
                topic="Die Kanzlei", title="Folge 1 (S01/E01)", duration=2700, id="a"
            ),
            _newest(
                topic="Die Kanzlei", title="Folge 2 (S01/E02)", duration=2700, id="b"
            ),
            _newest(topic="Clips", title="Kurz (S01/E05)", duration=120, id="c"),
            _newest(topic="Doku", title="Eine lange Doku", duration=3000, id="d"),
            _newest(
                topic="tagesschau", title="tagesschau 20:00 Uhr", duration=900, id="e"
            ),
            _newest(
                topic="Die Kanzlei",
                title="Folge 3 (S01/E03) (Gebärdensprache)",
                duration=2700,
                id="f",
            ),
            _newest(
                topic="Nur DGS", title="X (S01/E01) (Gebärdensprache)", duration=2700
            ),
            _newest(
                channel="KiKA.XX", topic="Fremd", title="Y (S01/E01)", duration=2700
            ),
        ]
    )
    episodes = api.newest_shows("episodes")
    assert [(s["topic"], s["newest"]["id"]) for s in episodes] == [("Die Kanzlei", "a")]
    assert [s["topic"] for s in api.newest_shows("programmes")] == ["Doku"]


def test_browse_rows_come_with_covers(mvw, monkeypatch):
    from aniworld import search

    mvw.extend(
        [
            _newest(topic="Die Kanzlei", title="Folge 1 (S01/E01)", duration=2700),
            _newest(topic="Doku", title="Eine lange Doku", duration=3000, id="d"),
        ]
    )
    monkeypatch.setattr(api, "_fetch_show_poster", lambda topic: "https://x/poster.jpg")
    monkeypatch.setattr(api, "_fetch_cover", lambda page: "https://x/still.jpg")
    [series] = search.fetch_mediathek_new_episodes()
    assert (series["title"], series["poster_url"]) == (
        "Die Kanzlei",
        "https://x/poster.jpg",
    )
    assert series["url"] == api.show_url("ZDFneo", "Die Kanzlei")
    [doku] = search.fetch_mediathek_new_programmes()
    # Films and documentaries skip TVmaze, which only knows series.
    assert doku["poster_url"] == "https://x/still.jpg"


def test_the_mediathek_tab_has_browse_rows(client, mvw, monkeypatch):
    from aniworld.web.views import api_media

    page = client.get("/").get_data(as_text=True)
    assert 'data-row="mediathek_episodes"' in page
    assert 'data-row="mediathek_programmes"' in page

    mvw.append(_newest(topic="Die Kanzlei", title="Folge 1 (S01/E01)", duration=2700))
    monkeypatch.setattr(api_media, "_browse_cache", {})
    response = client.get("/api/mediathek-episodes")
    assert response.status_code == 200
    [card] = response.get_json()["results"]
    assert card["title"] == "Die Kanzlei"
    assert card["channel"] == "ZDFneo"
