"""
Storage Location Classifier

Determines where a food item should be stored based on product name and category.
Supports user overrides which are saved for future classification.

Locations:
    pantry  — shelf-stable goods (rice, pasta, cans, spices)
    fridge  — refrigerated items (milk, eggs, produce, condiments)
    freezer — frozen items (frozen pizza, ice cream, frozen vegetables)
    other   — non-food or supplement items
    unknown — confidence too low to determine
"""

import logging
import re

logger = logging.getLogger(__name__)

# Storage location constants
PANTRY = "pantry"
FRIDGE = "fridge"
FREEZER = "freezer"
OTHER = "other"
UNKNOWN = "unknown"

STORAGE_CHOICES = [
    (PANTRY, "Pantry"),
    (FRIDGE, "Fridge"),
    (FREEZER, "Freezer"),
    (OTHER, "Other"),
    (UNKNOWN, "Unknown"),
]

# ─── Keyword rules ───────────────────────────────────────────────────────
# Each entry is (pattern, location). Patterns are matched case-insensitively
# against the product name. Order matters: first match wins, so more specific
# patterns (like "frozen") should come before generic ones.

_FREEZER_KEYWORDS = [
    r"\bfrozen\b",
    r"\bice cream\b",
    r"\bgelato\b",
    r"\bsorbet\b",
    r"\bpopsicle\b",
    r"\bfreezer\b",
    r"\bfrost(?:ed|y)?\b",
    r"\bfrozen pizza\b",
    r"\bfrozen meal\b",
    r"\bfrozen dinner\b",
    r"\bfrozen vegetable",
    r"\bfrozen fruit",
    r"\bfrozen meat",
    r"\bfrozen chicken",
    r"\bfrozen fish",
    r"\bfrozen shrimp",
    r"\bfrozen waffle",
    r"\bfrozen burrito",
    r"\btv dinner",
    r"\bfrozen entr",
    r"\bfrozen bread",
    r"\bfrozen dough",
]

_FRIDGE_KEYWORDS = [
    r"\bmilk\b",
    r"\bcheese\b",
    r"\byogurt\b",
    r"\bkefir\b",
    r"\bcottage cheese\b",
    r"\bcream cheese\b",
    r"\bsour cream\b",
    r"\bbutter\b",
    r"\bmargarine\b",
    r"\beggs?\b",
    r"\bjuice\b",
    r"\bfresh\b",
    r"\blettuce\b",
    r"\bsalad\b",
    r"\bspinach\b",
    r"\bkale\b",
    r"\bbroccoli\b",
    r"\bcauliflower\b",
    r"\bcarrots?\b",
    r"\bcelery\b",
    r"\bcucumber\b",
    r"\btomato(?:es)?\b",
    r"\bbell pepper",
    r"\bberries\b",
    r"\bstrawberr",
    r"\bblueberr",
    r"\braspberr",
    r"\bgrapes?\b",
    r"\bapples?\b",
    r"\boranges?\b",
    r"\blemons?\b",
    r"\blimes?\b",
    r"\bbananas?\b",  # debatable, but fridge extends life
    r"\bavocado",
    r"\bhummus\b",
    r"\bdeli\b",
    r"\blunch meat",
    r"\bham\b",
    r"\bturkey\b",
    r"\bchicken\b(?!.*(?:stock|broth|soup|ramen|noodle|can))",
    r"\bsteak\b",
    r"\bground beef\b",
    r"\bsausage\b",
    r"\bbacon\b",
    r"\bsalami\b",
    r"\btofu\b",
    r"\btempeh\b",
    r"\bcondiment",
    r"\bmayo(?:nnaise)?\b",
    r"\bketchup\b",
    r"\bmustard\b",
    r"\brelish\b",
    r"\bsalsa\b",
    r"\bpickle",
    r"\bolives?\b",
    r"\bcapers?\b",
    r"\bjam\b",
    r"\bjelly\b",
    r"\bpreserves\b",
    r"\bcreamer\b",
    r"\bhalf.and.half\b",
    r"\bheavy cream\b",
    r"\bwhipping cream\b",
]

_PANTRY_KEYWORDS = [
    r"\brice\b",
    r"\bpasta\b",
    r"\bnoodle",
    r"\bspaghetti\b",
    r"\bmacaroni\b",
    r"\bpenne\b",
    r"\bcereal\b",
    r"\boatmeal\b",
    r"\boats\b",
    r"\bgranola\b",
    r"\bchips?\b",
    r"\bcrackers?\b",
    r"\bpretzels?\b",
    r"\bpopcorn\b",
    r"\bcanned?\b",
    r"\bcan of\b",
    r"\bcans? of\b",
    r"\bsoup\b(?!.*fresh)",
    r"\bbroth\b",
    r"\bstock\b",
    r"\bsauce\b(?!.*fresh)",
    r"\bketchup\b",
    r"\bsoy sauce\b",
    r"\bhot sauce\b",
    r"\bbbq sauce\b",
    r"\bpasta sauce\b",
    r"\btomato sauce\b",
    r"\bmarinara\b",
    r"\bspice",
    r"\bseasoning",
    r"\bsalt\b",
    r"\bpepper\b",
    r"\bgarlic powder\b",
    r"\bonion powder\b",
    r"\bpaprika\b",
    r"\bcinnamon\b",
    r"\bcumin\b",
    r"\bturmeric\b",
    r"\boregano\b",
    r"\bbasil\b(?!.*fresh)",
    r"\bthyme\b",
    r"\bflour\b",
    r"\bsugar\b",
    r"\bbaking soda\b",
    r"\bbaking powder\b",
    r"\bvanilla\b",
    r"\byeast\b",
    r"\bcornstarch\b",
    r"\bbeans?\b",
    r"\blentils?\b",
    r"\bchickpeas?\b",
    r"\bpeanut butter\b",
    r"\balmond butter\b",
    r"\bnutella\b",
    r"\bhoney\b",
    r"\bsyrup\b",
    r"\bmolasses\b",
    r"\boil\b",
    r"\bolive oil\b",
    r"\bvegetable oil\b",
    r"\bcanola oil\b",
    r"\bcoconut oil\b",
    r"\bvinegar\b",
    r"\bbread\b",
    r"\btortilla",
    r"\bwrap\b",
    r"\bpita\b",
    r"\bprotein bar",
    r"\bgranola bar",
    r"\benergy bar",
    r"\bsnack bar",
    r"\bnuts?\b",
    r"\balmonds?\b",
    r"\bwalnuts?\b",
    r"\bpeanuts?\b",
    r"\bcashews?\b",
    r"\bseeds?\b",
    r"\btrail mix\b",
    r"\bdried\b",
    r"\braisins?\b",
    r"\bcranberr(?:y|ies)\b(?!.*fresh)",
    r"\bchocolate\b",
    r"\bcandy\b",
    r"\bcookies?\b",
    r"\bcoffee\b",
    r"\btea\b(?!.*iced)",
    r"\bcocoa\b",
    r"\bwater\b",
    r"\bsoda\b",
    r"\benergy drink",
    r"\bsport drink",
    r"\bprotein powder\b",
    r"\bwhey\b",
    r"\bcreatine\b",
]

_OTHER_KEYWORDS = [
    r"\bsupplement",
    r"\bvitamin",
    r"\bpet food\b",
    r"\bdog food\b",
    r"\bcat food\b",
    r"\bcat litter\b",
    r"\bdetergent\b",
    r"\bbleach\b",
    r"\bpaper towel",
    r"\btoilet paper\b",
    r"\btrash bag",
    r"\bgarbage bag",
    r"\bsoap\b",
    r"\bshampoo\b",
    r"\bdeodorant\b",
    r"\btoothpaste\b",
    r"\bbattery\b",
    r"\bbatteries\b",
    r"\blight bulb",
]

# Category-based classification (from Ingredient.CATEGORY_CHOICES or OFF categories)
_CATEGORY_MAP = {
    # Ingredient categories
    "dairy": FRIDGE,
    "protein": FRIDGE,
    "vegetable": FRIDGE,
    "fruit": FRIDGE,
    "grain": PANTRY,
    "spice": PANTRY,
    "condiment": FRIDGE,
    "beverage": PANTRY,
    "legume": PANTRY,
    "nut": PANTRY,
    "sweetener": PANTRY,
    "baking": PANTRY,
    "fat": PANTRY,
    "other": UNKNOWN,
    # Open Food Facts broad categories
    "frozen": FREEZER,
    "frozen foods": FREEZER,
    "frozen meals": FREEZER,
    "canned": PANTRY,
    "canned foods": PANTRY,
    "snacks": PANTRY,
    "cereals": PANTRY,
    "fresh": FRIDGE,
    "meats": FRIDGE,
    "seafood": FRIDGE,
    "produce": FRIDGE,
}


def determine_storage_location(product_name, category=""):
    """
    Determine where a food item should be stored.

    Args:
        product_name: Product name / ingredient name (e.g. "Organic Whole Milk")
        category: Optional category string from product API or ingredient model

    Returns:
        str: One of 'pantry', 'fridge', 'freezer', 'other', 'unknown'
    """
    if not product_name:
        return UNKNOWN

    name_lower = product_name.lower().strip()

    # Check user overrides first
    override = _check_user_override(name_lower)
    if override:
        return override

    # 1. Keyword matching (most specific → most general)
    #    Freezer first because "frozen chicken" should be freezer, not fridge
    for pattern in _FREEZER_KEYWORDS:
        if re.search(pattern, name_lower, re.IGNORECASE):
            return FREEZER

    for pattern in _OTHER_KEYWORDS:
        if re.search(pattern, name_lower, re.IGNORECASE):
            return OTHER

    for pattern in _FRIDGE_KEYWORDS:
        if re.search(pattern, name_lower, re.IGNORECASE):
            return FRIDGE

    for pattern in _PANTRY_KEYWORDS:
        if re.search(pattern, name_lower, re.IGNORECASE):
            return PANTRY

    # 2. Category-based fallback
    if category:
        cat_lower = category.lower().strip()
        location = _CATEGORY_MAP.get(cat_lower)
        if location and location != UNKNOWN:
            return location

    # 3. No confident match
    return UNKNOWN


def _check_user_override(name_lower):
    """
    Check if there's a user-defined storage override for this product name.
    Returns the stored location or None.
    """
    try:
        from apps.meals.models import StorageOverride

        override = StorageOverride.objects.filter(
            product_name_lower=name_lower
        ).first()
        if override:
            return override.storage_location
    except Exception:
        pass  # Model may not exist yet during migrations
    return None


def save_user_override(product_name, storage_location, user=None):
    """
    Save a user's storage location choice for future classification.

    This creates a global override that improves classification for all users.
    """
    from apps.meals.models import StorageOverride

    name_lower = product_name.lower().strip()
    StorageOverride.objects.update_or_create(
        product_name_lower=name_lower,
        defaults={
            "storage_location": storage_location,
            "product_name_display": product_name.strip(),
            "set_by": user,
        },
    )
    logger.info(
        "Storage override saved: '%s' → %s (by user %s)",
        product_name,
        storage_location,
        user,
    )
