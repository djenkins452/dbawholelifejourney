"""
Tests for Meal Intelligence views.

Covers:
- Dashboard loads (empty state + with data)
- Suggestions render
- Pantry view with grouping
- Pantry AJAX actions (confirm, mark used)
- Meal plan view
- Plan generation
- Receipt upload + detail
- Recipe intelligence detail
"""

import json
from decimal import Decimal

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from apps.meals.models import (
    DietaryProfile,
    Household,
    HouseholdMembership,
    Ingredient,
    InventoryTransaction,
    MealPlan,
    MealPlanEntry,
    PantryItem,
    Receipt,
    ReceiptItem,
    RecipeIngredient,
)
from apps.users.models import User


class TestUserMixin:
    """Mixin to create test users with proper onboarding."""

    def create_user(self, email="test@example.com"):
        from django.conf import settings
        from apps.users.models import TermsAcceptance
        user = User.objects.create_user(email=email, password="testpass123")
        terms_version = settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
        TermsAcceptance.objects.create(user=user, terms_version=terms_version)
        user.preferences.has_completed_onboarding = True
        user.preferences.save()
        return user


class TestMealsDashboardView(TestUserMixin, TestCase):
    """Tests for MealsDashboardView."""

    def setUp(self):
        self.user = self.create_user()
        self.client = Client()
        self.client.force_login(self.user)

    def test_dashboard_loads(self):
        response = self.client.get(reverse("meals:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "meals/dashboard.html")

    def test_dashboard_creates_household(self):
        """Dashboard auto-creates a household if user has none."""
        self.assertFalse(HouseholdMembership.objects.filter(user=self.user).exists())
        response = self.client.get(reverse("meals:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(HouseholdMembership.objects.filter(user=self.user).exists())

    def test_dashboard_empty_state(self):
        """Dashboard shows setup mode when below activation threshold."""
        response = self.client.get(reverse("meals:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Build Your Kitchen Intelligence")

    def test_dashboard_with_data(self):
        """Dashboard shows data when pantry items exist."""
        household = Household.objects.create(
            name="Test Household", primary_user=self.user
        )
        HouseholdMembership.objects.create(
            household=household, user=self.user, role="admin"
        )
        flour = Ingredient.objects.create(canonical_name="flour", category="grain")
        PantryItem.objects.create(
            household=household, ingredient=flour,
            quantity=Decimal("500"), unit="g",
        )
        response = self.client.get(reverse("meals:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1")  # pantry count

    def test_dashboard_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("meals:dashboard"))
        self.assertEqual(response.status_code, 302)


class TestDinnerSuggestionsView(TestUserMixin, TestCase):
    """Tests for DinnerSuggestionsView."""

    def setUp(self):
        self.user = self.create_user()
        self.client = Client()
        self.client.force_login(self.user)

    def test_suggestions_loads(self):
        response = self.client.get(reverse("meals:suggestions"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "meals/suggestions.html")

    def test_suggestions_empty_state(self):
        """Empty state shows setup required (activation gate fires first)."""
        response = self.client.get(reverse("meals:suggestions"))
        self.assertContains(response, "Setup Required")

    def test_suggestions_with_recipes_below_threshold(self):
        """Suggestions page shows setup required when below activation threshold."""
        from apps.life.models import Recipe
        Recipe.objects.create(
            user=self.user,
            title="Test Recipe",
            ingredients="1 cup flour",
            instructions="Mix.",
        )
        response = self.client.get(reverse("meals:suggestions"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Setup Required")


class TestPantryView(TestUserMixin, TestCase):
    """Tests for PantryView and AJAX actions."""

    def setUp(self):
        self.user = self.create_user()
        self.client = Client()
        self.client.force_login(self.user)
        self.household = Household.objects.create(
            name="Test Household", primary_user=self.user
        )
        HouseholdMembership.objects.create(
            household=self.household, user=self.user, role="admin"
        )
        self.flour = Ingredient.objects.create(
            canonical_name="flour", category="grain"
        )
        self.pantry_item = PantryItem.objects.create(
            household=self.household, ingredient=self.flour,
            quantity=Decimal("500"), unit="g",
        )

    def test_pantry_loads(self):
        response = self.client.get(reverse("meals:pantry"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "meals/pantry.html")

    def test_pantry_grouping(self):
        """Pantry items are grouped by section."""
        response = self.client.get(reverse("meals:pantry"))
        self.assertContains(response, "Pantry Staples")
        self.assertContains(response, "Flour")

    def test_pantry_stats(self):
        response = self.client.get(reverse("meals:pantry"))
        self.assertContains(response, "1")  # items tracked

    def test_pantry_confirm_ajax(self):
        """Confirm action resets confidence to 1.0."""
        self.pantry_item.confidence_score = Decimal("0.5")
        self.pantry_item.save()

        response = self.client.post(
            reverse("meals:pantry_confirm", kwargs={"pk": self.pantry_item.pk}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["confidence"], 1.0)
        self.pantry_item.refresh_from_db()
        self.assertEqual(self.pantry_item.confidence_score, Decimal("1.0"))

    def test_pantry_mark_used(self):
        """Mark used sets quantity to 0."""
        response = self.client.post(
            reverse("meals:pantry_mark_used", kwargs={"pk": self.pantry_item.pk}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.pantry_item.refresh_from_db()
        self.assertEqual(self.pantry_item.quantity, Decimal("0"))
        # Verify transaction was created
        self.assertTrue(
            InventoryTransaction.objects.filter(
                pantry_item=self.pantry_item,
                delta_quantity=Decimal("-500"),
            ).exists()
        )

    def test_pantry_update_quantity(self):
        """Update quantity via AJAX."""
        response = self.client.post(
            reverse("meals:pantry_update", kwargs={"pk": self.pantry_item.pk}),
            data=json.dumps({"quantity": "300"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.pantry_item.refresh_from_db()
        self.assertEqual(self.pantry_item.quantity, Decimal("300"))

    def test_pantry_empty_state(self):
        """Empty pantry shows appropriate message."""
        PantryItem.objects.all().delete()
        response = self.client.get(reverse("meals:pantry"))
        self.assertContains(response, "Pantry is empty")


class TestMealPlanView(TestUserMixin, TestCase):
    """Tests for MealPlanView."""

    def setUp(self):
        self.user = self.create_user()
        self.client = Client()
        self.client.force_login(self.user)
        self.household = Household.objects.create(
            name="Test Household", primary_user=self.user
        )
        HouseholdMembership.objects.create(
            household=self.household, user=self.user, role="admin"
        )

    def test_plan_loads_empty(self):
        response = self.client.get(reverse("meals:plan"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No active meal plan")

    def test_plan_with_active_plan(self):
        """Plan view shows calendar grid when plan exists."""
        today = timezone.now().date()
        plan = MealPlan.objects.create(
            user=self.user,
            household=self.household,
            start_date=today,
            end_date=today + timezone.timedelta(days=6),
        )
        from apps.life.models import Recipe
        recipe = Recipe.objects.create(
            user=self.user, title="Chicken Stir Fry",
            ingredients="chicken", instructions="Cook.",
        )
        MealPlanEntry.objects.create(
            meal_plan=plan, date=today, meal_type="dinner",
            recipe=recipe, serving_count=4,
        )
        response = self.client.get(reverse("meals:plan"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Chicken Stir Fry")

    def test_generate_plan_no_recipes(self):
        response = self.client.post(reverse("meals:plan_generate"))
        self.assertEqual(response.status_code, 302)  # redirect

    def test_generate_plan_with_recipes(self):
        from apps.life.models import Recipe
        Recipe.objects.create(
            user=self.user, title="Pasta",
            ingredients="pasta", instructions="Boil.",
        )
        response = self.client.post(reverse("meals:plan_generate"))
        self.assertEqual(response.status_code, 302)
        # Verify plan was created
        self.assertTrue(MealPlan.objects.filter(household=self.household).exists())


class TestReceiptUploadView(TestUserMixin, TestCase):
    """Tests for ReceiptUploadView."""

    def setUp(self):
        self.user = self.create_user()
        self.client = Client()
        self.client.force_login(self.user)
        self.household = Household.objects.create(
            name="Test Household", primary_user=self.user
        )
        HouseholdMembership.objects.create(
            household=self.household, user=self.user, role="admin"
        )

    def test_receipt_page_loads(self):
        response = self.client.get(reverse("meals:receipts"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "meals/receipt_upload.html")

    def test_receipt_upload_empty_text(self):
        response = self.client.post(
            reverse("meals:receipts"),
            {"receipt_text": ""},
        )
        self.assertEqual(response.status_code, 302)

    def test_receipt_upload_processes(self):
        """Receipt upload creates receipt and items."""
        receipt_text = "WALMART\n03/01/2026\nBANANAS $0.68\nCHICKEN $7.99\nTOTAL $8.67"
        response = self.client.post(
            reverse("meals:receipts"),
            {"receipt_text": receipt_text},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Receipt.objects.filter(household=self.household).exists())

    def test_receipt_detail_view(self):
        receipt = Receipt.objects.create(
            user=self.user,
            household=self.household,
            raw_text="test",
            store="WALMART",
            total=Decimal("10.00"),
            receipt_date=timezone.now().date(),
        )
        response = self.client.get(
            reverse("meals:receipt_detail", kwargs={"pk": receipt.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "WALMART")


class TestRecipeIntelligenceDetailView(TestUserMixin, TestCase):
    """Tests for RecipeIntelligenceDetailView."""

    def setUp(self):
        self.user = self.create_user()
        self.client = Client()
        self.client.force_login(self.user)
        self.household = Household.objects.create(
            name="Test Household", primary_user=self.user
        )
        HouseholdMembership.objects.create(
            household=self.household, user=self.user, role="admin"
        )
        from apps.life.models import Recipe
        self.recipe = Recipe.objects.create(
            user=self.user, title="Chicken Stir Fry",
            ingredients="2 cups chicken breast\n1 cup broccoli",
            instructions="Stir fry everything.",
        )

    def test_recipe_detail_loads(self):
        response = self.client.get(
            reverse("meals:recipe_detail", kwargs={"pk": self.recipe.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "meals/recipe_detail.html")
        self.assertContains(response, "Chicken Stir Fry")

    def test_recipe_detail_with_structured_ingredients(self):
        chicken = Ingredient.objects.create(
            canonical_name="chicken breast", category="protein"
        )
        RecipeIngredient.objects.create(
            recipe=self.recipe, ingredient=chicken,
            quantity=Decimal("2"), unit="cup", order_index=0,
        )
        response = self.client.get(
            reverse("meals:recipe_detail", kwargs={"pk": self.recipe.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Chicken Breast")

    def test_recipe_detail_other_user(self):
        """Can't view another user's recipe."""
        other_user = self.create_user("other@example.com")
        from apps.life.models import Recipe
        other_recipe = Recipe.objects.create(
            user=other_user, title="Secret Recipe",
            ingredients="secret", instructions="secret",
        )
        response = self.client.get(
            reverse("meals:recipe_detail", kwargs={"pk": other_recipe.pk})
        )
        self.assertEqual(response.status_code, 404)


class TestIntentRegistration(TestCase):
    """Test that MEALS_INTENTS are registered correctly."""

    def test_meals_intents_route_correctly(self):
        from apps.core.ai_orchestrator.intent_engine import (
            MEALS_INTENTS,
            get_intent_module,
        )
        for intent in MEALS_INTENTS:
            self.assertEqual(
                get_intent_module(intent),
                "meals",
                f"Intent '{intent}' should route to 'meals' module",
            )

    def test_all_meal_intents_exist(self):
        from apps.core.ai_orchestrator.intent_engine import MEALS_INTENTS
        expected = {"suggest_dinner", "plan_meal", "scan_receipt", "add_pantry_item"}
        self.assertEqual(MEALS_INTENTS, expected)
