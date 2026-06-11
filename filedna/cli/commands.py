"""
FileDNA CLI.

Usage:
    filedna analyze <path> [--pretty] [--no-metadata]
    filedna validate <path>
    filedna type <path>
    filedna tokens <path>
    filedna url <url>
"""
from __future__ import annotations

import json
import sys

import click


def _safe_echo(text: str, **kwargs) -> None:
    """Echo text safely on all platforms including Windows cp1252 terminals."""
    try:
        click.echo(text, **kwargs)
    except UnicodeEncodeError:
        # Strip non-ASCII characters and retry
        safe = text.encode("ascii", errors="replace").decode("ascii")
        click.echo(safe, **kwargs)


def _icon(valid: bool) -> str:
    """Return ASCII-safe status icon."""
    return "[OK]" if valid else "[FAIL]"


def _warn_icon() -> str:
    return "[WARN]"


@click.group()
@click.version_option(package_name="filedna")
def cli() -> None:
    """FileDNA - Discover a file's true identity."""


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("path")
@click.option("--pretty", is_flag=True, default=False, help="Human-friendly output")
@click.option("--no-metadata", is_flag=True, default=False, help="Skip metadata extraction")
def analyze(path: str, pretty: bool, no_metadata: bool) -> None:
    """Analyze PATH and print a full identity report."""
    from .. import analyze as _analyze

    result = _analyze(path, skip_metadata=no_metadata)

    if pretty:
        _print_pretty(result)
    else:
        click.echo(json.dumps(result.model_dump(), indent=2, default=str))


def _print_pretty(result) -> None:  # type: ignore[type-arg]
    from ..models.result import AnalysisResult
    r: AnalysisResult = result

    icon = _icon(r.valid)
    color = "green" if r.valid else "red"
    _safe_echo(click.style(f"{icon} {r.real_type.upper()}", fg=color, bold=True))
    click.echo()

    meta = r.metadata
    if "pages" in meta:
        click.echo(f"Pages:        {meta['pages']}")
    if "slides" in meta:
        click.echo(f"Slides:       {meta['slides']}")
    if "paragraphs" in meta:
        click.echo(f"Paragraphs:   {meta['paragraphs']}")
    if "sheets" in meta:
        click.echo(f"Sheets:       {meta['sheets']}")
    if "duration" in meta:
        click.echo(f"Duration:     {meta['duration']}s")
    if "width" in meta and "height" in meta:
        click.echo(f"Dimensions:   {meta['width']}x{meta['height']}")
    if "language" in meta:
        click.echo(f"Language:     {meta['language']}")
    if "contains_tables" in meta and meta["contains_tables"]:
        click.echo("Contains tables")
    if "contains_images" in meta and meta["contains_images"]:
        click.echo("Contains images")

    click.echo(f"Size:         {r.size_human}")

    if "estimated_tokens" in meta:
        tok = meta["estimated_tokens"]
        tok_str = f"{tok / 1000:.1f}k" if tok >= 1000 else str(tok)
        click.echo(f"Tokens:       {tok_str}")

    risk_color = "green" if r.risk_score == 0 else ("yellow" if r.risk_score < 50 else "red")
    click.echo(f"Risk Score:   {click.style(str(r.risk_score), fg=risk_color)}")
    click.echo(f"MIME:         {r.mime}")

    ext_match = click.style("yes", fg="green") if r.extension_matches else click.style("no", fg="red")
    click.echo(f"Ext match:    {ext_match}  ({r.extension!r} declared)")

    if r.warnings:
        click.echo()
        for w in r.warnings:
            _safe_echo(click.style(f"{_warn_icon()}  {w}", fg="yellow"))

    if r.errors:
        click.echo()
        for e in r.errors:
            _safe_echo(click.style(f"{_icon(False)}  {e}", fg="red"))


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("path")
def validate(path: str) -> None:
    """Validate PATH and print result. Exits 0 if valid, 1 if invalid."""
    from .. import validate as _validate

    result = _validate(path)
    icon = _icon(result.valid)
    color = "green" if result.valid else "red"
    _safe_echo(click.style(f"{icon} {result.real_type.upper()}", fg=color, bold=True))
    if result.errors:
        for e in result.errors:
            _safe_echo(click.style(f"  {_icon(False)}  {e}", fg="red"))
    if result.warnings:
        for w in result.warnings:
            _safe_echo(click.style(f"  {_warn_icon()}  {w}", fg="yellow"))
    sys.exit(0 if result.valid else 1)


# ---------------------------------------------------------------------------
# type
# ---------------------------------------------------------------------------

@cli.command(name="type")
@click.argument("path")
def detect_type_cmd(path: str) -> None:
    """Print the detected real type of PATH."""
    from .. import detect_type

    click.echo(detect_type(path))


# ---------------------------------------------------------------------------
# tokens
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("path")
def tokens(path: str) -> None:
    """Estimate token count for PATH."""
    from .. import estimate_tokens

    click.echo(estimate_tokens(path))


# ---------------------------------------------------------------------------
# url
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("url")
@click.option("--pretty", is_flag=True, default=False, help="Human-friendly output")
def url(url: str, pretty: bool) -> None:
    """Inspect URL and print content type / metadata."""
    from .. import inspect_url as _inspect_url

    result = _inspect_url(url)
    if pretty:
        valid = result.get("valid", False)
        icon = _icon(valid)
        color = "green" if valid else "red"
        _safe_echo(click.style(f"{icon} {result.get('real_type', 'unknown').upper()}", fg=color, bold=True))
        click.echo(f"URL:    {result['url']}")
        click.echo(f"MIME:   {result.get('mime', 'unknown')}")
        if result.get("size_human"):
            click.echo(f"Size:   {result['size_human']}")
        if result.get("status_code"):
            click.echo(f"HTTP:   {result['status_code']}")
        for e in result.get("errors", []):
            _safe_echo(click.style(f"{_icon(False)}  {e}", fg="red"))
    else:
        click.echo(json.dumps(result, indent=2, default=str))


def main() -> None:
    cli()


if __name__ == "__main__":
    main()