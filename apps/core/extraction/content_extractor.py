# ==============================================================================
# File: apps/core/extraction/content_extractor.py
# Description: Phase 6A — Shared content extraction for documents
# Created: 2026-03-17
# ==============================================================================
"""
ContentExtractor — Unified content extraction from PDF and image files.

Reuses existing infrastructure:
- apps.medical.services.pdf_text_extractor.PDFTextExtractor
- apps.medical.services.ocr_extractor.OCRExtractor
- apps.medical.services.ocr_extractor.extract_with_fallback

This module adds:
- File download from Cloudinary/storage
- Hash-based dedup (skip re-extraction)
- Quality scoring
- Image-specific extraction (non-PDF images)
"""

import hashlib
import io
import logging
import tempfile

from PIL import Image

logger = logging.getLogger(__name__)


def extract_document_content(document):
    """
    Extract text content from a Document's file.

    Returns:
        dict with keys:
            - text: str (extracted text)
            - method: str ('text', 'ocr', 'image_ocr', 'mixed')
            - page_count: int
            - has_text: bool
            - quality: float (0.0-1.0 extraction quality estimate)
            - content_hash: str (SHA-256 of file content)
            - error: str or None
    """
    if not document.file:
        return _empty_result(error="No file attached")

    # Download file content to memory
    try:
        file_bytes = _download_file(document)
    except Exception as e:
        logger.warning(
            "Failed to download file for document %s: %s",
            document.pk, e,
        )
        return _empty_result(error=f"Download failed: {e}")

    if not file_bytes:
        return _empty_result(error="Empty file")

    # Compute content hash for dedup
    content_hash = hashlib.sha256(file_bytes).hexdigest()

    # Route by file type
    file_type = getattr(document, 'file_type', '') or ''

    if file_type == 'pdf':
        return _extract_from_pdf(file_bytes, content_hash)
    elif file_type in ('image/jpeg', 'image/png'):
        return _extract_from_image(file_bytes, content_hash)
    else:
        return _empty_result(
            content_hash=content_hash,
            error=f"Unsupported file type: {file_type}",
        )


def _download_file(document):
    """Download file content to bytes."""
    f = document.file
    f.open('rb')
    try:
        return f.read()
    finally:
        f.close()


def _extract_from_pdf(file_bytes, content_hash):
    """Extract text from PDF using text extraction with OCR fallback."""
    try:
        from apps.medical.services.ocr_extractor import extract_with_fallback
    except ImportError:
        logger.warning("OCR extractor not available")
        return _empty_result(
            content_hash=content_hash,
            error="Extraction dependencies not available",
        )

    file_stream = io.BytesIO(file_bytes)
    result = extract_with_fallback(file_stream)

    quality = _estimate_quality(result)

    return {
        'text': result.get('text', ''),
        'method': result.get('method', 'unknown'),
        'page_count': result.get('page_count', 0),
        'has_text': result.get('has_text', False),
        'quality': quality,
        'content_hash': content_hash,
        'error': result.get('error'),
    }


def _extract_from_image(file_bytes, content_hash):
    """Extract text from an image file using OCR."""
    try:
        import pytesseract
    except ImportError:
        logger.warning("pytesseract not available for image OCR")
        return _empty_result(
            content_hash=content_hash,
            error="OCR dependencies not available",
        )

    try:
        img = Image.open(io.BytesIO(file_bytes))
        text = pytesseract.image_to_string(img)
        has_text = bool(text.strip())

        quality = 0.0
        if has_text:
            word_count = len(text.split())
            quality = min(1.0, word_count / 50)  # 50+ words = max quality

        return {
            'text': text,
            'method': 'image_ocr',
            'page_count': 1,
            'has_text': has_text,
            'quality': quality,
            'content_hash': content_hash,
            'error': None,
        }
    except Exception as e:
        logger.warning("Image OCR failed: %s", e)
        return _empty_result(
            content_hash=content_hash,
            error=f"Image OCR failed: {e}",
        )


def _estimate_quality(extraction_result):
    """Estimate extraction quality from result metrics."""
    if not extraction_result.get('has_text'):
        return 0.0

    text = extraction_result.get('text', '')
    method = extraction_result.get('method', '')

    # Text extraction is higher quality than OCR
    base_quality = 0.9 if method == 'text' else 0.6

    # Adjust by text density
    word_count = len(text.split())
    if word_count < 10:
        return base_quality * 0.3
    elif word_count < 50:
        return base_quality * 0.6
    else:
        return base_quality


def _empty_result(content_hash=None, error=None):
    """Return an empty extraction result."""
    return {
        'text': '',
        'method': 'none',
        'page_count': 0,
        'has_text': False,
        'quality': 0.0,
        'content_hash': content_hash or '',
        'error': error,
    }
