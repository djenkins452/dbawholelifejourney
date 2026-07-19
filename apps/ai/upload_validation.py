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


# ─────────────────────────────────────────────────────────────────────────────
# Universal attachment validation (all content classes) — used by the dedicated
# upload endpoint. Every attachment travels through THIS one validator; only the
# later perception stage differs by type
# (docs/WLJ_MULTIMODAL_INTAKE_ARCHITECTURE.md §3–§5).
# ─────────────────────────────────────────────────────────────────────────────

KIND_IMAGE = "image"
KIND_DOCUMENT = "document"
KIND_AUDIO = "audio"
KIND_VIDEO = "video"

# Per-class byte caps (on the raw upload). Generous — the client normalizes
# images, and the point of universal intake is to rarely reject.
MAX_BYTES = {
    KIND_IMAGE: 15 * 1024 * 1024,
    KIND_DOCUMENT: 25 * 1024 * 1024,
    KIND_AUDIO: 40 * 1024 * 1024,
    KIND_VIDEO: 100 * 1024 * 1024,
}

# Canonical MIME → content kind. The one registry of what WLJ accepts.
_MIME_KIND = {
    "image/jpeg": KIND_IMAGE, "image/png": KIND_IMAGE, "image/gif": KIND_IMAGE,
    "image/webp": KIND_IMAGE, "image/tiff": KIND_IMAGE, "image/heic": KIND_IMAGE,
    "image/heif": KIND_IMAGE,
    "application/pdf": KIND_DOCUMENT,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": KIND_DOCUMENT,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": KIND_DOCUMENT,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": KIND_DOCUMENT,
    "text/plain": KIND_DOCUMENT, "text/markdown": KIND_DOCUMENT, "text/csv": KIND_DOCUMENT,
    "audio/mpeg": KIND_AUDIO, "audio/mp4": KIND_AUDIO, "audio/wav": KIND_AUDIO,
    "audio/aac": KIND_AUDIO,
    "video/mp4": KIND_VIDEO, "video/quicktime": KIND_VIDEO,
}

# Extension → canonical MIME for formats that magic bytes can't disambiguate
# (zip-based Office documents; plain-text families).
_EXT_MIME = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".csv": "text/csv",
}
_TEXT_EXTS = (".txt", ".md", ".markdown", ".csv")


def _ext(filename: str) -> str:
    name = (filename or "").lower()
    dot = name.rfind(".")
    return name[dot:] if dot >= 0 else ""


def _looks_like_text(raw: bytes) -> bool:
    """Heuristic: decodable as UTF-8 and free of NUL bytes (binary marker)."""
    if b"\x00" in raw[:4096]:
        return False
    try:
        raw[:4096].decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def sniff_content_type(raw: bytes, filename: str = "") -> Optional[str]:
    """Determine canonical MIME from magic bytes (+ extension only for formats
    magic can't disambiguate: Office = zip container, plain text). Returns the
    canonical MIME or None if unrecognized/unsupported. Never trusts a declared
    MIME.
    """
    # Images (reuse the image sniffer first for the common case).
    img = sniff_image_type(raw)
    if img:
        return img
    if len(raw) >= 12:
        # TIFF
        if raw[0:4] in (b"II*\x00", b"MM\x00*"):
            return "image/tiff"
        # HEIC/HEIF (ISO-BMFF 'ftyp' brand)
        if raw[4:8] == b"ftyp" and raw[8:12] in (
            b"heic", b"heix", b"hevc", b"heim", b"heis", b"hevm", b"hevs", b"mif1",
        ):
            return "image/heic"
        # PDF
        if raw[0:5] == b"%PDF-":
            return "application/pdf"
        # WAV
        if raw[0:4] == b"RIFF" and raw[8:12] == b"WAVE":
            return "audio/wav"
        # MP3
        if raw[0:3] == b"ID3" or raw[0:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
            return "audio/mpeg"
        # AAC (ADTS)
        if raw[0:2] in (b"\xff\xf1", b"\xff\xf9"):
            return "audio/aac"
        # ISO-BMFF 'ftyp' — MP4/MOV/M4A by brand
        if raw[4:8] == b"ftyp":
            brand = raw[8:12]
            if brand in (b"M4A ", b"M4B "):
                return "audio/mp4"
            if brand == b"qt  ":
                return "video/quicktime"
            return "video/mp4"  # isom/mp41/mp42/avc1/dash/…
        # Zip-based Office: disambiguate by extension.
        if raw[0:4] == b"PK\x03\x04":
            return _EXT_MIME.get(_ext(filename))  # None for a bare zip → rejected
    # Plain text families: by extension + a text heuristic.
    ext = _ext(filename)
    if ext in _TEXT_EXTS and _looks_like_text(raw):
        return _EXT_MIME.get(ext)
    return None


def validate_attachment(raw: bytes, *, filename: str = "", declared_mime: str = ""):
    """Validate a single uploaded attachment of ANY supported class.

    Sniffs the true type from bytes, maps it to a content kind, and enforces the
    per-class size cap. Returns a dict {mime, kind, size} on success. Raises
    UploadValidationError (with an HTTP status) on empty, unsupported, or
    oversize input. `declared_mime` is accepted for logging only — never trusted.
    """
    if not raw:
        raise UploadValidationError("Empty file.")

    mime = sniff_content_type(raw, filename)
    kind = _MIME_KIND.get(mime) if mime else None
    if not mime or not kind:
        raise UploadValidationError(
            "That file type isn’t supported yet. You can attach images, PDFs, "
            "Office documents, text/CSV, audio, and video."
        )

    cap = MAX_BYTES.get(kind, MAX_BYTES[KIND_DOCUMENT])
    if len(raw) > cap:
        raise UploadValidationError(
            f"That {kind} is too large (max {cap // (1024 * 1024)} MB)."
        )

    return {"mime": mime, "kind": kind, "size": len(raw)}
