"""
Medication acquisition — Confidence Engine (Sprint 3C).

Deterministic, explainable confidence for an acquired medication record, at two
levels: per-field and overall. Confidence is NOT truth — it expresses how much we
should trust each acquired value before (and after) the user confirms.

Principles (Medication Intelligence Canon):
  - User confirmation is the strongest evidence: a manually-entered or user-edited
    field is high-confidence (the user stated it intentionally).
  - OCR/Vision is a candidate, never truth: extracted fields carry the extraction's
    own confidence, or a conservative source default.
  - Absence is not low confidence: a missing field is ``None`` (no observation),
    never 0.0 — we never fabricate a value or a false-confident zero.
"""

# Canonical acquirable fields and their weight toward OVERALL confidence.
# Name + dose dominate (a record is only trustworthy if we know WHAT and HOW MUCH).
FIELD_WEIGHTS = {
    "name": 0.30,
    "dose": 0.22,
    "frequency": 0.13,
    "sig": 0.08,
    "strength": 0.07,
    "provider": 0.05,
    "pharmacy": 0.04,
    "quantity": 0.03,
    "expiration": 0.03,
    "refills": 0.02,
    "purpose": 0.02,
    "ndc": 0.01,
}
CRITICAL_FIELDS = ("name", "dose")

# Source-default per-field confidence when the acquisition method gives no
# per-field confidence of its own.
SOURCE_DEFAULT_CONFIDENCE = {
    "manual": 0.95,          # user typed it intentionally
    "bottle_image": 0.60,    # vision candidate — needs review
    "pharmacy_label": 0.70,
    "pharmacy_pdf": 0.75,
    "med_list": 0.65,
    "provider_export": 0.85,
    "fhir": 0.90,            # structured clinical source
    "pharmacy_api": 0.90,
}

HIGH = 0.85
MEDIUM = 0.55


def compute_field_confidences(extracted_values, source, *, extraction_confidences=None,
                              user_edited_fields=None):
    """Return {field: confidence 0..1} for every present field.

    A field present in ``extracted_values`` (non-empty) gets:
      - 0.97 if the user edited/entered it during review (user_edited_fields),
      - else its extraction confidence (extraction_confidences[field]) if given,
      - else the source default.
    Absent/empty fields are omitted entirely (absence ≠ low confidence).
    """
    extraction_confidences = extraction_confidences or {}
    user_edited_fields = set(user_edited_fields or ())
    default = SOURCE_DEFAULT_CONFIDENCE.get(source, MEDIUM)

    out = {}
    for field, value in (extracted_values or {}).items():
        if value in (None, "", []):
            continue  # absence — no confidence entry
        if field in user_edited_fields:
            out[field] = 0.97
        elif field in extraction_confidences and extraction_confidences[field] is not None:
            out[field] = round(float(extraction_confidences[field]), 2)
        else:
            out[field] = default
    return out


def compute_overall_confidence(field_confidences, *, has_existing_match=False,
                               user_confirmed=False):
    """Compose an overall 0..1 confidence for the whole record.

    Weighted average over PRESENT fields (by FIELD_WEIGHTS), then:
      - penalize missing critical fields (no name → cap 0.30; no dose → ×0.70),
      - +0.05 if it corroborates an existing tracked medication,
      - lift to ≥0.97 once the user has confirmed (confirmation is the strongest
        evidence).
    Returns None when there is nothing to score.
    """
    fc = field_confidences or {}
    present = {f: c for f, c in fc.items() if f in FIELD_WEIGHTS and c is not None}
    if not present:
        return 1.0 if user_confirmed else None

    weight_sum = sum(FIELD_WEIGHTS[f] for f in present)
    score = sum(FIELD_WEIGHTS[f] * present[f] for f in present) / weight_sum

    if "name" not in present:
        score = min(score, 0.30)
    if "dose" not in present:
        score *= 0.70
    if has_existing_match:
        score = min(1.0, score + 0.05)
    if user_confirmed:
        score = max(score, 0.97)

    return round(min(1.0, max(0.0, score)), 2)


def missing_fields(extracted_values, *, intake_type="medication"):
    """List the canonical fields that were NOT acquired (drives the review's
    'needs confirmation / missing information' affordance, Sprint 3D)."""
    present = {
        f for f, v in (extracted_values or {}).items() if v not in (None, "", [])
    }
    # Supplements have no prescriber/Rx context — don't flag those as "missing".
    relevant = set(FIELD_WEIGHTS)
    if intake_type == "supplement":
        relevant -= {"provider", "refills", "sig"}
    return sorted(relevant - present)


def confidence_band(confidence):
    """Map a 0..1 confidence to a review band (Sprint 3D highlighting)."""
    if confidence is None:
        return "missing"
    if confidence >= HIGH:
        return "high"
    if confidence >= MEDIUM:
        return "medium"
    return "needs_confirmation"
