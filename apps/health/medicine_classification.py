"""
Canonical ingestible classification — the SINGLE SOURCE OF TRUTH for whether a tracked
Intake is a PRESCRIPTION medication, a SUPPLEMENT, or a WELLNESS / Nutrition product.

TRUST CONTRACT (origin: 2026-06-30 production review):
  - Medication Adherence counts ONLY prescription medications.
  - It MUST NEVER include supplements, vitamins, or wellness products.
  - A mixed metric is NEVER labeled "Medication Adherence" — it is "Health Routine
    Adherence".

Decision (2026-06-30): Prescription = category 'prescription' + insulin (any subtype).
Supplement = vitamin / mineral / amino_acid / herbal / probiotic / hormonal.
Wellness/Nutrition = otc / performance / other. Strict: an uncategorized medication
(category 'other') is Wellness, NOT Medication Adherence — by design, so a supplement can
never leak into the medication number.
"""
from django.db.models import Q

PRESCRIPTION = "prescription"
SUPPLEMENT = "supplement"
WELLNESS = "wellness"

# Intake.category → bucket
_SUPPLEMENT_CATEGORIES = {"vitamin", "mineral", "amino_acid", "herbal", "probiotic", "hormonal"}
_WELLNESS_CATEGORIES = {"otc", "performance", "other"}


def classify_intake(intake):
    """Bucket a single Intake into PRESCRIPTION | SUPPLEMENT | WELLNESS. Insulin (any
    intake_subtype) is always a prescription medication."""
    if (getattr(intake, "intake_subtype", None) or ""):
        return PRESCRIPTION
    cat = (getattr(intake, "category", "") or "").lower()
    if cat == "prescription":
        return PRESCRIPTION
    if cat in _SUPPLEMENT_CATEGORIES:
        return SUPPLEMENT
    if cat in _WELLNESS_CATEGORIES:
        return WELLNESS
    # Unmapped category → fall back to the coarse intake_type (never to prescription).
    return SUPPLEMENT if (getattr(intake, "intake_type", "") or "").lower() == "supplement" else WELLNESS


_HAS_INSULIN = Q(intake_subtype__isnull=False) & ~Q(intake_subtype="")
_NO_INSULIN = Q(intake_subtype__isnull=True) | Q(intake_subtype="")


def classification_q(classification):
    """A DB-side Q selecting Intakes of `classification`. None → all (Health Routine).
    Mirrors classify_intake exactly so the queryset and the per-object classifier agree."""
    if classification is None:
        return Q()
    if classification == PRESCRIPTION:
        return Q(category="prescription") | _HAS_INSULIN
    if classification == SUPPLEMENT:
        return Q(category__in=_SUPPLEMENT_CATEGORIES) & _NO_INSULIN
    if classification == WELLNESS:
        return Q(category__in=_WELLNESS_CATEGORIES) & _NO_INSULIN
    raise ValueError(f"unknown classification: {classification!r}")
