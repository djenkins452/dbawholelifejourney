"""
PDF text extraction service.

Extracts text from text-based PDFs using pdfplumber.
Falls back to OCR if text extraction yields no usable content.
"""

import hashlib
import logging

import pdfplumber

logger = logging.getLogger(__name__)


class PDFTextExtractor:
    """Extract text from text-based (non-scanned) PDFs."""

    def __init__(self, file_path_or_stream):
        """
        Args:
            file_path_or_stream: Path to PDF file or file-like object.
        """
        self.source = file_path_or_stream

    def extract(self):
        """
        Extract text from all pages.

        Returns:
            dict with keys:
                - text: str (full extracted text)
                - pages: list[str] (text per page)
                - page_count: int
                - method: str ('text')
                - has_text: bool
        """
        pages = []
        try:
            with pdfplumber.open(self.source) as pdf:
                page_count = len(pdf.pages)
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    pages.append(text)
        except Exception as e:
            logger.error("PDF text extraction failed: %s", type(e).__name__)
            return {
                "text": "",
                "pages": [],
                "page_count": 0,
                "method": "text",
                "has_text": False,
                "error": str(e),
            }

        full_text = "\n".join(pages)
        has_text = bool(full_text.strip())

        return {
            "text": full_text,
            "pages": pages,
            "page_count": page_count,
            "method": "text",
            "has_text": has_text,
        }

    @staticmethod
    def compute_file_hash(file_path_or_stream):
        """Compute SHA-256 hash of the file."""
        sha256 = hashlib.sha256()
        if isinstance(file_path_or_stream, str):
            with open(file_path_or_stream, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha256.update(chunk)
        else:
            # File-like object
            file_path_or_stream.seek(0)
            for chunk in iter(lambda: file_path_or_stream.read(8192), b""):
                sha256.update(chunk)
            file_path_or_stream.seek(0)
        return sha256.hexdigest()
