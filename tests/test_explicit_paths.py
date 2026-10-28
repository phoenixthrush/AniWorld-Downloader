"""Explicit file arguments expand ~ while relative destinations stay cwd-based."""

import importlib
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from zipfile import ZipFile

import pytest

from aniworld.common import common
from aniworld.env import merge_env, persist_env_values
from aniworld.models.common import check_downloaded, hls
from aniworld.models.common import common as model_common
from aniworld.models.common.naming import template_path

anime4k = importlib.import_module("aniworld.anime4k.anime4k")


@pytest.fixture(params=["tilde", "relative", "absolute", "literal_tilde"])
def explicit_path(monkeypatch, tmp_path, request):
    home = tmp_path / "home"
    work = tmp_path / "work"
    home.mkdir()
    work.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.chdir(work)
    (work / "files~copy").mkdir()

    def path(name):
        if request.param == "tilde":
            return Path("~") / name, home / name
        if request.param == "absolute":
            return home / name, home / name
        if request.param == "literal_tilde":
            return Path("files~copy") / name, work / "files~copy" / name
        return Path(name), work / name

    return path


def test_env_merge_expands_template_and_destination(explicit_path, monkeypatch):
    example_arg, example = explicit_path("example.env")
    env_arg, env = explicit_path("config/settings.env")
    key = "ANIWORLD_TEST_PATH"
    monkeypatch.delenv(key, raising=False)
    example.write_text(f"{key}=example\n")
    env.parent.mkdir(parents=True)
    env.write_text(f"{key}=kept\n")

    merge_env(example_arg, env_arg)

    assert env.read_text() == f"{key}=kept\n"
    assert os.environ[key] == "kept"
    assert not (Path.cwd() / "~").exists()


def test_env_persistence_expands_destination(explicit_path):
    env_arg, env = explicit_path("settings.env")
    env.write_text("# user comment\nANIWORLD_TEST_PATH=before\n")

    persist_env_values(env_arg, {"ANIWORLD_TEST_PATH": "after"})

    assert env.read_text() == "# user comment\nANIWORLD_TEST_PATH=after\n"
    assert not (Path.cwd() / "~").exists()


def test_download_check_expands_file_argument(explicit_path, monkeypatch):
    file_arg, file = explicit_path("episode.mkv")
    file.write_bytes(b"local video placeholder")
    probe = Mock(
        return_value={
            "streams": [
                {"codec_type": "video", "tags": {"language": "und"}},
                {"codec_type": "audio", "tags": {"language": "jpn"}},
            ]
        }
    )
    monkeypatch.setattr(model_common.ffmpeg, "probe", probe)

    assert check_downloaded(file_arg) == {
        "exists": True,
        "video_langs": {"und"},
        "audio_langs": {"jpn"},
    }
    probe.assert_called_once_with(file_arg.expanduser())
    assert not (Path.cwd() / "~").exists()


@pytest.mark.parametrize("root_name", ["", "download files"])
def test_template_path_expands_root_only(explicit_path, root_name):
    root_arg, root = explicit_path(root_name)

    path = template_path(
        root_arg,
        "{title}/{title}.mkv",
        {"title": "Example~Title"},
        is_series=True,
    )

    assert path.resolve() == root / "Example~Title" / "Example~Title.mkv"
    assert path.is_absolute() == root_arg.expanduser().is_absolute()
    assert not (Path.cwd() / "~").exists()


def test_unzip_expands_input_and_output_paths(explicit_path, monkeypatch):
    archive_arg, archive = explicit_path("archive with spaces.zip")
    target_arg, target = explicit_path("extracted files")
    with ZipFile(archive, "w") as output:
        output.writestr("example.txt", "example")
    # Exercise actual extraction without requiring a system unzip executable.
    monkeypatch.setattr(common, "sys", SimpleNamespace(platform="win32"))

    common.unzip(archive_arg, target_arg)

    assert (target / "example.txt").read_text() == "example"
    assert not (Path.cwd() / "~").exists()


def test_anime4k_download_finds_expanded_cached_folder(explicit_path, monkeypatch):
    target_arg, target = explicit_path("shader files")
    (target / "Anime4K" / "example").mkdir(parents=True)
    monkeypatch.setattr(
        anime4k,
        "get_anime4k_urls",
        lambda: {"high": "https://example.invalid/example.zip"},
    )
    monkeypatch.setattr(
        anime4k.GLOBAL_SESSION,
        "get",
        Mock(side_effect=AssertionError("Cached shaders must not be downloaded")),
    )

    files = anime4k.download_anime4k(target_arg)
    assert len(files) == 1
    assert files[0].resolve() == target / "Anime4K" / "example.zip"
    assert files[0].is_absolute() == target_arg.expanduser().is_absolute()
    assert not (Path.cwd() / "~").exists()


def test_anime4k_extract_expands_archive_and_target(explicit_path):
    archive_arg, archive = explicit_path("example.zip")
    target_arg, target = explicit_path("shader files")
    archive.write_bytes(b"cached archive")
    extracted = target / "Anime4K" / "example"
    extracted.mkdir(parents=True)

    folders = anime4k.extract_anime4k([archive_arg], target_arg)
    assert len(folders) == 1
    assert folders[0].resolve() == extracted
    assert folders[0].is_absolute() == target_arg.expanduser().is_absolute()
    assert not archive.exists()
    assert not (Path.cwd() / "~").exists()


def test_anime4k_copy_and_remove_expand_config_paths(explicit_path):
    source_arg, source = explicit_path("source.conf")
    target_arg, target = explicit_path("mpv.conf")
    source.write_text("shader=example\n")

    anime4k.copy_with_markers(source_arg, target_arg)
    assert "shader=example" in target.read_text()
    target.write_text(target.read_text() + "user-option=yes\n")
    anime4k.remove_anime4k_lines(target_arg)

    assert target.read_text() == "user-option=yes\n"
    assert not (Path.cwd() / "~").exists()


def test_hls_download_and_cleanup_expand_prefix(explicit_path, monkeypatch):
    prefix_arg, prefix = explicit_path("video with spaces")
    monkeypatch.setenv("ANIWORLD_HLS_CONCURRENCY", "2")
    monkeypatch.setattr(
        hls,
        "_fetch_text",
        lambda *_: "#EXTM3U\n#EXTINF:1,\nsegment.ts\n#EXT-X-ENDLIST\n",
    )
    monkeypatch.setattr(hls, "_fetch_bytes", lambda *_: b"local segment bytes")
    monkeypatch.setattr(hls, "_publish_progress", lambda **_: None)
    progress = hls._common()
    monkeypatch.setattr(progress, "_ffmpeg_progress", progress._ffmpeg_progress.copy())

    paths = hls.download_hls_parallel("https://example.invalid/video.m3u8", prefix_arg)

    expected = prefix.with_suffix(".hls_video.ts")
    assert len(paths) == 1
    assert paths[0].resolve() == expected
    assert paths[0].is_absolute() == prefix_arg.expanduser().is_absolute()
    assert expected.read_bytes() == b"local segment bytes"
    hls.cleanup_temp_files(prefix_arg)
    assert not expected.exists()
    assert not (Path.cwd() / "~").exists()
