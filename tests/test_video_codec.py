"""ANIWORLD_VIDEO_CODEC after #301: hardware encoders, probed, with a fallback."""

import pytest

from aniworld import config


@pytest.fixture(autouse=True)
def forget_probes(monkeypatch):
    monkeypatch.setattr(config, "_encoder_checks", {})


def test_the_setting_is_read_live(monkeypatch):
    monkeypatch.setenv("ANIWORLD_VIDEO_CODEC", "h264")
    assert config.get_video_codec() == "libx264"
    monkeypatch.setenv("ANIWORLD_VIDEO_CODEC", "copy")
    assert config.get_video_codec() == "copy"


def test_an_unknown_codec_falls_back_to_copy(monkeypatch):
    monkeypatch.setenv("ANIWORLD_VIDEO_CODEC", "prores")
    assert config.get_video_codec() == "copy"


@pytest.mark.parametrize(
    "key,encoder",
    [
        ("h264_nvenc", "h264_nvenc"),
        ("hevc_nvenc", "hevc_nvenc"),
        ("av1_nvenc", "av1_nvenc"),
        ("h264_amf", "h264_amf"),
        ("h264_qsv", "h264_qsv"),
        ("hevc_videotoolbox", "hevc_videotoolbox"),
    ],
)
def test_a_working_hardware_encoder_is_used_as_is(monkeypatch, key, encoder):
    monkeypatch.setenv("ANIWORLD_VIDEO_CODEC", key)
    monkeypatch.setattr(config, "encoder_works", lambda name: True)
    assert config.get_video_codec() == encoder


@pytest.mark.parametrize(
    "key,fallback",
    [
        ("h264_nvenc", "libx264"),
        ("hevc_nvenc", "libx265"),
        ("av1_nvenc", "libsvtav1"),
        ("hevc_amf", "libx265"),
        ("av1_qsv", "libsvtav1"),
        ("h264_videotoolbox", "libx264"),
    ],
)
def test_a_broken_hardware_encoder_falls_back_to_the_cpu_encoder_of_that_codec(
    monkeypatch, key, fallback
):
    monkeypatch.setenv("ANIWORLD_VIDEO_CODEC", key)
    monkeypatch.setattr(config, "encoder_works", lambda name: False)
    assert config.get_video_codec() == fallback


def test_an_unprobeable_machine_does_not_block_the_hardware_encoder(monkeypatch):
    """No ffmpeg on PATH yet (Windows fetches it later): trust the setting."""
    monkeypatch.setenv("ANIWORLD_VIDEO_CODEC", "h264_nvenc")
    monkeypatch.setattr(config, "encoder_works", lambda name: None)
    assert config.get_video_codec() == "h264_nvenc"


def test_software_codecs_are_never_probed(monkeypatch):
    monkeypatch.setenv("ANIWORLD_VIDEO_CODEC", "h265")
    monkeypatch.setattr(
        config, "encoder_works", lambda name: pytest.fail("probed a CPU encoder")
    )
    assert config.get_video_codec() == "libx265"


def test_the_probe_is_remembered_per_process(monkeypatch):
    calls = []

    class Result:
        returncode = 1
        stderr = "Cannot load libnvidia-encode.so.1"

    def fake_run(command, **kwargs):
        calls.append(command)
        return Result()

    import subprocess

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(config, "_ffmpeg_binary", lambda: "/usr/bin/ffmpeg")
    assert config.encoder_works("h264_nvenc") is False
    assert config.encoder_works("h264_nvenc") is False
    assert len(calls) == 1
    assert "h264_nvenc" in calls[0]


def test_every_hardware_key_has_a_label_and_a_fallback():
    for key in config.HARDWARE_CODEC_FALLBACK:
        assert key in config.VIDEO_CODEC_MAP
        assert key in config.VIDEO_CODEC_LABELS
        assert config.HARDWARE_CODEC_FALLBACK[key] in ("h264", "h265", "av1")
