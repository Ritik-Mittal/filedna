"""
FileDNA – risk scoring engine.

Computes a 0-100 risk score based on validation results and metadata.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def compute_risk(
    *,
    valid: bool,
    extension_matches: bool,
    errors: list[str],
    warnings: list[str],
    metadata: dict[str, Any],
    real_type: str,
    path: Path,
) -> tuple[int, list[str]]:
    """
    Return (risk_score, extra_warnings).
    Score is capped at 100.
    """
    score = 0
    extra_warnings: list[str] = []

    # Extension mismatch
    if not extension_matches:
        score += 40
        extra_warnings.append("Extension mismatch")

    # Corrupted / unreadable
    if not valid:
        score += 50
    elif errors:
        score += 30

    # Metadata could not be read
    if "inspection_error" in metadata:
        score += 20
        extra_warnings.append("Metadata could not be fully extracted")

    # Empty file
    if path.stat().st_size == 0:
        score += 30
        extra_warnings.append("File is empty")

    # Embedded executable heuristic for ZIP-based formats
    if real_type in ("zip", "docx", "xlsx", "pptx", "epub"):
        try:
            import zipfile
            with zipfile.ZipFile(path) as z:
                for name in z.namelist():
                    low = name.lower()
                    if any(low.endswith(ext) for ext in (
                        ".exe", ".dll", ".bat", ".cmd", ".ps1", ".vbs",
                        ".msi", ".scr", ".com", ".pif",
                    )):
                        score += 80
                        extra_warnings.append(
                            f"Embedded executable detected: {name}"
                        )
                        break
        except Exception:
            pass

    return min(score, 100), extra_warnings
