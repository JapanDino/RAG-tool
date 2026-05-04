import gc
import io
import logging
import os
import re

logger = logging.getLogger(__name__)

DEFAULT_MAX_TEXT_CHARS = int(os.getenv("TEXT_EXTRACT_MAX_CHARS", "120000"))
DEFAULT_PDF_MAX_PAGES = int(os.getenv("PDF_TEXT_MAX_PAGES", "40"))
DEFAULT_PDF_OCR_MAX_PAGES = int(os.getenv("PDF_OCR_MAX_PAGES", "8"))
DEFAULT_PDF_OCR_MAX_BYTES = int(os.getenv("PDF_OCR_MAX_BYTES", str(8 * 1024 * 1024)))
DEFAULT_ENABLE_PDF_OCR = os.getenv("ENABLE_PDF_OCR", "1").lower() not in {"0", "false", "no"}


def _collapse_text(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _clip_text(text: str, max_chars: int | None) -> str:
    if max_chars and len(text) > max_chars:
        return text[:max_chars].rstrip()
    return text


def extract_text(
    filename: str,
    content_type: str,
    data: bytes,
    *,
    max_chars: int | None = None,
    pdf_max_pages: int | None = None,
    allow_ocr: bool | None = None,
    ocr_max_pages: int | None = None,
) -> str:
    is_pdf = (content_type == "application/pdf" or
              (filename or "").lower().endswith(".pdf"))
    if is_pdf:
        return extract_pdf(
            data,
            max_chars=max_chars,
            max_pages=pdf_max_pages,
            allow_ocr=allow_ocr,
            ocr_max_pages=ocr_max_pages,
        )
    try:
        text = data.decode("utf-8")
    except Exception:
        text = data.decode("latin-1", errors="ignore")
    return _clip_text(_collapse_text(text), max_chars or DEFAULT_MAX_TEXT_CHARS)


def _pdf_page_count(data: bytes) -> int:
    try:
        from pypdf import PdfReader as _R

        return max(1, len(_R(io.BytesIO(data)).pages))
    except Exception:
        return 1


def extract_pdf(
    data: bytes,
    *,
    max_chars: int | None = None,
    max_pages: int | None = None,
    allow_ocr: bool | None = None,
    ocr_max_pages: int | None = None,
) -> str:
    """Extract text from PDF.
    1. Try pdfminer.six (best for native/vector PDFs).
    2. Fall back to pypdf if pdfminer fails.
    3. If extracted text is too short (scanned PDF), run Tesseract OCR.
    """
    max_chars = max_chars or DEFAULT_MAX_TEXT_CHARS
    page_count = _pdf_page_count(data)
    page_limit = max(1, min(page_count, max_pages or DEFAULT_PDF_MAX_PAGES))
    page_numbers = list(range(page_limit))
    if page_count > page_limit:
        logger.info("PDF extraction capped to %d/%d pages", page_limit, page_count)

    try:
        from pdfminer.high_level import extract_text as pdfminer_extract
        from pdfminer.layout import LAParams
        params = LAParams(char_margin=3.0, word_margin=0.2, line_margin=0.5)
        text = pdfminer_extract(
            io.BytesIO(data),
            laparams=params,
            page_numbers=page_numbers,
        )
    except Exception:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages[:page_limit]]
        text = "\n\n".join(pages)

    text = _clip_text(_collapse_text(text), max_chars)

    # Heuristic: if fewer than 50 meaningful characters per page, treat as scan
    processed_pages = max(1, page_limit)
    chars_per_page = len(text.replace(" ", "").replace("\n", "")) / processed_pages

    ocr_enabled = DEFAULT_ENABLE_PDF_OCR if allow_ocr is None else allow_ocr
    ocr_page_limit = ocr_max_pages or DEFAULT_PDF_OCR_MAX_PAGES
    if chars_per_page < 50 and ocr_enabled:
        if len(data) > DEFAULT_PDF_OCR_MAX_BYTES:
            logger.info(
                "Skipping OCR for PDF larger than %d bytes (%d bytes)",
                DEFAULT_PDF_OCR_MAX_BYTES,
                len(data),
            )
        elif processed_pages > ocr_page_limit:
            logger.info(
                "Skipping OCR for PDF with %d processed pages (limit %d)",
                processed_pages,
                ocr_page_limit,
            )
        else:
            text = ocr_pdf(data, max_pages=processed_pages) or text

    return text


OCR_PAGE_TIMEOUT = int(os.getenv("OCR_PAGE_TIMEOUT_S", "30"))  # seconds per page


def _ocr_page(data: bytes, page_num: int, total_pages: int) -> str:
    """OCR a single PDF page. Runs in a thread so it can be cancelled on timeout."""
    import pytesseract
    from pdf2image import convert_from_bytes

    images = convert_from_bytes(data, dpi=150, first_page=page_num, last_page=page_num)
    if not images:
        return ""
    image = images[0]
    page_text = pytesseract.image_to_string(image, lang="rus+eng")
    image.close()
    del images
    gc.collect()
    logger.info("OCR page %d/%s done", page_num, total_pages or "?")
    return page_text.strip()


def ocr_pdf(data: bytes, max_pages: int | None = None) -> str:
    """Convert each PDF page to an image and run Tesseract OCR.

    Processes one page at a time to avoid loading all pages into RAM at once.
    Each page is OCR-ed in a separate thread with a timeout of OCR_PAGE_TIMEOUT_S
    seconds (default 30) so a bad page never hangs the Celery worker indefinitely.
    """
    import concurrent.futures

    try:
        from pypdf import PdfReader as _R

        try:
            total_pages = len(_R(io.BytesIO(data)).pages)
        except Exception:
            total_pages = 0

        pages_text = []
        effective_total = min(total_pages, max_pages or total_pages) if total_pages else 1
        page_range = range(1, effective_total + 1)
        for page_num in page_range:
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    future = ex.submit(_ocr_page, data, page_num, total_pages)
                    try:
                        page_text = future.result(timeout=OCR_PAGE_TIMEOUT)
                        pages_text.append(page_text)
                    except concurrent.futures.TimeoutError:
                        logger.warning(
                            "OCR page %d timed out after %ds, skipping",
                            page_num, OCR_PAGE_TIMEOUT,
                        )
            except Exception as e:
                logger.warning("OCR failed on page %d: %s", page_num, e)

        return "\n\n".join(p for p in pages_text if p)
    except Exception as e:
        logger.warning("OCR unavailable or failed: %s", e)
        return ""
