"""Offline checks for small CLI fixes: search abort, --provider-url, banner, Anime4K remove."""

import importlib
import sys

import pytest

from aniworld import entry, search

# The packages re-export functions that shadow their submodule names.
a4k = importlib.import_module("aniworld.anime4k.anime4k")
ascii_art = importlib.import_module("aniworld.ascii.ascii")


def test_aborted_search_exits_cleanly(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["aniworld"])
    monkeypatch.setattr(search, "search", lambda: None)
    assert entry.aniworld() == 1
    assert "unexpected error" not in capsys.readouterr().err


def test_search_eof_exits_cleanly(monkeypatch, capsys):
    def eof(_prompt):
        raise EOFError

    monkeypatch.setattr(sys, "argv", ["aniworld"])
    monkeypatch.setattr("builtins.input", eof)
    assert entry.aniworld() == 1
    assert "unexpected error" not in capsys.readouterr().err


def test_provider_url_without_provider_is_rejected(monkeypatch):
    monkeypatch.setattr(
        sys, "argv", ["aniworld", "--provider-url", "https://voe.sx/e/x"]
    )
    with pytest.raises(SystemExit) as exc:
        entry.parse_args()
    assert exc.value.code == 2


def test_invalid_provider_url_args_leave_anime4k_alone(monkeypatch):
    remove = []
    monkeypatch.setattr("aniworld.arguments.anime4k", remove.append)
    monkeypatch.setattr(
        sys,
        "argv",
        ["aniworld", "--anime4k", "Remove", "--provider-url", "https://voe.sx/e/x"],
    )
    with pytest.raises(SystemExit) as exc:
        entry.parse_args()
    assert exc.value.code == 2
    assert remove == []


def test_provider_extraction_failure_reports_clean_cli_error(monkeypatch, caplog):
    from aniworld.extractors import provider_functions

    def missing_stream(_url):
        raise ValueError("No Vidoza stream URL found")

    monkeypatch.setitem(
        provider_functions, "get_direct_link_from_vidoza", missing_stream
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aniworld",
            "--provider",
            "Vidoza",
            "--provider-url",
            "https://vidoza.net/embed-x.html",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        entry.aniworld()
    assert exc.value.code == 1
    assert "No Vidoza stream URL found" in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize("provider,expect_headers", [("Vidoza", False), ("VOE", True)])
def test_direct_provider_cli_only_passes_configured_headers(
    monkeypatch, tmp_path, provider, expect_headers
):
    import ffmpeg

    from aniworld.extractors import provider_functions

    monkeypatch.setitem(
        provider_functions, f"get_direct_link_from_{provider.lower()}", lambda url: url
    )
    commands = []
    monkeypatch.setattr(
        ffmpeg.nodes.OutputStream,
        "run",
        lambda stream: commands.append(ffmpeg.compile(stream)),
    )
    monkeypatch.setenv("ANIWORLD_DOWNLOAD_PATH", str(tmp_path))
    url = "https://media.example/video.mp4"
    monkeypatch.setattr(
        sys, "argv", ["aniworld", "--provider", provider, "--provider-url", url]
    )
    with pytest.raises(SystemExit) as exc:
        entry.parse_args()
    assert exc.value.code == 0
    [command] = commands
    assert command[command.index("-i") + 1] == url
    assert ("-headers" in command) is expect_headers


def test_legacy_windows_banner_is_printed(monkeypatch, capsys):
    monkeypatch.setattr(ascii_art.platform, "system", lambda: "Windows")
    monkeypatch.setattr(ascii_art.platform, "release", lambda: "10")
    ascii_art.display_ascii_art()
    assert capsys.readouterr().out.strip()


def test_anime4k_remove_deletes_assets(monkeypatch, tmp_path):
    monkeypatch.setattr(a4k, "ANIWORLD_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(a4k, "MPV_CONFIG_DIR", tmp_path / "mpv")
    assets = tmp_path / "Anime4K" / "GLSL_Windows_High-end"
    assets.mkdir(parents=True)
    a4k.anime4k(mode="remove")
    assert not (tmp_path / "Anime4K").exists()


def test_anime4k_switch_keeps_cached_assets(monkeypatch, tmp_path):
    monkeypatch.setattr(a4k, "ANIWORLD_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(a4k, "MPV_CONFIG_DIR", tmp_path / "mpv")
    names = a4k.get_anime4k_folder_names()
    assets = tmp_path / "Anime4K"
    for mode in ("high", "low"):
        folder = assets / names[mode]
        folder.mkdir(parents=True)
        (folder / "input.conf").write_text(f"# Optimized shaders for {mode}er-end GPU:")
    monkeypatch.setattr(
        a4k,
        "get_anime4k_urls",
        lambda: {
            mode: f"https://example.invalid/{folder}.zip"
            for mode, folder in names.items()
        },
    )

    def unexpected_download(*args, **kwargs):
        pytest.fail("Switching to cached assets attempted a download")

    monkeypatch.setattr(a4k.GLOBAL_SESSION, "get", unexpected_download)
    a4k.anime4k("high")
    a4k.anime4k("low")
    assert a4k.detect_current_mode() == "low"
    assert (assets / names["high"]).is_dir()
