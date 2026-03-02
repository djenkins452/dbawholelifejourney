"""
Ingredient Parsing Service

Parses free-text ingredient lines (e.g., "2 cups diced chicken breast")
into structured data: quantity, unit, ingredient name, preparation notes.

Strategy: Deterministic regex parsing first, AI fallback for ambiguous cases.
"""

import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from .unit_conversion import UNIT_ALIASES, normalize_unit, parse_quantity

logger = logging.getLogger(__name__)


@dataclass
class ParsedIngredient:
    """Result of parsing a single ingredient line."""
    quantity: Optional[Decimal]
    unit: Optional[str]
    name: str
    preparation: str
    is_optional: bool
    confidence: Decimal
    original_text: str


# Preparation words that modify an ingredient (appear before or after name)
PREPARATION_WORDS = {
    "diced", "chopped", "minced", "sliced", "grated", "shredded",
    "julienned", "cubed", "crushed", "ground", "mashed", "melted",
    "softened", "sifted", "toasted", "roasted", "cooked", "uncooked",
    "raw", "fresh", "frozen", "thawed", "canned", "dried", "dehydrated",
    "peeled", "seeded", "deveined", "deboned", "boneless", "skinless",
    "bone-in", "skin-on", "trimmed", "halved", "quartered", "divided",
    "packed", "loosely packed", "firmly packed", "lightly beaten",
    "beaten", "whisked", "room temperature", "cold", "warm",
    "thinly sliced", "finely chopped", "finely minced", "roughly chopped",
    "coarsely chopped", "finely diced", "small dice", "medium dice",
    "large dice", "chiffonade",
}

# Words that indicate an ingredient is optional
OPTIONAL_MARKERS = {"optional", "if desired", "to garnish", "for garnish", "for serving"}

# Pattern for quantity at the start of a line
# Matches: "2", "1/2", "1 1/2", "0.5", unicode fractions
QUANTITY_PATTERN = re.compile(
    r"^"
    r"("
    r"\d+(?:\.\d+)?\s*[-–]\s*\d+(?:\.\d+)?"  # Range: "2-3" (MUST be before decimal/int)
    r"|\d+\s+\d+/\d+"      # Mixed: "1 1/2"
    r"|\d+/\d+"            # Fraction: "1/2"
    r"|\d+[\u00bc-\u00be\u2150-\u215e]"  # Mixed with unicode: "1½"
    r"|[\u00bc-\u00be\u2150-\u215e]"  # Unicode fractions
    r"|\d+(?:\.\d+)?"      # Decimal/int: "2", "0.5" (most general, last)
    r")"
    r"\s*",
    re.UNICODE,
)


def _extract_quantity(text: str) -> tuple[Optional[str], str]:
    """Extract quantity from the start of text. Returns (quantity_str, remaining)."""
    match = QUANTITY_PATTERN.match(text)
    if match:
        return match.group(1).strip(), text[match.end():].strip()
    return None, text


def _extract_unit(text: str) -> tuple[Optional[str], str]:
    """Extract unit from the start of text. Returns (canonical_unit, remaining)."""
    text_lower = text.lower()

    # Try multi-word units first (e.g., "fl oz", "to taste", "as needed")
    for alias in sorted(UNIT_ALIASES.keys(), key=len, reverse=True):
        if text_lower.startswith(alias):
            # Make sure it's a word boundary
            rest = text[len(alias):]
            if not rest or rest[0] in " \t.,;:)":
                canonical = UNIT_ALIASES[alias]
                remaining = rest.lstrip(" \t.,;:)")
                # Strip "of" after unit: "cups of flour"
                if remaining.lower().startswith("of "):
                    remaining = remaining[3:]
                return canonical, remaining.strip()

    return None, text


def _extract_preparation(name: str) -> tuple[str, str]:
    """
    Separate preparation notes from ingredient name.

    Returns (clean_name, preparation_notes).
    """
    preparations = []
    clean_parts = []

    # Check for parenthetical notes: "chicken breast (diced)"
    paren_match = re.search(r"\(([^)]+)\)", name)
    if paren_match:
        paren_content = paren_match.group(1).strip()
        preparations.append(paren_content)
        name = name[:paren_match.start()].strip() + " " + name[paren_match.end():].strip()
        name = name.strip()

    # Check for comma-separated preparation: "chicken breast, diced"
    if "," in name:
        parts = name.split(",")
        main_name = parts[0].strip()
        for part in parts[1:]:
            part = part.strip().lower()
            if any(prep in part for prep in PREPARATION_WORDS):
                preparations.append(part)
            else:
                # Could be part of the name: "salt, black pepper" scenario
                clean_parts.append(part)

        if clean_parts:
            name = main_name + ", " + ", ".join(clean_parts)
        else:
            name = main_name

    # Check for leading preparation words: "diced chicken breast"
    # Only strip if remaining name has 2+ words (to avoid stripping
    # compound names like "ground beef", "frozen peas")
    words = name.split()
    leading_preps = []
    remaining_words = []
    found_non_prep = False

    for word in words:
        word_lower = word.lower().rstrip(",")
        if not found_non_prep and word_lower in PREPARATION_WORDS:
            leading_preps.append(word_lower)
        else:
            found_non_prep = True
            remaining_words.append(word)

    # Only strip prep words if enough words remain (2+) to form a name
    if leading_preps and len(remaining_words) >= 2:
        preparations = leading_preps + preparations
        name = " ".join(remaining_words)
    elif leading_preps and remaining_words:
        # Single remaining word — keep the full name intact
        # "ground beef" stays as "ground beef", "diced onion" stays "diced onion"
        pass

    preparation_str = ", ".join(preparations)
    return name.strip(), preparation_str


def _check_optional(text: str) -> tuple[str, bool]:
    """Check if the ingredient is marked as optional."""
    text_lower = text.lower()
    is_optional = False

    for marker in OPTIONAL_MARKERS:
        # Check parenthetical: "(optional)"
        pattern = rf"\(\s*{re.escape(marker)}\s*\)"
        match = re.search(pattern, text_lower)
        if match:
            text = text[:match.start()].strip() + " " + text[match.end():].strip()
            is_optional = True
            break

        # Check trailing: ", optional"
        if text_lower.rstrip().endswith(marker):
            text = text[:-(len(marker))].rstrip(", ")
            is_optional = True
            break

    return text.strip(), is_optional


def parse_ingredient_line(text: str) -> ParsedIngredient:
    """
    Parse a single ingredient line into structured components.

    Examples:
        "2 cups diced chicken breast" →
            quantity=2, unit="cup", name="chicken breast", prep="diced"
        "1/2 tsp salt" →
            quantity=0.5, unit="tsp", name="salt", prep=""
        "salt and pepper to taste" →
            quantity=None, unit="to_taste", name="salt and pepper", prep=""
        "1 (14 oz) can diced tomatoes" →
            quantity=1, unit="can", name="diced tomatoes", prep=""
    """
    original = text.strip()
    if not original:
        return ParsedIngredient(
            quantity=None, unit=None, name="",
            preparation="", is_optional=False,
            confidence=Decimal("0"), original_text="",
        )

    working = original
    # Strip bullet/list prefixes
    working = re.sub(r"^[-\u2022*]\s*", "", working)
    confidence = Decimal("1.0")

    # Step 1: Check for optional markers
    working, is_optional = _check_optional(working)

    # Step 2: Handle "to taste" / "as needed" at the end
    working_lower = working.lower().strip()
    if working_lower.endswith("to taste"):
        name = working[:-len("to taste")].rstrip(", ").strip()
        return ParsedIngredient(
            quantity=None, unit="to_taste", name=name,
            preparation="", is_optional=is_optional,
            confidence=Decimal("0.95"), original_text=original,
        )
    if working_lower.endswith("as needed"):
        name = working[:-len("as needed")].rstrip(", ").strip()
        return ParsedIngredient(
            quantity=None, unit="as_needed", name=name,
            preparation="", is_optional=is_optional,
            confidence=Decimal("0.95"), original_text=original,
        )

    # Step 3: Extract quantity
    qty_str, working = _extract_quantity(working)
    quantity = parse_quantity(qty_str) if qty_str else None

    # Step 4: Handle parenthetical size: "1 (14 oz) can" pattern
    paren_size = re.match(r"^\((\d+(?:\.\d+)?)\s*([a-zA-Z.]+)\)\s*", working)
    if paren_size:
        # The parenthetical is a size modifier, skip it for now
        # and process what comes after as unit
        working = working[paren_size.end():]

    # Step 5: Extract unit
    unit, working = _extract_unit(working)

    # Step 6: Extract preparation notes from name
    name, preparation = _extract_preparation(working)

    # Step 7: Clean up the name
    name = re.sub(r"\s+", " ", name).strip()
    # Remove leading/trailing punctuation
    name = name.strip(".,;:-–")

    # Step 8: Compute confidence
    if not quantity and not unit:
        confidence = Decimal("0.60")  # Uncertain — just a name
    elif not quantity:
        confidence = Decimal("0.80")  # Have unit but no quantity
    elif not unit:
        confidence = Decimal("0.85")  # Have quantity but no unit (assume "piece")
        unit = "piece"

    if not name:
        confidence = Decimal("0.20")  # Very low — couldn't extract a name

    return ParsedIngredient(
        quantity=quantity,
        unit=unit,
        name=name.strip(),
        preparation=preparation,
        is_optional=is_optional,
        confidence=confidence,
        original_text=original,
    )


def parse_ingredient_block(text: str) -> list[ParsedIngredient]:
    """
    Parse a multi-line ingredient block (one ingredient per line).

    Skips blank lines and section headers (lines ending with ':').
    """
    results = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        # Skip section headers like "For the sauce:"
        if line.endswith(":"):
            continue
        # Skip bullet points/dashes and process content
        line = re.sub(r"^[-•*]\s*", "", line)
        if line:
            results.append(parse_ingredient_line(line))
    return results
