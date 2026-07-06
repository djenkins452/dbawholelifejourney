# ==============================================================================
# File: apps/ai/tests/test_health_teaching.py
# Description: HEALTH CHECK-IN teaches, not reports. Instead of a Weight/Sleep/Glucose
#   dashboard, a Chief of Staff explains the overall state, the one thing that needs
#   action now, and what's important-but-not-tonight — grounded in the ONE brain.
# ==============================================================================
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.chatgpt_cos.lanes import _health_overall_summary

User = get_user_model()
_INTERPRET = "apps.ai.chatgpt_cos.executive_interpretation.interpret"


def _sig(**kw):
    class S:
        pass
    s = S()
    s.health_read = kw.get("health_read", "stable")
    s.health_critical = kw.get("health_critical", [])
    s.priority_action = kw.get("priority_action", {})
    s.biggest_risk = kw.get("biggest_risk", "")
    return s


class HealthTeachingTests(TestCase):
    def setUp(self):
        self.u = User.objects.create_user(email="ht@x.com", password="x")

    def test_teaches_state_then_action_then_not_now(self):
        sig = _sig(health_read="stable",
                   priority_action={"kind": "health_obligation", "text": "Metformin",
                                    "why": "a prescription still due today"},
                   biggest_risk="muscle preservation as you keep losing weight")
        with mock.patch(_INTERPRET, return_value=sig):
            ans = _health_overall_summary(self.u).lower()
        self.assertIn("health is stable", ans)               # overall state
        self.assertIn("metformin", ans)                      # the one thing NOW
        self.assertIn("muscle preservation", ans)            # important, but not now
        self.assertNotIn("glucose", ans)                     # NOT a dashboard dump

    def test_nothing_urgent_is_honest(self):
        sig = _sig(health_read="improving", priority_action={"kind": "strategic"},
                   biggest_risk="")
        with mock.patch(_INTERPRET, return_value=sig):
            ans = _health_overall_summary(self.u).lower()
        self.assertIn("health is improving", ans)
        self.assertIn("nothing needs immediate action", ans)
