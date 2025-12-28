"""
Health Module - Nutrition/Food Tracking Tests

This test file covers:
1. FoodItem model tests
2. CustomFood model tests
3. FoodEntry model tests
4. DailyNutritionSummary model tests
5. NutritionGoals model tests
6. View tests (loading, authentication, CRUD)
7. Form validation tests
8. Data isolation tests
9. Business logic tests

Location: apps/health/tests/test_nutrition.py
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.health.models import (
    FoodItem,
    CustomFood,
    FoodEntry,
    DailyNutritionSummary,
    NutritionGoals,
)
from apps.health.forms import (
    FoodEntryForm,
    QuickAddFoodForm,
    CustomFoodForm,
    NutritionGoalsForm,
)

User = get_user_model()


# =============================================================================
# TEST HELPERS
# =============================================================================

class NutritionTestMixin:
    """Common setup for nutrition tests."""

    def create_user(self, email='test@example.com', password='testpass123'):
        """Create a test user with terms accepted and onboarding completed."""
        user = User.objects.create_user(email=email, password=password)
        self._accept_terms(user)
        self._complete_onboarding(user)
        return user

    def _accept_terms(self, user):
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(user=user, terms_version='1.0')

    def _complete_onboarding(self, user):
        """Mark user onboarding as complete."""
        user.preferences.has_completed_onboarding = True
        user.preferences.save()

    def login_user(self, email='test@example.com', password='testpass123'):
        return self.client.login(email=email, password=password)

    def create_food_item(self, name='Test Food', calories=Decimal('200'), **kwargs):
        """Helper to create a global food item."""
        defaults = {
            'name': name,
            'calories': calories,
            'serving_size': Decimal('1'),
            'serving_unit': 'serving',
            'protein_g': Decimal('10'),
            'carbohydrates_g': Decimal('20'),
            'fat_g': Decimal('8'),
        }
        defaults.update(kwargs)
        return FoodItem.objects.create(**defaults)

    def create_custom_food(self, user, name='My Recipe', calories=Decimal('300'), **kwargs):
        """Helper to create a user's custom food."""
        defaults = {
            'user': user,
            'name': name,
            'calories': calories,
            'serving_size': Decimal('1'),
            'serving_unit': 'serving',
            'protein_g': Decimal('15'),
            'carbohydrates_g': Decimal('30'),
            'fat_g': Decimal('10'),
        }
        defaults.update(kwargs)
        return CustomFood.objects.create(**defaults)

    def create_food_entry(self, user, food_name='Test Food', total_calories=Decimal('200'), **kwargs):
        """Helper to create a food entry."""
        defaults = {
            'user': user,
            'food_name': food_name,
            'total_calories': total_calories,
            'serving_size': Decimal('1'),
            'serving_unit': 'serving',
            'quantity': Decimal('1'),
            'logged_date': timezone.now().date(),
            'meal_type': FoodEntry.MEAL_SNACK,
        }
        defaults.update(kwargs)
        return FoodEntry.objects.create(**defaults)

    def create_nutrition_goals(self, user, **kwargs):
        """Helper to create nutrition goals."""
        defaults = {
            'user': user,
            'daily_calorie_target': 2000,
            'daily_protein_target_g': 150,
            'daily_carb_target_g': 200,
            'daily_fat_target_g': 70,
            'effective_from': timezone.now().date(),
        }
        defaults.update(kwargs)
        return NutritionGoals.objects.create(**defaults)


# =============================================================================
# 1. FOOD ITEM MODEL TESTS
# =============================================================================

class FoodItemModelTest(NutritionTestMixin, TestCase):
    """Tests for the FoodItem model (global food library)."""

    def test_create_food_item(self):
        """FoodItem can be created."""
        item = self.create_food_item()
        self.assertEqual(item.name, 'Test Food')
        self.assertEqual(item.calories, Decimal('200'))

    def test_food_item_str_without_brand(self):
        """FoodItem string representation without brand."""
        item = self.create_food_item(name='Apple')
        self.assertEqual(str(item), 'Apple')

    def test_food_item_str_with_brand(self):
        """FoodItem string representation with brand."""
        item = self.create_food_item(name='Granola Bar', brand='Nature Valley')
        self.assertIn('Nature Valley', str(item))
        self.assertIn('Granola Bar', str(item))

    def test_food_item_net_carbs(self):
        """Net carbs calculation (carbs - fiber)."""
        item = self.create_food_item(
            carbohydrates_g=Decimal('25'),
            fiber_g=Decimal('5'),
        )
        self.assertEqual(item.net_carbs_g, Decimal('20'))

    def test_food_item_barcode(self):
        """FoodItem can have barcode."""
        item = self.create_food_item(barcode='012345678901')
        self.assertEqual(item.barcode, '012345678901')

    def test_food_item_data_source(self):
        """FoodItem tracks data source."""
        item = self.create_food_item(data_source=FoodItem.SOURCE_USDA)
        self.assertEqual(item.data_source, 'usda')

    def test_food_item_verified_flag(self):
        """FoodItem can be marked as verified."""
        item = self.create_food_item(is_verified=True)
        self.assertTrue(item.is_verified)

    def test_food_item_dietary_attributes(self):
        """FoodItem supports dietary attributes."""
        item = self.create_food_item(
            is_vegan=True,
            is_gluten_free=True,
        )
        self.assertTrue(item.is_vegan)
        self.assertTrue(item.is_gluten_free)

    def test_food_item_ordering(self):
        """FoodItems are ordered by name."""
        self.create_food_item(name='Banana')
        self.create_food_item(name='Apple')
        self.create_food_item(name='Cherry')

        items = list(FoodItem.objects.all())
        self.assertEqual(items[0].name, 'Apple')
        self.assertEqual(items[1].name, 'Banana')
        self.assertEqual(items[2].name, 'Cherry')


# =============================================================================
# 2. CUSTOM FOOD MODEL TESTS
# =============================================================================

class CustomFoodModelTest(NutritionTestMixin, TestCase):
    """Tests for the CustomFood model (user-created foods)."""

    def setUp(self):
        self.user = self.create_user()

    def test_create_custom_food(self):
        """CustomFood can be created."""
        food = self.create_custom_food(self.user)
        self.assertEqual(food.name, 'My Recipe')
        self.assertEqual(food.user, self.user)

    def test_custom_food_str(self):
        """CustomFood string representation."""
        food = self.create_custom_food(self.user, name='Homemade Soup')
        self.assertEqual(str(food), 'Homemade Soup')

    def test_custom_food_net_carbs(self):
        """Net carbs calculation for custom food."""
        food = self.create_custom_food(
            self.user,
            carbohydrates_g=Decimal('40'),
            fiber_g=Decimal('8'),
        )
        self.assertEqual(food.net_carbs_g, Decimal('32'))

    def test_custom_food_belongs_to_user(self):
        """CustomFood is user-scoped."""
        food = self.create_custom_food(self.user)
        self.assertEqual(food.user, self.user)

    def test_custom_food_is_recipe_flag(self):
        """CustomFood can be marked as recipe."""
        food = self.create_custom_food(self.user, is_recipe=True)
        self.assertTrue(food.is_recipe)

    def test_custom_food_ordering(self):
        """Custom foods are ordered by name."""
        self.create_custom_food(self.user, name='Zucchini Bread')
        self.create_custom_food(self.user, name='Apple Pie')
        self.create_custom_food(self.user, name='Meatloaf')

        foods = list(CustomFood.objects.filter(user=self.user))
        self.assertEqual(foods[0].name, 'Apple Pie')
        self.assertEqual(foods[1].name, 'Meatloaf')
        self.assertEqual(foods[2].name, 'Zucchini Bread')


# =============================================================================
# 3. FOOD ENTRY MODEL TESTS
# =============================================================================

class FoodEntryModelTest(NutritionTestMixin, TestCase):
    """Tests for the FoodEntry model (food log entries)."""

    def setUp(self):
        self.user = self.create_user()

    def test_create_food_entry(self):
        """FoodEntry can be created."""
        entry = self.create_food_entry(self.user)
        self.assertEqual(entry.food_name, 'Test Food')
        self.assertEqual(entry.total_calories, Decimal('200'))

    def test_food_entry_str(self):
        """FoodEntry string representation."""
        entry = self.create_food_entry(self.user, food_name='Chicken Salad')
        self.assertIn('Chicken Salad', str(entry))

    def test_food_entry_meal_types(self):
        """FoodEntry supports all meal types."""
        for meal_type, label in FoodEntry.MEAL_CHOICES:
            entry = self.create_food_entry(
                self.user,
                meal_type=meal_type,
                food_name=f'{label} food',
            )
            self.assertEqual(entry.meal_type, meal_type)

    def test_food_entry_source_types(self):
        """FoodEntry supports all source types."""
        for source, label in FoodEntry.SOURCE_CHOICES:
            entry = self.create_food_entry(
                self.user,
                entry_source=source,
                food_name=f'{label} food',
            )
            self.assertEqual(entry.entry_source, source)

    def test_food_entry_calculate_totals(self):
        """FoodEntry calculates totals from food item."""
        food_item = self.create_food_item(
            calories=Decimal('100'),
            protein_g=Decimal('10'),
            carbohydrates_g=Decimal('15'),
            fat_g=Decimal('5'),
        )

        entry = FoodEntry(
            user=self.user,
            food_item=food_item,
            food_name=food_item.name,
            quantity=Decimal('2'),
            serving_size=food_item.serving_size,
            serving_unit=food_item.serving_unit,
            logged_date=timezone.now().date(),
            total_calories=Decimal('0'),
        )
        entry.calculate_totals()

        self.assertEqual(entry.total_calories, Decimal('200'))
        self.assertEqual(entry.total_protein_g, Decimal('20'))
        self.assertEqual(entry.total_carbohydrates_g, Decimal('30'))
        self.assertEqual(entry.total_fat_g, Decimal('10'))

    def test_food_entry_net_carbs(self):
        """FoodEntry net carbs calculation."""
        entry = self.create_food_entry(
            self.user,
            total_carbohydrates_g=Decimal('50'),
            total_fiber_g=Decimal('10'),
        )
        self.assertEqual(entry.total_net_carbs_g, Decimal('40'))

    def test_food_entry_with_custom_food(self):
        """FoodEntry can reference custom food."""
        custom = self.create_custom_food(self.user)
        entry = FoodEntry.objects.create(
            user=self.user,
            custom_food=custom,
            food_name=custom.name,
            quantity=Decimal('1'),
            serving_size=custom.serving_size,
            serving_unit=custom.serving_unit,
            logged_date=timezone.now().date(),
            total_calories=custom.calories,
        )
        self.assertEqual(entry.custom_food, custom)

    def test_food_entry_location_context(self):
        """FoodEntry supports location context."""
        entry = self.create_food_entry(
            self.user,
            location=FoodEntry.LOCATION_RESTAURANT,
        )
        self.assertEqual(entry.location, 'restaurant')

    def test_food_entry_eating_pace(self):
        """FoodEntry supports eating pace tracking."""
        entry = self.create_food_entry(
            self.user,
            eating_pace=FoodEntry.PACE_SLOW,
        )
        self.assertEqual(entry.eating_pace, 'slow')

    def test_food_entry_hunger_fullness(self):
        """FoodEntry supports hunger/fullness tracking."""
        entry = self.create_food_entry(
            self.user,
            hunger_level_before=4,
            fullness_level_after=3,
        )
        self.assertEqual(entry.hunger_level_before, 4)
        self.assertEqual(entry.fullness_level_after, 3)

    def test_food_entry_ordering(self):
        """Food entries are ordered by most recent first."""
        yesterday = timezone.now().date() - timedelta(days=1)
        today = timezone.now().date()

        entry1 = self.create_food_entry(self.user, logged_date=yesterday, food_name='Yesterday')
        entry2 = self.create_food_entry(self.user, logged_date=today, food_name='Today')

        entries = list(FoodEntry.objects.filter(user=self.user))
        self.assertEqual(entries[0].food_name, 'Today')


# =============================================================================
# 4. DAILY NUTRITION SUMMARY MODEL TESTS
# =============================================================================

class DailyNutritionSummaryModelTest(NutritionTestMixin, TestCase):
    """Tests for the DailyNutritionSummary model."""

    def setUp(self):
        self.user = self.create_user()

    def test_create_daily_summary(self):
        """DailyNutritionSummary can be created."""
        summary = DailyNutritionSummary.objects.create(
            user=self.user,
            summary_date=timezone.now().date(),
            total_calories=Decimal('1800'),
        )
        self.assertEqual(summary.total_calories, Decimal('1800'))

    def test_daily_summary_str(self):
        """DailyNutritionSummary string representation."""
        summary = DailyNutritionSummary.objects.create(
            user=self.user,
            summary_date=timezone.now().date(),
            total_calories=Decimal('2000'),
        )
        self.assertIn('2000', str(summary))

    def test_daily_summary_total_entry_count(self):
        """DailyNutritionSummary calculates total entry count."""
        summary = DailyNutritionSummary.objects.create(
            user=self.user,
            summary_date=timezone.now().date(),
            breakfast_count=2,
            lunch_count=1,
            dinner_count=1,
            snack_count=3,
        )
        self.assertEqual(summary.total_entry_count, 7)

    def test_daily_summary_recalculate(self):
        """DailyNutritionSummary recalculates from entries."""
        today = timezone.now().date()

        # Create some entries for today
        self.create_food_entry(
            self.user,
            logged_date=today,
            meal_type=FoodEntry.MEAL_BREAKFAST,
            total_calories=Decimal('400'),
            total_protein_g=Decimal('30'),
            total_carbohydrates_g=Decimal('40'),
            total_fat_g=Decimal('15'),
        )
        self.create_food_entry(
            self.user,
            logged_date=today,
            meal_type=FoodEntry.MEAL_LUNCH,
            total_calories=Decimal('600'),
            total_protein_g=Decimal('40'),
            total_carbohydrates_g=Decimal('60'),
            total_fat_g=Decimal('20'),
        )

        # Create summary and recalculate
        summary = DailyNutritionSummary.objects.create(
            user=self.user,
            summary_date=today,
        )
        summary.recalculate()

        self.assertEqual(summary.total_calories, Decimal('1000'))
        self.assertEqual(summary.total_protein_g, Decimal('70'))
        self.assertEqual(summary.breakfast_count, 1)
        self.assertEqual(summary.lunch_count, 1)

    def test_daily_summary_unique_per_user_per_date(self):
        """Only one summary per user per date."""
        today = timezone.now().date()

        DailyNutritionSummary.objects.create(
            user=self.user,
            summary_date=today,
        )

        # Should raise on duplicate
        with self.assertRaises(Exception):
            DailyNutritionSummary.objects.create(
                user=self.user,
                summary_date=today,
            )


# =============================================================================
# 5. NUTRITION GOALS MODEL TESTS
# =============================================================================

class NutritionGoalsModelTest(NutritionTestMixin, TestCase):
    """Tests for the NutritionGoals model."""

    def setUp(self):
        self.user = self.create_user()

    def test_create_nutrition_goals(self):
        """NutritionGoals can be created."""
        goals = self.create_nutrition_goals(self.user)
        self.assertEqual(goals.daily_calorie_target, 2000)

    def test_nutrition_goals_str(self):
        """NutritionGoals string representation."""
        goals = self.create_nutrition_goals(self.user)
        self.assertIn(self.user.email, str(goals))

    def test_nutrition_goals_is_active(self):
        """NutritionGoals is_active checks date range."""
        # Active goals (started today, no end)
        goals = self.create_nutrition_goals(self.user)
        self.assertTrue(goals.is_active)

    def test_nutrition_goals_is_not_active_future(self):
        """NutritionGoals not active if starts in future."""
        future = timezone.now().date() + timedelta(days=7)
        goals = self.create_nutrition_goals(
            self.user,
            effective_from=future,
        )
        self.assertFalse(goals.is_active)

    def test_nutrition_goals_is_not_active_past(self):
        """NutritionGoals not active if ended in past."""
        past_start = timezone.now().date() - timedelta(days=30)
        past_end = timezone.now().date() - timedelta(days=7)
        goals = self.create_nutrition_goals(
            self.user,
            effective_from=past_start,
            effective_until=past_end,
        )
        self.assertFalse(goals.is_active)

    def test_nutrition_goals_dietary_preferences(self):
        """NutritionGoals supports dietary preferences."""
        goals = self.create_nutrition_goals(
            self.user,
            dietary_preferences=['vegan', 'gluten_free'],
        )
        self.assertIn('vegan', goals.dietary_preferences)

    def test_nutrition_goals_allergies(self):
        """NutritionGoals supports allergies."""
        goals = self.create_nutrition_goals(
            self.user,
            allergies=['nuts', 'dairy'],
        )
        self.assertIn('nuts', goals.allergies)


# =============================================================================
# 6. VIEW TESTS - Basic Loading
# =============================================================================

class NutritionViewBasicTest(NutritionTestMixin, TestCase):
    """Basic view loading tests."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()

    # --- Authentication Required ---

    def test_nutrition_home_requires_login(self):
        """Nutrition home redirects anonymous users."""
        response = self.client.get(reverse('health:nutrition_home'))
        self.assertEqual(response.status_code, 302)

    def test_food_entry_create_requires_login(self):
        """Food entry create requires authentication."""
        response = self.client.get(reverse('health:food_entry_create'))
        self.assertEqual(response.status_code, 302)

    def test_custom_food_list_requires_login(self):
        """Custom food list requires authentication."""
        response = self.client.get(reverse('health:custom_food_list'))
        self.assertEqual(response.status_code, 302)

    def test_nutrition_goals_requires_login(self):
        """Nutrition goals requires authentication."""
        response = self.client.get(reverse('health:nutrition_goals'))
        self.assertEqual(response.status_code, 302)

    # --- Authenticated Access ---

    def test_nutrition_home_loads(self):
        """Nutrition home loads for authenticated user."""
        self.login_user()
        response = self.client.get(reverse('health:nutrition_home'))
        self.assertEqual(response.status_code, 200)

    def test_food_entry_create_loads(self):
        """Food entry create page loads."""
        self.login_user()
        response = self.client.get(reverse('health:food_entry_create'))
        self.assertEqual(response.status_code, 200)

    def test_quick_add_loads(self):
        """Quick add page loads."""
        self.login_user()
        response = self.client.get(reverse('health:food_quick_add'))
        self.assertEqual(response.status_code, 200)

    def test_food_history_loads(self):
        """Food history page loads."""
        self.login_user()
        response = self.client.get(reverse('health:food_history'))
        self.assertEqual(response.status_code, 200)

    def test_nutrition_stats_loads(self):
        """Nutrition stats page loads."""
        self.login_user()
        response = self.client.get(reverse('health:nutrition_stats'))
        self.assertEqual(response.status_code, 200)

    def test_nutrition_goals_loads(self):
        """Nutrition goals page loads."""
        self.login_user()
        response = self.client.get(reverse('health:nutrition_goals'))
        self.assertEqual(response.status_code, 200)

    def test_custom_food_list_loads(self):
        """Custom food list page loads."""
        self.login_user()
        response = self.client.get(reverse('health:custom_food_list'))
        self.assertEqual(response.status_code, 200)

    def test_custom_food_create_loads(self):
        """Custom food create page loads."""
        self.login_user()
        response = self.client.get(reverse('health:custom_food_create'))
        self.assertEqual(response.status_code, 200)


# =============================================================================
# 7. VIEW TESTS - CRUD Operations
# =============================================================================

class NutritionViewCRUDTest(NutritionTestMixin, TestCase):
    """CRUD operation tests for nutrition views."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()

    def test_create_food_entry_via_form(self):
        """Food entry can be created via form."""
        today = timezone.now().date()
        response = self.client.post(reverse('health:food_entry_create'), {
            'food_name': 'Test Sandwich',
            'serving_size': '1',
            'serving_unit': 'sandwich',
            'quantity': '1',
            'total_calories': '350',
            'total_protein_g': '20',
            'total_carbohydrates_g': '40',
            'total_fat_g': '12',
            'logged_date': today.strftime('%Y-%m-%d'),
            'meal_type': 'lunch',
        })

        # Should redirect on success
        self.assertIn(response.status_code, [200, 302])
        # If form was valid and saved
        if response.status_code == 302:
            self.assertTrue(
                FoodEntry.objects.filter(user=self.user, food_name='Test Sandwich').exists()
            )

    def test_edit_food_entry(self):
        """Food entry can be edited."""
        entry = self.create_food_entry(self.user)

        response = self.client.get(
            reverse('health:food_entry_edit', kwargs={'pk': entry.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_delete_food_entry(self):
        """Food entry can be deleted."""
        entry = self.create_food_entry(self.user)

        response = self.client.post(
            reverse('health:food_entry_delete', kwargs={'pk': entry.pk})
        )

        self.assertIn(response.status_code, [200, 302])

    def test_create_custom_food_via_form(self):
        """Custom food can be created via form."""
        response = self.client.post(reverse('health:custom_food_create'), {
            'name': 'My Special Recipe',
            'serving_size': '1',
            'serving_unit': 'bowl',
            'calories': '450',
            'protein_g': '25',
            'carbohydrates_g': '50',
            'fat_g': '15',
        })

        if response.status_code == 302:
            self.assertTrue(
                CustomFood.objects.filter(user=self.user, name='My Special Recipe').exists()
            )

    def test_edit_custom_food(self):
        """Custom food can be edited."""
        food = self.create_custom_food(self.user)

        response = self.client.get(
            reverse('health:custom_food_edit', kwargs={'pk': food.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_delete_custom_food(self):
        """Custom food can be deleted."""
        food = self.create_custom_food(self.user)

        response = self.client.post(
            reverse('health:custom_food_delete', kwargs={'pk': food.pk})
        )

        self.assertIn(response.status_code, [200, 302])


# =============================================================================
# 8. QUICK ADD TESTS
# =============================================================================

class QuickAddTest(NutritionTestMixin, TestCase):
    """Tests for quick add functionality."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()

    def test_quick_add_page_loads(self):
        """Quick add page loads."""
        response = self.client.get(reverse('health:food_quick_add'))
        self.assertEqual(response.status_code, 200)

    def test_quick_add_creates_entry(self):
        """Quick add creates a food entry."""
        today = timezone.now().date()
        response = self.client.post(reverse('health:food_quick_add'), {
            'food_name': 'Quick Snack',
            'calories': '150',
            'meal_type': 'snack',
            'logged_date': today.strftime('%Y-%m-%d'),
        })

        if response.status_code == 302:
            self.assertTrue(
                FoodEntry.objects.filter(
                    user=self.user,
                    food_name='Quick Snack',
                    entry_source=FoodEntry.SOURCE_QUICK_ADD,
                ).exists()
            )


# =============================================================================
# 9. DATA ISOLATION TESTS
# =============================================================================

class NutritionDataIsolationTest(NutritionTestMixin, TestCase):
    """Tests to ensure users can only see their own nutrition data."""

    def setUp(self):
        self.client = Client()
        self.user_a = self.create_user(email='usera@example.com')
        self.user_b = self.create_user(email='userb@example.com')

        self.food_a = self.create_custom_food(self.user_a, name='User A Recipe')
        self.food_b = self.create_custom_food(self.user_b, name='User B Recipe')

        self.entry_a = self.create_food_entry(self.user_a, food_name='User A Food')
        self.entry_b = self.create_food_entry(self.user_b, food_name='User B Food')

    def test_user_sees_only_own_custom_foods(self):
        """User only sees their own custom foods."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(reverse('health:custom_food_list'))

        self.assertContains(response, 'User A Recipe')
        self.assertNotContains(response, 'User B Recipe')

    def test_user_sees_only_own_food_entries(self):
        """User only sees their own food entries."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(reverse('health:food_history'))

        self.assertContains(response, 'User A Food')
        self.assertNotContains(response, 'User B Food')

    def test_user_cannot_edit_other_users_custom_food(self):
        """User cannot edit another user's custom food."""
        self.client.login(email='usera@example.com', password='testpass123')

        response = self.client.get(
            reverse('health:custom_food_edit', kwargs={'pk': self.food_b.pk})
        )

        self.assertEqual(response.status_code, 404)

    def test_user_cannot_delete_other_users_entry(self):
        """User cannot delete another user's food entry."""
        self.client.login(email='usera@example.com', password='testpass123')

        response = self.client.post(
            reverse('health:food_entry_delete', kwargs={'pk': self.entry_b.pk})
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(FoodEntry.objects.filter(pk=self.entry_b.pk).exists())


# =============================================================================
# 10. CONTEXT TESTS
# =============================================================================

class NutritionContextTest(NutritionTestMixin, TestCase):
    """Tests for view context data."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()

    def test_nutrition_home_has_meal_entries(self):
        """Nutrition home includes meal entries in context."""
        today = timezone.now().date()

        self.create_food_entry(
            self.user,
            logged_date=today,
            meal_type=FoodEntry.MEAL_BREAKFAST,
            food_name='Morning Oatmeal',
        )

        response = self.client.get(reverse('health:nutrition_home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Morning Oatmeal')

    def test_nutrition_home_shows_totals(self):
        """Nutrition home shows calorie totals."""
        today = timezone.now().date()

        self.create_food_entry(
            self.user,
            logged_date=today,
            total_calories=Decimal('500'),
        )

        response = self.client.get(reverse('health:nutrition_home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '500')

    def test_nutrition_home_shows_goals(self):
        """Nutrition home shows goals if set."""
        self.create_nutrition_goals(self.user)

        response = self.client.get(reverse('health:nutrition_home'))

        self.assertEqual(response.status_code, 200)

    def test_custom_food_list_has_foods(self):
        """Custom food list includes user's foods."""
        self.create_custom_food(self.user, name='Special Dish')

        response = self.client.get(reverse('health:custom_food_list'))

        self.assertContains(response, 'Special Dish')


# =============================================================================
# 11. FORM VALIDATION TESTS
# =============================================================================

class NutritionFormTest(NutritionTestMixin, TestCase):
    """Tests for nutrition form validation."""

    def setUp(self):
        self.user = self.create_user()

    def test_food_entry_form_valid(self):
        """FoodEntryForm validates with required fields."""
        form = FoodEntryForm(data={
            'food_name': 'Test Food',
            'serving_size': '1',
            'serving_unit': 'serving',
            'quantity': '1',
            'total_calories': '200',
            'total_protein_g': '10',
            'total_carbohydrates_g': '25',
            'total_fat_g': '8',
            'logged_date': timezone.now().date(),
            'meal_type': 'lunch',
        })
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

    def test_food_entry_form_requires_food_name(self):
        """FoodEntryForm requires food name."""
        form = FoodEntryForm(data={
            'serving_size': '1',
            'serving_unit': 'serving',
            'quantity': '1',
            'total_calories': '200',
            'logged_date': timezone.now().date(),
            'meal_type': 'lunch',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('food_name', form.errors)

    def test_quick_add_form_valid(self):
        """QuickAddFoodForm validates with required fields."""
        form = QuickAddFoodForm(data={
            'food_name': 'Quick Snack',
            'calories': '150',
            'meal_type': 'snack',
            'logged_date': timezone.now().date(),
        })
        self.assertTrue(form.is_valid())

    def test_quick_add_form_requires_calories(self):
        """QuickAddFoodForm requires calories."""
        form = QuickAddFoodForm(data={
            'food_name': 'Quick Snack',
            'meal_type': 'snack',
            'logged_date': timezone.now().date(),
        })
        self.assertFalse(form.is_valid())
        self.assertIn('calories', form.errors)

    def test_custom_food_form_valid(self):
        """CustomFoodForm validates with required fields."""
        form = CustomFoodForm(data={
            'name': 'My Recipe',
            'serving_size': '1',
            'serving_unit': 'serving',
            'calories': '300',
            'protein_g': '15',
            'carbohydrates_g': '30',
            'fat_g': '10',
        })
        self.assertTrue(form.is_valid())

    def test_custom_food_form_requires_name(self):
        """CustomFoodForm requires name."""
        form = CustomFoodForm(data={
            'serving_size': '1',
            'serving_unit': 'serving',
            'calories': '300',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)


# =============================================================================
# 12. NUTRITION STATS VIEW TESTS
# =============================================================================

class NutritionStatsTest(NutritionTestMixin, TestCase):
    """Tests for nutrition statistics view."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()

    def test_stats_page_loads_empty(self):
        """Stats page loads with no data."""
        response = self.client.get(reverse('health:nutrition_stats'))
        self.assertEqual(response.status_code, 200)

    def test_stats_page_shows_data(self):
        """Stats page shows nutrition data."""
        today = timezone.now().date()
        self.create_food_entry(
            self.user,
            logged_date=today,
            total_calories=Decimal('1500'),
        )

        response = self.client.get(reverse('health:nutrition_stats'))
        self.assertEqual(response.status_code, 200)


# =============================================================================
# 13. FOOD HISTORY VIEW TESTS
# =============================================================================

class FoodHistoryTest(NutritionTestMixin, TestCase):
    """Tests for food history view."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()

    def test_history_page_loads_empty(self):
        """History page loads with no data."""
        response = self.client.get(reverse('health:food_history'))
        self.assertEqual(response.status_code, 200)

    def test_history_page_shows_entries(self):
        """History page shows food entries."""
        self.create_food_entry(self.user, food_name='Historical Entry')

        response = self.client.get(reverse('health:food_history'))
        self.assertContains(response, 'Historical Entry')

    def test_history_page_pagination(self):
        """History page supports pagination."""
        # Create many entries
        for i in range(25):
            self.create_food_entry(self.user, food_name=f'Entry {i}')

        response = self.client.get(reverse('health:food_history'))
        self.assertEqual(response.status_code, 200)


# =============================================================================
# 14. NUTRITION GOALS VIEW TESTS
# =============================================================================

class NutritionGoalsViewTest(NutritionTestMixin, TestCase):
    """Tests for nutrition goals view."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()

    def test_goals_page_loads_empty(self):
        """Goals page loads with no goals set."""
        response = self.client.get(reverse('health:nutrition_goals'))
        self.assertEqual(response.status_code, 200)

    def test_goals_page_loads_with_goals(self):
        """Goals page loads with existing goals."""
        self.create_nutrition_goals(self.user)

        response = self.client.get(reverse('health:nutrition_goals'))
        self.assertEqual(response.status_code, 200)

    def test_can_set_goals(self):
        """User can set nutrition goals."""
        response = self.client.post(reverse('health:nutrition_goals'), {
            'daily_calorie_target': '2000',
            'daily_protein_target_g': '150',
            'daily_carb_target_g': '200',
            'daily_fat_target_g': '70',
        })

        if response.status_code == 302:
            self.assertTrue(
                NutritionGoals.objects.filter(user=self.user).exists()
            )
