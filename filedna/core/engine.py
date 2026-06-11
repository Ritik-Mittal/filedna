"""
FileDNA – core analysis engine.

Orchestrates detection → validation → inspection → risk scoring.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..core.risk import compute_risk
from ..detectors.type_detector import detect, extension_matches, get_extension
from ..inspectors.metadata import human_size, inspect
from ..models.result import AnalysisResult
from ..validators.file_validators import validate


def _make_result(**kwargs: Any) -> AnalysisResult:
    return AnalysisResult(**kwargs)


def analyze_file(path: str | Path, *, skip_metadata: bool = False) -> AnalysisResult:
    """
    Full analysis pipeline for a local file.

    Steps:
      1. Existence & readability check
      2. Type detection (magic bytes)
      3. Extension mismatch check
      4. Structural validation
      5. Metadata extraction
      6. Risk scoring
    """
    p = Path(path)
    errors: list[str] = []
    warnings: list[str] = []

    # ------------------------------------------------------------------ #
    # 1. File existence / readability                                       #
    # ------------------------------------------------------------------ #
    if not p.exists():
        return _make_result(
            valid=False,
            errors=[f"File not found: {path}"],
            warnings=[],
        )
    if not p.is_file():
        return _make_result(
            valid=False,
            errors=[f"Path is not a file: {path}"],
            warnings=[],
        )
    if not os.access(p, os.R_OK):
        return _make_result(
            valid=False,
            errors=[f"File is not readable: {path}"],
            warnings=[],
        )

    size_bytes = p.stat().st_size
    size_human_str = human_size(size_bytes)

    if size_bytes == 0:
        return _make_result(
            valid=False,
            size_bytes=0,
            size_human="0 B",
            errors=["File is empty"],
            warnings=[],
            risk_score=30,
        )

    declared_ext = get_extension(p)

    # ------------------------------------------------------------------ #
    # 2. Type detection                                                    #
    # ------------------------------------------------------------------ #
    real_type, mime = detect(p)

    # ------------------------------------------------------------------ #
    # 3. Extension mismatch                                                #
    # ------------------------------------------------------------------ #
    ext_ok = extension_matches(real_type, declared_ext)
    if not ext_ok and declared_ext:
        errors.append(f"File is not a valid {declared_ext.upper()} (real type: {real_type})")

    # ------------------------------------------------------------------ #
    # 4. Structural validation                                             #
    # ------------------------------------------------------------------ #
    valid, val_errors, val_warnings = validate(p, real_type)
    errors.extend(val_errors)
    warnings.extend(val_warnings)

    # ------------------------------------------------------------------ #
    # 5. Metadata extraction                                               #
    # ------------------------------------------------------------------ #
    metadata: dict[str, Any] = {}
    if not skip_metadata:
        metadata = inspect(p, real_type)

    # ------------------------------------------------------------------ #
    # 6. Risk scoring                                                      #
    # ------------------------------------------------------------------ #
    risk_score, risk_warnings = compute_risk(
        valid=valid,
        extension_matches=ext_ok,
        errors=errors,
        warnings=warnings,
        metadata=metadata,
        real_type=real_type,
        path=p,
    )
    warnings.extend(risk_warnings)

    # Extension mismatch means the file is NOT what it claims to be
    # (even if the actual content is valid for its real type)
    final_valid = valid and len(errors) == 0 and ext_ok

    return _make_result(
        valid=final_valid,
        real_type=real_type,
        mime=mime,
        extension=declared_ext,
        extension_matches=ext_ok,
        size_bytes=size_bytes,
        size_human=size_human_str,
        risk_score=risk_score,
        warnings=warnings,
        errors=errors,
        metadata=metadata,
    )
