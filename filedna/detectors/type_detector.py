"""
FileDNA – type detector.

Identifies the *real* type of a file using:
  1. magic bytes / binary signatures (fast, no deps)
  2. filetype library (fast)
  3. puremagic (fallback)
  4. MIME-type heuristics on extension (last resort)

All detection is content-based; extensions are deliberately ignored.
"""
from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Magic-byte signatures  {type_name: [(offset, bytes), ...]}
# All matches are AND-ed; first winning entry wins (order matters).
# ---------------------------------------------------------------------------
_SIGNATURES: list[tuple[str, str, list[tuple[int, bytes]]]] = [
    # (real_type, mime,  [(offset, magic_bytes), ...])
    ("pdf",  "application/pdf",            [(0, b"%PDF-")]),
    ("png",  "image/png",                  [(0, b"\x89PNG\r\n\x1a\n")]),
    ("jpg",  "image/jpeg",                 [(0, b"\xff\xd8\xff")]),
    ("gif",  "image/gif",                  [(0, b"GIF87a"), (0, b"GIF89a")][0:1]),  # either
    ("bmp",  "image/bmp",                  [(0, b"BM")]),
    ("webp", "image/webp",                 [(0, b"RIFF"), (8, b"WEBP")]),
    ("tiff", "image/tiff",                 [(0, b"II*\x00")]),
    ("tiff", "image/tiff",                 [(0, b"MM\x00*")]),
    ("mp3",  "audio/mpeg",                 [(0, b"ID3")]),
    ("mp3",  "audio/mpeg",                 [(0, b"\xff\xfb")]),
    ("flac", "audio/flac",                 [(0, b"fLaC")]),
    ("ogg",  "audio/ogg",                  [(0, b"OggS")]),
    ("wav",  "audio/wav",                  [(0, b"RIFF"), (8, b"WAVE")]),
    ("mp4",  "video/mp4",                  [(4, b"ftyp")]),
    ("avi",  "video/x-msvideo",            [(0, b"RIFF"), (8, b"AVI ")]),
    ("mkv",  "video/x-matroska",           [(0, b"\x1a\x45\xdf\xa3")]),
    ("webm", "video/webm",                 [(0, b"\x1a\x45\xdf\xa3")]),
    # ZIP-based containers (must come AFTER specific zip-based checks below)
    ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                           [(0, b"PK\x03\x04")]),
    ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                           [(0, b"PK\x03\x04")]),
    ("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                                           [(0, b"PK\x03\x04")]),
    ("zip",  "application/zip",            [(0, b"PK\x03\x04")]),
    ("zip",  "application/zip",            [(0, b"PK\x05\x06")]),
    ("tar",  "application/x-tar",          [(257, b"ustar")]),
    ("gz",   "application/gzip",           [(0, b"\x1f\x8b")]),
    ("bz2",  "application/x-bzip2",        [(0, b"BZh")]),
    ("7z",   "application/x-7z-compressed",[(0, b"7z\xbc\xaf'\x1c")]),
    ("rar",  "application/x-rar-compressed",[(0, b"Rar!\x1a\x07")]),
    ("gif",  "image/gif",                  [(0, b"GIF87a")]),
    ("gif",  "image/gif",                  [(0, b"GIF89a")]),
    ("svg",  "image/svg+xml",              [(0, b"<?xml"), (None, b"<svg")]),
    ("svg",  "image/svg+xml",              [(0, b"<svg")]),
    ("epub", "application/epub+zip",       [(0, b"PK\x03\x04")]),
]

# Text-based types recognised by content sniffing
_TEXT_SIGNATURES: list[tuple[str, str, bytes]] = [
    ("html",  "text/html",              b"<!DOCTYPE html"),
    ("html",  "text/html",              b"<!doctype html"),
    ("html",  "text/html",              b"<html"),
    ("xml",   "application/xml",        b"<?xml"),
    ("json",  "application/json",       b"{"),
    ("json",  "application/json",       b"["),
    ("csv",   "text/csv",               b""),          # handled separately
    ("md",    "text/markdown",          b""),          # handled separately
    ("txt",   "text/plain",             b""),          # handled separately
]

# Mapping real_type → canonical extension
_TYPE_TO_EXT: dict[str, str] = {
    "pdf": "pdf", "png": "png", "jpg": "jpg", "jpeg": "jpg", "gif": "gif",
    "bmp": "bmp", "webp": "webp", "tiff": "tif", "svg": "svg",
    "mp3": "mp3", "flac": "flac", "ogg": "ogg", "wav": "wav",
    "mp4": "mp4", "avi": "avi", "mkv": "mkv", "webm": "webm", "mov": "mov",
    "docx": "docx", "xlsx": "xlsx", "pptx": "pptx",
    "zip": "zip", "tar": "tar", "gz": "gz", "bz2": "bz2", "7z": "7z", "rar": "rar",
    "epub": "epub",
    "html": "html", "xml": "xml", "json": "json", "csv": "csv", "md": "md", "txt": "txt",
}

_READ_BYTES = 512


def _read_head(path: Path, n: int = _READ_BYTES) -> bytes:
    try:
        with open(path, "rb") as f:
            return f.read(n)
    except OSError:
        return b""


def _check_sig(head: bytes, sig: list[tuple[int, bytes]]) -> bool:
    """Return True if all (offset, bytes) pairs match in *head*."""
    for offset, pattern in sig:
        if offset is None:
            if pattern not in head:
                return False
        else:
            if head[offset: offset + len(pattern)] != pattern:
                return False
    return True


def _refine_zip(path: Path) -> tuple[str, str]:
    """Try to figure out if a PK zip is docx/xlsx/pptx/epub vs plain zip."""
    import zipfile
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
    except Exception:
        return "zip", "application/zip"

    if "word/document.xml" in names:
        return "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if "xl/workbook.xml" in names:
        return "xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if "ppt/presentation.xml" in names:
        return "pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    if "META-INF/container.xml" in names:
        return "epub", "application/epub+zip"
    return "zip", "application/zip"


def _detect_text(path: Path) -> tuple[str, str] | None:
    """Sniff text-based types: json, xml, html, csv, md, txt."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            sample = f.read(2048)
    except OSError:
        return None

    stripped = sample.lstrip()

    # JSON: starts with object/array (common) OR is a primitive (null/true/false/number/string)
    if stripped.startswith("{") or stripped.startswith("["):
        import json as _json
        try:
            _json.loads(sample)
            return "json", "application/json"
        except Exception:
            pass
    elif stripped.lower() in ("null", "true", "false") or stripped.startswith('"'):
        import json as _json
        try:
            _json.loads(stripped.strip())
            return "json", "application/json"
        except Exception:
            pass
    elif stripped and (stripped[0].isdigit() or stripped[0] in "-+"):
        import json as _json
        try:
            _json.loads(stripped.strip())
            return "json", "application/json"
        except Exception:
            pass

    low = stripped.lower()

    # HTML: must have doctype or <html root element
    if low.startswith("<!doctype html") or low.startswith("<html"):
        return "html", "text/html"

    # Markdown: check BEFORE XML because .md files often start with <div> for badges
    # Use extension as a strong hint, plus content patterns
    declared_ext = path.suffix.lower().lstrip(".")
    md_patterns = ["# ", "## ", "### ", "* ", "- ", "> ", "```", "**", "__"]
    md_hits = sum(1 for p in md_patterns if p in sample)

    if declared_ext in ("md", "markdown") and md_hits >= 1:
        return "md", "text/markdown"

    # XML: only claim XML if it starts with the XML declaration OR
    # starts with < AND actually parses as valid XML
    if stripped.startswith("<?xml"):
        return "xml", "application/xml"

    if stripped.startswith("<") and not low.startswith("<!doctype"):
        # Try to parse — if it fails, it might be Markdown with HTML badges
        import xml.etree.ElementTree as _ET
        try:
            _ET.fromstring(stripped[:2048])
            return "xml", "application/xml"
        except Exception:
            pass  # not valid XML — fall through to markdown/txt checks

    # CSV heuristic: at least 2 lines and consistent delimiter count
    lines = sample.splitlines()
    if len(lines) >= 2:
        delimiters = [",", ";", "\t"]
        for delim in delimiters:
            counts = [line.count(delim) for line in lines[:5] if line]
            if counts and min(counts) > 0 and max(counts) - min(counts) <= 2:
                return "csv", "text/csv"

    # Markdown: standalone check (no extension hint needed)
    if md_hits >= 2:
        return "md", "text/markdown"

    return "txt", "text/plain"


def detect(path: Path) -> tuple[str, str]:
    """
    Return (real_type, mime) for *path* based purely on file content.

    Never raises; returns ("unknown", "application/octet-stream") on error.
    """
    if not path.is_file():
        return "unknown", "application/octet-stream"

    head = _read_head(path)
    if not head:
        return "unknown", "application/octet-stream"

    # --- binary signature pass -------------------------------------------
    for real_type, mime, sig in _SIGNATURES:
        if _check_sig(head, sig):
            # Disambiguate ZIP-based formats
            if head[:4] == b"PK\x03\x04":
                return _refine_zip(path)
            # Disambiguate MKV vs WEBM (both start with \x1a\x45\xdf\xa3)
            if real_type in ("mkv", "webm"):
                # webm has "webm" doctype; mkv has "matroska"
                extended = _read_head(path, 64)
                if b"webm" in extended:
                    return "webm", "video/webm"
                return "mkv", "video/x-matroska"
            return real_type, mime

    # --- text pass -------------------------------------------------------
    # Only attempt if the head looks like text (no null bytes in first 512)
    if b"\x00" not in head:
        result = _detect_text(path)
        if result:
            return result

    # --- fallback: filetype library --------------------------------------
    try:
        import filetype as ft  # type: ignore
        kind = ft.guess(str(path))
        if kind:
            return kind.extension, kind.mime
    except Exception:
        pass

    # --- fallback: puremagic ---------------------------------------------
    try:
        import puremagic  # type: ignore
        matches = puremagic.magic_file(str(path))
        if matches:
            m = matches[0]
            ext = m.extension.lstrip(".") if m.extension else "unknown"
            mime = m.mime_type or "application/octet-stream"
            return ext, mime
    except Exception:
        pass

    return "unknown", "application/octet-stream"


def get_extension(path: Path) -> str:
    """Return the on-disk extension (without dot, lower-cased)."""
    suffix = path.suffix
    return suffix.lstrip(".").lower() if suffix else ""


def extension_matches(real_type: str, declared_ext: str) -> bool:
    """Return True if the declared extension is consistent with real_type."""
    declared = declared_ext.lower().lstrip(".")

    # Same-family aliases
    aliases: dict[str, set[str]] = {
        "jpg": {"jpg", "jpeg"},
        "jpeg": {"jpg", "jpeg"},
        "tiff": {"tiff", "tif"},
        "tif": {"tiff", "tif"},
        "gz": {"gz", "gzip"},
        "tar": {"tar"},
        "txt": {"txt", "text"},
        "md": {"md", "markdown"},
        "xml": {"xml"},
        "html": {"html", "htm"},
    }

    expected = _TYPE_TO_EXT.get(real_type, real_type)
    allowed = aliases.get(expected, {expected}) | aliases.get(real_type, {real_type})
    allowed.add(expected)
    allowed.add(real_type)

    return declared in allowed
