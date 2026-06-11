"""
FileDNA – URL content extractor.

extract_url(url) → URLContent

Fetches the actual page/file body and returns clean text.
This is different from inspect_url() which only does HEAD.

What this replaces (code developers write every time in RAG pipelines):
    resp = requests.get(url)
    soup = BeautifulSoup(resp.text, "html.parser")
    # Remove nav, footer, scripts, ads...
    # 30+ lines of cleanup

Uses trafilatura for web pages (removes boilerplate, nav, ads automatically)
Falls back to BeautifulSoup for structured HTML when trafilatura returns nothing.
For non-HTML URLs (PDF, DOCX etc.) — downloads the file to a temp path,
then routes through the normal extract_text() pipeline.
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


@dataclass
class URLContent:
    """Result of fetching and extracting content from a URL."""
    url: str = ""
    text: str = ""
    title: str | None = None
    author: str | None = None
    date: str | None = None
    description: str | None = None
    real_type: str = "unknown"
    mime: str | None = None
    size_bytes: int = 0
    char_count: int = 0
    word_count: int = 0
    extractor: str = "unknown"
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.text:
            self.char_count = len(self.text)
            self.word_count = len(self.text.split())

    @property
    def valid(self) -> bool:
        return bool(self.text.strip()) and not self.errors


def extract_url(
    url: str,
    *,
    timeout: int = 15,
    max_chars: int = 0,
    include_metadata: bool = True,
    user_agent: str = "Mozilla/5.0 (compatible; FileDNA/1.0)",
) -> URLContent:
    """
    Fetch a URL and extract clean text from its content.

    For web pages: uses trafilatura to strip boilerplate (nav, ads, footers).
    For files (PDF, DOCX, etc.): downloads to temp dir, routes through
    the normal text extraction pipeline.

    Args:
        url:              The URL to fetch.
        timeout:          HTTP timeout in seconds.
        max_chars:        Truncate text at this many characters (0 = no limit).
        include_metadata: Extract title, author, date alongside text.
        user_agent:       User-agent header for the request.

    Returns:
        URLContent — always succeeds, never raises.
    """
    result = URLContent(url=url)

    # Validate URL first
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            result.errors.append(f"Unsupported scheme: {parsed.scheme!r}")
            return result
        if not parsed.netloc:
            result.errors.append("URL has no host")
            return result
    except Exception as exc:
        result.errors.append(f"Invalid URL: {exc}")
        return result

    # Fetch with httpx
    try:
        import httpx  # type: ignore
        headers = {"User-Agent": user_agent}
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            resp = client.get(url)

        if resp.status_code >= 400:
            result.errors.append(f"HTTP {resp.status_code}: {resp.reason_phrase}")
            return result

        content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
        result.mime = content_type
        result.size_bytes = len(resp.content)

    except Exception as exc:
        result.errors.append(f"Fetch failed: {exc}")
        return result

    # Route based on content type
    if "text/html" in content_type or content_type == "":
        return _extract_html_response(result, resp.text, max_chars, include_metadata)

    # Non-HTML: treat as a file download
    return _extract_file_response(result, resp.content, content_type, max_chars)


def _extract_html_response(
    result: URLContent,
    html: str,
    max_chars: int,
    include_metadata: bool,
) -> URLContent:
    """Extract text from HTML using trafilatura (primary) or BeautifulSoup (fallback)."""
    result.real_type = "html"

    # trafilatura is purpose-built for article extraction
    try:
        import trafilatura  # type: ignore
        from trafilatura.settings import use_config  # type: ignore

        # Try with metadata extraction
        extracted = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            output_format="txt",
        )

        if include_metadata:
            try:
                meta = trafilatura.extract_metadata(html)
                if meta:
                    result.title = meta.title
                    result.author = ", ".join(meta.author) if meta.author else None
                    result.date = meta.date
                    result.description = meta.description
            except Exception:
                pass

        if extracted:
            text = extracted
            if max_chars and len(text) > max_chars:
                text = text[:max_chars]
                result.warnings.append(f"Text truncated at {max_chars} characters")
            result.text = text
            result.extractor = "trafilatura"
            return result

    except Exception as exc:
        result.warnings.append(f"trafilatura failed, falling back to BeautifulSoup: {exc}")

    # BeautifulSoup fallback
    try:
        from bs4 import BeautifulSoup  # type: ignore
        soup = BeautifulSoup(html, "html.parser")

        # Remove noise elements
        for tag in soup(["script", "style", "nav", "footer", "header",
                         "aside", "form", "noscript", "iframe"]):
            tag.decompose()

        # Try to find the main content area
        main = (
            soup.find("main") or
            soup.find("article") or
            soup.find(id="content") or
            soup.find(id="main-content") or
            soup.find(class_="content") or
            soup.body or
            soup
        )

        text = main.get_text(separator="\n", strip=True) if main else soup.get_text()
        # Collapse excessive blank lines
        import re
        text = re.sub(r"\n{3,}", "\n\n", text).strip()

        if include_metadata:
            title_tag = soup.find("title")
            if title_tag:
                result.title = title_tag.get_text().strip()
            desc = soup.find("meta", attrs={"name": "description"})
            if desc:
                result.description = desc.get("content", "")

        if max_chars and len(text) > max_chars:
            text = text[:max_chars]
            result.warnings.append(f"Text truncated at {max_chars} characters")

        result.text = text
        result.extractor = "beautifulsoup"
        return result

    except Exception as exc:
        result.errors.append(f"BeautifulSoup extraction failed: {exc}")
        return result


def _extract_file_response(
    result: URLContent,
    content: bytes,
    content_type: str,
    max_chars: int,
) -> URLContent:
    """
    Download binary content to a temp file, detect real type,
    then route through the standard text extraction pipeline.
    """
    from ..core.url_inspector import _mime_to_type
    from .text_extractor import extract_text

    real_type = _mime_to_type(content_type)
    result.real_type = real_type

    # Write to temp file
    suffix_map = {
        "pdf": ".pdf", "docx": ".docx", "xlsx": ".xlsx", "pptx": ".pptx",
        "csv": ".csv", "json": ".json", "xml": ".xml", "txt": ".txt",
        "epub": ".epub",
    }
    suffix = suffix_map.get(real_type, ".bin")

    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        extraction = extract_text(tmp_path, real_type, max_chars)
        result.text = extraction.text
        result.extractor = extraction.extractor
        result.warnings.extend(extraction.warnings)

        # Clean up
        tmp_path.unlink(missing_ok=True)

    except Exception as exc:
        result.errors.append(f"File extraction failed: {exc}")

    return result
