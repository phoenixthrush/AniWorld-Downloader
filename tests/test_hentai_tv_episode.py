"""Episode-only hentai.tv support: provider shape, naming and downloads."""

import pytest

from aniworld.config import Audio, Subtitles
from aniworld.models.common import ProviderData
from aniworld.models.hentai_tv import episode as module


@pytest.fixture
def episode(monkeypatch, tmp_path):
    monkeypatch.setattr(
        module.HentaiTVEpisode,
        "_metadata",
        property(lambda self: {"uploadDate": "2023-09-22T22:11:27.000Z"}),
    )
    return module.HentaiTVEpisode(
        "https://hentai.tv/hentai/example-episode-2", selected_path=tmp_path
    )


def test_provider_data_does_not_resolve_media(monkeypatch):
    episode = module.HentaiTVEpisode("https://hentai.tv/hentai/example-episode-2")
    data = episode.provider_data
    assert isinstance(data, ProviderData)
    assert data[(Audio.JAPANESE, Subtitles.ENGLISH)] == {"HentaiTV": episode.url}


def test_default_template_folders(episode, monkeypatch, tmp_path):
    monkeypatch.setenv(
        "ANIWORLD_NAMING_TEMPLATE",
        "{title} ({year}) [imdbid-{imdbid}]/Season {season}/{title} S{season}E{episode}.mkv",
    )
    assert episode._base_folder == tmp_path / "Example (2023)"
    assert episode._folder_path == tmp_path / "Example (2023)/Season 01"
    assert episode._episode_path == (
        tmp_path / "Example (2023)/Season 01/Example S01E002.mkv"
    )


def test_legacy_placeholders_and_updated_settings(episode, monkeypatch, tmp_path):
    monkeypatch.setenv(
        "ANIWORLD_NAMING_TEMPLATE",
        "%title%/%year%/Season %season%/%title% %episode% %language%.mp4",
    )
    assert episode._episode_path == (
        tmp_path / "Example/2023/Season 01/Example 002 English Sub.mp4"
    )
    episode.selected_path = tmp_path / "other"
    episode.selected_language = "Japanese"
    assert episode._episode_path == (
        tmp_path / "other/Example/2023/Season 01/Example 002 Japanese.mp4"
    )
    monkeypatch.setenv("ANIWORLD_NAMING_TEMPLATE", "{title}")
    assert episode._episode_path == tmp_path / "other/Example.mkv"


def test_download_creates_folders_and_skips_existing(episode, monkeypatch):
    calls = []
    monkeypatch.setattr(
        module.HentaiTVEpisode,
        "stream_url",
        property(lambda self: "https://media.example/video.mp4"),
    )

    def download(path, url, name):
        assert path.parent.is_dir()
        calls.append((path, url, name))
        path.touch()

    monkeypatch.setattr(module, "_download_direct_http", download)
    monkeypatch.setattr(
        module, "check_downloaded", lambda path: {"exists": path.exists()}
    )
    episode.download()
    episode.download()
    assert calls == [
        (episode._episode_path, "https://media.example/video.mp4", episode._file_name)
    ]


def test_stream_url_uses_player_result_and_refreshes(episode, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        module.HentaiTVEpisode,
        "_metadata",
        property(lambda self: {"embedUrl": "https://nhplayer.com/v/example/"}),
    )
    fetches = []

    def get(url, **kwargs):
        fetches.append(url)
        return SimpleNamespace(
            text='<li data-id="/player.php?vid=opaque&amp;type=">Main Player</li>',
            raise_for_status=lambda: None,
        )

    monkeypatch.setattr(module.GLOBAL_SESSION, "get", get)
    resolved = []

    def resolve(url):
        resolved.append(url)
        return f"https://media.example/video.mp4?verify=token-{len(resolved)}"

    monkeypatch.setattr(module, "resolve_stream_url", resolve)
    first = episode.stream_url
    assert episode.stream_url == first
    assert resolved == ["https://nhplayer.com/player.php?vid=opaque&type="]
    assert len(fetches) == 1
    assert episode.refresh_stream_url() != first
    assert len(fetches) == 2


def test_expired_url_is_refreshed_once(episode, monkeypatch):
    from niquests import Response
    from niquests.exceptions import HTTPError

    monkeypatch.setattr(
        module.HentaiTVEpisode, "stream_url", property(lambda self: "expired")
    )
    monkeypatch.setattr(episode, "refresh_stream_url", lambda: "fresh")
    calls = []

    def download(path, url, name):
        calls.append(url)
        if url == "expired":
            response = Response()
            response.status_code = 403
            raise HTTPError(response=response)

    monkeypatch.setattr(module, "_download_direct_http", download)
    episode.download()
    assert calls == ["expired", "fresh"]


@pytest.mark.parametrize(
    "url", [None, "https://example.com/hentai/test", "https://hentai.tv/hentai/test\n"]
)
def test_invalid_urls(url):
    with pytest.raises(ValueError, match="Invalid hentai.tv URL"):
        module.HentaiTVEpisode(url)


@pytest.mark.parametrize("failure", [False, True])
def test_browser_reads_main_context_and_closes(monkeypatch, failure):
    from unittest.mock import MagicMock

    from patchright import sync_api

    from aniworld.models.hentai_tv import player

    browser = MagicMock()
    page = browser.new_page.return_value
    page.evaluate.side_effect = [
        {"url": None, "error": None},
        {"url": None, "error": "Player rejected the request"}
        if failure
        else {
            "url": "https://media.example/video.mp4?verify=real-token",
            "error": None,
        },
    ]
    runtime = MagicMock()
    runtime.__enter__.return_value.chromium.launch.return_value = browser
    runtime.__enter__.return_value.chromium.executable_path = "/fake/chromium"
    monkeypatch.setattr(sync_api, "sync_playwright", lambda: runtime)
    monkeypatch.setattr(player.Path, "is_file", lambda self: True)

    if failure:
        with pytest.raises(RuntimeError, match="Player rejected"):
            player.resolve_stream_url("https://nhplayer.com/player.php?vid=opaque")
    else:
        assert player.resolve_stream_url(
            "https://nhplayer.com/player.php?vid=opaque"
        ) == ("https://media.example/video.mp4?verify=real-token")
    assert all(
        call.kwargs == {"isolated_context": False}
        for call in page.evaluate.call_args_list
    )
    browser.close.assert_called_once()
