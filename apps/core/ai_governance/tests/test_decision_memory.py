"""
Tests for the Decision Memory module.

Covers:
- Decision recording
- Confidence calculation and decay
- Reliability thresholds
- Context key computation
- Option reordering based on suggestions
- UserDecisionPreference model methods
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.core.ai_orchestrator.decision_memory import (
    apply_suggestion_to_options,
    compute_context_key,
    get_decision_suggestion,
    record_decision,
)


class ComputeContextKeyTests(TestCase):
    """Test context key computation for grouping similar decisions."""

    def test_delete_recurring_task(self):
        key = compute_context_key(
            'mutate_task', {'action': 'delete', 'delete_series': True}
        )
        self.assertEqual(key, 'delete_recurring')

    def test_delete_single_task(self):
        key = compute_context_key(
            'mutate_task', {'action': 'delete'}
        )
        self.assertEqual(key, 'delete')

    def test_update_task(self):
        key = compute_context_key(
            'mutate_task', {'action': 'update'}
        )
        self.assertEqual(key, 'update')

    def test_log_intents(self):
        self.assertEqual(compute_context_key('log_heart_rate', {}), 'log')
        self.assertEqual(compute_context_key('log_weight', {}), 'log')
        self.assertEqual(compute_context_key('log_medicine', {}), 'log')

    def test_create_intents(self):
        self.assertEqual(compute_context_key('create_task', {}), 'create')
        self.assertEqual(compute_context_key('create_event', {}), 'create')

    def test_default_fallback(self):
        self.assertEqual(compute_context_key('search_tasks', {}), 'default')

    def test_delete_calendar_event_recurring(self):
        key = compute_context_key(
            'mutate_calendar_event',
            {'action': 'delete', 'delete_series': True},
        )
        self.assertEqual(key, 'delete_recurring')


class RecordDecisionTests(TestCase):
    """Test that decisions are recorded correctly."""

    def setUp(self):
        from apps.users.models import User
        self.user = User.objects.create_user(
            email='decision@test.com', password='test123',
        )

    def test_record_first_decision(self):
        record_decision(self.user, 'log_heart_rate', 'log', 'confirm')

        from apps.core.ai_governance.models import UserDecisionPreference
        pref = UserDecisionPreference.objects.get(
            user=self.user,
            intent_type='log_heart_rate',
            context_key='log',
        )
        self.assertEqual(pref.sample_size, 1)
        self.assertEqual(pref.confirm_count, 1)
        self.assertEqual(pref.preferred_action, 'confirm')

    def test_record_multiple_decisions(self):
        for _ in range(3):
            record_decision(self.user, 'log_heart_rate', 'log', 'confirm')
        record_decision(self.user, 'log_heart_rate', 'log', 'cancel')

        from apps.core.ai_governance.models import UserDecisionPreference
        pref = UserDecisionPreference.objects.get(
            user=self.user,
            intent_type='log_heart_rate',
            context_key='log',
        )
        self.assertEqual(pref.sample_size, 4)
        self.assertEqual(pref.confirm_count, 3)
        self.assertEqual(pref.cancel_count, 1)
        self.assertEqual(pref.preferred_action, 'confirm')
        self.assertAlmostEqual(pref.confidence, 0.75, places=2)


class GetDecisionSuggestionTests(TestCase):
    """Test suggestion retrieval with thresholds."""

    def setUp(self):
        from apps.users.models import User
        self.user = User.objects.create_user(
            email='suggest@test.com', password='test123',
        )

    def test_no_history_returns_none(self):
        result = get_decision_suggestion(
            self.user, 'log_heart_rate', 'log'
        )
        self.assertIsNone(result)

    def test_insufficient_sample_returns_none(self):
        """Sample size < 5 should return no suggestion."""
        for _ in range(4):
            record_decision(self.user, 'log_heart_rate', 'log', 'confirm')

        result = get_decision_suggestion(
            self.user, 'log_heart_rate', 'log'
        )
        self.assertIsNone(result)

    def test_sufficient_sample_with_high_confidence(self):
        """5+ samples with >= 70% agreement should return suggestion."""
        for _ in range(5):
            record_decision(self.user, 'log_heart_rate', 'log', 'confirm')

        result = get_decision_suggestion(
            self.user, 'log_heart_rate', 'log'
        )
        self.assertIsNotNone(result)
        self.assertEqual(result['suggested_action'], 'confirm')
        self.assertGreaterEqual(result['confidence'], 0.70)
        self.assertEqual(result['sample_size'], 5)

    def test_low_confidence_returns_none(self):
        """Mixed decisions should not yield a suggestion."""
        # 3 confirms + 3 cancels = 50% confidence → below threshold
        for _ in range(3):
            record_decision(self.user, 'mutate_task', 'update', 'confirm')
        for _ in range(3):
            record_decision(self.user, 'mutate_task', 'update', 'cancel')

        result = get_decision_suggestion(
            self.user, 'mutate_task', 'update'
        )
        self.assertIsNone(result)


class DecisionPreferenceDecayTests(TestCase):
    """Test confidence decay over time."""

    def setUp(self):
        from apps.users.models import User
        self.user = User.objects.create_user(
            email='decay@test.com', password='test123',
        )

    def test_decay_reduces_effective_confidence(self):
        """After many days without interaction, confidence should decay."""
        from apps.core.ai_governance.models import UserDecisionPreference

        for _ in range(10):
            record_decision(self.user, 'log_weight', 'log', 'confirm')

        pref = UserDecisionPreference.objects.get(
            user=self.user,
            intent_type='log_weight',
            context_key='log',
        )
        # Use .update() to bypass auto_now=True on last_seen_at
        old_date = timezone.now() - timedelta(days=30)
        UserDecisionPreference.objects.filter(pk=pref.pk).update(
            last_seen_at=old_date,
        )
        pref.refresh_from_db()

        effective = pref.get_effective_confidence()
        # 30 * 0.02 = 0.60 decay → confidence 1.0 - 0.60 = 0.40
        self.assertLess(effective, 0.70)

    def test_recent_interaction_no_decay(self):
        from apps.core.ai_governance.models import UserDecisionPreference

        for _ in range(5):
            record_decision(self.user, 'log_weight', 'log', 'confirm')

        pref = UserDecisionPreference.objects.get(
            user=self.user,
            intent_type='log_weight',
            context_key='log',
        )
        # last_seen_at is 'now' (auto_now=True) — no decay
        effective = pref.get_effective_confidence()
        self.assertAlmostEqual(effective, pref.confidence, places=2)


class ApplySuggestionToOptionsTests(TestCase):
    """Test option reordering based on decision suggestions."""

    def test_no_suggestion_returns_original(self):
        options = [
            {'key': 'A', 'label': 'Confirm', 'action': 'confirm'},
            {'key': 'B', 'label': 'Cancel', 'action': 'cancel'},
        ]
        result = apply_suggestion_to_options(options, None)
        self.assertEqual(result, options)

    def test_suggestion_reorders_options(self):
        options = [
            {'key': 'A', 'label': 'Confirm', 'action': 'confirm'},
            {'key': 'B', 'label': 'Cancel', 'action': 'cancel'},
            {'key': 'C', 'label': 'Edit', 'action': 'edit'},
        ]
        suggestion = {
            'suggested_action': 'cancel',
            'confidence': 0.80,
            'sample_size': 8,
        }
        result = apply_suggestion_to_options(options, suggestion)
        self.assertEqual(result[0]['action'], 'cancel')
        self.assertTrue(result[0]['is_suggested'])
        self.assertEqual(result[0]['key'], 'A')
        self.assertEqual(result[1]['key'], 'B')
        self.assertEqual(result[2]['key'], 'C')

    def test_already_first_stays_first(self):
        options = [
            {'key': 'A', 'label': 'Confirm', 'action': 'confirm'},
            {'key': 'B', 'label': 'Cancel', 'action': 'cancel'},
        ]
        suggestion = {
            'suggested_action': 'confirm',
            'confidence': 0.85,
            'sample_size': 10,
        }
        result = apply_suggestion_to_options(options, suggestion)
        self.assertEqual(result[0]['action'], 'confirm')
        self.assertTrue(result[0]['is_suggested'])

    def test_empty_options_returns_empty(self):
        result = apply_suggestion_to_options([], {'suggested_action': 'confirm'})
        self.assertEqual(result, [])

    def test_unknown_suggestion_returns_original(self):
        options = [
            {'key': 'A', 'label': 'Confirm', 'action': 'confirm'},
        ]
        suggestion = {
            'suggested_action': 'nonexistent',
            'confidence': 0.90,
            'sample_size': 15,
        }
        result = apply_suggestion_to_options(options, suggestion)
        self.assertEqual(result, options)
