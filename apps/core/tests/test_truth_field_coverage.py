"""Truth-Layer field-coverage CONTRACT.

For each audited user-truth model, EVERY concrete field must be classified as either
EXPOSED (surfaced by a DomainTruth composer/metric) or EXCLUDED (implementation
metadata that must never reach the CoS). The test fails when a NEW model field is added
but left unclassified — so hidden deterministic user truth cannot silently reappear as
the schema evolves (replaces manual field-counting audits).

To satisfy a failure: add the new field to `exposed` (and actually surface it in the
composer) or to `excluded` (with a real implementation-metadata reason).
"""
from django.apps import apps
from django.test import TestCase

# model label -> {"exposed": {...}, "excluded": {...}}. Union must equal the model's
# concrete field names. `id` is auto-added to every excluded set by the harness.
CLASSIFICATION = {
    "health.FoodEntry": {
        "exposed": {"food_name", "food_brand", "quantity", "serving_size",
                    "serving_unit", "meal_type", "logged_date", "logged_time",
                    "total_calories", "total_protein_g", "total_carbohydrates_g",
                    "total_fiber_g", "total_sugar_g", "total_fat_g",
                    "total_saturated_fat_g", "total_sodium_mg", "total_cholesterol_mg",
                    "total_potassium_mg", "data_source_used", "entry_source",
                    "is_favorite", "location", "eating_pace", "hunger_level_before",
                    "fullness_level_after", "mood_tags", "notes"},
        "excluded": {"user", "created_at", "updated_at", "status", "deleted_at",
                     "created_via", "food_item", "custom_food", "snapshot_nutrients",
                     "food_item_version", "ai_confidence_score", "confidence_score",
                     "copied_from_entry", "applied_template"},
    },
    "health.GlucoseEntry": {
        "exposed": {"value", "unit", "recorded_at", "context", "notes", "source",
                    "trend", "trend_rate", "display_device"},
        "excluded": {"user", "created_at", "updated_at", "status", "deleted_at",
                     "created_via", "dexcom_record_id", "sync_id"},
    },
    "health.BloodPressureEntry": {
        "exposed": {"systolic", "diastolic", "pulse", "recorded_at", "context",
                    "arm", "position", "notes", "source"},
        "excluded": {"user", "created_at", "updated_at", "status", "deleted_at",
                     "created_via", "sync_id"},
    },
    "health.WeightEntry": {
        "exposed": {"value", "unit", "recorded_at", "notes", "body_fat_percentage",
                    "lean_body_mass", "source"},
        "excluded": {"user", "created_at", "updated_at", "status", "deleted_at",
                     "created_via", "sync_id", "session"},
    },
    "health.StepsEntry": {
        "exposed": {"count", "logged_date", "recorded_at", "source", "goal",
                    "distance_miles", "calories_burned", "resting_calories",
                    "flights_climbed", "exercise_minutes", "stand_hours", "notes"},
        "excluded": {"user", "created_at", "updated_at", "status", "deleted_at",
                     "created_via", "sync_id"},
    },
    "life.SignificantEvent": {
        "exposed": {"title", "description", "event_type", "event_date",
                    "original_year", "person_name", "person", "custom_message"},
        "excluded": {"user", "created_at", "updated_at", "status", "deleted_at",
                     "created_via", "sms_reminder_enabled", "reminder_days"},
    },
    "meals.DietaryProfile": {
        "exposed": {"carb_limit_daily", "protein_target_daily", "calorie_target",
                    "fat_limit_daily", "dietary_flags", "diabetes_sensitive"},
        "excluded": {"user", "created_at", "updated_at", "status", "deleted_at",
                     "created_via"},
    },
    "medical.MedicalDocument": {
        "exposed": {"original_filename", "page_count", "extraction_method", "notes"},
        "excluded": {"user", "created_at", "updated_at", "status", "deleted_at",
                     "created_via", "file_hash", "extracted_text", "organize_document"},
    },
}


class TruthFieldCoverageContractTests(TestCase):
    def test_every_audited_field_is_classified(self):
        problems = []
        for label, cls in CLASSIFICATION.items():
            app_label, model_name = label.split(".")
            model = apps.get_model(app_label, model_name)
            concrete = {f.name for f in model._meta.concrete_fields}
            classified = set(cls["exposed"]) | set(cls["excluded"]) | {"id"}
            unclassified = concrete - classified
            stale = classified - concrete - {"id"}
            if unclassified:
                problems.append(f"{label}: UNCLASSIFIED fields {sorted(unclassified)} "
                                f"— expose them or mark excluded")
            if stale:
                problems.append(f"{label}: classification lists non-existent fields "
                                f"{sorted(stale)}")
        self.assertEqual(problems, [], "\n".join(problems))
