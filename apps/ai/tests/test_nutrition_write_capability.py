# ==============================================================================
# File: apps/ai/tests/test_nutrition_write_capability.py
# Description: Contract — M3 SAFE NUTRITION WRITE CAPABILITY.
#
#   GOVERNING INVARIANT: explicit user-supplied nutrition truth is authoritative for
#   that entry and must survive the entire write path exactly as supplied. Estimation
#   may fill genuinely missing values; it may NEVER silently replace an explicit one.
#
#   Origin (production 2026-08-27): the certified runtime had NO nutrition write at
#   all, so an explicit confirmed meal request was satisfied by the nearest available
#   numeric writes — a Task, then a Weight carrying the calorie value. `log_food`
#   existed but accepted only `calories`, and every other macro was overwritten from a
#   food-search/AI result, so exposing it as-is would have silently discarded truth.
#
#   Values here are arbitrary test data; nothing incident-specific is a mechanism.
# ==============================================================================
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from apps.ai.cos_services import action_interface as ai
from apps.ai.models import ActionConfirmation
from apps.health.models import FoodEntry, WeightEntry

# A complete explicit nutrition payload, as a user would state it.
SUPPLIED = {
    "food_name": "Test Casserole", "meal_type": "dinner",
    "calories": 534, "protein_g": 30, "carbohydrates_g": 29, "fiber_g": 5,
    "fat_g": 33, "saturated_fat_g": 13, "sodium_mg": 419, "sugar_g": 9,
}


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="nutrition-write@test.com", password="x")

    def setUp(self):
        cache.clear()
        FoodEntry.objects.all().delete()
        WeightEntry.objects.all().delete()
        ActionConfirmation.objects.all().delete()
        # Reproduce the production configuration: "ask me first before creating,
        # changing or deleting anything" is ON, which is why every write in the
        # incident was routed through a confirmation.
        from apps.users.models import UserPreferences
        UserPreferences.objects.update_or_create(
            user=self.user, defaults={"assistant_confirm_actions": True})
        # `setUpTestData` hands each test a DEEPCOPY whose reverse-one-to-one cache
        # still holds the pre-update preferences, so clear it explicitly.
        self.user.refresh_from_db()
        self.user._state.fields_cache.clear()

    def _propose(self, params=None):
        return ai.request_action(self.user, "log_food", dict(params or SUPPLIED),
                                 turn_id="t")

    def _confirm_write(self, params=None):
        out = self._propose(params)
        cid = out["confirmation"]["confirmation_id"]
        ai.resolve_pending_action(self.user, cid, confirm=True)
        return out, cid


class ExposureTests(TestCase):
    """1 — the certified runtime actually offers the capability."""

    def test_certified_runtime_exposes_the_nutrition_write(self):
        from apps.ai.model_interface.constitution import ALLOWED_WRITE_INTENTS, all_tools
        self.assertIn("log_food", ALLOWED_WRITE_INTENTS)
        names = {t["function"]["name"] for t in all_tools(writes_enabled=True)}
        self.assertIn("log_food", names)

    def test_the_schema_accepts_every_nutrient_the_canonical_model_stores(self):
        from apps.ai.model_interface.constitution import all_tools
        tool = [t for t in all_tools(writes_enabled=True)
                if t["function"]["name"] == "log_food"][0]
        props = tool["function"]["parameters"]["properties"]
        for p in ("calories", "protein_g", "carbohydrates_g", "fiber_g", "sugar_g",
                  "fat_g", "saturated_fat_g", "sodium_mg", "meal_type"):
            self.assertIn(p, props, f"the write cannot carry {p!r}")

    def test_no_write_is_exposed_that_the_canonical_model_cannot_store(self):
        """4 — a supplied field must never vanish between schema and column."""
        from apps.ai.model_interface.constitution import all_tools
        tool = [t for t in all_tools(writes_enabled=True)
                if t["function"]["name"] == "log_food"][0]
        fields = {f.name for f in FoodEntry._meta.get_fields()}
        mapping = dict(__import__("apps.ai.action_handlers", fromlist=["x"])
                       .ActionHandler._FOOD_NUTRIENT_FIELDS)
        for param in tool["function"]["parameters"]["properties"]:
            if param in mapping:
                self.assertIn(mapping[param], fields,
                              f"{param!r} has no canonical column to land in")


class SuppliedTruthSurvivesTests(_Base):
    """2, 3, 5, 6, 11 — what the user said is what gets stored."""

    def test_every_supplied_nutrient_survives_to_the_canonical_record(self):
        self._confirm_write()
        e = FoodEntry.objects.get(user=self.user)
        self.assertEqual(e.food_name, "Test Casserole")
        self.assertEqual(e.meal_type, "dinner")
        self.assertEqual(e.total_calories, Decimal("534"))
        self.assertEqual(e.total_protein_g, Decimal("30"))
        self.assertEqual(e.total_carbohydrates_g, Decimal("29"))
        self.assertEqual(e.total_fiber_g, Decimal("5"))
        self.assertEqual(e.total_fat_g, Decimal("33"))
        self.assertEqual(e.total_saturated_fat_g, Decimal("13"))
        self.assertEqual(e.total_sodium_mg, Decimal("419"))
        self.assertEqual(e.total_sugar_g, Decimal("9"))

    def test_explicit_values_are_never_replaced_by_estimation(self):
        """The exact defect that made naive exposure unsafe."""
        fake = mock.Mock(name="match", food_item_id=None, source="ai",
                         calories=999, protein_g=1, carbohydrates_g=1, fat_g=1,
                         fiber_g=1, sugar_g=1, serving_size=1, serving_unit="serving")
        fake.name = "Something Else Entirely"
        with mock.patch("apps.health.services.food_search.food_search_service.search",
                        return_value=[fake]) as searched:
            self._confirm_write()
        e = FoodEntry.objects.get(user=self.user)
        self.assertEqual(e.total_calories, Decimal("534"))
        self.assertEqual(e.total_protein_g, Decimal("30"))
        self.assertEqual(e.food_name, "Test Casserole",
                         "the user's own meal name was replaced by a search match")
        self.assertEqual(searched.call_count, 0,
                         "an estimate that is never fetched cannot overwrite anything")

    def test_estimation_may_still_fill_genuinely_missing_values(self):
        fake = mock.Mock(name="match", food_item_id=None, source="fatsecret",
                         calories=210, protein_g=7, carbohydrates_g=11, fat_g=3,
                         fiber_g=2, sugar_g=4, serving_size=1, serving_unit="serving")
        fake.name = "Matched Food"
        with mock.patch("apps.health.services.food_search.food_search_service.search",
                        return_value=[fake]):
            self._confirm_write({"food_name": "Mystery", "meal_type": "lunch"})
        e = FoodEntry.objects.get(user=self.user)
        self.assertEqual(e.total_calories, Decimal("210"))

    def test_partial_supply_keeps_supplied_and_fills_the_rest(self):
        fake = mock.Mock(name="match", food_item_id=None, source="fatsecret",
                         calories=210, protein_g=7, carbohydrates_g=11, fat_g=3,
                         fiber_g=2, sugar_g=4, serving_size=1, serving_unit="serving")
        fake.name = "Matched Food"
        with mock.patch("apps.health.services.food_search.food_search_service.search",
                        return_value=[fake]):
            self._confirm_write({"food_name": "Mystery", "meal_type": "lunch",
                                 "protein_g": 42})
        e = FoodEntry.objects.get(user=self.user)
        self.assertEqual(e.total_protein_g, Decimal("42"), "supplied value lost")
        self.assertEqual(e.total_calories, Decimal("210"), "missing value not filled")

    def test_meal_type_survives(self):
        self._confirm_write()
        self.assertEqual(FoodEntry.objects.get(user=self.user).meal_type, "dinner")

    def test_date_attribution_uses_the_users_local_day(self):
        from apps.core.utils import get_user_today
        self._confirm_write()
        self.assertEqual(FoodEntry.objects.get(user=self.user).logged_date,
                         get_user_today(self.user))

    def test_provenance_distinguishes_supplied_from_derived(self):
        self._confirm_write()
        e = FoodEntry.objects.get(user=self.user)
        self.assertEqual(e.data_source_used, FoodEntry.DATA_SOURCE_USER_OVERRIDE)
        self.assertEqual(float(e.snapshot_nutrients["total_protein_g"]), 30.0)

    def test_malformed_supplied_value_fails_closed(self):
        out = self._propose({**SUPPLIED, "protein_g": "thirty"})
        cid = (out.get("confirmation") or {}).get("confirmation_id")
        if cid:
            ai.resolve_pending_action(self.user, cid, confirm=True)
        self.assertEqual(FoodEntry.objects.count(), 0,
                         "an unparseable nutrient must not produce a partial record")


class AuthorizationAndIsolationTests(_Base):
    """7, 8, 9, 10 — M1 integrity holds, and no other domain receives the values."""

    def test_authorization_line_matches_the_bound_nutrition_payload(self):
        conf = self._propose()["confirmation"]
        rec = ActionConfirmation.objects.get(id=conf["confirmation_id"])
        self.assertEqual(rec.action, "log_food")
        self.assertIn("Log food", conf["authorization"])
        self.assertIn("Test Casserole", conf["authorization"])
        self.assertEqual(rec.authorization_line, conf["authorization"])
        self.assertEqual(rec.params["protein_g"], 30)

    def test_nutrition_write_creates_no_task_and_no_weight(self):
        from apps.life.models import Task
        self._confirm_write()
        self.assertEqual(FoodEntry.objects.count(), 1)
        self.assertEqual(WeightEntry.objects.count(), 0)
        self.assertEqual(Task.objects.filter(user=self.user).count(), 0)

    def test_repeated_confirmation_is_exactly_once(self):
        out = self._propose()
        cid = out["confirmation"]["confirmation_id"]
        for _ in range(3):
            ai.resolve_pending_action(self.user, cid, confirm=True)
        self.assertEqual(FoodEntry.objects.count(), 1)

    def test_failure_cannot_be_narrated_as_success(self):
        out = self._propose()
        cid = out["confirmation"]["confirmation_id"]
        with mock.patch("apps.health.models.FoodEntry.objects.create",
                        side_effect=RuntimeError("db down")):
            res = ai.resolve_pending_action(self.user, cid, confirm=True)
        self.assertEqual(FoodEntry.objects.count(), 0)
        self.assertNotEqual(res["status"], ai.OK,
                            "a failed write reported as success")

    def test_no_incident_specific_logic_exists(self):
        """12 — the capability is generic; the reproducer is only test data."""
        import ast
        import inspect
        import io
        import tokenize

        from apps.ai import action_handlers
        import textwrap
        src = textwrap.dedent(
            inspect.getsource(action_handlers.ActionHandler.handle_log_food))
        code = "".join("" if t.type == tokenize.COMMENT else t.string
                       for t in tokenize.generate_tokens(io.StringIO(src).readline))
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    code = code.replace(doc, "")
        low = code.lower()
        for banned in ("stuffed", "peppers", "534", "419"):
            self.assertNotIn(banned, low)
