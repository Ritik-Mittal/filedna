"""
FileDNA – Discover a file's true identity.

FileDNA's core job: tell you what a file REALLY is, whether it's trustworthy,
and surface every signal about it — without trusting extensions.

What makes FileDNA different from content-core / LangChain / etc:
  - content-core extracts TEXT from files (that's its whole job)
  - LangChain chunks that text for RAG pipelines
  - FileDNA answers: what IS this file? is it valid? is it what it claims?
    is it a duplicate? does it contain PII? what are its hashes?

These are the things nobody else does as a unified file-identity layer.

Core API (no API key, no network):
    analyze(path)              → AnalysisResult   — full identity report
    validate(path)             → AnalysisResult   — is it structurally valid?
    detect_type(path)          → str              — real type from magic bytes
    inspect_file(path)         → dict             — metadata (pages, dims, etc)
    inspect_url(url)           → dict             — HEAD request metadata
    estimate_tokens(path)      → int              — token count estimate

File identity utilities (no API key, no network):
    extract_exif(path)         → ExifData         — GPS, camera, timestamps
    detect_pii(text)           → PIIResult        — email, phone, card, SSN...
    redact_pii(text)           → str              — replace PII with [REDACTED]
    content_hash(path)         → ContentHash      — SHA-256 + MD5
    find_duplicates(paths)     → list[DuplicateGroup]
    diff_files(path_a, path_b) → FileDiff
    analyze_many(paths)        → BatchResult      — concurrent batch analysis

AI features (optional, requires API key via AIConfig):
    from filedna.features.ai_features import (
        AIConfig,
        classify_content,      — "is this a legal contract or invoice?"
        extract_structured,    — pull typed fields from unstructured text
        clean_document,        — remove headers/footers/page numbers
        semantic_similarity,   — are these two documents saying the same thing?
    )
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .models.result import AnalysisResult

__version__ = "1.2.6"

__all__ = [
    # Core
    "analyze", "validate", "detect_type", "inspect_file",
    "inspect_url", "estimate_tokens",
    # File identity
    "extract_exif",
    "detect_pii", "redact_pii",
    "content_hash", "find_duplicates",
    "diff_files", "analyze_many",
    # Model
    "AnalysisResult",
]


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------

def analyze(path: str | Path, *, skip_metadata: bool = False) -> AnalysisResult:
    """
    Full file identity report.

    Detects real type from magic bytes (never trusts the extension),
    validates structural integrity, extracts metadata, scores risk.

    Returns AnalysisResult with: valid, real_type, mime, extension,
    extension_matches, size_human, risk_score, warnings, errors, metadata.
    """
    from .core.engine import analyze_file
    return analyze_file(path, skip_metadata=skip_metadata)


def validate(path: str | Path) -> AnalysisResult:
    """
    Structural integrity check — faster than analyze(), skips metadata.

    Use this for upload validation: check result.valid and result.errors.
    """
    return analyze(path, skip_metadata=True)


def detect_type(path: str | Path) -> str:
    """
    Real file type from magic bytes — never trusts the extension.

    detect_type("photo.pdf")  →  "png"   (extension lied)
    detect_type("data.zip")   →  "docx"  (actually a Word document)
    """
    from .detectors.type_detector import detect
    real_type, _ = detect(Path(path))
    return real_type


def inspect_file(path: str | Path) -> dict[str, Any]:
    """
    Type-specific metadata for a file.

    PDF  → pages, language, contains_tables, estimated_tokens
    DOCX → paragraphs, words, estimated_pages
    XLSX → sheets, rows, columns
    PNG  → width, height, mode, dpi, has_transparency
    MP3  → duration, bitrate, sample_rate, channels
    """
    from .detectors.type_detector import detect
    from .inspectors.metadata import inspect
    p = Path(path)
    real_type, _ = detect(p)
    return inspect(p, real_type)


def inspect_url(url: str, *, timeout: int = 10) -> dict[str, Any]:
    """
    HTTP HEAD request — detect content type and file size without downloading.

    Returns: valid, mime, real_type, size_bytes, size_human, status_code.
    Does NOT fetch the page body. Use content-core for full URL extraction.
    """
    from .core.url_inspector import inspect_url as _inspect_url
    return _inspect_url(url, timeout=timeout)


def estimate_tokens(path: str | Path) -> int:
    """
    Estimate LLM token count for a file's text content.

    Uses tiktoken (cl100k_base) if available, else word-count heuristic.
    Returns 0 for binary types (images, audio, video).
    """
    from .utils.tokens import estimate_tokens as _et
    return _et(path)


# ---------------------------------------------------------------------------
# File identity utilities
# ---------------------------------------------------------------------------

def extract_exif(path: str | Path) -> "ExifData":
    """
    Extract EXIF metadata from an image file.

    Returns typed ExifData — no raw IFD tag parsing needed.

    What this eliminates: manually converting GPS DMS→decimal, parsing
    Rational values, handling missing tags. All done for you.

    result.camera_make     → "Apple"
    result.camera_model    → "iPhone 15 Pro"
    result.focal_length    → 6.86   (mm)
    result.aperture        → 1.78   (f-number)
    result.iso             → 50
    result.datetime_taken  → "2024:03:15 14:22:31"
    result.gps.latitude    → 51.507351   (decimal degrees, ready to use)
    result.gps.longitude   → -0.127758
    result.gps.google_maps_url  → "https://www.google.com/maps?q=51.5,−0.12"
    """
    from .extractors.exif_extractor import extract_exif as _ee
    return _ee(Path(path))


def detect_pii(text: str) -> "PIIResult":
    """
    Scan text for Personally Identifiable Information.

    Detects: email, phone (US + intl), credit card, SSN, IBAN,
    IP address, API keys, AWS keys, bearer tokens.

    Works offline. No LLM. No API key. Regex-based, fast.

    result.has_pii         → True
    result.types_found     → ["email", "credit_card", "aws_key"]
    result.count           → 3
    result.matches[0]      → PIIMatch(type="email", value="...", start=12)
    result.redacted_text   → "...send to [REDACTED_EMAIL]..."
    """
    from .features.pipeline import detect_pii as _dp
    return _dp(text)


def redact_pii(text: str) -> str:
    """Replace all detected PII with [REDACTED_TYPE] tags."""
    from .features.pipeline import redact_pii as _rp
    return _rp(text)


def content_hash(path: str | Path) -> "ContentHash":
    """
    Compute SHA-256 + MD5 of file content.

    Reads in 64KB chunks — works on files of any size without loading
    into memory. Use SHA-256 for deduplication and integrity checks,
    MD5 for legacy system compatibility.

    result.sha256  → "a750aec01847d06d..."
    result.md5     → "d7591a0ac484c964..."
    result == other_hash  → True if same file content
    str(result)    → "a750aec01847d06d..."  (short display form)
    """
    from .features.pipeline import content_hash as _ch
    return _ch(Path(path))


def find_duplicates(paths: list, *, min_size: int = 1) -> list:
    """
    Find files with identical content in a list of paths.

    Uses SHA-256 — catches exact binary duplicates regardless of filename.
    Returns only groups with 2+ files. Empty list = no duplicates.

    group.count        → 3          (how many copies)
    group.wasted_bytes → 40         (space wasted by copies)
    group.paths        → [Path(...), Path(...), Path(...)]

    Example:
        groups = find_duplicates(list(Path("uploads").rglob("*")))
        for g in groups:
            # keep first, delete the rest
            for duplicate in g.paths[1:]:
                duplicate.unlink()
    """
    from .features.pipeline import find_duplicates as _fd
    return _fd([Path(p) for p in paths], min_size=min_size)


def diff_files(path_a: str | Path, path_b: str | Path) -> "FileDiff":
    """
    Structural diff between two text files.

    Good for: comparing document versions, detecting what changed
    in a contract, checking if a config file was modified.

    diff.lines_added    → 6
    diff.lines_removed  → 3
    diff.diff_ratio     → 0.72   (0.0=completely different, 1.0=identical)
    diff.identical      → False
    diff.summary        → "+6 lines added, -3 lines removed, 72% similar"
    diff.unified_diff   → standard unified diff string (--- a/  +++ b/ format)
    """
    from .features.pipeline import diff_files as _df
    return _df(Path(path_a), Path(path_b))


def analyze_many(
    paths: list,
    *,
    max_workers: int = 8,
    skip_metadata: bool = False,
    on_progress: Any = None,
) -> "BatchResult":
    """
    Analyze a list of files concurrently using a thread pool.

    Returns BatchResult — aggregate stats + per-file AnalysisResult dict.

    batch.total              → 50
    batch.succeeded          → 47
    batch.failed             → 3
    batch.duration_seconds   → 1.24
    batch.success_rate       → 0.94
    batch.results["path"]    → AnalysisResult
    batch.errors["path"]     → "error message"

    on_progress callback: fn(completed: int, total: int, path: str)

    Example — find all high-risk files in an uploads folder:
        batch = analyze_many(list(Path("uploads").rglob("*")))
        risky = [p for p, r in batch.results.items() if r.risk_score > 50]
    """
    from .features.pipeline import analyze_many as _am
    return _am(paths, max_workers=max_workers,
               skip_metadata=skip_metadata, on_progress=on_progress)


# ---------------------------------------------------------------------------
# TYPE_CHECKING imports for IDE support (avoids circular imports at runtime)
# ---------------------------------------------------------------------------
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .extractors.exif_extractor import ExifData
    from .features.pipeline import (
        PIIResult, ContentHash, DuplicateGroup, FileDiff, BatchResult
    )
