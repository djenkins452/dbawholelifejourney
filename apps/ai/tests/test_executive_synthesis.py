# ==============================================================================
# File: apps/ai/tests/test_executive_synthesis.py
# Description: EXECUTIVE SYNTHESIS OVER RETRIEVED TRUTH (Phase 2). A volunteered morning
#   self-report ("I feel rested, six hours is fine for energy, I already did my prayer
#   and Bible reading") must be LISTENED to and answered with ONE whole-picture executive
#   assessment — not routed to a single-domain health intent that replies "prioritize
#   sleep". Regression for the domain-first reasoning gap.
# ==============================================================================
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase

from apps.ai.chatgpt_cos import accomplishment as A
from apps.ai.chatgpt_cos import executive_brief as EB
from apps.ai.chatgpt_cos.executive_interpretation import ExecutiveSignals

User = get_user_model()
_C = "apps.ai.services.ai_service._call_api"
_CT = "apps.ai.services.ai_service._call_api_with_tools"
_PLANNED = "apps.ai.chatgpt_cos.day_truth.todays_planned_workout"
_PROTEIN = "apps.ai.chatgpt_cos.day_truth.protein_options"
_INTERPRET = "apps.ai.chatgpt_cos.executive_brief._safe_interpret"
_AGENDA = "apps.ai.chatgpt_cos.executive_brief._agenda_narrative"
CARDIO = {"type": "cardio", "time": "6:00 PM", "completed": False}

REPORT = ("Overall I feel rested. Six hours isn't bad for me for energy. I wish I'd "
          "gotten more for my health. I got a great start today by finishing my prayer "
          "and Bible reading.")


def _mkuser(email):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="x")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


# ── Accomplishment capture (the near-miss phrasing) ────────────────────────────
class FoundationCaptureTests(SimpleTestCase):
    def test_natural_phrasing_is_recognized(self):
        for m in ("I got a great start today by finishing my prayer and Bible reading",
                  "finished my Bible reading this morning",
                  "started my day with prayer",
                  "I already got my prayer in"):
            a = A.detect(m)
            self.assertIsNotNone(a, m)
            self.assertEqual(a.kind, "foundation")

    def test_is_foundation_label(self):
        self.assertTrue(A.is_foundation_label("prayer and Bible reading"))
        self.assertFalse(A.is_foundation_label("got today's workout in"))


# ── interpret() keeps foundation separate from physical effort ─────────────────
class FoundationNotRecoveryTests(TestCase):
    def setUp(self):
        self.u = _mkuser("synth_found@example.com")

    def test_foundation_does_not_flip_the_day_into_recovery(self):
        from apps.ai.chatgpt_cos.executive_evidence import record_accomplishment
        from apps.ai.chatgpt_cos.executive_interpretation import interpret
        record_accomplishment(self.u, "prayer and Bible reading")
        sig = interpret(self.u)
        # Foundation is captured in its own field…
        self.assertIn("prayer and Bible reading", sig.foundation)
        # …and NOT treated as a completed workout ("ahead of plan → recovery latitude").
        self.assertNotIn("prayer and Bible reading", sig.accomplishments)
        self.assertNotIn("ahead of plan", (sig.headline or "").lower())


# ── The whole-picture synthesis (one executive assessment) ─────────────────────
class ExecutiveSynthesisTests(SimpleTestCase):
    def _brief(self, sig):
        with mock.patch(_INTERPRET, return_value=sig), \
             mock.patch(_AGENDA, return_value="This morning your rhythm is clear."), \
             mock.patch(_PLANNED, return_value=CARDIO), \
             mock.patch(_PROTEIN, return_value="eggs, Greek yogurt, or a protein shake"):
            return EB.compose_executive_brief(
                None, lead="Got it. ", subjective="positive").lower()

    def test_brief_synthesizes_foundation_energy_recovery_and_next_move(self):
        sig = ExecutiveSignals(
            foundation=["prayer and Bible reading"], reconciliation="positive_over_debt",
            sleep_hours=6.0, workload="manageable", backlog_can_wait=True,
            stance={"stance": "plan"})
        brief = self._brief(sig)
        # 1. acknowledges the foundation (listening + accomplishment incorporated)
        self.assertIn("prayer and bible reading", brief)
        self.assertIn("foundation", brief)
        # 2. distinguishes ENERGY (use it) from RECOVERY (still protect sleep) — in
        #    natural language, no internal "energy/recovery-management day" labels.
        self.assertIn("put that energy to work", brief)
        self.assertIn("earlier night", brief)
        self.assertNotIn("energy-management day", brief)
        self.assertNotIn("lived experience", brief)
        # 3. actionable, personalized next move tied to tonight's ACTUAL workout
        self.assertIn("protein", brief)
        self.assertIn("cardio", brief)
        self.assertTrue(any(f in brief for f in ("eggs", "yogurt", "shake")))
        # 4. it is ONE assessment, not a lone sleep line
        self.assertNotIn("prioritize getting more sleep", brief)

    def test_foundation_beat_is_not_workout_framed(self):
        sig = ExecutiveSignals(foundation=["prayer and Bible reading"],
                               reconciliation="confirmed_good", stance={"stance": "plan"})
        brief = self._brief(sig)
        # Spiritual work is never framed as physical "recovery latitude".
        self.assertNotIn("recovery latitude", brief)
        self.assertNotIn("ahead of plan", brief)


# ── Routing: a volunteered self-report reaches the executive synthesis ─────────
class SelfReportRoutingTests(TestCase):
    def setUp(self):
        from apps.ai.models import AssistantConversation
        self.u = _mkuser("synth_route@example.com")
        self.conv = AssistantConversation.objects.create(user=self.u, is_active=True)

    def _route(self, msg):
        from apps.ai.chatgpt_cos.lanes import route_message
        from apps.ai.models import AssistantMessage
        AssistantMessage.objects.create(conversation=self.conv, role="user", content=msg)
        with mock.patch(_C, side_effect=RuntimeError("down")), \
             mock.patch(_CT, side_effect=RuntimeError("down")), \
             mock.patch(_PLANNED, return_value=CARDIO), \
             mock.patch(_PROTEIN, return_value="eggs, Greek yogurt, or a protein shake"):
            return route_message(self.u, msg, self.conv)

    def test_volunteered_report_routes_to_self_report_not_health_intent(self):
        res = self._route(REPORT)
        self.assertIsNotNone(res)
        self.assertEqual(res["lane"], "self_report")
        ans = res["answer"]
        low = ans.lower()
        # A volunteered positive report is ORIENTED (acknowledge the strong start, hand
        # back), not answered with a single-domain sleep recommendation or a full report.
        self.assertTrue(ans.rstrip().endswith("?"))
        self.assertIn("strong start", low)
        self.assertFalse(low.startswith("today's focus"))
        self.assertFalse(low.startswith("today, focus on"))

    def test_a_plain_question_is_not_stolen_by_self_report(self):
        # A real question must still fall through to normal routing (not self_report).
        res = self._route("What should I focus on for my health today?")
        if res is not None:
            self.assertNotEqual(res.get("lane"), "self_report")
