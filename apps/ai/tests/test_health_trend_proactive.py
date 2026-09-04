"""Proactive health-trend interventions — Capability 6 (2026-06-21).

REWRITTEN 2026-09-04. The selection half of this file certified an if-ladder that ranked
signals and wrote the sentence — WLJ doing two of the model's jobs deterministically, and
the reason one goal-pace calculation crossing one line became an unprompted notification.
That ladder is gone. WLJ now throttles, detects, and hands the FACTS to the authoring
model, which decides whether any of it is worth interrupting the person and may decline.

What is still certified here is WLJ's half: the detection and the delivery gating. The
decision half lives in `apps/core/tests/test_proactive_autonomy_contract.py`.
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


class SignalDetection(TestCase):
    """WLJ detects and hands over facts. It no longer picks or phrases anything."""

    def setUp(self):
        self.svc = get_proactive_service(_user("trend@test.com"))

    def _signals(self, intel):
        from apps.ai.proactive_checkins import _detected_signals
        return _detected_signals(intel)

    def test_a_pace_signal_is_handed_over_as_facts(self):
        out = self._signals(
            {"goal_pace": {"target_date": "2026-12-01", "current_pace_lb_wk": 0.5,
                           "required_pace_lb_wk": 2.1, "on_pace": False}})
        self.assertEqual(out["goal_pace"]["required_pace_lb_wk"], 2.1)
        self.assertIs(out["goal_pace"]["on_pace"], False)

    def test_an_effectiveness_signal_is_handed_over_verbatim(self):
        out = self._signals(
            {"recommendation_effectiveness": "it hasn't moved — time for a "
             "different approach."})
        self.assertIn("different approach", out["recommendation_effectiveness"])

    def test_nothing_detected_is_silent(self):
        for empty in ({}, None):
            self.assertEqual(self._signals(empty), {})

    def test_wlj_no_longer_composes_the_intervention(self):
        self.assertFalse(hasattr(self.svc, "_select_health_trend_message"))

    def test_an_on_pace_reading_is_still_a_signal_the_model_may_ignore(self):
        """WLJ deliberately does NOT decide that "on pace" is uninteresting — that is a
        judgment. It hands the fact over; the model chooses silence if it does not matter.
        """
        out = self._signals({"goal_pace": {"current_pace_lb_wk": 1.5, "on_pace": True}})
        self.assertIs(out["goal_pace"]["on_pace"], True)


class GenerationGating(TestCase):
    def setUp(self):
        self.user = _user("trendgen@test.com")
        self.svc = get_proactive_service(self.user)

    def test_throttled_returns_none(self):
        with patch.object(self.svc.throttler, "can_send", return_value=False):
            self.assertIsNone(self.svc.generate_health_trend_check_in())

    def test_nothing_detected_returns_none(self):
        with patch.object(self.svc.throttler, "can_send", return_value=True), \
             patch("apps.ai.cos_intelligence.build_cos_intelligence",
                   return_value={}), \
             patch("apps.ai.checkin_author.author_checkin") as author:
            self.assertIsNone(self.svc.generate_health_trend_check_in())
        author.assert_not_called()

    def test_the_model_declining_returns_none(self):
        """A detected signal is a candidate, not a decision. WLJ used to send whatever
        crossed a line; it now asks, and takes no for an answer."""
        with patch.object(self.svc.throttler, "can_send", return_value=True), \
             patch("apps.ai.cos_intelligence.build_cos_intelligence",
                   return_value={"goal_pace": {"on_pace": True,
                                               "current_pace_lb_wk": 2.0}}), \
             patch("apps.ai.checkin_author.author_checkin", return_value=""):
            self.assertIsNone(self.svc.generate_health_trend_check_in())

    def test_condition_creates_message(self):
        sentinel = object()
        with patch.object(self.svc.throttler, "can_send", return_value=True), \
             patch("apps.ai.cos_intelligence.build_cos_intelligence",
                   return_value={"goal_pace": {"target_date": "2026-06-13",
                                 "remaining": 58.3, "current_pace_lb_wk": 0.88,
                                 "target_passed": True}}), \
             patch("apps.ai.checkin_author.author_checkin",
                   return_value="Your target date has passed."), \
             patch.object(self.svc, "_create_proactive_message",
                          return_value=sentinel) as mock_create:
            out = self.svc.generate_health_trend_check_in()
        self.assertIs(out, sentinel)
        kwargs = mock_create.call_args.kwargs
        self.assertEqual(kwargs["content"], "Your target date has passed.")
        self.assertEqual(kwargs["metadata"]["check_in_type"], "health_trend")

    def test_the_signals_actually_reach_the_author(self):
        with patch.object(self.svc.throttler, "can_send", return_value=True), \
             patch("apps.ai.cos_intelligence.build_cos_intelligence",
                   return_value={"goal_pace": {"target_passed": True}}), \
             patch("apps.ai.checkin_author.author_checkin",
                   return_value="msg") as author, \
             patch.object(self.svc, "_create_proactive_message"):
            self.svc.generate_health_trend_check_in()
        self.assertEqual(author.call_args.kwargs["signals"],
                         {"goal_pace": {"target_passed": True}})

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
