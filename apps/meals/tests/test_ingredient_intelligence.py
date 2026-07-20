# ==============================================================================
# File: apps/meals/tests/test_ingredient_intelligence.py
# Project: Whole Life Journey - Meal Intelligence
# Description: Canonical Ingredient Intelligence — deterministic identity resolution.
#   Proves two surface forms of the same real ingredient resolve to ONE canonical row, that
#   distinct-but-related things (variants/substitutions) do NOT merge, and that every seam
#   (resolve, match, search, merge) is deterministic and explainable — no fuzzy, no AI.
# ==============================================================================
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.meals.models import (
    Household, HouseholdMembership, Ingredient, InventoryTransaction, PantryItem,
    Recipe, RecipeIngredient,
)
from apps.meals.services.ingredient_intelligence import (
    merge_duplicate_ingredients, normalize_name, resolve_ingredient, search_ingredients,
)
from apps.meals.services.ingredient_matching import (
    get_or_create_ingredient, match_ingredient_name,
)
from apps.users.models import TermsAcceptance

User = get_user_model()


class NormalizeNameTests(TestCase):
    def test_plural_and_case_and_punctuation_collapse_to_one_key(self):
        self.assertEqual(normalize_name("Hamburger Bun"), "hamburger bun")
        self.assertEqual(normalize_name("Hamburger Buns"), "hamburger bun")
        self.assertEqual(normalize_name("  HAMBURGER   BUNS! "), "hamburger bun")
        self.assertEqual(normalize_name("Tomatoes"), "tomato")
        self.assertEqual(normalize_name("Hamburger Patties"), "hamburger patty")

    def test_modifiers_and_singular_s_words_are_preserved(self):
        # Variants stay DISTINCT — identity must not merge different real things.
        self.assertNotEqual(normalize_name("Whole Milk"), normalize_name("Milk"))
        self.assertNotEqual(normalize_name("2% Milk"), normalize_name("Whole Milk"))
        self.assertEqual(normalize_name("Hummus"), "hummus")        # not "hummu"
        self.assertEqual(normalize_name("Asparagus"), "asparagus")  # not "asparagu"
        self.assertEqual(normalize_name("Ground Beef"), "ground beef")


class ResolveTests(TestCase):
    def test_create_sets_canonical_and_normalized(self):
        ing = resolve_ingredient("Hamburger Bun", category="grain")
        self.assertEqual(ing.canonical_name, "hamburger bun")
        self.assertEqual(ing.normalized_name, "hamburger bun")

    def test_plural_resolves_to_same_canonical_no_duplicate(self):
        a = resolve_ingredient("Hamburger Bun", category="grain")
        before = Ingredient.objects.count()
        b = resolve_ingredient("Hamburger Buns", category="grain")   # plural surface form
        self.assertEqual(a.id, b.id)                                  # SAME canonical row
        self.assertEqual(Ingredient.objects.count(), before)         # no new row
        b.refresh_from_db()
        self.assertIn("hamburger buns", b.aliases)                   # variant learned as alias

    def test_alias_resolves(self):
        ing = Ingredient.objects.create(canonical_name="ketchup", category="condiment",
                                        aliases=["catsup"])
        self.assertEqual(resolve_ingredient("Catsup").id, ing.id)

    def test_create_false_is_read_only(self):
        self.assertIsNone(resolve_ingredient("nonexistent thing", create=False))
        # A normalized read-only match must not mutate aliases.
        ing = resolve_ingredient("Bagel", category="grain")
        got = resolve_ingredient("Bagels", create=False)
        self.assertEqual(got.id, ing.id)
        ing.refresh_from_db()
        self.assertNotIn("bagels", ing.aliases)

    def test_variants_do_not_merge(self):
        # Whole Milk and Milk are DIFFERENT identities (a substitution/variant relationship).
        whole = resolve_ingredient("Whole Milk", category="dairy")
        milk = resolve_ingredient("Milk", category="dairy")
        self.assertNotEqual(whole.id, milk.id)


class MatchTests(TestCase):
    def test_deterministic_methods_only(self):
        Ingredient.objects.create(canonical_name="ground beef", category="protein",
                                  aliases=["minced beef"])
        self.assertEqual(match_ingredient_name("Ground Beef").match_method, "exact")
        self.assertEqual(match_ingredient_name("Ground Beefs").match_method, "normalized")
        self.assertEqual(match_ingredient_name("Minced Beef").match_method, "alias")
        self.assertEqual(match_ingredient_name("kumquat").match_method, "none")

    def test_no_fuzzy_partial_match(self):
        # Old fuzzy logic would link "chicken" -> "chicken breast" by substring; deterministic
        # resolution must NOT (they are different ingredients).
        Ingredient.objects.create(canonical_name="chicken breast", category="protein")
        self.assertEqual(match_ingredient_name("chicken").match_method, "none")

    def test_get_or_create_delegates_and_dedupes(self):
        a = get_or_create_ingredient("Hamburger Bun")
        b = get_or_create_ingredient("hamburger buns")
        self.assertEqual(a.id, b.id)


class SearchTests(TestCase):
    def setUp(self):
        for n, c in [("hamburger bun", "grain"), ("ground beef", "protein"),
                     ("ground turkey", "protein"), ("ground chicken", "protein"),
                     ("ketchup", "condiment")]:
            Ingredient.objects.create(canonical_name=n, category=c)
        Ingredient.objects.get(canonical_name="ketchup").aliases = ["heinz ketchup"]
        k = Ingredient.objects.get(canonical_name="ketchup"); k.aliases = ["heinz ketchup"]; k.save()

    def test_substring_search(self):
        self.assertIn("hamburger bun", [i.canonical_name for i in search_ingredients("burger")])
        grounds = [i.canonical_name for i in search_ingredients("ground")]
        self.assertEqual(set(grounds), {"ground beef", "ground turkey", "ground chicken"})
        self.assertIn("ketchup", [i.canonical_name for i in search_ingredients("ket")])

    def test_alias_search(self):
        self.assertIn("ketchup", [i.canonical_name for i in search_ingredients("heinz")])

    def test_empty_is_empty(self):
        self.assertEqual(list(search_ingredients("")), [])


class MergeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="ii@test.com", password="x")
        TermsAcceptance.objects.create(
            user=self.user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        self.household = Household.objects.create(name="H", primary_user=self.user)
        HouseholdMembership.objects.create(household=self.household, user=self.user, role="admin")

    def test_merge_folds_duplicates_and_repoints_fks(self):
        # Simulate legacy duplicate rows (created before Ingredient Intelligence).
        bun = Ingredient.objects.create(canonical_name="hamburger bun", category="grain")
        buns = Ingredient.objects.create(canonical_name="hamburger buns", category="grain")
        self.assertEqual(bun.normalized_name, buns.normalized_name)  # same key

        recipe = Recipe.objects.create(user=self.user, title="Burger", ingredients="",
                                       instructions="grill", servings=1)
        RecipeIngredient.objects.create(recipe=recipe, ingredient=buns,
                                        quantity=Decimal("2"), unit="piece", order_index=0)
        PantryItem.objects.create(household=self.household, ingredient=bun,
                                  quantity=Decimal("8"), unit="piece")

        removed = merge_duplicate_ingredients()
        self.assertEqual(removed, 1)
        survivor = Ingredient.objects.get(normalized_name="hamburger bun")
        # RecipeIngredient repointed to the survivor.
        self.assertEqual(RecipeIngredient.objects.get(recipe=recipe).ingredient_id, survivor.id)
        # PantryItem present on the survivor; the folded name is now an alias.
        self.assertTrue(PantryItem.objects.filter(
            household=self.household, ingredient=survivor).exists())
        self.assertIn("hamburger buns", survivor.aliases)

    def test_merge_sums_pantry_quantity_on_conflict(self):
        a = Ingredient.objects.create(canonical_name="egg", category="protein")
        b = Ingredient.objects.create(canonical_name="eggs", category="protein")
        ia = PantryItem.objects.create(household=self.household, ingredient=a,
                                       quantity=Decimal("6"), unit="piece")
        PantryItem.objects.create(household=self.household, ingredient=b,
                                  quantity=Decimal("4"), unit="piece")
        InventoryTransaction.objects.create(pantry_item=PantryItem.objects.get(ingredient=b),
                                            delta_quantity=Decimal("4"), source="manual")
        merge_duplicate_ingredients()
        survivor = Ingredient.objects.get(normalized_name="egg")
        items = PantryItem.objects.filter(household=self.household, ingredient=survivor)
        self.assertEqual(items.count(), 1)                       # one row, not two
        self.assertEqual(items.first().quantity, Decimal("10"))  # 6 + 4 summed


class ReportedBugTests(TestCase):
    """The exact product-validation failure: recipe 'Hamburger Bun' + pantry 'Hamburger Buns'."""

    def setUp(self):
        self.user = User.objects.create_user(email="bug@test.com", password="x")
        TermsAcceptance.objects.create(
            user=self.user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        self.household = Household.objects.create(name="H", primary_user=self.user)
        HouseholdMembership.objects.create(household=self.household, user=self.user, role="admin")

    def test_recipe_bun_and_pantry_buns_resolve_and_show_available(self):
        from apps.meals.services.inventory_gap import analyze_recipe_gaps

        # Pantry acquired "Hamburger Buns"; recipe calls for "Hamburger Bun" — one identity now.
        pantry_ing = get_or_create_ingredient("Hamburger Buns", category="grain")
        PantryItem.objects.create(household=self.household, ingredient=pantry_ing,
                                  quantity=Decimal("8"), unit="piece")
        recipe_ing = get_or_create_ingredient("Hamburger Bun", category="grain")
        self.assertEqual(pantry_ing.id, recipe_ing.id)  # SAME canonical ingredient

        recipe = Recipe.objects.create(user=self.user, title="Burgers", ingredients="",
                                       instructions="grill", servings=2)
        RecipeIngredient.objects.create(recipe=recipe, ingredient=recipe_ing,
                                        quantity=Decimal("2"), unit="piece", order_index=0)
        gaps = analyze_recipe_gaps(recipe, self.household)
        self.assertEqual(gaps.gaps[0].gap_type, "available")  # was "missing" before the fix


class SaveHookTests(TestCase):
    def test_save_keeps_normalized_name_in_sync(self):
        ing = Ingredient.objects.create(canonical_name="Ground Chuck", category="protein")
        self.assertEqual(ing.normalized_name, "ground chuck")
        ing.canonical_name = "Ground Chucks"
        ing.save()
        ing.refresh_from_db()
        self.assertEqual(ing.normalized_name, "ground chuck")
