"""MangaFire filenames, image recovery, and atomic CBZ/EPUB updates."""

import builtins
import sys
from functools import cache
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from xml.etree import ElementTree as ET
from zipfile import ZIP_STORED, ZipFile

import pytest
from PIL import Image

from aniworld.models.mangafire_to import series as manga

DARLING = "https://mangafire.to/title/zlwvm-darling-in-the-franxx"
VELVET_KISS = "https://mangafire.to/title/z9w-velvet-kisss"


@cache
def image_bytes(format="PNG"):
    output = BytesIO()
    Image.new("RGB", (8, 8), "red").save(output, format=format)
    return output.getvalue()


def write_archive(path, pages):
    with ZipFile(path, "w") as archive:
        for name, data in pages.items():
            archive.writestr(name, data)


def read_images(path):
    return {
        name: data
        for name, data in read_archive(path).items()
        if Path(name).suffix in (".png", ".jpg", ".gif", ".webp")
    }


def read_archive(path):
    with ZipFile(path) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names))
        return {name: archive.read(name) for name in names}


@pytest.fixture(params=[DARLING, VELVET_KISS], ids=["darling", "velvet-kiss"])
def chapter(monkeypatch, request):
    def make(number=1, selected_pages=None, selected_path=None, format="cbz"):
        result = manga.MangaFireToChapter(
            url=f"{request.param}/chapter/{number}",
            chapter_id=1,
            chapter_number=number,
            selected_pages=selected_pages,
            selected_path=selected_path,
            format=format,
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


@pytest.mark.parametrize("format", ["jpg", "cbz", "epub"])
def test_selected_root_keeps_existing_downloads(
    tmp_path, chapter, fetch, monkeypatch, format
):
    monkeypatch.setenv("ANIWORLD_DOWNLOAD_PATH", str(tmp_path / "ignored"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    item = chapter(selected_path="Manga with spaces")
    item.mangafire_format = format
    destination = item.download()
    folder = tmp_path / "Manga with spaces" / "Chapter 1" / "Chapter 1"
    if format in ("cbz", "epub"):
        assert destination == folder.with_name(f"Chapter 1.{format}")
        assert read_images(destination) == {
            "001.png": image_bytes(),
            "002.png": image_bytes(),
        }
    else:
        assert destination == folder
        assert (folder / "001.png").read_bytes() == image_bytes()
        assert (folder / "002.png").read_bytes() == image_bytes()
    assert fetch.call_count == 2
    assert item.download() == destination
    assert fetch.call_count == 2
    assert not (tmp_path / "ignored").exists()


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


@pytest.mark.parametrize("format", ["cbz", "epub"])
def test_fractional_chapters_have_distinct_archives(tmp_path, chapter, fetch, format):
    archives = []
    for number in (1, 1.5, 1.6):
        item = chapter(number, format=format)
        path = item.download(tmp_path / item.folder_name)
        assert path.name == f"Chapter {number}.{format}"
        archives.append(path)
    assert len(set(archives)) == 3
    assert all(path.is_file() for path in archives)


@pytest.mark.parametrize("format", ["cbz", "epub"])
def test_chapter_title_with_dots_is_preserved(tmp_path, chapter, fetch, format):
    item = chapter(1.5, format=format)
    item.chapter_name = "Bonus. Part 2"
    assert (
        item.download(tmp_path / item.folder_name).name
        == f"Chapter 1.5 - Bonus. Part 2.{format}"
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


@pytest.mark.parametrize("format", ["cbz", "epub"])
def test_archive_repairs_bad_images_and_preserves_valid_pages(
    tmp_path, chapter, fetch, format
):
    item = chapter(format=format)
    folder = tmp_path / item.folder_name
    archive = tmp_path / f"{item.folder_name}.{format}"
    original = image_bytes("JPEG")
    write_archive(archive, {"001.png": original, "002.png": b"broken image"})
    item.download(folder)
    assert read_images(archive) == {
        ("001.jpg" if format == "epub" else "001.png"): original,
        "002.png": image_bytes(),
    }
    fetch.assert_called_once_with("https://example.invalid/2.png")
    item.download(folder)
    assert fetch.call_count == 1


@pytest.mark.parametrize("format", ["cbz", "epub"])
def test_invalid_zip_is_rebuilt(tmp_path, chapter, fetch, format):
    item = chapter(format=format)
    archive = tmp_path / f"{item.folder_name}.{format}"
    archive.write_bytes(b"broken zip")
    item.download(tmp_path / item.folder_name)
    assert read_images(archive) == dict.fromkeys(("001.png", "002.png"), image_bytes())


@pytest.mark.parametrize("format", ["cbz", "epub"])
@pytest.mark.parametrize("failure", ["download", "write", "verify", "replace"])
def test_failed_update_preserves_original_archive(
    tmp_path, chapter, fetch, monkeypatch, failure, format
):
    item = chapter(format=format)
    folder = tmp_path / item.folder_name
    archive = tmp_path / f"{item.folder_name}.{format}"
    write_archive(archive, {"001.png": image_bytes()})
    original = archive.read_bytes()
    if failure == "download":
        fetch.side_effect = OSError("download failed")
    elif failure == "write":
        monkeypatch.setattr(ZipFile, "writestr", Mock(side_effect=OSError("disk full")))
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


@pytest.mark.parametrize("format", ["cbz", "epub"])
def test_subset_update_preserves_unselected_pages(tmp_path, chapter, fetch, format):
    folder = tmp_path / "Chapter 1"
    archive = chapter(selected_pages=[1], format=format).download(folder)
    chapter(selected_pages=[2], format=format).download(folder)
    assert read_images(archive) == dict.fromkeys(("001.png", "002.png"), image_bytes())
    assert fetch.call_count == 2


def test_png_with_damaged_pixels_is_rejected():
    data = bytearray(image_bytes())
    data[data.index(b"IDAT") + 4] ^= 1
    assert not manga._valid_image(bytes(data))


@pytest.mark.parametrize("format", ["cbz", "epub"])
def test_archive_with_bad_crc_redownloads_page(tmp_path, chapter, fetch, format):
    item = chapter(selected_pages=[1], format=format)
    archive = tmp_path / f"{item.folder_name}.{format}"
    data = image_bytes()
    write_archive(archive, {"001.png": data})
    damaged = bytearray(archive.read_bytes())
    damaged[damaged.index(data) + 20] ^= 1
    archive.write_bytes(damaged)
    item.download(tmp_path / item.folder_name)
    assert read_images(archive) == {"001.png": data}
    fetch.assert_called_once()


@pytest.mark.parametrize("format", ["cbz", "epub"])
def test_empty_selection_does_not_create_archive(tmp_path, chapter, fetch, format):
    item = chapter(selected_pages=[], format=format)
    with pytest.raises(ValueError, match="No MangaFire pages"):
        item.download(tmp_path / item.folder_name)
    assert not (tmp_path / item.folder_name).exists()
    assert not (tmp_path / f"{item.folder_name}.{format}").exists()
    fetch.assert_not_called()


@pytest.mark.parametrize("image_format", ["PNG", "JPEG", "WEBP", "GIF"])
def test_epub_structure_and_image_formats(tmp_path, chapter, fetch, image_format):
    item = chapter(1.5, format="epub")
    item._series = SimpleNamespace(title="Velvet Kiss & <Friends>")
    item.chapter_language = "ja"
    item.chapter_name = "Bonus. Part 2 & Friends"
    # Dimensions must come from the image, even when provider metadata is missing.
    item.pages[0].image.width = 0
    item.pages[0].image.height = 0
    fetch.return_value.content = image_bytes(image_format)
    path = item.download(tmp_path / item.folder_name)
    contents = read_archive(path)
    with ZipFile(path) as archive:
        assert archive.infolist()[0].filename == "mimetype"
        assert archive.getinfo("mimetype").compress_type == ZIP_STORED
        assert archive.read("mimetype") == b"application/epub+zip"
        assert archive.testzip() is None
    ns = {
        "opf": "http://www.idpf.org/2007/opf",
        "dc": "http://purl.org/dc/elements/1.1/",
        "html": "http://www.w3.org/1999/xhtml",
        "epub": "http://www.idpf.org/2007/ops",
        "container": "urn:oasis:names:tc:opendocument:xmlns:container",
    }
    container = ET.fromstring(contents["META-INF/container.xml"])
    assert (
        container.find("container:rootfiles/container:rootfile", ns).get("full-path")
        == "content.opf"
    )
    package = ET.fromstring(contents["content.opf"])
    assert (
        package.find("opf:metadata/dc:title", ns).text
        == "Velvet Kiss & <Friends> - Chapter 1.5 - Bonus. Part 2 & Friends"
    )
    assert package.find("opf:metadata/dc:language", ns).text == "ja"
    assert (
        package.find("opf:metadata/opf:meta[@property='rendition:layout']", ns).text
        == "pre-paginated"
    )
    manifest = {entry.get("id"): entry for entry in package.find("opf:manifest", ns)}
    assert all(entry.get("href") in contents for entry in manifest.values())
    spine = [entry.get("idref") for entry in package.find("opf:spine", ns)]
    assert spine == ["page-1", "page-2"]
    expected = "PNG" if image_format == "WEBP" else image_format
    for page_id in spine:
        page = ET.fromstring(contents[manifest[page_id].get("href")])
        assert (
            page.find("html:head/html:meta", ns).get("content") == "width=8, height=8"
        )
        src = page.find("html:body/html:img", ns).get("src")
        with Image.open(BytesIO(contents[src])) as image:
            assert image.format == expected
            image.load()
    nav = ET.fromstring(contents["nav.xhtml"])
    assert [
        link.get("href")
        for link in nav.findall(
            "html:body/html:nav[@epub:type='toc']/html:ol/html:li/html:a", ns
        )
    ] == ["page-001.xhtml", "page-002.xhtml"]
    assert not (tmp_path / item.folder_name).exists()
    item.download(tmp_path / item.folder_name)
    assert fetch.call_count == 2


def test_epub_page_order_is_numeric(tmp_path, chapter, fetch):
    item = chapter(format="epub", selected_pages=[1000, 2, 10])
    item._MangaFireToChapter__pages = [
        manga.MangaFireToPage(item, n, f"https://example.invalid/{n}.png", 8, 8)
        for n in (1000, 2, 10)
    ]
    archive = item.download(tmp_path / item.folder_name)
    package = ET.fromstring(read_archive(archive)["content.opf"])
    assert [
        entry.get("idref")
        for entry in package.find("{http://www.idpf.org/2007/opf}spine")
    ] == ["page-2", "page-10", "page-1000"]


def test_epub_environment_format(monkeypatch):
    monkeypatch.setenv("ANIWORLD_MANGAFIRE_FORMAT", " EPUB ")
    item = manga.MangaFireToChapter(
        url="https://mangafire.to/title/z9w-velvet-kisss/chapter/1",
        chapter_id=1,
        chapter_number=1,
    )
    assert item.mangafire_format == "epub"


@pytest.mark.parametrize("format", ["jpg", "cbz", "epub"])
def test_pillow_is_only_required_for_epub(
    tmp_path, chapter, fetch, monkeypatch, format
):
    original_import = builtins.__import__

    def without_pillow(name, *args, **kwargs):
        if name == "PIL" or name.startswith("PIL."):
            raise ModuleNotFoundError("No module named 'PIL'", name="PIL")
        return original_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "aniworld.models.mangafire_to.epub", raising=False)
    monkeypatch.setattr(builtins, "__import__", without_pillow)
    item = chapter(format=format)
    folder = tmp_path / item.folder_name
    if format == "epub":
        archive = folder.with_name(folder.name + ".epub")
        archive.write_bytes(b"existing book")
        with pytest.raises(RuntimeError, match=r'pip install "aniworld\[epub\]"'):
            item.download(folder)
        fetch.assert_not_called()
        assert not folder.exists()
        assert archive.read_bytes() == b"existing book"
    else:
        assert item.download(folder).exists()
        assert fetch.call_count == 2


@pytest.fixture
def volume_api(monkeypatch):
    """Source IDs and grouping flags for both titles, with synthetic page data."""
    profiles = [
        (DARLING, "DARLING in the FRANXX", True, [250113, 250114], [4532228, 4532229]),
        (VELVET_KISS, "Velvet Kiss", False, [8124], [5484330, 5484333]),
    ]
    payloads = {}
    for url, title, has_volumes, volume_ids, chapter_ids in profiles:
        slug = url.rsplit("/", 1)[-1]
        hid = slug.split("-", 1)[0]
        prefix = f"titles/{hid}"
        payloads[prefix] = {"data": {"title": title, "hasVolumes": has_volumes}}
        volumes = [
            {"id": item_id, "number": number, "language": "en", "name": ""}
            for number, item_id in enumerate(volume_ids, 1)
        ]
        if has_volumes:
            volumes.append({"id": 181456, "number": 1, "language": "ja", "name": ""})
        else:
            volumes[0]["chapterCount"] = 32  # Velvet Kiss's legacy whole-series bundle.
        payloads[f"{prefix}/volumes"] = {"items": list(reversed(volumes))}
        payloads[f"{prefix}/chapters"] = {
            "items": [
                {
                    "id": item_id,
                    "number": number,
                    "language": "en",
                    "name": "",
                    "type": "unofficial",
                    "createdAt": 0,
                }
                for number, item_id in enumerate(chapter_ids, 1)
            ]
        }
        for kind, ids in (("volumes", volume_ids), ("chapters", chapter_ids)):
            for number, item_id in enumerate(ids, 1):
                payloads[f"{kind}/{item_id}"] = {
                    "data": {
                        "id": item_id,
                        "number": number,
                        "language": "en",
                        "name": "",
                        "type": "volume" if kind == "volumes" else "unofficial",
                        "pages": [
                            {
                                "url": f"https://example.invalid/{hid}/{n}.png",
                                "width": 8,
                                "height": 8,
                            }
                            for n in (1, 2)
                        ],
                        "title": {"name": title, "url": f"/title/{slug}"},
                    }
                }
    calls = []

    def get(url):
        from urllib.parse import urlparse

        path = urlparse(url).path.removeprefix("/api/")
        calls.append(path)
        if url.startswith("https://example.invalid/"):
            return SimpleNamespace(content=image_bytes())
        return SimpleNamespace(json=lambda: payloads[path])

    monkeypatch.setattr(manga, "_get", get)
    return manga.MangaFireToSeries(DARLING), payloads, calls


def test_native_volumes_are_sorted_filtered_and_cached(volume_api):
    series, _, calls = volume_api
    volumes = series.volumes
    assert [volume.volume_number for volume in volumes] == [1, 2]
    assert [volume.url for volume in volumes] == [
        f"{DARLING}/volume/250113",
        f"{DARLING}/volume/250114",
    ]
    assert all(volume.is_volume for volume in volumes)
    assert series.volumes is volumes
    assert calls == ["titles/zlwvm", "titles/zlwvm/volumes"]


@pytest.mark.parametrize("format", ["cbz", "epub"])
def test_series_archives_use_native_volumes(tmp_path, volume_api, format):
    series, _, calls = volume_api
    folder = tmp_path / "DARLING in the FRANXX"
    assert series.download(folder, format=format) == folder
    assert sorted(path.name for path in folder.iterdir()) == [
        f"Volume 1.{format}",
        f"Volume 2.{format}",
    ]
    for path in folder.iterdir():
        assert read_images(path) == dict.fromkeys(("001.png", "002.png"), image_bytes())
    assert "titles/zlwvm/chapters" not in calls
    assert "volumes/250113" in calls
    assert "volumes/250114" in calls


def test_jpg_series_keeps_chapter_images(tmp_path, volume_api):
    series, _, calls = volume_api
    folder = tmp_path / "DARLING in the FRANXX"
    series.download(folder, format="jpg")
    assert sorted(path.name for path in folder.iterdir()) == [
        "Chapter 1",
        "Chapter 2",
    ]
    assert "titles/zlwvm/volumes" not in calls


@pytest.mark.parametrize("format", ["cbz", "epub"])
def test_velvet_kiss_legacy_bundle_is_not_a_published_volume(
    tmp_path, volume_api, format
):
    _, _, calls = volume_api
    series = manga.MangaFireToSeries(VELVET_KISS)
    folder = tmp_path / "Velvet Kiss"
    series.download(folder, format=format)
    assert sorted(path.name for path in folder.iterdir()) == [
        f"Chapter 1.{format}",
        f"Chapter 2.{format}",
    ]
    assert "titles/z9w" in calls
    assert "titles/z9w/volumes" not in calls
    assert "volumes/8124" not in calls


def test_missing_english_volumes_falls_back_to_chapters(volume_api):
    series, payloads, _ = volume_api
    payloads["titles/zlwvm/volumes"]["items"] = [
        {"id": 181456, "number": 1, "language": "ja"}
    ]
    assert series.download_items("cbz") == series.preferred_chapters


def test_volume_fetch_failure_can_be_retried(volume_api, monkeypatch):
    series, _, _ = volume_api
    assert series.title == "DARLING in the FRANXX"
    original = manga._get
    monkeypatch.setattr(manga, "_get", Mock(side_effect=OSError("offline")))
    with pytest.raises(OSError, match="offline"):
        _ = series.volumes
    monkeypatch.setattr(manga, "_get", original)
    assert len(series.volumes) == 2


@pytest.mark.parametrize("format", ["cbz", "epub"])
def test_direct_volume_url_uses_id_but_names_file_by_number(
    tmp_path, volume_api, format
):
    _, _, calls = volume_api
    volume = manga.MangaFireToChapter(
        url=f"{DARLING}/volume/250113", format=format, selected_pages=[2]
    )
    assert calls == []
    destination = volume.download(tmp_path / "Volume 1")
    assert destination.name == f"Volume 1.{format}"
    assert volume.volume_number == 1
    assert volume.chapter_language == "en"
    assert read_images(destination) == {"002.png": image_bytes()}
    assert "volumes/250113" in calls
    assert "chapters/250113" not in calls
    volume.download(tmp_path / "Volume 1")
    assert calls.count("/zlwvm/2.png") == 1


def test_empty_explicit_series_selection_does_not_download_units(tmp_path, volume_api):
    series, _, calls = volume_api
    folder = tmp_path / "DARLING in the FRANXX"
    series.download(folder, chapters=[], format="cbz")
    assert list(folder.iterdir()) == []
    assert calls == []


@pytest.mark.parametrize("format", ["cbz", "epub"])
def test_archive_environment_selects_volumes(tmp_path, volume_api, monkeypatch, format):
    monkeypatch.setenv("ANIWORLD_MANGAFIRE_FORMAT", f" {format.upper()} ")
    series, _, _ = volume_api
    series.download(tmp_path)
    assert (tmp_path / f"Volume 1.{format}").exists()


def test_web_format_selection_lists_volume_pages(client, volume_api):
    _, _, calls = volume_api
    chapters = client.get(
        "/api/seasons", query_string={"url": DARLING, "mangafire_format": "jpg"}
    ).get_json()["seasons"]
    assert [chapter["season_number"] for chapter in chapters] == [1, 2]
    assert not any(chapter["is_volume"] for chapter in chapters)
    calls.clear()
    response = client.get(
        "/api/seasons", query_string={"url": DARLING, "mangafire_format": "epub"}
    )
    assert response.status_code == 200
    volumes = response.get_json()["seasons"]
    assert [volume["season_number"] for volume in volumes] == [1, 2]
    assert all(volume["is_volume"] for volume in volumes)
    assert "titles/zlwvm/chapters" not in calls
    response = client.get(
        "/api/episodes",
        query_string={"url": volumes[0]["url"], "series_url": DARLING},
    )
    assert response.status_code == 200
    pages = response.get_json()["episodes"]
    assert [page["page_number"] for page in pages] == [1, 2]
    assert all(page["chapter_url"] == f"{DARLING}/volume/250113" for page in pages)


def test_worker_preserves_volume_url_and_page_selection(tmp_path, volume_api):
    from aniworld.web import worker

    provider, volume = worker._build_episode(
        f"{DARLING}/volume/250113",
        {"_format": "cbz", "selected_pages": [2]},
        {"language": "MangaFire", "provider": "MangaFire"},
        str(tmp_path),
    )
    assert provider.name == "MangaFire"
    assert volume.series.series_url == DARLING
    assert volume.is_volume
    assert volume.selected_pages == [2]
    destination = volume.download()
    assert destination == tmp_path / "DARLING in the FRANXX" / "Volume 1.cbz"
    assert read_images(destination) == {"002.png": image_bytes()}


@pytest.mark.parametrize("format", ["cbz", "epub"])
def test_explicit_chapters_override_automatic_volume_selection(
    tmp_path, volume_api, format
):
    series, _, calls = volume_api
    folder = tmp_path / "DARLING in the FRANXX"
    series.download(folder, chapters=series.preferred_chapters[:1], format=format)
    assert [path.name for path in folder.iterdir()] == [f"Chapter 1.{format}"]
    assert "titles/zlwvm/volumes" not in calls
    assert "volumes/250113" not in calls


def test_cli_recognizes_source_volume_urls(volume_api):
    from aniworld.entry import model_for_url

    _, _, calls = volume_api
    volume = model_for_url(f"{DARLING}/volume/250113")
    assert isinstance(volume, manga.MangaFireToChapter)
    assert volume.is_volume
    assert calls == []
    assert volume.volume_number == 1
    assert volume.folder_name == "Volume 1"
