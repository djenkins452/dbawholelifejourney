# ==============================================================================
# File: apps/core/tests/test_multi_item_food_lifecycle_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: N requested foods stay one action, one authorization, N verified writes
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-09-05
# ==============================================================================
"""One request naming two foods is one user action, and must survive as one.

Production 2026-09-05: "Log McAlistairs Ham and Cheese sandwich and mac and cheese for
lunch." The model minted two independent confirmations a second apart. The client displays
the newest, so only the mac and cheese was ever shown; one "yes" resolves exactly one
confirmation; the sandwich expired unseen while the assistant reported the request done.

Nothing was wrong with either write. The requested SET was never a thing the system could
hold, so it could not be authorized, executed or verified as one.

`items` binds the whole set to a single action, which mints a single confirmation whose
authorization line enumerates every food. One "yes" authorizes exactly that set; each food
is then written and verified independently; and the result reports per item, so a partial
write is reported as partial.

Every guarantee the single-food path makes still applies to each member — exact identity,
unknown-is-not-zero, post-write verification. No provider calls.
"""

from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.ai.action_handlers import ActionHandler
from apps.ai.confirmation_contract import authorization_line
from apps.health.models import FoodEntry

User = get_user_model()


class _Result:
    def __init__(self, name, calories=None, source="custom"):
        self.name = name
        self.calories = calories
        self.source = source
        self.food_item_id = None
        for attr in ("protein_g", "carbohydrates_g", "fat_g", "fiber_g", "sugar_g",
                     "serving_size", "serving_unit"):
            setattr(self, attr, None)


class AuthorizationNamesTheWholeSetTests(SimpleTestCase):
    """The user must see everything they are authorizing."""

    def test_every_member_is_named(self):
        line = authorization_line("log_food", {
            "items": [{"food_name": "ham and cheese sandwich"},
                      {"food_name": "mac and cheese"}],
            "meal_type": "lunch"})
        self.assertIn("ham and cheese sandwich", line)
        self.assertIn("mac and cheese", line)
        self.assertIn("2 items", line)
        self.assertIn("lunch", line)

    def test_three_members_are_all_named(self):
        line = authorization_line("log_food", {"items": [
            {"food_name": "a"}, {"food_name": "b"}, {"food_name": "c"}]})
        for name in ("a", "b", "c"):
            self.assertIn(name, line)
        self.assertIn("3 items", line)

    def test_a_long_set_states_its_true_count(self):
        """A truncated list must never read as the whole set."""
        line = authorization_line("log_food", {
            "items": [{"food_name": f"food {i}"} for i in range(20)]})
        self.assertIn("20 items", line)
        self.assertIn("more", line)

    def test_the_single_food_line_is_unchanged(self):
        line = authorization_line("log_food", {"food_name": "banana",
                                               "meal_type": "breakfast"})
        self.assertIn("banana", line)
        self.assertNotIn("items", line)

    def test_the_set_renderer_names_no_domain(self):
        import ast
        import inspect
        import textwrap

        from apps.ai.confirmation_contract import _bound_set_line
        tree = ast.parse(textwrap.dedent(inspect.getsource(_bound_set_line)))
        fn = tree.body[0]
        body = fn.body[1:] if ast.get_docstring(fn) else fn.body
        code = "\n".join(ast.unparse(n) for n in body).lower()
        for word in ("food", "meal", "sandwich", "task"):
            self.assertNotIn(f'"{word}"', code)


class ExecutionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="multi@food.test", password="x")
        self.handler = ActionHandler(self.user)

    def _log(self, results=(), **kw):
        service = mock.Mock()
        service.search.return_value = list(results)
        with mock.patch("apps.health.services.food_search.food_search_service", service):
            return self.handler.handle_log_food(**kw)

    def _names(self):
        return sorted(FoodEntry.objects.filter(user=self.user)
                      .values_list("food_name", flat=True))

    def test_two_foods_produce_two_canonical_rows(self):
        out = self._log(items=[{"food_name": "ham and cheese sandwich"},
                               {"food_name": "mac and cheese"}], meal_type="lunch")
        self.assertTrue(out.success)
        self.assertEqual(self._names(), ["ham and cheese sandwich", "mac and cheese"])
        self.assertTrue(out.data["complete"])

    def test_three_foods_produce_three_canonical_rows(self):
        self._log(items=[{"food_name": "a"}, {"food_name": "b"}, {"food_name": "c"}],
                  meal_type="dinner")
        self.assertEqual(self._names(), ["a", "b", "c"])

    def test_the_meal_type_applies_to_every_item(self):
        self._log(items=[{"food_name": "a"}, {"food_name": "b"}], meal_type="lunch")
        self.assertEqual(
            set(FoodEntry.objects.filter(user=self.user)
                .values_list("meal_type", flat=True)), {"lunch"})

    def test_an_item_may_override_the_shared_meal_type(self):
        self._log(items=[{"food_name": "a"},
                         {"food_name": "b", "meal_type": "snack"}], meal_type="lunch")
        by_name = dict(FoodEntry.objects.filter(user=self.user)
                       .values_list("food_name", "meal_type"))
        self.assertEqual(by_name, {"a": "lunch", "b": "snack"})

    def test_per_item_nutrition_is_honoured(self):
        self._log(items=[{"food_name": "a", "calories": 300},
                         {"food_name": "b", "calories": 150}], meal_type="lunch")
        by_name = dict(FoodEntry.objects.filter(user=self.user)
                       .values_list("food_name", "total_calories"))
        self.assertEqual(by_name["a"], Decimal("300"))
        self.assertEqual(by_name["b"], Decimal("150"))

    def test_one_item_failing_does_not_stop_the_others(self):
        real = self.handler.handle_log_food

        def _flaky(**kw):
            if kw.get("food_name") == "b":
                raise RuntimeError("this one breaks")
            return real(**kw)

        with mock.patch.object(self.handler, "handle_log_food", side_effect=_flaky):
            out = ActionHandler.handle_log_food(
                self.handler, items=[{"food_name": "a"}, {"food_name": "b"},
                                     {"food_name": "c"}], meal_type="lunch")
        self.assertEqual(self._names(), ["a", "c"])
        self.assertEqual([f["food_name"] for f in out.data["failed"]], ["b"])
        self.assertEqual(len(out.data["logged"]), 2)

    def test_a_partial_write_is_never_reported_as_success(self):
        real = self.handler.handle_log_food

        def _flaky(**kw):
            if kw.get("food_name") == "b":
                raise RuntimeError("nope")
            return real(**kw)

        with mock.patch.object(self.handler, "handle_log_food", side_effect=_flaky):
            out = ActionHandler.handle_log_food(
                self.handler, items=[{"food_name": "a"}, {"food_name": "b"}],
                meal_type="lunch")
        self.assertFalse(out.success, "a partial write was narrated as complete")
        self.assertEqual(out.error, "partial_write")
        self.assertFalse(out.data["complete"])
        self.assertIn("b", out.message)
        self.assertIn("1 of 2", out.message)

    def test_no_requested_item_silently_disappears(self):
        out = self._log(items=[{"food_name": "a"}, {"food_name": "b"},
                               {"food_name": "c"}], meal_type="lunch")
        self.assertEqual(out.data["requested_count"], 3)
        self.assertEqual(len(out.data["logged"]) + len(out.data["failed"]), 3)

    def test_no_cross_item_identity_substitution(self):
        """Each member keeps its own name; a near-match on one cannot rename another."""
        self._log(results=[_Result("Oikos Pro Banana", calories=130)],
                  items=[{"food_name": "banana"}, {"food_name": "toast"}],
                  meal_type="breakfast")
        self.assertEqual(self._names(), ["banana", "toast"])

    def test_unknown_nutrition_stays_unknown_for_every_member(self):
        self._log(items=[{"food_name": "a"}, {"food_name": "b"}], meal_type="lunch")
        self.assertEqual(
            set(FoodEntry.objects.filter(user=self.user)
                .values_list("data_source_used", flat=True)),
            {FoodEntry.DATA_SOURCE_UNKNOWN})

    def test_every_member_is_postcondition_verified(self):
        """Each item goes through the single-food path, which verifies its own write."""
        out = self._log(items=[{"food_name": "a"}, {"food_name": "b"}], meal_type="lunch")
        for entry in out.data["logged"]:
            self.assertTrue(FoodEntry.objects.filter(
                user=self.user, food_name=entry["food_name"]).exists())

    def test_an_empty_set_is_rejected_rather_than_silently_doing_nothing(self):
        out = self._log(items=[{"quantity": 2}], meal_type="lunch")
        self.assertFalse(out.success)
        self.assertEqual(FoodEntry.objects.filter(user=self.user).count(), 0)

    def test_an_absurd_set_is_bounded(self):
        out = self._log(items=[{"food_name": f"f{i}"} for i in range(40)])
        self.assertFalse(out.success)
        self.assertEqual(FoodEntry.objects.filter(user=self.user).count(), 0)

    def test_a_single_food_call_still_works_exactly_as_before(self):
        out = self._log(food_name="banana", meal_type="breakfast")
        self.assertTrue(out.success)
        self.assertEqual(self._names(), ["banana"])


class ConfirmationLifecycleTests(TestCase):
    """One set, one confirmation, one authorization — and it is single-use."""

    def setUp(self):
        self.user = User.objects.create_user(email="conf@food.test", password="x")
        from apps.ai.models import AssistantConversation
        self.conv = AssistantConversation.get_or_create_active(self.user)
        self.params = {"items": [{"food_name": "ham and cheese sandwich"},
                                 {"food_name": "mac and cheese"}],
                       "meal_type": "lunch"}

    def _mint(self):
        from apps.ai.model_interface import confirmation as c
        return c.create(self.user, "log_food", self.params,
                        c.summarize("log_food", self.params))

    def test_a_two_food_request_mints_exactly_one_confirmation(self):
        from apps.ai.model_interface import confirmation as c
        self._mint()
        self.assertEqual(len(c.list_open(self.user)), 1)

    def test_nothing_is_left_pending_after_the_single_yes(self):
        from apps.ai.cos_services import action_interface as ai
        from apps.ai.model_interface import confirmation as c
        handle = self._mint()
        with mock.patch("apps.ai.cos_services.action_interface.execute_action",
                        return_value={"status": "ok", "message": "2 of 2 logged"}):
            out = ai.resolve_pending_action(self.user, handle["confirmation_id"],
                                            confirm=True)
        self.assertNotIn("still_awaiting_authorization", out)
        self.assertEqual(c.list_open(self.user), [])

    def test_the_authorization_the_user_sees_names_both_foods(self):
        from apps.ai.model_interface import confirmation as c
        handle = self._mint()
        line = handle.get("authorization") or ""
        self.assertIn("ham and cheese sandwich", line)
        self.assertIn("mac and cheese", line)
        c.list_open(self.user)

    def test_cancelling_writes_nothing(self):
        from apps.ai.cos_services import action_interface as ai
        handle = self._mint()
        with mock.patch("apps.ai.cos_services.action_interface.execute_action") as ex:
            ai.resolve_pending_action(self.user, handle["confirmation_id"], confirm=False)
        ex.assert_not_called()
        self.assertEqual(FoodEntry.objects.filter(user=self.user).count(), 0)

    def test_confirming_twice_replays_rather_than_writing_the_set_again(self):
        from apps.ai.cos_services import action_interface as ai
        handle = self._mint()
        with mock.patch("apps.ai.cos_services.action_interface.execute_action",
                        return_value={"status": "ok", "message": "2 of 2 logged"}) as ex:
            first = ai.resolve_pending_action(self.user, handle["confirmation_id"],
                                              confirm=True)
            second = ai.resolve_pending_action(self.user, handle["confirmation_id"],
                                               confirm=True)
        self.assertEqual(ex.call_count, 1, "the authorized set executed twice")
        self.assertEqual(first.get("status"), second.get("status"))
