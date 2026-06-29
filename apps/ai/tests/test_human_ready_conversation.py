# ==============================================================================
# File: apps/ai/tests/test_human_ready_conversation.py
# Description: Human-Ready Conversation Layer. User-preference rendering, complete
#   glucose fact, active-topic follow-ups (time/concern/meaning/currency) answered
#   deterministically from the SAME fact, no internal leakage, dangerous-value safety.
#   Origin: real Beth conversation. No OpenAI (LLM forced off).
# ==============================================================================
from datetime import datetime, timedelta, timezone as _tz
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.ai.models import AssistantConversation
from apps.ai.chatgpt_cos.foundational_facts import answer_foundational_fact
from apps.ai.chatgpt_cos.conversation_memory import record_last_answer
from apps.ai.chatgpt_cos.lanes import _why_explainer_lane
from apps.core.truth import render as R

User = get_user_model()
_GMS = "apps.core.ai_state.state_engine.get_module_state"
_CALL = "apps.ai.services.ai_service._call_api"
_LEAKS = ("sae", "recorded_at", "last_glucose_entry", "last_food_entry", "logged meal entry",
          "module state", "foundational", "iso", "utc", "field")


class RenderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="rend@test.com", password="x")
        self.user.preferences.timezone = "America/New_York"
        self.user.preferences.save()

    def test_date_is_mm_dd_yyyy(self):
        self.assertEqual(R.render_date(self.user, "2026-06-28"), "06/28/2026")

    def test_time_is_12_hour_in_user_tz(self):
        # 18:05 UTC -> 2:05 PM Eastern (EDT)
        self.assertEqual(R.render_time(self.user, "2026-06-28T18:05:00+00:00"), "2:05 PM")

    def test_datetime_combines_both(self):
        self.assertEqual(R.render_datetime(self.user, "2026-06-28T18:05:00+00:00"),
                         "06/28/2026 at 2:05 PM")

    def test_no_iso_or_24h_leak(self):
        out = R.render_datetime(self.user, "2026-06-28T18:05:00+00:00")
        self.assertNotIn("T", out)
        self.assertNotIn("+00:00", out)


class GlucoseConversationTests(TestCase):
    """The full real conversation, on one glucose topic, deterministic + user-ready."""

    def setUp(self):
        self.user = User.objects.create_user(email="gconv@test.com", password="x")
        self.user.preferences.timezone = "America/New_York"
        self.user.preferences.save()
        self.conv = AssistantConversation.objects.create(user=self.user)
        ts = (timezone.now() - timedelta(hours=2)).isoformat()
        self.state = {"latest_glucose": 43, "latest_glucose_unit": "mg/dL",
                      "last_glucose_entry": ts}

    def _ask_glucose(self):
        with mock.patch(_CALL, return_value=None), mock.patch(_GMS, return_value=self.state):
            r = answer_foundational_fact(self.user, "How is my glucose doing today?")
        record_last_answer(self.conv, "foundational_facts", r)
        self.conv.refresh_from_db()
        return r["answer"]

    def _follow(self, q):
        out = _why_explainer_lane(self.user, q, self.conv)
        self.assertIsNotNone(out, f"follow-up lost: {q}")
        self.assertEqual(out["fast_path"], "conversation_memory")   # deterministic
        return out["answer"]

    def test_full_conversation_stays_on_glucose_and_is_user_ready(self):
        g = self._ask_glucose()
        self.assertIn("43", g)
        self.assertIn("very low", g.lower())
        for bad in ("good range", "healthy range", "in range"):
            self.assertNotIn(bad, g.lower())

        when = self._follow("At what time?")
        self.assertIn("/", when)                       # MM/DD/YYYY
        self.assertIn("M", when)                       # AM/PM
        self.assertNotIn("T", when.replace("That", ""))  # no ISO 'T'

        why = self._follow("Why is that reading important?")
        self.assertNotIn("because your data", why.lower())
        self.assertIn("low", why.lower())

        concern = self._follow("Should I be concerned?")
        self.assertIn("yes", concern.lower())          # never reassures a danger
        self.assertNotIn("healthy", concern.lower())

        current = self._follow("Is that current?")
        self.assertIn("ago", current.lower())          # rendered recency

        for ans in (when, why, concern, current):
            low = ans.lower()
            for leak in _LEAKS:
                self.assertNotIn(leak, low, f"leak {leak!r} in: {ans}")

    def test_concern_never_reassures_on_danger(self):
        self._ask_glucose()
        concern = self._follow("Is that good?")
        self.assertNotIn("yes", concern.lower()[:6])   # not "Yes, that's good"
        self.assertIn("dangerously low", concern.lower())
