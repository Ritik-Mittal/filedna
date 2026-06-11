"""
Pytest fixtures for FileDNA tests.

Creates real (minimal) test files in a temporary directory.
"""
from __future__ import annotations

import io
import json
import struct
import zipfile
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers – minimal valid binary signatures
# ---------------------------------------------------------------------------

def _png_bytes() -> bytes:
    """Return a 1×1 red PNG."""
    import zlib
    # IHDR
    w, h = 1, 1
    ihdr_data = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
    ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)

    # IDAT (1×1 RGB red pixel, filter byte 0)
    raw = b"\x00\xFF\x00\x00"  # filter=0, R=255, G=0, B=0
    compressed = zlib.compress(raw)
    idat_crc = zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF
    idat = struct.pack(">I", len(compressed)) + b"IDAT" + compressed + struct.pack(">I", idat_crc)

    # IEND
    iend_crc = zlib.crc32(b"IEND") & 0xFFFFFFFF
    iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)

    return b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend


def _pdf_bytes() -> bytes:
    """Return a minimal valid 1-page PDF."""
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
        b"xref\n0 4\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"trailer\n<< /Size 4 /Root 1 0 R >>\n"
        b"startxref\n190\n%%EOF\n"
    )


def _docx_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(
            "word/document.xml",
            '<?xml version="1.0"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>Hello FileDNA</w:t></w:r></w:p></w:body>"
            "</w:document>",
        )
        z.writestr("[Content_Types].xml",
            '<?xml version="1.0"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>")
        z.writestr("_rels/.rels",
            '<?xml version="1.0"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>")
        z.writestr("word/_rels/document.xml.rels",
            '<?xml version="1.0"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
    return buf.getvalue()


def _xlsx_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/workbook.xml",
            '<?xml version="1.0"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
            "</sheets></workbook>")
        z.writestr("xl/worksheets/sheet1.xml",
            '<?xml version="1.0"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<sheetData><row r=\"1\"><c r=\"A1\" t=\"inlineStr\"><is><t>Hello</t></is></c></row></sheetData>"
            "</worksheet>")
        z.writestr("[Content_Types].xml",
            '<?xml version="1.0"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            "</Types>")
        z.writestr("_rels/.rels",
            '<?xml version="1.0"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>")
        z.writestr("xl/_rels/workbook.xml.rels",
            '<?xml version="1.0"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            "</Relationships>")
    return buf.getvalue()


def _zip_bytes(members: dict[str, bytes] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in (members or {"hello.txt": b"hello"}).items():
            z.writestr(name, data)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def tmp_files(tmp_path_factory) -> dict[str, Path]:
    """
    Session-scoped dict of named temp files.

    Keys: "valid_pdf", "valid_png", "valid_docx", "valid_xlsx",
          "fake_pdf"  (PNG renamed .pdf),
          "corrupted_pdf",
          "valid_json", "valid_csv", "valid_txt",
          "valid_zip",
          "empty_file",
    """
    d: Path = tmp_path_factory.mktemp("filedna_fixtures")
    files: dict[str, Path] = {}

    # Valid PDF
    p = d / "report.pdf"
    p.write_bytes(_pdf_bytes())
    files["valid_pdf"] = p

    # Valid PNG
    p = d / "photo.png"
    p.write_bytes(_png_bytes())
    files["valid_png"] = p

    # Fake PDF: PNG with .pdf extension
    p = d / "photo.pdf"
    p.write_bytes(_png_bytes())
    files["fake_pdf"] = p

    # Corrupted PDF: starts with %PDF- but then garbage
    p = d / "corrupted.pdf"
    p.write_bytes(b"%PDF-1.4\nGARBAGE_BINARY_DATA\x00\xFF\x00")
    files["corrupted_pdf"] = p

    # Valid DOCX
    p = d / "document.docx"
    p.write_bytes(_docx_bytes())
    files["valid_docx"] = p

    # Corrupted DOCX: invalid zip
    p = d / "corrupted.docx"
    p.write_bytes(b"PK\x03\x04NOTAVALIDDOCX\x00\xFF")
    files["corrupted_docx"] = p

    # Valid XLSX
    p = d / "spreadsheet.xlsx"
    p.write_bytes(_xlsx_bytes())
    files["valid_xlsx"] = p

    # Valid ZIP
    p = d / "archive.zip"
    p.write_bytes(_zip_bytes({"readme.txt": b"Hello", "data.json": b'{"x":1}'}))
    files["valid_zip"] = p

    # Renamed PNG as ZIP
    p = d / "photo.zip"
    p.write_bytes(_png_bytes())
    files["png_as_zip"] = p

    # Valid JSON
    p = d / "data.json"
    p.write_bytes(json.dumps({"key": "value", "nums": [1, 2, 3]}).encode())
    files["valid_json"] = p

    # Invalid JSON
    p = d / "broken.json"
    p.write_bytes(b"{not valid json!!")
    files["invalid_json"] = p

    # Valid CSV
    p = d / "data.csv"
    p.write_text("name,age,city\nAlice,30,London\nBob,25,Paris\n")
    files["valid_csv"] = p

    # Valid TXT
    p = d / "readme.txt"
    p.write_text("This is a test document.\nIt has multiple lines.\nFileDNA rocks.")
    files["valid_txt"] = p

    # Valid Markdown
    p = d / "notes.md"
    p.write_text("# Title\n\n## Section\n\n- item 1\n- item 2\n\n> quote\n")
    files["valid_md"] = p

    # Empty file
    p = d / "empty.pdf"
    p.write_bytes(b"")
    files["empty_file"] = p

    return files
