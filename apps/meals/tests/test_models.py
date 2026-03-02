"""
Tests for Meal Intelligence models.

Phase 1: Ingredient, RecipeIngredient
Phase 2: Household, HouseholdMembership, DietaryProfile
Phase 3: PantryItem, InventoryTransaction
"""

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.meals.models import (
    DietaryProfile,
    Household,
    HouseholdMembership,
    Ingredient,
    InventoryTransaction,
    PantryItem,
    RecipeIngredient,
)
from apps.users.models import User


class TestUserMixin:
    """Mixin to create test users."""

    def create_user(self, email="test@example.com"):
        from apps.users.models import TermsAcceptance, UserPreferences
        user = User.objects.create_user(email=email, password="testpass123")
        TermsAcceptance.objects.create(user=user, terms_version="1.0")
        prefs, _ = UserPreferences.objects.get_or_create(user=user)
        prefs.has_completed_onboarding = True
        prefs.save(update_fields=["has_completed_onboarding"])
        return user


class TestIngredientModel(TestUserMixin, TestCase):
    """Tests for the Ingredient model."""

    def test_create_ingredient(self):
        ing = Ingredient.objects.create(
            canonical_name="chicken breast",
            category="protein",
            storage_type="refrigerator",
            shelf_life_days=5,
        )
        self.assertEqual(str(ing), "chicken breast")
        self.assertEqual(ing.category, "protein")

    def test_aliases(self):
        ing = Ingredient.objects.create(
            canonical_name="chicken breast",
            aliases=["boneless chicken", "pollo", "chicken"],
            category="protein",
        )
        self.assertTrue(ing.matches_text("boneless chicken"))
        self.assertTrue(ing.matches_text("chicken breast"))
        self.assertTrue(ing.matches_text("Chicken Breast"))  # case insensitive
        self.assertFalse(ing.matches_text("beef"))

    def test_unique_canonical_name(self):
        Ingredient.objects.create(canonical_name="salt", category="spice")
        with self.assertRaises(Exception):
            Ingredient.objects.create(canonical_name="salt", category="spice")

    def test_substitution_group(self):
        chicken = Ingredient.objects.create(
            canonical_name="chicken breast",
            category="protein",
            substitution_group="poultry",
        )
        turkey = Ingredient.objects.create(
            canonical_name="turkey breast",
            category="protein",
            substitution_group="poultry",
        )
        group = Ingredient.objects.filter(substitution_group="poultry")
        self.assertEqual(group.count(), 2)

    def test_low_carb_alternative(self):
        pasta = Ingredient.objects.create(
            canonical_name="spaghetti",
            category="grain",
            carb_density=Decimal("25.0"),
        )
        zoodles = Ingredient.objects.create(
            canonical_name="zucchini noodles",
            category="vegetable",
            carb_density=Decimal("3.1"),
        )
        pasta.low_carb_alternative = zoodles
        pasta.save()
        self.assertEqual(pasta.low_carb_alternative.canonical_name, "zucchini noodles")

    def test_default_values(self):
        ing = Ingredient.objects.create(
            canonical_name="test item",
            category="other",
        )
        self.assertEqual(ing.default_unit, "g")
        self.assertEqual(ing.default_quantity, Decimal("100"))
        self.assertEqual(ing.carb_density, Decimal("0"))
        self.assertEqual(ing.protein_density, Decimal("0"))
        self.assertEqual(ing.storage_type, "pantry")

    def test_ordering(self):
        Ingredient.objects.create(canonical_name="zucchini", category="vegetable")
        Ingredient.objects.create(canonical_name="apple", category="fruit")
        Ingredient.objects.create(canonical_name="milk", category="dairy")
        names = list(Ingredient.objects.values_list("canonical_name", flat=True))
        self.assertEqual(names, ["apple", "milk", "zucchini"])


class TestRecipeIngredientModel(TestUserMixin, TestCase):
    """Tests for the RecipeIngredient model."""

    def setUp(self):
        self.user = self.create_user()
        from apps.life.models import Recipe
        self.recipe = Recipe.objects.create(
            user=self.user,
            title="Test Recipe",
            ingredients="2 cups flour\n1 tsp salt",
            instructions="Mix and bake.",
        )
        self.flour = Ingredient.objects.create(
            canonical_name="flour",
            category="grain",
        )
        self.salt = Ingredient.objects.create(
            canonical_name="salt",
            category="spice",
        )

    def test_create_recipe_ingredient(self):
        ri = RecipeIngredient.objects.create(
            recipe=self.recipe,
            ingredient=self.flour,
            quantity=Decimal("2"),
            unit="cup",
            order_index=0,
        )
        self.assertIn("flour", str(ri))

    def test_ordering(self):
        ri1 = RecipeIngredient.objects.create(
            recipe=self.recipe,
            ingredient=self.flour,
            quantity=Decimal("2"),
            unit="cup",
            order_index=0,
        )
        ri2 = RecipeIngredient.objects.create(
            recipe=self.recipe,
            ingredient=self.salt,
            quantity=Decimal("1"),
            unit="tsp",
            order_index=1,
        )
        ingredients = list(self.recipe.structured_ingredients.all())
        self.assertEqual(ingredients[0].ingredient, self.flour)
        self.assertEqual(ingredients[1].ingredient, self.salt)

    def test_optional_ingredient(self):
        ri = RecipeIngredient.objects.create(
            recipe=self.recipe,
            ingredient=self.flour,
            quantity=Decimal("1"),
            unit="cup",
            is_optional=True,
            order_index=0,
        )
        self.assertTrue(ri.is_optional)

    def test_null_quantity_for_to_taste(self):
        ri = RecipeIngredient.objects.create(
            recipe=self.recipe,
            ingredient=self.salt,
            quantity=None,
            unit="to_taste",
            order_index=0,
        )
        self.assertIsNone(ri.quantity)
        self.assertEqual(ri.unit, "to_taste")

    def test_parse_confidence(self):
        ri = RecipeIngredient.objects.create(
            recipe=self.recipe,
            ingredient=self.flour,
            quantity=Decimal("2"),
            unit="cup",
            parse_confidence=Decimal("0.85"),
            original_text="2 cups all-purpose flour",
            order_index=0,
        )
        self.assertEqual(ri.parse_confidence, Decimal("0.85"))
        self.assertEqual(ri.original_text, "2 cups all-purpose flour")

    def test_preparation_notes(self):
        ri = RecipeIngredient.objects.create(
            recipe=self.recipe,
            ingredient=self.flour,
            quantity=Decimal("2"),
            unit="cup",
            preparation_notes="sifted",
            order_index=0,
        )
        self.assertEqual(ri.preparation_notes, "sifted")

    def test_cascade_delete_recipe(self):
        RecipeIngredient.objects.create(
            recipe=self.recipe,
            ingredient=self.flour,
            quantity=Decimal("2"),
            unit="cup",
            order_index=0,
        )
        self.recipe.soft_delete()
        # RecipeIngredient still exists (recipe is soft-deleted, not hard-deleted)
        # but if we hard delete the recipe, cascade should work
        from apps.life.models import Recipe
        Recipe.all_objects.filter(pk=self.recipe.pk).delete()
        self.assertEqual(RecipeIngredient.objects.count(), 0)


class TestHouseholdModel(TestUserMixin, TestCase):
    """Tests for Household and HouseholdMembership models."""

    def setUp(self):
        self.user1 = self.create_user("user1@example.com")
        self.user2 = self.create_user("user2@example.com")

    def test_create_household(self):
        household = Household.objects.create(
            name="Jenkins Family",
            primary_user=self.user1,
        )
        self.assertEqual(str(household), "Jenkins Family")
        self.assertEqual(household.grocery_cycle_days, 7)

    def test_add_members(self):
        household = Household.objects.create(
            name="Test Household",
            primary_user=self.user1,
        )
        m1 = HouseholdMembership.objects.create(
            household=household,
            user=self.user1,
            role="admin",
        )
        m2 = HouseholdMembership.objects.create(
            household=household,
            user=self.user2,
            role="member",
        )
        self.assertEqual(household.memberships.count(), 2)
        self.assertEqual(m1.role, "admin")
        self.assertEqual(m2.role, "member")

    def test_unique_membership(self):
        household = Household.objects.create(
            name="Test",
            primary_user=self.user1,
        )
        HouseholdMembership.objects.create(
            household=household,
            user=self.user1,
            role="admin",
        )
        with self.assertRaises(Exception):
            HouseholdMembership.objects.create(
                household=household,
                user=self.user1,
                role="member",
            )


class TestDietaryProfileModel(TestUserMixin, TestCase):
    """Tests for DietaryProfile model."""

    def setUp(self):
        self.user = self.create_user()

    def test_create_profile(self):
        profile = DietaryProfile.objects.create(
            user=self.user,
            carb_limit_daily=Decimal("50"),
            protein_target_daily=Decimal("120"),
            calorie_target=2000,
            diabetes_sensitive=True,
        )
        self.assertTrue(profile.diabetes_sensitive)
        self.assertEqual(profile.carb_limit_daily, Decimal("50"))

    def test_dietary_flags(self):
        profile = DietaryProfile.objects.create(
            user=self.user,
            dietary_flags=["gluten_free", "dairy_free"],
        )
        self.assertIn("gluten_free", profile.dietary_flags)
        self.assertIn("dairy_free", profile.dietary_flags)

    def test_soft_delete(self):
        profile = DietaryProfile.objects.create(
            user=self.user,
            calorie_target=2000,
        )
        profile.soft_delete()
        self.assertEqual(DietaryProfile.objects.count(), 0)
        self.assertEqual(DietaryProfile.all_objects.count(), 1)


class TestPantryItemModel(TestUserMixin, TestCase):
    """Tests for PantryItem and InventoryTransaction models."""

    def setUp(self):
        self.user = self.create_user()
        self.household = Household.objects.create(
            name="Test Household",
            primary_user=self.user,
        )
        self.flour = Ingredient.objects.create(
            canonical_name="flour",
            category="grain",
            shelf_life_days=365,
        )

    def test_create_pantry_item(self):
        item = PantryItem.objects.create(
            household=self.household,
            ingredient=self.flour,
            quantity=Decimal("1000"),
            unit="g",
        )
        self.assertIn("flour", str(item))
        self.assertEqual(item.confidence_score, Decimal("1.0"))

    def test_unique_household_ingredient(self):
        PantryItem.objects.create(
            household=self.household,
            ingredient=self.flour,
            quantity=Decimal("500"),
            unit="g",
        )
        with self.assertRaises(Exception):
            PantryItem.objects.create(
                household=self.household,
                ingredient=self.flour,
                quantity=Decimal("200"),
                unit="g",
            )

    def test_expiration_detection(self):
        item = PantryItem.objects.create(
            household=self.household,
            ingredient=self.flour,
            quantity=Decimal("500"),
            unit="g",
            expiration_date_estimated=timezone.now().date() - timezone.timedelta(days=1),
        )
        self.assertTrue(item.is_expired)
        self.assertLess(item.days_until_expiration, 0)

    def test_not_expired(self):
        item = PantryItem.objects.create(
            household=self.household,
            ingredient=self.flour,
            quantity=Decimal("500"),
            unit="g",
            expiration_date_estimated=timezone.now().date() + timezone.timedelta(days=30),
        )
        self.assertFalse(item.is_expired)
        self.assertEqual(item.days_until_expiration, 30)

    def test_confidence_decay(self):
        item = PantryItem.objects.create(
            household=self.household,
            ingredient=self.flour,
            quantity=Decimal("500"),
            unit="g",
            last_confirmed_at=timezone.now() - timezone.timedelta(days=10),
        )
        item.decay_confidence()
        self.assertLess(item.confidence_score, Decimal("1.0"))
        self.assertGreater(item.confidence_score, Decimal("0.0"))

    def test_confidence_no_decay_within_3_days(self):
        item = PantryItem.objects.create(
            household=self.household,
            ingredient=self.flour,
            quantity=Decimal("500"),
            unit="g",
            last_confirmed_at=timezone.now() - timezone.timedelta(days=2),
        )
        item.decay_confidence()
        self.assertEqual(item.confidence_score, Decimal("1.0"))

    def test_inventory_transaction(self):
        item = PantryItem.objects.create(
            household=self.household,
            ingredient=self.flour,
            quantity=Decimal("500"),
            unit="g",
        )
        tx = InventoryTransaction.objects.create(
            pantry_item=item,
            delta_quantity=Decimal("200"),
            source="receipt",
        )
        self.assertIn("+", str(tx))

        tx2 = InventoryTransaction.objects.create(
            pantry_item=item,
            delta_quantity=Decimal("-100"),
            source="meal_plan",
        )
        self.assertNotIn("+", str(tx2))
