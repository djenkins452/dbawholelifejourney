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
    {
        # Full pharmacy label WITH refills — exercises Pharmacy/Provider/Prescription linking.
        "key": "pharmacy_label_with_refills",
        "category": "medicine",
        "expected_intake_type": "medication",
        "vision_items": [{"label": "Amoxicillin 500mg", "details": {
            "name": "Amoxicillin", "strength": "500mg", "dosage": "500mg",
            "dosage_form": "capsule", "route": "oral",
            "directions": "Take 1 capsule three times daily",
            "quantity": "30 capsules", "ndc": "00093-3109-01", "rx_number": "RX9988776",
            "prescriber": "Dr. Reyes", "pharmacy": "Wellness Pharmacy",
            "pharmacy_phone": "555-987-6543", "refills": "2",
            "written_date": "2026-06-10", "expiration": "2027-06-10",
        }}],
        "scan_confidence": 0.86,
    },
    {
        # Label with NO refills (refills 0).
        "key": "pharmacy_label_no_refills",
        "category": "medicine",
        "expected_intake_type": "medication",
        "vision_items": [{"label": "Prednisone 20mg", "details": {
            "name": "Prednisone", "strength": "20mg", "dosage": "20mg",
            "directions": "Take 1 tablet daily for 5 days", "quantity": "5 tablets",
            "rx_number": "RX5500001", "prescriber": "Dr. Lee", "pharmacy": "Wellness Pharmacy",
            "refills": "0",
        }}],
        "scan_confidence": 0.83,
    },
    {
        # Low-confidence / partial label — only name + dose legible.
        "key": "partial_low_confidence",
        "category": "medicine",
        "expected_intake_type": "medication",
        "vision_items": [{"label": "Losartan", "details": {"dosage": "50mg"}}],
        "scan_confidence": 0.45,
    },
    {
        # Old bottle that duplicates an existing tracked medication (the test
        # pre-creates "Atorvastatin 40mg"). Used for duplicate-detection.
        "key": "old_bottle_duplicate",
        "category": "medicine",
        "expected_intake_type": "medication",
        "vision_items": [{"label": "Atorvastatin", "details": {
            "name": "Atorvastatin", "dosage": "40mg", "rx_number": "RXOLD0001",
        }}],
        "scan_confidence": 0.7,
    },
]
