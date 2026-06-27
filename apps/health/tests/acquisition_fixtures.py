"""
Reusable medication-acquisition regression fixtures (Sprint 3.5).

Representative real-world medication types, shaped exactly like the Scan/Vision
extraction output (``items`` = [{"label", "details": {...}}], plus an overall
``scan_confidence``). Future acquisition enhancements should be validated against
these representative types rather than synthetic one-off examples.

Each sample: key, category ('medicine'|'supplement'), expected_intake_type,
vision_items, scan_confidence.
"""

ACQUISITION_SAMPLES = [
    {
        "key": "prescription_bottle",
        "category": "medicine",
        "expected_intake_type": "medication",
        "vision_items": [{"label": "Metformin", "details": {
            "dosage": "500mg",
            "directions": "Take 1 tablet twice daily with meals",
            "quantity": "60",
            "purpose": "Type 2 diabetes",
            "prescriber": "Dr. Adams",
            "pharmacy": "Corner Pharmacy",
            "refills": "3",
        }}],
        "scan_confidence": 0.82,
    },
    {
        "key": "supplement_facts",
        "category": "supplement",
        "expected_intake_type": "supplement",
        "vision_items": [{"label": "Vitamin D3", "details": {
            "dosage": "2000 IU",
            "directions": "Take 1 softgel daily",
            "quantity": "120",
        }}],
        "scan_confidence": 0.78,
    },
    {
        "key": "otc_drug_facts",
        "category": "medicine",
        "expected_intake_type": "medication",
        "vision_items": [{"label": "Ibuprofen", "details": {
            "dosage": "200mg",
            "directions": "Take 1-2 tablets every 4-6 hours as needed",
            "purpose": "Pain reliever / fever reducer",
        }}],
        "scan_confidence": 0.70,
    },
    {
        "key": "injection_pen",
        "category": "medicine",
        "expected_intake_type": "medication",
        "vision_items": [{"label": "Lantus SoloStar", "details": {
            "dosage": "20 units",
            "directions": "Inject subcutaneously once daily at bedtime",
            "prescriber": "Dr. Endo",
        }}],
        "scan_confidence": 0.75,
    },
    {
        "key": "pharmacy_label",
        "category": "medicine",
        "expected_intake_type": "medication",
        "vision_items": [{"label": "Atorvastatin", "details": {
            "dosage": "40mg",
            "directions": "Take 1 tablet at bedtime",
            "quantity": "90",
            "prescriber": "Dr. Cardio",
            "pharmacy": "MedMart",
            "refills": "5",
            "ndc": "00071-0156-23",
        }}],
        "scan_confidence": 0.88,
    },
    {
        "key": "supplement_bottle_minimal",
        "category": "supplement",
        "expected_intake_type": "supplement",
        "vision_items": [{"label": "Creatine Monohydrate", "details": {"dosage": "5g"}}],
        "scan_confidence": 0.60,
    },
    {
        "key": "glp1_injection",
        "category": "medicine",
        "expected_intake_type": "medication",
        "vision_items": [{"label": "Mounjaro", "details": {
            "dosage": "5mg/0.5mL",
            "directions": "Inject 5 mg subcutaneously once weekly",
            "prescriber": "Dr. Endo",
            "pharmacy": "Specialty Rx",
        }}],
        "scan_confidence": 0.80,
    },
]
