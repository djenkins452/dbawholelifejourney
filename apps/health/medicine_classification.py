"""
Canonical ingestible classification — the SINGLE SOURCE OF TRUTH for whether a tracked
Intake is a PRESCRIPTION medication, a SUPPLEMENT, or a WELLNESS / Nutrition product.

TRUST CONTRACT (origin: 2026-06-30 production review):
  - Medication Adherence counts ONLY prescription medications.
  - It MUST NEVER include supplements, vitamins, or wellness products.
  - A mixed metric is NEVER labeled "Medication Adherence" — it is "Health Routine
    Adherence".

FOUR canonical business categories (authoritative vocabulary — Layer 1 Medication Domain):
  - Prescription Medication = category 'prescription' + insulin (any subtype). "Medicine"
    means THIS and nothing else.
  - Supplement = vitamin / mineral / amino_acid / herbal / probiotic / hormonal. Never medicine.
  - OTC = category 'otc'. Its own business category — never medicine, never supplement.
  - Wellness = performance / other / anything else. Never medicine.

Strict by design: an uncategorized medication (category 'other') is Wellness, NOT
medicine — so a supplement/OTC can never leak into the medication number.
"""
from django.db.models import Q

PRESCRIPTION = "prescription"
SUPPLEMENT = "supplement"
OTC = "otc"
WELLNESS = "wellness"

CLASSIFICATIONS = (PRESCRIPTION, SUPPLEMENT, OTC, WELLNESS)

# Intake.category → bucket
_SUPPLEMENT_CATEGORIES = {"vitamin", "mineral", "amino_acid", "herbal", "probiotic", "hormonal"}
_WELLNESS_CATEGORIES = {"performance", "other"}

# DEFENSE-IN-DEPTH safety net (trust-critical): unambiguous supplement INGREDIENTS that
# must NEVER classify as prescription even when the data is mis-tagged category=prescription
# (production review 2026-06-30: "Fish Oil" + "Magnesium glycinate" appeared as Rx). Kept
# conservative — only ingredients that are supplements in essentially all forms. Insulin is
# checked first, so a real Rx is never caught here.
_SUPPLEMENT_NAME_TOKENS = (
    "fish oil", "fish-oil", "omega-3", "omega 3", "omega3", "magnesium", "glucosamine",
    "chondroitin", "probiotic", "melatonin", "biotin", "turmeric", "curcumin", "collagen",
    "coq10", "co q10", "ashwagandha", "elderberry", "psyllium",
    "milk thistle", "ginkgo", "saw palmetto",
)


def _name_says_supplement(intake):
    name = (getattr(intake, "name", "") or "").lower()
    return any(tok in name for tok in _SUPPLEMENT_NAME_TOKENS)


def classify_intake(intake):
    """Bucket a single Intake into PRESCRIPTION | SUPPLEMENT | OTC | WELLNESS. Insulin
    (any intake_subtype) is always a prescription medication; an unambiguous supplement
    INGREDIENT name can never be prescription (safety net for mis-tagged data)."""
    if (getattr(intake, "intake_subtype", None) or ""):
        return PRESCRIPTION
    if _name_says_supplement(intake):          # safety net — overrides a mis-tagged category
        return SUPPLEMENT
    cat = (getattr(intake, "category", "") or "").lower()
    if cat == "prescription":
        return PRESCRIPTION
    if cat == "otc":
        return OTC
    if cat in _SUPPLEMENT_CATEGORIES:
        return SUPPLEMENT
    if cat in _WELLNESS_CATEGORIES:
        return WELLNESS
    # Unmapped category → fall back to the coarse intake_type (never to prescription/OTC).
    return SUPPLEMENT if (getattr(intake, "intake_type", "") or "").lower() == "supplement" else WELLNESS


_HAS_INSULIN = Q(intake_subtype__isnull=False) & ~Q(intake_subtype="")
_NO_INSULIN = Q(intake_subtype__isnull=True) | Q(intake_subtype="")

# DB mirror of the supplement-name safety net — a name-says-supplement item is excluded
# from prescription/OTC and included in supplement, regardless of a mis-tagged category.
_NAME_SUPPLEMENT_Q = Q()
for _tok in _SUPPLEMENT_NAME_TOKENS:
    _NAME_SUPPLEMENT_Q |= Q(name__icontains=_tok)


def classification_q(classification):
    """A DB-side Q selecting Intakes of `classification`. None → all (Health Routine).
    Mirrors classify_intake exactly (incl. the supplement-name safety net) so the queryset
    and the per-object classifier always agree."""
    if classification is None:
        return Q()
    if classification == PRESCRIPTION:
        return (Q(category="prescription") & ~_NAME_SUPPLEMENT_Q) | _HAS_INSULIN
    if classification == OTC:
        return Q(category="otc") & ~_NAME_SUPPLEMENT_Q & _NO_INSULIN
    if classification == SUPPLEMENT:
        return (Q(category__in=_SUPPLEMENT_CATEGORIES) | _NAME_SUPPLEMENT_Q) & _NO_INSULIN
    if classification == WELLNESS:
        # Everything not prescription / OTC / supplement — including uncategorized.
        return (~Q(category="prescription") & ~Q(category="otc")
                & ~Q(category__in=_SUPPLEMENT_CATEGORIES) & ~_NAME_SUPPLEMENT_Q & _NO_INSULIN)
    raise ValueError(f"unknown classification: {classification!r}")
