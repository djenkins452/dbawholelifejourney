"""
Receipt Vision Service

Processes receipt images through GPT-4o Vision API to extract
structured receipt data (store, date, items, total, receipt type).

For PDFs: extracts text via pdfplumber first, falls back to
Vision API only if text extraction yields insufficient content.

Prefers URL-based image input (Cloudinary URL) over base64 to avoid
format issues — iPhone cameras may produce HEIC which can't be read
without pillow-heif. Cloudinary normalizes the format on upload.
"""

import base64
import hashlib
import io
import json
import logging
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)


# Receipt-specific Vision prompt — extracts + classifies in one call
RECEIPT_VISION_PROMPT = """You are a receipt OCR specialist. Your job is to read a photo of a receipt and extract EVERY purchased item into structured JSON.

CRITICAL RULES — read carefully:
- Read the receipt TOP to BOTTOM, section by section. Do NOT skip any section.
- Extract EVERY SINGLE line item printed on the receipt. Typical grocery receipts have 15-40+ items.
- Read item names EXACTLY as printed on the receipt (they are often abbreviated like "DM CREAM CORN", "FL NAT PROV CHS SLCS"). Copy the abbreviations exactly — do NOT expand or rewrite them.
- Do NOT invent, guess, or hallucinate items. Only include items you can actually read on the receipt.
- Each item has a DIFFERENT name and usually a DIFFERENT price. If you find yourself listing the same item name multiple times, you are hallucinating — re-read the receipt.
- Lines with discounts, coupons, savings, tax, or subtotals are NOT items — skip those.
- Weight-based items (e.g., "2.34 lb @ $3.99/lb") should have quantity set to the weight.
- Multi-quantity items (e.g., "2 @ 3.99") should have quantity=2 and price=3.99 (unit price).

CLASSIFICATION RULES:
- "grocery": Supermarket, grocery store, bulk food store (Food Lion, Walmart, Kroger, Whole Foods, Costco, Aldi, Publix, etc.)
- "restaurant": Restaurant, cafe, bar, fast food, takeout, delivery service
- "retail": Non-food retail (Amazon, Target non-grocery, clothing, electronics, hardware, etc.)
- "unknown": Cannot determine

EXTRACTION RULES:
1. Extract the STORE NAME exactly as printed at the top of the receipt
2. Extract the DATE in YYYY-MM-DD format (look near the top or bottom)
3. Extract EVERY line item: name (as printed), quantity, unit price
4. Extract subtotal, tax, and total amounts
5. For grocery items, classify each into a category
6. Detect the payment method if visible

RESPONSE FORMAT (strict JSON):
{{
  "receipt_type": "grocery",
  "store": "Store Name",
  "date": "YYYY-MM-DD",
  "items": [
    {{
      "name": "item description as printed on receipt",
      "quantity": 1,
      "price": 3.99,
      "category": "produce"
    }}
  ],
  "subtotal": 45.23,
  "tax": 3.12,
  "total": 48.35,
  "payment_method": "credit"
}}

Category options: produce, dairy, meat, seafood, bakery, frozen, beverage, snack, canned, cereal, condiment, household, health, other
Payment method options: cash, credit, debit, ebt, mobile, other (omit if not visible)

Respond ONLY with valid JSON. No markdown, no explanation."""


@dataclass
class ReceiptVisionResult:
    """Structured result from Vision API receipt processing."""

    receipt_type: str = "unknown"
    store: str = ""
    date: Optional[str] = None
    items: list = field(default_factory=list)
    subtotal: Optional[Decimal] = None
    tax: Optional[Decimal] = None
    total: Optional[Decimal] = None
    raw_text: str = ""
    source: str = "vision_api"  # "vision_api" or "pdf_text"
    error: Optional[str] = None
    payment_method: str = ""
    image_hash: str = ""  # SHA-256 of original bytes for deduplication


def detect_image_format(raw_bytes):
    """Detect actual image format from magic bytes (file signature)."""
    if len(raw_bytes) < 12:
        return "unknown"
    if raw_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if raw_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if raw_bytes[:4] == b"GIF8":
        return "image/gif"
    if raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WEBP":
        return "image/webp"
    if raw_bytes[4:8] == b"ftyp":
        # HEIF/HEIC container (ISO base media file format)
        return "image/heic"
    return "unknown"


def prepare_image_for_api(raw_bytes, content_type="image/jpeg"):
    """
    Prepare image for Vision API with format detection and validation.

    Detects the ACTUAL format from magic bytes (ignoring declared content_type
    which may be wrong — e.g., iPhone may declare HEIC as image/jpeg).

    For API-supported formats (JPEG, PNG, GIF, WebP): pass through as-is.
    For unsupported formats (HEIC, etc.): convert through Pillow.
    If conversion fails: return error instead of sending unreadable data.

    Returns (image_bytes, mime_type) or raises ValueError if unconvertible.
    """
    # Detect actual format from magic bytes
    detected = detect_image_format(raw_bytes)
    logger.info(
        "Receipt image: %d KB, declared=%s, detected=%s",
        len(raw_bytes) // 1024,
        content_type,
        detected,
    )

    # Warn if declared type doesn't match detected type
    if detected != "unknown" and detected != content_type:
        logger.warning(
            "Receipt image format mismatch: declared=%s but detected=%s",
            content_type,
            detected,
        )

    # API supports: JPEG, PNG, GIF, WebP
    api_supported = {"image/jpeg", "image/png", "image/gif", "image/webp"}

    if detected in api_supported:
        # Format is correct — send as-is
        return raw_bytes, detected

    # Unsupported format — must convert through Pillow
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(raw_bytes))

        # Convert RGBA/P to RGB for JPEG
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        converted = buf.getvalue()

        logger.info(
            "Receipt image converted from %s: %d KB → %d KB JPEG (%dx%d)",
            detected,
            len(raw_bytes) // 1024,
            len(converted) // 1024,
            img.size[0],
            img.size[1],
        )
        return converted, "image/jpeg"

    except Exception as e:
        logger.error(
            "Cannot convert receipt image (format=%s, declared=%s): %s",
            detected,
            content_type,
            e,
        )
        raise ValueError(
            f"Unsupported image format ({detected}). "
            f"Please use JPEG or PNG. Error: {e}"
        )


def compute_receipt_hash(raw_bytes):
    """Compute SHA-256 hash of raw file bytes for deduplication."""
    return hashlib.sha256(raw_bytes).hexdigest()


class ReceiptVisionService:
    """
    Processes receipt images/PDFs through Vision AI.

    Flow:
    1. For images with a URL (Cloudinary): pass URL directly to Vision API
       — this avoids HEIC/format issues since Cloudinary serves JPEG/PNG
    2. For images without URL: detect format, convert if needed, base64 encode
    3. For PDFs: try pdfplumber text extraction first, Vision API fallback
    4. Returns ReceiptVisionResult with extracted data
    """

    def __init__(self):
        self._client = None

    @property
    def client(self):
        """Lazy-initialize OpenAI client."""
        if self._client is None:
            try:
                import openai

                self._client = openai.OpenAI(
                    api_key=getattr(settings, "OPENAI_API_KEY", ""),
                    timeout=60,
                )
            except ImportError:
                logger.error("openai package not installed")
            except Exception as e:
                logger.error(
                    "Failed to initialize OpenAI client: %s", e, exc_info=True
                )
        return self._client

    def process_image(self, raw_bytes, content_type="image/jpeg", image_url=None):
        """
        Process image through Vision API.

        Prefers image_url (Cloudinary) over raw bytes to avoid format issues.
        iPhone cameras may produce HEIC which pillow can't convert without
        pillow-heif. Cloudinary normalizes format on upload.

        Args:
            raw_bytes: Raw image file bytes (used for hash + fallback)
            content_type: MIME type from upload
            image_url: Optional URL (e.g., Cloudinary) — preferred path

        Returns:
            ReceiptVisionResult
        """
        # Compute hash on original bytes for deduplication
        image_hash = compute_receipt_hash(raw_bytes)

        # Prefer URL approach — avoids format issues entirely
        if image_url and image_url.startswith("http"):
            logger.info(
                "Receipt %s: using URL approach (%d KB uploaded, url=%s)",
                image_hash[:8],
                len(raw_bytes) // 1024,
                image_url[:80],
            )
            result = self._call_vision_api_with_url(image_url)
        else:
            # Fallback to base64 approach with format detection
            logger.info(
                "Receipt %s: using base64 approach (%d KB, type=%s)",
                image_hash[:8],
                len(raw_bytes) // 1024,
                content_type,
            )
            try:
                api_bytes, api_mime = prepare_image_for_api(raw_bytes, content_type)
            except ValueError as e:
                return ReceiptVisionResult(error=str(e))

            base64_data = base64.b64encode(api_bytes).decode("utf-8")
            result = self._call_vision_api_with_base64(base64_data, api_mime)

        result.image_hash = image_hash
        return result

    def process_pdf(self, raw_bytes):
        """
        Process PDF bytes: try text extraction first, Vision API fallback.

        Args:
            raw_bytes: Raw PDF file bytes

        Returns:
            ReceiptVisionResult
        """
        pdf_hash = compute_receipt_hash(raw_bytes)

        # Try pdfplumber text extraction first (fast, free)
        text_result = self._extract_pdf_text(raw_bytes)

        if text_result and len(text_result.strip()) > 50:
            # Got usable text — return it for the text parser
            return ReceiptVisionResult(
                raw_text=text_result,
                source="pdf_text",
                image_hash=pdf_hash,
            )

        # Scanned/image PDF — render first page and send to Vision
        result = self._process_pdf_as_image(raw_bytes)
        if not result.image_hash:
            result.image_hash = pdf_hash
        return result

    def _extract_pdf_text(self, raw_bytes):
        """Extract text from PDF using pdfplumber."""
        try:
            import pdfplumber

            pages_text = []
            with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
                for page in pdf.pages[:5]:  # Max 5 pages for receipts
                    text = page.extract_text() or ""
                    pages_text.append(text)

            return "\n".join(pages_text)

        except ImportError:
            logger.warning("pdfplumber not installed, cannot extract PDF text")
            return ""
        except Exception as e:
            logger.error("PDF text extraction failed: %s", e, exc_info=True)
            return ""

    def _process_pdf_as_image(self, raw_bytes):
        """Render PDF first page as image and process via Vision API."""
        try:
            from pdf2image import convert_from_bytes

            images = convert_from_bytes(raw_bytes, first_page=1, last_page=1, dpi=200)
            if not images:
                return ReceiptVisionResult(error="Could not render PDF to image")

            # Convert to JPEG bytes at high quality
            buf = io.BytesIO()
            images[0].save(buf, format="JPEG", quality=95)
            return self.process_image(buf.getvalue(), "image/jpeg")

        except ImportError:
            logger.warning("pdf2image not installed, cannot render PDF pages")
            return ReceiptVisionResult(error="PDF image rendering not available")
        except Exception as e:
            logger.error("PDF to image conversion failed: %s", e, exc_info=True)
            return ReceiptVisionResult(error=f"PDF conversion failed: {e}")

    def _call_vision_api_with_url(self, image_url):
        """
        Call Vision API using an image URL (preferred — avoids format issues).
        OpenAI fetches the image directly from the URL (e.g., Cloudinary CDN).
        """
        if not self.client:
            return ReceiptVisionResult(error="Vision API client not available")

        model = getattr(settings, "OPENAI_VISION_MODEL", "gpt-4o")

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": RECEIPT_VISION_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_url,
                                    "detail": "high",
                                },
                            },
                        ],
                    }
                ],
                max_tokens=4096,
                temperature=0,
            )

            content = response.choices[0].message.content.strip()
            logger.info("Vision API response (URL mode): %d chars", len(content))

            return self._parse_raw_response(content)

        except Exception as e:
            logger.error("Vision API call (URL) failed: %s", e, exc_info=True)
            return ReceiptVisionResult(error=str(e))

    def _call_vision_api_with_base64(self, base64_data, mime_type):
        """
        Call Vision API using base64-encoded image data (fallback).
        """
        if not self.client:
            return ReceiptVisionResult(error="Vision API client not available")

        model = getattr(settings, "OPENAI_VISION_MODEL", "gpt-4o")

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": RECEIPT_VISION_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{base64_data}",
                                    "detail": "high",
                                },
                            },
                        ],
                    }
                ],
                max_tokens=4096,
                temperature=0,
            )

            content = response.choices[0].message.content.strip()
            logger.info("Vision API response (base64 mode): %d chars", len(content))

            return self._parse_raw_response(content)

        except Exception as e:
            logger.error("Vision API call (base64) failed: %s", e, exc_info=True)
            return ReceiptVisionResult(error=str(e))

    def _parse_raw_response(self, content):
        """Parse raw Vision API response string into ReceiptVisionResult."""
        try:
            # Strip markdown fences if present
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

            data = json.loads(content)

            # Check for hallucination before parsing
            hallucination_error = self._detect_hallucination(data)
            if hallucination_error:
                logger.warning(
                    "Vision API result rejected (hallucination): %s — raw items: %s",
                    hallucination_error,
                    json.dumps(data.get("items", [])[:5]),
                )
                return ReceiptVisionResult(
                    error=f"Could not read receipt clearly: {hallucination_error}. "
                    f"Please try again with better lighting and a straight-on angle."
                )

            result = self._parse_vision_response(data)

            # Log extraction summary for debugging
            logger.info(
                "Vision extracted: store=%s, date=%s, items=%d, total=%s",
                result.store,
                result.date,
                len(result.items),
                result.total,
            )
            return result

        except json.JSONDecodeError as e:
            logger.error("Vision API returned invalid JSON: %s — content: %s", e, content[:500])
            return ReceiptVisionResult(error=f"Invalid JSON response: {e}")

    def _detect_hallucination(self, data):
        """
        Detect if Vision API result is hallucinated (model couldn't read
        the image and made up a generic grocery list).

        Returns error string if hallucination detected, None if OK.
        """
        items = data.get("items", [])
        if not items:
            return None  # No items isn't hallucination, just empty

        # Check 1: Too many items with the same price (hallucination pattern)
        prices = [item.get("price") for item in items if item.get("price")]
        if len(prices) >= 5:
            from collections import Counter
            price_counts = Counter(prices)
            most_common_price, count = price_counts.most_common(1)[0]
            # If >60% of items have the same price, likely hallucinated
            if count / len(prices) > 0.6 and len(prices) >= 5:
                return (
                    f"{count} of {len(prices)} items have the same price "
                    f"(${most_common_price})"
                )

        # Check 2: Too many duplicate item names
        names = [item.get("name", "").upper().strip() for item in items]
        unique_names = set(names)
        if len(names) >= 5 and len(unique_names) < len(names) * 0.6:
            return (
                f"Too many duplicate items ({len(names)} items but only "
                f"{len(unique_names)} unique names)"
            )

        # Check 3: Generic item names (hallucination produces simple names
        # like "BREAD", "EGGS", "MILK" instead of receipt abbreviations)
        generic_names = {
            "BREAD", "EGGS", "MILK", "BUTTER", "CHEESE", "RICE",
            "PASTA", "PIZZA", "ICE CREAM", "CHICKEN", "BEEF",
            "PORK", "FISH", "APPLE", "BANANA", "ORANGE",
            "TOMATO", "POTATO", "ONION", "LETTUCE", "CUCUMBER",
            "CUECUMBER",  # common misspelling in hallucinations
        }
        generic_count = sum(
            1 for name in names if name in generic_names
        )
        # If >50% of items are simple generic names, likely hallucinated
        if len(names) >= 8 and generic_count / len(names) > 0.5:
            return (
                f"{generic_count} of {len(names)} items are generic names — "
                f"receipt text was likely not readable"
            )

        return None

    def _parse_vision_response(self, data):
        """Parse Vision API JSON response into ReceiptVisionResult."""
        items = []
        for item in data.get("items", []):
            name = item.get("name", "").strip()
            if not name:
                continue
            items.append(
                {
                    "name": name,
                    "quantity": item.get("quantity", 1),
                    "price": item.get("price"),
                    "category": item.get("category", "other"),
                }
            )

        # Reconstruct raw text for storage
        raw_lines = []
        store = data.get("store", "")
        if store:
            raw_lines.append(store)
        date_str = data.get("date", "")
        if date_str:
            raw_lines.append(date_str)
        raw_lines.append("")
        for item in items:
            price_str = f"${item['price']:.2f}" if item.get("price") else ""
            raw_lines.append(f"{item['name']}    {price_str}")
        total = data.get("total")
        if total is not None:
            raw_lines.append(f"\nTOTAL    ${total:.2f}" if isinstance(total, (int, float)) else f"\nTOTAL    {total}")

        # Normalize payment method
        payment_method = data.get("payment_method", "")
        valid_methods = {"cash", "credit", "debit", "ebt", "mobile", "other"}
        if payment_method not in valid_methods:
            payment_method = ""

        return ReceiptVisionResult(
            receipt_type=data.get("receipt_type", "unknown"),
            store=store,
            date=date_str or None,
            items=items,
            subtotal=_safe_decimal(data.get("subtotal")),
            tax=_safe_decimal(data.get("tax")),
            total=_safe_decimal(data.get("total")),
            raw_text="\n".join(raw_lines),
            source="vision_api",
            payment_method=payment_method,
        )


def _safe_decimal(value):
    """Convert a value to Decimal safely, returning None on failure."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
