"""Tests for the risk scoring engine."""
from __future__ import annotations

from pathlib import Path

import pytest

from filedna.core.risk import compute_risk


class TestComputeRisk:
    def _base_kwargs(self, path: Path, **overrides):
        kwargs = dict(
            valid=True,
            extension_matches=True,
            errors=[],
            warnings=[],
            metadata={},
            real_type="pdf",
            path=path,
        )
        kwargs.update(overrides)
        return kwargs

    def test_clean_file_zero_risk(self, tmp_files):
        score, warnings = compute_risk(**self._base_kwargs(tmp_files["valid_pdf"]))
        assert score == 0
        assert warnings == []

    def test_extension_mismatch_adds_40(self, tmp_files):
        score, warnings = compute_risk(
            **self._base_kwargs(tmp_files["fake_pdf"], extension_matches=False)
        )
        assert score >= 40
        assert any("mismatch" in w.lower() for w in warnings)

    def test_invalid_adds_to_score(self, tmp_files):
        score, warnings = compute_risk(
            **self._base_kwargs(tmp_files["valid_pdf"], valid=False)
        )
        assert score >= 50

    def test_errors_add_to_score(self, tmp_files):
        score, warnings = compute_risk(
            **self._base_kwargs(tmp_files["valid_pdf"], errors=["Something failed"])
        )
        assert score >= 30

    def test_score_capped_at_100(self, tmp_files):
        score, warnings = compute_risk(
            **self._base_kwargs(
                tmp_files["fake_pdf"],
                valid=False,
                extension_matches=False,
                errors=["Error 1", "Error 2"],
            )
        )
        assert score <= 100

    def test_empty_file_high_risk(self, tmp_files):
        score, warnings = compute_risk(
            **self._base_kwargs(tmp_files["empty_file"])
        )
        assert score >= 30

    def test_metadata_error_adds_risk(self, tmp_files):
        score, warnings = compute_risk(
            **self._base_kwargs(
                tmp_files["valid_pdf"],
                metadata={"inspection_error": "something went wrong"},
            )
        )
        assert score >= 20
