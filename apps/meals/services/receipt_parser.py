"""
Receipt Parsing Service

Parses grocery receipt text (from OCR) into structured items,
matches them to ingredients, and updates pantry inventory.

Uses the existing scan app's OCR capabilities as input.
"""

import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional

from .ingredient_matching import get_or_create_ingredient, match_ingredient_name

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


def process_receipt_to_pantry(receipt_model, household):
    """
    Process a saved Receipt into PantryItem updates.

    1. Parse the receipt text
    2. Match items to ingredients
    3. Create/update PantryItems
    4. Log InventoryTransactions
    """
    from django.utils import timezone as tz

    from apps.meals.models import (
        Ingredient,
        InventoryTransaction,
        PantryItem,
        ReceiptItem,
    )

    parsed = parse_receipt_text(receipt_model.raw_text)
    matched = match_receipt_items(parsed)

    created_items = 0
    updated_items = 0

    for parsed_item, match in matched:
        if match.ingredient_id:
            ingredient = Ingredient.objects.get(pk=match.ingredient_id)
        elif match.confidence == Decimal("0"):
            # No match — create new ingredient
            ingredient = get_or_create_ingredient(parsed_item.raw_name)
        else:
            ingredient = Ingredient.objects.get(pk=match.ingredient_id)

        # Save ReceiptItem
        ReceiptItem.objects.create(
            receipt=receipt_model,
            ingredient=ingredient,
            raw_name=parsed_item.raw_name,
            raw_price=parsed_item.price,
            quantity=parsed_item.quantity,
            unit=parsed_item.unit,
            match_confidence=match.confidence,
        )

        # Update or create PantryItem
        pantry_item, created = PantryItem.objects.get_or_create(
            household=household,
            ingredient=ingredient,
            defaults={
                "quantity": parsed_item.quantity,
                "unit": parsed_item.unit,
                "confidence_score": Decimal("0.95"),
                "last_confirmed_at": tz.now(),
            },
        )

        if not created:
            pantry_item.quantity += parsed_item.quantity
            pantry_item.confidence_score = Decimal("0.95")
            pantry_item.last_confirmed_at = tz.now()
            pantry_item.save(update_fields=[
                "quantity", "confidence_score", "last_confirmed_at", "updated_at",
            ])
            updated_items += 1
        else:
            created_items += 1
            # Set estimated expiration
            if ingredient.shelf_life_days:
                pantry_item.expiration_date_estimated = (
                    tz.now().date() + tz.timedelta(days=ingredient.shelf_life_days)
                )
                pantry_item.save(update_fields=["expiration_date_estimated"])

        # Log transaction
        InventoryTransaction.objects.create(
            pantry_item=pantry_item,
            delta_quantity=parsed_item.quantity,
            source="receipt",
            notes=f"From receipt: {receipt_model.store or 'Unknown Store'}",
        )

    # Update receipt with parsed data
    receipt_model.parsed_json = {
        "store": parsed.store,
        "date": parsed.date,
        "item_count": len(parsed.items),
        "matched_count": sum(1 for _, m in matched if m.ingredient_id),
        "total": str(parsed.total) if parsed.total else None,
    }
    receipt_model.store = parsed.store or receipt_model.store
    receipt_model.save(update_fields=["parsed_json", "store", "updated_at"])

    logger.info(
        f"Processed receipt {receipt_model.id}: "
        f"{created_items} new, {updated_items} updated pantry items"
    )
    return created_items, updated_items
