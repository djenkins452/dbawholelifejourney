"""
Shared upload validation for the CoS multimodal arrival path.

ONE validation layer that BOTH chat transports (non-streaming /api/chat/ and
streaming /api/chat/stream/) — and any future domain intake surface — call, so
no endpoint can skip size/type/count enforcement. Implements the production
standards in docs/WLJ_MULTIMODAL_INTAKE_ARCHITECTURE.md §4:

  - True content type is determined by BYTE SNIFFING (magic numbers); the
    client-declared MIME is advisory only and never trusted for authorization.
  - Size and count are enforced on the DECODED bytes, identically on every path.

Images arrive in a common representation regardless of transport: a list of
(base64_string, declared_mime) tuples. Validation normalizes each to the
sniffed MIME and rejects anything unrecognized.
"""
from __future__ import annotations

import base64
import binascii
from typing import List, Optional, Tuple

# Platform limits (single source of truth for the chat intake path).
MAX_IMAGE_SIZE = 5 * 1024 * 1024   # 5 MB per image (decoded)
MAX_IMAGES = 5                     # per message

# Canonical image MIME types the CoS vision path accepts.
ALLOWED_IMAGE_TYPES = ("image/jpeg", "image/png", "image/gif", "image/webp")


class UploadValidationError(Exception):
    """Raised when an upload payload fails validation. `status` is the HTTP code."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def _strip_data_uri(b64: str) -> str:
    """Tolerate a `data:<mime>;base64,<payload>` prefix from browser FileReader."""
    if isinstance(b64, str) and b64.startswith("data:") and "," in b64:
        return b64.split(",", 1)[1]
    return b64


def sniff_image_type(raw: bytes) -> Optional[str]:
    """
    Return the canonical image MIME sniffed from magic bytes, or None if the
    bytes are not a recognized/allowed image. Never trusts a declared type.
    """
    if len(raw) < 12:
        return None
    # JPEG: FF D8 FF
    if raw[0:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    # PNG: 89 50 4E 47 0D 0A 1A 0A
    if raw[0:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    # GIF: GIF87a / GIF89a
    if raw[0:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    # WEBP: 'RIFF' .... 'WEBP'
    if raw[0:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_images_list(
    images_list: Optional[List[Tuple[str, str]]],
) -> List[Tuple[str, str]]:
    """
    Validate a list of (base64, declared_mime) image tuples and return a
    normalized list of (base64_without_data_uri, sniffed_mime).

    Raises UploadValidationError (with an HTTP status) on any violation:
      - too many images
      - undecodable base64
      - decoded size over the limit
      - bytes that are not a recognized/allowed image type

    An empty/None input returns [] (text-only turn).
    """
    if not images_list:
        return []

    if len(images_list) > MAX_IMAGES:
        raise UploadValidationError(f"Maximum {MAX_IMAGES} images per message")

    normalized: List[Tuple[str, str]] = []
    for item in images_list:
        try:
            b64, _declared = item
        except (ValueError, TypeError):
            raise UploadValidationError("Malformed image payload")

        b64 = _strip_data_uri(b64)
        try:
            raw = base64.b64decode(b64, validate=True)
        except (binascii.Error, ValueError):
            raise UploadValidationError("Invalid image data")

        if len(raw) > MAX_IMAGE_SIZE:
            raise UploadValidationError("Image too large (max 5MB)")

        sniffed = sniff_image_type(raw)
        if sniffed is None or sniffed not in ALLOWED_IMAGE_TYPES:
            raise UploadValidationError(
                "Invalid or unsupported image. Allowed: "
                + ", ".join(ALLOWED_IMAGE_TYPES)
            )

        # Trust the sniffed type, not the client-declared MIME.
        normalized.append((b64, sniffed))

    return normalized
