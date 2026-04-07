"""
Tests for CDCE — Cross-Domain Correlation Engine.

Project: Whole Life Journey
Path: apps/core/ai_cross_domain/tests.py
"""

import datetime
from unittest.mock import MagicMock, patch

from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.users.models import User


class DomainCorrelationModelTests(TestCase):
    """Tests for the DomainCorrelation model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="cdce@test.com", password="testpass123",
        )

    def test_create_domain_correlation(self):
        from apps.core.ai_cross_domain.models import DomainCorrelation

        corr = DomainCorrelation.objects.create(
            user=self.user,
            domain_a="health",
            domain_b="journal",
            correlation_type="sleep_mood",
            strength="strong",
            strength_score=0.78,
            direction="inverse",
            narrative="When sleep drops below 6.5h, mood is negative 78% of the time.",
            evidence_summary="14 of 18 low-sleep days had negative mood.",
            evidence={"low_sleep_days": 18, "negative_mood_days": 14},
            data_points=30,
            dedupe_key="test_key_123",
            status="active",
        )
        str_repr = str(corr)
        self.assertIn("[strong]", str_repr)
        self.assertIn("sleep_mood", str_repr)
        self.assertIn("When sleep drops", str_repr)
        self.assertEqual(corr.strength_score, 0.78)
        self.assertEqual(corr.direction, "inverse")

    def test_dedupe_key_builder(self):
        from apps.core.ai_cross_domain.models import build_correlation_dedupe_key

        key1 = build_correlation_dedupe_key(1, "sleep_mood", "30d")
        key2 = build_correlation_dedupe_key(1, "sleep_mood", "30d")
        key3 = build_correlation_dedupe_key(2, "sleep_mood", "30d")
        key4 = build_correlation_dedupe_key(1, "exercise_mood", "30d")

        # Same inputs → same key
        self.assertEqual(key1, key2)
        # Different user → different key
        self.assertNotEqual(key1, key3)
        # Different type → different key
        self.assertNotEqual(key1, key4)
        # Key is 64 chars hex
        self.assertEqual(len(key1), 64)

    def test_status_choices(self):
        from apps.core.ai_cross_domain.models import DomainCorrelation

        corr = DomainCorrelation.objects.create(
            user=self.user,
            domain_a="health",
            domain_b="health",
            correlation_type="fasting_fitness",
            strength="moderate",
            strength_score=0.55,
            narrative="Test",
            evidence_summary="Test",
            dedupe_key="test_status",
        )
        self.assertEqual(corr.status, "active")

        corr.status = "superseded"
        corr.save()
        corr.refresh_from_db()
        self.assertEqual(corr.status, "superseded")


class CDCEEngineTests(TestCase):
    """Tests for the CDCE engine core."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="cdce-engine@test.com", password="testpass123",
        )

    def test_classify_strength(self):
        from apps.core.ai_cross_domain.cdce_engine import _classify_strength

        self.assertEqual(_classify_strength(0.85), "strong")
        self.assertEqual(_classify_strength(0.70), "strong")
        self.assertEqual(_classify_strength(0.60), "moderate")
        self.assertEqual(_classify_strength(0.50), "moderate")
        self.assertEqual(_classify_strength(0.40), "weak")
        self.assertEqual(_classify_strength(0.30), "weak")
        self.assertIsNone(_classify_strength(0.29))
        self.assertIsNone(_classify_strength(0.0))

    def test_mood_score_map(self):
        from apps.core.ai_cross_domain.cdce_engine import _get_mood_score_map

        mood_map = _get_mood_score_map()
        self.assertEqual(mood_map['great'], 5)
        self.assertEqual(mood_map['good'], 4)
        self.assertEqual(mood_map['okay'], 3)
        self.assertEqual(mood_map['bad'], 2)
        self.assertEqual(mood_map['terrible'], 1)

    @patch("apps.core.ai_cross_domain.cdce_engine._collect_domain_signals")
    def test_run_cdce_no_signals(self, mock_collect):
        """Engine returns empty when no signals available."""
        mock_collect.return_value = None

        from apps.core.ai_cross_domain.cdce_engine import run_cdce
        results = run_cdce(self.user)
        self.assertEqual(results, [])

    def test_detect_sleep_mood_insufficient_data(self):
        """Detector returns empty with insufficient data."""
        from apps.core.ai_cross_domain.cdce_engine import detect_sleep_mood

        signals = {'_sleep_mood_series': []}
        result = detect_sleep_mood(self.user, signals)
        self.assertEqual(result, [])

    def test_detect_sleep_mood_strong_correlation(self):
        """Detector finds sleep→mood correlation with synthetic data."""
        from apps.core.ai_cross_domain.cdce_engine import detect_sleep_mood

        today = timezone.now().date()
        series = []
        # 10 low-sleep days with bad mood (score 2)
        for i in range(10):
            series.append({
                'date': today - datetime.timedelta(days=i),
                'sleep_hours': 5.5,
                'mood_score': 2,
            })
        # 10 normal-sleep days with good mood (score 4)
        for i in range(10, 20):
            series.append({
                'date': today - datetime.timedelta(days=i),
                'sleep_hours': 7.5,
                'mood_score': 4,
            })

        signals = {'_sleep_mood_series': series}
        result = detect_sleep_mood(self.user, signals)

        self.assertEqual(len(result), 1)
        corr = result[0]
        self.assertEqual(corr['correlation_type'], 'sleep_mood')
        self.assertEqual(corr['strength'], 'strong')
        self.assertEqual(corr['strength_score'], 1.0)
        self.assertEqual(corr['domain_a'], 'health')
        self.assertEqual(corr['domain_b'], 'journal')
        self.assertIn('6.5h', corr['narrative'])

    def test_detect_exercise_mood(self):
        """Detector finds exercise→mood correlation."""
        from apps.core.ai_cross_domain.cdce_engine import detect_exercise_mood

        today = timezone.now().date()
        series = []
        # 8 exercise days with great mood (score 5)
        for i in range(8):
            series.append({
                'date': today - datetime.timedelta(days=i * 2),
                'exercised': True,
                'mood_score': 5,
            })
        # 8 rest days with neutral mood (score 3)
        for i in range(8):
            series.append({
                'date': today - datetime.timedelta(days=i * 2 + 1),
                'exercised': False,
                'mood_score': 3,
            })

        signals = {'_exercise_mood_series': series}
        result = detect_exercise_mood(self.user, signals)

        self.assertEqual(len(result), 1)
        corr = result[0]
        self.assertEqual(corr['correlation_type'], 'exercise_mood')
        self.assertEqual(corr['direction'], 'positive')
        self.assertGreater(corr['strength_score'], 0.3)

    def test_detect_habit_goal_both_high(self):
        """Detector finds habit-goal alignment when both are high."""
        from apps.core.ai_cross_domain.cdce_engine import detect_habit_goal_alignment

        signals = {
            'habits': {
                'active_habit_count': 5,
                'avg_completion_rate': 0.85,
            },
            'goals': {
                'active_goal_count': 3,
                'completion_rate': 0.72,
            },
        }
        result = detect_habit_goal_alignment(self.user, signals)

        self.assertEqual(len(result), 1)
        corr = result[0]
        self.assertEqual(corr['correlation_type'], 'habit_goal_alignment')
        self.assertEqual(corr['direction'], 'positive')
        self.assertIn('discipline', corr['narrative'])

    def test_detect_habit_goal_both_low(self):
        """Detector finds habit-goal co-decline."""
        from apps.core.ai_cross_domain.cdce_engine import detect_habit_goal_alignment

        signals = {
            'habits': {
                'active_habit_count': 3,
                'avg_completion_rate': 0.2,
            },
            'goals': {
                'active_goal_count': 2,
                'completion_rate': 0.1,
            },
        }
        result = detect_habit_goal_alignment(self.user, signals)

        self.assertEqual(len(result), 1)
        corr = result[0]
        self.assertIn('Rebuilding', corr['narrative'])

    def test_detect_habit_goal_no_data(self):
        """Returns empty when no habits or goals."""
        from apps.core.ai_cross_domain.cdce_engine import detect_habit_goal_alignment

        signals = {
            'habits': {'active_habit_count': 0, 'avg_completion_rate': 0},
            'goals': {'active_goal_count': 0, 'completion_rate': 0},
        }
        result = detect_habit_goal_alignment(self.user, signals)
        self.assertEqual(result, [])

    def test_detect_faith_consistency_strong(self):
        """Detector finds faith-mood correlation."""
        from apps.core.ai_cross_domain.cdce_engine import detect_faith_consistency

        signals = {
            'faith': {
                'reading_streak': 14,
                'days_since_reading': 0,
            },
            'journal': {
                'mood_distribution': {
                    'great': 10,
                    'good': 5,
                    'okay': 2,
                    'bad': 1,
                },
            },
        }
        result = detect_faith_consistency(self.user, signals)

        self.assertEqual(len(result), 1)
        corr = result[0]
        self.assertEqual(corr['correlation_type'], 'faith_mood')
        self.assertIn('faith reading streak', corr['narrative'])

    def test_detect_faith_broken(self):
        """Detector finds broken faith practice + negative mood."""
        from apps.core.ai_cross_domain.cdce_engine import detect_faith_consistency

        signals = {
            'faith': {
                'reading_streak': 0,
                'days_since_reading': 10,
            },
            'journal': {
                'mood_distribution': {
                    'bad': 8,
                    'terrible': 3,
                    'okay': 2,
                    'good': 1,
                },
            },
        }
        result = detect_faith_consistency(self.user, signals)

        self.assertEqual(len(result), 1)
        corr = result[0]
        self.assertIn('inactive', corr['narrative'])

    def test_detect_fasting_fitness_both_strong(self):
        """Detector finds fasting-fitness positive correlation."""
        from apps.core.ai_cross_domain.cdce_engine import detect_fasting_fitness

        signals = {
            'fasting': {
                'enabled': True,
                'fasting_compliance_score': 85,
                'fasts_7d': 5,
            },
            'fitness': {
                'workout_consistency_score': 90,
                'workouts_7d': 4,
            },
        }
        result = detect_fasting_fitness(self.user, signals)

        self.assertEqual(len(result), 1)
        corr = result[0]
        self.assertEqual(corr['correlation_type'], 'fasting_fitness')
        self.assertIn('reinforcing', corr['narrative'])

    def test_detect_momentum_mood(self):
        """Detector finds momentum-mood correlation."""
        from apps.core.ai_cross_domain.cdce_engine import detect_momentum_engagement

        signals = {
            'transformation': {'momentum_score': 80},
            'journal': {
                'mood_distribution': {
                    'great': 12,
                    'good': 8,
                    'okay': 3,
                },
            },
        }
        result = detect_momentum_engagement(self.user, signals)

        self.assertEqual(len(result), 1)
        corr = result[0]
        self.assertEqual(corr['correlation_type'], 'momentum_mood')


class CDCEStorageTests(TestCase):
    """Tests for correlation storage and deduplication."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="cdce-storage@test.com", password="testpass123",
        )

    def test_store_creates_new_correlation(self):
        from apps.core.ai_cross_domain.cdce_engine import _store_correlation
        from apps.core.ai_cross_domain.models import DomainCorrelation

        corr_data = {
            'domain_a': 'health',
            'domain_b': 'journal',
            'correlation_type': 'sleep_mood',
            'strength': 'strong',
            'strength_score': 0.78,
            'direction': 'inverse',
            'narrative': 'Test narrative',
            'evidence_summary': 'Test evidence',
            'evidence': {'test': True},
            'data_points': 30,
            'window_label': '30d',
        }

        obj = _store_correlation(self.user, corr_data)
        self.assertIsNotNone(obj)
        self.assertEqual(obj.correlation_type, 'sleep_mood')
        self.assertEqual(DomainCorrelation.objects.filter(user=self.user).count(), 1)

    def test_store_deduplication_no_change(self):
        """Same correlation with same strength → no update (returns None)."""
        from apps.core.ai_cross_domain.cdce_engine import _store_correlation
        from apps.core.ai_cross_domain.models import DomainCorrelation

        corr_data = {
            'domain_a': 'health',
            'domain_b': 'journal',
            'correlation_type': 'sleep_mood',
            'strength': 'strong',
            'strength_score': 0.78,
            'direction': 'inverse',
            'narrative': 'Test narrative',
            'evidence_summary': 'Test evidence',
            'evidence': {},
            'data_points': 30,
            'window_label': '30d',
        }

        obj1 = _store_correlation(self.user, corr_data)
        self.assertIsNotNone(obj1)

        # Store again with same strength — should skip
        obj2 = _store_correlation(self.user, corr_data)
        self.assertIsNone(obj2)
        self.assertEqual(DomainCorrelation.objects.filter(user=self.user).count(), 1)

    def test_store_deduplication_updates_on_change(self):
        """Same correlation with changed strength → updates."""
        from apps.core.ai_cross_domain.cdce_engine import _store_correlation
        from apps.core.ai_cross_domain.models import DomainCorrelation

        corr_data = {
            'domain_a': 'health',
            'domain_b': 'journal',
            'correlation_type': 'sleep_mood',
            'strength': 'moderate',
            'strength_score': 0.55,
            'direction': 'inverse',
            'narrative': 'Original narrative',
            'evidence_summary': 'Original evidence',
            'evidence': {},
            'data_points': 20,
            'window_label': '30d',
        }
        obj1 = _store_correlation(self.user, corr_data)
        self.assertIsNotNone(obj1)

        # Update with significantly different strength
        corr_data['strength'] = 'strong'
        corr_data['strength_score'] = 0.78
        corr_data['narrative'] = 'Updated narrative'
        corr_data['data_points'] = 30

        obj2 = _store_correlation(self.user, corr_data)
        self.assertIsNotNone(obj2)
        self.assertEqual(obj2.pk, obj1.pk)  # Same record updated
        self.assertEqual(obj2.strength_score, 0.78)
        self.assertEqual(obj2.narrative, 'Updated narrative')
        self.assertEqual(DomainCorrelation.objects.filter(user=self.user).count(), 1)

    def test_expire_stale_correlations(self):
        from apps.core.ai_cross_domain.cdce_engine import expire_stale_correlations
        from apps.core.ai_cross_domain.models import DomainCorrelation

        # Create a stale correlation
        corr = DomainCorrelation.objects.create(
            user=self.user,
            domain_a="health",
            domain_b="journal",
            correlation_type="sleep_mood",
            strength="moderate",
            strength_score=0.55,
            narrative="Old",
            evidence_summary="Old",
            dedupe_key="stale_test",
            status="active",
        )
        # Backdate updated_at
        DomainCorrelation.objects.filter(pk=corr.pk).update(
            updated_at=timezone.now() - datetime.timedelta(days=90),
        )

        expired = expire_stale_correlations(max_age_days=60)
        self.assertEqual(expired, 1)

        corr.refresh_from_db()
        self.assertEqual(corr.status, "expired")


class CDCESchedulerRunnerTests(TestCase):
    """Tests for the CDCE scheduler runner."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="cdce-sched@test.com", password="testpass123",
        )

    def test_cdce_registered_in_engine_registry(self):
        from apps.core.ai_observability.engine_registry import ENGINE_REGISTRY

        self.assertIn("CDCE", ENGINE_REGISTRY)
        meta = ENGINE_REGISTRY["CDCE"]
        self.assertEqual(meta["phase"], 2)  # Execution phase (canonical)
        self.assertEqual(meta["category"], "Execute")
        self.assertTrue(meta["can_manual_run"])
        self.assertIn("cdce_engine.run_cdce", meta["per_user_func"])

    def test_cdce_registered_in_scheduler_registry(self):
        from apps.core.ai_scheduler.scheduler_registry import SCHEDULED_TASKS

        self.assertIn("run_cdce_correlations", SCHEDULED_TASKS)
        task = SCHEDULED_TASKS["run_cdce_correlations"]
        self.assertEqual(task["interval_seconds"], 21600)  # 6 hours
        self.assertIn("run_cdce_synthetic", task["function_path"])

    @patch("apps.core.ai_cross_domain.cdce_engine.run_cdce")
    @patch("apps.core.ai_cross_domain.cdce_engine.expire_stale_correlations")
    def test_scheduler_runner_calls_cdce(self, mock_expire, mock_run):
        """Scheduler runner iterates users and calls run_cdce."""
        mock_run.return_value = []
        mock_expire.return_value = 0

        from apps.core.ai_scheduler.scheduler_runner import run_cdce_synthetic

        result = run_cdce_synthetic()
        self.assertIn("processed", result)
        self.assertIn("correlations_found", result)
        self.assertEqual(result["errors"], 0)


class CDCEContextInjectionTests(TransactionTestCase):
    """Tests for CDCE output wiring into CoS context."""

    def setUp(self):
        from django.conf import settings
        from apps.users.models import TermsAcceptance

        self.user = User.objects.create_user(
            email="cdce-ctx@test.com", password="testpass123",
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

    def test_correlation_appears_in_context(self):
        """Active correlations are included in build_cos_context."""
        from apps.core.ai_cross_domain.models import DomainCorrelation

        DomainCorrelation.objects.create(
            user=self.user,
            domain_a="health",
            domain_b="journal",
            correlation_type="sleep_mood",
            strength="strong",
            strength_score=0.78,
            narrative="When sleep drops below 6.5h, mood is negative 78% of the time.",
            evidence_summary="14 of 18 low-sleep days had negative mood.",
            dedupe_key="ctx_test",
            status="active",
        )

        from apps.core.ai_orchestrator.cos_context import build_cos_context

        context = build_cos_context(self.user)
        correlations = context.get('cross_domain_correlations', [])
        self.assertEqual(len(correlations), 1)
        self.assertEqual(correlations[0]['type'], 'sleep_mood')
        self.assertEqual(correlations[0]['strength'], 'strong')

    def test_correlation_in_system_injection(self):
        """Active correlations appear in formatted system injection."""
        from apps.core.ai_cross_domain.models import DomainCorrelation

        DomainCorrelation.objects.create(
            user=self.user,
            domain_a="health",
            domain_b="journal",
            correlation_type="sleep_mood",
            strength="strong",
            strength_score=0.78,
            narrative="When sleep drops below 6.5h, mood is negative 78% of the time.",
            evidence_summary="Test evidence",
            dedupe_key="inj_test",
            status="active",
        )

        from apps.core.ai_orchestrator.cos_context import (
            build_cos_context,
            format_cos_system_injection,
        )

        context = build_cos_context(self.user)
        injection = format_cos_system_injection(context)
        self.assertIn("CROSS-DOMAIN PATTERNS", injection)
        self.assertIn("[STRONG]", injection)
        self.assertIn("6.5h", injection)

    def test_no_correlations_no_block(self):
        """No CROSS-DOMAIN PATTERNS block when no correlations exist."""
        from apps.core.ai_orchestrator.cos_context import (
            build_cos_context,
            format_cos_system_injection,
        )

        context = build_cos_context(self.user)
        injection = format_cos_system_injection(context)
        self.assertNotIn("CROSS-DOMAIN PATTERNS (CDCE):", injection)


class FastingFitnessGatingTests(TestCase):
    """
    Regression tests for the false 'Both fasting (0%) and workout consistency
    (43%) have dropped' correlation that surfaced for users with fasting
    disabled. The detector and state builder must gate on the fasting domain
    being enabled and on signals being non-None.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="cdce_gate@test.com", password="testpass123",
        )

    def test_detect_fasting_fitness_gated_by_enabled_flag(self):
        from apps.core.ai_cross_domain.cdce_engine import detect_fasting_fitness

        signals = {
            "fasting": {
                "enabled": False,  # disabled domain — must short-circuit
                "fasting_compliance_score": 0,  # would have triggered old bug
                "fasts_7d": 0,
            },
            "fitness": {
                "workout_consistency_score": 43,
                "workouts_7d": 8,
            },
        }
        self.assertEqual(detect_fasting_fitness(self.user, signals), [])

    def test_detect_fasting_fitness_skips_when_score_is_none(self):
        from apps.core.ai_cross_domain.cdce_engine import detect_fasting_fitness

        signals = {
            "fasting": {
                "enabled": True,
                "fasting_compliance_score": None,  # unknown != 0%
                "fasts_7d": 0,
            },
            "fitness": {
                "workout_consistency_score": 43,
                "workouts_7d": 8,
            },
        }
        self.assertEqual(detect_fasting_fitness(self.user, signals), [])

    def test_detect_fasting_fitness_requires_both_domains_active(self):
        from apps.core.ai_cross_domain.cdce_engine import detect_fasting_fitness

        # Enabled and scored, but no actual fasts in window
        signals = {
            "fasting": {
                "enabled": True,
                "fasting_compliance_score": 25,
                "fasts_7d": 0,
            },
            "fitness": {
                "workout_consistency_score": 30,
                "workouts_7d": 5,
            },
        }
        self.assertEqual(detect_fasting_fitness(self.user, signals), [])

    def test_detect_fasting_fitness_emits_when_both_legitimately_low(self):
        from apps.core.ai_cross_domain.cdce_engine import detect_fasting_fitness

        signals = {
            "fasting": {
                "enabled": True,
                "fasting_compliance_score": 30,
                "fasts_7d": 2,
            },
            "fitness": {
                "workout_consistency_score": 40,
                "workouts_7d": 2,
            },
        }
        results = detect_fasting_fitness(self.user, signals)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["correlation_type"], "fasting_fitness")
        self.assertIn("have dropped", results[0]["narrative"])

    def test_build_fasting_state_returns_disabled_when_pref_none(self):
        from apps.core.ai_state.state_builder import build_fasting_state

        # Default UserPreferences has default_fasting_type='none'
        self.user.preferences.default_fasting_type = "none"
        self.user.preferences.save()

        state = build_fasting_state(self.user)
        self.assertEqual(state, {"enabled": False})
        self.assertNotIn("fasting_compliance_score", state)
        self.assertNotIn("fasts_7d", state)

    def test_build_fasting_state_returns_disabled_when_subfeature_off(self):
        from apps.core.ai_state.state_builder import build_fasting_state

        prefs = self.user.preferences
        prefs.default_fasting_type = "16:8"  # type set
        prefs.health_features = {"fasting": False}  # but sub-feature off
        prefs.save()

        state = build_fasting_state(self.user)
        self.assertEqual(state, {"enabled": False})

    def test_build_fasting_state_compliance_score_is_none_with_no_fasts(self):
        """Enabled fasting + zero fasts → compliance_score is None, NOT 0."""
        from apps.core.ai_state.state_builder import build_fasting_state

        prefs = self.user.preferences
        prefs.default_fasting_type = "16:8"
        prefs.health_features = {"fasting": True}
        prefs.save()

        state = build_fasting_state(self.user)
        self.assertTrue(state["enabled"])
        self.assertIsNone(state["fasting_compliance_score"])
        self.assertEqual(state["fasts_7d"], 0)
