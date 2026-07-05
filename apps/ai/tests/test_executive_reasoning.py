# ==============================================================================
# File: apps/ai/tests/test_executive_reasoning.py
# Description: EXECUTIVE REASONING STRUCTURE. An exceptional Chief of Staff answers an
#   executive question ASSESSMENT → REASONING → ACTION, not question → recommendation.
#   Production failures showed Beth jumping straight to a fact/recommendation. `frame()`
#   enforces the order for the deterministic executive lanes (risk, priority).
# ==============================================================================
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.ai.chatgpt_cos.executive_reasoning import frame
from apps.ai.chatgpt_cos.lanes import _deterministic_risk_answer, _deterministic_priority_answer

User = get_user_model()
_DOSES = "apps.health.services.medicine_queries.MedicineQueries.today_doses"
_INTEL = "apps.ai.cos_intelligence.active_intelligence"
_DECISION = "apps.ai.cos_services.tool_registry._h_decision"


class FrameTests(SimpleTestCase):
    def test_order_is_assessment_reasoning_action(self):
        out = frame("you're in solid shape", "nothing is overdue", "keep steady")
        self.assertEqual(out, "You're in solid shape. Nothing is overdue. Keep steady.")
        self.assertLess(out.index("solid shape"), out.index("Nothing is overdue"))
        self.assertLess(out.index("Nothing is overdue"), out.index("Keep steady"))

    def test_assessment_alone_is_valid(self):
        self.assertEqual(frame("no real risk today"), "No real risk today.")

    def test_empty_is_safe(self):
        self.assertEqual(frame(""), "")


class ExecutiveLaneReasoningOrderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="err@test.com", password="x")

    def test_risk_answer_leads_with_assessment_then_action(self):
        risks = [{"text": "protein has been below target for 3 weeks",
                  "basis": "nutrition insight", "confidence": "high"}]
        with mock.patch(_DOSES, return_value=[]), \
                mock.patch(_INTEL, return_value={"risks": risks, "opportunities": [],
                                                 "predictions": [], "patterns": [], "guidance": []}):
            ans = _deterministic_risk_answer(self.user).lower()
        # Assessment (the risk) first, the recommended action last.
        self.assertLess(ans.index("biggest risk"), ans.index("get ahead of it"))

    def test_priority_answer_leads_with_assessment_then_action(self):
        with mock.patch(_DOSES, return_value=[]), \
                mock.patch(_DECISION, return_value={"message": "finish the Q3 report",
                                                    "reason": "it's due today"}):
            ans = _deterministic_priority_answer(self.user).lower()
        # Assessment (highest-leverage move) + reasoning (due today) precede the action.
        self.assertIn("highest-leverage move", ans)
        self.assertLess(ans.index("highest-leverage move"), ans.index("start there"))
        self.assertLess(ans.index("due today"), ans.index("start there"))
