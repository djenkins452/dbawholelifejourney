# ==============================================================================
# File: apps/ai/tests/test_overview_and_priority.py
# Description: Two production CoS behaviors.
#   #1 "How am I doing overall?" must produce a whole-life EXECUTIVE BRIEFING (cos_
#      briefing), not a health report (it was routing to personal_reasoning → health).
#   #2 "What is the single most important thing I should do right now?" must ALWAYS
#      have a deterministic answer (health-critical → execution decision → rhythm →
#      canonical) and NEVER fall to the LLM / "I couldn't pull that together".
# ==============================================================================
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.chatgpt_cos.lanes import (
    route_message, _cos_briefing_lane, _deterministic_priority_answer)

User = get_user_model()
_GDS = "apps.ai.cos_services.get_domain_state"
_DOSES = "apps.health.services.medicine_queries.MedicineQueries.today_doses"
_DECISION = "apps.ai.cos_services.tool_registry._h_decision"
_RHYTHM = "apps.core.cos_briefing.rhythm_api.get_current_rhythm_item"


def _empty(user, domain):
    return {"state": {}}


class OverviewBriefingTests(TestCase):
    def setUp(self):
        from apps.ai.models import AssistantConversation
        self.user = User.objects.create_user(email="ov@test.com", password="x")
        self.conv = AssistantConversation.objects.create(user=self.user)

    def test_how_am_i_doing_overall_is_an_executive_briefing(self):
        with mock.patch(_GDS, side_effect=_empty):
            out = route_message(self.user, "How am I doing overall?", self.conv)
        self.assertIsNotNone(out)
        self.assertEqual(out["lane"], "cos_briefing")     # NOT personal_reasoning/health
        self.assertTrue(out["answer"])

    def test_domain_scoped_overview_stays_a_domain_question(self):
        # A health/goal-scoped "how am I doing" must NOT be claimed by the whole-life
        # briefing — it belongs to reasoning/foundational.
        for q in ("how am I doing on my weight",
                  "How am I doing overall with my health goals?",
                  "how am I doing with my glucose"):
            self.assertIsNone(_cos_briefing_lane(self.user, q), q)


class PriorityNowTests(TestCase):
    def setUp(self):
        from apps.ai.models import AssistantConversation
        self.user = User.objects.create_user(email="pr@test.com", password="x")
        self.conv = AssistantConversation.objects.create(user=self.user)

    def test_always_answers_never_the_generic_failure(self):
        out = route_message(
            self.user, "What is the single most important thing I should do right now?",
            self.conv)
        self.assertIsNotNone(out)
        self.assertEqual(out["lane"], "priority_now")
        self.assertTrue(out["answer"])
        self.assertNotIn("couldn't pull", out["answer"].lower())

    def test_health_critical_is_the_priority(self):
        overdue = [{"medication": "Metformin", "time": "8:00 AM", "status": "overdue"}]
        with mock.patch(_DOSES, return_value=overdue):
            ans = _deterministic_priority_answer(self.user)
        self.assertIn("overdue", ans.lower())
        self.assertIn("first", ans.lower())

    def test_graceful_degrade_when_every_preferred_source_fails(self):
        # Health-critical empty, execution decision + rhythm both raise → still a
        # deterministic, honest answer (never an error, never None).
        with mock.patch(_DOSES, return_value=[]), \
                mock.patch(_DECISION, side_effect=RuntimeError("service down")), \
                mock.patch(_RHYTHM, side_effect=RuntimeError("rhythm down")):
            ans = _deterministic_priority_answer(self.user)
        self.assertTrue(ans)
        self.assertNotIn("couldn't", ans.lower())
        self.assertNotIn("unavailable", ans.lower())

    def test_uses_execution_decision_when_available(self):
        with mock.patch(_DOSES, return_value=[]), \
                mock.patch(_DECISION, return_value={"message": "finish the Q3 report",
                                                    "reason": "it's due today"}):
            ans = _deterministic_priority_answer(self.user)
        self.assertIn("q3 report", ans.lower())
        self.assertIn("due today", ans.lower())
