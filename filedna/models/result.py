"""
FileDNA – AnalysisResult model.

All public API calls return an instance of this class.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class AnalysisResult(BaseModel):
    """Unified result object returned by every FileDNA API call."""

    # --- identity --------------------------------------------------------
    valid: bool = False
    real_type: str = "unknown"
    mime: str = "application/octet-stream"
    extension: str = ""
    extension_matches: bool = False

    # --- size -------------------------------------------------------------
    size_bytes: int = 0
    size_human: str = "0 B"

    # --- risk & warnings -------------------------------------------------
    risk_score: int = Field(default=0, ge=0, le=100)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    # --- metadata --------------------------------------------------------
    metadata: dict[str, Any] = Field(default_factory=dict)

    # --- source (internal, not serialised by default) --------------------
    _source: str = ""

    # ------------------------------------------------------------------ #
    # Convenience properties                                               #
    # ------------------------------------------------------------------ #

    @property
    def summary(self) -> str:
        """Return a human-friendly multi-line summary."""
        lines: list[str] = []

        status = "✓ Valid" if self.valid else "✗ Invalid"
        type_label = self.real_type.upper() if self.real_type != "unknown" else "Unknown type"
        lines.append(f"{status} {type_label}")

        meta = self.metadata

        # document-specific
        if "pages" in meta:
            lines.append(f"Pages: {meta['pages']}")
        if "slides" in meta:
            lines.append(f"Slides: {meta['slides']}")
        if "paragraphs" in meta:
            lines.append(f"Paragraphs: {meta['paragraphs']}")
        if "sheets" in meta:
            lines.append(f"Sheets: {meta['sheets']}")

        # image-specific
        if "width" in meta and "height" in meta:
            lines.append(f"Dimensions: {meta['width']}×{meta['height']}")

        # audio / video
        if "duration" in meta:
            lines.append(f"Duration: {meta['duration']:.1f}s")

        # language
        if "language" in meta:
            lines.append(f"Language: {meta['language']}")

        if "contains_tables" in meta and meta["contains_tables"]:
            lines.append("Contains tables")
        if "contains_images" in meta and meta["contains_images"]:
            lines.append("Contains images")

        lines.append(f"Size: {self.size_human}")

        if "estimated_tokens" in meta:
            tok = meta["estimated_tokens"]
            tok_str = f"{tok / 1000:.1f}k" if tok >= 1000 else str(tok)
            lines.append(f"Tokens: {tok_str}")

        lines.append(f"Risk Score: {self.risk_score}")

        if self.warnings:
            for w in self.warnings:
                lines.append(f"⚠  {w}")
        if self.errors:
            for e in self.errors:
                lines.append(f"✗  {e}")

        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Validators                                                           #
    # ------------------------------------------------------------------ #

    @model_validator(mode="after")
    def _cap_risk(self) -> AnalysisResult:
        if self.risk_score > 100:
            self.risk_score = 100
        return self
