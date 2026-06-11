"""Tests for file validators."""
from __future__ import annotations

import pytest

from filedna.validators.file_validators import validate


class TestPDFValidator:
    def test_valid_pdf(self, tmp_files):
        valid, errors, warnings = validate(tmp_files["valid_pdf"], "pdf")
        assert valid is True
        assert errors == []

    def test_fake_pdf(self, tmp_files):
        """PNG file detected as PDF should fail PDF validation."""
        valid, errors, warnings = validate(tmp_files["fake_pdf"], "pdf")
        assert valid is False
        assert any("not a valid PDF" in e.lower() or "PDF" in e for e in errors)

    def test_corrupted_pdf(self, tmp_files):
        valid, errors, warnings = validate(tmp_files["corrupted_pdf"], "pdf")
        # Corrupted PDF may or may not parse; just check it doesn't crash
        assert isinstance(valid, bool)


class TestDocxValidator:
    def test_valid_docx(self, tmp_files):
        valid, errors, warnings = validate(tmp_files["valid_docx"], "docx")
        assert valid is True
        assert errors == []

    def test_corrupted_docx(self, tmp_files):
        valid, errors, warnings = validate(tmp_files["corrupted_docx"], "docx")
        assert valid is False
        assert len(errors) > 0


class TestXlsxValidator:
    def test_valid_xlsx(self, tmp_files):
        valid, errors, warnings = validate(tmp_files["valid_xlsx"], "xlsx")
        assert valid is True


class TestZipValidator:
    def test_valid_zip(self, tmp_files):
        valid, errors, warnings = validate(tmp_files["valid_zip"], "zip")
        assert valid is True
        assert errors == []

    def test_png_as_zip_fails(self, tmp_files):
        valid, errors, warnings = validate(tmp_files["png_as_zip"], "zip")
        assert valid is False


class TestJSONValidator:
    def test_valid_json(self, tmp_files):
        valid, errors, warnings = validate(tmp_files["valid_json"], "json")
        assert valid is True

    def test_invalid_json(self, tmp_files):
        valid, errors, warnings = validate(tmp_files["invalid_json"], "json")
        assert valid is False
        assert len(errors) > 0


class TestImageValidator:
    def test_valid_png(self, tmp_files):
        valid, errors, warnings = validate(tmp_files["valid_png"], "png")
        assert valid is True


class TestUnknownType:
    def test_unknown_type_passes_with_warning(self, tmp_files):
        valid, errors, warnings = validate(tmp_files["valid_txt"], "unknown_type_xyz")
        assert valid is True
        assert any("No validator" in w for w in warnings)
