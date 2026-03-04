import io
import logging
import re

logger = logging.getLogger(__name__)


def extract_text(filename: str, content_type: str, data: bytes) -> str:
    is_pdf = (content_type == "application/pdf" or
              (filename or "").lower().endswith(".pdf"))
    if is_pdf:
        return extract_pdf(data)
    try:
        return data.decode("utf-8")
    except Exception:
        return data.decode("latin-1", errors="ignore")


def extract_pdf(data: bytes) -> str:
    """Extract text from PDF.
    1. Try pdfminer.six (best for native/vector PDFs).
    2. Fall back to pypdf if pdfminer fails.
    3. If extracted text is too short (scanned PDF), run Tesseract OCR.
    """
    try:
        from pdfminer.high_level import extract_text as pdfminer_extract
        from pdfminer.layout import LAParams
        params = LAParams(char_margin=3.0, word_margin=0.2, line_margin=0.5)
        text = pdfminer_extract(io.BytesIO(data), laparams=params)
    except Exception:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n\n".join(pages)

    text = re.sub(r'\n{3,}', '\n\n', text).strip()

    # Heuristic: if fewer than 50 meaningful characters per page, treat as scan
    try:
        from pypdf import PdfReader as _R
        page_count = max(1, len(_R(io.BytesIO(data)).pages))
    except Exception:
        page_count = 1
    chars_per_page = len(text.replace(" ", "").replace("\n", "")) / page_count

    if chars_per_page < 50:
        text = ocr_pdf(data) or text

    return text


def ocr_pdf(data: bytes) -> str:
    """Convert each PDF page to an image and run Tesseract OCR.

    Processes one page at a time to avoid loading all pages into RAM at once
    (a 300-page scan at 250 DPI would consume ~5 GB otherwise).
    DPI 150 is sufficient for OCR and is 4x lighter than 250.
    No page limit — intended to be called from a Celery worker.
    """
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
        from pypdf import PdfReader as _R

        try:
            total_pages = len(_R(io.BytesIO(data)).pages)
        except Exception:
            total_pages = 0

        pages_text = []
        page_range = range(1, total_pages + 1) if total_pages else [1]
        for page_num in page_range:
            try:
                images = convert_from_bytes(
                    data, dpi=150, first_page=page_num, last_page=page_num
                )
                if images:
                    page_text = pytesseract.image_to_string(images[0], lang="rus+eng")
                    pages_text.append(page_text.strip())
                    logger.info("OCR page %d/%s done", page_num, total_pages or "?")
            except Exception as e:
                logger.warning("OCR failed on page %d: %s", page_num, e)

        return "\n\n".join(p for p in pages_text if p)
    except Exception as e:
        logger.warning("OCR unavailable or failed: %s", e)
        return ""
