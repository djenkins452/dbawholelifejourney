"""
Tests for RecipeNutritionService.

Covers calculate_recipe_nutrition, invalidate_recipe_nutrition_cache,
get_recipe_macro_summary across happy paths, edge cases, caching,
multi-user isolation, confidence scoring, and diabetes flagging.
"""

from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase

from apps.health.models import FoodItem
from apps.meals.models import Ingredient, RecipeIngredient
from apps.meals.services.recipe_nutrition import (
    CACHE_PREFIX,
    calculate_recipe_nutrition,
    get_recipe_macro_summary,
    invalidate_recipe_nutrition_cache,
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


class NutritionTestDataMixin(TestUserMixin):
    """Provides standard test data for recipe nutrition tests."""

    def create_recipe(self, user, title="Test Recipe", servings=4):
        from apps.life.models import Recipe
        return Recipe.objects.create(
            user=user,
            title=title,
            ingredients="placeholder",
            instructions="Cook it.",
            servings=servings,
        )

    def create_food_item(self, name, calories=100, protein_g=20,
                         carbohydrates_g=5, fat_g=3, **kwargs):
        defaults = {
            "name": name,
            "serving_size": 100,
            "serving_unit": "g",
            "calories": calories,
            "protein_g": protein_g,
            "carbohydrates_g": carbohydrates_g,
            "fat_g": fat_g,
            "fiber_g": 0,
            "sugar_g": 0,
            "saturated_fat_g": 1,
            "unsaturated_fat_g": 1,
            "trans_fat_g": 0,
        }
        defaults.update(kwargs)
        return FoodItem.objects.create(**defaults)

    def create_ingredient_with_food(self, name, category="protein",
                                    food_item=None, **food_kwargs):
        if food_item is None:
            food_item = self.create_food_item(name, **food_kwargs)
        return Ingredient.objects.create(
            canonical_name=name,
            category=category,
            nutrition_source=food_item,
        )

    def link_recipe_ingredient(self, recipe, ingredient, quantity=Decimal("1"),
                               unit="piece", order_index=0):
        return RecipeIngredient.objects.create(
            recipe=recipe,
            ingredient=ingredient,
            quantity=quantity,
            unit=unit,
            order_index=order_index,
        )


# =============================================================================
# calculate_recipe_nutrition tests
# =============================================================================

class TestCalculateRecipeNutrition(NutritionTestDataMixin, TestCase):
    """Core tests for calculate_recipe_nutrition."""

    def setUp(self):
        self.user = self.create_user()
        self.recipe = self.create_recipe(self.user, servings=2)
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_basic_nutrition_calculation(self):
        """Single ingredient with known nutrition should calculate correctly."""
        chicken = self.create_ingredient_with_food(
            "chicken breast", "protein",
            calories=165, protein_g=31, carbohydrates_g=0, fat_g=3.6,
        )
        self.link_recipe_ingredient(self.recipe, chicken, Decimal("2"), "piece", 0)

        result = calculate_recipe_nutrition(self.recipe, use_cache=False)

        # Total: 2 * 165 = 330 calories
        self.assertEqual(result.total["calories"], Decimal("330.00"))
        self.assertEqual(result.total["protein_g"], Decimal("62.00"))
        # Per serving (2 servings): 165 cal
        self.assertEqual(result.per_serving["calories"], Decimal("165.00"))

    def test_multiple_ingredients_aggregation(self):
        """Multiple ingredients should sum up correctly."""
        chicken = self.create_ingredient_with_food(
            "chicken breast", "protein",
            calories=165, protein_g=31, carbohydrates_g=0, fat_g=3,
        )
        rice = self.create_ingredient_with_food(
            "rice", "grain",
            calories=130, protein_g=2.7, carbohydrates_g=28, fat_g=0.3,
        )

        self.link_recipe_ingredient(self.recipe, chicken, Decimal("1"), "piece", 0)
        self.link_recipe_ingredient(self.recipe, rice, Decimal("1"), "piece", 1)

        result = calculate_recipe_nutrition(self.recipe, use_cache=False)

        expected_total_cal = Decimal("165") + Decimal("130")
        self.assertEqual(result.total["calories"], expected_total_cal)
        self.assertEqual(result.ingredient_count, 2)
        self.assertEqual(result.linked_count, 2)

    def test_servings_division(self):
        """Per-serving values should divide total by servings count."""
        recipe = self.create_recipe(self.user, servings=4)
        rice = self.create_ingredient_with_food(
            "rice", "grain",
            calories=400, protein_g=8, carbohydrates_g=80, fat_g=1,
        )
        self.link_recipe_ingredient(recipe, rice, Decimal("1"), "piece", 0)

        result = calculate_recipe_nutrition(recipe, use_cache=False)

        self.assertEqual(result.per_serving["calories"], Decimal("100.00"))
        self.assertEqual(result.per_serving["carbohydrates_g"], Decimal("20.00"))
        self.assertEqual(result.servings, 4)

    def test_quantity_scaling(self):
        """Quantity multiplies the nutrient values."""
        oil = self.create_ingredient_with_food(
            "olive oil", "fat",
            calories=120, protein_g=0, carbohydrates_g=0, fat_g=14,
        )
        self.link_recipe_ingredient(self.recipe, oil, Decimal("3"), "tbsp", 0)

        result = calculate_recipe_nutrition(self.recipe, use_cache=False)

        # 3 * 120 = 360 total calories
        self.assertEqual(result.total["calories"], Decimal("360.00"))
        self.assertEqual(result.total["fat_g"], Decimal("42.00"))

    def test_null_quantity_defaults_to_one(self):
        """RecipeIngredient with null quantity should use 1 as default."""
        salt_food = self.create_food_item("salt", calories=0, protein_g=0,
                                          carbohydrates_g=0, fat_g=0)
        salt = Ingredient.objects.create(
            canonical_name="salt", category="spice",
            nutrition_source=salt_food,
        )
        RecipeIngredient.objects.create(
            recipe=self.recipe, ingredient=salt,
            quantity=None, unit="to_taste", order_index=0,
        )

        result = calculate_recipe_nutrition(self.recipe, use_cache=False)
        self.assertEqual(result.ingredient_count, 1)
        self.assertEqual(result.linked_count, 1)

    def test_null_servings_defaults_to_one(self):
        """Recipe with null servings should use 1."""
        recipe = self.create_recipe(self.user, servings=None)
        rice = self.create_ingredient_with_food(
            "rice", "grain",
            calories=200, protein_g=4, carbohydrates_g=44, fat_g=0.5,
        )
        self.link_recipe_ingredient(recipe, rice, Decimal("1"), "piece", 0)

        result = calculate_recipe_nutrition(recipe, use_cache=False)

        # With servings=1 (default), per_serving == total
        self.assertEqual(result.per_serving["calories"], result.total["calories"])


class TestRecipeNutritionEdgeCases(NutritionTestDataMixin, TestCase):
    """Edge case tests for nutrition calculation."""

    def setUp(self):
        self.user = self.create_user()
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_no_structured_ingredients(self):
        """Recipe with no structured ingredients returns zero nutrition."""
        recipe = self.create_recipe(self.user)
        result = calculate_recipe_nutrition(recipe, use_cache=False)

        self.assertEqual(result.ingredient_count, 0)
        self.assertEqual(result.linked_count, 0)
        self.assertEqual(result.confidence, Decimal("0"))
        self.assertEqual(result.total["calories"], Decimal("0"))

    def test_ingredient_without_food_item_link(self):
        """Unlinked ingredient should generate a warning."""
        unlinked = Ingredient.objects.create(
            canonical_name="mystery spice", category="spice",
            nutrition_source=None,
        )
        recipe = self.create_recipe(self.user)
        self.link_recipe_ingredient(recipe, unlinked, Decimal("1"), "tsp", 0)

        result = calculate_recipe_nutrition(recipe, use_cache=False)

        self.assertEqual(result.ingredient_count, 1)
        self.assertEqual(result.linked_count, 0)
        self.assertIn("No nutrition data", result.warnings[0])

    def test_mixed_linked_and_unlinked(self):
        """Mix of linked and unlinked ingredients should have partial confidence."""
        recipe = self.create_recipe(self.user, servings=1)
        chicken = self.create_ingredient_with_food(
            "chicken breast", "protein",
            calories=165, protein_g=31, carbohydrates_g=0, fat_g=3,
        )
        unknown = Ingredient.objects.create(
            canonical_name="special sauce", category="condiment",
            nutrition_source=None,
        )

        self.link_recipe_ingredient(recipe, chicken, Decimal("1"), "piece", 0)
        self.link_recipe_ingredient(recipe, unknown, Decimal("1"), "tbsp", 1)

        result = calculate_recipe_nutrition(recipe, use_cache=False)

        self.assertEqual(result.ingredient_count, 2)
        self.assertEqual(result.linked_count, 1)
        self.assertEqual(result.confidence, Decimal("0.5"))
        self.assertEqual(len(result.warnings), 1)


class TestRecipeNutritionDiabetes(NutritionTestDataMixin, TestCase):
    """Diabetes awareness tests for recipe nutrition."""

    def setUp(self):
        self.user = self.create_user()
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_high_carb_recipe_flagged(self):
        """Per-serving carbs > 45g should trigger diabetes flag."""
        recipe = self.create_recipe(self.user, servings=1)
        pasta = self.create_ingredient_with_food(
            "pasta", "grain",
            calories=350, protein_g=12, carbohydrates_g=70, fat_g=2,
        )
        self.link_recipe_ingredient(recipe, pasta, Decimal("1"), "piece", 0)

        result = calculate_recipe_nutrition(recipe, use_cache=False)

        self.assertTrue(result.is_diabetes_flagged)
        self.assertTrue(any("High carbs" in w for w in result.warnings))

    def test_low_carb_recipe_not_flagged(self):
        """Per-serving carbs <= 45g should not trigger diabetes flag."""
        recipe = self.create_recipe(self.user, servings=2)
        chicken = self.create_ingredient_with_food(
            "chicken breast", "protein",
            calories=165, protein_g=31, carbohydrates_g=0, fat_g=3,
        )
        self.link_recipe_ingredient(recipe, chicken, Decimal("2"), "piece", 0)

        result = calculate_recipe_nutrition(recipe, use_cache=False)

        self.assertFalse(result.is_diabetes_flagged)

    def test_borderline_carbs_exactly_45(self):
        """Exactly 45g per serving should NOT be flagged (> 45 needed)."""
        recipe = self.create_recipe(self.user, servings=1)
        food = self.create_food_item(
            "borderline food",
            calories=200, protein_g=5, carbohydrates_g=45, fat_g=3,
        )
        ing = Ingredient.objects.create(
            canonical_name="borderline food", category="grain",
            nutrition_source=food,
        )
        self.link_recipe_ingredient(recipe, ing, Decimal("1"), "piece", 0)

        result = calculate_recipe_nutrition(recipe, use_cache=False)
        self.assertFalse(result.is_diabetes_flagged)


# =============================================================================
# Caching tests
# =============================================================================

class TestRecipeNutritionCache(NutritionTestDataMixin, TestCase):
    """Caching tests for recipe nutrition."""

    def setUp(self):
        self.user = self.create_user()
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_result_is_cached(self):
        """Second call should return cached result."""
        recipe = self.create_recipe(self.user)
        chicken = self.create_ingredient_with_food(
            "chicken breast", "protein",
            calories=165, protein_g=31, carbohydrates_g=0, fat_g=3,
        )
        self.link_recipe_ingredient(recipe, chicken, Decimal("1"), "piece", 0)

        result1 = calculate_recipe_nutrition(recipe, use_cache=True)
        cache_key = f"{CACHE_PREFIX}:{recipe.id}"
        self.assertIsNotNone(cache.get(cache_key))

        result2 = calculate_recipe_nutrition(recipe, use_cache=True)
        self.assertEqual(result1.total["calories"], result2.total["calories"])

    def test_cache_bypass(self):
        """use_cache=False should not read or write cache."""
        recipe = self.create_recipe(self.user)
        chicken = self.create_ingredient_with_food(
            "chicken breast", "protein",
            calories=165, protein_g=31, carbohydrates_g=0, fat_g=3,
        )
        self.link_recipe_ingredient(recipe, chicken, Decimal("1"), "piece", 0)

        calculate_recipe_nutrition(recipe, use_cache=False)
        cache_key = f"{CACHE_PREFIX}:{recipe.id}"
        self.assertIsNone(cache.get(cache_key))

    def test_invalidate_cache(self):
        """invalidate_recipe_nutrition_cache should clear cached result."""
        recipe = self.create_recipe(self.user)
        chicken = self.create_ingredient_with_food(
            "chicken breast", "protein",
            calories=165, protein_g=31, carbohydrates_g=0, fat_g=3,
        )
        self.link_recipe_ingredient(recipe, chicken, Decimal("1"), "piece", 0)

        calculate_recipe_nutrition(recipe, use_cache=True)
        cache_key = f"{CACHE_PREFIX}:{recipe.id}"
        self.assertIsNotNone(cache.get(cache_key))

        invalidate_recipe_nutrition_cache(recipe.id)
        self.assertIsNone(cache.get(cache_key))


# =============================================================================
# get_recipe_macro_summary tests
# =============================================================================

class TestGetRecipeMacroSummary(NutritionTestDataMixin, TestCase):
    """Tests for get_recipe_macro_summary."""

    def setUp(self):
        self.user = self.create_user()
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_returns_summary_with_sufficient_confidence(self):
        """When confidence >= 0.3, summary should be returned."""
        recipe = self.create_recipe(self.user, servings=2)
        chicken = self.create_ingredient_with_food(
            "chicken breast", "protein",
            calories=165, protein_g=31, carbohydrates_g=0, fat_g=3.6,
        )
        self.link_recipe_ingredient(recipe, chicken, Decimal("2"), "piece", 0)

        summary = get_recipe_macro_summary(recipe)

        self.assertIsNotNone(summary)
        self.assertIn("calories", summary)
        self.assertIn("protein_g", summary)
        self.assertIn("carbohydrates_g", summary)
        self.assertIn("fat_g", summary)
        self.assertIn("fiber_g", summary)
        self.assertIn("confidence", summary)
        self.assertIn("is_diabetes_flagged", summary)
        self.assertIn("servings", summary)
        self.assertEqual(summary["servings"], 2)

    def test_returns_none_with_low_confidence(self):
        """When confidence < 0.3, summary should be None."""
        recipe = self.create_recipe(self.user)
        # Unlinked ingredient produces 0 confidence
        unlinked = Ingredient.objects.create(
            canonical_name="mystery", category="other",
            nutrition_source=None,
        )
        self.link_recipe_ingredient(recipe, unlinked, Decimal("1"), "piece", 0)

        summary = get_recipe_macro_summary(recipe)
        self.assertIsNone(summary)

    def test_summary_values_are_floats(self):
        """Summary values should be native floats, not Decimals."""
        recipe = self.create_recipe(self.user, servings=1)
        chicken = self.create_ingredient_with_food(
            "chicken breast", "protein",
            calories=165, protein_g=31, carbohydrates_g=0, fat_g=3,
        )
        self.link_recipe_ingredient(recipe, chicken, Decimal("1"), "piece", 0)

        summary = get_recipe_macro_summary(recipe)

        self.assertIsInstance(summary["calories"], float)
        self.assertIsInstance(summary["protein_g"], float)
        self.assertIsInstance(summary["confidence"], float)

    def test_summary_includes_diabetes_flag(self):
        """Summary should expose diabetes flag status."""
        recipe = self.create_recipe(self.user, servings=1)
        pasta = self.create_ingredient_with_food(
            "pasta", "grain",
            calories=350, protein_g=12, carbohydrates_g=70, fat_g=2,
        )
        self.link_recipe_ingredient(recipe, pasta, Decimal("1"), "piece", 0)

        summary = get_recipe_macro_summary(recipe)
        self.assertTrue(summary["is_diabetes_flagged"])


class TestRecipeNutritionMultiUser(NutritionTestDataMixin, TestCase):
    """Multi-user isolation tests for recipe nutrition."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_different_users_different_recipes(self):
        """Each user's recipe nutrition should be independent."""
        user_a = self.create_user("a@test.com")
        user_b = self.create_user("b@test.com")

        recipe_a = self.create_recipe(user_a, "Recipe A", servings=1)
        recipe_b = self.create_recipe(user_b, "Recipe B", servings=1)

        chicken = self.create_ingredient_with_food(
            "chicken breast", "protein",
            calories=165, protein_g=31, carbohydrates_g=0, fat_g=3,
        )
        pasta = self.create_ingredient_with_food(
            "pasta", "grain",
            calories=350, protein_g=12, carbohydrates_g=70, fat_g=2,
        )

        self.link_recipe_ingredient(recipe_a, chicken, Decimal("1"), "piece", 0)
        self.link_recipe_ingredient(recipe_b, pasta, Decimal("1"), "piece", 0)

        result_a = calculate_recipe_nutrition(recipe_a, use_cache=False)
        result_b = calculate_recipe_nutrition(recipe_b, use_cache=False)

        self.assertEqual(result_a.total["calories"], Decimal("165.00"))
        self.assertEqual(result_b.total["calories"], Decimal("350.00"))

        # Only recipe B should be diabetes-flagged
        self.assertFalse(result_a.is_diabetes_flagged)
        self.assertTrue(result_b.is_diabetes_flagged)


class TestRecipeNutritionConfidence(NutritionTestDataMixin, TestCase):
    """Confidence scoring tests for recipe nutrition."""

    def setUp(self):
        self.user = self.create_user()
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_full_confidence_all_linked(self):
        """All linked ingredients should produce confidence 1.0."""
        recipe = self.create_recipe(self.user)
        for i, name in enumerate(["chicken", "rice", "salt"]):
            ing = self.create_ingredient_with_food(
                name, "protein" if name == "chicken" else "grain",
                calories=100, protein_g=10, carbohydrates_g=5, fat_g=2,
            )
            self.link_recipe_ingredient(recipe, ing, Decimal("1"), "piece", i)

        result = calculate_recipe_nutrition(recipe, use_cache=False)
        self.assertEqual(result.confidence, Decimal("1.0"))

    def test_zero_confidence_none_linked(self):
        """No linked ingredients should produce confidence 0."""
        recipe = self.create_recipe(self.user)
        unlinked = Ingredient.objects.create(
            canonical_name="mystery", category="other",
            nutrition_source=None,
        )
        self.link_recipe_ingredient(recipe, unlinked, Decimal("1"), "piece", 0)

        result = calculate_recipe_nutrition(recipe, use_cache=False)
        self.assertEqual(result.confidence, Decimal("0"))

    def test_partial_confidence_ratio(self):
        """2 of 4 linked should produce confidence 0.5."""
        recipe = self.create_recipe(self.user)
        for i in range(2):
            ing = self.create_ingredient_with_food(
                f"linked_{i}", "protein",
                calories=100, protein_g=10, carbohydrates_g=5, fat_g=2,
            )
            self.link_recipe_ingredient(recipe, ing, Decimal("1"), "piece", i)

        for i in range(2, 4):
            unlinked = Ingredient.objects.create(
                canonical_name=f"unlinked_{i}", category="other",
                nutrition_source=None,
            )
            self.link_recipe_ingredient(recipe, unlinked, Decimal("1"), "piece", i)

        result = calculate_recipe_nutrition(recipe, use_cache=False)
        self.assertEqual(result.confidence, Decimal("0.5"))
