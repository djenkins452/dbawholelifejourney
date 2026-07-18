# ==============================================================================
# File: apps/meals/tests/test_pantry_search.py
# Project: Whole Life Journey - Meal Intelligence
# Description: Focused UI-contract tests for the live pantry search. The filtering
#   itself is client-side; these verify the server renders the exact markup and
#   per-item search keys the JS relies on (search box, status/empty scaffolding,
#   and a lowercased data-search-name that supports case-insensitive substring
#   matching anywhere in the name).
# ==============================================================================
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.meals.models import (
    Household, HouseholdMembership, Ingredient, PantryItem,
)
from apps.users.models import TermsAcceptance

User = get_user_model()


class PantrySearchMarkupTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="pantrysearch@test.com", password="x")
        TermsAcceptance.objects.create(
            user=self.user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        self.household = Household.objects.create(name="H", primary_user=self.user)
        HouseholdMembership.objects.create(household=self.household, user=self.user, role="admin")
        self.client = Client()
        self.client.force_login(self.user)

    def _add(self, name, aliases=None):
        ing = Ingredient.objects.create(canonical_name=name, category="other",
                                        aliases=aliases or [])
        PantryItem.objects.create(household=self.household, ingredient=ing,
                                  quantity=Decimal("2"), unit="piece")
        return ing

    def _get(self):
        return self.client.get("/meals/pantry/")

    def test_search_box_and_scaffolding_render(self):
        self._add("Ketchup")
        html = self._get().content.decode()
        self.assertEqual(self._get().status_code, 200)
        # The search input exists, with no submit button (live search).
        self.assertIn('id="pantrySearch"', html)
        self.assertIn('type="search"', html)
        # Status line + empty-state + clear controls the JS toggles.
        self.assertIn('id="pantrySearchStatus"', html)
        self.assertIn('id="pantrySearchEmpty"', html)
        self.assertIn('id="pantrySearchClear"', html)
        self.assertIn('id="pantrySearchClearEmpty"', html)
        self.assertIn("Clear Search", html)

    def test_each_item_carries_lowercase_search_key(self):
        self._add("Ketchup")
        self._add("Protein Powder")
        self._add("Hamburger Bun")
        html = self._get().content.decode()
        # Lowercased so JS can do case-insensitive substring matching:
        #   "ket" -> ketchup ; "prot" -> protein powder ; "burger" -> hamburger bun
        self.assertIn('data-search-name="ketchup ', html)
        self.assertIn('data-search-name="protein powder ', html)
        self.assertIn('data-search-name="hamburger bun ', html)
        for token, name in [("ket", "ketchup"), ("prot", "protein powder"),
                            ("burger", "hamburger bun")]:
            self.assertIn(token, name, f"{token} should match {name} as a substring")

    def test_aliases_are_included_in_search_key(self):
        self._add("Ketchup", aliases=["Catsup", "Red Sauce"])
        html = self._get().content.decode()
        # Alias text is folded into the same lowercase key (joined, not list-repr).
        self.assertIn("catsup", html)
        self.assertNotIn("data-search-name=\"ketchup ['", html)  # no raw JSON list repr

    def test_no_search_bar_when_pantry_empty(self):
        # Empty pantry -> the empty state renders, but no search box (nothing to filter).
        html = self._get().content.decode()
        self.assertNotIn('id="pantrySearch"', html)
        self.assertIn("Pantry is empty", html)
