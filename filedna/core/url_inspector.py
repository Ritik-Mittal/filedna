"""
FileDNA – URL inspector.

Uses HTTP HEAD requests to determine content-type and metadata.
Uses httpx (modern requests replacement: async-capable, HTTP/2, better timeouts).
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def inspect_url(url: str, timeout: int = 10) -> dict[str, Any]:
    """
    Validate URL and fetch metadata via HEAD request.

    Returns a dict with keys:
        valid, url, mime, real_type, size_bytes, size_human,
        status_code, content_encoding, server, warnings, errors
    """
    from ..inspectors.metadata import human_size

    result: dict[str, Any] = {
        "valid": False,
        "url": url,
        "mime": None,
        "real_type": "unknown",
        "size_bytes": None,
        "size_human": None,
        "status_code": None,
        "content_encoding": None,
        "server": None,
        "warnings": [],
        "errors": [],
    }

    # Basic URL validation
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            result["errors"].append(f"Unsupported scheme: {parsed.scheme!r}")
            return result
        if not parsed.netloc:
            result["errors"].append("URL has no host")
            return result
    except Exception as exc:
        result["errors"].append(f"Invalid URL: {exc}")
        return result

    # HEAD request via httpx (modern requests replacement)
    try:
        import httpx  # type: ignore
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.head(url)

        result["status_code"] = resp.status_code

        if resp.status_code >= 400:
            result["errors"].append(f"HTTP {resp.status_code}: {resp.reason_phrase}")
            return result

        headers = resp.headers
        mime = headers.get("content-type", "").split(";")[0].strip()
        result["mime"] = mime or None
        result["content_encoding"] = headers.get("content-encoding")
        result["server"] = headers.get("server")

        content_length = headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
                result["size_bytes"] = size
                result["size_human"] = human_size(size)
            except ValueError:
                pass

        result["real_type"] = _mime_to_type(mime)
        result["valid"] = True

        if not mime:
            result["warnings"].append("Server did not return Content-Type")

    except Exception as exc:
        result["errors"].append(f"Request failed: {exc}")
        return result

    return result


_MIME_MAP: dict[str, str] = {
    "application/pdf": "pdf",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/svg+xml": "svg",
    "image/tiff": "tiff",
    "image/bmp": "bmp",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/flac": "flac",
    "audio/ogg": "ogg",
    "audio/aac": "aac",
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "video/x-matroska": "mkv",
    "video/webm": "webm",
    "video/x-msvideo": "avi",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/zip": "zip",
    "application/gzip": "gz",
    "application/x-tar": "tar",
    "application/x-bzip2": "bz2",
    "application/x-7z-compressed": "7z",
    "application/x-rar-compressed": "rar",
    "application/json": "json",
    "application/xml": "xml",
    "text/html": "html",
    "text/plain": "txt",
    "text/csv": "csv",
    "text/markdown": "md",
    "application/epub+zip": "epub",
}


def _mime_to_type(mime: str) -> str:
    return _MIME_MAP.get(mime, "unknown")
