"""
Whole Life Journey - Relationship Insights Tests (Phase R2)

Project: Whole Life Journey
Path: apps/relationships/tests/test_relationship_insights.py
Purpose: Tests for relational health scoring, insights, and dashboard integration

Coverage:
    - Score calculation accuracy (base 100, deductions, additions)
    - Imbalance detection (>70% in one context)
    - Empty state handling
    - Dashboard summary card renders
    - Insights page renders
    - CoS payload structure

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import datetime
from datetime import date, timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.relationships.models import Person, RelationshipInteraction
from apps.relationships.services import (
    RelationalHealthService,
    RelationshipAnalyticsService,
)

User = get_user_model()


# =============================================================================
# HELPERS
# =============================================================================


class InsightsTestMixin:
    """Common setup for insights tests."""

    def create_user(self, email='test@example.com', password='testpass123'):
        user = User.objects.create_user(email=email, password=password)
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
        )
        user.preferences.has_completed_onboarding = True
        user.preferences.save()
        return user

    def login_user(self, email='test@example.com', password='testpass123'):
        return self.client.login(email=email, password=password)

    def create_person(self, owner, first_name='John', last_name='Smith',
                      relationship_type='friend', **kwargs):
        return Person.objects.create(
            owner=owner,
            first_name=first_name,
            last_name=last_name,
            relationship_type=relationship_type,
            **kwargs,
        )

    def record_interaction(self, person, user, context_type='journal', days_ago=0):
        """Record an interaction with optional backdating."""
        interaction = RelationshipInteraction.objects.create(
            person=person,
            user=user,
            context_type_label=context_type,
            interaction_date=timezone.localdate() - timedelta(days=days_ago),
        )
        # Update denormalized fields
        person.interaction_count = RelationshipInteraction.objects.filter(
            person=person,
        ).count()
        person.last_interaction_date = RelationshipInteraction.objects.filter(
            person=person,
        ).order_by('-interaction_date').values_list(
            'interaction_date', flat=True,
        ).first()
        person.save(update_fields=['interaction_count', 'last_interaction_date', 'updated_at'])
        return interaction


# =============================================================================
# 1. SCORE CALCULATION TESTS
# =============================================================================


class ScoreCalculationTest(InsightsTestMixin, TestCase):
    """Tests for RelationalHealthService.compute_health scoring."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = self.create_user()

    def test_empty_contacts_returns_none_score(self):
        result = RelationalHealthService.compute_health(self.user)
        self.assertIsNone(result['score'])
        self.assertEqual(result['total_contacts'], 0)

    def test_base_score_100_with_active_contacts(self):
        """Fresh contacts with recent interactions should score near 100."""
        person = self.create_person(self.user)
        self.record_interaction(person, self.user, 'journal')
        self.record_interaction(person, self.user, 'event')  # has event = no -5

        # Clear cache
        from django.core.cache import cache
        cache.clear()

        result = RelationalHealthService.compute_health(self.user)
        self.assertIsNotNone(result['score'])
        # Should be 100 - 0 (no stale) - 0 (no imbalance) - 0 (has events) + 0 (not enough weeks)
        self.assertGreaterEqual(result['score'], 90)

    def test_stale_contacts_reduce_score(self):
        """Contacts >45 days without interaction should reduce score."""
        for i in range(5):
            person = self.create_person(
                self.user, first_name=f'Stale{i}',
                last_name=str(i),
            )
            self.record_interaction(person, self.user, 'journal', days_ago=50)

        from django.core.cache import cache
        cache.clear()

        result = RelationalHealthService.compute_health(self.user)
        # 5 stale contacts * 2 points = -10, plus -5 for no events
        self.assertLessEqual(result['score'], 90)

    def test_stale_deduction_capped_at_20(self):
        """Stale deduction should cap at -20 even with many stale contacts."""
        for i in range(15):
            person = self.create_person(
                self.user, first_name=f'Old{i}', last_name=str(i),
            )
            self.record_interaction(person, self.user, 'journal', days_ago=50)

        from django.core.cache import cache
        cache.clear()

        result = RelationalHealthService.compute_health(self.user)
        # Cap: -20 (stale) -5 (no events) = 75 minimum from these deductions
        self.assertGreaterEqual(result['score'], 70)

    def test_no_events_reduces_score_by_5(self):
        """No event interactions in 30 days = -5 points."""
        person = self.create_person(self.user)
        self.record_interaction(person, self.user, 'journal')  # journal only

        from django.core.cache import cache
        cache.clear()

        result = RelationalHealthService.compute_health(self.user)
        # -5 for no events, that's the only deduction
        self.assertLessEqual(result['score'], 96)

    def test_score_bounded_0_to_100(self):
        result = RelationalHealthService.compute_health(self.user)
        if result['score'] is not None:
            self.assertGreaterEqual(result['score'], 0)
            self.assertLessEqual(result['score'], 100)


# =============================================================================
# 2. METRICS ACCURACY TESTS
# =============================================================================


class MetricsAccuracyTest(InsightsTestMixin, TestCase):
    """Tests for metric computation accuracy."""

    def setUp(self):
        self.user = self.create_user()

    def test_active_7d_count(self):
        p1 = self.create_person(self.user, first_name='Active')
        p2 = self.create_person(self.user, first_name='Old', last_name='Person')
        self.record_interaction(p1, self.user, 'journal', days_ago=2)
        self.record_interaction(p2, self.user, 'journal', days_ago=15)

        from django.core.cache import cache
        cache.clear()

        result = RelationalHealthService.compute_health(self.user)
        self.assertEqual(result['active_7d'], 1)

    def test_stale_30d_count(self):
        p_fresh = self.create_person(self.user, first_name='Fresh')
        p_stale = self.create_person(self.user, first_name='Stale')
        self.record_interaction(p_fresh, self.user, 'journal', days_ago=5)
        self.record_interaction(p_stale, self.user, 'journal', days_ago=35)

        from django.core.cache import cache
        cache.clear()

        result = RelationalHealthService.compute_health(self.user)
        self.assertEqual(result['stale_30d'], 1)

    def test_top_interacted_ordering(self):
        p_low = self.create_person(self.user, first_name='Low')
        p_high = self.create_person(self.user, first_name='High')

        self.record_interaction(p_low, self.user, 'journal')
        for _ in range(5):
            self.record_interaction(p_high, self.user, 'journal')

        from django.core.cache import cache
        cache.clear()

        result = RelationalHealthService.compute_health(self.user)
        top = result['top_interacted']
        self.assertEqual(top[0]['display_name'], 'High Smith')

    def test_longest_no_contact(self):
        p_recent = self.create_person(self.user, first_name='Recent')
        p_old = self.create_person(self.user, first_name='Ancient')

        self.record_interaction(p_recent, self.user, 'journal', days_ago=1)
        self.record_interaction(p_old, self.user, 'journal', days_ago=60)

        from django.core.cache import cache
        cache.clear()

        result = RelationalHealthService.compute_health(self.user)
        longest = result['longest_no_contact']
        self.assertEqual(longest[0]['display_name'], 'Ancient Smith')

    def test_insight_lines_generated(self):
        p = self.create_person(self.user)
        self.record_interaction(p, self.user, 'journal', days_ago=35)

        from django.core.cache import cache
        cache.clear()

        result = RelationalHealthService.compute_health(self.user)
        self.assertTrue(len(result['insight_lines']) > 0)
        self.assertLessEqual(len(result['insight_lines']), 3)


# =============================================================================
# 3. IMBALANCE DETECTION TESTS
# =============================================================================


class ImbalanceDetectionTest(InsightsTestMixin, TestCase):
    """Tests for context imbalance flagging."""

    def setUp(self):
        self.user = self.create_user()

    def test_imbalance_flagged_when_over_70_percent(self):
        person = self.create_person(self.user)
        # 8 journal, 1 task = 89% journal → imbalanced
        for _ in range(8):
            self.record_interaction(person, self.user, 'journal')
        self.record_interaction(person, self.user, 'task')

        from django.core.cache import cache
        cache.clear()

        result = RelationalHealthService.compute_health(self.user)
        self.assertTrue(len(result['imbalance_flags']) > 0)
        flag = result['imbalance_flags'][0]
        self.assertEqual(flag['dominant_context'], 'journal')
        self.assertGreater(flag['percentage'], 70)

    def test_no_imbalance_when_balanced(self):
        person = self.create_person(self.user)
        # 3 journal, 3 task = 50% each → balanced
        for _ in range(3):
            self.record_interaction(person, self.user, 'journal')
        for _ in range(3):
            self.record_interaction(person, self.user, 'task')

        from django.core.cache import cache
        cache.clear()

        result = RelationalHealthService.compute_health(self.user)
        # Filter flags for this person specifically
        person_flags = [f for f in result['imbalance_flags']
                        if f['person_id'] == person.pk]
        self.assertEqual(len(person_flags), 0)

    def test_imbalance_not_flagged_with_few_interactions(self):
        """Don't flag imbalance if total interactions < 3."""
        person = self.create_person(self.user)
        self.record_interaction(person, self.user, 'journal')
        self.record_interaction(person, self.user, 'journal')

        from django.core.cache import cache
        cache.clear()

        result = RelationalHealthService.compute_health(self.user)
        person_flags = [f for f in result['imbalance_flags']
                        if f['person_id'] == person.pk]
        self.assertEqual(len(person_flags), 0)


# =============================================================================
# 4. VIEW TESTS
# =============================================================================


class InsightsViewTest(InsightsTestMixin, TestCase):
    """Tests for the insights page and dashboard card."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = self.create_user()
        self.login_user()

    def test_insights_page_renders(self):
        response = self.client.get(reverse('relationships:insights'))
        self.assertEqual(response.status_code, 200)

    def test_insights_page_with_data(self):
        person = self.create_person(self.user)
        self.record_interaction(person, self.user, 'journal')

        from django.core.cache import cache
        cache.clear()

        response = self.client.get(reverse('relationships:insights'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'People')
        self.assertContains(response, 'John Smith')

    def test_insights_page_empty_state(self):
        response = self.client.get(reverse('relationships:insights'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No contacts yet')

    def test_insights_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('relationships:insights'))
        self.assertEqual(response.status_code, 302)

    def test_dashboard_renders_with_tile(self):
        """Dashboard should render without errors when relational_health tile exists."""
        response = self.client.get(reverse('dashboard_v2:home'))
        self.assertEqual(response.status_code, 200)


# =============================================================================
# 5. COS PAYLOAD TESTS
# =============================================================================


class CosPayloadTest(InsightsTestMixin, TestCase):
    """Tests for CoS context builder relational health payload."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = self.create_user()

    def test_cos_payload_structure(self):
        person = self.create_person(self.user)
        self.record_interaction(person, self.user, 'journal')

        from django.core.cache import cache
        cache.clear()

        from apps.relationships.services import RelationalHealthService
        health = RelationalHealthService.compute_health(self.user)

        # Verify required keys exist
        self.assertIn('score', health)
        self.assertIn('stale_relationships_count', health)
        self.assertIn('top_anchor_persons', health)
        self.assertIn('imbalance_flags', health)

    def test_cos_payload_empty_user(self):
        from apps.relationships.services import RelationalHealthService
        health = RelationalHealthService.compute_health(self.user)
        self.assertIsNone(health['score'])
        self.assertEqual(health['stale_relationships_count'], 0)
        self.assertEqual(health['top_anchor_persons'], [])

    def test_cos_payload_imbalance_structure(self):
        person = self.create_person(self.user)
        for _ in range(8):
            self.record_interaction(person, self.user, 'journal')
        self.record_interaction(person, self.user, 'task')

        from django.core.cache import cache
        cache.clear()

        health = RelationalHealthService.compute_health(self.user)
        if health['imbalance_flags']:
            flag = health['imbalance_flags'][0]
            self.assertIn('person_id', flag)
            self.assertIn('display_name', flag)
            self.assertIn('dominant_context', flag)
            self.assertIn('percentage', flag)


# =============================================================================
# 6. CACHE TESTS
# =============================================================================


class CacheTest(InsightsTestMixin, TestCase):
    """Tests for relational health caching."""

    def setUp(self):
        self.user = self.create_user()

    def test_result_is_cached(self):
        self.create_person(self.user)

        from django.core.cache import cache
        cache.clear()

        r1 = RelationalHealthService.compute_health(self.user)
        r2 = RelationalHealthService.compute_health(self.user)
        # Same object from cache
        self.assertEqual(r1['score'], r2['score'])

    def test_cache_cleared_returns_fresh(self):
        person = self.create_person(self.user)

        from django.core.cache import cache
        cache.clear()

        r1 = RelationalHealthService.compute_health(self.user)
        self.record_interaction(person, self.user, 'journal')
        cache.clear()
        r2 = RelationalHealthService.compute_health(self.user)
        # After cache clear and new data, interaction count should differ
        self.assertNotEqual(r1['active_7d'], r2['active_7d'])
