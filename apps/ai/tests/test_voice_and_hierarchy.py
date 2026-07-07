# ==============================================================================
# File: apps/ai/tests/test_voice_and_hierarchy.py
# Description: NATURAL EXECUTIVE VOICE + GOAL HIERARCHY (Phase 2). Two production gaps:
#   (a) internal reasoning vocabulary leaked to the user ("backlog", "energy-management
#       day", "I trust your lived experience"); (b) the primary MISSION (France 2027) was
#       treated as a competing priority ("the real leverage is moving France forward")
#       instead of an OUTCOME that today's daily health execution ADVANCES.
# ==============================================================================
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.ai.chatgpt_cos.naturalize import naturalize
from apps.ai.chatgpt_cos import executive_brief as EB
from apps.ai.chatgpt_cos.executive_interpretation import ExecutiveSignals

User = get_user_model()


def _mkuser(email):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="x")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u

_INTERPRET = "apps.ai.chatgpt_cos.executive_brief._safe_interpret"
_AGENDA = "apps.ai.chatgpt_cos.executive_brief._agenda_narrative"
_PLANNED = "apps.ai.chatgpt_cos.day_truth.todays_planned_workout"
_PROTEIN = "apps.ai.chatgpt_cos.day_truth.protein_options"
MISSION = {"title": "France 2027 Family 18K Mission", "advanced_by": "health",
           "current_focus": "Goal Weight of 289.9"}


# ── Natural voice: internal vocabulary is translated ───────────────────────────
class NaturalizeTests(SimpleTestCase):
    def test_operational_and_internal_terms_are_translated(self):
        self.assertEqual(naturalize("The rest of your backlog can wait."),
                         "The rest of your open items can wait.")
        self.assertNotIn("energy-management day",
                         naturalize("today is an energy-management day").lower())
        self.assertNotIn("lived experience",
                         naturalize("I trust your lived experience").lower())
        self.assertNotIn("recovery latitude",
                         naturalize("that earns recovery latitude").lower())

    def test_it_never_raises_and_preserves_clean_text(self):
        self.assertEqual(naturalize(""), "")
        self.assertEqual(naturalize(None), None)
        clean = "Good — let's put that energy to work today."
        self.assertEqual(naturalize(clean), clean)


# ── Goal hierarchy: interpret() reframes a health-advanced mission ─────────────
class MissionHierarchyInterpretTests(TestCase):
    def setUp(self):
        self.u = _mkuser("voice_interp@example.com")

    def _interpret_mission(self, mission):
        # Only the mission read matters here; stub the rest so interpret is cheap.
        with mock.patch("apps.ai.chatgpt_cos.executive_interpretation._mission_info",
                        return_value=mission), \
             mock.patch("apps.ai.chatgpt_cos.executive_interpretation._task_horizons",
                        return_value={"today": 0, "overdue": 0, "soon": 0,
                                      "backlog": 5, "total": 5}), \
             mock.patch("apps.ai.chatgpt_cos.executive_interpretation._exec_summary",
                        return_value={}), \
             mock.patch("apps.ai.chatgpt_cos.executive_interpretation._health_read",
                        return_value={"recovery_needed": False, "read": "stable",
                                      "sleep_hours": 7.0}):
            from apps.ai.chatgpt_cos.executive_interpretation import interpret
            return interpret(self.u)

    def test_health_advanced_mission_is_not_a_competing_leverage_bullet(self):
        sig = self._interpret_mission(MISSION)
        # It is carried as the mission hierarchy…
        self.assertEqual(sig.mission.get("advanced_by"), "health")
        # …and NOT emitted as a separate "move France forward" leverage item.
        self.assertNotIn("moving france", (sig.highest_leverage or "").lower())
        self.assertEqual(sig.highest_leverage, "")

    def test_non_health_mission_still_uses_the_leverage_framing(self):
        other = {"title": "Write my book", "advanced_by": None}
        sig = self._interpret_mission(other)
        self.assertIn("write my book", (sig.highest_leverage or "").lower())


# ── Composer: the mission is the through-line, one thesis, natural voice ───────
class MissionThesisComposeTests(SimpleTestCase):
    def _brief(self, sig):
        with mock.patch(_INTERPRET, return_value=sig), \
             mock.patch(_AGENDA, return_value="This morning your rhythm is clear."), \
             mock.patch(_PLANNED, return_value={"type": "cardio", "time": "6:00 PM",
                                                "completed": False}), \
             mock.patch(_PROTEIN, return_value="eggs, Greek yogurt, or a protein shake"):
            return EB.compose_executive_brief(None, lead="Got it. ", subjective="positive")

    def test_mission_is_the_through_line_not_a_competing_priority(self):
        sig = ExecutiveSignals(
            foundation=["prayer and Bible reading"], reconciliation="positive_over_debt",
            sleep_hours=6.0, workload="manageable", backlog_can_wait=True,
            stance={"stance": "plan"}, mission=MISSION)
        brief = self._brief(sig).lower()
        # The mission is framed as advanced by today's execution ("it IS the mission").
        self.assertIn("france 2027", brief)
        self.assertIn("it is the mission", brief)
        self.assertTrue("moves" in brief or "advancing it" in brief)
        # NEVER the old competing-priority framing.
        self.assertNotIn("the real leverage is moving france", brief)

    def test_brief_uses_natural_voice_no_internal_jargon(self):
        sig = ExecutiveSignals(
            foundation=["prayer and Bible reading"], reconciliation="positive_over_debt",
            sleep_hours=6.0, workload="manageable", backlog_can_wait=True,
            stance={"stance": "plan"}, mission=MISSION)
        # Simulate the full choke-point (compose → naturalize).
        brief = naturalize(self._brief(sig)).lower()
        for jargon in ("backlog", "lived experience", "energy-management day",
                       "recovery-management", "recovery latitude"):
            self.assertNotIn(jargon, brief)
