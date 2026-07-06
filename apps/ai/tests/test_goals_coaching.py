# ==============================================================================
# File: apps/ai/tests/test_goals_coaching.py
# Description: EXECUTIVE COACHING. The goals & commitments answer must COACH, not report.
#   "Your mission is France 2027" is a report; a Chief of Staff connects current context →
#   strategic mission → the current decision, using the ONE brain's value-ranked
#   priority_action. When what matters most right now is NOT the mission (a health
#   obligation, the evening), Beth says so and tells the user WHEN to push the mission.
# ==============================================================================
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.chatgpt_cos.lanes import _strategic_summary

User = get_user_model()
_INTERPRET = "apps.ai.chatgpt_cos.executive_interpretation.interpret"
_GDS = "apps.ai.cos_services.get_domain_state"
_MISSION = "apps.purpose.mission_selection.select_active_mission_goal"

_STATE = {"state": {"mission": {"title": "France 2027", "current_focus": "Goal Weight 279.9"},
                    "active_titles": ["France 2027", "Relationship with God"],
                    "active_goal_count": 4}}


def _sig(priority_action):
    class S:
        strategic_focus = "France 2027"
        highest_leverage = "moving France 2027 forward"
    s = S()
    s.priority_action = priority_action
    return s


class GoalsCoachingTests(TestCase):
    def setUp(self):
        self.u = User.objects.create_user(email="coach@x.com", password="x")

    def test_health_obligation_coaches_deferral_of_the_mission(self):
        pa = {"kind": "health_obligation", "text": "Metformin",
              "why": "a prescription still due today"}
        with mock.patch(_INTERPRET, return_value=_sig(pa)), \
             mock.patch(_GDS, return_value=_STATE), \
             mock.patch(_MISSION, return_value=None):
            ans = _strategic_summary(self.u).lower()
        self.assertIn("france 2027", ans)                 # the mission is named
        self.assertIn("metformin", ans)                   # what matters NOW
        self.assertIn("right now", ans)                   # connects the current context
        # NOT the reflexive "advance the mission" report
        self.assertNotIn("advancing your current milestone", ans)

    def test_strategic_top_move_names_the_concrete_milestone(self):
        pa = {"kind": "strategic", "text": "moving France 2027 forward",
              "why": "foundational to your mission"}
        with mock.patch(_INTERPRET, return_value=_sig(pa)), \
             mock.patch(_GDS, return_value=_STATE), \
             mock.patch(_MISSION, return_value=None):
            ans = _strategic_summary(self.u).lower()
        self.assertIn("goal weight 279.9", ans)           # the concrete milestone, when it IS the move
        self.assertIn("france 2027", ans)
