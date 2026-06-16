"""Approved modifications (2026-06-16):
  Mod 1 — Canonical faith truth: one source consumed by all (plan + routine
          bridge); dashboard / adherence / Beth / days-since cannot diverge.
  Mod 2 — Structured, evidence-required focus overrides; silent / hallucinated
          overrides are rejected.
"""
from datetime import time as dt_time, timedelta

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


# ── Mod 1 — canonical faith truth ───────────────────────────────────

class CanonicalFaithTruth(TestCase):
    def setUp(self):
        self.user = _user("canonfaith@test.com")
        from apps.core.utils import get_user_today
        self.today = get_user_today(self.user)

    def _complete_bible_routine_on(self, d):
        from apps.life.models import Routine, RoutineSchedule, RoutineLog
        routine, _ = Routine.objects.get_or_create(user=self.user, name="Morning")
        sched, _ = RoutineSchedule.objects.get_or_create(
            routine=routine, name="Bible Reading",
            defaults={"scheduled_time": dt_time(6, 0)})
        ts = timezone.now()
        RoutineLog.objects.create(
            user=self.user, schedule=sched, scheduled_date=d,
            log_status=RoutineLog.STATUS_COMPLETED,
            completed_at=ts, performed_at=ts)

    def test_scenario_a_completed_today_all_agree(self):
        """A: Bible read today (via routine) → every reader agrees: complete,
        days_since=0 — across the canonical resolver, completion_service,
        execution truth, and the SAE faith metric."""
        self._complete_bible_routine_on(self.today)
        from apps.faith.services.faith_queries import FaithQueries
        from apps.core.execution.completion_service import is_bible_reading_complete
        from apps.core.execution.execution_truth_engine import get_execution_truth
        from apps.core.ai_state.state_builder import build_faith_state

        self.assertTrue(FaithQueries.is_bible_complete_on(self.user, self.today))
        self.assertIn(self.today, FaithQueries.bible_completion_dates(self.user))
        self.assertTrue(is_bible_reading_complete(self.user, self.today))
        self.assertTrue(
            get_execution_truth(self.user)["domains"]["faith"]["bible_reading_completed"])
        self.assertEqual(build_faith_state(self.user).get("days_since_reading"), 0)

    def test_scenario_b_22_day_gap_consistent(self):
        """B: last reading 22 days ago, none since → days_since=22 everywhere,
        and today reads as NOT complete consistently."""
        self._complete_bible_routine_on(self.today - timedelta(days=22))
        from apps.faith.services.faith_queries import FaithQueries
        from apps.core.execution.completion_service import is_bible_reading_complete
        from apps.core.ai_state.state_builder import build_faith_state

        self.assertFalse(FaithQueries.is_bible_complete_on(self.user, self.today))
        self.assertFalse(is_bible_reading_complete(self.user, self.today))
        self.assertEqual(build_faith_state(self.user).get("days_since_reading"), 22)

    def test_scenario_c_late_backfill_reconciles(self):
        """C: a backfilled routine completion for today immediately reconciles
        across the live readers (no stale per-date snapshot blocks it)."""
        from apps.faith.services.faith_queries import FaithQueries
        from apps.core.execution.completion_service import is_bible_reading_complete
        self.assertFalse(is_bible_reading_complete(self.user, self.today))
        self._complete_bible_routine_on(self.today)  # late backfill
        self.assertTrue(is_bible_reading_complete(self.user, self.today))
        self.assertTrue(FaithQueries.is_bible_complete_on(self.user, self.today))


# ── Mod 2 — structured override framework ───────────────────────────

class StructuredOverride(SimpleTestCase):
    def _report(self, **kw):
        r = {"priority_level": "high", "confidence": 80, "sufficiency": "ok",
             "priority_reason": "22 days since last scripture reading"}
        r.update(kw)
        return r

    def test_1_normal_no_override_when_not_completed(self):
        from apps.core.ai_state.right_now import compute_right_now_focus
        out = compute_right_now_focus({"faith": self._report()}, completed_today=set())
        self.assertFalse(out.get("completed_override"))
        self.assertIsNone(out.get("override"))

    def test_2_valid_override_surfaces_with_evidence(self):
        from apps.core.ai_state.right_now import compute_right_now_focus, build_focus_override
        ov = build_focus_override(
            "Faith is complete today",
            ["recurring journal theme: wants deeper consistency"],
            "your journal themes suggest you want deeper spiritual consistency")
        self.assertIsNotNone(ov)
        out = compute_right_now_focus(
            {"faith": self._report(focus_override=ov)}, completed_today={"faith"})
        self.assertTrue(out["completed_override"])
        self.assertIn("grounded in:", out["reason"])
        self.assertIn("journal theme", out["reason"])

    def test_3_override_without_evidence_is_blocked(self):
        from apps.core.ai_state.right_now import compute_right_now_focus
        # explanation present but evidence empty → invalid → suppressed.
        out = compute_right_now_focus(
            {"faith": self._report(focus_override={
                "rule_overridden": "Faith is complete today",
                "evidence": [],
                "explanation": "trust me, you should do more",
            })},
            completed_today={"faith"})
        self.assertEqual(out["status"], "steady")  # blocked → normal prioritization

    def test_4_hallucinated_rationale_rejected(self):
        from apps.core.ai_state.right_now import build_focus_override, _valid_override
        # No evidence source → builder returns None, validator rejects.
        self.assertIsNone(build_focus_override("rule", [], "vibes"))
        self.assertIsNone(build_focus_override("rule", None, "vibes"))
        self.assertFalse(_valid_override({"rule_overridden": "r", "evidence": [""],
                                          "explanation": "x"}))
        self.assertFalse(_valid_override({"evidence": ["e"], "explanation": "x"}))  # no rule
        self.assertFalse(_valid_override("not a dict"))
