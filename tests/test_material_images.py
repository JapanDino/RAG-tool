import io

from material_image_fixtures import docx, pdf, png
from PIL import Image

from backend.app.services import material_images as extraction


def test_docx_illustration_has_real_caption_and_nearby_text():
    result = extraction.extract_docx(docx())
    assert len(result.images) == 1 and result.skipped == 0
    picture = result.images[0]
    assert picture.caption == "Схема связи фаз фотосинтеза"
    assert picture.location == "Абзац 2" and picture.page is None
    assert "Световая фаза" in picture.context and "Рисунок 1" in picture.context
    assert Image.open(io.BytesIO(picture.data)).format == "PNG"


def test_pdf_images_keep_page_context_and_distinct_pixels():
    result = extraction.extract_pdf(pdf())
    assert len(result.images) == 2 and result.skipped == 0
    assert [image.page for image in result.images] == [1, 2]
    assert "light phase" in result.images[0].context
    assert "stroma" in result.images[1].context
    assert result.images[0].data != result.images[1].data


def test_external_and_broken_docx_images_preserve_readable_text():
    for document in [docx(external=True), docx(b"not an image")]:
        result = extraction.extract_docx(document)
        assert "Световая фаза" in result.text
        assert result.images == [] and result.skipped == 1


def test_limits_skip_images_without_hiding_text(monkeypatch):
    monkeypatch.setattr(extraction, "MAX_IMAGES", 1)
    result = extraction.extract_pdf(pdf())
    assert len(result.images) == 1 and result.skipped == 1
    assert "stroma" in result.text
    monkeypatch.setattr(extraction, "MAX_PIXELS", 100)
    result = extraction.extract_docx(docx())
    assert not result.images and result.skipped == 1


def test_normalization_downsizes_and_caps_total_bytes(monkeypatch):
    output = io.BytesIO()
    Image.new("RGB", (2000, 1000), "white").save(output, "PNG")
    result = extraction.ExtractedMaterial()
    result.add(output.getvalue(), caption="Test", context="Text", location="Page 1")
    assert (result.images[0].width, result.images[0].height) == (1600, 800)
    monkeypatch.setattr(extraction, "MAX_TOTAL_BYTES", 1)
    result = extraction.extract_docx(docx(png()))
    assert not result.images and result.skipped == 1


def test_normalized_illustration_does_not_keep_exif_metadata():
    metadata = Image.Exif()
    metadata[315] = "Synthetic private author"
    output = io.BytesIO()
    Image.new("RGB", (100, 100), "white").save(output, "JPEG", exif=metadata)
    result = extraction.extract_docx(docx(output.getvalue()))
    clean = Image.open(io.BytesIO(result.images[0].data))
    assert len(clean.getexif()) == 0
