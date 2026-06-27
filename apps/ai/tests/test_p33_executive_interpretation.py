# ==============================================================================
# File: apps/ai/tests/test_p33_executive_interpretation.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: P33 Executive Interpretation Engine — JUDGMENT, not counting. Raw
#   facts become ExecutiveSignals before composition: workload is today's
#   commitments + overdue (NOT total pending), and a strategic backlog is never an
#   overload conclusion. Permanent regression = the EXACT production case (22 pending,
#   1 due today). Tests executive INTERPRETATION, not task counts.
# ==============================================================================
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase

from apps.ai.chatgpt_cos import executive_interpretation as ei
from apps.ai.chatgpt_cos import executive_brief as eb

User = get_user_model()
_HZN = "apps.ai.chatgpt_cos.executive_interpretation._task_horizons"
_ES = "apps.ai.chatgpt_cos.executive_interpretation._exec_summary"
_HEALTH = "apps.ai.chatgpt_cos.executive_interpretation._health_read"


class WorkloadInterpretationTests(SimpleTestCase):
    # The PRODUCTION case: 22 pending, only 1 due today.
    PROD = {"today": 1, "overdue": 0, "soon": 4, "backlog": 18, "total": 22}

    def _interpret(self, horizons, es=None, health=None):
        es = es if es is not None else {}
        health = health or {"recovery_needed": False, "read": "stable", "note": ""}
        with mock.patch(_HZN, return_value=horizons), \
             mock.patch(_ES, return_value=es), \
             mock.patch(_HEALTH, return_value=health):
            return ei.interpret(user=mock.Mock())

    def test_production_case_is_manageable_not_overload(self):
        sig = self._interpret(self.PROD)
        self.assertEqual(sig.workload, "manageable")          # NOT heavy/overloaded
        self.assertNotIn("overload", sig.headline.lower())
        # the exact conclusion an outstanding human CoS would reach:
        self.assertIn("despite a healthy strategic backlog", sig.headline.lower())
        self.assertEqual(sig.today_count, 1)
        self.assertEqual(sig.total_pending, 22)
        self.assertFalse(sig.intervention_required)           # backlog != intervention

    def test_workload_summary_separates_today_from_backlog(self):
        sig = self._interpret(self.PROD)
        s = sig.workload_summary.lower()
        self.assertIn("1 due today", s)
        self.assertIn("backlog", s)
        self.assertIn("not today's load", s)

    def test_truly_busy_day_is_full_or_heavy(self):
        self.assertEqual(self._interpret(
            {"today": 5, "overdue": 1, "soon": 6, "backlog": 2, "total": 14}).workload,
            "full")
        self.assertIn(self._interpret(
            {"today": 8, "overdue": 4, "soon": 12, "backlog": 0, "total": 12}).workload,
            ("heavy", "overloaded"))

    def test_huge_backlog_zero_due_today_is_light(self):
        sig = self._interpret({"today": 0, "overdue": 0, "soon": 0, "backlog": 40,
                               "total": 40})
        self.assertEqual(sig.workload, "light")
        self.assertFalse(sig.intervention_required)

    def test_overdue_drives_intervention_not_backlog(self):
        sig = self._interpret({"today": 0, "overdue": 6, "soon": 6, "backlog": 30,
                               "total": 36})
        self.assertTrue(sig.intervention_required)            # 6 overdue is real
        self.assertEqual(sig.overdue_count, 6)


class ComposerNarratesJudgmentTests(TestCase):
    def setUp(self):
        from apps.users.models import TermsAcceptance
        self.u = User.objects.create_user(email="p33@example.com", password="x")
        TermsAcceptance.objects.create(
            user=self.u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.u.preferences.has_completed_onboarding = True
        self.u.preferences.save()

    def test_brief_concludes_manageable_not_overload(self):
        prod = {"today": 1, "overdue": 0, "soon": 4, "backlog": 18, "total": 22}
        with mock.patch(_HZN, return_value=prod), mock.patch(_ES, return_value={}):
            brief = eb.compose_executive_brief(self.u)
        low = brief.lower()
        # the success criterion, demonstrated:
        self.assertIn("manageable", low)
        self.assertIn("backlog", low)                  # backlog distinguished, can wait
        self.assertNotIn("22 pending", low)
        self.assertNotIn("is overloaded", low)
        self.assertNotIn("high workload", low)
        self.assertIn("don't have an overloaded", low)   # explicitly negates overload
        # judgment scorer agrees
        j = eb.score_executive_judgment(brief)
        self.assertTrue(j["workload_interpreted"])
        self.assertTrue(j["backlog_distinguished"])
        self.assertTrue(j["no_count_overload"])
        self.assertGreaterEqual(j["score"], 0.75)

    def test_judgment_scorer_flags_raw_count_dump(self):
        bad = "You're carrying 22 pending tasks, so today is a high workload — overload."
        j = eb.score_executive_judgment(bad)
        self.assertFalse(j["no_count_overload"])
        self.assertLess(j["score"], 0.6)

