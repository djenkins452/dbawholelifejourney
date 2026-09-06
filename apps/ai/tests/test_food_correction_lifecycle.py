# ==============================================================================
# File: apps/ai/tests/test_food_correction_lifecycle.py
# Description: The CoS can now ADDRESS, UPDATE, and DELETE a specific existing FoodEntry —
#   the structural fix for the production defect where correcting a logged food created a
#   duplicate and removing one looped without executing (2026-09-05).
#     create -> correct that EXACT entry     -> canonical row updated, NO duplicate
#     create duplicate -> remove EXACT one   -> the correct row remains
#     unknown nutrition -> asked to estimate -> estimated values written with provenance
#     no exact target                        -> FAIL CLOSED, nothing mutated
# ==============================================================================
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.health.models import FoodEntry
from apps.health.services.nutrition_queries import NutritionQueries
from apps.ai.cos_services import food_correction as fc
from apps.ai.cos_services import record_correction as rc

User = get_user_model()


def _entry(user, name="Roast Beef", *, per_serving=None, qty=1, meal="dinner",
           source=FoodEntry.DATA_SOURCE_UNKNOWN, date="2026-09-05"):
    snap = per_serving or {}
    e = FoodEntry(user=user, food_name=name, quantity=Decimal(str(qty)),
                  serving_size=Decimal("1"), serving_unit="serving",
                  snapshot_nutrients=snap, data_source_used=source,
                  logged_date=date, meal_type=meal)
    if snap:
        e.calculate_totals()
    e.save()
    return e


class AddressabilityTests(TestCase):
    """Truth exposes the canonical id so the model can target one exact entry."""

    def setUp(self):
        self.user = User.objects.create_user(email="addr@t.co", password="x")

    def test_food_entity_carries_record_id_and_type(self):
        e = _entry(self.user, per_serving={"calories": 280.0})
        ents = NutritionQueries.describe(self.user)
        self.assertTrue(ents, "describe returned nothing")
        ext = ents[0].to_dict().get("extensions", {})
        self.assertEqual(ext.get("record_id"), e.pk)
        self.assertEqual(ext.get("record_type"), "food")

    def test_meal_items_carry_record_id(self):
        e = _entry(self.user, per_serving={"calories": 280.0})
        meals = NutritionQueries.describe_meals(self.user, on_date="2026-09-05")
        items = meals[0].to_dict()["definition"]["items"]
        self.assertEqual(items[0]["record_id"], e.pk)


class UpdateInPlaceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="upd@t.co", password="x")

    def test_correct_exact_entry_updates_row_and_creates_no_duplicate(self):
        e = _entry(self.user, "Roast Beef", per_serving={"calories": 0.0})  # logged unknown/0
        out = fc.update_food_entry(self.user, e.pk, calories=280, protein_g=23,
                                   carbohydrates_g=0, fat_g=20)
        self.assertEqual(out["status"], fc.OK)
        self.assertTrue(out["changed"])
        e.refresh_from_db()
        self.assertEqual(float(e.total_calories), 280.0)
        self.assertEqual(float(e.total_protein_g), 23.0)
        # exactly ONE row for this user — corrected in place, not duplicated
        self.assertEqual(FoodEntry.objects.filter(user=self.user, status="active").count(), 1)

    def test_quantity_change_recomputes_through_canonical_calc(self):
        e = _entry(self.user, per_serving={"calories": 480.0}, qty=1)  # 480
        out = fc.update_food_entry(self.user, e.pk, quantity=2)
        self.assertEqual(out["status"], fc.OK)
        e.refresh_from_db()
        self.assertEqual(float(e.total_calories), 960.0)   # 480 × 2, applied ONCE
        self.assertEqual(e.snapshot_nutrients["calories"], 480.0)  # per-serving preserved

    def test_bad_id_fails_closed_and_mutates_nothing(self):
        _entry(self.user, per_serving={"calories": 100.0})
        out = fc.update_food_entry(self.user, 999999, calories=500)
        self.assertEqual(out["status"], fc.NOT_FOUND)
        self.assertFalse(out["changed"])

    def test_cannot_update_another_users_entry(self):
        other = User.objects.create_user(email="other@t.co", password="x")
        e = _entry(other, per_serving={"calories": 100.0})
        out = fc.update_food_entry(self.user, e.pk, calories=999)
        self.assertEqual(out["status"], fc.NOT_FOUND)
        e.refresh_from_db()
        self.assertEqual(float(e.total_calories), 100.0)   # untouched


class RemoveExactDuplicateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="del@t.co", password="x")

    def test_remove_exact_duplicate_leaves_the_correct_row(self):
        good = _entry(self.user, "Roast Beef", per_serving={"calories": 280.0})
        dup = _entry(self.user, "Roast Beef", per_serving={"calories": 0.0})  # the duplicate
        out = rc.remove_record(self.user, "food", dup.pk)
        self.assertTrue(out["removed"])
        dup.refresh_from_db()
        self.assertEqual(dup.status, "deleted")             # soft-deleted, recoverable
        good.refresh_from_db()
        self.assertEqual(good.status, "active")             # the correct one remains
        self.assertEqual(FoodEntry.objects.filter(user=self.user, status="active").count(), 1)

    def test_remove_without_exact_id_fails_closed(self):
        out = rc.remove_record(self.user, "food", None)
        self.assertFalse(out["removed"])


class EstimationProvenanceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="est@t.co", password="x")

    def test_estimate_written_with_ai_guess_provenance(self):
        e = _entry(self.user, "Mystery Stew")  # logged UNKNOWN, no numbers
        self.assertEqual(e.data_source_used, FoodEntry.DATA_SOURCE_UNKNOWN)
        out = fc.update_food_entry(self.user, e.pk, calories=250, protein_g=12, estimated=True)
        self.assertEqual(out["status"], fc.OK)
        self.assertTrue(out["estimated"])
        e.refresh_from_db()
        self.assertEqual(e.data_source_used, FoodEntry.DATA_SOURCE_AI_GUESS)
        self.assertEqual(float(e.total_calories), 250.0)   # honest number, not a zero

    def test_estimated_entry_travels_labelled_not_as_measurement(self):
        _entry(self.user, "Stew", per_serving={"calories": 250.0},
               source=FoodEntry.DATA_SOURCE_AI_GUESS)
        ent = NutritionQueries.describe(self.user)[0].to_dict()
        self.assertEqual(ent["confidence"], "medium")      # not "high"
        self.assertTrue(ent["extensions"].get("nutrition_estimated"))

    def test_user_stated_values_are_not_labelled_estimate(self):
        e = _entry(self.user, "Chicken")
        out = fc.update_food_entry(self.user, e.pk, calories=200)  # estimated defaults False
        self.assertFalse(out["estimated"])
        e.refresh_from_db()
        self.assertEqual(e.data_source_used, FoodEntry.DATA_SOURCE_USER_OVERRIDE)
