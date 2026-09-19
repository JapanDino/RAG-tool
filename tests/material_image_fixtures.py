"""Small synthetic documents shared by image extraction and API tests."""

import io
import zipfile

from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
)


def png():
    output = io.BytesIO()
    Image.new("RGB", (180, 90), "#14865b").save(output, "PNG")
    return output.getvalue()


def docx(picture=None, external=False):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            "word/document.xml",
            """<w:document
          xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
          xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
          xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">
          <w:body><w:p><w:r><w:t>Световая фаза образует АТФ и НАДФН для цикла Кальвина.</w:t></w:r></w:p>
          <w:p><w:r><w:drawing><wp:docPr id="1" descr="Схема связи фаз фотосинтеза"/>
          <a:blip r:embed="rId1"/></w:drawing></w:r></w:p>
          <w:p><w:r><w:t>Рисунок 1. АТФ и НАДФН используются в цикле Кальвина.</w:t></w:r></w:p>
          </w:body></w:document>""",
        )
        target = (
            "https://example.invalid/private.png" if external else "media/image.png"
        )
        mode = ' TargetMode="External"' if external else ""
        archive.writestr(
            "word/_rels/document.xml.rels",
            f'''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="{target}"{mode}/></Relationships>''',
        )
        archive.writestr("word/media/image.png", png() if picture is None else picture)
    return output.getvalue()


def pdf():
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    for label, color in [
        ("Photosynthesis light phase produces ATP and NADPH.", "green"),
        ("Calvin cycle uses ATP and NADPH in the stroma.", "blue"),
    ]:
        page = writer.add_blank_page(width=595, height=842)
        raw = Image.new("RGB", (180, 90), color)
        asset = DecodedStreamObject()
        asset.set_data(raw.tobytes())
        asset.update(
            {
                NameObject("/Type"): NameObject("/XObject"),
                NameObject("/Subtype"): NameObject("/Image"),
                NameObject("/Width"): NumberObject(180),
                NameObject("/Height"): NumberObject(90),
                NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
                NameObject("/BitsPerComponent"): NumberObject(8),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref}),
                NameObject("/XObject"): DictionaryObject(
                    {NameObject("/Im0"): writer._add_object(asset)}
                ),
            }
        )
        stream = DecodedStreamObject()
        stream.set_data(
            f"BT /F1 14 Tf 40 780 Td ({label}) Tj ET q 360 0 0 180 40 500 cm /Im0 Do Q".encode()
        )
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
