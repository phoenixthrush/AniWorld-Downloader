"""Package chapter or volume images as a fixed-layout EPUB 3 book."""

from datetime import UTC, datetime
from html import escape
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_STORED

from PIL import Image


def write_epub(archive, chapter, title, images):
    """Write image pages, metadata, and navigation into an open ZIP archive."""
    title = escape(f"{title} - {chapter.folder_name}")
    language = escape(chapter.chapter_language or "en")
    modified = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    archive.writestr("mimetype", "application/epub+zip", compress_type=ZIP_STORED)
    archive.writestr(
        "META-INF/container.xml",
        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">'
        '<rootfiles><rootfile full-path="content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>',
    )
    manifest = [
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
    ]
    spine = []
    links = []
    for name in sorted(images, key=lambda name: int(Path(name).stem)):
        number = int(Path(name).stem)
        data = images[name]
        with Image.open(BytesIO(data)) as image:
            width, height = image.size
            image.load()
            suffix, media_type = {
                "JPEG": ("jpg", "image/jpeg"),
                "PNG": ("png", "image/png"),
                "GIF": ("gif", "image/gif"),
            }.get(image.format, ("png", "image/png"))
            if image.format not in ("JPEG", "PNG", "GIF"):
                output = BytesIO()
                image.convert("RGBA").save(output, format="PNG")
                data = output.getvalue()
        image_name = f"{number:03}.{suffix}"
        page_name = f"page-{number:03}.xhtml"
        archive.writestr(image_name, data)
        archive.writestr(
            page_name,
            '<html xmlns="http://www.w3.org/1999/xhtml"><head>'
            f'<title>Page {number}</title><meta name="viewport" '
            f'content="width={width}, height={height}"/>'
            "<style>html,body{margin:0;padding:0;width:100%;height:100%;}img{display:block;width:100%;height:100%;}</style>"
            f'</head><body><img src="{image_name}" alt="Page {number}"/></body></html>',
        )
        cover = ' properties="cover-image"' if not spine else ""
        manifest.extend(
            [
                f'<item id="image-{number}" href="{image_name}" media-type="{media_type}"{cover}/>',
                f'<item id="page-{number}" href="{page_name}" media-type="application/xhtml+xml"/>',
            ]
        )
        spine.append(f'<itemref idref="page-{number}"/>')
        links.append(f'<li><a href="{page_name}">Page {number}</a></li>')
    first_page = f"page-{min(int(Path(name).stem) for name in images):03}.xhtml"
    archive.writestr(
        "nav.xhtml",
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
        f'<head><title>{title}</title></head><body><nav epub:type="toc">'
        f"<h1>{title}</h1><ol>{''.join(links)}</ol></nav>"
        '<nav epub:type="landmarks" hidden="hidden"><ol><li>'
        f'<a epub:type="bodymatter" href="{first_page}">Start</a></li></ol></nav></body></html>',
    )
    archive.writestr(
        "content.opf",
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:identifier id="book-id">{escape(chapter.url)}</dc:identifier>'
        f"<dc:title>{title}</dc:title><dc:language>{language}</dc:language>"
        f'<meta property="dcterms:modified">{modified}</meta>'
        '<meta property="rendition:layout">pre-paginated</meta>'
        '<meta property="rendition:spread">none</meta></metadata>'
        f"<manifest>{''.join(manifest)}</manifest><spine>{''.join(spine)}</spine>"
        f'<guide><reference type="text" title="Start" href="{first_page}"/></guide></package>',
    )
