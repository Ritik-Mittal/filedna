"""
FileDNA – token estimation utility.
"""
from __future__ import annotations

from pathlib import Path


def estimate_tokens(path: str | Path) -> int:
    """
    Estimate the number of LLM tokens for the text content of a file.

    For non-text files (images, audio, video, archives) this returns 0.
    Uses tiktoken (cl100k_base) when available, falls back to word-count heuristic.
    """
    from ..inspectors.metadata import inspect

    p = Path(path)
    if not p.is_file():
        return 0

    from ..detectors.type_detector import detect
    real_type, _ = detect(p)

    meta = inspect(p, real_type)
    return meta.get("estimated_tokens", 0)
