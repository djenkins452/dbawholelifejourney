"""Proactive strategic health-trend interventions — Capability 6 (2026-06-21).

Beth proactively intervenes when a health trend turns (goal slipping, weight
stalling/reversing, a recommendation failing, or a win) — reusing the unified
CoS standing read. In-app + DNE delivery (no push device required); strategic,
not spam (None when nothing meaningful turned).
"""
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.proactive_checkins import (
    get_proactive_service, generate_health_trend_check_ins_for_user)

User = get_user_model()


def _user(email):
    u = User.objects.create_user(email=email, password="x" * 20)
    from apps.users.models import TermsAcceptance
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class MessageSelection(TestCase):
    def setUp(self):
        self.svc = get_proactive_service(_user("trend@test.com"))

    def test_target_passed(self):
        m = self.svc._select_health_trend_message(
            {"goal_pace": {"target_date": "2026-06-13", "remaining": 58.3,
                           "current_pace_lb_wk": 0.88, "target_passed": True}})
        self.assertIn("target date", m)
        self.assertIn("passed", m)

    def test_behind_pace(self):
        m = self.svc._select_health_trend_message(
            {"goal_pace": {"target_date": "2026-12-01", "current_pace_lb_wk": 0.5,
                           "required_pace_lb_wk": 2.1, "on_pace": False}})
        self.assertIn("slipping", m)

    def test_stalled(self):
        m = self.svc._select_health_trend_message(
            {"goal_pace": {"current_pace_lb_wk": -0.2}})
        self.assertIn("stalled", m)

    def test_recommendation_not_working(self):
        m = self.svc._select_health_trend_message(
            {"recommendation_effectiveness": "it hasn't moved — time for a "
             "different approach."})
        self.assertIn("rethink", m.lower())

    def test_win(self):
        m = self.svc._select_health_trend_message(
            {"recommendation_effectiveness": "now 298.3 lb. This appears to be "
             "working."})
        self.assertIn("positive", m.lower())

    def test_nothing_turned_is_silent(self):
        self.assertIsNone(self.svc._select_health_trend_message(
            {"goal_pace": {"current_pace_lb_wk": 1.5, "on_pace": True}}))
        self.assertIsNone(self.svc._select_health_trend_message({}))
        self.assertIsNone(self.svc._select_health_trend_message(None))


class GenerationGating(TestCase):
    def setUp(self):
        self.user = _user("trendgen@test.com")
        self.svc = get_proactive_service(self.user)

    def test_throttled_returns_none(self):
        with patch.object(self.svc.throttler, "can_send", return_value=False):
            self.assertIsNone(self.svc.generate_health_trend_check_in())

    def test_no_condition_returns_none(self):
        with patch.object(self.svc.throttler, "can_send", return_value=True), \
             patch("apps.ai.cos_intelligence.build_cos_intelligence",
                   return_value={"goal_pace": {"on_pace": True,
                                               "current_pace_lb_wk": 2.0}}):
            self.assertIsNone(self.svc.generate_health_trend_check_in())

    def test_condition_creates_message(self):
        sentinel = object()
        with patch.object(self.svc.throttler, "can_send", return_value=True), \
             patch("apps.ai.cos_intelligence.build_cos_intelligence",
                   return_value={"goal_pace": {"target_date": "2026-06-13",
                                 "remaining": 58.3, "current_pace_lb_wk": 0.88,
                                 "target_passed": True}}), \
             patch.object(self.svc, "_create_proactive_message",
                          return_value=sentinel) as mock_create:
            out = self.svc.generate_health_trend_check_in()
        self.assertIs(out, sentinel)
        kwargs = mock_create.call_args.kwargs
        self.assertIn("target date", kwargs["content"])
        self.assertEqual(kwargs["metadata"]["check_in_type"], "health_trend")

    def test_respects_proactive_switch_off(self):
        self.user.preferences.assistant_proactive_checkins = False
        self.user.preferences.save()
        self.assertIsNone(
            generate_health_trend_check_ins_for_user(self.user))


class Registration(TestCase):
    def test_registered_in_scheduler(self):
        from apps.core.ai_scheduler.scheduler_registry import get_registered_tasks
        tasks = get_registered_tasks()
        self.assertIn("generate_health_trend_check_ins", tasks)
        self.assertIn("run_health_trend_check_ins",
                      tasks["generate_health_trend_check_ins"]["function_path"])

    def test_runner_callable(self):
        from apps.core.ai_scheduler.scheduler_runner import run_health_trend_check_ins
        result = run_health_trend_check_ins()
        self.assertIn("users_processed", result)
