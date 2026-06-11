"""Tests for the FileDNA CLI."""
from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from filedna.cli.commands import cli


@pytest.fixture()
def runner():
    return CliRunner()


class TestAnalyzeCommand:
    def test_valid_pdf_json(self, runner, tmp_files):
        result = runner.invoke(cli, ["analyze", str(tmp_files["valid_pdf"])])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["valid"] is True
        assert data["real_type"] == "pdf"

    def test_valid_pdf_pretty(self, runner, tmp_files):
        result = runner.invoke(cli, ["analyze", str(tmp_files["valid_pdf"]), "--pretty"])
        assert result.exit_code == 0
        assert "PDF" in result.output.upper()

    def test_fake_pdf_json(self, runner, tmp_files):
        result = runner.invoke(cli, ["analyze", str(tmp_files["fake_pdf"])])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["valid"] is False
        assert data["real_type"] == "png"
        assert data["extension_matches"] is False

    def test_missing_file(self, runner, tmp_path):
        result = runner.invoke(cli, ["analyze", str(tmp_path / "missing.pdf")])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["valid"] is False

    def test_no_metadata_flag(self, runner, tmp_files):
        result = runner.invoke(
            cli, ["analyze", str(tmp_files["valid_pdf"]), "--no-metadata"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["metadata"] == {}


class TestValidateCommand:
    def test_valid_pdf_exits_0(self, runner, tmp_files):
        result = runner.invoke(cli, ["validate", str(tmp_files["valid_pdf"])])
        assert result.exit_code == 0

    def test_fake_pdf_exits_1(self, runner, tmp_files):
        result = runner.invoke(cli, ["validate", str(tmp_files["fake_pdf"])])
        assert result.exit_code == 1


class TestTypeCommand:
    def test_type_pdf(self, runner, tmp_files):
        result = runner.invoke(cli, ["type", str(tmp_files["valid_pdf"])])
        assert result.exit_code == 0
        assert result.output.strip() == "pdf"

    def test_type_fake_pdf(self, runner, tmp_files):
        result = runner.invoke(cli, ["type", str(tmp_files["fake_pdf"])])
        assert result.exit_code == 0
        assert result.output.strip() == "png"


class TestTokensCommand:
    def test_tokens_txt(self, runner, tmp_files):
        result = runner.invoke(cli, ["tokens", str(tmp_files["valid_txt"])])
        assert result.exit_code == 0
        tokens = int(result.output.strip())
        assert tokens > 0
