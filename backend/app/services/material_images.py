"""Bounded extraction of embedded raster illustrations; no external URL fetching."""

from __future__ import annotations

import io
import posixpath
import warnings
import zipfile
from dataclasses import dataclass, field

from defusedxml import ElementTree
from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from pypdf import PdfReader

MAX_IMAGES = 20
MAX_PIXELS = 12_000_000
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_TOTAL_BYTES = 10 * 1024 * 1024


@dataclass
class Illustration:
    data: bytes
    width: int
    height: int
    caption: str
    context: str
    location: str
    page: int | None = None
    canvas_file_id: int | None = None
    canvas_file_version: str | None = None


@dataclass
class ExtractedMaterial:
    text: str = ""
    images: list[Illustration] = field(default_factory=list)
    skipped: int = 0

    def add(self, data: bytes, *, caption: str, context: str, location: str, page=None):
        if len(self.images) >= MAX_IMAGES or len(data) > MAX_IMAGE_BYTES:
            self.skipped += 1
            return
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as original:
                    if original.width * original.height > MAX_PIXELS:
                        self.skipped += 1
                        return
                    picture = ImageOps.exif_transpose(original).convert("RGBA")
                    picture.thumbnail((1600, 1600))
                    picture.info.clear()
                    output = io.BytesIO()
                    picture.save(output, format="PNG")
                    clean = output.getvalue()
            if len(clean) + sum(len(i.data) for i in self.images) > MAX_TOTAL_BYTES:
                self.skipped += 1
                return
            self.images.append(
                Illustration(
                    clean,
                    picture.width,
                    picture.height,
                    caption[:500],
                    " ".join(context.split())[:1500],
                    location,
                    page,
                )
            )
        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ):
            self.skipped += 1


def _xml(archive: zipfile.ZipFile, name: str):
    if archive.getinfo(name).file_size > 4 * 1024 * 1024:
        raise HTTPException(413, "DOCX содержит слишком большой текстовый блок")
    return ElementTree.fromstring(archive.read(name))


def extract_docx(data: bytes) -> ExtractedMaterial:
    result = ExtractedMaterial()
    ns = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
        "v": "urn:schemas-microsoft-com:vml",
    }
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = _xml(archive, "word/document.xml")
        paragraphs = root.findall(".//w:body//w:p", ns)
        texts = [
            "".join(n.text or "" for n in p.findall(".//w:t", ns)) for p in paragraphs
        ]
        result.text = "\n".join(texts)
        relationships = {}
        if "word/_rels/document.xml.rels" in archive.namelist():
            relationships = {
                r.get("Id"): r for r in _xml(archive, "word/_rels/document.xml.rels")
            }
        for index, paragraph in enumerate(paragraphs):
            pictures = paragraph.findall(".//a:blip", ns) + paragraph.findall(
                ".//v:imagedata", ns
            )
            descriptions = paragraph.findall(".//wp:docPr", ns)
            for number, picture in enumerate(pictures):
                rel_id = picture.get(f"{{{ns['r']}}}embed") or picture.get(
                    f"{{{ns['r']}}}id"
                )
                rel = relationships.get(rel_id)
                if (
                    rel is None
                    or rel.get("TargetMode") == "External"
                    or not (rel.get("Type") or "").endswith("/image")
                ):
                    result.skipped += 1
                    continue
                target = rel.get("Target", "")
                path = posixpath.normpath(posixpath.join("word", target))
                if (
                    not path.startswith("word/media/")
                    or "\\" in target
                    or path not in archive.namelist()
                ):
                    result.skipped += 1
                    continue
                if (
                    len(result.images) >= MAX_IMAGES
                    or archive.getinfo(path).file_size > MAX_IMAGE_BYTES
                ):
                    result.skipped += 1
                    continue
                description = (
                    descriptions[number] if number < len(descriptions) else None
                )
                caption = (
                    (description.get("descr") or description.get("title") or "")
                    if description is not None
                    else ""
                )
                context = "\n".join(texts[max(0, index - 1) : index + 3])
                result.add(
                    archive.read(path),
                    caption=caption or f"Иллюстрация {len(result.images) + 1}",
                    context=caption + "\n" + context,
                    location=f"Абзац {index + 1}",
                )
    return result


def extract_pdf(data: bytes) -> ExtractedMaterial:
    result = ExtractedMaterial()
    reader = PdfReader(io.BytesIO(data))
    if len(reader.pages) > 40:
        raise HTTPException(
            413, "Лимит пилота: 40 страниц PDF. Разделите документ на главы."
        )
    pages = []
    for number, page in enumerate(reader.pages, 1):
        content = page.extract_text() or ""
        pages.append(content)
        if sum(map(len, pages)) > 60000:
            raise HTTPException(
                413,
                "Лимит пилота: 60 000 символов на материал. Разделите документ на главы.",
            )
        for key in page.images.keys():  # noqa: SIM118 - Iterating pypdf images yields decoded images, not keys.
            if len(result.images) >= MAX_IMAGES:
                result.skipped += 1
                continue
            try:
                # Check declared size before pypdf decodes XObject pixel data.
                resource = page
                for part in [key] if isinstance(key, str) else key:
                    resource = resource["/Resources"]["/XObject"][part].get_object()
                if (
                    int(resource.get("/Width", MAX_PIXELS + 1))
                    * int(resource.get("/Height", 1))
                    > MAX_PIXELS
                ):
                    result.skipped += 1
                    continue
                extracted = page.images[key]
                result.add(
                    extracted.data,
                    caption=f"Иллюстрация со страницы {number}",
                    context=content,
                    location=f"Страница {number}",
                    page=number,
                )
            except Exception:  # noqa: BLE001 - Unsupported PDF image must not discard readable text.
                result.skipped += 1
    result.text = "\n\n".join(pages)
    return result
