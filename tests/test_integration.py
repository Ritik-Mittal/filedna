"""Integration tests for the full FileDNA public API."""
from __future__ import annotations

import pytest

import filedna
from filedna import analyze, validate, detect_type, inspect_file, estimate_tokens
from filedna.models.result import AnalysisResult


class TestAnalyzeValidPDF:
    def test_returns_analysis_result(self, tmp_files):
        result = analyze(tmp_files["valid_pdf"])
        assert isinstance(result, AnalysisResult)

    def test_valid(self, tmp_files):
        result = analyze(tmp_files["valid_pdf"])
        assert result.valid is True

    def test_type(self, tmp_files):
        result = analyze(tmp_files["valid_pdf"])
        assert result.real_type == "pdf"

    def test_mime(self, tmp_files):
        result = analyze(tmp_files["valid_pdf"])
        assert result.mime == "application/pdf"

    def test_extension_matches(self, tmp_files):
        result = analyze(tmp_files["valid_pdf"])
        assert result.extension_matches is True

    def test_size_populated(self, tmp_files):
        result = analyze(tmp_files["valid_pdf"])
        assert result.size_bytes > 0
        assert result.size_human != ""

    def test_risk_score_zero(self, tmp_files):
        result = analyze(tmp_files["valid_pdf"])
        assert result.risk_score == 0

    def test_no_errors(self, tmp_files):
        result = analyze(tmp_files["valid_pdf"])
        assert result.errors == []

    def test_pages_in_metadata(self, tmp_files):
        result = analyze(tmp_files["valid_pdf"])
        assert "pages" in result.metadata
        assert result.metadata["pages"] >= 1

    def test_tokens_in_metadata(self, tmp_files):
        result = analyze(tmp_files["valid_pdf"])
        assert "estimated_tokens" in result.metadata

    def test_summary_contains_pdf(self, tmp_files):
        result = analyze(tmp_files["valid_pdf"])
        assert "PDF" in result.summary.upper()


class TestAnalyzeFakePDF:
    """PNG renamed to .pdf – the classic extension-mismatch scenario."""

    def test_invalid(self, tmp_files):
        result = analyze(tmp_files["fake_pdf"])
        assert result.valid is False

    def test_real_type_is_png(self, tmp_files):
        result = analyze(tmp_files["fake_pdf"])
        assert result.real_type == "png"

    def test_extension_mismatch(self, tmp_files):
        result = analyze(tmp_files["fake_pdf"])
        assert result.extension_matches is False

    def test_high_risk_score(self, tmp_files):
        result = analyze(tmp_files["fake_pdf"])
        assert result.risk_score >= 40

    def test_extension_mismatch_warning(self, tmp_files):
        result = analyze(tmp_files["fake_pdf"])
        assert any("mismatch" in w.lower() for w in result.warnings)

    def test_error_present(self, tmp_files):
        result = analyze(tmp_files["fake_pdf"])
        assert len(result.errors) > 0


class TestAnalyzeCorruptedPDF:
    def test_corrupted_pdf_not_fully_valid(self, tmp_files):
        result = analyze(tmp_files["corrupted_pdf"])
        # Corrupted PDF: either invalid or has errors/high risk
        assert result.risk_score > 0 or not result.valid or result.errors


class TestAnalyzePNG:
    def test_valid_png(self, tmp_files):
        result = analyze(tmp_files["valid_png"])
        assert result.real_type == "png"
        assert result.valid is True

    def test_png_dimensions_in_metadata(self, tmp_files):
        result = analyze(tmp_files["valid_png"])
        assert "width" in result.metadata
        assert "height" in result.metadata


class TestAnalyzeDocx:
    def test_valid_docx(self, tmp_files):
        result = analyze(tmp_files["valid_docx"])
        assert result.valid is True
        assert result.real_type == "docx"

    def test_paragraphs_in_metadata(self, tmp_files):
        result = analyze(tmp_files["valid_docx"])
        assert "paragraphs" in result.metadata

    def test_corrupted_docx_invalid(self, tmp_files):
        result = analyze(tmp_files["corrupted_docx"])
        assert result.valid is False


class TestAnalyzeXlsx:
    def test_valid_xlsx(self, tmp_files):
        result = analyze(tmp_files["valid_xlsx"])
        assert result.valid is True
        assert result.real_type == "xlsx"

    def test_sheets_in_metadata(self, tmp_files):
        result = analyze(tmp_files["valid_xlsx"])
        assert "sheets" in result.metadata


class TestAnalyzeJSON:
    def test_valid_json(self, tmp_files):
        result = analyze(tmp_files["valid_json"])
        assert result.valid is True
        assert result.real_type == "json"

    def test_invalid_json(self, tmp_files):
        result = analyze(tmp_files["invalid_json"])
        assert result.valid is False


class TestAnalyzeCSV:
    def test_valid_csv(self, tmp_files):
        result = analyze(tmp_files["valid_csv"])
        assert result.valid is True
        assert result.real_type == "csv"


class TestAnalyzeZip:
    def test_valid_zip(self, tmp_files):
        result = analyze(tmp_files["valid_zip"])
        assert result.valid is True
        assert result.real_type == "zip"

    def test_png_as_zip(self, tmp_files):
        result = analyze(tmp_files["png_as_zip"])
        assert result.valid is False
        assert result.extension_matches is False
        assert result.risk_score >= 40


class TestAnalyzeEmptyFile:
    def test_empty_file_invalid(self, tmp_files):
        result = analyze(tmp_files["empty_file"])
        assert result.valid is False
        assert result.risk_score > 0
        assert any("empty" in e.lower() for e in result.errors)


class TestAnalyzeMissingFile:
    def test_missing_file(self, tmp_path):
        result = analyze(tmp_path / "does_not_exist.pdf")
        assert result.valid is False
        assert len(result.errors) > 0


class TestValidateAPI:
    def test_validate_valid_pdf(self, tmp_files):
        result = validate(tmp_files["valid_pdf"])
        assert result.valid is True

    def test_validate_fake_pdf(self, tmp_files):
        result = validate(tmp_files["fake_pdf"])
        assert result.valid is False

    def test_validate_returns_analysis_result(self, tmp_files):
        result = validate(tmp_files["valid_png"])
        assert isinstance(result, AnalysisResult)


class TestDetectTypeAPI:
    def test_detect_type_pdf(self, tmp_files):
        assert detect_type(tmp_files["valid_pdf"]) == "pdf"

    def test_detect_type_png(self, tmp_files):
        assert detect_type(tmp_files["valid_png"]) == "png"

    def test_detect_type_fake_pdf(self, tmp_files):
        assert detect_type(tmp_files["fake_pdf"]) == "png"


class TestInspectFileAPI:
    def test_inspect_pdf(self, tmp_files):
        meta = inspect_file(tmp_files["valid_pdf"])
        assert isinstance(meta, dict)
        assert "pages" in meta

    def test_inspect_png(self, tmp_files):
        meta = inspect_file(tmp_files["valid_png"])
        assert "width" in meta
        assert "height" in meta


class TestEstimateTokensAPI:
    def test_estimate_txt(self, tmp_files):
        tokens = estimate_tokens(tmp_files["valid_txt"])
        assert isinstance(tokens, int)
        assert tokens > 0

    def test_estimate_missing_file(self, tmp_path):
        tokens = estimate_tokens(tmp_path / "missing.txt")
        assert tokens == 0


class TestAnalysisResultModel:
    def test_risk_score_capped_at_100(self, tmp_files):
        result = analyze(tmp_files["fake_pdf"])
        assert result.risk_score <= 100

    def test_serialisable_to_dict(self, tmp_files):
        result = analyze(tmp_files["valid_pdf"])
        d = result.model_dump()
        assert isinstance(d, dict)
        assert "valid" in d
        assert "real_type" in d
        assert "risk_score" in d

    def test_summary_property(self, tmp_files):
        result = analyze(tmp_files["valid_pdf"])
        s = result.summary
        assert isinstance(s, str)
        assert len(s) > 0

    def test_skip_metadata_flag(self, tmp_files):
        result = analyze(tmp_files["valid_pdf"], skip_metadata=True)
        assert result.valid is True
        assert result.metadata == {}
