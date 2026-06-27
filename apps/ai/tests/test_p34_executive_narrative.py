# ==============================================================================
# File: apps/ai/tests/test_p34_executive_narrative.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: P34 Executive CONVERSATION — the composer tells ONE coherent story,
#   not labeled sections. New quality dimension: Executive Narrative (no report
#   headings, synthesis, integrated reasoning, explains recommendations, feels
#   conversational). The EXACT production conversation is the permanent regression.
# ==============================================================================
from datetime import datetime, timezone as _tz
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase

from apps.ai.chatgpt_cos import executive_brief as eb
from apps.ai.chatgpt_cos import acceptance_rules as ar

User = get_user_model()
_HZN = "apps.ai.chatgpt_cos.executive_interpretation._task_horizons"
_ES = "apps.ai.chatgpt_cos.executive_interpretation._exec_summary"
_HEALTH = "apps.ai.chatgpt_cos.executive_interpretation._health_read"
_AGENDA = "apps.ai.chatgpt_cos.executive_brief._agenda_narrative"

# The production scenario: 22 pending / 1 due today, ~5h sleep, feeling stretched.
PROD = {"today": 1, "overdue": 0, "soon": 3, "backlog": 18, "total": 22}
RECOVERY = {"recovery_needed": True, "read": "stable", "note": "", "sleep_hours": 5}
_HEADINGS = ("where things stand", "overall read:", "what matters today:",
             "highest-leverage move:", "your biggest risk right now:", "today's agenda —")


class ExecutiveNarrativeTests(TestCase):
    def setUp(self):
        from apps.users.models import TermsAcceptance
        self.u = User.objects.create_user(email="p34@example.com", password="x")
        TermsAcceptance.objects.create(
            user=self.u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.u.preferences.has_completed_onboarding = True
        self.u.preferences.save()

    def _brief(self, **kw):
        with mock.patch(_HZN, return_value=PROD), mock.patch(_ES, return_value={}), \
             mock.patch(_HEALTH, return_value=RECOVERY), \
             mock.patch(_AGENDA, return_value="This afternoon you've still got "
                        "Bike Ride at 2:00 PM — keep it light, none of it has to be heavy."):
            return eb.compose_executive_brief(self.u, **kw)

    def test_reads_as_one_story_not_sections(self):
        brief = self._brief(lead="Thanks — that helps.")
        low = brief.lower()
        self.assertNotIn("\n\n", brief)                       # one paragraph, not blocks
        for h in _HEADINGS:                                   # no implementation artifacts
            self.assertNotIn(h, low)

    def test_synthesizes_and_leads_with_conclusion(self):
        low = self._brief().lower()
        self.assertTrue(low.startswith("looking at everything together"))
        self.assertIn("more manageable than it probably feels", low)

    def test_energy_is_the_story_not_task_count(self):
        low = self._brief().lower()
        self.assertIn("the bigger challenge", low)
        self.assertIn("it's your energy", low)
        self.assertIn("about 5 hours", low)                   # evidence woven in
        self.assertIn("matters more", low)                    # judgment: energy > tasks

    def test_recommendation_has_a_why_and_resolves_conflict(self):
        low = self._brief().lower()
        self.assertIn("because of that", low)                 # explains WHY
        self.assertIn("count today as a win", low)            # a real recommendation
        self.assertIn("backlog can wait", low)
        self.assertIn("keep it light", low)                   # bike ride reconciled w/ recovery

    def test_no_repeated_raw_evidence_or_coming_up(self):
        low = self._brief().lower()
        self.assertNotIn("22 pending", low)
        self.assertNotIn("coming up", low)

    def test_scores_high_on_executive_narrative(self):
        brief = self._brief(lead="Thanks — that helps.")
        s = eb.score_executive_presence(brief)
        self.assertGreaterEqual(s["score"], 0.85)
        for d in ("no_report_headings", "synthesis", "explains_why", "judgment",
                  "actionability", "temporal_ok"):
            self.assertTrue(s[d], d)
        self.assertFalse(ar.is_failure_message(brief))
        self.assertEqual(ar.banned_hits(brief), [])


class RepairDemonstratesBetterJudgmentTests(TestCase):
    """When Danny critiques, the rewrite must obviously be better — a narrative
    executive brief, not a reworded report."""
    def setUp(self):
        from apps.users.models import TermsAcceptance
        from apps.ai.models import AssistantConversation, AssistantMessage
        self.u = User.objects.create_user(email="p34r@example.com", password="x")
        TermsAcceptance.objects.create(
            user=self.u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.u.preferences.has_completed_onboarding = True
        self.u.preferences.save()
        self.conv = AssistantConversation.objects.create(user=self.u, is_active=True)
        AssistantMessage.objects.create(
            conversation=self.conv, role="assistant",
            content="Coming up today you have Drink Protein Shake at 6:45 AM. "
                    "Your highest priority is Drink Protein Shake.")

    def test_repair_is_a_narrative_not_a_report(self):
        from apps.ai.chatgpt_cos.lanes import route_message
        from apps.ai.models import AssistantMessage
        _C, _CT = ("apps.ai.services.ai_service._call_api",
                   "apps.ai.services.ai_service._call_api_with_tools")
        AssistantMessage.objects.create(conversation=self.conv, role="user",
                                        content="Does that sound right to you?")
        with mock.patch(_C, side_effect=RuntimeError("down")), \
             mock.patch(_CT, side_effect=RuntimeError("down")):
            res = route_message(self.u, "Does that sound right to you?", self.conv)
        self.assertEqual(res["lane"], "conversation_repair")
        ans = res["answer"]
        self.assertIn("you're right", ans.lower())
        self.assertIn("led with the agenda", ans.lower())     # names the miss
        s = eb.score_executive_presence(ans)
        self.assertTrue(s["no_report_headings"])              # the rewrite is narrative
        self.assertTrue(s["synthesis"])


class NarrativeScorerTests(SimpleTestCase):
    def test_section_report_fails_the_scorer(self):
        report = ("Where things stand: ok. Overall read: steady. What matters today: "
                  "tasks. Highest-leverage move: workout. Today's agenda — Workout.")
        s = eb.score_executive_presence(report)
        self.assertFalse(s["no_report_headings"])
        self.assertLess(s["score"], 0.5)
