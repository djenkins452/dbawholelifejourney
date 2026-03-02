"""
Unit conversion and normalization for ingredient parsing.

Handles common cooking unit aliases and conversions to a standard form.
"""

import re
from decimal import Decimal, InvalidOperation
from typing import Optional

# Map of common unit aliases to canonical unit codes
UNIT_ALIASES = {
    # Volume
    "tsp": "tsp",
    "teaspoon": "tsp",
    "teaspoons": "tsp",
    "t": "tsp",
    "tbsp": "tbsp",
    "tablespoon": "tbsp",
    "tablespoons": "tbsp",
    "tbs": "tbsp",
    "tb": "tbsp",
    "fl oz": "fl_oz",
    "fluid ounce": "fl_oz",
    "fluid ounces": "fl_oz",
    "cup": "cup",
    "cups": "cup",
    "c": "cup",
    "ml": "ml",
    "milliliter": "ml",
    "milliliters": "ml",
    "millilitre": "ml",
    "millilitres": "ml",
    "l": "l",
    "liter": "l",
    "liters": "l",
    "litre": "l",
    "litres": "l",
    "pint": "cup",  # 1 pint = 2 cups, but normalize to cup
    "pints": "cup",
    "pt": "cup",
    "quart": "l",
    "quarts": "l",
    "qt": "l",
    "gallon": "l",
    "gallons": "l",
    "gal": "l",
    # Weight
    "g": "g",
    "gram": "g",
    "grams": "g",
    "oz": "oz",
    "ounce": "oz",
    "ounces": "oz",
    "lb": "lb",
    "lbs": "lb",
    "pound": "lb",
    "pounds": "lb",
    "kg": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "kilo": "kg",
    "kilos": "kg",
    # Count/misc
    "piece": "piece",
    "pieces": "piece",
    "pc": "piece",
    "pcs": "piece",
    "each": "piece",
    "whole": "piece",
    "slice": "slice",
    "slices": "slice",
    "clove": "clove",
    "cloves": "clove",
    "bunch": "bunch",
    "bunches": "bunch",
    "sprig": "sprig",
    "sprigs": "sprig",
    "pinch": "pinch",
    "pinches": "pinch",
    "dash": "dash",
    "dashes": "dash",
    "can": "can",
    "cans": "can",
    "jar": "jar",
    "jars": "jar",
    "package": "package",
    "packages": "package",
    "pkg": "package",
    "pkgs": "package",
    "stick": "piece",
    "sticks": "piece",
    "head": "piece",
    "heads": "piece",
    "large": "piece",
    "medium": "piece",
    "small": "piece",
    "to taste": "to_taste",
    "as needed": "as_needed",
}

# Fraction mapping for unicode and text fractions
FRACTION_MAP = {
    "\u00bc": Decimal("0.25"),   # ¼
    "\u00bd": Decimal("0.5"),    # ½
    "\u00be": Decimal("0.75"),   # ¾
    "\u2153": Decimal("0.333"),  # ⅓
    "\u2154": Decimal("0.667"),  # ⅔
    "\u2155": Decimal("0.2"),    # ⅕
    "\u2156": Decimal("0.4"),    # ⅖
    "\u2157": Decimal("0.6"),    # ⅗
    "\u2158": Decimal("0.8"),    # ⅘
    "\u2159": Decimal("0.167"),  # ⅙
    "\u215a": Decimal("0.833"),  # ⅚
    "\u215b": Decimal("0.125"),  # ⅛
    "\u215c": Decimal("0.375"),  # ⅜
    "\u215d": Decimal("0.625"),  # ⅝
    "\u215e": Decimal("0.875"),  # ⅞
}

# Conversion factors to base unit (grams for weight, ml for volume)
WEIGHT_TO_GRAMS = {
    "g": Decimal("1"),
    "oz": Decimal("28.3495"),
    "lb": Decimal("453.592"),
    "kg": Decimal("1000"),
}

VOLUME_TO_ML = {
    "ml": Decimal("1"),
    "tsp": Decimal("4.929"),
    "tbsp": Decimal("14.787"),
    "fl_oz": Decimal("29.574"),
    "cup": Decimal("236.588"),
    "l": Decimal("1000"),
}


def normalize_unit(text: str) -> Optional[str]:
    """Convert a unit string to its canonical form."""
    cleaned = text.strip().lower().rstrip(".")
    return UNIT_ALIASES.get(cleaned)


def parse_quantity(text: str) -> Optional[Decimal]:
    """
    Parse a quantity string into a Decimal.

    Handles:
    - Simple numbers: "2", "0.5"
    - Fractions: "1/2", "3/4"
    - Mixed numbers: "1 1/2", "2 3/4"
    - Unicode fractions: "½", "¼"
    - Ranges: "2-3" (takes average)
    """
    text = text.strip()
    if not text:
        return None

    # Check for unicode fractions
    for char, value in FRACTION_MAP.items():
        if char in text:
            # Mixed number with unicode fraction: "1½"
            prefix = text.replace(char, "").strip()
            if prefix:
                try:
                    return Decimal(prefix) + value
                except InvalidOperation:
                    return value
            return value

    # Range: "2-3" → average
    range_match = re.match(r"^(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)$", text)
    if range_match:
        low = Decimal(range_match.group(1))
        high = Decimal(range_match.group(2))
        return (low + high) / 2

    # Mixed number: "1 1/2"
    mixed_match = re.match(r"^(\d+)\s+(\d+)/(\d+)$", text)
    if mixed_match:
        whole = Decimal(mixed_match.group(1))
        num = Decimal(mixed_match.group(2))
        den = Decimal(mixed_match.group(3))
        if den != 0:
            return whole + (num / den)
        return whole

    # Simple fraction: "1/2"
    frac_match = re.match(r"^(\d+)/(\d+)$", text)
    if frac_match:
        num = Decimal(frac_match.group(1))
        den = Decimal(frac_match.group(2))
        if den != 0:
            return num / den
        return None

    # Simple decimal or integer
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def convert_to_grams(quantity: Decimal, unit: str) -> Optional[Decimal]:
    """Convert a weight quantity to grams."""
    factor = WEIGHT_TO_GRAMS.get(unit)
    if factor:
        return quantity * factor
    return None


def convert_to_ml(quantity: Decimal, unit: str) -> Optional[Decimal]:
    """Convert a volume quantity to milliliters."""
    factor = VOLUME_TO_ML.get(unit)
    if factor:
        return quantity * factor
    return None


def is_weight_unit(unit: str) -> bool:
    return unit in WEIGHT_TO_GRAMS


def is_volume_unit(unit: str) -> bool:
    return unit in VOLUME_TO_ML
