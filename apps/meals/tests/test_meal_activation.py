"""
Tests for Meal Intelligence Progressive Activation.

Covers:
- Below threshold blocks scoring
- Exactly threshold activates
- Setup mode renders correctly on dashboard
- Setup mode renders correctly on suggestions
- Soft-skip preserves state
- Activation timestamp stored
- Setup wizard renders
- CoS context reflects activation state
"""

from decimal import Decimal

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from apps.meals.models import (
    Household,
    HouseholdMembership,
    Ingredient,
    PantryItem,
)
from apps.meals.services.activation import (
    PANTRY_REQUIRED,
    RECIPE_REQUIRED,
    ActivationStatus,
    get_activation_status,
    invalidate_activation_cache,
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


class TestActivationService(TestUserMixin, TestCase):
    """Tests for MealActivationService."""

    def setUp(self):
        self.user = self.create_user()
        self.household = Household.objects.create(
            name="Test Household", primary_user=self.user
        )
        HouseholdMembership.objects.create(
            household=self.household, user=self.user, role="admin"
        )
        invalidate_activation_cache(self.user.id)

    def _add_pantry_items(self, count):
        """Add pantry items for the household."""
        for i in range(count):
            ingredient = Ingredient.objects.create(
                canonical_name=f"ingredient_{i}_{self.id()}", category="other"
            )
            PantryItem.objects.create(
                household=self.household,
                ingredient=ingredient,
                quantity=Decimal("100"),
                unit="g",
            )

    def _add_recipes(self, count):
        """Add recipes for the user."""
        from apps.life.models import Recipe

        for i in range(count):
            Recipe.objects.create(
                user=self.user,
                title=f"Recipe {i} {self.id()}",
                ingredients="flour, sugar",
                instructions="Mix.",
            )

    def test_below_threshold_not_ready(self):
        """No pantry items and no recipes = not ready."""
        status = get_activation_status(self.user, self.household)
        self.assertFalse(status.is_ready)
        self.assertEqual(status.pantry_count, 0)
        self.assertEqual(status.recipe_count, 0)

    def test_partial_pantry_not_ready(self):
        """Some pantry but below threshold = not ready."""
        self._add_pantry_items(3)
        invalidate_activation_cache(self.user.id)
        status = get_activation_status(self.user, self.household)
        self.assertFalse(status.is_ready)
        self.assertEqual(status.pantry_count, 3)

    def test_partial_recipes_not_ready(self):
        """Enough pantry but too few recipes = not ready."""
        self._add_pantry_items(PANTRY_REQUIRED)
        self._add_recipes(1)
        invalidate_activation_cache(self.user.id)
        status = get_activation_status(self.user, self.household)
        self.assertFalse(status.is_ready)

    def test_exactly_threshold_activates(self):
        """Exactly at threshold = ready."""
        self._add_pantry_items(PANTRY_REQUIRED)
        self._add_recipes(RECIPE_REQUIRED)
        invalidate_activation_cache(self.user.id)
        status = get_activation_status(self.user, self.household)
        self.assertTrue(status.is_ready)
        self.assertEqual(status.pantry_count, PANTRY_REQUIRED)
        self.assertEqual(status.recipe_count, RECIPE_REQUIRED)

    def test_above_threshold_ready(self):
        """Above threshold = ready."""
        self._add_pantry_items(10)
        self._add_recipes(5)
        invalidate_activation_cache(self.user.id)
        status = get_activation_status(self.user, self.household)
        self.assertTrue(status.is_ready)

    def test_activation_timestamp_stored(self):
        """Activation sets meals_activated_at on household."""
        self.assertIsNone(self.household.meals_activated_at)
        self._add_pantry_items(PANTRY_REQUIRED)
        self._add_recipes(RECIPE_REQUIRED)
        invalidate_activation_cache(self.user.id)
        get_activation_status(self.user, self.household)
        self.household.refresh_from_db()
        self.assertIsNotNone(self.household.meals_activated_at)

    def test_activation_timestamp_not_overwritten(self):
        """Once activated_at is set, it stays the same."""
        original_time = timezone.now()
        self.household.meals_activated_at = original_time
        self.household.save()
        self._add_pantry_items(PANTRY_REQUIRED)
        self._add_recipes(RECIPE_REQUIRED)
        invalidate_activation_cache(self.user.id)
        get_activation_status(self.user, self.household)
        self.household.refresh_from_db()
        self.assertEqual(self.household.meals_activated_at, original_time)

    def test_missing_requirements_both(self):
        """Missing both pantry and recipes."""
        status = get_activation_status(self.user, self.household)
        missing = status.missing
        self.assertEqual(len(missing), 2)
        self.assertIn("pantry", missing[0].lower())
        self.assertIn("recipe", missing[1].lower())

    def test_missing_requirements_pantry_only(self):
        """Missing pantry only."""
        self._add_pantry_items(2)
        self._add_recipes(RECIPE_REQUIRED)
        invalidate_activation_cache(self.user.id)
        status = get_activation_status(self.user, self.household)
        missing = status.missing
        self.assertEqual(len(missing), 1)
        self.assertIn("pantry", missing[0].lower())

    def test_progress_percentages(self):
        """Progress percentages calculated correctly."""
        self._add_pantry_items(3)
        self._add_recipes(1)
        invalidate_activation_cache(self.user.id)
        status = get_activation_status(self.user, self.household)
        self.assertEqual(status.pantry_pct, 60)  # 3/5 = 60%
        self.assertEqual(status.recipe_pct, 33)  # 1/3 = 33%

    def test_progress_capped_at_100(self):
        """Progress does not exceed 100%."""
        self._add_pantry_items(10)
        self._add_recipes(10)
        invalidate_activation_cache(self.user.id)
        status = get_activation_status(self.user, self.household)
        self.assertEqual(status.pantry_pct, 100)
        self.assertEqual(status.recipe_pct, 100)

    def test_cache_invalidation(self):
        """Cache invalidation makes next call re-query."""
        status1 = get_activation_status(self.user, self.household)
        self.assertFalse(status1.is_ready)
        self._add_pantry_items(PANTRY_REQUIRED)
        self._add_recipes(RECIPE_REQUIRED)
        # Without invalidation, cache would return old result
        invalidate_activation_cache(self.user.id)
        status2 = get_activation_status(self.user, self.household)
        self.assertTrue(status2.is_ready)


class TestDashboardSetupMode(TestUserMixin, TestCase):
    """Tests for dashboard setup mode rendering."""

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
        invalidate_activation_cache(self.user.id)

    def test_dashboard_setup_mode_renders(self):
        """Dashboard shows setup hero when below threshold."""
        response = self.client.get(reverse("meals:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kitchen Intelligence Initialization")
        self.assertContains(response, "Initialize (3 Minutes)")

    def test_dashboard_setup_mode_shows_capabilities(self):
        """Dashboard shows capability tags in setup mode."""
        response = self.client.get(reverse("meals:dashboard"))
        self.assertContains(response, "Blood sugar protection")
        self.assertContains(response, "Waste reduction")
        self.assertContains(response, "capability-tag")

    def test_dashboard_setup_mode_shows_preview_cards(self):
        """Dashboard shows locked preview cards in setup mode."""
        response = self.client.get(reverse("meals:dashboard"))
        self.assertContains(response, "What Activates Next")
        self.assertContains(response, "Optimized Dinner")
        self.assertContains(response, "Expiration Intelligence")
        self.assertContains(response, "Grocery Optimization")
        self.assertContains(response, "preview-card locked")

    def test_dashboard_setup_mode_no_dinner_suggestion(self):
        """Dashboard does NOT show dinner suggestions in setup mode."""
        response = self.client.get(reverse("meals:dashboard"))
        self.assertNotContains(response, "Tonight&#x27;s Recommendation")
        self.assertNotContains(response, "tonight-hero-score")

    def test_dashboard_setup_mode_shows_progress(self):
        """Dashboard shows progress bars in setup mode."""
        response = self.client.get(reverse("meals:dashboard"))
        self.assertContains(response, "0 / 5")  # pantry
        self.assertContains(response, "0 / 3")  # recipes

    def test_dashboard_setup_mode_with_partial_data(self):
        """Dashboard shows correct counts with partial data."""
        for i in range(3):
            ingredient = Ingredient.objects.create(
                canonical_name=f"item_{i}", category="other"
            )
            PantryItem.objects.create(
                household=self.household,
                ingredient=ingredient,
                quantity=Decimal("100"),
                unit="g",
            )
        invalidate_activation_cache(self.user.id)
        response = self.client.get(reverse("meals:dashboard"))
        self.assertContains(response, "3 / 5")

    def test_dashboard_normal_mode_when_ready(self):
        """Dashboard shows normal mode when threshold met."""
        for i in range(PANTRY_REQUIRED):
            ingredient = Ingredient.objects.create(
                canonical_name=f"item_{i}", category="other"
            )
            PantryItem.objects.create(
                household=self.household,
                ingredient=ingredient,
                quantity=Decimal("100"),
                unit="g",
            )
        from apps.life.models import Recipe

        for i in range(RECIPE_REQUIRED):
            Recipe.objects.create(
                user=self.user,
                title=f"Recipe {i}",
                ingredients="flour",
                instructions="Mix.",
            )
        invalidate_activation_cache(self.user.id)
        response = self.client.get(reverse("meals:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Kitchen Intelligence Initialization")


class TestSuggestionsSetupMode(TestUserMixin, TestCase):
    """Tests for suggestions page when below threshold."""

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
        invalidate_activation_cache(self.user.id)

    def test_suggestions_setup_mode(self):
        """Suggestions shows setup required message when below threshold."""
        response = self.client.get(reverse("meals:suggestions"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Setup Required")
        self.assertContains(response, "Complete Setup")

    def test_suggestions_no_scoring_in_setup_mode(self):
        """Suggestions does NOT run scoring engine when below threshold."""
        from apps.life.models import Recipe

        Recipe.objects.create(
            user=self.user,
            title="Test Recipe",
            ingredients="flour",
            instructions="Mix.",
        )
        response = self.client.get(reverse("meals:suggestions"))
        # Should show setup required, not recipe cards
        self.assertContains(response, "Setup Required")
        self.assertNotContains(response, "Optimal Tonight")


class TestSetupWizard(TestUserMixin, TestCase):
    """Tests for MealsSetupView."""

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
        invalidate_activation_cache(self.user.id)

    def test_setup_page_loads(self):
        """Setup wizard loads successfully."""
        response = self.client.get(reverse("meals:setup"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kitchen Intelligence Setup")

    def test_setup_shows_step_1_first(self):
        """Setup starts at step 1 (Pantry) when no data."""
        response = self.client.get(reverse("meals:setup"))
        self.assertContains(response, "Step 1: Stock Your Pantry")

    def test_setup_step_2_when_pantry_done(self):
        """Setup shows step 2 when pantry threshold met."""
        for i in range(PANTRY_REQUIRED):
            ingredient = Ingredient.objects.create(
                canonical_name=f"item_{i}", category="other"
            )
            PantryItem.objects.create(
                household=self.household,
                ingredient=ingredient,
                quantity=Decimal("100"),
                unit="g",
            )
        invalidate_activation_cache(self.user.id)
        response = self.client.get(reverse("meals:setup"))
        self.assertEqual(response.context["current_step"], 2)

    def test_setup_shows_activation_when_ready(self):
        """Setup shows activation message when thresholds met."""
        for i in range(PANTRY_REQUIRED):
            ingredient = Ingredient.objects.create(
                canonical_name=f"item_{i}", category="other"
            )
            PantryItem.objects.create(
                household=self.household,
                ingredient=ingredient,
                quantity=Decimal("100"),
                unit="g",
            )
        from apps.life.models import Recipe

        for i in range(RECIPE_REQUIRED):
            Recipe.objects.create(
                user=self.user,
                title=f"Recipe {i}",
                ingredients="flour",
                instructions="Mix.",
            )
        invalidate_activation_cache(self.user.id)
        response = self.client.get(reverse("meals:setup"))
        self.assertContains(response, "Kitchen Intelligence Activated")

    def test_setup_skip_available(self):
        """Skip button available when not ready."""
        response = self.client.get(reverse("meals:setup"))
        self.assertContains(response, "Skip for now")


class TestSoftSkipBehavior(TestUserMixin, TestCase):
    """Tests that soft-skip preserves setup state."""

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
        invalidate_activation_cache(self.user.id)

    def test_dashboard_accessible_in_setup_mode(self):
        """Dashboard is accessible even in setup mode (soft skip)."""
        response = self.client.get(reverse("meals:dashboard"))
        self.assertEqual(response.status_code, 200)
        # Shows setup content, not an error
        self.assertContains(response, "Kitchen Intelligence Initialization")

    def test_pantry_accessible_in_setup_mode(self):
        """Pantry page works during setup mode."""
        response = self.client.get(reverse("meals:pantry"))
        self.assertEqual(response.status_code, 200)

    def test_setup_mode_persists_until_threshold(self):
        """Setup mode stays even if user navigates away and back."""
        # Visit dashboard - setup mode
        response = self.client.get(reverse("meals:dashboard"))
        self.assertContains(response, "Kitchen Intelligence Initialization")

        # Visit pantry
        self.client.get(reverse("meals:pantry"))

        # Come back to dashboard - still setup mode
        response = self.client.get(reverse("meals:dashboard"))
        self.assertContains(response, "Kitchen Intelligence Initialization")


class TestCoSActivationContext(TestUserMixin, TestCase):
    """Tests for CoS meals context with activation state."""

    def setUp(self):
        self.user = self.create_user()
        self.household = Household.objects.create(
            name="Test Household", primary_user=self.user
        )
        HouseholdMembership.objects.create(
            household=self.household, user=self.user, role="admin"
        )
        invalidate_activation_cache(self.user.id)

    def test_cos_context_not_activated(self):
        """CoS context shows setup_needed when below threshold."""
        from apps.core.ai_orchestrator.cos_context import _build_meals_context

        context = _build_meals_context(self.user)
        meals = context.get("meals_context", {})
        self.assertFalse(meals.get("activated"))
        self.assertTrue(meals.get("setup_needed"))
        self.assertEqual(meals.get("pantry_required"), PANTRY_REQUIRED)
        self.assertEqual(meals.get("recipe_required"), RECIPE_REQUIRED)
        self.assertEqual(meals.get("setup_url"), "/meals/setup/")

    def test_cos_context_activated(self):
        """CoS context shows activated when threshold met."""
        for i in range(PANTRY_REQUIRED):
            ingredient = Ingredient.objects.create(
                canonical_name=f"item_{i}", category="other"
            )
            PantryItem.objects.create(
                household=self.household,
                ingredient=ingredient,
                quantity=Decimal("100"),
                unit="g",
            )
        from apps.life.models import Recipe

        for i in range(RECIPE_REQUIRED):
            Recipe.objects.create(
                user=self.user,
                title=f"Recipe {i}",
                ingredients="flour",
                instructions="Mix.",
            )
        invalidate_activation_cache(self.user.id)
        from apps.core.ai_orchestrator.cos_context import _build_meals_context

        context = _build_meals_context(self.user)
        meals = context.get("meals_context", {})
        self.assertTrue(meals.get("activated"))
        self.assertNotIn("setup_needed", meals)
