"""
OCR fallback extractor for scanned PDFs.

Uses pdf2image + pytesseract to OCR scanned pages.
Only used when text extraction yields no usable content.
"""

import logging
import tempfile

logger = logging.getLogger(__name__)


class OCRExtractor:
    """OCR extraction for scanned PDFs."""

    def __init__(self, file_path_or_stream):
        self.source = file_path_or_stream

    def extract(self):
        """
        OCR all pages of a PDF.

        Returns:
            dict with keys:
                - text: str
                - pages: list[str]
                - page_count: int
                - method: str ('ocr')
                - has_text: bool
        """
        try:
            from pdf2image import convert_from_path, convert_from_bytes
            import pytesseract
        except ImportError as e:
            logger.warning("OCR dependencies not available: %s", e)
            return {
                "text": "",
                "pages": [],
                "page_count": 0,
                "method": "ocr",
                "has_text": False,
                "error": f"OCR dependencies not installed: {e}",
            }

        try:
            # Convert PDF pages to images
            if isinstance(self.source, str):
                images = convert_from_path(self.source, dpi=300)
            else:
                self.source.seek(0)
                pdf_bytes = self.source.read()
                self.source.seek(0)
                images = convert_from_bytes(pdf_bytes, dpi=300)

            pages = []
            for img in images:
                text = pytesseract.image_to_string(img)
                pages.append(text)

            full_text = "\n".join(pages)
            return {
                "text": full_text,
                "pages": pages,
                "page_count": len(pages),
                "method": "ocr",
                "has_text": bool(full_text.strip()),
            }

        except Exception as e:
            logger.error("OCR extraction failed: %s", type(e).__name__)
            return {
                "text": "",
                "pages": [],
                "page_count": 0,
                "method": "ocr",
                "has_text": False,
                "error": str(e),
            }


def extract_with_fallback(file_path_or_stream):
    """
    Try text extraction first, fall back to OCR if no text found.

    Returns extraction result dict with 'method' indicating which was used.
    """
    from .pdf_text_extractor import PDFTextExtractor

    # Try text extraction first
    text_result = PDFTextExtractor(file_path_or_stream).extract()
    if text_result["has_text"]:
        return text_result

    # Fall back to OCR
    logger.info("No text found in PDF, attempting OCR fallback")
    ocr_result = OCRExtractor(file_path_or_stream).extract()
    if ocr_result["has_text"]:
        return ocr_result

    # Both failed - return text result with combined info
    return {
        "text": "",
        "pages": [],
        "page_count": text_result.get("page_count", 0),
        "method": "mixed",
        "has_text": False,
        "error": "Neither text extraction nor OCR produced usable content",
    }
