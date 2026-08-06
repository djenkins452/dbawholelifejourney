# ==============================================================================
# File: apps/health/tests/test_nutrition_quantity_scaling.py
# Description: Regression coverage for the quantity double-apply defect — a food logged
#   with quantity N must produce EXACTLY N× the per-serving nutrition, on add, on edit
#   (never compounding), and on copy; and meal/daily totals must equal the line items.
#   Root cause: the client wrote scaled totals into the per-serving fields and the form
#   re-multiplied by quantity (qty 2 -> 4×). Fixed by keeping the fields per-serving.
# ==============================================================================
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.health.forms import FoodEntryForm
from apps.health.models import FoodEntry
from apps.health.services.nutrition_calculator import compute_totals

User = get_user_model()

# The required base serving from the task.
BASE = {"calories": 480, "protein_g": 20, "carbohydrates_g": 30, "fat_g": 30}


def _form_data(cal, protein, carbs, fat, qty, **over):
    d = {
        "food_name": over.get("food_name", "Test Food"),
        "quantity": str(qty),
        "serving_size": "1",
        "serving_unit": "serving",
        "total_calories": str(cal),
        "total_protein_g": str(protein),
        "total_carbohydrates_g": str(carbs),
        "total_fat_g": str(fat),
        "logged_date": "2026-08-06",
        "meal_type": FoodEntry.MEAL_BREAKFAST,
    }
    d.update({k: v for k, v in over.items() if k != "food_name"})
    return d


class ComputeTotalsUnitTests(TestCase):
    """The canonical multiply — per-serving × quantity, exactly once."""

    def test_quantity_scaling_matrix(self):
        cases = {
            1: (480, 20, 30, 30),
            2: (960, 40, 60, 60),
            3: (1440, 60, 90, 90),
            0.5: (240, 10, 15, 15),
            1.5: (720, 30, 45, 45),
        }
        snap = {k: float(v) for k, v in BASE.items()}
        for qty, (cal, p, c, f) in cases.items():
            t = compute_totals(snap, qty)
            self.assertAlmostEqual(t["total_calories"], cal, places=2, msg=f"qty={qty}")
            self.assertAlmostEqual(t["total_protein_g"], p, places=2, msg=f"qty={qty}")
            self.assertAlmostEqual(t["total_carbohydrates_g"], c, places=2, msg=f"qty={qty}")
            self.assertAlmostEqual(t["total_fat_g"], f, places=2, msg=f"qty={qty}")


class FoodEntryFormScalingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="nutri@test.com", password="x")

    def _add(self, qty):
        """Add a food via the form with PER-SERVING inputs (as the fixed client submits)."""
        form = FoodEntryForm(data=_form_data(480, 20, 30, 30, qty), user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        e = form.save(commit=False)
        e.user = self.user
        e.save()
        return e

    def test_add_quantity_2_is_exactly_double_not_quadruple(self):
        e = self._add(2)
        self.assertEqual(float(e.total_calories), 960.0)   # NOT 1920
        self.assertEqual(float(e.total_protein_g), 40.0)
        self.assertEqual(float(e.total_carbohydrates_g), 60.0)
        self.assertEqual(float(e.total_fat_g), 60.0)
        # the stored snapshot is PER-SERVING, not the line total
        self.assertEqual(e.snapshot_nutrients["calories"], 480.0)

    def test_add_quantity_3(self):
        e = self._add(3)
        self.assertEqual(float(e.total_calories), 1440.0)

    def test_edit_reload_shows_per_serving_not_the_line_total(self):
        # The heart of the defect: editing a qty-2 entry must pre-fill the nutrient fields
        # with the PER-SERVING value (480), never the stored line total (960) — otherwise
        # save re-multiplies by quantity.
        e = self._add(2)
        edit_form = FoodEntryForm(instance=e, user=self.user)
        self.assertEqual(float(edit_form.initial["total_calories"]), 480.0)   # per serving
        self.assertNotEqual(float(edit_form.initial["total_calories"]), 960.0)

    def test_edit_resave_unchanged_does_not_compound(self):
        e = self._add(2)                       # 960
        # Simulate the edit form: fields pre-filled from per-serving snapshot, resubmitted.
        data = _form_data(480, 20, 30, 30, 2)  # per-serving values, same qty
        form = FoodEntryForm(data=data, instance=e, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        e.refresh_from_db()
        self.assertEqual(float(e.total_calories), 960.0)   # unchanged, NOT 1920/3840

    def test_edit_quantity_2_to_3_becomes_exactly_triple(self):
        e = self._add(2)                       # 960
        data = _form_data(480, 20, 30, 30, 3)  # per-serving unchanged, qty 2 -> 3
        form = FoodEntryForm(data=data, instance=e, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        e.refresh_from_db()
        self.assertEqual(float(e.total_calories), 1440.0)  # 3×, NOT 6× (2880)

    def test_edit_quantity_back_to_1_returns_to_base(self):
        e = self._add(2)
        data = _form_data(480, 20, 30, 30, 1)
        form = FoodEntryForm(data=data, instance=e, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        e.refresh_from_db()
        self.assertEqual(float(e.total_calories), 480.0)

    def test_mcmuffin_production_scenario(self):
        # The screenshot: Sausage Egg and Cheese McMuffin, base ~480 cal, quantity 2.
        form = FoodEntryForm(
            data=_form_data(480, 20, 30, 26, 2, food_name="Sausage Egg and Cheese McMuffin"),
            user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        e = form.save(commit=False)
        e.user = self.user
        e.save()
        self.assertEqual(float(e.total_calories), 960.0)   # corrected — was 1920


class TotalsRollupTests(TestCase):
    """Meal totals == sum of line items; daily totals == sum of meals."""

    def setUp(self):
        self.user = User.objects.create_user(email="rollup@test.com", password="x")

    def _entry(self, cal, qty, meal):
        e = FoodEntry(user=self.user, food_name="f", quantity=Decimal(str(qty)),
                      serving_size=Decimal("1"), serving_unit="serving",
                      snapshot_nutrients={"calories": float(cal)},
                      logged_date="2026-08-06", meal_type=meal)
        e.calculate_totals()
        e.save()
        return e

    def test_meal_and_daily_totals_equal_line_sums(self):
        self._entry(480, 2, FoodEntry.MEAL_BREAKFAST)   # 960
        self._entry(100, 1, FoodEntry.MEAL_BREAKFAST)   # 100
        self._entry(300, 3, FoodEntry.MEAL_LUNCH)       # 900
        from apps.health.services.nutrition_queries import NutritionQueries
        meals = NutritionQueries.get_meal_totals(self.user, "2026-08-06")
        self.assertEqual(float(meals[FoodEntry.MEAL_BREAKFAST]["calories"]), 1060.0)
        self.assertEqual(float(meals[FoodEntry.MEAL_LUNCH]["calories"]), 900.0)
        # daily == sum of meals == sum of lines (1060 + 900)
        daily = NutritionQueries.get_daily_totals(self.user, "2026-08-06")
        self.assertEqual(float(daily["calories"]), 1960.0)


class CopyPreservesQuantityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="copy@test.com", password="x")

    def test_copying_a_quantity_2_entry_stays_quantity_2(self):
        src = FoodEntry(user=self.user, food_name="f", quantity=Decimal("2"),
                        serving_size=Decimal("1"), serving_unit="serving",
                        snapshot_nutrients={"calories": 480.0},
                        logged_date="2026-08-06", meal_type=FoodEntry.MEAL_BREAKFAST)
        src.calculate_totals()
        src.save()
        # A copy preserves quantity + stored totals (does not recompute/compound).
        copy = FoodEntry.objects.create(
            user=self.user, food_name=src.food_name, quantity=src.quantity,
            serving_size=src.serving_size, serving_unit=src.serving_unit,
            snapshot_nutrients=src.snapshot_nutrients,
            total_calories=src.total_calories,
            logged_date="2026-08-07", meal_type=src.meal_type)
        self.assertEqual(float(copy.quantity), 2.0)
        self.assertEqual(float(copy.total_calories), 960.0)   # NOT 1920
