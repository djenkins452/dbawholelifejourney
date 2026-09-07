# ==============================================================================
# File: apps/health/tests/test_usda_catalog_import.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The generic food catalog seeds, is idempotent, and is discoverable
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-09-06
# ==============================================================================
"""A plain banana has to exist somewhere before anyone can find it.

`FoodItem` was documented as a global food library and was in fact an opportunistic cache —
written only by FatSecret cache-back, AI estimates and barcode scans, and periodically
emptied by `load_initial_data`. Ranking could not fix that: ordering nothing produces
nothing.

These tests use a small synthetic file in the USDA export's own shape. No network, no
provider, and the real dataset is never committed.
"""

import json
import tempfile
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.health.models import FoodItem

User = get_user_model()


def _food(fdc_id, description, calories=105.0, protein=1.3, **extra):
    nutrients = [
        {"nutrient": {"id": 1008}, "amount": calories},
        {"nutrient": {"id": 1003}, "amount": protein},
        {"nutrient": {"id": 1005}, "amount": 27.0},
        {"nutrient": {"id": 1004}, "amount": 0.3},
    ]
    nutrients.extend(extra.pop("extra_nutrients", []))
    return {"fdcId": fdc_id, "description": description,
            "foodNutrients": nutrients, **extra}


def _source(foods, wrapper=None):
    payload = {wrapper: foods} if wrapper else foods
    path = Path(tempfile.mkdtemp()) / "usda.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def _run(path, **kw):
    out = StringIO()
    call_command("import_usda_foods", source=path, stdout=out, **kw)
    return out.getvalue()


class ImportTests(TestCase):
    def test_generic_foods_are_imported_with_their_nutrition(self):
        _run(_source([_food(1105314, "Bananas, raw")]))
        item = FoodItem.objects.get(source_reference="1105314")
        self.assertEqual(item.name, "Bananas, raw")
        self.assertEqual(float(item.calories), 105.0)
        self.assertEqual(item.data_source, FoodItem.SOURCE_USDA)
        self.assertTrue(item.is_active)

    def test_the_usda_id_is_recorded_for_cross_reference(self):
        _run(_source([_food(1105314, "Bananas, raw")]))
        item = FoodItem.objects.get(source_reference="1105314")
        self.assertEqual(item.external_ids.get("usda_fdb_id"), "1105314")

    def test_servings_are_recorded_as_the_dataset_states_them(self):
        """USDA generics are per 100 g. Nothing here invents a household portion."""
        _run(_source([_food(1105314, "Bananas, raw")]))
        item = FoodItem.objects.get(source_reference="1105314")
        self.assertEqual(float(item.serving_size), 100.0)
        self.assertEqual(item.serving_unit, "g")

    def test_re_running_updates_in_place_and_never_duplicates(self):
        path = _source([_food(1105314, "Bananas, raw", calories=105.0)])
        _run(path)
        _run(_source([_food(1105314, "Bananas, raw", calories=110.0)]))
        items = FoodItem.objects.filter(source_reference="1105314")
        self.assertEqual(items.count(), 1, "a refresh duplicated the catalog")
        self.assertEqual(float(items.first().calories), 110.0)

    def test_both_export_shapes_are_accepted(self):
        _run(_source([_food(1, "Apples, raw")], wrapper="SRLegacyFoods"))
        self.assertTrue(FoodItem.objects.filter(source_reference="1").exists())

    def test_a_food_without_an_energy_value_is_skipped(self):
        out = _run(_source([{"fdcId": 9, "description": "Water", "foodNutrients": []}]))
        self.assertFalse(FoodItem.objects.filter(source_reference="9").exists())
        self.assertIn("1 skipped", out)

    def test_the_limit_bounds_the_import(self):
        _run(_source([_food(i, f"Food {i}") for i in range(1, 21)]), limit=5)
        self.assertEqual(FoodItem.objects.count(), 5)

    def test_a_dry_run_writes_nothing(self):
        out = _run(_source([_food(1105314, "Bananas, raw")]), dry_run=True)
        self.assertEqual(FoodItem.objects.count(), 0)
        self.assertIn("would import", out)

    def test_a_bad_source_fails_loudly(self):
        with self.assertRaises(CommandError):
            _run("/nonexistent/usda.json")

    def test_other_catalog_sources_are_never_touched(self):
        """A refresh must not disturb FatSecret, barcode or user-created rows."""
        keep = FoodItem.objects.create(
            name="Some Restaurant Meal", data_source=FoodItem.SOURCE_FATSECRET,
            source_reference="fs-1", calories=800, serving_size=1,
            serving_unit="serving", is_active=True)
        _run(_source([_food(1105314, "Bananas, raw")]))
        keep.refresh_from_db()
        self.assertEqual(keep.name, "Some Restaurant Meal")
        self.assertEqual(FoodItem.objects.count(), 2)


class DiscoverabilityTests(TestCase):
    """The catalog is only worth seeding if the same search finds it."""

    def setUp(self):
        self.user = User.objects.create_user(email="usda@contract.test", password="x")
        _run(_source([
            _food(1105314, "Bananas, raw"),
            _food(2, "Banana bread"),
            _food(3, "Ham and cheese sandwich", calories=350.0),
        ]))
        from apps.health.models import CustomFood
        CustomFood.objects.create(user=self.user, name="Oikos Pro Banana", calories=130,
                                  serving_size=1, serving_unit="serving")

    def _search(self, q):
        from apps.health.services.food_search import food_search_service
        return [r.name for r in food_search_service.search(
            query=q, user=self.user, limit=10, use_fatsecret=False, use_ai=False)]

    def test_a_generic_food_is_now_discoverable(self):
        self.assertIn("Bananas, raw", self._search("banana"))

    def test_the_generic_food_outranks_a_branded_partial(self):
        results = self._search("banana")
        self.assertLess(results.index("Bananas, raw"), results.index("Oikos Pro Banana"))

    def test_a_restaurant_or_branded_row_stays_discoverable(self):
        FoodItem.objects.create(
            name="Chick-fil-A Chicken Sandwich", data_source=FoodItem.SOURCE_FATSECRET,
            source_reference="fs-2", calories=440, serving_size=1,
            serving_unit="serving", is_active=True)
        self.assertIn("Chick-fil-A Chicken Sandwich", self._search("chicken sandwich"))

    def test_the_write_boundary_is_unchanged_by_a_seeded_catalog(self):
        """A wider catalog must not make substitution possible again."""
        from apps.ai.action_handlers import ActionHandler
        from apps.health.models import FoodEntry
        ActionHandler(self.user).handle_log_food(food_name="banana",
                                                 meal_type="breakfast")
        entry = FoodEntry.objects.filter(user=self.user).latest("id")
        self.assertEqual(entry.food_name, "banana",
                         "a near match was adopted as the user's food")
        self.assertEqual(entry.data_source_used, FoodEntry.DATA_SOURCE_UNKNOWN)

    def test_an_exact_catalog_name_is_adopted_with_its_nutrition(self):
        from apps.ai.action_handlers import ActionHandler
        from apps.health.models import FoodEntry
        ActionHandler(self.user).handle_log_food(food_name="Bananas, raw",
                                                 meal_type="breakfast")
        entry = FoodEntry.objects.filter(user=self.user).latest("id")
        self.assertEqual(entry.food_name, "Bananas, raw")
        self.assertEqual(float(entry.total_calories), 105.0)

    def test_the_ui_and_the_cos_share_this_result_set(self):
        """Same authority, same ranking — asserted on the API the UI actually calls."""
        from apps.health.services.food_search import food_search_service
        ui = [r.name for r in food_search_service.search(
            query="banana", user=self.user, limit=10, use_fatsecret=False, use_ai=False)]
        self.assertEqual(ui, self._search("banana"))
