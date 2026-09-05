# ==============================================================================
# File: apps/core/tests/test_nutrition_action_integrity_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Explicit food identity, honest gaps, and whole multi-item requests
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-09-05
# ==============================================================================
"""Production, 2026-09-05. Three failures in one lunch.

"Log McAlistairs Ham and Cheese sandwich and mac and cheese for lunch today." Two
confirmations were minted a second apart; only the newest was ever shown; the user
confirmed it; the sandwich expired unseen while the assistant reported success. Then "add
one banana to my breakfast" logged **Oikos Pro Banana**, and three explicit corrections —
each sending `food_name="banana"` — logged it three more times.

The model sent the right arguments every single time. The write layer substituted the
product, because the local food search is `name__icontains` ordered by `-updated_at` and
`results[0]` was adopted whole: its name AND its nutrition. "banana" is a substring of
"Oikos Pro Banana". Correction could not work; it was not a wording problem.

And "mac and cheese", which matched nothing, was stored as 0 calories and 0 of every
macro — reaching the model as `confidence: "high"`. A number nobody looked up is not a
measurement.

These tests certify the CLASSES. No banana, no Oikos, no McAlister's, no sandwich, no mac
and cheese is named in any fix. No provider calls.
"""

from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.ai.action_handlers import ActionHandler, _exact_food_match
from apps.health.models import FoodEntry

User = get_user_model()


class _Result:
    """A food-search result, shaped like the real one."""

    def __init__(self, name, calories=None, source="custom"):
        self.name = name
        self.calories = calories
        self.source = source
        self.food_item_id = None
        for attr in ("protein_g", "carbohydrates_g", "fat_g", "fiber_g", "sugar_g",
                     "serving_size", "serving_unit"):
            setattr(self, attr, None)


class ExactIdentityTests(SimpleTestCase):
    """A match may take over the user's food only when it IS that food."""

    def test_a_more_specific_product_is_not_the_requested_food(self):
        self.assertIsNone(_exact_food_match([_Result("Oikos Pro Banana")], "banana"))

    def test_an_exact_name_matches_regardless_of_case_and_punctuation(self):
        for stored in ("Banana", "banana", "BANANA", "  banana  ", "Banana!"):
            self.assertIsNotNone(_exact_food_match([_Result(stored)], "banana"),
                                 f"{stored!r} is the same food and was rejected")

    def test_the_exact_match_wins_over_an_earlier_partial_one(self):
        """The production ordering put the user's custom product first."""
        results = [_Result("Oikos Pro Banana"), _Result("Banana")]
        self.assertEqual(_exact_food_match(results, "banana").name, "Banana")

    def test_a_broader_name_is_not_the_requested_food_either(self):
        """Containment in EITHER direction is still not identity."""
        self.assertIsNone(_exact_food_match([_Result("cheese")], "mac and cheese"))

    def test_no_results_and_no_query_are_handled(self):
        self.assertIsNone(_exact_food_match([], "banana"))
        self.assertIsNone(_exact_food_match([_Result("Banana")], ""))

    def test_the_matcher_names_no_food_or_brand(self):
        """Asserts on the BODY. The docstring says the function knows nothing about brands
        or foods — that sentence is the record of intent, not a violation of it, and a
        first draft of this test failed on its own explanation."""
        import ast
        import inspect
        import textwrap
        tree = ast.parse(textwrap.dedent(inspect.getsource(_exact_food_match)))
        fn = tree.body[0]
        body = fn.body[1:] if ast.get_docstring(fn) else fn.body
        code = "\n".join(ast.unparse(node) for node in body).lower()
        for word in ("banana", "oikos", "mcalist", "sandwich", "cheese", "brand"):
            self.assertNotIn(word, code)


class WritePathTests(TestCase):
    """What actually reaches the database."""

    def setUp(self):
        self.user = User.objects.create_user(email="food@contract.test", password="x")
        self.handlers = ActionHandler(self.user)

    def _log(self, results, **kw):
        service = mock.Mock()
        service.search.return_value = results
        with mock.patch("apps.health.services.food_search.food_search_service", service):
            return self.handlers.handle_log_food(**kw)

    def _entry(self):
        return FoodEntry.objects.filter(user=self.user).latest("id")

    def test_the_users_stated_food_is_what_gets_stored(self):
        out = self._log([_Result("Oikos Pro Banana", calories=130)],
                        food_name="banana", meal_type="breakfast")
        self.assertTrue(out.success)
        self.assertEqual(self._entry().food_name, "banana",
                         "the entry was renamed to a different product")

    def test_a_different_products_nutrition_is_never_borrowed(self):
        self._log([_Result("Oikos Pro Banana", calories=130)],
                  food_name="banana", meal_type="breakfast")
        self.assertEqual(self._entry().total_calories, Decimal("0"))
        self.assertEqual(self._entry().data_source_used, FoodEntry.DATA_SOURCE_UNKNOWN)

    def test_a_near_match_is_offered_back_rather_than_applied(self):
        out = self._log([_Result("Oikos Pro Banana", calories=130)],
                        food_name="banana", meal_type="breakfast")
        self.assertIn("Oikos Pro Banana", out.message)
        self.assertIn("nutrition unknown", out.message)
        self.assertEqual(out.data["candidates"], ["Oikos Pro Banana"])
        self.assertFalse(out.data["nutrition_established"])

    def test_an_exact_match_is_still_adopted_with_its_nutrition(self):
        """The fix must not cost the capability it protects."""
        self._log([_Result("Banana", calories=105)],
                  food_name="banana", meal_type="breakfast")
        entry = self._entry()
        self.assertEqual(entry.total_calories, Decimal("105"))
        self.assertEqual(entry.data_source_used, FoodEntry.DATA_SOURCE_LOCAL)

    def test_nothing_matched_records_unknown_not_zero(self):
        self._log([], food_name="mac and cheese", meal_type="lunch")
        entry = self._entry()
        self.assertEqual(entry.food_name, "mac and cheese")
        self.assertEqual(entry.data_source_used, FoodEntry.DATA_SOURCE_UNKNOWN)

    def test_user_supplied_nutrition_is_still_authoritative_and_known(self):
        self._log([], food_name="mac and cheese", meal_type="lunch", calories=420)
        entry = self._entry()
        self.assertEqual(entry.total_calories, Decimal("420"))
        self.assertEqual(entry.data_source_used, FoodEntry.DATA_SOURCE_USER_OVERRIDE)

    def test_repeated_correction_stops_producing_the_same_substitution(self):
        """The production loop: three corrections, three identical wrong rows."""
        for _ in range(3):
            self._log([_Result("Oikos Pro Banana", calories=130)],
                      food_name="banana", meal_type="breakfast")
        names = set(FoodEntry.objects.filter(user=self.user)
                    .values_list("food_name", flat=True))
        self.assertEqual(names, {"banana"})


class UnknownIsNotZeroTests(TestCase):
    """A gap must reach the model as a gap."""

    def setUp(self):
        self.user = User.objects.create_user(email="unk@contract.test", password="x")

    def _describe(self, **kw):
        from apps.health.services.nutrition_queries import NutritionQueries
        entry = FoodEntry.objects.create(
            user=self.user, food_name="anything", quantity=Decimal("1"),
            serving_size=Decimal("1"), serving_unit="serving",
            logged_date="2026-09-05", meal_type="lunch", **kw)
        return NutritionQueries._to_entity(entry)

    def test_an_unestablished_entry_reports_unknown_not_numbers(self):
        entity = self._describe(data_source_used=FoodEntry.DATA_SOURCE_UNKNOWN)
        self.assertEqual(entity.performance.get("nutrition"), "unknown")
        self.assertNotIn("calories", entity.performance,
                         "placeholder zeros were presented as measurements")

    def test_an_unestablished_entry_is_low_confidence(self):
        entity = self._describe(data_source_used=FoodEntry.DATA_SOURCE_UNKNOWN)
        self.assertEqual(entity.confidence, "low")

    def test_a_genuine_zero_calorie_food_keeps_its_measurement(self):
        """Black coffee is not a gap. Provenance decides, never the value."""
        entity = self._describe(data_source_used=FoodEntry.DATA_SOURCE_LOCAL,
                                total_calories=Decimal("0"))
        self.assertEqual(entity.performance["calories"], 0.0)
        self.assertEqual(entity.confidence, "high")

    def test_a_user_supplied_entry_stays_high_confidence(self):
        entity = self._describe(data_source_used=FoodEntry.DATA_SOURCE_USER_OVERRIDE,
                                total_calories=Decimal("420"))
        self.assertEqual(entity.performance["calories"], 420.0)


class MultiItemAuthorizationTests(TestCase):
    """A request naming two things cannot be finished by authorizing one."""

    def setUp(self):
        self.user = User.objects.create_user(email="multi@contract.test", password="x")
        from apps.ai.models import AssistantConversation
        self.conv = AssistantConversation.get_or_create_active(self.user)

    def _mint(self, food):
        from apps.ai.model_interface import confirmation as c
        return c.create(self.user, "log_food", {"food_name": food, "meal_type": "lunch"},
                        f"Log food — food name {food}, meal type lunch")

    def test_a_sibling_confirmation_is_no_longer_invisible(self):
        from apps.ai.model_interface import confirmation as c
        self._mint("first item")
        self._mint("second item")
        payload = c.bind_conversation(self.user, self.conv.id)
        self.assertIn("also_pending", payload,
                      "only one of two confirmations was surfaced")
        self.assertEqual(len(payload["also_pending"]), 1)

    def test_a_single_confirmation_is_unchanged(self):
        from apps.ai.model_interface import confirmation as c
        self._mint("only item")
        payload = c.bind_conversation(self.user, self.conv.id)
        self.assertNotIn("also_pending", payload)

    def test_resolving_one_reports_what_is_still_unauthorized(self):
        from apps.ai.cos_services import action_interface as ai
        first, second = self._mint("first item"), self._mint("second item")
        with mock.patch("apps.ai.cos_services.action_interface.execute_action",
                        return_value={"status": "ok", "message": "done"}):
            out = ai.resolve_pending_action(self.user, first["confirmation_id"],
                                            confirm=True)
        remaining = out.get("still_awaiting_authorization") or []
        self.assertEqual([r["confirmation_id"] for r in remaining],
                         [second["confirmation_id"]],
                         "a completed write reported no outstanding authorization")

    def test_resolving_the_last_one_reports_nothing_outstanding(self):
        from apps.ai.cos_services import action_interface as ai
        only = self._mint("only item")
        with mock.patch("apps.ai.cos_services.action_interface.execute_action",
                        return_value={"status": "ok", "message": "done"}):
            out = ai.resolve_pending_action(self.user, only["confirmation_id"],
                                            confirm=True)
        self.assertNotIn("still_awaiting_authorization", out)


class NoSpecialCasingTests(SimpleTestCase):
    """The incident nouns appear in the record of why, never in the logic."""

    def test_no_incident_noun_is_a_string_literal_in_the_changed_code(self):
        import ast
        import pathlib
        for path in ("apps/ai/action_handlers.py",
                     "apps/health/services/nutrition_queries.py",
                     "apps/ai/model_interface/confirmation.py"):
            tree = ast.parse(pathlib.Path(path).read_text(encoding="utf-8"))
            docs = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                                     ast.ClassDef)):
                    doc = ast.get_docstring(node, clean=False)
                    if doc:
                        docs.add(doc)
            literals = [n.value.lower() for n in ast.walk(tree)
                        if isinstance(n, ast.Constant) and isinstance(n.value, str)
                        and n.value not in docs]
            for noun in ("banana", "oikos", "mcalist", "mac and cheese", "sandwich"):
                for literal in literals:
                    self.assertNotIn(noun, literal,
                                     f"{path} special-cases {noun!r}")
