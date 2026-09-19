"""Import page illustrations only through course-scoped Canvas file metadata."""

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from . import canvas_client
from .material_images import MAX_IMAGE_BYTES, MAX_IMAGES, ExtractedMaterial


def page_hash(body: str) -> str:
    return "html-v1:" + hashlib.sha256(body.encode()).hexdigest()


def file_version(info: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                key: info.get(key)
                for key in (
                    "id",
                    "updated_at",
                    "modified_at",
                    "size",
                    "md5",
                    "content-type",
                )
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()


def file_available(info: dict) -> bool:
    if any(
        info.get(key)
        for key in (
            "locked",
            "hidden",
            "locked_for_user",
            "hidden_for_user",
            "lock_info",
        )
    ):
        return False
    if info.get("visibility_level") not in (None, "inherit", "course", "public"):
        return False
    now = datetime.now(timezone.utc)
    try:
        for key, future_blocks in (("unlock_at", True), ("lock_at", False)):
            if info.get(key):
                when = datetime.fromisoformat(info[key].replace("Z", "+00:00"))
                if (when > now) == future_blocks:
                    return False
    except (TypeError, ValueError):
        return False
    return bool(info.get("updated_at") or info.get("modified_at") or info.get("md5"))


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.scheme not in ("http", "https"):
        raise ValueError("Invalid file origin")
    return f"{parsed.scheme}://{parsed.netloc.lower()}"


def download_image(url: str) -> bytes:
    base = canvas_client._base_url()
    canvas_origin = _origin(base)
    allowed = {canvas_origin}
    for value in os.getenv("CANVAS_FILE_ORIGINS", "").split(","):
        value = value.strip().rstrip("/")
        if value and value.startswith("https://") and _origin(value) == value:
            allowed.add(value)
    for _ in range(4):
        origin = _origin(url)
        if origin not in allowed:
            raise ValueError("Canvas file host is not configured")
        # Never forward the Canvas token to a CDN or a URL from page HTML.
        headers = canvas_client._headers() if origin == canvas_origin else {}
        with requests.get(
            url, headers=headers, timeout=(5, 15), stream=True, allow_redirects=False
        ) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                url = urljoin(url, response.headers["Location"])
                continue
            response.raise_for_status()
            if int(response.headers.get("Content-Length", "0")) > MAX_IMAGE_BYTES:
                raise ValueError("Image too large")
            data = bytearray()
            for block in response.iter_content(64 * 1024):
                data.extend(block)
                if len(data) > MAX_IMAGE_BYTES:
                    raise ValueError("Image too large")
            return bytes(data)
    raise ValueError("Too many redirects")


def extract_canvas_images(body: str, course_id: int) -> ExtractedMaterial:
    soup = BeautifulSoup(body, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    result = ExtractedMaterial()
    base = canvas_client._base_url()
    images = soup.find_all("img")
    result.skipped = max(0, len(images) - MAX_IMAGES)
    for index, image in enumerate(images[:MAX_IMAGES], 1):
        try:
            src = image.get("data-api-endpoint") or image.get("src") or ""
            url = urljoin(base + "/", src)
            if _origin(url) != _origin(base):
                raise ValueError("External illustration")
            match = re.fullmatch(
                r"(?:/api/v1)?(?:/courses/(\d+))?/files/(\d+)(?:/(?:preview|download))?",
                urlsplit(url).path,
            )
            if not match or (match[1] and int(match[1]) != course_id):
                raise ValueError("Not a course file")
            file_id = int(match[2])
            info = canvas_client.get_file(course_id, file_id)
            if info.get("id") != file_id or not file_available(info):
                raise ValueError("Unavailable file")
            if (
                not (info.get("content-type") or "").startswith("image/")
                or int(info.get("size", 0)) > MAX_IMAGE_BYTES
            ):
                raise ValueError("Unsupported image")
            figure = image.find_parent("figure")
            caption_node = figure.find("figcaption") if figure else None
            caption = image.get("alt") or (
                caption_node.get_text(" ", strip=True) if caption_node else ""
            )
            block = image.find_parent(["figure", "p", "div", "td"]) or image.parent
            context = " ".join(
                node.get_text(" ", strip=True)
                for node in [
                    block.find_previous_sibling(),
                    block,
                    block.find_next_sibling(),
                ]
                if node
            )
            before = len(result.images)
            result.add(
                download_image(info["url"]),
                caption=caption or f"Иллюстрация {index}",
                context=caption + " " + context,
                location=f"Страница Canvas · иллюстрация {index}",
            )
            if len(result.images) > before:
                result.images[-1].canvas_file_id = file_id
                result.images[-1].canvas_file_version = file_version(info)
        except Exception:  # noqa: BLE001 - One unavailable image must not discard the page text.
            result.skipped += 1
    return result
