# ==============================================================================
# File: apps/ai/tests/test_executive_opportunity.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Executive Opportunity is EXECUTIVE JUDGMENT, not positive-insight aliasing.
#   The prior implementation aliased a positive domain insight (protein, weight, a habit
#   streak) into an "opportunity". Those are EVIDENCE / WINS — not opportunities. A real
#   executive opportunity answers "What action, taken now, creates disproportionate
#   value?" and is derived from executive STATE (capacity, strategic leverage, momentum,
#   energy, task drag) by interpret(), ranked by EXPECTED VALUE (leverage × probability),
#   with an honest "no standout opportunity" when none exists.
# ==============================================================================
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.chatgpt_cos.executive_interpretation import _opportunity_assessment
from apps.ai.chatgpt_cos.lanes import _executive_opportunity_lane

User = get_user_model()
_OPP = "apps.ai.chatgpt_cos.lanes._executive_opportunity"


def _tw(today=0, overdue=0, soon=0, backlog=0, total=0):
    return {"today": today, "overdue": overdue, "soon": soon,
            "backlog": backlog, "total": total}


class OpportunityAssessmentTests(TestCase):
    """The assessment itself is executive judgment — derived from state, ranked by
    expected value, and honestly empty when there is no standout opening."""

    def test_open_capacity_plus_strategic_leverage_is_the_opportunity(self):
        o = _opportunity_assessment(
            workload="light", ease_load=False, strategic="the France trip",
            tw=_tw(), reconciliation="", subjective=None, accomplishments=[])
        self.assertIsNotNone(o)
        self.assertIn("france trip", o["text"].lower())
        self.assertTrue(o["basis"] and o["action"])   # explainable through evidence

    def test_no_signals_is_honestly_none(self):
        # Full day, no capacity, no strategic leverage, no energy, no cluster → NO
        # opportunity. Honesty over invention: today is for disciplined execution.
        o = _opportunity_assessment(
            workload="full", ease_load=False, strategic="",
            tw=_tw(today=4), reconciliation="", subjective=None, accomplishments=[])
        self.assertIsNone(o)

    def test_probability_lets_a_near_certain_cluster_win_when_alone(self):
        # Only a cluster of small items → it wins by being near-certain (the Probability
        # of Success addition: max expected value, not max theoretical leverage).
        o = _opportunity_assessment(
            workload="full", ease_load=False, strategic="",
            tw=_tw(soon=4), reconciliation="", subjective=None, accomplishments=[])
        self.assertIn("clear in one pass", o["text"])

    def test_strategic_leverage_outranks_quickwin_by_expected_value(self):
        # Both present: strategic EV (.90×.85) beats the cluster EV (.40×.95).
        o = _opportunity_assessment(
            workload="light", ease_load=False, strategic="the launch",
            tw=_tw(soon=6), reconciliation="", subjective=None, accomplishments=[])
        self.assertIn("launch", o["text"].lower())

    def test_good_energy_becomes_a_hard_problem_opportunity(self):
        o = _opportunity_assessment(
            workload="full", ease_load=False, strategic="",
            tw=_tw(), reconciliation="", subjective="positive", accomplishments=[])
        self.assertIn("energy", o["text"].lower())
        self.assertIn("deferring", o["action"].lower())

    def test_ahead_of_plan_pulls_the_next_milestone_forward(self):
        o = _opportunity_assessment(
            workload="full", ease_load=False, strategic="",
            tw=_tw(), reconciliation="", subjective=None,
            accomplishments=["shipped the report"])
        self.assertIn("ahead of plan", o["text"].lower())

    def test_recovery_day_is_not_an_opening_to_push(self):
        # ease_load gates the capacity candidate — a recovery day is not opportunism.
        o = _opportunity_assessment(
            workload="light", ease_load=True, strategic="the launch",
            tw=_tw(), reconciliation="", subjective=None, accomplishments=[])
        self.assertIsNone(o)


class ExecutiveOpportunityLaneTests(TestCase):
    """'What opportunity am I missing today?' is answered by executive judgment and is
    NEVER a positive-insight recommendation (no protein)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="opp_lane@test.com", password="x")

    def test_presents_the_executive_opportunity(self):
        opp = {"text": "a genuinely open day and real leverage in the France trip",
               "basis": "your required load is light today and your strategic focus is clear",
               "action": "protect a real block and move the France trip forward"}
        with mock.patch(_OPP, return_value=opp):
            out = _executive_opportunity_lane(
                self.user, "What opportunity am I missing today?")
        self.assertIsNotNone(out)
        self.assertEqual(out["lane"], "executive_opportunity")
        low = out["answer"].lower()
        self.assertIn("opportunity to seize", low)     # ASSESSMENT
        self.assertIn("france trip", low)              # ACTION, grounded in evidence

    def test_no_opportunity_is_honest_never_a_positive_insight(self):
        # The production failure: a positive protein insight must NOT be sold as an
        # opportunity. With no executive opportunity, Beth says so and explains why.
        with mock.patch(_OPP, return_value=None):
            out = _executive_opportunity_lane(
                self.user, "What opportunity am I missing today?")
        low = out["answer"].lower()
        self.assertIn("no standout opportunity", low)
        self.assertIn("disciplined execution", low)
        self.assertNotIn("protein", low)

    def test_domain_scoped_opportunity_yields_to_domain_reasoning(self):
        self.assertIsNone(_executive_opportunity_lane(
            self.user, "any opportunity to improve my protein?"))
        self.assertIsNone(_executive_opportunity_lane(
            self.user, "where's the opportunity in my health?"))

    def test_unrelated_message_not_claimed(self):
        self.assertIsNone(_executive_opportunity_lane(
            self.user, "what's my glucose right now?"))
