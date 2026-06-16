"""Trust Recovery Phases 1+2 — regression tests (2026-06-16).

P1A Faith single source: days-since/streak derive from the unified canonical
    completion set (plan + routine→faith bridge), so "22 days since scripture"
    cannot occur while reading daily via a routine.
P1B Wake time: actual wake answered from Tier-1 truth (performed_at / sleep),
    never the scheduled time; honest uncertainty when unverifiable.
P2  Focus gate: a domain completed today is not surfaced as a gap unless a
    grounded override is present — and then the reason MUST cite it.
"""
from datetime import time as dt_time, timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

User = get_user_model()


def _user(email):
    u = User.objects.create_user(email=email, password="x" * 20)
    from apps.users.models import TermsAcceptance
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class FaithUnifiedSource(TestCase):
    """P1A — routine-bridge Bible reading counts toward canonical history."""

    def setUp(self):
        self.user = _user("faithsrc@test.com")
        from apps.core.utils import get_user_today
        self.today = get_user_today(self.user)
        from apps.life.models import Routine, RoutineSchedule, RoutineLog
        routine = Routine.objects.create(user=self.user, name="Morning")
        sched = RoutineSchedule.objects.create(
            routine=routine, name="Bible Reading", scheduled_time=dt_time(6, 0))
        RoutineLog.objects.create(
            user=self.user, schedule=sched, scheduled_date=self.today,
            log_status=RoutineLog.STATUS_COMPLETED,
            completed_at=timezone.now(), performed_at=timezone.now())

    def test_routine_bible_reading_in_canonical_dates(self):
        from apps.faith.services.faith_queries import FaithQueries
        unified = FaithQueries.bible_completion_dates(self.user, limit=30)
        plan_only = FaithQueries.reading_completion_dates(self.user, limit=30)
        # Unified includes the routine completion; plan-only does NOT —
        # proving the two would diverge and the unified source fixes it.
        self.assertIn(self.today, unified)
        self.assertNotIn(self.today, plan_only)

    def test_days_since_reading_is_zero_today(self):
        from apps.core.ai_state.state_builder import build_faith_state
        state = build_faith_state(self.user)
        self.assertEqual(state.get("days_since_reading"), 0)
        self.assertGreaterEqual(state.get("reading_streak", 0), 1)


class WakeTimeMatcher(SimpleTestCase):
    def test_past_tense_matches(self):
        from apps.ai.deterministic_router import _match_actual_wake_query
        for q in ("what time did i wake up", "when did i wake up",
                  "what time did i get up", "when did i get up"):
            self.assertTrue(_match_actual_wake_query(q), q)

    def test_present_tense_schedule_not_matched(self):
        from apps.ai.deterministic_router import _match_actual_wake_query
        for q in ("what time is wake up", "when is my wake up scheduled"):
            self.assertFalse(_match_actual_wake_query(q), q)


class WakeTimeHandler(TestCase):
    def setUp(self):
        self.user = _user("wake@test.com")
        from apps.core.utils import get_user_today
        self.today = get_user_today(self.user)

    def test_uses_actual_not_scheduled(self):
        from apps.life.models import Routine, RoutineSchedule, RoutineLog
        routine = Routine.objects.create(user=self.user, name="Morning")
        sched = RoutineSchedule.objects.create(
            routine=routine, name="Wake Up", scheduled_time=dt_time(5, 0))
        actual = timezone.now().replace(hour=5, minute=50, second=0, microsecond=0)
        RoutineLog.objects.create(
            user=self.user, schedule=sched, scheduled_date=self.today,
            log_status=RoutineLog.STATUS_COMPLETED,
            completed_at=actual, performed_at=actual)

        from apps.ai.deterministic_router import _handle_actual_wake_query
        resp = _handle_actual_wake_query(self.user)
        self.assertIsNotNone(resp)
        self.assertIn("5:50", resp)            # actual surfaced
        self.assertIn("scheduled", resp.lower())  # transparency
        self.assertIn("actually", resp.lower())

    def test_no_data_is_honest_not_scheduled(self):
        from apps.ai.deterministic_router import _handle_actual_wake_query
        resp = _handle_actual_wake_query(self.user)
        self.assertIsNotNone(resp)
        self.assertIn("don't have a confirmed", resp.lower())


class FocusGate(SimpleTestCase):
    def _report(self, **kw):
        r = {"priority_level": "high", "confidence": 80, "sufficiency": "ok",
             "priority_reason": "22 days since last scripture reading"}
        r.update(kw)
        return r

    def test_completed_domain_suppressed_without_override(self):
        from apps.core.ai_state.right_now import compute_right_now_focus
        out = compute_right_now_focus(
            {"faith": self._report()}, completed_today={"faith"})
        self.assertEqual(out["status"], "steady")  # suppressed, not surfaced

    def test_completed_domain_surfaced_must_cite_structured_override(self):
        from apps.core.ai_state.right_now import compute_right_now_focus
        out = compute_right_now_focus(
            {"faith": self._report(focus_override={
                "rule_overridden": "Faith is complete today",
                "evidence": ["recurring journal theme: spiritual consistency"],
                "explanation": "your recent journal themes suggest you want "
                               "deeper consistency",
            })},
            completed_today={"faith"})
        self.assertEqual(out["status"], "focused")
        self.assertTrue(out["completed_override"])
        self.assertIn("completed today", out["reason"].lower())
        self.assertIn("Faith is complete today", out["reason"])      # rule cited
        self.assertIn("journal themes suggest", out["reason"])       # explanation
        self.assertIn("recurring journal theme", out["reason"])      # evidence
        self.assertIsNotNone(out["override"])

    def test_not_completed_domain_surfaces_normally(self):
        from apps.core.ai_state.right_now import compute_right_now_focus
        out = compute_right_now_focus(
            {"faith": self._report()}, completed_today=set())
        self.assertEqual(out["status"], "focused")
        self.assertFalse(out.get("completed_override"))
        self.assertIn("22 days", out["reason"])

    def test_backward_compatible_without_completed_today(self):
        from apps.core.ai_state.right_now import compute_right_now_focus
        out = compute_right_now_focus({"faith": self._report()})
        self.assertEqual(out["status"], "focused")  # no gate when arg omitted


class ExecutionCompletedDomains(SimpleTestCase):
    def test_maps_execution_truth_to_domains(self):
        from apps.core.ai_state import right_now
        truth = {
            "domains": {
                "faith": {"bible_reading_completed": True, "prayer_completed": False},
                "workout": {"completed": True},
                "journal": {"completed": False},
            },
            "medications": {"expected": 2, "all_taken": True},
        }
        with patch(
            "apps.core.execution.execution_truth_engine.get_execution_truth",
            return_value=truth,
        ):
            done = right_now._execution_completed_domains(object())
        self.assertEqual(done, {"faith", "workouts", "medication"})
