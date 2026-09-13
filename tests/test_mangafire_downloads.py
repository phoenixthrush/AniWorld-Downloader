"""MangaFire filenames, image recovery, and atomic CBZ updates."""

import shutil
import subprocess
from functools import cache
from types import SimpleNamespace
from unittest.mock import Mock
from zipfile import ZipFile

import pytest

from aniworld.models.mangafire_to import series as manga


@cache
def image_bytes(format="PNG"):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg is required to generate test images")
    codec = {"PNG": "png", "JPEG": "mjpeg", "WEBP": "libwebp", "GIF": "gif"}[format]
    result = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=8x8",
            "-frames:v",
            "1",
            "-c:v",
            codec,
            "-f",
            "image2pipe",
            "pipe:1",
        ],
        capture_output=True,
        timeout=30,
        check=False,
    )
    if b"Unknown encoder" in result.stderr:
        pytest.skip(f"FFmpeg encoder {codec} is unavailable")
    result.check_returncode()
    return result.stdout


def write_archive(path, pages):
    with ZipFile(path, "w") as archive:
        for name, data in pages.items():
            archive.writestr(name, data)


def read_archive(path):
    with ZipFile(path) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names))
        return {name: archive.read(name) for name in names}


@pytest.fixture
def chapter(monkeypatch):
    def make(number=1, selected_pages=None):
        result = manga.MangaFireToChapter(
            url=f"https://mangafire.to/title/example/chapter/{number}",
            chapter_id=1,
            chapter_number=number,
            selected_pages=selected_pages,
            format="cbz",
        )
        pages = [
            manga.MangaFireToPage(result, n, f"https://example.invalid/{n}.png", 8, 8)
            for n in (1, 2)
        ]
        monkeypatch.setattr(result, "_MangaFireToChapter__pages", pages)
        return result

    return make


@pytest.fixture
def fetch(monkeypatch):
    fetch = Mock(return_value=SimpleNamespace(content=image_bytes()))
    monkeypatch.setattr(manga, "_get", fetch)
    return fetch


@pytest.mark.parametrize("format", ["PNG", "JPEG", "WEBP", "GIF"])
def test_image_validation(format):
    data = image_bytes(format)
    assert manga._valid_image(data)
    assert not manga._valid_image(data[: len(data) // 2])


@pytest.mark.parametrize(
    "data",
    [b"", b"broken image", b"<html>challenge</html>", b"\xff\xd8garbage\xff\xd9"],
)
def test_reject_invalid_images(data):
    assert not manga._valid_image(data)


def test_fractional_chapters_have_distinct_archives(tmp_path, chapter, fetch):
    archives = []
    for number in (1, 1.5, 1.6):
        item = chapter(number)
        path = item.download(tmp_path / item.folder_name)
        assert path.name == f"Chapter {number}.cbz"
        archives.append(path)
    assert len(set(archives)) == 3
    assert all(path.is_file() for path in archives)


def test_chapter_title_with_dots_is_preserved(tmp_path, chapter, fetch):
    item = chapter(1.5)
    item.chapter_name = "Bonus. Part 2"
    assert (
        item.download(tmp_path / item.folder_name).name
        == "Chapter 1.5 - Bonus. Part 2.cbz"
    )


def test_page_redownloads_broken_image_and_reuses_valid_one(tmp_path, chapter, fetch):
    page = chapter().pages[0]
    path = tmp_path / page.file_name
    path.write_bytes(b"broken image")
    page.download(tmp_path)
    assert path.read_bytes() == image_bytes()
    page.download(tmp_path)
    fetch.assert_called_once()


def test_invalid_response_preserves_existing_image(tmp_path, chapter, fetch):
    page = chapter().pages[0]
    path = tmp_path / page.file_name
    path.write_bytes(image_bytes())
    fetch.return_value.content = b"broken response"
    with pytest.raises(ValueError, match="Invalid or incomplete"):
        page.image.download(path)
    assert path.read_bytes() == image_bytes()


def test_archive_repairs_bad_images_and_preserves_valid_pages(tmp_path, chapter, fetch):
    item = chapter()
    folder = tmp_path / item.folder_name
    archive = tmp_path / f"{item.folder_name}.cbz"
    original = image_bytes("JPEG")
    write_archive(archive, {"001.png": original, "002.png": b"broken image"})
    item.download(folder)
    assert read_archive(archive) == {"001.png": original, "002.png": image_bytes()}
    fetch.assert_called_once_with("https://example.invalid/2.png")
    item.download(folder)
    assert fetch.call_count == 1


def test_invalid_zip_is_rebuilt(tmp_path, chapter, fetch):
    item = chapter()
    archive = tmp_path / f"{item.folder_name}.cbz"
    archive.write_bytes(b"broken zip")
    item.download(tmp_path / item.folder_name)
    assert read_archive(archive) == dict.fromkeys(("001.png", "002.png"), image_bytes())


@pytest.mark.parametrize("failure", ["download", "write", "verify", "replace"])
def test_failed_update_preserves_original_archive(
    tmp_path, chapter, fetch, monkeypatch, failure
):
    item = chapter()
    folder = tmp_path / item.folder_name
    archive = tmp_path / f"{item.folder_name}.cbz"
    write_archive(archive, {"001.png": image_bytes()})
    original = archive.read_bytes()
    if failure == "download":
        fetch.side_effect = OSError("download failed")
    elif failure == "write":
        monkeypatch.setattr(ZipFile, "write", Mock(side_effect=OSError("disk full")))
    elif failure == "verify":
        monkeypatch.setattr(ZipFile, "testzip", lambda self: "002.png")
    else:
        replace = type(archive).replace

        def fail_replace(self, target):
            if target == archive:
                raise OSError("replace failed")
            return replace(self, target)

        monkeypatch.setattr(type(archive), "replace", fail_replace)
    with pytest.raises((OSError, ValueError)):
        item.download(folder)
    assert archive.read_bytes() == original
    assert not list(tmp_path.glob(".mangafire-*"))


def test_subset_update_preserves_unselected_pages(tmp_path, chapter, fetch):
    folder = tmp_path / "Chapter 1"
    archive = chapter(selected_pages=[1]).download(folder)
    chapter(selected_pages=[2]).download(folder)
    assert read_archive(archive) == dict.fromkeys(("001.png", "002.png"), image_bytes())
    assert fetch.call_count == 2


def test_png_with_damaged_pixels_is_rejected():
    data = bytearray(image_bytes())
    data[data.index(b"IDAT") + 4] ^= 1
    assert not manga._valid_image(bytes(data))


def test_archive_with_bad_crc_redownloads_page(tmp_path, chapter, fetch):
    item = chapter(selected_pages=[1])
    archive = tmp_path / f"{item.folder_name}.cbz"
    data = image_bytes()
    write_archive(archive, {"001.png": data})
    damaged = bytearray(archive.read_bytes())
    damaged[damaged.index(data) + 20] ^= 1
    archive.write_bytes(damaged)
    item.download(tmp_path / item.folder_name)
    assert read_archive(archive) == {"001.png": data}
    fetch.assert_called_once()


def test_empty_selection_does_not_create_archive(tmp_path, chapter, fetch):
    item = chapter(selected_pages=[])
    with pytest.raises(ValueError, match="No MangaFire pages"):
        item.download(tmp_path / item.folder_name)
    assert not (tmp_path / item.folder_name).exists()
    assert not (tmp_path / f"{item.folder_name}.cbz").exists()
    fetch.assert_not_called()
