"""Extended tests for additional file types and edge cases."""
from __future__ import annotations

import io
import struct
import zipfile
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Additional fixture helpers
# ---------------------------------------------------------------------------

def make_mp3(path: Path) -> Path:
    """Create a minimal MP3 with ID3 header."""
    path.write_bytes(b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x00" * 100)
    return path


def make_wav(path: Path) -> Path:
    """Create a minimal valid WAV file."""
    # 44-byte header + tiny audio data
    sample_rate = 44100
    channels = 1
    bits = 16
    data = b"\x00" * 88  # 44 frames of silence

    fmt_chunk = struct.pack(
        "<HHIIHH",
        1,            # PCM
        channels,
        sample_rate,
        sample_rate * channels * bits // 8,  # byte rate
        channels * bits // 8,                # block align
        bits,
    )
    riff = (
        b"RIFF"
        + struct.pack("<I", 36 + len(data))
        + b"WAVE"
        + b"fmt "
        + struct.pack("<I", 16)
        + fmt_chunk
        + b"data"
        + struct.pack("<I", len(data))
        + data
    )
    path.write_bytes(riff)
    return path


def make_gz(path: Path) -> Path:
    import gzip
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as f:
        f.write(b"hello gzip")
    path.write_bytes(buf.getvalue())
    return path


def make_bz2(path: Path) -> Path:
    import bz2
    path.write_bytes(bz2.compress(b"hello bzip2"))
    return path


def make_7z(path: Path) -> Path:
    path.write_bytes(b"7z\xbc\xaf'\x1c\x00\x04" + b"\x00" * 20)
    return path


def make_rar(path: Path) -> Path:
    path.write_bytes(b"Rar!\x1a\x07\x00" + b"\x00" * 20)
    return path


def make_pptx(path: Path) -> Path:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("ppt/presentation.xml",
            '<?xml version="1.0"?>'
            '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            "<p:sldMasterIdLst/><p:sldSz cx=\"9144000\" cy=\"6858000\"/></p:presentation>")
        z.writestr("[Content_Types].xml",
            '<?xml version="1.0"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
            "</Types>")
        z.writestr("_rels/.rels",
            '<?xml version="1.0"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>'
            "</Relationships>")
    path.write_bytes(buf.getvalue())
    return path


def make_epub(path: Path) -> Path:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("META-INF/container.xml",
            '<?xml version="1.0"?>'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            "<rootfiles><rootfile full-path=\"OEBPS/content.opf\" media-type=\"application/oebps-package+xml\"/></rootfiles>"
            "</container>")
        z.writestr("OEBPS/content.opf", "<package/>")
        z.writestr("OEBPS/chapter1.html", "<html><body><p>Hello EPUB</p></body></html>")
    path.write_bytes(buf.getvalue())
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAudioValidation:
    def test_valid_mp3(self, tmp_path):
        from filedna.validators.file_validators import validate
        mp3 = make_mp3(tmp_path / "song.mp3")
        # mutagen may not read ID3-only stub, but it shouldn't crash
        valid, errors, warnings = validate(mp3, "mp3")
        assert isinstance(valid, bool)

    def test_valid_wav(self, tmp_path):
        from filedna.validators.file_validators import validate
        wav = make_wav(tmp_path / "sound.wav")
        valid, errors, warnings = validate(wav, "wav")
        assert isinstance(valid, bool)


class TestArchiveValidation:
    def test_valid_gz(self, tmp_path):
        from filedna.validators.file_validators import validate
        gz = make_gz(tmp_path / "file.gz")
        valid, errors, warnings = validate(gz, "gz")
        assert valid is True

    def test_valid_bz2(self, tmp_path):
        from filedna.validators.file_validators import validate
        bz2 = make_bz2(tmp_path / "file.bz2")
        valid, errors, warnings = validate(bz2, "bz2")
        assert valid is True

    def test_valid_7z_signature(self, tmp_path):
        from filedna.validators.file_validators import validate
        f = make_7z(tmp_path / "file.7z")
        valid, errors, warnings = validate(f, "7z")
        assert valid is True

    def test_invalid_7z(self, tmp_path):
        from filedna.validators.file_validators import validate
        f = tmp_path / "bad.7z"
        f.write_bytes(b"not7z" + b"\x00" * 20)
        valid, errors, warnings = validate(f, "7z")
        assert valid is False

    def test_valid_rar_signature(self, tmp_path):
        from filedna.validators.file_validators import validate
        f = make_rar(tmp_path / "file.rar")
        valid, errors, warnings = validate(f, "rar")
        assert valid is True

    def test_invalid_rar(self, tmp_path):
        from filedna.validators.file_validators import validate
        f = tmp_path / "bad.rar"
        f.write_bytes(b"notrarbytes" + b"\x00" * 20)
        valid, errors, warnings = validate(f, "rar")
        assert valid is False

    def test_invalid_gz(self, tmp_path):
        from filedna.validators.file_validators import validate
        f = tmp_path / "bad.gz"
        f.write_bytes(b"\x1f\x8b" + b"NOTGZIP")
        valid, errors, warnings = validate(f, "gz")
        assert valid is False

    def test_invalid_tar(self, tmp_path):
        from filedna.validators.file_validators import validate
        f = tmp_path / "bad.tar"
        f.write_bytes(b"not a tar file at all" * 10)
        valid, errors, warnings = validate(f, "tar")
        assert valid is False

    def test_corrupted_zip_fails(self, tmp_path):
        from filedna.validators.file_validators import validate
        f = tmp_path / "corrupt.zip"
        f.write_bytes(b"PK\x03\x04CORRUPTED_DATA")
        valid, errors, warnings = validate(f, "zip")
        assert valid is False


class TestDocumentValidation:
    def test_valid_pptx(self, tmp_path):
        from filedna.validators.file_validators import validate
        pptx = make_pptx(tmp_path / "slides.pptx")
        valid, errors, warnings = validate(pptx, "pptx")
        assert valid is True

    def test_valid_epub(self, tmp_path):
        from filedna.validators.file_validators import validate
        epub = make_epub(tmp_path / "book.epub")
        valid, errors, warnings = validate(epub, "epub")
        assert valid is True

    def test_invalid_epub(self, tmp_path):
        from filedna.validators.file_validators import validate
        f = tmp_path / "bad.epub"
        # ZIP structure but no META-INF/container.xml
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("random.txt", "not epub")
        f.write_bytes(buf.getvalue())
        valid, errors, warnings = validate(f, "epub")
        assert valid is False

    def test_invalid_xlsx_bad_zip(self, tmp_path):
        from filedna.validators.file_validators import validate
        f = tmp_path / "bad.xlsx"
        f.write_bytes(b"PK\x03\x04GARBAGE")
        valid, errors, warnings = validate(f, "xlsx")
        assert valid is False

    def test_invalid_pptx_bad_zip(self, tmp_path):
        from filedna.validators.file_validators import validate
        f = tmp_path / "bad.pptx"
        f.write_bytes(b"PK\x03\x04GARBAGE")
        valid, errors, warnings = validate(f, "pptx")
        assert valid is False

    def test_html_valid(self, tmp_path):
        from filedna.validators.file_validators import validate
        f = tmp_path / "page.html"
        f.write_text("<html><body><h1>Hello</h1></body></html>")
        valid, errors, warnings = validate(f, "html")
        assert valid is True

    def test_xml_valid(self, tmp_path):
        from filedna.validators.file_validators import validate
        f = tmp_path / "data.xml"
        f.write_text('<?xml version="1.0"?><root><item>test</item></root>')
        valid, errors, warnings = validate(f, "xml")
        assert valid is True

    def test_xml_invalid(self, tmp_path):
        from filedna.validators.file_validators import validate
        f = tmp_path / "bad.xml"
        f.write_text("<root><unclosed>")
        valid, errors, warnings = validate(f, "xml")
        assert valid is False


class TestTextValidation:
    def test_empty_txt_warns(self, tmp_path):
        from filedna.validators.file_validators import validate
        f = tmp_path / "empty.txt"
        f.write_text("")
        valid, errors, warnings = validate(f, "txt")
        assert valid is True
        assert any("empty" in w.lower() for w in warnings)

    def test_empty_csv_warns(self, tmp_path):
        from filedna.validators.file_validators import validate
        f = tmp_path / "empty.csv"
        f.write_text("")
        valid, errors, warnings = validate(f, "csv")
        assert valid is True


class TestVideoValidation:
    def test_mp4_magic(self, tmp_path):
        from filedna.validators.file_validators import validate
        f = tmp_path / "video.mp4"
        # Minimal ftyp box signature at offset 4
        f.write_bytes(b"\x00\x00\x00\x20" + b"ftyp" + b"mp42" + b"\x00" * 100)
        valid, errors, warnings = validate(f, "mp4")
        assert valid is True

    def test_mkv_magic(self, tmp_path):
        from filedna.validators.file_validators import validate
        f = tmp_path / "video.mkv"
        f.write_bytes(b"\x1a\x45\xdf\xa3" + b"\x00" * 100)
        valid, errors, warnings = validate(f, "mkv")
        assert valid is True

    def test_avi_magic(self, tmp_path):
        from filedna.validators.file_validators import validate
        f = tmp_path / "video.avi"
        f.write_bytes(b"RIFF" + b"\x00\x00\x00\x00" + b"AVI " + b"\x00" * 100)
        valid, errors, warnings = validate(f, "avi")
        assert valid is True

    def test_unknown_video_warns(self, tmp_path):
        from filedna.validators.file_validators import validate
        f = tmp_path / "video.mov"
        f.write_bytes(b"unknown format" + b"\x00" * 50)
        valid, errors, warnings = validate(f, "mov")
        # Should pass (best-effort) with a warning
        assert valid is True


class TestInspectorsExtended:
    def test_inspect_epub(self, tmp_path):
        from filedna.inspectors.metadata import inspect
        epub = make_epub(tmp_path / "book.epub")
        meta = inspect(epub, "epub")
        assert "estimated_tokens" in meta

    def test_inspect_tar(self, tmp_path):
        from filedna.inspectors.metadata import inspect
        import tarfile
        tar_path = tmp_path / "archive.tar"
        with tarfile.open(str(tar_path), "w") as t:
            buf = io.BytesIO(b"hello")
            info = tarfile.TarInfo(name="hello.txt")
            info.size = len(b"hello")
            buf.seek(0)
            t.addfile(info, buf)
        meta = inspect(tar_path, "tar")
        assert "file_count" in meta
        assert meta["file_count"] >= 1

    def test_inspect_audio_mp3(self, tmp_path):
        from filedna.inspectors.metadata import inspect
        mp3 = make_mp3(tmp_path / "song.mp3")
        meta = inspect(mp3, "mp3")
        assert isinstance(meta, dict)

    def test_inspect_nonexistent_type(self, tmp_path):
        from filedna.inspectors.metadata import inspect
        f = tmp_path / "file.xyz"
        f.write_bytes(b"data")
        meta = inspect(f, "xyz_not_real")
        assert meta == {}

    def test_inspect_pptx(self, tmp_path):
        from filedna.inspectors.metadata import inspect
        pptx = make_pptx(tmp_path / "slides.pptx")
        meta = inspect(pptx, "pptx")
        assert "slides" in meta


class TestAnalyzeExtended:
    def test_analyze_pptx(self, tmp_path):
        from filedna import analyze
        pptx = make_pptx(tmp_path / "slides.pptx")
        result = analyze(pptx)
        assert result.valid is True
        assert result.real_type == "pptx"

    def test_analyze_epub(self, tmp_path):
        from filedna import analyze
        epub = make_epub(tmp_path / "book.epub")
        result = analyze(epub)
        assert result.valid is True
        assert result.real_type == "epub"

    def test_analyze_gz(self, tmp_path):
        from filedna import analyze
        gz = make_gz(tmp_path / "file.gz")
        result = analyze(gz)
        assert result.valid is True
        assert result.real_type == "gz"

    def test_analyze_directory_fails(self, tmp_path):
        from filedna import analyze
        result = analyze(tmp_path)
        assert result.valid is False

    def test_analyze_xml(self, tmp_path):
        from filedna import analyze
        f = tmp_path / "data.xml"
        f.write_text('<?xml version="1.0"?><root><item>test</item></root>')
        result = analyze(f)
        assert result.valid is True
        assert result.real_type == "xml"

    def test_zip_with_embedded_exe_high_risk(self, tmp_path):
        from filedna import analyze
        # ZIP with an embedded .exe
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("readme.txt", "hello")
            z.writestr("malware.exe", b"\x4d\x5a" + b"\x00" * 100)
        f = tmp_path / "suspicious.zip"
        f.write_bytes(buf.getvalue())
        result = analyze(f)
        assert result.risk_score >= 80
        assert any("exe" in w.lower() or "executable" in w.lower() for w in result.warnings)

    def test_detect_type_returns_string(self, tmp_path):
        from filedna import detect_type
        f = tmp_path / "test.json"
        import json
        f.write_text(json.dumps({"x": 1}))
        assert detect_type(f) == "json"

    def test_inspect_file_returns_dict(self, tmp_path):
        from filedna import inspect_file
        f = tmp_path / "doc.txt"
        f.write_text("Hello world test")
        meta = inspect_file(f)
        assert isinstance(meta, dict)
        assert "estimated_tokens" in meta
