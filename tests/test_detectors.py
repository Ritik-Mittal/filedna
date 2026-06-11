"""Tests for the type detection module."""
from __future__ import annotations

from pathlib import Path

import pytest

from filedna.detectors.type_detector import detect, extension_matches, get_extension


class TestDetect:
    def test_valid_pdf(self, tmp_files):
        real_type, mime = detect(tmp_files["valid_pdf"])
        assert real_type == "pdf"
        assert mime == "application/pdf"

    def test_valid_png(self, tmp_files):
        real_type, mime = detect(tmp_files["valid_png"])
        assert real_type == "png"
        assert mime == "image/png"

    def test_fake_pdf_detected_as_png(self, tmp_files):
        """A PNG renamed .pdf must be detected as png, not pdf."""
        real_type, mime = detect(tmp_files["fake_pdf"])
        assert real_type == "png"
        assert mime == "image/png"

    def test_valid_json(self, tmp_files):
        real_type, mime = detect(tmp_files["valid_json"])
        assert real_type == "json"

    def test_valid_csv(self, tmp_files):
        real_type, mime = detect(tmp_files["valid_csv"])
        assert real_type == "csv"

    def test_valid_md(self, tmp_files):
        real_type, mime = detect(tmp_files["valid_md"])
        assert real_type == "md"

    def test_valid_txt(self, tmp_files):
        real_type, mime = detect(tmp_files["valid_txt"])
        assert real_type == "txt"

    def test_valid_docx(self, tmp_files):
        real_type, mime = detect(tmp_files["valid_docx"])
        assert real_type == "docx"

    def test_valid_xlsx(self, tmp_files):
        real_type, mime = detect(tmp_files["valid_xlsx"])
        assert real_type == "xlsx"

    def test_valid_zip(self, tmp_files):
        real_type, mime = detect(tmp_files["valid_zip"])
        assert real_type == "zip"

    def test_nonexistent(self, tmp_path):
        real_type, mime = detect(tmp_path / "missing.pdf")
        assert real_type == "unknown"

    def test_empty_file(self, tmp_files):
        real_type, mime = detect(tmp_files["empty_file"])
        assert real_type == "unknown"


class TestExtensionMatches:
    def test_pdf_matches(self):
        assert extension_matches("pdf", "pdf") is True

    def test_jpg_jpeg_alias(self):
        assert extension_matches("jpg", "jpeg") is True
        assert extension_matches("jpeg", "jpg") is True

    def test_tiff_tif_alias(self):
        assert extension_matches("tiff", "tif") is True

    def test_html_htm(self):
        assert extension_matches("html", "htm") is True

    def test_mismatch(self):
        assert extension_matches("png", "pdf") is False

    def test_case_insensitive(self):
        assert extension_matches("pdf", "PDF") is True


class TestGetExtension:
    def test_pdf(self, tmp_files):
        assert get_extension(tmp_files["valid_pdf"]) == "pdf"

    def test_no_extension(self, tmp_path):
        p = tmp_path / "noext"
        p.write_text("x")
        assert get_extension(p) == ""
