import hashlib
import os
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf", ".csv"}
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))


def read_validated_upload(file: UploadFile) -> tuple[str, str, bytes, str]:
    raw_name = file.filename or "upload"
    filename = Path(raw_name).name
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, f"unsupported file type: {extension or 'none'}")

    content_type = (file.content_type or "application/octet-stream").lower()
    if (
        content_type != "application/pdf"
        and not content_type.startswith("text/")
        and content_type != "application/octet-stream"
    ):
        raise HTTPException(415, f"unsupported MIME type: {content_type}")

    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(400, "empty file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"file exceeds {MAX_UPLOAD_BYTES} bytes")
    digest = hashlib.sha256(data).hexdigest()
    return filename, content_type, data, digest


def persist_upload(data: bytes, filename: str, upload_dir: str) -> tuple[str, str]:
    root = Path(upload_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{Path(filename).suffix.lower()}"
    path = (root / stored_name).resolve()
    if root not in path.parents:
        raise HTTPException(400, "invalid upload path")
    path.write_bytes(data)
    return str(path), f"upload://{stored_name}"
