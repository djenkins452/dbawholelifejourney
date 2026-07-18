"""
Receipt Parsing Service

Parses grocery receipt text (from OCR) into structured items and matches them to
canonical ingredients. Pantry writes are performed by the confirmation-gated
ReceiptRoutingService (via finalize_pantry_item) — this module only parses/matches.

Uses the existing scan app's OCR capabilities as input.
"""

import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional

from .ingredient_matching import match_ingredient_name

logger = logging.getLogger(__name__)


@dataclass
class ParsedReceiptItem:
    """A single item parsed from a receipt."""
    raw_name: str
    quantity: Decimal
    unit: str
    price: Optional[Decimal]
    ingredient_match: Optional[object] = None  # IngredientMatch


@dataclass
class ParsedReceipt:
    """Complete parsed receipt."""
    store: str
    date: Optional[str]
    items: list
    total: Optional[Decimal]
    raw_text: str


def parse_receipt_text(raw_text: str) -> ParsedReceipt:
    """
    Parse raw OCR text from a grocery receipt into structured data.

    Handles common receipt formats:
    - Item name followed by price
    - Quantity x price patterns
    - Subtotal/total lines
    """
    lines = raw_text.strip().splitlines()
    items = []
    store = ""
    receipt_date = None
    total = None

    # Try to detect store name (usually first non-empty line)
    for line in lines[:3]:
        line = line.strip()
        if line and not _is_price_line(line):
            store = line
            break

    # Try to detect date
    for line in lines[:10]:
        date_match = re.search(
            r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            line,
        )
        if date_match:
            receipt_date = date_match.group(1)
            break

    # Parse line items
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Skip non-item lines
        if _is_header_line(line) or _is_footer_line(line):
            continue

        # Check for total line
        total_match = re.match(
            r"(?:total|grand total|amount due|balance)\s*[:\$]?\s*(\d+\.\d{2})",
            line,
            re.IGNORECASE,
        )
        if total_match:
            try:
                total = Decimal(total_match.group(1))
            except InvalidOperation:
                pass
            continue

        # Try to parse as item line
        parsed = _parse_item_line(line)
        if parsed:
            items.append(parsed)

    return ParsedReceipt(
        store=store,
        date=receipt_date,
        items=items,
        total=total,
        raw_text=raw_text,
    )


def _is_price_line(line: str) -> bool:
    """Check if a line is just a price."""
    return bool(re.match(r"^\$?\d+\.\d{2}$", line.strip()))


def _is_header_line(line: str) -> bool:
    """Check if a line is a receipt header."""
    lower = line.lower()
    return any(kw in lower for kw in [
        "receipt", "store #", "cashier", "register",
        "welcome", "thank you", "phone", "address",
    ])


def _is_footer_line(line: str) -> bool:
    """Check if a line is a receipt footer."""
    lower = line.lower()
    return any(kw in lower for kw in [
        "subtotal", "tax", "change", "tender", "visa",
        "mastercard", "debit", "credit", "savings",
        "you saved", "member", "rewards", "coupon",
    ])


def _parse_item_line(line: str) -> Optional[ParsedReceiptItem]:
    """
    Parse a single receipt line into an item.

    Common patterns:
    - "CHICKEN BREAST    5.99"
    - "2 x BANANAS    1.98"
    - "ORGANIC MILK 1GAL    4.99 F"
    """
    # Pattern: qty x item  price
    qty_pattern = re.match(
        r"^(\d+)\s*[xX]\s+(.+?)\s+\$?(\d+\.\d{2})\s*[A-Z]?$",
        line,
    )
    if qty_pattern:
        try:
            qty = Decimal(qty_pattern.group(1))
            name = qty_pattern.group(2).strip()
            price = Decimal(qty_pattern.group(3))
            return ParsedReceiptItem(
                raw_name=name,
                quantity=qty,
                unit="piece",
                price=price,
            )
        except (InvalidOperation, ValueError):
            pass

    # Pattern: item  price
    item_pattern = re.match(
        r"^(.+?)\s{2,}\$?(\d+\.\d{2})\s*[A-Z]?$",
        line,
    )
    if item_pattern:
        name = item_pattern.group(1).strip()
        # Skip if name is too short or looks like a code
        if len(name) > 2 and not re.match(r"^\d+$", name):
            try:
                price = Decimal(item_pattern.group(2))
                return ParsedReceiptItem(
                    raw_name=name,
                    quantity=Decimal("1"),
                    unit="piece",
                    price=price,
                )
            except InvalidOperation:
                pass

    return None


def match_receipt_items(parsed_receipt: ParsedReceipt) -> list:
    """
    Match parsed receipt items to canonical ingredients.

    Returns list of (ParsedReceiptItem, IngredientMatch) tuples.
    """
    results = []
    for item in parsed_receipt.items:
        match = match_ingredient_name(item.raw_name)
        item.ingredient_match = match
        results.append((item, match))
    return results
