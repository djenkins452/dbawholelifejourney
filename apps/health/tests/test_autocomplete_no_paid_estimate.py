# ==============================================================================
# File: apps/health/tests/test_autocomplete_no_paid_estimate.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Autocomplete never buys an estimate; a person can still ask for one
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-09-08
# ==============================================================================
"""Estimating nutrition is a capability someone asks for, not something a text box does.

AI estimation was the automatic final tier of ordinary search: every query that matched
nothing spent an OpenAI call. The 1,585 AI-sourced rows in the production catalog are what
that looked like accumulated. The same automatic tier sat behind `log_food`, where a bought
guess becomes indistinguishable from a looked-up fact once it is stored.

Both are now explicit. No provider is called anywhere in this file.
"""

from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


def _onboarded(email):
    from apps.users.models import TermsAcceptance
    user = User.objects.create_user(email=email, password="pw")
    TermsAcceptance.objects.create(
        user=user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    prefs = getattr(user, "preferences", None)
    if prefs is not None:
        prefs.has_completed_onboarding = True
        prefs.save()
    return user


class AutocompleteTests(TestCase):
    def setUp(self):
        self.user = _onboarded("noai@contract.test")
        self.client.force_login(self.user)
        self.url = reverse("health:food_search_api")

    def _get(self, **params):
        with mock.patch("apps.health.services.food_search.food_search_service."
                        "_search_local", return_value=[]), \
             mock.patch("apps.health.services.food_search.food_search_service."
                        "_search_fatsecret", return_value=[]), \
             mock.patch("apps.health.services.food_search.food_search_service."
                        "_estimate_with_ai", return_value=None) as estimate:
            response = self.client.get(self.url, {"q": "a food nobody has", **params})
        return response, estimate

    def test_an_ordinary_search_never_reaches_the_paid_tier(self):
        _response, estimate = self._get()
        estimate.assert_not_called()

    def test_a_no_match_is_reported_honestly(self):
        response, _estimate = self._get()
        body = response.json()
        self.assertEqual(body["results"], [])
        self.assertTrue(body["no_match"])

    def test_the_estimate_is_offered_as_a_cue_not_taken(self):
        response, estimate = self._get()
        self.assertIn("Estimate with AI", response.json()["estimate_action"]["label"])
        estimate.assert_not_called()

    def test_an_explicit_request_is_the_only_way_to_reach_it(self):
        _response, estimate = self._get(estimate="1")
        estimate.assert_called_once()

    def test_the_cue_is_not_repeated_once_the_estimate_was_asked_for(self):
        response, _estimate = self._get(estimate="1")
        self.assertNotIn("estimate_action", response.json())

    def test_a_successful_search_offers_no_cue(self):
        from apps.health.services.food_search import FoodSearchResult
        hit = FoodSearchResult(id="local_1", name="Bananas, raw", brand="",
                               source="local", calories=89)
        with mock.patch("apps.health.services.food_search.food_search_service."
                        "_search_local", return_value=[hit]), \
             mock.patch("apps.health.services.food_search.food_search_service."
                        "_estimate_with_ai") as estimate:
            response = self.client.get(self.url, {"q": "banana"})
        estimate.assert_not_called()
        self.assertNotIn("no_match", response.json())


class WritePathTests(TestCase):
    def setUp(self):
        self.user = _onboarded("noaiw@contract.test")

    def test_logging_an_unknown_food_never_buys_an_estimate(self):
        from apps.ai.action_handlers import ActionHandler
        from apps.health.models import FoodEntry
        with mock.patch("apps.health.services.food_search.food_search_service."
                        "_estimate_with_ai") as estimate:
            ActionHandler(self.user).handle_log_food(
                food_name="something nobody has", meal_type="lunch")
        estimate.assert_not_called()
        entry = FoodEntry.objects.filter(user=self.user).latest("id")
        self.assertEqual(entry.food_name, "something nobody has")
        self.assertEqual(entry.data_source_used, FoodEntry.DATA_SOURCE_UNKNOWN)

    def test_a_person_supplied_value_is_still_recorded_as_theirs(self):
        """The explicit path the assistant uses once someone asks it to estimate."""
        from apps.ai.action_handlers import ActionHandler
        from apps.health.models import FoodEntry
        ActionHandler(self.user).handle_log_food(
            food_name="something nobody has", meal_type="lunch", calories=420)
        entry = FoodEntry.objects.filter(user=self.user).latest("id")
        self.assertEqual(float(entry.total_calories), 420.0)
        self.assertEqual(entry.data_source_used, FoodEntry.DATA_SOURCE_USER_OVERRIDE)

    def test_the_estimation_capability_still_exists(self):
        """Removed from the automatic path, not from the product."""
        from apps.health.services.ai_nutrition import ai_nutrition_service
        self.assertTrue(hasattr(ai_nutrition_service, "estimate_nutrition"))
        from apps.health.services.food_search import food_search_service
        self.assertTrue(hasattr(food_search_service, "_estimate_with_ai"))


class SeededCatalogTests(TestCase):
    """The bundled extract seeds generics; discovery finds them without any provider.

    Seeded explicitly here rather than by the migration, which deliberately skips test
    databases so 7,793 catalog rows do not become the baseline of every unrelated suite.
    """

    @classmethod
    def setUpTestData(cls):
        from io import StringIO

        from django.core.management import call_command
        call_command("import_usda_foods", stdout=StringIO())

    def test_the_bundled_extract_seeds_the_generic_catalog(self):
        from apps.health.models import FoodItem
        self.assertGreater(FoodItem.objects.filter(data_source="usda").count(), 5000)

    def test_a_plain_banana_is_discoverable_with_no_provider_at_all(self):
        from apps.health.services.food_search import food_search_service
        user = _onboarded("seed@contract.test")
        names = [r.name for r in food_search_service.search(
            query="banana", user=user, limit=10, use_fatsecret=False, use_ai=False)]
        self.assertTrue(any(n.lower().startswith("bananas, raw") for n in names),
                        f"no generic banana in {names[:5]}")

    def test_seeding_is_idempotent(self):
        from apps.health.models import FoodItem
        before = FoodItem.objects.filter(data_source="usda").count()
        from django.core.management import call_command
        from io import StringIO
        call_command("import_usda_foods", limit=50, stdout=StringIO())
        self.assertEqual(FoodItem.objects.filter(data_source="usda").count(), before)
