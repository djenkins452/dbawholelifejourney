"""
Guided Capture profiles (Medication Acquisition V1 completion).

Deterministic per-product capture guidance — so the user never wonders "what
picture do you need?". These profiles drive a guided, multi-image capture SESSION
whose accumulated images merge into one combined extraction → the existing
acquisition pipeline (MedicationScanDraft → review → confirm). No pipeline change.
"""

# Each profile: ordered steps with a label, a short instruction, the "why", and
# whether the step is required (vs optional/skippable).
CAPTURE_PROFILES = {
    "prescription": {
        "title": "Prescription bottle",
        "intake_type": "medication",
        "steps": [
            {"key": "front", "label": "Front of bottle",
             "instruction": "Take a photo of the front of the bottle.",
             "why": "Identifies the medication.", "required": True},
            {"key": "pharmacy_label", "label": "Pharmacy label",
             "instruction": "Now the pharmacy label.",
             "why": "Has the dose, directions, prescriber, and Rx number.", "required": True},
            {"key": "other_side", "label": "Another side",
             "instruction": "One more side if anything was hard to read.",
             "why": "Fills in anything missed.", "required": False},
        ],
    },
    "supplement": {
        "title": "Supplement",
        "intake_type": "supplement",
        "steps": [
            {"key": "front", "label": "Front label",
             "instruction": "Take a photo of the front label.",
             "why": "Identifies the supplement.", "required": True},
            {"key": "supplement_facts", "label": "Supplement Facts",
             "instruction": "Now the Supplement Facts panel.",
             "why": "Has serving size and ingredients.", "required": True},
            {"key": "directions", "label": "Directions",
             "instruction": "The suggested-use / directions, if separate.",
             "why": "Helps set the schedule.", "required": False},
        ],
    },
    "otc": {
        "title": "OTC medication",
        "intake_type": "medication",
        "steps": [
            {"key": "front", "label": "Front",
             "instruction": "Take a photo of the front.",
             "why": "Identifies the product.", "required": True},
            {"key": "drug_facts", "label": "Drug Facts",
             "instruction": "Now the Drug Facts panel.",
             "why": "Has active ingredients and directions.", "required": True},
            {"key": "directions", "label": "Directions",
             "instruction": "The directions, if separate.",
             "why": "Helps set how it's taken.", "required": False},
        ],
    },
    "injection": {
        "title": "Injection pen",
        "intake_type": "medication",
        "steps": [
            {"key": "front", "label": "Pen / carton front",
             "instruction": "Take a photo of the pen label or its box.",
             "why": "Identifies the medication and dose.", "required": True},
            {"key": "lot_expiration", "label": "Lot / expiration",
             "instruction": "Now the lot number and expiration.",
             "why": "Captures expiration details.", "required": False},
        ],
    },
}

# Maps a missing/low-confidence field to the photo that would supply it — for the
# confidence-driven "to improve confidence, I'd like one more picture of …" prompt.
FIELD_TO_PHOTO_SUGGESTION = [
    (("name",), "a clear photo of the front label"),
    (("dose", "strength"), "a closer photo of the dosage on the label"),
    (("rx_number", "provider", "refills"), "a photo of the pharmacy label"),
    (("sig",), "a photo of the directions"),
    (("serving_size", "active_ingredients"), "a photo of the Supplement Facts panel"),
]


def get_profile(profile_key):
    return CAPTURE_PROFILES.get(profile_key)


def profile_choices():
    return [(k, v["title"]) for k, v in CAPTURE_PROFILES.items()]


def suggested_next_photo(missing_fields):
    """Deterministically suggest the single most useful next photo from the set of
    still-missing fields (drives the 'I still need …' prompt). None if nothing
    high-value is missing."""
    missing = set(missing_fields or ())
    for fields, suggestion in FIELD_TO_PHOTO_SUGGESTION:
        if missing & set(fields):
            return suggestion
    return None
