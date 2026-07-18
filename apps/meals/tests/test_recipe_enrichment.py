# ==============================================================================
# File: apps/meals/tests/test_recipe_enrichment.py
# Project: Whole Life Journey - Meal Intelligence
# Description: Foundation 2 — recipe enrichment at the write boundary. Proves the
#   keystone gap is closed: saving a recipe now populates structured RecipeIngredient
#   rows (deterministically), which unblocks real recipe nutrition.
# ==============================================================================
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.meals.models import Ingredient, Recipe, RecipeIngredient
from apps.meals.tasks import enrich_recipe_ingredients

User = get_user_model()


class RecipeEnrichmentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="enrich@test.com", password="x")

    def test_enrichment_creates_structured_ingredients_from_text(self):
        r = Recipe.objects.create(
            user=self.user, title="Stew",
            ingredients="2 cups flour\n1 tsp salt\n3 chicken breasts",
            instructions="cook")
        # (eager signal already ran on save; call again to assert idempotence too)
        enrich_recipe_ingredients(r.pk)
        rows = RecipeIngredient.objects.filter(recipe=r).order_by("order_index")
        self.assertEqual(rows.count(), 3)
        names = [ri.ingredient.canonical_name for ri in rows]
        self.assertTrue(any("flour" in n for n in names))
        self.assertTrue(any("salt" in n for n in names))
        self.assertTrue(any("chicken" in n for n in names))

    def test_signal_enriches_on_save(self):
        # CELERY eager in tests → post_save enqueue runs synchronously.
        r = Recipe.objects.create(
            user=self.user, title="Auto",
            ingredients="1 onion\n2 tomatoes", instructions="chop")
        self.assertEqual(RecipeIngredient.objects.filter(recipe=r).count(), 2)

    def test_enrichment_is_idempotent(self):
        r = Recipe.objects.create(
            user=self.user, title="Idem",
            ingredients="1 egg\n1 egg\n1 cup milk", instructions="mix")
        enrich_recipe_ingredients(r.pk)
        enrich_recipe_ingredients(r.pk)
        # rebuilt, not duplicated — 3 lines in → 3 rows (two eggs kept as distinct lines)
        self.assertEqual(RecipeIngredient.objects.filter(recipe=r).count(), 3)

    def test_no_ingredients_text_skips_and_preserves_manual_rows(self):
        r = Recipe.objects.create(
            user=self.user, title="Empty", ingredients="", instructions="x")
        ing = Ingredient.objects.create(canonical_name="manual-thing", category="other")
        RecipeIngredient.objects.create(recipe=r, ingredient=ing, order_index=0)
        result = enrich_recipe_ingredients(r.pk)
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(RecipeIngredient.objects.filter(recipe=r).count(), 1)

    def test_enrichment_reparses_on_text_change(self):
        r = Recipe.objects.create(
            user=self.user, title="Changing",
            ingredients="1 apple", instructions="x")
        self.assertEqual(RecipeIngredient.objects.filter(recipe=r).count(), 1)
        r.ingredients = "1 apple\n1 banana\n1 cherry"
        r.save()  # signal re-enriches (eager)
        self.assertEqual(RecipeIngredient.objects.filter(recipe=r).count(), 3)

    def test_enrichment_unblocks_real_recipe_nutrition(self):
        """The keystone: a recipe whose ingredient matches a canonical Ingredient
        with a FoodItem now yields real per-serving nutrition (previously always None)."""
        from apps.health.models import FoodItem
        from apps.meals.services.recipe_nutrition import calculate_recipe_nutrition

        food = FoodItem.objects.create(
            name="Chicken Breast", serving_size=Decimal("100"), serving_unit="g",
            calories=Decimal("165"), protein_g=Decimal("31"),
            carbohydrates_g=Decimal("0"), fat_g=Decimal("4"))
        Ingredient.objects.create(
            canonical_name="chicken breast", category="protein", nutrition_source=food)

        r = Recipe.objects.create(
            user=self.user, title="Grilled Chicken",
            ingredients="2 chicken breast", instructions="grill", servings=1)
        # enrichment linked the RecipeIngredient to the canonical ingredient + FoodItem
        ri = RecipeIngredient.objects.filter(recipe=r).first()
        self.assertIsNotNone(ri)
        self.assertEqual(ri.ingredient.nutrition_source_id, food.id)

        nutrition = calculate_recipe_nutrition(r, use_cache=False)
        self.assertGreater(float(nutrition.per_serving.get("calories", 0)), 0.0,
                           "recipe nutrition must now be real (keystone gap closed)")
        self.assertGreater(float(nutrition.confidence), 0.0)
