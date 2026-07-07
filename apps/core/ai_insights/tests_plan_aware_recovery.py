"""
Plan-aware recovery reasoning (Phase 2 CoS production-readiness).

The OvertrainingRiskRule must coach WITHIN the user's intentional training program —
a high workout count that matches a structured plan with a built-in recovery day is the
PLAN, not overtraining. It should protect sleep, not recommend another rest day. Only a
genuinely unstructured / excess load keeps the raw "consider a rest day" framing.
"""
import datetime
from unittest.mock import patch

from django.test import TestCase

from apps.core.ai_insights.rules_cross_domain import OvertrainingRiskRule
from apps.users.models import User

_READ_PLAN = "apps.health.services.training_plan.read_training_plan"
_ON_PLAN = {"has_plan": True, "has_recovery_day": True, "days_per_week": 6,
            "alternates": True, "today_is_rest": False, "today_type": "Bike Ride",
            "tomorrow_type": "Strength Day"}
_NO_PLAN = {"has_plan": False, "has_recovery_day": False, "days_per_week": 0,
            "alternates": False, "today_is_rest": False, "today_type": None,
            "tomorrow_type": None}


class OvertrainingPlanAwarenessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="ot@test.com", password="x")
        self.event = {
            "event_type": "scheduled_check", "module": "core",
            "user_state": {
                "health": {"enabled": True, "sleep_avg_hours_7d": 5.7,
                           "sleep_trend": "decreasing"},
                "fitness": {"workouts_7d": 5},
            },
        }

    def test_on_plan_reframes_to_protect_sleep_not_rest_day(self):
        with patch(_READ_PLAN, return_value=_ON_PLAN):
            out = OvertrainingRiskRule().evaluate(self.user, self.event)
        self.assertEqual(len(out), 1)
        ins = out[0]
        self.assertIn("protect tonight's sleep", ins["title"].lower())
        self.assertIn("on plan", ins["message"].lower())
        # Never casually recommends changing the intentional program.
        self.assertNotIn("consider a rest day", ins["message"].lower())
        self.assertNotIn("overtraining", ins["title"].lower())
        self.assertTrue(ins["evidence"]["on_plan_with_recovery"])

    def test_no_plan_keeps_the_overtraining_framing(self):
        with patch(_READ_PLAN, return_value=_NO_PLAN):
            out = OvertrainingRiskRule().evaluate(self.user, self.event)
        self.assertEqual(len(out), 1)
        ins = out[0]
        self.assertIn("overtraining", ins["title"].lower())
        self.assertIn("rest day or lighter session", ins["message"].lower())
        self.assertFalse(ins["evidence"]["on_plan_with_recovery"])

    def test_volume_exceeding_the_plan_is_still_overtraining(self):
        # 8 workouts against a 6-day plan → genuinely over the program.
        self.event["user_state"]["fitness"]["workouts_7d"] = 8
        with patch(_READ_PLAN, return_value=_ON_PLAN):
            out = OvertrainingRiskRule().evaluate(self.user, self.event)
        self.assertIn("overtraining", out[0]["title"].lower())

    def test_plan_without_a_recovery_day_is_not_reframed(self):
        no_rest = {**_ON_PLAN, "has_recovery_day": False}
        with patch(_READ_PLAN, return_value=no_rest):
            out = OvertrainingRiskRule().evaluate(self.user, self.event)
        self.assertIn("overtraining", out[0]["title"].lower())


class TrainingPlanReaderTests(TestCase):
    def setUp(self):
        from apps.health.models import WorkoutPlan, WorkoutSchedule, WorkoutTemplate
        self.user = User.objects.create_user(email="tpr@test.com", password="x")
        self.plan = WorkoutPlan.objects.create(
            user=self.user, name="6-day split", is_active=True, days_per_week=6)
        strength = WorkoutTemplate.objects.create(user=self.user, name="Strength Day")
        cardio = WorkoutTemplate.objects.create(user=self.user, name="Bike Ride")
        for d in range(6):                       # Mon–Sat, alternating
            WorkoutSchedule.objects.create(
                plan=self.plan, day_of_week=d,
                template=(strength if d % 2 == 0 else cardio))
        WorkoutSchedule.objects.create(          # Sunday: built-in recovery
            plan=self.plan, day_of_week=6, template=strength, is_rest_day=True)

    def test_reads_structure_recovery_day_and_alternation(self):
        from apps.health.services.training_plan import read_training_plan
        tp = read_training_plan(self.user, today=datetime.date(2026, 7, 7))  # Tuesday
        self.assertTrue(tp["has_plan"])
        self.assertTrue(tp["has_recovery_day"])
        self.assertEqual(tp["days_per_week"], 6)
        self.assertTrue(tp["alternates"])
        self.assertEqual(tp["today_type"], "Bike Ride")

    def test_sunday_is_a_planned_rest_day(self):
        from apps.health.services.training_plan import read_training_plan
        tp = read_training_plan(self.user, today=datetime.date(2026, 7, 12))  # Sunday
        self.assertTrue(tp["today_is_rest"])

    def test_no_plan_returns_blank(self):
        from apps.health.services.training_plan import read_training_plan
        other = User.objects.create_user(email="noplan@test.com", password="x")
        tp = read_training_plan(other)
        self.assertFalse(tp["has_plan"])
        self.assertFalse(tp["has_recovery_day"])
