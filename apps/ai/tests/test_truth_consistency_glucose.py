# ==============================================================================
# File: apps/ai/tests/test_truth_consistency_glucose.py
# Description: Truth Consistency — the glucose VALUE answer and the "At what time?"
#   follow-up must originate from the SAME deterministic struct and never contradict.
#   Root cause: the value answer was LLM-phrased and could assert claims ("time is
#   unconfirmed") NOT in the struct, while the follow-up read the struct. Fix: a fact
#   with a timestamp/clinical interpretation is answered deterministically (LLM
#   bypassed). The test injects a ROGUE LLM to prove the bypass. No mocked agreement.
# ==============================================================================
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.ai.models import AssistantConversation
from apps.ai.chatgpt_cos.foundational_facts import answer_foundational_fact
from apps.ai.chatgpt_cos.conversation_memory import record_last_answer
from apps.ai.chatgpt_cos.lanes import _why_explainer_lane

User = get_user_model()
_GMS = "apps.core.ai_state.state_engine.get_module_state"
_CALL = "apps.ai.services.ai_service._call_api"
_ROGUE = "91 mg/dL, but the reading's time is unconfirmed."   # the LLM's bad claim


class GlucoseTimeConsistencyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="tc@test.com", password="x")
        self.user.preferences.timezone = "America/New_York"
        self.user.preferences.save()

    def _value_then_time(self, ts):
        conv = AssistantConversation.objects.create(user=self.user)
        state = {"latest_glucose": 91, "latest_glucose_unit": "mg/dL",
                 "last_glucose_entry": ts}
        with mock.patch(_CALL, return_value=_ROGUE), mock.patch(_GMS, return_value=state):
            r = answer_foundational_fact(self.user, "What is my BG?")
        record_last_answer(conv, "foundational_facts", r)
        conv.refresh_from_db()
        follow = _why_explainer_lane(self.user, "At what time?", conv)
        return r["answer"], (follow or {}).get("answer")

    def test_valid_timestamp_value_answer_is_deterministic_and_agrees(self):
        value, when = self._value_then_time(
            (timezone.now() - timedelta(hours=2)).isoformat())
        # The rogue LLM "unconfirmed" must be BYPASSED — value answer is struct-backed.
        self.assertNotIn("unconfirmed", value.lower())
        self.assertIn("91", value)
        # The follow-up gives the real time; neither answer claims the other's opposite.
        self.assertIn("recorded on", when.lower())
        self.assertNotIn("unconfirmed", when.lower())

    def test_future_timestamp_both_say_unconfirmed(self):
        value, when = self._value_then_time(
            (timezone.now() + timedelta(hours=3)).isoformat())
        self.assertIn("future", value.lower())          # value answer flags it
        self.assertIn("future", when.lower())            # follow-up AGREES
        self.assertNotIn("recorded on", when.lower())    # never a concrete time

    def test_invariant_followup_never_contradicts_value(self):
        # The core invariant: if the value answer declares the time unavailable, the
        # follow-up must not return a time; if available, the follow-up returns it and
        # the value answer does NOT call it unavailable.
        for ts, future in (((timezone.now() - timedelta(hours=1)).isoformat(), False),
                           ((timezone.now() + timedelta(hours=2)).isoformat(), True)):
            value, when = self._value_then_time(ts)
            value_unavailable = "unconfirmed" in value.lower() or "future" in value.lower()
            when_unavailable = "unconfirmed" in when.lower() or "future" in when.lower()
            self.assertEqual(value_unavailable, when_unavailable,
                             f"contradiction: value={value!r} when={when!r}")
