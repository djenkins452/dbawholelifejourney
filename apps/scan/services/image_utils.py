"""
Image utility functions for vision analysis.

Provides helpers to normalize images from different sources (ImageField,
FileField, base64 strings) into a consistent format for the vision API.
"""

import base64
import hashlib
import io
import logging
import mimetypes

from PIL import Image

logger = logging.getLogger(__name__)

# Max dimension for vision API (OpenAI processes at 2048x2048 max for "high" detail)
MAX_VISION_DIMENSION = 2048

# Image types we can analyze
ANALYZABLE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def compute_image_hash(base64_data: str) -> str:
    """Compute SHA-256 hash of base64-encoded image data for deduplication."""
    return hashlib.sha256(base64_data.encode("utf-8")).hexdigest()


def file_is_analyzable_image(file_field) -> bool:
    """Check if a FileField/ImageField contains an analyzable image."""
    if not file_field or not file_field.name:
        return False
    mime_type, _ = mimetypes.guess_type(file_field.name)
    return mime_type in ANALYZABLE_MIME_TYPES


def image_field_to_base64(image_field) -> tuple:
    """
    Read an ImageField/FileField and return (base64_str, mime_type).

    Returns (None, None) if the field is empty or unreadable.
    """
    if not image_field or not image_field.name:
        return None, None

    try:
        mime_type, _ = mimetypes.guess_type(image_field.name)
        if not mime_type:
            mime_type = "image/jpeg"

        image_field.open("rb")
        raw_bytes = image_field.read()
        image_field.close()

        encoded = base64.b64encode(raw_bytes).decode("utf-8")
        return encoded, mime_type

    except Exception as e:
        logger.warning("Failed to read image field %s: %s", image_field.name, e)
        return None, None


def resize_for_vision(base64_data: str, mime_type: str = "image/jpeg",
                      max_dim: int = MAX_VISION_DIMENSION) -> str:
    """
    Resize image if larger than max_dim to reduce API token costs.

    Returns the (possibly unchanged) base64 string.
    """
    try:
        raw_bytes = base64.b64decode(base64_data)
        img = Image.open(io.BytesIO(raw_bytes))

        if max(img.size) <= max_dim:
            return base64_data

        # Resize preserving aspect ratio
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)

        # Re-encode
        fmt_map = {
            "image/jpeg": "JPEG",
            "image/png": "PNG",
            "image/webp": "WEBP",
            "image/gif": "GIF",
        }
        fmt = fmt_map.get(mime_type, "JPEG")

        buf = io.BytesIO()
        save_kwargs = {"quality": 85} if fmt == "JPEG" else {}
        if img.mode in ("RGBA", "P") and fmt == "JPEG":
            img = img.convert("RGB")
        img.save(buf, format=fmt, **save_kwargs)

        return base64.b64encode(buf.getvalue()).decode("utf-8")

    except Exception as e:
        logger.warning("Image resize failed, using original: %s", e)
        return base64_data


def clean_base64(data: str) -> tuple:
    """
    Strip data URI prefix from base64 string.

    Returns (clean_base64, mime_type).
    """
    if "," in data and data.startswith("data:"):
        header, encoded = data.split(",", 1)
        # Extract mime type from "data:image/jpeg;base64"
        mime = header.replace("data:", "").replace(";base64", "")
        return encoded, mime
    return data, "image/jpeg"
