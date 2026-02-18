# ==============================================================================
# Tests for Nutrition Log Upgrade — Phase 1-5
# Tests: compute_totals, build_snapshot, copy entry/meal/day,
#        meal templates, audit trails, FoodItemOverride
# ==============================================================================

import json
from datetime import date, time
from decimal import Decimal

from django.conf import settings
from django.test import TestCase, RequestFactory
from django.urls import reverse

from apps.core.tests.test_core_comprehensive import CoreTestMixin
from apps.health.models import (
    CustomFood,
    FoodEntry,
    FoodItem,
    FoodItemOverride,
    MealTemplate,
    MealTemplateItem,
    NutritionEntryAudit,
)
from apps.health.services.nutrition_calculator import (
    build_snapshot,
    compute_totals,
    snapshot_from_totals,
)


class ComputeTotalsTest(TestCase):
    """Tests for the authoritative nutrient math function."""

    def test_quantity_1_returns_same_values(self):
        snapshot = {'calories': 200, 'protein_g': 10, 'fat_g': 5}
        totals = compute_totals(snapshot, 1)
        self.assertEqual(totals['total_calories'], 200.0)
        self.assertEqual(totals['total_protein_g'], 10.0)
        self.assertEqual(totals['total_fat_g'], 5.0)

    def test_quantity_2_doubles_all(self):
        snapshot = {'calories': 100, 'protein_g': 8, 'carbohydrates_g': 25, 'fat_g': 3}
        totals = compute_totals(snapshot, 2)
        self.assertEqual(totals['total_calories'], 200.0)
        self.assertEqual(totals['total_protein_g'], 16.0)
        self.assertEqual(totals['total_carbohydrates_g'], 50.0)
        self.assertEqual(totals['total_fat_g'], 6.0)

    def test_quantity_half_halves_all(self):
        snapshot = {'calories': 100, 'protein_g': 10}
        totals = compute_totals(snapshot, 0.5)
        self.assertEqual(totals['total_calories'], 50.0)
        self.assertEqual(totals['total_protein_g'], 5.0)

    def test_quantity_decimal_precision(self):
        snapshot = {'calories': 10, 'carbohydrates_g': 4}
        totals = compute_totals(snapshot, Decimal('0.33'))
        self.assertEqual(totals['total_calories'], 3.3)
        self.assertEqual(totals['total_carbohydrates_g'], 1.32)

    def test_none_values_preserved_as_none(self):
        snapshot = {'calories': 100, 'sodium_mg': None}
        totals = compute_totals(snapshot, 2)
        self.assertEqual(totals['total_calories'], 200.0)
        self.assertIsNone(totals['total_sodium_mg'])

    def test_zero_quantity_defaults_to_1(self):
        """compute_totals with qty=None should default to 1."""
        snapshot = {'calories': 100}
        totals = compute_totals(snapshot, None)
        self.assertEqual(totals['total_calories'], 100.0)

    def test_string_quantity_handled(self):
        snapshot = {'calories': 100}
        totals = compute_totals(snapshot, '3')
        self.assertEqual(totals['total_calories'], 300.0)


class BuildSnapshotTest(TestCase):
    """Tests for building per-serving snapshots from food sources."""

    def test_snapshot_from_food_item(self):
        item = FoodItem(
            name='Test', serving_size=1, serving_unit='serving',
            calories=200, protein_g=10, carbohydrates_g=25,
            fat_g=8, fiber_g=3, sugar_g=5,
            saturated_fat_g=2, sodium_mg=150,
        )
        snapshot = build_snapshot(item)
        self.assertEqual(snapshot['calories'], 200.0)
        self.assertEqual(snapshot['protein_g'], 10.0)
        self.assertEqual(snapshot['sodium_mg'], 150.0)

    def test_snapshot_from_custom_food(self):
        cf = CustomFood(
            name='My Food', serving_size=1, serving_unit='serving',
            calories=100, protein_g=5, carbohydrates_g=15,
            fat_g=3, fiber_g=1, sugar_g=2, saturated_fat_g=1,
        )
        snapshot = build_snapshot(cf)
        self.assertEqual(snapshot['calories'], 100.0)
        self.assertEqual(snapshot['protein_g'], 5.0)

    def test_snapshot_skips_none_fields(self):
        item = FoodItem(
            name='Test', serving_size=1, serving_unit='serving',
            calories=100, protein_g=0, carbohydrates_g=0,
            fat_g=0, fiber_g=0, sugar_g=0, saturated_fat_g=0,
        )
        # sodium_mg is None by default
        snapshot = build_snapshot(item)
        self.assertNotIn('sodium_mg', snapshot)


class SnapshotFromTotalsTest(TestCase):
    """Tests for reverse-computing snapshots from totals."""

    def test_basic_reverse(self):
        totals = {'total_calories': 400, 'total_protein_g': 20}
        snapshot = snapshot_from_totals(totals, 2)
        self.assertEqual(snapshot['calories'], 200.0)
        self.assertEqual(snapshot['protein_g'], 10.0)

    def test_zero_quantity_defaults_to_1(self):
        totals = {'total_calories': 100}
        snapshot = snapshot_from_totals(totals, 0)
        self.assertEqual(snapshot['calories'], 100.0)


class FoodEntrySnapshotTest(CoreTestMixin, TestCase):
    """Tests that FoodEntry correctly uses snapshot_nutrients."""

    def setUp(self):
        self.user = self.create_user()
        self.food_item = FoodItem.objects.create(
            name='Test Food', brand='TestBrand',
            serving_size=1, serving_unit='serving',
            calories=200, protein_g=10, carbohydrates_g=25,
            fat_g=8, fiber_g=3, sugar_g=5, saturated_fat_g=2,
        )

    def test_calculate_totals_from_snapshot(self):
        entry = FoodEntry(
            user=self.user,
            food_name='Test Food',
            quantity=2,
            serving_size=1,
            serving_unit='serving',
            logged_date=date.today(),
            snapshot_nutrients={
                'calories': 200, 'protein_g': 10, 'carbohydrates_g': 25,
                'fat_g': 8, 'fiber_g': 3, 'sugar_g': 5, 'saturated_fat_g': 2,
            },
        )
        entry.calculate_totals()
        self.assertEqual(float(entry.total_calories), 400.0)
        self.assertEqual(float(entry.total_protein_g), 20.0)

    def test_calculate_totals_fallback_to_food_item(self):
        """If no snapshot exists, calculate_totals builds one from food_item."""
        entry = FoodEntry(
            user=self.user,
            food_item=self.food_item,
            food_name='Test Food',
            quantity=1,
            serving_size=1,
            serving_unit='serving',
            logged_date=date.today(),
        )
        entry.calculate_totals()
        self.assertIn('calories', entry.snapshot_nutrients)
        self.assertEqual(float(entry.total_calories), 200.0)


class CopyEntryAPITest(CoreTestMixin, TestCase):
    """Tests for copy entry API."""

    def setUp(self):
        self.user = self.create_user()
        self.client.force_login(self.user)
        self.entry = FoodEntry.objects.create(
            user=self.user,
            food_name='Original Food',
            food_brand='TestBrand',
            quantity=Decimal('1.5'),
            serving_size=1,
            serving_unit='serving',
            total_calories=300,
            total_protein_g=15,
            total_carbohydrates_g=38,
            total_fat_g=12,
            total_fiber_g=4,
            total_sugar_g=8,
            total_saturated_fat_g=3,
            logged_date=date(2026, 2, 1),
            meal_type='breakfast',
            snapshot_nutrients={
                'calories': 200, 'protein_g': 10, 'carbohydrates_g': 25,
                'fat_g': 8, 'fiber_g': 3, 'sugar_g': 5, 'saturated_fat_g': 2,
            },
            data_source_used='local',
            confidence_score=95,
        )

    def test_copy_entry_success(self):
        url = reverse('health:copy_entry_api')
        resp = self.client.post(url, json.dumps({
            'entry_id': self.entry.pk,
            'target_date': '2026-02-10',
            'target_meal': 'lunch',
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])

        new_entry = FoodEntry.objects.get(pk=data['new_entry_id'])
        self.assertEqual(new_entry.food_name, 'Original Food')
        self.assertEqual(new_entry.logged_date, date(2026, 2, 10))
        self.assertEqual(new_entry.meal_type, 'lunch')
        self.assertEqual(new_entry.copied_from_entry_id, self.entry.pk)
        self.assertEqual(float(new_entry.total_calories), 300.0)
        self.assertEqual(new_entry.snapshot_nutrients, self.entry.snapshot_nutrients)

        # Audit trail
        audit = NutritionEntryAudit.objects.filter(entry=new_entry).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.change_type, 'copy_action')

    def test_copy_entry_invalid_date(self):
        url = reverse('health:copy_entry_api')
        resp = self.client.post(url, json.dumps({
            'entry_id': self.entry.pk,
            'target_date': 'not-a-date',
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_copy_entry_not_found(self):
        url = reverse('health:copy_entry_api')
        resp = self.client.post(url, json.dumps({
            'entry_id': 99999,
            'target_date': '2026-02-10',
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 404)


class CopyMealAPITest(CoreTestMixin, TestCase):
    """Tests for copy meal API."""

    def setUp(self):
        self.user = self.create_user()
        self.client.force_login(self.user)
        # Create 3 breakfast entries
        for i in range(3):
            FoodEntry.objects.create(
                user=self.user,
                food_name=f'Breakfast Item {i}',
                quantity=1,
                serving_size=1,
                serving_unit='serving',
                total_calories=100 * (i + 1),
                logged_date=date(2026, 2, 1),
                meal_type='breakfast',
                snapshot_nutrients={'calories': 100 * (i + 1)},
            )

    def test_copy_meal_success(self):
        url = reverse('health:copy_meal_api')
        resp = self.client.post(url, json.dumps({
            'source_date': '2026-02-01',
            'source_meal': 'breakfast',
            'target_date': '2026-02-15',
            'target_meal': 'lunch',
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['copied_count'], 3)

        # Verify entries created
        new_entries = FoodEntry.objects.filter(
            user=self.user, logged_date=date(2026, 2, 15), meal_type='lunch'
        )
        self.assertEqual(new_entries.count(), 3)


class CopyDayAPITest(CoreTestMixin, TestCase):
    """Tests for copy day API."""

    def setUp(self):
        self.user = self.create_user()
        self.client.force_login(self.user)
        for meal in ['breakfast', 'lunch']:
            FoodEntry.objects.create(
                user=self.user,
                food_name=f'{meal} item',
                quantity=1,
                serving_size=1,
                serving_unit='serving',
                total_calories=200,
                logged_date=date(2026, 2, 1),
                meal_type=meal,
                snapshot_nutrients={'calories': 200},
            )

    def test_copy_day_merge(self):
        # Create existing entry on target date
        FoodEntry.objects.create(
            user=self.user,
            food_name='Existing',
            quantity=1,
            serving_size=1,
            serving_unit='serving',
            total_calories=100,
            logged_date=date(2026, 2, 15),
            meal_type='snack',
            snapshot_nutrients={'calories': 100},
        )

        url = reverse('health:copy_day_api')
        resp = self.client.post(url, json.dumps({
            'source_date': '2026-02-01',
            'target_date': '2026-02-15',
            'mode': 'merge',
        }), content_type='application/json')
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['copied_count'], 2)

        # Existing entry should still be there (merge)
        total = FoodEntry.objects.filter(
            user=self.user, logged_date=date(2026, 2, 15), status='active'
        ).count()
        self.assertEqual(total, 3)  # 2 copied + 1 existing

    def test_copy_day_replace(self):
        FoodEntry.objects.create(
            user=self.user,
            food_name='Will Be Replaced',
            quantity=1,
            serving_size=1,
            serving_unit='serving',
            total_calories=100,
            logged_date=date(2026, 2, 15),
            meal_type='snack',
            snapshot_nutrients={'calories': 100},
        )

        url = reverse('health:copy_day_api')
        resp = self.client.post(url, json.dumps({
            'source_date': '2026-02-01',
            'target_date': '2026-02-15',
            'mode': 'replace',
        }), content_type='application/json')
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['replaced_count'], 1)
        self.assertEqual(data['copied_count'], 2)

        # Only the copied entries should be active
        active = FoodEntry.objects.filter(
            user=self.user, logged_date=date(2026, 2, 15), status='active'
        ).count()
        self.assertEqual(active, 2)

    def test_copy_same_day_rejected(self):
        url = reverse('health:copy_day_api')
        resp = self.client.post(url, json.dumps({
            'source_date': '2026-02-01',
            'target_date': '2026-02-01',
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 400)


class MealTemplateTest(CoreTestMixin, TestCase):
    """Tests for meal template creation and application."""

    def setUp(self):
        self.user = self.create_user()
        self.client.force_login(self.user)
        self.entries = []
        for i in range(2):
            entry = FoodEntry.objects.create(
                user=self.user,
                food_name=f'Template Item {i}',
                quantity=1,
                serving_size=1,
                serving_unit='serving',
                total_calories=150 * (i + 1),
                logged_date=date(2026, 2, 1),
                meal_type='lunch',
                snapshot_nutrients={
                    'calories': 150 * (i + 1),
                    'protein_g': 10 * (i + 1),
                },
            )
            self.entries.append(entry)

    def test_create_template_from_entries(self):
        url = reverse('health:meal_template_create')
        resp = self.client.post(url, json.dumps({
            'name': 'My Lunch',
            'source': 'entries',
            'entry_ids': [e.pk for e in self.entries],
            'default_meal_type': 'lunch',
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['item_count'], 2)

        template = MealTemplate.objects.get(pk=data['template_id'])
        self.assertEqual(template.name, 'My Lunch')
        self.assertEqual(template.items.count(), 2)

    def test_apply_template_creates_entries(self):
        # Create a template first
        template = MealTemplate.objects.create(
            user=self.user, name='Test Template', default_meal_type='dinner',
        )
        for i, entry in enumerate(self.entries):
            MealTemplateItem.objects.create(
                template=template,
                food_name=entry.food_name,
                quantity=entry.quantity,
                serving_size=entry.serving_size,
                serving_unit=entry.serving_unit,
                snapshot_nutrients=entry.snapshot_nutrients,
                sort_order=i,
            )

        url = reverse('health:meal_template_apply_api', args=[template.pk])
        resp = self.client.post(url, json.dumps({
            'target_date': '2026-02-20',
            'target_meal': 'dinner',
        }), content_type='application/json')
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['created_count'], 2)

        # Verify entries created with correct nutrients
        entries = FoodEntry.objects.filter(
            user=self.user, logged_date=date(2026, 2, 20), meal_type='dinner'
        ).order_by('created_at')
        self.assertEqual(entries.count(), 2)

        # Check first entry has correct totals
        first = entries.first()
        self.assertEqual(float(first.total_calories), 150.0)
        self.assertEqual(first.applied_template_id, template.pk)

        # Audit trail
        audits = NutritionEntryAudit.objects.filter(change_type='template_apply')
        self.assertEqual(audits.count(), 2)

        # Use count incremented
        template.refresh_from_db()
        self.assertEqual(template.use_count, 1)

    def test_delete_template(self):
        template = MealTemplate.objects.create(
            user=self.user, name='To Delete', default_meal_type='snack',
        )
        url = reverse('health:meal_template_delete', args=[template.pk])
        resp = self.client.post(url, content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        template.refresh_from_db()
        self.assertEqual(template.status, 'deleted')


    def test_save_meal_as_template(self):
        """Test saving a meal's entries as a new template via API."""
        url = reverse('health:save_meal_template_api')
        resp = self.client.post(url, json.dumps({
            'name': 'Italian Lunch',
            'source_date': '2026-02-01',
            'source_meal': 'lunch',
        }), content_type='application/json')
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['name'], 'Italian Lunch')
        self.assertEqual(data['item_count'], 2)

        template = MealTemplate.objects.get(pk=data['template_id'])
        self.assertEqual(template.default_meal_type, 'lunch')
        self.assertEqual(template.items.count(), 2)

    def test_save_meal_as_template_empty(self):
        """No entries for the given meal returns error."""
        url = reverse('health:save_meal_template_api')
        resp = self.client.post(url, json.dumps({
            'name': 'Empty Meal',
            'source_date': '2026-02-01',
            'source_meal': 'breakfast',
        }), content_type='application/json')
        data = resp.json()
        self.assertIn('error', data)

    def test_save_meal_as_template_no_name(self):
        """Missing name returns error."""
        url = reverse('health:save_meal_template_api')
        resp = self.client.post(url, json.dumps({
            'name': '',
            'source_date': '2026-02-01',
            'source_meal': 'lunch',
        }), content_type='application/json')
        data = resp.json()
        self.assertIn('error', data)


class FoodItemOverrideTest(CoreTestMixin, TestCase):
    """Tests for user nutrient overrides."""

    def setUp(self):
        self.user = self.create_user()
        self.food_item = FoodItem.objects.create(
            name='Mrs Butterworths Sugar Free',
            brand='Mrs Butterworths',
            serving_size=60, serving_unit='ml',
            calories=3, protein_g=0, carbohydrates_g=Decimal('1.2'),
            fat_g=0, fiber_g=0, sugar_g=0, saturated_fat_g=0,
            data_source=FoodItem.SOURCE_FATSECRET,
        )

    def test_override_created(self):
        override = FoodItemOverride.objects.create(
            user=self.user,
            food_item=self.food_item,
            overridden_nutrients={
                'calories': 10, 'carbohydrates_g': 4,
                'protein_g': 0, 'fat_g': 0,
            },
            override_reason='Label says 10 cal, not 3',
        )
        self.assertEqual(override.overridden_nutrients['calories'], 10)

    def test_build_snapshot_with_override(self):
        FoodItemOverride.objects.create(
            user=self.user,
            food_item=self.food_item,
            overridden_nutrients={
                'calories': 10, 'carbohydrates_g': 4,
                'protein_g': 0, 'fat_g': 0,
            },
        )
        snapshot = build_snapshot(self.food_item, user=self.user)
        self.assertEqual(snapshot['calories'], 10)
        self.assertEqual(snapshot['carbohydrates_g'], 4)

    def test_build_snapshot_without_override(self):
        """Without override, returns FoodItem's own values."""
        snapshot = build_snapshot(self.food_item)
        self.assertEqual(snapshot['calories'], 3.0)

    def test_unique_per_user_per_food_item(self):
        FoodItemOverride.objects.create(
            user=self.user,
            food_item=self.food_item,
            overridden_nutrients={'calories': 10},
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            FoodItemOverride.objects.create(
                user=self.user,
                food_item=self.food_item,
                overridden_nutrients={'calories': 15},
            )


class AuditTrailTest(CoreTestMixin, TestCase):
    """Tests for NutritionEntryAudit records."""

    def setUp(self):
        self.user = self.create_user()
        self.entry = FoodEntry.objects.create(
            user=self.user,
            food_name='Test',
            quantity=1,
            serving_size=1,
            serving_unit='serving',
            total_calories=100,
            logged_date=date.today(),
            snapshot_nutrients={'calories': 100},
        )

    def test_audit_created(self):
        audit = NutritionEntryAudit.objects.create(
            entry=self.entry,
            changed_by=self.user,
            change_type=NutritionEntryAudit.CHANGE_CREATE,
            after_data={'calories': 100},
        )
        self.assertEqual(audit.entry, self.entry)
        self.assertEqual(audit.change_type, 'create')

    def test_audit_change_types(self):
        """All defined change types are valid."""
        for change_type, _ in NutritionEntryAudit.CHANGE_TYPE_CHOICES:
            audit = NutritionEntryAudit.objects.create(
                entry=self.entry,
                changed_by=self.user,
                change_type=change_type,
            )
            self.assertIsNotNone(audit.pk)
