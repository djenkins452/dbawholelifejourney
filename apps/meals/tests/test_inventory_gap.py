"""
Tests for InventoryGapService.

Covers analyze_recipe_gaps, find_pantry_expiring_soon, and
decay_all_pantry_confidence across happy paths, edge cases,
multi-user isolation, confidence scoring, and diabetes awareness.
"""

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.meals.models import (
    Household,
    HouseholdMembership,
    Ingredient,
    PantryItem,
    RecipeIngredient,
)
from apps.meals.services.inventory_gap import (
    analyze_recipe_gaps,
    decay_all_pantry_confidence,
    find_pantry_expiring_soon,
)
from apps.users.models import User


class TestUserMixin:
    """Mixin to create test users with proper onboarding."""

    def create_user(self, email="test@example.com"):
        from apps.users.models import TermsAcceptance, UserPreferences
        user = User.objects.create_user(email=email, password="testpass123")
        TermsAcceptance.objects.create(user=user, terms_version="1.0")
        prefs, _ = UserPreferences.objects.get_or_create(user=user)
        prefs.has_completed_onboarding = True
        prefs.save(update_fields=["has_completed_onboarding"])
        return user


class MealsTestDataMixin(TestUserMixin):
    """Mixin providing standard test data for meals service tests."""

    def set_up_household(self, user=None, name="Test Household"):
        if user is None:
            user = self.create_user()
        household = Household.objects.create(name=name, primary_user=user)
        HouseholdMembership.objects.create(
            household=household, user=user, role="admin"
        )
        return user, household

    def create_recipe(self, user, title="Test Recipe", servings=4,
                      prep_time=10, cook_time=20):
        from apps.life.models import Recipe
        return Recipe.objects.create(
            user=user,
            title=title,
            ingredients="placeholder",
            instructions="Cook it.",
            servings=servings,
            prep_time_minutes=prep_time,
            cook_time_minutes=cook_time,
        )

    def create_ingredient(self, name, category="protein", **kwargs):
        return Ingredient.objects.create(
            canonical_name=name, category=category, **kwargs
        )

    def create_pantry_item(self, household, ingredient, quantity=Decimal("500"),
                           unit="g", **kwargs):
        defaults = {
            "confidence_score": Decimal("1.0"),
            "last_confirmed_at": timezone.now(),
        }
        defaults.update(kwargs)
        return PantryItem.objects.create(
            household=household,
            ingredient=ingredient,
            quantity=quantity,
            unit=unit,
            **defaults,
        )

    def link_recipe_ingredient(self, recipe, ingredient, quantity=Decimal("1"),
                               unit="piece", order_index=0, **kwargs):
        return RecipeIngredient.objects.create(
            recipe=recipe,
            ingredient=ingredient,
            quantity=quantity,
            unit=unit,
            order_index=order_index,
            **kwargs,
        )


# =============================================================================
# analyze_recipe_gaps tests
# =============================================================================

class TestAnalyzeRecipeGapsHappyPath(MealsTestDataMixin, TestCase):
    """Happy-path tests for analyze_recipe_gaps."""

    def setUp(self):
        self.user, self.household = self.set_up_household()
        self.recipe = self.create_recipe(self.user)
        self.chicken = self.create_ingredient("chicken breast", "protein")
        self.rice = self.create_ingredient("rice", "grain")
        self.salt = self.create_ingredient("salt", "spice")

    def test_all_ingredients_available(self):
        """When pantry has everything, availability_score should be 1.0."""
        self.link_recipe_ingredient(self.recipe, self.chicken, Decimal("2"), "piece", 0)
        self.link_recipe_ingredient(self.recipe, self.rice, Decimal("200"), "g", 1)
        self.link_recipe_ingredient(self.recipe, self.salt, Decimal("1"), "tsp", 2)

        self.create_pantry_item(self.household, self.chicken, Decimal("5"), "piece")
        self.create_pantry_item(self.household, self.rice, Decimal("1000"), "g")
        self.create_pantry_item(self.household, self.salt, Decimal("10"), "tsp")

        result = analyze_recipe_gaps(self.recipe, self.household)

        self.assertEqual(result.total_ingredients, 3)
        self.assertEqual(result.available_count, 3)
        self.assertEqual(result.missing_count, 0)
        self.assertEqual(result.partial_count, 0)
        self.assertEqual(result.availability_score, Decimal("1.0"))

    def test_all_ingredients_missing(self):
        """When pantry is empty, availability_score should be 0."""
        self.link_recipe_ingredient(self.recipe, self.chicken, Decimal("2"), "piece", 0)
        self.link_recipe_ingredient(self.recipe, self.rice, Decimal("200"), "g", 1)

        result = analyze_recipe_gaps(self.recipe, self.household)

        self.assertEqual(result.total_ingredients, 2)
        self.assertEqual(result.available_count, 0)
        self.assertEqual(result.missing_count, 2)
        self.assertEqual(result.availability_score, Decimal("0"))

    def test_partial_availability(self):
        """When pantry has less than needed, gap_type should be partial."""
        self.link_recipe_ingredient(self.recipe, self.rice, Decimal("500"), "g", 0)
        self.create_pantry_item(self.household, self.rice, Decimal("200"), "g")

        result = analyze_recipe_gaps(self.recipe, self.household)

        self.assertEqual(result.partial_count, 1)
        self.assertEqual(result.available_count, 0)
        gap = result.gaps[0]
        self.assertEqual(gap.gap_type, "partial")
        self.assertEqual(gap.available_quantity, Decimal("200"))
        self.assertEqual(gap.needed_quantity, Decimal("500"))

    def test_mixed_availability(self):
        """Mix of available, partial, and missing ingredients."""
        garlic = self.create_ingredient("garlic", "vegetable")
        self.link_recipe_ingredient(self.recipe, self.chicken, Decimal("2"), "piece", 0)
        self.link_recipe_ingredient(self.recipe, self.rice, Decimal("500"), "g", 1)
        self.link_recipe_ingredient(self.recipe, garlic, Decimal("3"), "clove", 2)

        # Chicken fully in stock
        self.create_pantry_item(self.household, self.chicken, Decimal("5"), "piece")
        # Rice partially in stock
        self.create_pantry_item(self.household, self.rice, Decimal("100"), "g")
        # Garlic missing entirely

        result = analyze_recipe_gaps(self.recipe, self.household)

        self.assertEqual(result.available_count, 1)
        self.assertEqual(result.partial_count, 1)
        self.assertEqual(result.missing_count, 1)
        # availability_score: 1 available out of 3
        self.assertAlmostEqual(float(result.availability_score), 0.333, places=2)

    def test_gap_analysis_returns_correct_recipe_info(self):
        """GapAnalysis should contain recipe_id and recipe_title."""
        self.link_recipe_ingredient(self.recipe, self.chicken, Decimal("1"), "piece", 0)
        result = analyze_recipe_gaps(self.recipe, self.household)
        self.assertEqual(result.recipe_id, self.recipe.id)
        self.assertEqual(result.recipe_title, self.recipe.title)


class TestAnalyzeRecipeGapsEdgeCases(MealsTestDataMixin, TestCase):
    """Edge cases for analyze_recipe_gaps."""

    def setUp(self):
        self.user, self.household = self.set_up_household()
        self.recipe = self.create_recipe(self.user)

    def test_recipe_with_no_structured_ingredients(self):
        """Recipes without structured ingredients return zero analysis."""
        result = analyze_recipe_gaps(self.recipe, self.household)
        self.assertEqual(result.total_ingredients, 0)
        self.assertEqual(result.availability_score, Decimal("0"))
        self.assertEqual(result.urgency_score, Decimal("0"))
        self.assertEqual(len(result.gaps), 0)

    def test_pantry_item_with_zero_quantity(self):
        """Zero-quantity pantry items should count as missing."""
        chicken = self.create_ingredient("chicken breast")
        self.link_recipe_ingredient(self.recipe, chicken, Decimal("2"), "piece", 0)
        self.create_pantry_item(self.household, chicken, Decimal("0"), "piece")

        result = analyze_recipe_gaps(self.recipe, self.household)
        self.assertEqual(result.missing_count, 1)
        gap = result.gaps[0]
        self.assertEqual(gap.gap_type, "missing")

    def test_null_quantity_ingredient_defaults_to_one(self):
        """RecipeIngredient with null quantity should default to 1."""
        salt = self.create_ingredient("salt", "spice")
        self.link_recipe_ingredient(self.recipe, salt, None, "to_taste", 0)

        result = analyze_recipe_gaps(self.recipe, self.household)
        gap = result.gaps[0]
        self.assertEqual(gap.needed_quantity, Decimal("1"))

    def test_different_units_treated_as_partial(self):
        """When pantry unit differs from recipe unit, treat as partial."""
        flour = self.create_ingredient("flour", "grain")
        self.link_recipe_ingredient(self.recipe, flour, Decimal("2"), "cup", 0)
        # Pantry has flour in grams, recipe needs cups
        self.create_pantry_item(self.household, flour, Decimal("500"), "g")

        result = analyze_recipe_gaps(self.recipe, self.household)
        self.assertEqual(result.partial_count, 1)
        gap = result.gaps[0]
        self.assertEqual(gap.gap_type, "partial")


class TestAnalyzeRecipeGapsExpiration(MealsTestDataMixin, TestCase):
    """Expiration and urgency scoring tests."""

    def setUp(self):
        self.user, self.household = self.set_up_household()
        self.recipe = self.create_recipe(self.user)

    def test_expiring_ingredient_detected(self):
        """Ingredient expiring within 3 days should be flagged."""
        milk = self.create_ingredient("milk", "dairy")
        self.link_recipe_ingredient(self.recipe, milk, Decimal("1"), "cup", 0)
        self.create_pantry_item(
            self.household, milk, Decimal("2"), "cup",
            expiration_date_estimated=timezone.now().date() + timezone.timedelta(days=2),
        )

        result = analyze_recipe_gaps(self.recipe, self.household)
        self.assertEqual(result.expiring_count, 1)
        self.assertGreater(result.urgency_score, Decimal("0"))
        gap = result.gaps[0]
        self.assertEqual(gap.gap_type, "expiring")
        self.assertIsNotNone(gap.days_until_expiration)

    def test_no_urgency_when_nothing_expiring(self):
        """Urgency score should be 0 when no items are expiring."""
        rice = self.create_ingredient("rice", "grain")
        self.link_recipe_ingredient(self.recipe, rice, Decimal("200"), "g", 0)
        self.create_pantry_item(
            self.household, rice, Decimal("1000"), "g",
            expiration_date_estimated=timezone.now().date() + timezone.timedelta(days=365),
        )

        result = analyze_recipe_gaps(self.recipe, self.household)
        self.assertEqual(result.urgency_score, Decimal("0"))
        self.assertEqual(result.expiring_count, 0)

    def test_urgency_capped_at_one(self):
        """Urgency score should never exceed 1.0 even with many expiring items."""
        ingredients = []
        for i in range(5):
            ing = self.create_ingredient(f"expiring_item_{i}", "dairy")
            ingredients.append(ing)
            self.link_recipe_ingredient(self.recipe, ing, Decimal("1"), "piece", i)
            self.create_pantry_item(
                self.household, ing, Decimal("5"), "piece",
                expiration_date_estimated=timezone.now().date() + timezone.timedelta(days=1),
            )

        result = analyze_recipe_gaps(self.recipe, self.household)
        self.assertLessEqual(result.urgency_score, Decimal("1.0"))

    def test_already_expired_item_not_flagged_as_expiring(self):
        """Items past expiration should NOT be flagged as 'expiring' (days <= 0)."""
        milk = self.create_ingredient("old milk", "dairy")
        self.link_recipe_ingredient(self.recipe, milk, Decimal("1"), "cup", 0)
        self.create_pantry_item(
            self.household, milk, Decimal("2"), "cup",
            expiration_date_estimated=timezone.now().date() - timezone.timedelta(days=1),
        )

        result = analyze_recipe_gaps(self.recipe, self.household)
        # Already expired: days_until_expiration < 0, so is_expiring = False
        self.assertEqual(result.expiring_count, 0)


class TestAnalyzeRecipeGapsMultiUser(MealsTestDataMixin, TestCase):
    """Multi-user isolation tests for gap analysis."""

    def test_different_households_have_isolated_pantries(self):
        """User A's pantry should not affect User B's gap analysis."""
        user_a, household_a = self.set_up_household(
            self.create_user("a@test.com"), "Household A"
        )
        user_b, household_b = self.set_up_household(
            self.create_user("b@test.com"), "Household B"
        )

        chicken = self.create_ingredient("chicken breast")
        recipe_a = self.create_recipe(user_a, "Recipe A")
        recipe_b = self.create_recipe(user_b, "Recipe B")

        self.link_recipe_ingredient(recipe_a, chicken, Decimal("2"), "piece", 0)
        self.link_recipe_ingredient(recipe_b, chicken, Decimal("2"), "piece", 0)

        # Only Household A has chicken
        self.create_pantry_item(household_a, chicken, Decimal("5"), "piece")

        result_a = analyze_recipe_gaps(recipe_a, household_a)
        result_b = analyze_recipe_gaps(recipe_b, household_b)

        self.assertEqual(result_a.available_count, 1)
        self.assertEqual(result_a.missing_count, 0)

        self.assertEqual(result_b.available_count, 0)
        self.assertEqual(result_b.missing_count, 1)


class TestAnalyzeRecipeGapsConfidence(MealsTestDataMixin, TestCase):
    """Confidence scoring in gap analysis."""

    def test_low_confidence_pantry_item_reported(self):
        """Gap items should carry the pantry item's confidence score."""
        user, household = self.set_up_household()
        recipe = self.create_recipe(user)
        rice = self.create_ingredient("rice", "grain")

        self.link_recipe_ingredient(recipe, rice, Decimal("200"), "g", 0)
        self.create_pantry_item(
            household, rice, Decimal("500"), "g",
            confidence_score=Decimal("0.30"),
        )

        result = analyze_recipe_gaps(recipe, household)
        gap = result.gaps[0]
        self.assertEqual(gap.confidence, Decimal("0.30"))

    def test_missing_item_has_full_confidence(self):
        """Missing items should report confidence 1.0 (certain they are missing)."""
        user, household = self.set_up_household()
        recipe = self.create_recipe(user)
        chicken = self.create_ingredient("chicken breast")
        self.link_recipe_ingredient(recipe, chicken, Decimal("2"), "piece", 0)

        result = analyze_recipe_gaps(recipe, household)
        gap = result.gaps[0]
        self.assertEqual(gap.confidence, Decimal("1.0"))


# =============================================================================
# find_pantry_expiring_soon tests
# =============================================================================

class TestFindPantryExpiringSoon(MealsTestDataMixin, TestCase):
    """Tests for find_pantry_expiring_soon."""

    def setUp(self):
        self.user, self.household = self.set_up_household()

    def test_finds_items_expiring_within_default_window(self):
        """Default 3-day window should find items expiring in 1-3 days."""
        milk = self.create_ingredient("milk", "dairy")
        self.create_pantry_item(
            self.household, milk, Decimal("1"), "piece",
            expiration_date_estimated=timezone.now().date() + timezone.timedelta(days=2),
        )

        results = find_pantry_expiring_soon(self.household)
        self.assertEqual(results.count(), 1)
        self.assertEqual(results.first().ingredient.canonical_name, "milk")

    def test_excludes_already_expired(self):
        """Already-expired items should not appear."""
        old_milk = self.create_ingredient("old milk", "dairy")
        self.create_pantry_item(
            self.household, old_milk, Decimal("1"), "piece",
            expiration_date_estimated=timezone.now().date() - timezone.timedelta(days=1),
        )

        results = find_pantry_expiring_soon(self.household)
        self.assertEqual(results.count(), 0)

    def test_excludes_zero_quantity_items(self):
        """Items with no remaining quantity should not appear."""
        milk = self.create_ingredient("milk", "dairy")
        self.create_pantry_item(
            self.household, milk, Decimal("0"), "piece",
            expiration_date_estimated=timezone.now().date() + timezone.timedelta(days=1),
        )

        results = find_pantry_expiring_soon(self.household)
        self.assertEqual(results.count(), 0)

    def test_custom_days_window(self):
        """Custom window of 7 days should catch more items."""
        bread = self.create_ingredient("bread", "grain")
        self.create_pantry_item(
            self.household, bread, Decimal("1"), "piece",
            expiration_date_estimated=timezone.now().date() + timezone.timedelta(days=5),
        )

        results_3 = find_pantry_expiring_soon(self.household, days=3)
        results_7 = find_pantry_expiring_soon(self.household, days=7)

        self.assertEqual(results_3.count(), 0)
        self.assertEqual(results_7.count(), 1)

    def test_ordered_by_expiration_date(self):
        """Results should be ordered by soonest expiration first."""
        ing_a = self.create_ingredient("item_a", "dairy")
        ing_b = self.create_ingredient("item_b", "dairy")

        self.create_pantry_item(
            self.household, ing_b, Decimal("1"), "piece",
            expiration_date_estimated=timezone.now().date() + timezone.timedelta(days=3),
        )
        self.create_pantry_item(
            self.household, ing_a, Decimal("1"), "piece",
            expiration_date_estimated=timezone.now().date() + timezone.timedelta(days=1),
        )

        results = list(find_pantry_expiring_soon(self.household))
        self.assertEqual(results[0].ingredient.canonical_name, "item_a")
        self.assertEqual(results[1].ingredient.canonical_name, "item_b")

    def test_empty_pantry(self):
        """Empty pantry returns no results."""
        results = find_pantry_expiring_soon(self.household)
        self.assertEqual(results.count(), 0)


# =============================================================================
# decay_all_pantry_confidence tests
# =============================================================================

class TestDecayAllPantryConfidence(MealsTestDataMixin, TestCase):
    """Tests for decay_all_pantry_confidence."""

    def setUp(self):
        self.user, self.household = self.set_up_household()

    def test_decays_old_items(self):
        """Items confirmed > 3 days ago should have reduced confidence."""
        flour = self.create_ingredient("flour", "grain")
        self.create_pantry_item(
            self.household, flour, Decimal("500"), "g",
            last_confirmed_at=timezone.now() - timezone.timedelta(days=10),
        )

        count = decay_all_pantry_confidence(self.household)
        self.assertEqual(count, 1)

        item = PantryItem.objects.get(
            household=self.household, ingredient=flour
        )
        self.assertLess(item.confidence_score, Decimal("1.0"))

    def test_does_not_decay_recent_items(self):
        """Items confirmed within 3 days should keep full confidence."""
        sugar = self.create_ingredient("sugar", "sweetener")
        self.create_pantry_item(
            self.household, sugar, Decimal("200"), "g",
            last_confirmed_at=timezone.now() - timezone.timedelta(days=1),
        )

        count = decay_all_pantry_confidence(self.household)
        self.assertEqual(count, 0)

        item = PantryItem.objects.get(
            household=self.household, ingredient=sugar
        )
        self.assertEqual(item.confidence_score, Decimal("1.0"))

    def test_does_not_decay_empty_items(self):
        """Items with zero quantity should be skipped."""
        flour = self.create_ingredient("flour", "grain")
        self.create_pantry_item(
            self.household, flour, Decimal("0"), "g",
            last_confirmed_at=timezone.now() - timezone.timedelta(days=20),
        )

        count = decay_all_pantry_confidence(self.household)
        self.assertEqual(count, 0)

    def test_confidence_minimum_is_0_10(self):
        """Confidence should never drop below 0.10."""
        flour = self.create_ingredient("flour", "grain")
        self.create_pantry_item(
            self.household, flour, Decimal("500"), "g",
            last_confirmed_at=timezone.now() - timezone.timedelta(days=100),
        )

        decay_all_pantry_confidence(self.household)

        item = PantryItem.objects.get(
            household=self.household, ingredient=flour
        )
        self.assertGreaterEqual(item.confidence_score, Decimal("0.10"))

    def test_bulk_update_multiple_items(self):
        """Multiple items should all be decayed in one pass."""
        items_data = [
            ("old_flour", 15),
            ("old_sugar", 20),
            ("old_milk", 25),
        ]
        for name, days_old in items_data:
            ing = self.create_ingredient(name, "grain")
            self.create_pantry_item(
                self.household, ing, Decimal("100"), "g",
                last_confirmed_at=timezone.now() - timezone.timedelta(days=days_old),
            )

        count = decay_all_pantry_confidence(self.household)
        self.assertEqual(count, 3)

        for name, _ in items_data:
            item = PantryItem.objects.get(
                ingredient__canonical_name=name,
                household=self.household,
            )
            self.assertLess(item.confidence_score, Decimal("1.0"))

    def test_household_isolation_for_decay(self):
        """Decay in household A should not affect household B."""
        user_b = self.create_user("b@test.com")
        household_b = Household.objects.create(
            name="Household B", primary_user=user_b
        )

        flour = self.create_ingredient("flour", "grain")
        self.create_pantry_item(
            self.household, flour, Decimal("500"), "g",
            last_confirmed_at=timezone.now() - timezone.timedelta(days=10),
        )
        self.create_pantry_item(
            household_b, flour, Decimal("500"), "g",
            last_confirmed_at=timezone.now() - timezone.timedelta(days=10),
        )

        decay_all_pantry_confidence(self.household)

        item_a = PantryItem.objects.get(
            household=self.household, ingredient=flour
        )
        item_b = PantryItem.objects.get(
            household=household_b, ingredient=flour
        )

        self.assertLess(item_a.confidence_score, Decimal("1.0"))
        # Household B should still have full confidence (not decayed)
        self.assertEqual(item_b.confidence_score, Decimal("1.0"))
