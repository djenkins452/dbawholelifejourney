# ==============================================================================
# File: apps/ai/tests/test_executive_risk.py
# Description: "What is the biggest risk I should pay attention to today?" is an
#   EXECUTIVE-RISK question — a whole-life risk synthesis, NOT a health intent and NOT a
#   goal update. Production failure: it was answered "no significant risks, your mission
#   France 2027 is on pace" (a goal update — a category error), because the reasoning
#   planner classified "biggest risk" as a health intent → goal-risk fallback. Fix: a
#   first-class executive_risk lane synthesizing health-critical + risk intelligence +
#   the at-risk decision, degrading to an honest "why no risk" + biggest opportunity.
# ==============================================================================
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.chatgpt_cos.lanes import (
    route_message, _executive_risk_lane, _deterministic_risk_answer)

User = get_user_model()
_DOSES = "apps.health.services.medicine_queries.MedicineQueries.today_doses"
_INTEL = "apps.ai.cos_intelligence.active_intelligence"
_DECISION = "apps.ai.cos_services.tool_registry._h_decision"
Q = "What is the biggest risk I should pay attention to today?"


def _intel(risks=None, opportunities=None):
    return {"risks": risks or [], "opportunities": opportunities or [],
            "predictions": [], "patterns": [], "guidance": []}


class ExecutiveRiskTests(TestCase):
    def setUp(self):
        from apps.ai.models import AssistantConversation
        self.user = User.objects.create_user(email="er@test.com", password="x")
        self.conv = AssistantConversation.objects.create(user=self.user)

    def test_the_production_question_routes_to_executive_risk_not_goals(self):
        with mock.patch(_DOSES, return_value=[]), mock.patch(_INTEL, return_value=_intel()), \
                mock.patch(_DECISION, return_value={}):
            out = route_message(self.user, Q, self.conv)
        self.assertEqual(out["lane"], "executive_risk")     # NOT personal_reasoning/goal
        low = out["answer"].lower()
        self.assertNotIn("on pace", low)                    # never a goal update
        self.assertNotIn("mission", low)

    def test_health_critical_is_the_biggest_risk(self):
        overdue = [{"medication": "Metformin", "time": "8:00 AM", "status": "overdue"}]
        with mock.patch(_DOSES, return_value=overdue):
            ans = _deterministic_risk_answer(self.user).lower()
        self.assertIn("health-critical", ans)
        self.assertIn("overdue", ans)

    def test_computed_risk_intelligence_is_cited_with_basis(self):
        risks = [{"text": "Protein trending well below target", "basis": "nutrition insight",
                  "confidence": "high"}]
        with mock.patch(_DOSES, return_value=[]), mock.patch(_INTEL, return_value=_intel(risks=risks)):
            ans = _deterministic_risk_answer(self.user).lower()
        self.assertIn("protein", ans)
        self.assertIn("basis:", ans)

    def test_at_risk_decision_used_when_no_higher_risk(self):
        with mock.patch(_DOSES, return_value=[]), mock.patch(_INTEL, return_value=_intel()), \
                mock.patch(_DECISION, return_value={"message": "your Q3 review is overdue",
                                                    "reason": "it was due yesterday"}):
            ans = _deterministic_risk_answer(self.user).lower()
        self.assertIn("q3 review", ans)
        self.assertIn("biggest risk", ans)

    def test_no_meaningful_risk_explains_why_and_offers_opportunity(self):
        opps = [{"text": "workout consistency up 40%"}]
        with mock.patch(_DOSES, return_value=[]), \
                mock.patch(_INTEL, return_value=_intel(opportunities=opps)), \
                mock.patch(_DECISION, return_value={"message": "No significant risk right now"}):
            ans = _deterministic_risk_answer(self.user).lower()
        self.assertIn("nothing rises to a real risk", ans)   # explains WHY
        self.assertIn("opportunity", ans)                     # offers the biggest opportunity
        self.assertIn("workout consistency", ans)

    def test_domain_scoped_risk_yields_to_reasoning(self):
        # "biggest HEALTH risk" / "risk to my GOAL" stays a domain question.
        self.assertIsNone(_executive_risk_lane(self.user, "what's my biggest health risk?"))
        self.assertIsNone(_executive_risk_lane(self.user, "what's the risk to my goal?"))
