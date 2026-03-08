# ==============================================================================
# File: test_situational_awareness.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for v8 Situational Awareness Summary
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-07
# ==============================================================================
"""
Situational Awareness Tests (v8)

Tests cover:
1. Pattern classification logic (consistent / mixed / slipping)
2. Accountability gate (proven priority required for drift)
3. One-off sensitive domain detection
4. Fatigue/distress keyword scanning (user messages only)
5. Mood trend as weak signal
6. Medication adherence conditional inclusion
7. Formatter output correctness
8. Integration with CoS context pipeline
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.ai.situational_awareness import (
    build_situational_awareness,
    format_situational_awareness_injection,
    _classify_consistency,
)

User = get_user_model()


class SATestMixin:
    """Common setup for situational awareness tests."""

    def create_user(self, email='sa@example.com', password='testpass123'):
        user = User.objects.create_user(email=email, password=password)
        from django.conf import settings
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
        )
        user.preferences.has_completed_onboarding = True
        user.preferences.save()
        return user

    def enable_ai(self, user):
        user.preferences.ai_enabled = True
        user.preferences.ai_data_consent = True
        user.preferences.ai_data_consent_date = timezone.now()
        user.preferences.personal_assistant_enabled = True
        user.preferences.personal_assistant_consent = True
        user.preferences.personal_assistant_consent_date = timezone.now()
        user.preferences.save()


class TestClassifyConsistency(TestCase):
    """Test the pattern classification thresholds."""

    def test_consistent(self):
        self.assertEqual(_classify_consistency(5), 'consistent')
        self.assertEqual(_classify_consistency(6), 'consistent')
        self.assertEqual(_classify_consistency(7), 'consistent')

    def test_mixed(self):
        self.assertEqual(_classify_consistency(3), 'mixed')
        self.assertEqual(_classify_consistency(4), 'mixed')

    def test_slipping(self):
        self.assertEqual(_classify_consistency(0), 'slipping')
        self.assertEqual(_classify_consistency(1), 'slipping')
        self.assertEqual(_classify_consistency(2), 'slipping')


class TestSituationalAwarenessBuilder(SATestMixin, TestCase):
    """Test build_situational_awareness() with various data scenarios."""

    def setUp(self):
        self.user = self.create_user()
        self.enable_ai(self.user)

    def test_empty_user_no_data(self):
        """New user with no data returns empty/minimal SA."""
        result = build_situational_awareness(self.user)
        self.assertIsInstance(result, dict)
        self.assertIn('lines', result)
        self.assertIn('momentum_signals', result)
        self.assertIn('drift_signals', result)
        self.assertIn('one_off_sensitive_domains', result)
        self.assertIn('emotional_context', result)
        self.assertEqual(result['emotional_context'], 'none')

    def test_workout_consistency_high(self):
        """5+ workouts in 7 days → momentum + one_off_sensitive."""
        from apps.health.models import DailyHealthSummary
        today = timezone.now().date()
        for i in range(1, 7):
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=today - timedelta(days=i),
                workout_count=1,
            )

        result = build_situational_awareness(self.user)
        self.assertIn('workout', result['momentum_signals'])
        self.assertIn('workout', result['one_off_sensitive_domains'])
        # Should have at least one line about workouts
        workout_lines = [l for l in result['lines'] if 'Workout' in l]
        self.assertTrue(len(workout_lines) > 0)
        self.assertIn('consistent', workout_lines[0])

    def test_workout_consistency_low(self):
        """1 workout in 7 days → slipping classification."""
        from apps.health.models import DailyHealthSummary
        today = timezone.now().date()
        # Create 6 days of data, only 1 with workout
        for i in range(1, 7):
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=today - timedelta(days=i),
                workout_count=1 if i == 1 else 0,
            )

        result = build_situational_awareness(self.user)
        self.assertNotIn('workout', result['momentum_signals'])
        workout_lines = [l for l in result['lines'] if 'Workout' in l]
        self.assertTrue(len(workout_lines) > 0)
        self.assertIn('slipping', workout_lines[0])

    def test_workout_mixed(self):
        """3-4 workouts in 7 days → mixed, neither momentum nor drift."""
        from apps.health.models import DailyHealthSummary
        today = timezone.now().date()
        for i in range(1, 8):
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=today - timedelta(days=i),
                workout_count=1 if i <= 4 else 0,
            )

        result = build_situational_awareness(self.user)
        self.assertNotIn('workout', result['momentum_signals'])
        self.assertNotIn('workout', result['drift_signals'])
        workout_lines = [l for l in result['lines'] if 'Workout' in l]
        self.assertTrue(len(workout_lines) > 0)
        self.assertIn('mixed', workout_lines[0])

    def test_journal_gap_with_active_goal(self):
        """No journal entries with active journal goal → drift signal."""
        from apps.purpose.models import HabitGoal
        today = timezone.now().date()
        HabitGoal.objects.create(
            user=self.user,
            name="Daily Journaling",
            purpose="Self-reflection",
            start_date=today - timedelta(days=30),
            end_date=today + timedelta(days=60),
            measurement_type='binary',
            frequency_type='daily',
            status='active',
        )
        # Create a journal entry 10 days ago to establish history
        from apps.journal.models import JournalEntry
        JournalEntry.objects.create(
            user=self.user,
            title="Old entry",
            body="Test content",
            entry_date=today - timedelta(days=10),
        )

        result = build_situational_awareness(self.user)
        self.assertIn('journaling', result['drift_signals'])

    def test_journal_gap_no_goal(self):
        """No journal entries but no active goal → NOT in drift_signals."""
        from apps.journal.models import JournalEntry
        today = timezone.now().date()
        JournalEntry.objects.create(
            user=self.user,
            title="Old entry",
            body="Test content",
            entry_date=today - timedelta(days=10),
        )

        result = build_situational_awareness(self.user)
        self.assertNotIn('journaling', result['drift_signals'])

    def test_mood_insufficient_data(self):
        """Fewer than 3 mood entries → mood line skipped."""
        from apps.journal.models import JournalEntry
        today = timezone.now().date()
        # Only 2 entries with mood
        for i in range(1, 3):
            JournalEntry.objects.create(
                user=self.user,
                title=f"Entry {i}",
                body="Test",
                entry_date=today - timedelta(days=i),
                mood='good',
            )

        result = build_situational_awareness(self.user)
        mood_lines = [l for l in result['lines'] if 'Mood' in l]
        self.assertEqual(len(mood_lines), 0, "Mood should be skipped with < 3 entries")

    def test_mood_trend_weak_signal(self):
        """Mood with sufficient data is labeled as weak signal."""
        from apps.journal.models import JournalEntry
        today = timezone.now().date()
        for i in range(1, 5):
            JournalEntry.objects.create(
                user=self.user,
                title=f"Entry {i}",
                body="Test",
                entry_date=today - timedelta(days=i),
                mood='good',
            )

        result = build_situational_awareness(self.user)
        mood_lines = [l for l in result['lines'] if 'Mood' in l]
        self.assertTrue(len(mood_lines) > 0)
        self.assertIn('weak signal', mood_lines[0])

    @patch('apps.health.medicine_utils.calculate_medicine_adherence_rate')
    def test_medication_adherence_included(self, mock_adherence):
        """Active meds → medication line included."""
        mock_adherence.return_value = 85
        result = build_situational_awareness(self.user)
        med_lines = [l for l in result['lines'] if 'Medication' in l]
        self.assertTrue(len(med_lines) > 0)
        self.assertIn('85%', med_lines[0])

    @patch('apps.health.medicine_utils.calculate_medicine_adherence_rate')
    def test_medication_no_active_meds(self, mock_adherence):
        """No active meds → medication line skipped."""
        mock_adherence.return_value = None
        result = build_situational_awareness(self.user)
        med_lines = [l for l in result['lines'] if 'Medication' in l]
        self.assertEqual(len(med_lines), 0)

    def test_fatigue_keyword_detection(self):
        """User messages with fatigue keywords → emotional_context = 'fatigue'."""
        from apps.ai.models import AssistantConversation, AssistantMessage

        conv1 = AssistantConversation.objects.create(
            user=self.user, session_type='general', is_active=True,
        )
        conv2 = AssistantConversation.objects.create(
            user=self.user, session_type='general', is_active=False,
        )
        # Two user messages in different conversations with fatigue keywords
        AssistantMessage.objects.create(
            conversation=conv1, role='user',
            content="I'm really tired today, can barely focus",
        )
        AssistantMessage.objects.create(
            conversation=conv2, role='user',
            content="Feeling exhausted after this week",
        )

        result = build_situational_awareness(self.user)
        self.assertEqual(result['emotional_context'], 'fatigue')

    def test_fatigue_ignores_assistant_messages(self):
        """Assistant messages with keywords → NOT detected."""
        from apps.ai.models import AssistantConversation, AssistantMessage

        conv = AssistantConversation.objects.create(
            user=self.user, session_type='general', is_active=True,
        )
        # Only assistant messages have fatigue keywords
        AssistantMessage.objects.create(
            conversation=conv, role='assistant',
            content="You mentioned being tired yesterday. How are you feeling?",
        )
        AssistantMessage.objects.create(
            conversation=conv, role='assistant',
            content="I notice you've been exhausted lately.",
        )
        # User message is clean
        AssistantMessage.objects.create(
            conversation=conv, role='user',
            content="What's on my schedule today?",
        )

        result = build_situational_awareness(self.user)
        self.assertEqual(result['emotional_context'], 'none')

    def test_no_fatigue_clean_messages(self):
        """Clean user messages → emotional_context = 'none'."""
        from apps.ai.models import AssistantConversation, AssistantMessage

        conv = AssistantConversation.objects.create(
            user=self.user, session_type='general', is_active=True,
        )
        AssistantMessage.objects.create(
            conversation=conv, role='user',
            content="Check my schedule please",
        )
        AssistantMessage.objects.create(
            conversation=conv, role='user',
            content="What tasks do I have today?",
        )

        result = build_situational_awareness(self.user)
        self.assertEqual(result['emotional_context'], 'none')

    def test_one_off_sensitive_domains(self):
        """Consistent domains appear in one_off_sensitive_domains."""
        from apps.health.models import DailyHealthSummary, WeightEntry
        today = timezone.now().date()

        # 6 days of workouts (consistent)
        for i in range(1, 7):
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=today - timedelta(days=i),
                workout_count=1,
            )

        # 5 days of weight entries (consistent)
        for i in range(1, 6):
            WeightEntry.objects.create(
                user=self.user,
                value=Decimal('185.0'),
                recorded_at=timezone.now() - timedelta(days=i),
            )

        result = build_situational_awareness(self.user)
        self.assertIn('workout', result['one_off_sensitive_domains'])
        self.assertIn('weight_tracking', result['one_off_sensitive_domains'])


class TestSituationalAwarenessFormatter(TestCase):
    """Test format_situational_awareness_injection()."""

    def test_format_with_data(self):
        """Full SA dict produces formatted block with header/footer."""
        sa_data = {
            'lines': [
                "Workout pattern: 5 of 7 days — consistent",
                "Weight tracking: 6 of 7 days — consistent",
                "Journaling: no entries in 5 days — slipping",
            ],
            'momentum_signals': ['workout', 'weight_tracking'],
            'drift_signals': ['journaling'],
            'one_off_sensitive_domains': ['workout', 'weight_tracking'],
            'emotional_context': 'none',
        }

        output = format_situational_awareness_injection(sa_data)
        self.assertIn('=== SITUATIONAL AWARENESS SUMMARY (v8) ===', output)
        self.assertIn('=== END SITUATIONAL AWARENESS ===', output)
        self.assertIn('Workout pattern: 5 of 7 days', output)
        self.assertIn('MOMENTUM: workout, weight_tracking', output)
        self.assertIn('DRIFT: journaling', output)
        self.assertIn('ONE-OFF SENSITIVE: workout, weight_tracking', output)

    def test_format_empty(self):
        """No data dict returns empty string."""
        self.assertEqual(format_situational_awareness_injection({}), '')
        self.assertEqual(
            format_situational_awareness_injection({'lines': []}), ''
        )
        self.assertEqual(format_situational_awareness_injection(None), '')

    def test_momentum_drift_labels(self):
        """Labels section generated correctly."""
        sa_data = {
            'lines': ["Workout pattern: 6 of 7 days — consistent"],
            'momentum_signals': ['workout'],
            'drift_signals': [],
            'one_off_sensitive_domains': ['workout'],
            'emotional_context': 'none',
        }
        output = format_situational_awareness_injection(sa_data)
        self.assertIn('MOMENTUM: workout', output)
        self.assertNotIn('DRIFT:', output)

    def test_one_off_rule_in_output(self):
        """One-off guidance rule present in formatted output."""
        sa_data = {
            'lines': ["Workout pattern: 5 of 7 days — consistent"],
            'momentum_signals': ['workout'],
            'drift_signals': [],
            'one_off_sensitive_domains': ['workout'],
            'emotional_context': 'none',
        }
        output = format_situational_awareness_injection(sa_data)
        self.assertIn("not yet completed", output)
        self.assertIn("gentle nudge", output)

    def test_emotional_context_in_output(self):
        """Emotional context generates appropriate guidance."""
        sa_data = {
            'lines': ["Fatigue signal: mentioned tiredness in 3 conversations"],
            'momentum_signals': [],
            'drift_signals': [],
            'one_off_sensitive_domains': [],
            'emotional_context': 'distress',
        }
        output = format_situational_awareness_injection(sa_data)
        self.assertIn('EMOTIONAL CONTEXT: distress', output)
        self.assertIn('reduce pressure', output)

    def test_guidance_rules_always_present(self):
        """Pattern-aware guidance rules always present in non-empty output."""
        sa_data = {
            'lines': ["Workout pattern: 5 of 7 days — consistent"],
            'momentum_signals': [],
            'drift_signals': [],
            'one_off_sensitive_domains': [],
            'emotional_context': 'none',
        }
        output = format_situational_awareness_injection(sa_data)
        self.assertIn('PATTERN-AWARE GUIDANCE RULES:', output)
        # Without a priority model, rule 4 should suggest asking user
        self.assertIn('NON-NEGOTIABLES:', output)

    def test_dynamic_non_negotiables_in_output(self):
        """User-defined non-negotiables appear in formatted output."""
        sa_data = {
            'lines': ["Workout pattern: 5 of 7 days — consistent"],
            'momentum_signals': ['workout'],
            'drift_signals': [],
            'one_off_sensitive_domains': ['workout'],
            'emotional_context': 'none',
            'user_priority_model': {
                'non_negotiables': ['Morning Prayer', 'Workout', 'Bible Reading'],
                'non_negotiable_keys': {'WORKOUT', 'FAITH_BLOCK', 'MEDS_ADHERENCE'},
                'pillars_ranked': ['FAITH', 'HEALTH_DISCIPLINE', 'PURPOSE'],
                'module_commitments': {},
                'has_blueprint': True,
            },
        }
        output = format_situational_awareness_injection(sa_data)
        self.assertIn('Morning Prayer', output)
        self.assertIn('Workout', output)
        self.assertIn('Bible Reading', output)
        self.assertIn('Daily non-negotiables:', output)
        self.assertIn('Life pillars (ranked):', output)
        self.assertIn('Faith > Health Discipline > Purpose', output)

    def test_no_blueprint_shows_ask_prompt(self):
        """No blueprint → rule suggests asking what matters most."""
        sa_data = {
            'lines': ["Workout pattern: 5 of 7 days — consistent"],
            'momentum_signals': [],
            'drift_signals': [],
            'one_off_sensitive_domains': [],
            'emotional_context': 'none',
            'user_priority_model': {
                'non_negotiables': [],
                'non_negotiable_keys': set(),
                'pillars_ranked': [],
                'module_commitments': {},
                'has_blueprint': False,
            },
        }
        output = format_situational_awareness_injection(sa_data)
        self.assertIn('ask what matters most', output)


class TestDynamicPriorityModel(SATestMixin, TestCase):
    """Test that SA uses the user's actual blueprint/governance for priorities."""

    def setUp(self):
        self.user = self.create_user(email='priority@example.com')
        self.enable_ai(self.user)

    def test_drift_with_governance_non_negotiable(self):
        """Slipping domain with GovernanceProfile non_negotiable → drift signal."""
        from apps.core.ai_governance.models import GovernanceProfile
        from apps.journal.models import JournalEntry
        today = timezone.now().date()

        # Create governance profile marking journal as non-negotiable
        GovernanceProfile.objects.create(
            user=self.user,
            module_key='journal',
            display_name='Journaling',
            commitment_level='non_negotiable',
        )

        # Create old journal entry to establish history
        JournalEntry.objects.create(
            user=self.user,
            title="Old entry",
            body="Test content",
            entry_date=today - timedelta(days=10),
        )

        result = build_situational_awareness(self.user)
        self.assertIn('journaling', result['drift_signals'])

    def test_drift_with_blueprint_tier1(self):
        """Slipping domain with tier1_protected → drift signal."""
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        from apps.health.models import DailyHealthSummary
        today = timezone.now().date()

        # Create blueprint with WORKOUT as tier1
        bp = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        bp.tier1_protected_behaviors = ['WORKOUT']
        bp.save()

        # Create workout data: slipping (1 of 7 days)
        for i in range(1, 8):
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=today - timedelta(days=i),
                workout_count=1 if i == 1 else 0,
            )

        result = build_situational_awareness(self.user)
        self.assertIn('workout', result['drift_signals'])

    def test_no_drift_without_priority(self):
        """Slipping domain without any priority declaration → NOT drift."""
        from apps.health.models import DailyHealthSummary
        today = timezone.now().date()

        # Slipping workout data, no blueprint, no governance, no goal
        for i in range(1, 8):
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=today - timedelta(days=i),
                workout_count=1 if i == 1 else 0,
            )

        result = build_situational_awareness(self.user)
        self.assertNotIn('workout', result['drift_signals'])

    def test_priority_model_in_result(self):
        """user_priority_model is included in SA result."""
        from apps.core.blueprint.models import PersonalOperatingBlueprint

        bp = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        bp.tier1_protected_behaviors = ['WORKOUT', 'FAITH_BLOCK']
        bp.pillars_ranked = ['FAITH', 'HEALTH_DISCIPLINE']
        bp.save()

        result = build_situational_awareness(self.user)
        pm = result.get('user_priority_model', {})
        self.assertTrue(pm.get('has_blueprint'))
        self.assertIn('WORKOUT', pm.get('non_negotiable_keys', set()))
        self.assertIn('FAITH_BLOCK', pm.get('non_negotiable_keys', set()))
        self.assertEqual(pm['pillars_ranked'], ['FAITH', 'HEALTH_DISCIPLINE'])


class TestSituationalAwarenessIntegration(SATestMixin, TestCase):
    """Test SA integration with CoS context pipeline."""

    def setUp(self):
        self.user = self.create_user(email='sa-integration@example.com')
        self.enable_ai(self.user)

    @patch('apps.ai.situational_awareness.build_situational_awareness')
    def test_sa_in_parallel_builders(self, mock_build_sa):
        """build_cos_context() includes situational_awareness key when enabled.

        SA builder is temporarily disabled in cos_context._PARALLEL_BUILDERS
        for production stability (524 timeout investigation). This test
        verifies the builder is disabled and will need updating when re-enabled.
        """
        mock_build_sa.return_value = {
            'lines': ["Workout pattern: 5 of 7 days — consistent"],
            'momentum_signals': ['workout'],
            'drift_signals': [],
            'one_off_sensitive_domains': ['workout'],
            'emotional_context': 'none',
        }

        from apps.core.ai_orchestrator.cos_context import build_cos_context
        context = build_cos_context(self.user)
        # SA builder is currently disabled — verify it's absent
        self.assertNotIn('situational_awareness', context)
