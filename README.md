<div align="center">

```
███████╗██╗██╗     ███████╗██████╗ ███╗   ██╗ █████╗
██╔════╝██║██║     ██╔════╝██╔══██╗████╗  ██║██╔══██╗
█████╗  ██║██║     █████╗  ██║  ██║██╔██╗ ██║███████║
██╔══╝  ██║██║     ██╔══╝  ██║  ██║██║╚██╗██║██╔══██║
██║     ██║███████╗███████╗██████╔╝██║ ╚████║██║  ██║
╚═╝     ╚═╝╚══════╝╚══════╝╚═════╝ ╚═╝  ╚═══╝╚═╝  ╚═╝
```

**Discover a file's true identity.**

*The Python file analysis library that trusts content, not extensions.*

[![PyPI version](https://img.shields.io/badge/PyPI-v1.2.4-brightgreen)](https://pypi.org/project/filedna/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-189%20passed-brightgreen)](tests/)
[![Coverage](https://img.shields.io/badge/coverage-76%25-yellow)](tests/)
[![Pure Python](https://img.shields.io/badge/pure%20python-no%20libmagic-blue)](pyproject.toml)

[**Quick Start**](#-quick-start) · [**Why FileDNA?**](#-why-filedna) · [**API Reference**](#-api-reference) · [**CLI**](#-cli) · [**Real-World Use Cases**](#-real-world-use-cases)

</div>

---

## The Problem Every Developer Knows

```python
# You've written some version of this. Every project. Every time.
def handle_upload(file_path):
    ext = file_path.split(".")[-1]         # ← trusting the extension
    if ext == "pdf":
        process_pdf(file_path)             # ← what if it's actually a PNG?
    elif ext == "docx":
        process_docx(file_path)            # ← what if it's corrupted?
    elif ext == "mp3":
        process_audio(file_path)           # ← what if it's a ZIP with malware?
```

Extensions lie. FileDNA doesn't.

```python
from filedna import analyze

result = analyze("invoice.pdf")

result.real_type          # "png"   ← it's actually a PNG
result.extension_matches  # False   ← extension lied
result.risk_score         # 90      ← high risk
result.errors             # ["File is not a valid PDF (real type: png)"]
```

One function. Every file type. No system dependencies. No API keys.

---

## 🚀 Quick Start

```bash
pip install filedna
```

```python
from filedna import analyze

result = analyze("report.pdf")

print(result.valid)           # True
print(result.real_type)       # "pdf"
print(result.risk_score)      # 0
print(result.summary)
# ✓ Valid PDF
# Pages: 34
# Language: en
# Contains tables
# Size: 4.2 MB
# Tokens: 15.4k
# Risk Score: 0
```

---

## 🧬 Why FileDNA?

### The competition does one thing. FileDNA does everything.

| Feature | `python-magic` | `filetype` | `puremagic` | `file-validator` | **FileDNA** |
|---|:---:|:---:|:---:|:---:|:---:|
| Magic byte detection | ✓ | ✓ | ✓ | ✓ | ✓ |
| No system deps (no `libmagic`) | ✗ | ✓ | ✓ | partial | **✓** |
| Extension mismatch detection | ✗ | ✗ | ✗ | ✗ | **✓** |
| Structural validation (is PDF parseable?) | ✗ | ✗ | ✗ | ✗ | **✓** |
| Risk score 0–100 | ✗ | ✗ | ✗ | ✗ | **✓** |
| Rich metadata (pages, dimensions, duration) | ✗ | ✗ | ✗ | ✗ | **✓** |
| Embedded executable detection | ✗ | ✗ | ✗ | ✗ | **✓** |
| PII detection & redaction | ✗ | ✗ | ✗ | ✗ | **✓** |
| Duplicate file detection | ✗ | ✗ | ✗ | ✗ | **✓** |
| Batch analysis with concurrency | ✗ | ✗ | ✗ | ✗ | **✓** |
| Single unified API | ✗ | ✗ | ✗ | ✗ | **✓** |

> **`python-magic` requires `libmagic` as a system dependency** — `apt install libmagic1` or `brew install libmagic`. Breaks on Windows, in Docker, in serverless. FileDNA is pure Python. Zero system dependencies.

---

## 🔬 What FileDNA Detects

### Extension Mismatch — The Spoofed File Problem

```python
# photo.png renamed to invoice.pdf
result = analyze("invoice.pdf")

result.valid              # False
result.real_type          # "png"          ← magic bytes say PNG
result.mime               # "image/png"
result.extension          # "pdf"          ← what the filename claims
result.extension_matches  # False          ← they don't match
result.risk_score         # 90             ← high risk
result.errors             # ["File is not a valid PDF (real type: png)"]
result.warnings           # ["Extension mismatch"]
```

### Corrupted Files

```python
result = analyze("broken.docx")

result.valid       # False
result.real_type   # "docx"
result.risk_score  # 70
result.errors      # ["DOCX is corrupted: bad ZIP structure"]
```

### Embedded Executables

```python
# ZIP containing a hidden .exe
result = analyze("document.zip")

result.risk_score  # 100
result.warnings    # ["Embedded executable detected: payload.exe"]
```

### PII in Documents

```python
from filedna import detect_pii, redact_pii

text = "Contact sarah@company.com or call +1-415-555-0192. Card: 4532015112830366"

pii = detect_pii(text)
pii.has_pii       # True
pii.types_found   # ["email", "phone_us", "credit_card"]
pii.count         # 3

# Replace all PII instantly
clean = redact_pii(text)
# "Contact [REDACTED_EMAIL] or call +[REDACTED_PHONE_US]. Card: [REDACTED_CREDIT_CARD]"
```

---

## 📦 Full API Reference

### Core Analysis

```python
from filedna import analyze, validate, detect_type, inspect_file, inspect_url, estimate_tokens

# Full identity report: type + validation + metadata + risk score
result = analyze("file.pdf")
result = analyze("file.pdf", skip_metadata=True)   # faster, no metadata

# Structural validation only (faster than analyze)
result = validate("file.pdf")
if not result.valid:
    print(result.errors)    # ["File is not a valid PDF"]

# Real type from magic bytes — fastest, no validation
detect_type("photo.pdf")    # → "png"    extension lied
detect_type("data.zip")     # → "docx"  actually a Word document

# Type-specific metadata
meta = inspect_file("report.pdf")
# {"pages": 34, "language": "en", "contains_tables": True, "estimated_tokens": 15423}

# URL inspection via HTTP HEAD — no download
info = inspect_url("https://example.com/file.pdf")
# {"valid": True, "real_type": "pdf", "size_human": "4.2 MB", "status_code": 200}

# LLM token count estimate
estimate_tokens("report.pdf")   # → 15423
```

### The AnalysisResult Object

```python
result = analyze("file.pdf")

result.valid              # bool   — passed all checks?
result.real_type          # str    — "pdf", "png", "mp3", "zip"...
result.mime               # str    — "application/pdf"
result.extension          # str    — declared extension from filename
result.extension_matches  # bool   — does extension match real type?
result.size_bytes         # int    — 4213567
result.size_human         # str    — "4.2 MB"
result.risk_score         # int    — 0 (clean) to 100 (dangerous)
result.warnings           # list   — ["Extension mismatch"]
result.errors             # list   — ["File is not a valid PDF"]
result.metadata           # dict   — pages, dims, duration, etc.
result.summary            # str    — human-readable one-liner

# Serialize to JSON
import json
print(json.dumps(result.model_dump(), indent=2))
```

### File Identity Utilities

```python
from filedna import (
    extract_exif,       # GPS coords, camera model, focal length, ISO
    detect_pii,         # email, phone, credit card, SSN, IBAN, API keys
    redact_pii,         # replace PII with [REDACTED_TYPE] tags
    content_hash,       # SHA-256 + MD5 in one call
    find_duplicates,    # content-based dedup across a folder
    diff_files,         # what changed between two versions?
    analyze_many,       # batch analysis with thread pool
)

# EXIF: GPS, camera, timestamps — no manual DMS→decimal conversion
exif = extract_exif("photo.jpg")
exif.camera_make          # "Apple"
exif.camera_model         # "iPhone 15 Pro"
exif.focal_length         # 6.86   (mm)
exif.iso                  # 50
exif.datetime_taken       # "2024:03:15 14:22:31"
exif.gps.latitude         # 51.507351   (decimal degrees, ready to use)
exif.gps.google_maps_url  # "https://www.google.com/maps?q=51.5,-0.12"

# Content hashing — SHA-256 + MD5, streams large files
h = content_hash("contract.pdf")
h.sha256   # "a750aec01847d06d..."
h.md5      # "d7591a0ac484c964..."
h == content_hash("contract_copy.pdf")   # True if identical content

# Find duplicates in an uploads folder
groups = find_duplicates(list(Path("uploads").rglob("*")))
for g in groups:
    print(f"{g.count} copies, {g.wasted_bytes} bytes wasted")
    # keep first, delete the rest
    for dup in g.paths[1:]:
        dup.unlink()

# Diff two document versions
diff = diff_files("contract_v1.pdf", "contract_v2.pdf")
diff.lines_added    # 6
diff.lines_removed  # 3
diff.diff_ratio     # 0.72
diff.summary        # "+6 added, -3 removed, 72% similar"
diff.unified_diff   # standard --- a/ +++ b/ format

# Batch analysis with concurrency
batch = analyze_many(list(Path("uploads").glob("*")), max_workers=8)
batch.total            # 50
batch.succeeded        # 47
batch.duration_seconds # 1.24
# Find all high-risk files
risky = [p for p, r in batch.results.items() if r.risk_score > 50]
```

### AI Features (Optional — Requires API Key)

```python
from filedna.features.ai_features import AIConfig, classify_content, extract_structured

# Works with OpenAI, Anthropic, Gemini, Mistral, Ollama, and 100+ providers
config = AIConfig(
    provider="openai",
    model="gpt-4o-mini",
    fallbacks=[
        AIConfig(provider="anthropic", model="claude-haiku-4-5"),
        AIConfig(provider="gemini",    model="gemini-1.5-flash"),
    ]
)

# "Is this a legal contract or invoice?" — beyond what extensions tell you
result = classify_content(text, config=config)
result.value            # {"label": "invoice", "confidence": "high"}
result.provider_used    # "openai/gpt-4o-mini"
result.used_fallback    # True if primary failed, fallback served it
result.summary()        # full attempt audit log with ✓/✗ per call

# Extract structured fields from any document
data = extract_structured(
    text,
    schema={
        "invoice_number": "string",
        "total_amount":   "float",
        "vendor_name":    "string",
        "line_items":     "list of {description: str, amount: float}",
    },
    config=config,
)
data.value["invoice_number"]   # "INV-2024-001"
data.value["total_amount"]     # 4250.00
```

> **AI features use exponential backoff with jitter, automatic fallback chains, and error classification** (rate limits retry, auth failures skip to next provider immediately). Every call returns an `AIResponse` with full audit trail — which provider served it, how many retries, what failed.

---

## 🛡️ Risk Score Engine

Scores range from **0** (clean) to **100** (dangerous). Capped at 100.

| Condition | Points |
|---|---|
| Extension mismatch | +40 |
| Corrupted / invalid structure | +50 |
| Errors present | +30 |
| Unreadable metadata | +20 |
| Empty file | +30 |
| **Embedded executable** (.exe, .dll, .bat, .ps1...) | **+80** |

```python
result = analyze("suspicious.zip")

if result.risk_score == 0:
    print("✓ Clean")
elif result.risk_score < 40:
    print("⚠ Low risk — review warnings")
elif result.risk_score < 70:
    print("⚠ Medium risk — manual review required")
else:
    print("✗ High risk — quarantine this file")
```

---

## 📁 Supported File Formats

| Category | Formats | Validation | Metadata |
|---|---|---|---|
| **Documents** | PDF, DOCX, XLSX, PPTX, EPUB, CSV, TXT, MD, JSON, XML, HTML | ✓ | ✓ |
| **Images** | PNG, JPG, WebP, GIF, BMP, TIFF, SVG | ✓ | ✓ |
| **Audio** | MP3, WAV, FLAC, OGG, M4A, AAC | ✓ | ✓ |
| **Video** | MP4, MOV, MKV, WebM, AVI | ✓ | ✓* |
| **Archives** | ZIP, TAR, GZ, BZ2, 7Z, RAR | ✓ | ✓ |

*Full video metadata (fps, codec, resolution) requires `ffprobe`: `brew install ffmpeg` or `apt install ffmpeg`

---

## 📊 Metadata by File Type

<details>
<summary><strong>PDF</strong></summary>

```python
meta = inspect_file("report.pdf")
meta["pages"]             # 34
meta["encrypted"]         # False
meta["contains_images"]   # True
meta["contains_tables"]   # True
meta["language"]          # "en"
meta["estimated_tokens"]  # 15423
```
</details>

<details>
<summary><strong>DOCX</strong></summary>

```python
meta["paragraphs"]        # 82
meta["words"]             # 3210
meta["estimated_pages"]   # 11
meta["language"]          # "en"
meta["estimated_tokens"]  # 6780
```
</details>

<details>
<summary><strong>XLSX</strong></summary>

```python
meta["sheets"]            # 3
meta["sheet_names"]       # ["Q1", "Q2", "Summary"]
meta["rows"]              # 1204
meta["columns"]           # 12
meta["estimated_tokens"]  # 3201
```
</details>

<details>
<summary><strong>Images (PNG, JPG, WebP, GIF, BMP, TIFF)</strong></summary>

```python
meta["width"]             # 1920
meta["height"]            # 1080
meta["mode"]              # "RGB"
meta["dpi"]               # (72, 72)
meta["has_transparency"]  # False
```
</details>

<details>
<summary><strong>Audio (MP3, WAV, FLAC, OGG, M4A)</strong></summary>

```python
meta["duration"]          # 213.4   (seconds)
meta["bitrate"]           # 320000  (bits/s)
meta["sample_rate"]       # 44100   (Hz)
meta["channels"]          # 2
```
</details>

<details>
<summary><strong>Video (MP4, MOV, MKV, WebM, AVI)</strong></summary>

```python
meta["duration"]          # 92.4    (seconds)
meta["resolution"]        # "1920x1080"
meta["fps"]               # 29.97
meta["codec"]             # "h264"
```
</details>

<details>
<summary><strong>Archives (ZIP, TAR, GZ)</strong></summary>

```python
meta["file_count"]                # 24
meta["total_uncompressed_bytes"]  # 4194304
```
</details>

---

## 💻 CLI

```bash
# Full analysis (JSON output)
filedna analyze report.pdf

# Human-friendly output
filedna analyze report.pdf --pretty

# Validate only — exits 0 (valid) or 1 (invalid), perfect for CI/CD
filedna validate upload.pdf && echo "safe to process"

# Detect real type — ignores the extension completely
filedna type photo.pdf
# → png

# Token count estimate
filedna tokens report.pdf
# → 15423

# URL inspection (HEAD only, no download)
filedna url https://example.com/file.pdf --pretty
```

**`--pretty` output:**

```
✓ PDF

Pages:        34
Language:     en
Contains tables
Size:         4.2 MB
Tokens:       15.4k
Risk Score:   0
MIME:         application/pdf
Ext match:    yes  ('pdf' declared)
```

---

## 🔧 Real-World Use Cases

### File Upload Validation (Web Apps / APIs)

```python
from filedna import analyze

def validate_upload(path: str, allowed_types: list[str]) -> dict:
    result = analyze(path, skip_metadata=True)   # fast path

    if not result.valid:
        return {"accept": False, "reason": result.errors[0]}

    if result.real_type not in allowed_types:
        return {"accept": False, "reason": f"File type '{result.real_type}' not allowed"}

    if result.risk_score > 50:
        return {"accept": False, "reason": f"High-risk file (score: {result.risk_score})"}

    return {"accept": True, "type": result.real_type, "size": result.size_human}
```

### RAG Pipeline — Pre-flight Check Before Indexing

```python
from filedna import analyze, estimate_tokens

MAX_TOKENS = 100_000

def preflight(path: str) -> bool:
    result = analyze(path)

    if not result.valid:
        print(f"Skipping {path}: {result.errors}")
        return False

    tokens = result.metadata.get("estimated_tokens", 0)
    if tokens > MAX_TOKENS:
        print(f"Skipping {path}: {tokens:,} tokens exceeds limit")
        return False

    return True
```

### Scan an Entire Uploads Folder

```python
from pathlib import Path
from filedna import analyze_many

batch = analyze_many(
    list(Path("uploads").rglob("*")),
    max_workers=8,
    on_progress=lambda done, total, path: print(f"{done}/{total}: {path}")
)

print(f"Processed {batch.total} files in {batch.duration_seconds}s")
print(f"Success rate: {batch.success_rate:.0%}")

# Files needing attention
for path, result in batch.results.items():
    if result.risk_score > 0:
        print(f"⚠ {path}: risk={result.risk_score}, {result.warnings}")
```

### Deduplicate an Archive

```python
from pathlib import Path
from filedna import find_duplicates

groups = find_duplicates(list(Path("documents").rglob("*")))

total_wasted = sum(g.wasted_bytes for g in groups)
print(f"Found {len(groups)} duplicate groups, {total_wasted / 1024 / 1024:.1f} MB wasted")

for group in groups:
    print(f"\nDuplicate ({group.count}x, {group.size_bytes} bytes each):")
    for i, path in enumerate(group.paths):
        marker = "KEEP" if i == 0 else "DELETE"
        print(f"  [{marker}] {path}")
```

### EXIF GPS Extraction

```python
from filedna import extract_exif

exif = extract_exif("photo.jpg")

if exif.has_gps:
    print(f"Location: {exif.gps}")                    # "51.507351, -0.127758"
    print(f"Maps: {exif.gps.google_maps_url}")         # ready-to-use URL
    print(f"Camera: {exif.camera_make} {exif.camera_model}")
    print(f"Settings: f/{exif.aperture}, ISO {exif.iso}, {exif.shutter_speed}")
    print(exif.summary)
```

---

## ⚙️ Architecture

```
filedna/
├── __init__.py              ← public API (all functions)
├── core/
│   ├── engine.py            ← analysis pipeline orchestration
│   ├── risk.py              ← risk scoring engine (0–100)
│   └── url_inspector.py     ← HTTP HEAD inspection
├── detectors/
│   └── type_detector.py     ← magic bytes + binary signatures (no libmagic)
├── validators/
│   └── file_validators.py   ← structural validation per type
├── inspectors/
│   └── metadata.py          ← metadata extraction per type
├── extractors/
│   ├── exif_extractor.py    ← EXIF + GPS extraction
│   └── text_extractor.py    ← plain text extraction (internal)
├── features/
│   ├── pipeline.py          ← PII, hashing, dedup, diff, batch
│   └── ai_features.py       ← AI layer with retry/fallback orchestration
├── models/
│   └── result.py            ← AnalysisResult (Pydantic v2)
└── cli/
    └── commands.py          ← Click CLI
```

### Detection Pipeline

```
File input
    │
    ▼
Magic bytes / binary signatures ──── offset-based pattern matching
    │
    ├── ZIP container? ──────────────── peek inside → docx/xlsx/pptx/epub/zip
    │
    ├── Text content? ───────────────── sniff → json/xml/html/csv/md/txt
    │
    ├── filetype library ────────────── fallback
    │
    └── puremagic ───────────────────── fallback
    │
    ▼
Extension mismatch check
    │
    ▼
Structural validation (is it actually parseable?)
    │
    ▼
Metadata extraction
    │
    ▼
Risk score computation
    │
    ▼
AnalysisResult
```

---

## 🏎️ Performance

| Operation | Time |
|---|---|
| `detect_type()` | < 10ms |
| `validate()` | < 100ms |
| `analyze()` | < 500ms |
| `analyze_many(50 files, workers=8)` | ~1.2s |

All imports are lazy — dependencies only load for the relevant file type. `detect_type()` loads nothing extra.

---

## 🔌 Installation Options

```bash
# Core (everything in this README)
pip install filedna

# With AI features (litellm for classify, extract_structured, etc.)
pip install filedna[ai]

# Development
pip install filedna[dev]
```

**Zero system dependencies.** Unlike `python-magic`, FileDNA does not require `libmagic`, so it works on Windows, macOS, Linux, Docker, and serverless without any `apt install` or `brew install`.

---

## 🛠️ Development

```bash
git clone https://github.com/filedna/filedna
cd filedna
pip install -e ".[dev]"

# Run tests (190 tests)
pytest

# With coverage
pytest --cov=filedna --cov-report=term-missing

# Lint
ruff check filedna/
```

---

## 🗺️ Roadmap

| Version | Features |
|---|---|
| **v1.2** ✓ | PII detection, content hashing, deduplication, file diff, batch analysis, EXIF extraction, AI classify/extract with retry+fallback |
| **v1.3** | OCR for scanned PDFs (AI-powered), archive deep inspection, HEIC/HEIF support |
| **v1.4** | Malware heuristics (YARA rules), steganography detection, content-level dedup |
| **v2.0** | MCP server, REST API, async API, FileDNA Server |

---

## 🤝 Contributing

Contributions are welcome. Please open an issue first to discuss what you want to change.

1. Fork the repo
2. Create a branch: `git checkout -b feature/your-feature`
3. Make your changes and add tests
4. Ensure tests pass: `pytest`
5. Ensure lint passes: `ruff check filedna/`
6. Open a pull request

---

## 📄 License

MIT — see [LICENSE](LICENSE).

---

<div align="center">

**FileDNA** · [PyPI](https://pypi.org/project/filedna/) · [Issues](https://github.com/filedna/filedna/issues)

*If FileDNA saved you from writing boilerplate, consider giving it a ⭐*

</div>