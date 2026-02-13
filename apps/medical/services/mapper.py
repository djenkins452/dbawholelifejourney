"""
Maps parsed lab results to LabTestCatalog entries.

Hybrid Mode C: alias matching first, auto-create on miss.
"""

import logging
import re
import unicodedata

from apps.medical.models import LabTestAlias, LabTestCatalog

logger = logging.getLogger(__name__)


def normalize_test_name(raw_name: str) -> str:
    """
    Normalize a raw test name for alias lookup.

    Steps:
        1. Casefold
        2. Strip whitespace
        3. Collapse internal whitespace
        4. Remove certain punctuation (keep /, -, %)
        5. Unicode normalize
    """
    if not raw_name:
        return ""

    name = raw_name.strip()
    name = unicodedata.normalize("NFKD", name)
    name = name.casefold()
    # Collapse whitespace
    name = re.sub(r'\s+', ' ', name)
    # Remove parentheses content like "(Calc)" but keep the core
    # Actually keep it — "(SGOT)" is useful for matching
    # Strip trailing/leading punctuation only
    name = name.strip(' ,.:;')

    return name


def map_to_catalog(raw_name: str) -> tuple[LabTestCatalog, bool]:
    """
    Map a raw test name to a canonical LabTestCatalog entry.

    Returns:
        (catalog_entry, was_created)
        - was_created=False if matched an existing alias
        - was_created=True if a new entry was auto-created
    """
    normalized = normalize_test_name(raw_name)
    if not normalized:
        raise ValueError("Empty test name cannot be mapped")

    # Try alias match
    try:
        alias = LabTestAlias.objects.select_related("canonical_test").get(alias=normalized)
        return (alias.canonical_test, False)
    except LabTestAlias.DoesNotExist:
        pass

    # Try some common variations
    variations = _generate_variations(normalized)
    for variation in variations:
        try:
            alias = LabTestAlias.objects.select_related("canonical_test").get(alias=variation)
            # Create alias for the original normalized name too
            LabTestAlias.objects.get_or_create(
                alias=normalized,
                defaults={"canonical_test": alias.canonical_test},
            )
            return (alias.canonical_test, False)
        except LabTestAlias.DoesNotExist:
            continue

    # No match — create new catalog entry
    display_name = raw_name.strip()
    catalog_entry = LabTestCatalog.objects.create(
        name=display_name,
        category="uncategorized",
        is_system_seeded=False,
        needs_review=True,
    )
    # Create self-alias
    LabTestAlias.objects.create(
        alias=normalized,
        canonical_test=catalog_entry,
    )

    logger.info("Auto-created catalog entry: '%s' (needs review)", display_name)
    return (catalog_entry, True)


def _generate_variations(normalized: str) -> list[str]:
    """Generate common name variations for matching."""
    variations = []

    # Remove leading/trailing "serum", "blood", "plasma", "urine"
    for suffix in [', serum', ', blood', ', plasma', ', urine', ' serum', ' blood']:
        if normalized.endswith(suffix):
            variations.append(normalized[:-len(suffix)])

    # Handle portal-style names like "sodium-na" -> "sodium" and "na"
    if '-' in normalized:
        parts = normalized.split('-')
        variations.extend(parts)
        # Also try without hyphen
        variations.append(normalized.replace('-', ' '))

    # Handle parenthetical abbreviations: "(sgot) ast" -> "ast (sgot)" and "ast" and "sgot"
    paren_match = re.match(r'^\(([^)]+)\)\s+(.+)$', normalized)
    if paren_match:
        abbr = paren_match.group(1)
        name = paren_match.group(2)
        variations.append(name)
        variations.append(abbr)
        variations.append(f"{name} ({abbr})")

    # "total bili" -> "bilirubin, total" and "total bilirubin"
    if normalized.startswith('total '):
        rest = normalized[6:]
        variations.append(f"{rest}, total")
        variations.append(f"{rest} total")

    # "hgb a1c" -> "hemoglobin a1c", "hba1c", "a1c"
    # "creatinine" -> "creat"
    # These should be handled by seed aliases

    # Portal names like "glucose level" -> "glucose"
    if normalized.endswith(' level'):
        variations.append(normalized[:-6])

    # "ca-corrected for alb" type names
    if 'corrected' in normalized:
        variations.append(normalized)  # Keep as is, will create new entry

    # "vldl calc" -> "vldl cholesterol (calc)"
    if normalized.endswith(' calc'):
        base = normalized[:-5]
        variations.append(f"{base} cholesterol (calc)")
        variations.append(f"{base} cholesterol")

    # "chol/hdl ratio" -> "total cholesterol/hdl ratio"
    if 'chol/' in normalized:
        variations.append(normalized.replace('chol/', 'cholesterol/'))
        variations.append(normalized.replace('chol/', 'total cholesterol/'))

    return [v for v in variations if v and v != normalized]


def guess_panel_type(panel_name: str) -> str:
    """Guess panel type from section/panel name."""
    if not panel_name:
        return "custom"

    name_lower = panel_name.lower()
    mappings = {
        "cbc": "cbc",
        "complete blood count": "cbc",
        "hematology": "cbc",
        "blood counts": "cbc",
        "diff": "cbc",
        "cmp": "cmp",
        "comprehensive metabolic": "cmp",
        "chem profiles": "cmp",
        "bmp": "bmp",
        "basic metabolic": "bmp",
        "lipid": "lipid",
        "lipids": "lipid",
        "thyroid": "thyroid",
        "a1c": "a1c",
        "hemoglobin a1c": "a1c",
        "diabetes": "a1c",
        "urinalysis": "urinalysis",
        "liver": "liver",
        "hepatic": "liver",
        "renal": "kidney",
        "kidney": "kidney",
        "inflammation": "inflammation",
        "cardiac": "cardiac",
        "coagulation": "coagulation",
        "iron": "iron",
        "vitamin": "vitamin",
        "hormone": "hormone",
        "calc values": "custom",
    }

    for key, panel_type in mappings.items():
        if key in name_lower:
            return panel_type

    return "custom"
