"""
FileDNA – AI-powered features.

These are the functions developers write manually over and over in
every document pipeline. None require an API key — pure Python.

Functions:
    chunk_text(text, strategy, size, overlap)  → list[Chunk]
    detect_pii(text)                           → PIIResult
    diff_files(path_a, path_b)                 → FileDiff
    content_hash(path)                         → ContentHash
    find_duplicates(paths)                     → list[DuplicateGroup]
    redact_pii(text)                           → str
    extract_structured(text, schema)           → dict   ← uses LLM if configured
    classify_content(text)                     → str   ← uses LLM if configured

Each function is completely standalone — import only what you need.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


# ===========================================================================
# 1. SMART CHUNKING
# Developers write this from scratch for every RAG pipeline.
# ===========================================================================

@dataclass
class Chunk:
    """A single text chunk with positional metadata."""
    text: str
    index: int              # chunk number (0-based)
    char_start: int         # position in original text
    char_end: int
    word_count: int = 0
    token_estimate: int = 0

    def __post_init__(self) -> None:
        self.word_count = len(self.text.split())
        self.token_estimate = max(1, int(self.word_count / 0.75))

    def __len__(self) -> int:
        return len(self.text)


def chunk_text(
    text: str,
    strategy: Literal["fixed", "sentence", "paragraph", "semantic"] = "paragraph",
    size: int = 512,
    overlap: int = 50,
) -> list[Chunk]:
    """
    Split text into chunks for embedding / RAG pipelines.

    Strategies:
        fixed      — split by character count with overlap
        sentence   — split at sentence boundaries, respect size limit
        paragraph  — split at paragraph breaks, merge short paragraphs
        semantic   — split at paragraph breaks, then split oversized paragraphs
                     at sentence boundaries (best for most RAG use cases)

    Args:
        text:     The text to chunk.
        strategy: Chunking strategy.
        size:     Target chunk size in characters.
        overlap:  Overlap between consecutive chunks (fixed strategy only).

    Returns:
        List of Chunk objects with positional metadata.
    """
    if not text.strip():
        return []

    if strategy == "fixed":
        return _chunk_fixed(text, size, overlap)
    if strategy == "sentence":
        return _chunk_sentence(text, size)
    if strategy == "paragraph":
        return _chunk_paragraph(text, size)
    # Default: semantic
    return _chunk_semantic(text, size)


def _chunk_fixed(text: str, size: int, overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    step = max(1, size - overlap)
    i = 0
    idx = 0
    while i < len(text):
        end = min(i + size, len(text))
        chunks.append(Chunk(text=text[i:end], index=idx, char_start=i, char_end=end))
        idx += 1
        i += step
    return chunks


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences. Handles abbreviations reasonably well."""
    # Sentence boundaries: ., !, ? followed by whitespace and capital letter
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"])", text)
    return [p.strip() for p in parts if p.strip()]


def _chunk_sentence(text: str, size: int) -> list[Chunk]:
    sentences = _split_sentences(text)
    chunks: list[Chunk] = []
    current = ""
    current_start = 0
    idx = 0
    pos = 0

    for sent in sentences:
        if current and len(current) + len(sent) + 1 > size:
            chunks.append(Chunk(
                text=current.strip(),
                index=idx,
                char_start=current_start,
                char_end=current_start + len(current),
            ))
            idx += 1
            current_start = pos
            current = sent
        else:
            current = (current + " " + sent).strip() if current else sent
        pos += len(sent) + 1

    if current.strip():
        chunks.append(Chunk(
            text=current.strip(),
            index=idx,
            char_start=current_start,
            char_end=current_start + len(current),
        ))

    return chunks


def _chunk_paragraph(text: str, size: int) -> list[Chunk]:
    paras = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: list[Chunk] = []
    current = ""
    current_start = 0
    idx = 0
    pos = 0

    for para in paras:
        if current and len(current) + len(para) + 2 > size:
            chunks.append(Chunk(
                text=current.strip(),
                index=idx,
                char_start=current_start,
                char_end=current_start + len(current),
            ))
            idx += 1
            current_start = pos
            current = para
        else:
            current = (current + "\n\n" + para).strip() if current else para
        pos += len(para) + 2

    if current.strip():
        chunks.append(Chunk(
            text=current.strip(),
            index=idx,
            char_start=current_start,
            char_end=current_start + len(current),
        ))

    return chunks


def _chunk_semantic(text: str, size: int) -> list[Chunk]:
    """Paragraph-first, then sentence-split oversized paragraphs."""
    para_chunks = _chunk_paragraph(text, size)
    result: list[Chunk] = []
    idx = 0

    for chunk in para_chunks:
        if len(chunk.text) > size * 1.5:
            # Split oversized paragraph at sentence boundaries
            sub = _chunk_sentence(chunk.text, size)
            for s in sub:
                result.append(Chunk(
                    text=s.text,
                    index=idx,
                    char_start=chunk.char_start + s.char_start,
                    char_end=chunk.char_start + s.char_end,
                ))
                idx += 1
        else:
            result.append(Chunk(text=chunk.text, index=idx,
                                char_start=chunk.char_start, char_end=chunk.char_end))
            idx += 1

    return result


# ===========================================================================
# 2. PII DETECTION & REDACTION
# Every document pipeline that handles user data needs this.
# Regex-based — no LLM, no API key, works offline.
# ===========================================================================

@dataclass
class PIIMatch:
    pii_type: str       # "email", "phone", "credit_card", etc.
    value: str          # the actual matched text
    start: int          # position in original text
    end: int
    confidence: str     # "high" | "medium" | "low"


@dataclass
class PIIResult:
    has_pii: bool = False
    matches: list[PIIMatch] = field(default_factory=list)
    types_found: list[str] = field(default_factory=list)
    redacted_text: str = ""    # text with PII replaced by [REDACTED_TYPE]

    @property
    def count(self) -> int:
        return len(self.matches)


# PII patterns — ordered from most to least specific
_PII_PATTERNS: list[tuple[str, str, str]] = [
    # (pii_type, pattern, confidence)
    ("credit_card",     r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b", "high"),
    ("ssn",             r"\b\d{3}-\d{2}-\d{4}\b",                                                                          "high"),
    ("email",           r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b",                                         "high"),
    ("phone_us",        r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b",                                        "high"),
    ("phone_intl",      r"\b\+\d{1,3}[-.\s]\d{1,4}[-.\s]\d{4,10}\b",                                                     "medium"),
    ("ip_address",      r"\b(?:\d{1,3}\.){3}\d{1,3}\b",                                                                   "medium"),
    ("iban",            r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}(?:[A-Z0-9]?){0,16}\b",                                        "high"),
    ("passport",        r"\b[A-Z]{1,2}[0-9]{6,9}\b",                                                                      "low"),
    ("date_of_birth",   r"\b(?:born|dob|date of birth)[\s:]*\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b",                         "medium"),
    ("url_with_token",  r"https?://[^\s]+(?:token|key|secret|auth)=[^\s&]+",                                               "high"),
    ("api_key",         r"\b(?:sk|pk|api|key|secret)[-_][a-zA-Z0-9]{16,}\b",                                              "high"),
    ("aws_key",         r"\bAKIA[0-9A-Z]{16}\b",                                                                           "high"),
]

_COMPILED_PII = [
    (ptype, re.compile(pattern, re.IGNORECASE), confidence)
    for ptype, pattern, confidence in _PII_PATTERNS
]


def detect_pii(text: str) -> PIIResult:
    """
    Scan text for Personally Identifiable Information using regex patterns.

    Detects: email, phone (US/intl), credit card, SSN, IBAN, IP address,
    passport, API keys, AWS keys, bearer tokens, dates of birth.

    No LLM. No API key. Works offline. Fast.

    Returns:
        PIIResult with all matches and a pre-redacted version of the text.
    """
    if not text:
        return PIIResult(redacted_text=text)

    matches: list[PIIMatch] = []
    seen_spans: set[tuple[int, int]] = set()

    for ptype, pattern, confidence in _COMPILED_PII:
        for m in pattern.finditer(text):
            span = (m.start(), m.end())
            # Skip overlapping matches (more specific patterns take priority)
            if any(s <= span[0] < e or s < span[1] <= e for s, e in seen_spans):
                continue
            seen_spans.add(span)
            matches.append(PIIMatch(
                pii_type=ptype,
                value=m.group(),
                start=m.start(),
                end=m.end(),
                confidence=confidence,
            ))

    # Sort by position
    matches.sort(key=lambda x: x.start)

    types_found = list(dict.fromkeys(m.pii_type for m in matches))

    # Build redacted text in one pass
    redacted = text
    offset = 0
    for match in matches:
        tag = f"[REDACTED_{match.pii_type.upper()}]"
        start = match.start + offset
        end = match.end + offset
        redacted = redacted[:start] + tag + redacted[end:]
        offset += len(tag) - (match.end - match.start)

    return PIIResult(
        has_pii=bool(matches),
        matches=matches,
        types_found=types_found,
        redacted_text=redacted,
    )


def redact_pii(text: str) -> str:
    """Convenience wrapper — returns redacted text directly."""
    return detect_pii(text).redacted_text


# ===========================================================================
# 3. CONTENT HASHING
# Developers always need this for deduplication and change detection.
# ===========================================================================

@dataclass
class ContentHash:
    sha256: str
    md5: str
    size_bytes: int
    path: str = ""

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ContentHash):
            return self.sha256 == other.sha256
        return NotImplemented

    def __str__(self) -> str:
        return self.sha256[:16] + "..."  # short form for display


def content_hash(path: Path) -> ContentHash:
    """
    Compute SHA-256 + MD5 of file content.

    Reads in chunks — handles large files without loading into memory.
    """
    sha256 = hashlib.sha256()
    md5 = hashlib.md5()
    size = 0

    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
                md5.update(chunk)
                size += len(chunk)
    except OSError as exc:
        raise ValueError(f"Cannot hash file: {exc}") from exc

    return ContentHash(
        sha256=sha256.hexdigest(),
        md5=md5.hexdigest(),
        size_bytes=size,
        path=str(path),
    )


# ===========================================================================
# 4. DUPLICATE DETECTION
# "Find all duplicate files in this folder" — written manually every time.
# ===========================================================================

@dataclass
class DuplicateGroup:
    """A set of files with identical content."""
    sha256: str
    size_bytes: int
    paths: list[Path]

    @property
    def count(self) -> int:
        return len(self.paths)

    @property
    def wasted_bytes(self) -> int:
        return self.size_bytes * (self.count - 1)


def find_duplicates(
    paths: list[Path],
    *,
    min_size: int = 1,
) -> list[DuplicateGroup]:
    """
    Find files with identical content using SHA-256 hashing.

    Args:
        paths:    List of file paths to check.
        min_size: Ignore files smaller than this (bytes). Default: 1 (skip empty).

    Returns:
        List of DuplicateGroup — each group has 2+ paths with identical content.
        Empty list if no duplicates found.

    Example:
        groups = find_duplicates(list(Path("uploads").rglob("*")))
        for g in groups:
            print(f"Duplicate ({g.count}x, {g.size_bytes} bytes):")
            for p in g.paths:
                print(f"  {p}")
    """
    from collections import defaultdict

    hash_map: dict[str, list[Path]] = defaultdict(list)
    size_map: dict[str, int] = {}

    for path in paths:
        if not path.is_file():
            continue
        size = path.stat().st_size
        if size < min_size:
            continue
        try:
            h = content_hash(path)
            hash_map[h.sha256].append(path)
            size_map[h.sha256] = h.size_bytes
        except Exception:
            continue

    return [
        DuplicateGroup(sha256=sha256, size_bytes=size_map[sha256], paths=file_paths)
        for sha256, file_paths in hash_map.items()
        if len(file_paths) >= 2
    ]


# ===========================================================================
# 5. FILE DIFF
# "What changed between these two versions of a document?" — written
# manually every time someone processes revisions.
# ===========================================================================

@dataclass
class FileDiff:
    """Structural diff between two text files."""
    path_a: str
    path_b: str
    lines_added: int = 0
    lines_removed: int = 0
    lines_unchanged: int = 0
    chars_added: int = 0
    chars_removed: int = 0
    identical: bool = False
    diff_ratio: float = 0.0    # 0.0 = completely different, 1.0 = identical
    summary: str = ""
    unified_diff: str = ""     # standard unified diff format


def diff_files(path_a: Path, path_b: Path) -> FileDiff:
    """
    Compute a human-readable diff between two text files.

    Works on: .txt, .md, .json, .xml, .html, .csv, .py, any plain text.
    For binary files (PDF, DOCX etc.) — extracts text first, then diffs.

    Returns:
        FileDiff with line counts, char counts, similarity ratio,
        and a full unified diff string.
    """
    import difflib

    def _read(path: Path) -> list[str]:
        try:
            return path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        except Exception:
            return []

    lines_a = _read(path_a)
    lines_b = _read(path_b)

    if lines_a == lines_b:
        return FileDiff(
            path_a=str(path_a),
            path_b=str(path_b),
            lines_unchanged=len(lines_a),
            identical=True,
            diff_ratio=1.0,
            summary="Files are identical",
        )

    # Compute similarity ratio
    seq = difflib.SequenceMatcher(None, lines_a, lines_b)
    ratio = round(seq.ratio(), 3)

    # Count changes
    added = removed = unchanged = chars_added = chars_removed = 0
    for tag, i1, i2, j1, j2 in seq.get_opcodes():
        if tag == "equal":
            unchanged += i2 - i1
        elif tag == "insert":
            added += j2 - j1
            chars_added += sum(len(l) for l in lines_b[j1:j2])
        elif tag == "delete":
            removed += i2 - i1
            chars_removed += sum(len(l) for l in lines_a[i1:i2])
        elif tag == "replace":
            removed += i2 - i1
            added += j2 - j1
            chars_removed += sum(len(l) for l in lines_a[i1:i2])
            chars_added += sum(len(l) for l in lines_b[j1:j2])

    # Unified diff
    unified = "".join(difflib.unified_diff(
        lines_a,
        lines_b,
        fromfile=str(path_a),
        tofile=str(path_b),
        lineterm="",
    ))

    summary_parts = []
    if added:
        summary_parts.append(f"+{added} lines added")
    if removed:
        summary_parts.append(f"-{removed} lines removed")
    if unchanged:
        summary_parts.append(f"{unchanged} unchanged")
    summary_parts.append(f"{int(ratio * 100)}% similar")
    summary = ", ".join(summary_parts)

    return FileDiff(
        path_a=str(path_a),
        path_b=str(path_b),
        lines_added=added,
        lines_removed=removed,
        lines_unchanged=unchanged,
        chars_added=chars_added,
        chars_removed=chars_removed,
        identical=False,
        diff_ratio=ratio,
        summary=summary,
        unified_diff=unified,
    )


# ===========================================================================
# 6. BATCH ANALYSIS
# Process many files concurrently — the threading boilerplate every
# developer writes when building an upload processor or indexer.
# ===========================================================================

@dataclass
class BatchResult:
    """Results from analyzing a batch of files.

    Note: `succeeded` counts files where analysis completed without
    a crash (even if result.valid=False). Use result.valid per file
    to check actual file validity. `failed` counts files that caused
    an unhandled exception during analysis.
    """
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    results: dict[str, Any] = field(default_factory=dict)   # path → AnalysisResult
    errors: dict[str, str] = field(default_factory=dict)    # path → error message
    duration_seconds: float = 0.0

    @property
    def success_rate(self) -> float:
        return self.succeeded / self.total if self.total else 0.0


def analyze_many(
    paths: list[Path | str],
    *,
    max_workers: int = 8,
    skip_metadata: bool = False,
    on_progress: Any = None,    # optional callback(completed, total, path)
) -> BatchResult:
    """
    Analyze multiple files concurrently using a thread pool.

    Args:
        paths:         List of file paths to analyze.
        max_workers:   Thread pool size. Default 8 is good for I/O-bound work.
        skip_metadata: Skip metadata extraction (faster, less info).
        on_progress:   Optional callback(completed: int, total: int, path: str).

    Returns:
        BatchResult with per-file results and aggregate statistics.

    Example:
        result = analyze_many(list(Path("uploads").glob("*")))
        print(f"Processed {result.total} files")
        print(f"High-risk files:")
        for path, r in result.results.items():
            if r.risk_score > 50:
                print(f"  {path}: score={r.risk_score}")
    """
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from ..core.engine import analyze_file

    paths = [Path(p) for p in paths]
    batch = BatchResult(total=len(paths))
    start = time.perf_counter()

    def _analyze_one(path: Path) -> tuple[str, Any, str | None]:
        try:
            result = analyze_file(path, skip_metadata=skip_metadata)
            return str(path), result, None
        except Exception as exc:
            return str(path), None, str(exc)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_analyze_one, p): p for p in paths}
        completed = 0
        for future in as_completed(futures):
            path_str, result, error = future.result()
            completed += 1
            if error:
                batch.failed += 1
                batch.errors[path_str] = error
            else:
                batch.succeeded += 1
                batch.results[path_str] = result
            if on_progress:
                on_progress(completed, len(paths), path_str)

    batch.duration_seconds = round(time.perf_counter() - start, 3)
    return batch
