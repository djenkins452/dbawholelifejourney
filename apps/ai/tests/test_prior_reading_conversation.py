# ==============================================================================
# File: apps/ai/tests/test_prior_reading_conversation.py
# Description: Evidence Integrity + Provenance + Prior-Reading Truth — validated on
#   the REAL routed conversation path (route_message), not just units. The exact
#   production flow that exposed the gaps:
#     current glucose → previous glucose → what time recorded → impossible-timestamp
#     challenge → where did it come from.
#   Contract: current and previous are DISTINCT and earlier-in-time; a follow-up
#   timestamp refers to the REFERENCED (previous) reading; provenance answers the
#   SOURCE (not the value); an impossible timestamp triggers investigation; and
#   "only one reading" is stated plainly — current is NEVER substituted for previous.
# ==============================================================================
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.ai.models import AssistantConversation
from apps.ai.chatgpt_cos.lanes import route_message
from apps.health.models import GlucoseEntry

User = get_user_model()


class PriorReadingConversationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="prior@test.com", password="x")
        p = self.user.preferences
        p.timezone = "UTC"
        p.save()
        self.conv = AssistantConversation.objects.create(user=self.user)
        self.now = timezone.now()

    def _glucose(self, value, minutes_ago, source="dexcom"):
        return GlucoseEntry.objects.create(
            user=self.user, value=value, unit="mg/dL", context="random",
            source=source, recorded_at=self.now - timedelta(minutes=minutes_ago))

    def _say(self, message):
        return route_message(self.user, message, self.conv)

    # ── previous is DISTINCT from current and earlier in time ──────────────────
    def test_previous_glucose_is_distinct_from_current(self):
        self._glucose(113, minutes_ago=15)     # current
        self._glucose(122, minutes_ago=90)     # previous (earlier, different value)
        out = self._say("What was the previous glucose reading?")
        self.assertIsNotNone(out)
        ans = out["answer"].lower()
        self.assertIn("122", ans)                       # the PREVIOUS value
        self.assertIn("previous", ans)
        self.assertNotIn("your last glucose reading was 113", ans)  # not current-as-previous
        # continuity: the previous reading is now the active referenced fact
        from apps.ai.chatgpt_cos.conversation_memory import get_last_answer
        last = get_last_answer(self.conv)
        self.assertEqual(last["fact"]["value"], 122)
        self.assertEqual(last["fact_key"], "previous_glucose_reading")

    # ── the timestamp follow-up refers to the PREVIOUS reading ─────────────────
    def test_timestamp_followup_refers_to_previous_reading(self):
        self._glucose(113, minutes_ago=15)
        self._glucose(122, minutes_ago=90)
        self._say("What was the previous glucose reading?")
        out = self._say("What time was it recorded?")
        self.assertIsNotNone(out)
        ans = out["answer"].lower()
        self.assertIn("recorded", ans)
        self.assertNotIn("doesn't add up", ans)         # valid time, no false alarm
        # It renders the PREVIOUS reading's time, not the current one's.
        from apps.core.truth.render import render_datetime
        prev_when = render_datetime(self.user,
                                    (self.now - timedelta(minutes=90)).isoformat())
        cur_when = render_datetime(self.user,
                                   (self.now - timedelta(minutes=15)).isoformat())
        self.assertIn(prev_when.lower().split(" at ")[-1], ans)
        self.assertNotIn(cur_when.lower().split(" at ")[-1], ans)

    # ── provenance answers the SOURCE, never restates the value ────────────────
    def test_provenance_answers_source_not_value(self):
        self._glucose(113, minutes_ago=15)
        self._glucose(122, minutes_ago=90)
        self._say("What was the previous glucose reading?")
        out = self._say("Where did that come from?")
        self.assertIsNotNone(out)
        ans = out["answer"].lower()
        self.assertIn("dexcom", ans)                    # the SOURCE
        self.assertFalse(ans.strip().startswith("your previous glucose reading was"))

    # ── only one reading → say so; NEVER substitute current for previous ───────
    def test_only_one_reading_says_so(self):
        self._glucose(113, minutes_ago=15)              # the only reading
        out = self._say("What was the previous glucose reading?")
        self.assertIsNotNone(out)
        ans = out["answer"].lower()
        self.assertIn("one glucose reading", ans)
        self.assertIn("only", ans)
        self.assertNotIn("113", ans)                    # current NOT presented as previous

    # ── impossible timestamp → investigation, not a confident/generic answer ───
    def test_impossible_timestamp_challenge_investigates(self):
        from apps.core.truth import integrity as _integrity
        from apps.ai.chatgpt_cos.conversation_memory import record_last_answer
        # Beth just presented a reading whose timestamp is in the future (sync artifact).
        fact = {"value": 113, "unit": "mg/dL",
                "recorded_at": (self.now + timedelta(hours=1)).isoformat(),
                "provenance": "your Dexcom CGM", "presented_as": "current"}
        _integrity.attach(fact)                          # real composition → integrity fails
        self.assertTrue(_integrity.failed(fact))
        record_last_answer(self.conv, "foundational_facts",
                           {"answer": "Your glucose is 113.",
                            "fact_key": "last_glucose_reading", "fact": fact})
        out = self._say("That's impossible because it's still 10:11 AM.")
        self.assertIsNotNone(out)                        # NOT a generic failure / None
        ans = out["answer"].lower()
        self.assertIn("doesn't add up", ans)             # investigation
        self.assertEqual(out["lane"], "trust_verification")
