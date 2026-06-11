"""Tests for metadata inspectors."""
from __future__ import annotations

import pytest

from filedna.inspectors.metadata import inspect, human_size


class TestHumanSize:
    def test_bytes(self):
        assert human_size(500) == "500 B"

    def test_kilobytes(self):
        result = human_size(2048)
        assert "KB" in result or "2.0" in result

    def test_megabytes(self):
        result = human_size(4 * 1024 * 1024)
        assert "MB" in result


class TestInspectPDF:
    def test_valid_pdf_has_pages(self, tmp_files):
        meta = inspect(tmp_files["valid_pdf"], "pdf")
        assert "pages" in meta
        assert meta["pages"] >= 1

    def test_valid_pdf_tokens(self, tmp_files):
        meta = inspect(tmp_files["valid_pdf"], "pdf")
        assert "estimated_tokens" in meta
        assert isinstance(meta["estimated_tokens"], int)


class TestInspectDocx:
    def test_valid_docx_paragraphs(self, tmp_files):
        meta = inspect(tmp_files["valid_docx"], "docx")
        assert "paragraphs" in meta
        assert "words" in meta
        assert "estimated_pages" in meta

    def test_valid_docx_tokens(self, tmp_files):
        meta = inspect(tmp_files["valid_docx"], "docx")
        assert "estimated_tokens" in meta


class TestInspectXlsx:
    def test_valid_xlsx_sheets(self, tmp_files):
        meta = inspect(tmp_files["valid_xlsx"], "xlsx")
        assert "sheets" in meta
        assert meta["sheets"] >= 1
        assert "rows" in meta
        assert "columns" in meta


class TestInspectImage:
    def test_valid_png_dimensions(self, tmp_files):
        meta = inspect(tmp_files["valid_png"], "png")
        assert "width" in meta
        assert "height" in meta
        assert meta["width"] == 1
        assert meta["height"] == 1
        assert "mode" in meta


class TestInspectJSON:
    def test_valid_json(self, tmp_files):
        meta = inspect(tmp_files["valid_json"], "json")
        assert "estimated_tokens" in meta


class TestInspectCSV:
    def test_valid_csv(self, tmp_files):
        meta = inspect(tmp_files["valid_csv"], "csv")
        assert "rows" in meta
        assert meta["rows"] >= 1
        assert "columns" in meta
        assert "estimated_tokens" in meta


class TestInspectZip:
    def test_valid_zip_file_count(self, tmp_files):
        meta = inspect(tmp_files["valid_zip"], "zip")
        assert "file_count" in meta
        assert meta["file_count"] >= 1


class TestInspectUnknown:
    def test_unknown_type_returns_empty_dict(self, tmp_files):
        meta = inspect(tmp_files["valid_txt"], "not_a_real_type")
        assert isinstance(meta, dict)
        assert meta == {}
