"""
FileDNA – EXIF metadata extractor.

Developers constantly write this manually every time they need
to pull GPS coordinates, camera info, or shoot timestamps from images.

extract_exif(path) → ExifData

Returns a clean, typed dataclass — not the raw tag soup that
exifread/Pillow return directly.

What this replaces (code developers write every time):
    import exifread
    tags = exifread.process_file(open(path, 'rb'))
    # Now hand-parse IFD Rational values, convert GPS DMS→decimal...
    # 40+ lines of boilerplate
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GPSCoordinates:
    latitude: float
    longitude: float
    altitude: float | None = None
    direction: str | None = None   # "N"/"S"/"E"/"W"

    def __str__(self) -> str:
        return f"{self.latitude:.6f}, {self.longitude:.6f}"

    @property
    def google_maps_url(self) -> str:
        return f"https://www.google.com/maps?q={self.latitude},{self.longitude}"


@dataclass
class ExifData:
    """Clean, typed EXIF metadata. Raw tags available in `raw` if needed."""

    # Camera
    camera_make: str | None = None
    camera_model: str | None = None
    lens_model: str | None = None
    software: str | None = None

    # Capture settings
    focal_length: float | None = None      # mm
    focal_length_35mm: float | None = None # equivalent
    aperture: float | None = None          # f-number
    shutter_speed: str | None = None       # "1/125"
    iso: int | None = None
    exposure_mode: str | None = None
    flash: str | None = None
    white_balance: str | None = None

    # Timestamps
    datetime_taken: str | None = None      # original capture time
    datetime_digitized: str | None = None

    # Image properties
    orientation: int | None = None
    width: int | None = None
    height: int | None = None
    color_space: str | None = None

    # GPS
    gps: GPSCoordinates | None = None

    # Author / copyright
    artist: str | None = None
    copyright: str | None = None
    description: str | None = None

    # Raw tags — always available for edge cases
    raw: dict[str, Any] = field(default_factory=dict)

    # Extraction metadata
    warnings: list[str] = field(default_factory=list)
    extractor: str = "unknown"

    @property
    def has_gps(self) -> bool:
        return self.gps is not None

    @property
    def summary(self) -> str:
        lines: list[str] = []
        if self.camera_make and self.camera_model:
            lines.append(f"Camera: {self.camera_make} {self.camera_model}")
        elif self.camera_model:
            lines.append(f"Camera: {self.camera_model}")
        if self.datetime_taken:
            lines.append(f"Taken: {self.datetime_taken}")
        if self.focal_length:
            lines.append(f"Focal length: {self.focal_length}mm")
        if self.aperture:
            lines.append(f"Aperture: f/{self.aperture}")
        if self.shutter_speed:
            lines.append(f"Shutter: {self.shutter_speed}")
        if self.iso:
            lines.append(f"ISO: {self.iso}")
        if self.gps:
            lines.append(f"GPS: {self.gps}")
        return "\n".join(lines) if lines else "No EXIF data found"


# ---------------------------------------------------------------------------
# Rational → float helper (EXIF stores many values as fractions)
# ---------------------------------------------------------------------------

def _rational_to_float(tag_val: Any) -> float | None:
    """Convert exifread IfdTag rational to Python float."""
    try:
        v = tag_val.values
        if not v:
            return None
        r = v[0]
        if hasattr(r, "num") and hasattr(r, "den"):
            return r.num / r.den if r.den else None
        return float(r)
    except Exception:
        return None


def _tag_str(tags: dict, key: str) -> str | None:
    v = tags.get(key)
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _tag_int(tags: dict, key: str) -> int | None:
    v = tags.get(key)
    if v is None:
        return None
    try:
        return int(str(v))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# GPS parsing — the part developers dread most
# ---------------------------------------------------------------------------

def _parse_gps(tags: dict) -> GPSCoordinates | None:
    """
    Convert GPS IFD tags to decimal degrees.
    DMS (degrees, minutes, seconds) → decimal degrees.
    """
    try:
        lat_tag = tags.get("GPS GPSLatitude")
        lat_ref = tags.get("GPS GPSLatitudeRef")
        lon_tag = tags.get("GPS GPSLongitude")
        lon_ref = tags.get("GPS GPSLongitudeRef")

        if not (lat_tag and lon_tag):
            return None

        def dms_to_decimal(tag: Any, ref: Any) -> float:
            vals = tag.values
            d = vals[0].num / vals[0].den
            m = vals[1].num / vals[1].den
            s = vals[2].num / vals[2].den
            decimal = d + m / 60 + s / 3600
            if ref and str(ref) in ("S", "W"):
                decimal = -decimal
            return round(decimal, 7)

        lat = dms_to_decimal(lat_tag, lat_ref)
        lon = dms_to_decimal(lon_tag, lon_ref)

        alt: float | None = None
        alt_tag = tags.get("GPS GPSAltitude")
        if alt_tag:
            alt_val = _rational_to_float(alt_tag)
            alt_ref = tags.get("GPS GPSAltitudeRef")
            if alt_val is not None:
                alt = -alt_val if (alt_ref and str(alt_ref) == "1") else alt_val

        direction: str | None = None
        dir_tag = tags.get("GPS GPSImgDirection")
        if dir_tag:
            d = _rational_to_float(dir_tag)
            if d is not None:
                direction = f"{d:.1f}°"

        return GPSCoordinates(latitude=lat, longitude=lon, altitude=alt, direction=direction)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Shutter speed formatter
# ---------------------------------------------------------------------------

def _format_shutter(tag: Any) -> str | None:
    """Format shutter speed as human-readable fraction like '1/125'."""
    try:
        v = tag.values[0]
        n, d = v.num, v.den
        if n == 0:
            return None
        if d == 1:
            return f"{n}s"
        if n == 1:
            return f"1/{d}"
        # Simplify by normalising to 1/x
        ratio = d / n
        return f"1/{int(round(ratio))}"
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_exif(path: Path) -> ExifData:
    """
    Extract EXIF metadata from an image file.

    Returns ExifData with typed fields — camera info, capture settings,
    timestamps, and GPS coordinates as decimal degrees.

    Never raises. Returns ExifData with warnings on failure.
    """
    try:
        import exifread  # type: ignore
    except ImportError:
        return ExifData(
            warnings=["exifread not installed. Run: pip install exifread"],
            extractor="unavailable",
        )

    warnings: list[str] = []

    try:
        with open(path, "rb") as f:
            tags = exifread.process_file(f, details=False)
    except Exception as exc:
        return ExifData(warnings=[f"Could not read EXIF data: {exc}"])

    if not tags:
        # Try Pillow as fallback (handles more formats)
        try:
            from PIL import Image  # type: ignore
            from PIL.ExifTags import TAGS
            with Image.open(str(path)) as img:
                raw_exif = img._getexif()
                if raw_exif:
                    pil_tags = {TAGS.get(k, k): v for k, v in raw_exif.items()}
                    return _from_pil_tags(pil_tags)
        except Exception:
            pass
        return ExifData(
            warnings=["No EXIF data found in this file"],
            extractor="exifread",
        )

    # Build clean ExifData from exifread tags
    focal_raw = _rational_to_float(tags["EXIF FocalLength"]) if "EXIF FocalLength" in tags else None
    focal_35mm = _rational_to_float(tags["EXIF FocalLengthIn35mmFilm"]) if "EXIF FocalLengthIn35mmFilm" in tags else None
    aperture_raw = _rational_to_float(tags["EXIF FNumber"]) if "EXIF FNumber" in tags else None

    # Round to sensible precision
    focal = round(focal_raw, 1) if focal_raw else None
    focal35 = round(focal_35mm, 1) if focal_35mm else None
    aperture = round(aperture_raw, 1) if aperture_raw else None

    shutter: str | None = None
    if "EXIF ExposureTime" in tags:
        shutter = _format_shutter(tags["EXIF ExposureTime"])

    iso: int | None = None
    iso_tag = tags.get("EXIF ISOSpeedRatings")
    if iso_tag:
        try:
            iso = int(str(iso_tag))
        except Exception:
            pass

    # Raw dict for power users (convert to str for JSON safety)
    raw = {k: str(v) for k, v in tags.items()}

    return ExifData(
        camera_make=_tag_str(tags, "Image Make"),
        camera_model=_tag_str(tags, "Image Model"),
        lens_model=_tag_str(tags, "EXIF LensModel"),
        software=_tag_str(tags, "Image Software"),
        focal_length=focal,
        focal_length_35mm=focal35,
        aperture=aperture,
        shutter_speed=shutter,
        iso=iso,
        exposure_mode=_tag_str(tags, "EXIF ExposureMode"),
        flash=_tag_str(tags, "EXIF Flash"),
        white_balance=_tag_str(tags, "EXIF WhiteBalance"),
        datetime_taken=_tag_str(tags, "EXIF DateTimeOriginal"),
        datetime_digitized=_tag_str(tags, "EXIF DateTimeDigitized"),
        orientation=_tag_int(tags, "Image Orientation"),
        color_space=_tag_str(tags, "EXIF ColorSpace"),
        gps=_parse_gps(tags),
        artist=_tag_str(tags, "Image Artist"),
        copyright=_tag_str(tags, "Image Copyright"),
        description=_tag_str(tags, "Image ImageDescription"),
        raw=raw,
        warnings=warnings,
        extractor="exifread",
    )


def _from_pil_tags(pil_tags: dict) -> ExifData:
    """Build ExifData from Pillow's TAGS-decoded dict."""
    def _get(key: str) -> str | None:
        v = pil_tags.get(key)
        return str(v).strip() if v else None

    def _get_float(key: str) -> float | None:
        v = pil_tags.get(key)
        if v is None:
            return None
        try:
            if hasattr(v, "numerator"):
                return v.numerator / v.denominator
            return float(v)
        except Exception:
            return None

    focal = _get_float("FocalLength")
    aperture = _get_float("FNumber")

    return ExifData(
        camera_make=_get("Make"),
        camera_model=_get("Model"),
        focal_length=round(focal, 1) if focal else None,
        aperture=round(aperture, 1) if aperture else None,
        datetime_taken=_get("DateTimeOriginal"),
        raw={k: str(v) for k, v in pil_tags.items()},
        extractor="pillow",
    )
