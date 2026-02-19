"""
Phase 5 — Governance Onboarding + Adaptive Authority Tests.

Tests for:
1. GovernanceProfile model
2. GovernanceAlignmentSession model
3. ConsistencyEvaluator (DriftPressure)
4. Strategy Selector
5. Alignment Session handler
6. Recalibration Loop
7. Tomorrow Protection Pass
8. Language Rules
9. Display Filter
10. Scheduler registration
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.users.models import TermsAcceptance, User


class GovernanceProfileModelTest(TestCase):
    """Test GovernanceProfile model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="gov@test.com", password="test1234"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )

    def test_create_governance_profile(self):
        from apps.core.ai_governance.models import GovernanceProfile

        profile = GovernanceProfile.objects.create(
            user=self.user,
            module_key="faith",
            display_name="Morning Prayer",
            commitment_level="non_negotiable",
            importance_weight=2.0,
        )
        self.assertEqual(profile.module_key, "faith")
        self.assertEqual(profile.commitment_level, "non_negotiable")
        self.assertEqual(profile.importance_weight, 2.0)

    def test_unique_together_constraint(self):
        from django.db import IntegrityError
        from apps.core.ai_governance.models import GovernanceProfile

        GovernanceProfile.objects.create(
            user=self.user,
            module_key="faith",
            display_name="Prayer",
        )
        with self.assertRaises(IntegrityError):
            GovernanceProfile.objects.create(
                user=self.user,
                module_key="faith",
                display_name="Devotion",
            )

    def test_get_for_user(self):
        from apps.core.ai_governance.models import GovernanceProfile

        GovernanceProfile.objects.create(
            user=self.user, module_key="faith", display_name="Prayer",
            commitment_level="non_negotiable",
        )
        GovernanceProfile.objects.create(
            user=self.user, module_key="health.exercise", display_name="Workout",
            commitment_level="important",
        )

        profiles = GovernanceProfile.get_for_user(self.user)
        self.assertEqual(len(profiles), 2)

    def test_get_non_negotiables(self):
        from apps.core.ai_governance.models import GovernanceProfile

        GovernanceProfile.objects.create(
            user=self.user, module_key="faith", display_name="Prayer",
            commitment_level="non_negotiable",
        )
        GovernanceProfile.objects.create(
            user=self.user, module_key="journal", display_name="Journal",
            commitment_level="flexible",
        )

        nns = GovernanceProfile.get_non_negotiables(self.user)
        self.assertEqual(len(nns), 1)
        self.assertEqual(nns[0].module_key, "faith")


class GovernanceAlignmentSessionTest(TestCase):
    """Test GovernanceAlignmentSession model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="align@test.com", password="test1234"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )

    def test_create_session(self):
        from apps.core.ai_governance.models import GovernanceAlignmentSession

        session = GovernanceAlignmentSession.objects.create(
            user=self.user,
            current_stage="core_values",
        )
        self.assertFalse(session.is_complete)
        self.assertEqual(session.current_stage, "core_values")

    def test_advance_to_next_stage(self):
        from apps.core.ai_governance.models import GovernanceAlignmentSession

        session = GovernanceAlignmentSession.objects.create(
            user=self.user, current_stage="core_values",
        )
        session.advance_to_next_stage()
        self.assertEqual(session.current_stage, "success_definition")

        session.advance_to_next_stage()
        self.assertEqual(session.current_stage, "chaos_protection")

        session.advance_to_next_stage()
        self.assertEqual(session.current_stage, "top_three")

        session.advance_to_next_stage()
        self.assertEqual(session.current_stage, "module_classification")

    def test_record_response(self):
        from apps.core.ai_governance.models import GovernanceAlignmentSession

        session = GovernanceAlignmentSession.objects.create(
            user=self.user, current_stage="core_values",
        )
        session.record_response("core_values", {"response": "exercise and family"})
        self.assertIn("core_values", session.responses)
        self.assertEqual(session.responses["core_values"]["response"], "exercise and family")


class DriftPressureTest(TestCase):
    """Test ConsistencyEvaluator DriftPressure computation."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="drift@test.com", password="test1234"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )

    def test_compute_drift_pressure_no_profile(self):
        from apps.core.ai_governance.consistency_evaluator import compute_drift_pressure

        result = compute_drift_pressure(self.user, "nonexistent")
        self.assertIsNone(result)

    def test_compute_drift_pressure_with_profile(self):
        from apps.core.ai_governance.models import GovernanceProfile
        from apps.core.ai_governance.consistency_evaluator import compute_drift_pressure

        GovernanceProfile.objects.create(
            user=self.user,
            module_key="faith",
            display_name="Prayer",
            commitment_level="non_negotiable",
            importance_weight=2.0,
        )

        result = compute_drift_pressure(self.user, "faith")
        self.assertIsNotNone(result)
        self.assertEqual(result.module_key, "faith")
        self.assertGreaterEqual(result.drift_pressure, 0)
        self.assertLessEqual(result.drift_pressure, 100)

    def test_drift_pressure_clamped(self):
        """DriftPressure should always be between 0 and 100."""
        from apps.core.ai_governance.models import GovernanceProfile
        from apps.core.ai_governance.consistency_evaluator import compute_drift_pressure

        GovernanceProfile.objects.create(
            user=self.user,
            module_key="health.exercise",
            display_name="Workout",
            commitment_level="important",
            importance_weight=1.0,
        )

        result = compute_drift_pressure(self.user, "health.exercise")
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result.drift_pressure, 0)
        self.assertLessEqual(result.drift_pressure, 100)

    def test_compute_all_drift_pressures(self):
        from apps.core.ai_governance.models import GovernanceProfile
        from apps.core.ai_governance.consistency_evaluator import compute_all_drift_pressures

        GovernanceProfile.objects.create(
            user=self.user, module_key="faith", display_name="Prayer",
            commitment_level="non_negotiable", importance_weight=2.0,
        )
        GovernanceProfile.objects.create(
            user=self.user, module_key="journal", display_name="Journal",
            commitment_level="flexible", importance_weight=0.3,
        )

        results = compute_all_drift_pressures(self.user)
        self.assertEqual(len(results), 2)
        # Should be sorted by drift_pressure descending
        self.assertGreaterEqual(results[0].drift_pressure, results[1].drift_pressure)

    def test_miss_rate_no_data(self):
        """Miss rate should be 0 when no data exists."""
        from apps.core.ai_governance.consistency_evaluator import get_miss_rate
        rate = get_miss_rate(self.user, "faith", days=7)
        self.assertEqual(rate, 0.0)


class StrategySelectionTest(TestCase):
    """Test Strategy Selector."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="strategy@test.com", password="test1234"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )

    def test_select_align_strategy(self):
        from apps.core.ai_governance.consistency_evaluator import DriftPressureResult
        from apps.core.ai_governance.strategy_selector import select_strategy, STRATEGY_ALIGN

        dp = DriftPressureResult(
            module_key="faith", display_name="Prayer",
            commitment_level="important", drift_pressure=10,
            miss_rate=0.1, importance_weight=1.0,
            goal_impact=0, time_sensitivity=0,
            capacity_factor=0, responsiveness=0, strategy=None,
        )

        decision = select_strategy(self.user, dp)
        self.assertEqual(decision.strategy, STRATEGY_ALIGN)

    def test_select_challenge_strategy(self):
        from apps.core.ai_governance.consistency_evaluator import DriftPressureResult
        from apps.core.ai_governance.strategy_selector import select_strategy, STRATEGY_CHALLENGE

        dp = DriftPressureResult(
            module_key="faith", display_name="Prayer",
            commitment_level="non_negotiable", drift_pressure=55,
            miss_rate=0.7, importance_weight=2.0,
            goal_impact=10, time_sensitivity=10,
            capacity_factor=0, responsiveness=5, strategy=None,
        )

        decision = select_strategy(self.user, dp)
        self.assertEqual(decision.strategy, STRATEGY_CHALLENGE)

    def test_select_protect_strategy(self):
        from apps.core.ai_governance.consistency_evaluator import DriftPressureResult
        from apps.core.ai_governance.strategy_selector import select_strategy, STRATEGY_PROTECT

        dp = DriftPressureResult(
            module_key="journal", display_name="Journal",
            commitment_level="important", drift_pressure=45,
            miss_rate=0.4, importance_weight=1.0,
            goal_impact=5, time_sensitivity=5,
            capacity_factor=10, responsiveness=5, strategy=None,
        )

        decision = select_strategy(self.user, dp)
        self.assertEqual(decision.strategy, STRATEGY_PROTECT)

    def test_strategy_instructions(self):
        from apps.core.ai_governance.strategy_selector import (
            get_strategy_instructions,
            STRATEGY_ALIGN, STRATEGY_CHALLENGE, STRATEGY_PROTECT, STRATEGY_COMPRESS,
        )

        for strategy in [STRATEGY_ALIGN, STRATEGY_CHALLENGE, STRATEGY_PROTECT, STRATEGY_COMPRESS]:
            instructions = get_strategy_instructions(strategy)
            self.assertIn("STRATEGY:", instructions)

    def test_build_strategy_system_injection_no_profiles(self):
        from apps.core.ai_governance.strategy_selector import build_strategy_system_injection

        result = build_strategy_system_injection(self.user)
        self.assertEqual(result, "")


class AlignmentSessionTest(TestCase):
    """Test Alignment Session handler."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="session@test.com", password="test1234"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

    def test_get_first_stage(self):
        from apps.core.ai_governance.alignment_session import get_alignment_stage

        stage = get_alignment_stage(self.user)
        self.assertIsNotNone(stage)
        self.assertEqual(stage["stage_key"], "core_values")
        self.assertIn("good day", stage["question"])

    def test_record_response_advances_stage(self):
        from apps.core.ai_governance.alignment_session import (
            get_alignment_stage,
            record_alignment_response,
        )

        # Start at core_values
        stage = get_alignment_stage(self.user)
        self.assertEqual(stage["stage_key"], "core_values")

        # Record response
        result = record_alignment_response(
            self.user, "core_values", "Exercise and time with family"
        )
        self.assertIn("next_stage", result)
        self.assertEqual(result["next_stage"], "success_definition")

    def test_needs_alignment(self):
        from apps.core.ai_governance.alignment_session import needs_alignment

        # New user with no profiles should need alignment
        self.assertTrue(needs_alignment(self.user))

    def test_needs_alignment_false_with_profiles(self):
        from apps.core.ai_governance.alignment_session import needs_alignment
        from apps.core.ai_governance.models import GovernanceProfile

        GovernanceProfile.objects.create(
            user=self.user, module_key="faith", display_name="Prayer",
        )
        self.assertFalse(needs_alignment(self.user))

    def test_build_alignment_injection(self):
        from apps.core.ai_governance.alignment_session import (
            build_alignment_system_injection,
        )

        injection = build_alignment_system_injection(self.user)
        self.assertIn("GOVERNANCE ALIGNMENT", injection)
        self.assertIn("ASK THIS NATURALLY", injection)


class RecalibrationTest(TestCase):
    """Test Recalibration Loop."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="recal@test.com", password="test1234"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )

    def test_no_triggers_without_profiles(self):
        from apps.core.ai_governance.recalibration import check_recalibration_needed

        triggers = check_recalibration_needed(self.user)
        self.assertEqual(len(triggers), 0)

    def test_no_trigger_for_low_miss_rate(self):
        from apps.core.ai_governance.models import GovernanceProfile
        from apps.core.ai_governance.recalibration import check_recalibration_needed

        GovernanceProfile.objects.create(
            user=self.user, module_key="faith", display_name="Prayer",
            commitment_level="non_negotiable", importance_weight=2.0,
        )
        # Miss rate will be 0 since no data exists
        triggers = check_recalibration_needed(self.user)
        self.assertEqual(len(triggers), 0)

    def test_record_recommit(self):
        from apps.core.ai_governance.models import GovernanceProfile
        from apps.core.ai_governance.recalibration import record_recalibration_decision

        profile = GovernanceProfile.objects.create(
            user=self.user, module_key="faith", display_name="Prayer",
            commitment_level="non_negotiable", importance_weight=2.0,
        )

        record_recalibration_decision(self.user, "faith", "recommit")
        profile.refresh_from_db()
        self.assertEqual(profile.commitment_level, "non_negotiable")
        self.assertIsNotNone(profile.last_reviewed_at)

    def test_record_downgrade(self):
        from apps.core.ai_governance.models import GovernanceProfile
        from apps.core.ai_governance.recalibration import record_recalibration_decision

        profile = GovernanceProfile.objects.create(
            user=self.user, module_key="faith", display_name="Prayer",
            commitment_level="non_negotiable", importance_weight=2.0,
        )

        record_recalibration_decision(self.user, "faith", "downgrade", "important")
        profile.refresh_from_db()
        self.assertEqual(profile.commitment_level, "important")
        self.assertEqual(profile.importance_weight, 1.0)

    def test_record_drop(self):
        from apps.core.ai_governance.models import GovernanceProfile
        from apps.core.ai_governance.recalibration import record_recalibration_decision

        profile = GovernanceProfile.objects.create(
            user=self.user, module_key="faith", display_name="Prayer",
            commitment_level="non_negotiable", importance_weight=2.0,
        )

        record_recalibration_decision(self.user, "faith", "drop")
        profile.refresh_from_db()
        self.assertFalse(profile.is_active)


class LanguageRulesTest(TestCase):
    """Test Language Rules."""

    def test_banned_terms_list(self):
        from apps.core.ai_governance.language_rules import BANNED_TERMS

        self.assertIn("drift pressure", BANNED_TERMS)
        self.assertIn("governance profile", BANNED_TERMS)
        self.assertIn("noise budget", BANNED_TERMS)

    def test_build_injection(self):
        from apps.core.ai_governance.language_rules import build_language_rules_injection

        injection = build_language_rules_injection()
        self.assertIn("LANGUAGE RULES", injection)
        self.assertIn("BANNED PHRASES", injection)
        self.assertIn("drift pressure", injection)


class DisplayFilterTest(TestCase):
    """Test Governance Display Filter."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="display@test.com", password="test1234"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )

    def test_filter_empty_list(self):
        from apps.core.ai_governance.display_filter import filter_for_display

        result = filter_for_display(self.user, [])
        self.assertEqual(result, [])

    def test_filter_respects_max_display(self):
        from apps.core.ai_governance.display_filter import filter_for_display, MAX_DISPLAY_PER_DAY

        items = [
            {"id": i, "type": "insight", "severity": "info"}
            for i in range(20)
        ]
        result = filter_for_display(self.user, items)
        self.assertLessEqual(len(result), MAX_DISPLAY_PER_DAY)

    def test_priority_items_first(self):
        from apps.core.ai_governance.display_filter import filter_for_display

        items = [
            {"id": 1, "type": "insight", "severity": "info"},
            {"id": 2, "type": "insight", "is_non_negotiable_risk": True},
            {"id": 3, "type": "insight", "severity": "info"},
        ]
        result = filter_for_display(self.user, items)
        # Priority item should be first
        self.assertEqual(result[0]["id"], 2)


class SchedulerRegistrationTest(TestCase):
    """Test Phase 5 scheduler registrations."""

    def test_tomorrow_protection_pass_registered(self):
        from apps.core.ai_scheduler.scheduler_registry import SCHEDULED_TASKS

        self.assertIn("run_tomorrow_protection_pass", SCHEDULED_TASKS)
        task = SCHEDULED_TASKS["run_tomorrow_protection_pass"]
        self.assertIn("tomorrow_protection", task["function_path"])

    def test_protection_pass_runner_importable(self):
        from apps.core.ai_scheduler.scheduler_runner import run_tomorrow_protection_pass
        self.assertTrue(callable(run_tomorrow_protection_pass))


class CosContextIntegrationTest(TestCase):
    """Test Phase 5 integration into CoS context."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="cos@test.com", password="test1234"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

    def test_cos_context_includes_governance_strategy(self):
        from apps.core.ai_orchestrator.cos_context import build_cos_context

        context = build_cos_context(self.user)
        # Should have governance_strategy_prompt key
        self.assertIn("governance_strategy_prompt", context)

    def test_cos_injection_includes_language_rules(self):
        from apps.core.ai_orchestrator.cos_context import (
            build_cos_context, format_cos_system_injection,
        )

        context = build_cos_context(self.user)
        injection = format_cos_system_injection(context)
        self.assertIn("LANGUAGE RULES", injection)
