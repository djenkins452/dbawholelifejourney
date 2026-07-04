# ==============================================================================
# File: apps/ai/tests/test_checkin_happy_path.py
# Description: WI-2 — the morning check-in HAPPY PATH must never fail. Greeting →
#   feeling → executive morning briefing. Origin: "I am feeling good. Rested actually.
#   I know 6.4 isn't my 7 hours, but 6.4 is good for me." → generic failure, because
#   the check-in reply classifier used a 14-word cap as a proxy for "feeling vs pivot"
#   and misread an ELABORATED feeling as a subject change (planner routed it away →
#   every lane declined → tool-loop generic failure). Length is not the test; whether
#   the reply OPENS with affect is.
# ==============================================================================
from datetime import datetime, timezone as _tz
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.ai.chatgpt_cos import conversation_planner as cp

User = get_user_model()
MORNING = datetime(2026, 7, 4, 7, 30, tzinfo=_tz.utc)

PROD = "I am feeling good. Rested actually. I know 6.4 isn't my 7 hours, but 6.4 is good for me."


class FeelingClassifierTests(SimpleTestCase):
    def test_the_production_elaborated_feeling_is_recognized(self):
        self.assertTrue(cp._is_plausible_feeling(PROD))

    def test_short_feelings_still_recognized(self):
        for m in ("I'm good", "feeling good, rested", "tired honestly", "pretty rough"):
            self.assertTrue(cp._is_plausible_feeling(m), m)

    def test_elaborated_feelings_of_any_length_recognized(self):
        for m in ("I'm feeling great today, honestly slept well and ready to go get after it",
                  "Rested, actually — better than I expected given how late I got to bed",
                  "Honestly pretty drained, didn't sleep much and the kids were up all night"):
            self.assertTrue(cp._is_plausible_feeling(m), m)

    def test_questions_and_new_subjects_are_pivots_not_feelings(self):
        # A pivot must abandon the check-in — never trapped as a feeling.
        for m in ("What's on my calendar today?",
                  "Actually can you add a task to email John about the Q3 report",
                  "Remind me to reschedule my 3pm meeting to tomorrow afternoon please",
                  "What did the Bible say about Jezebel again"):
            self.assertFalse(cp._is_plausible_feeling(m), m)


class CheckinHappyPathRoutingTests(TestCase):
    def setUp(self):
        from apps.ai.models import AssistantConversation
        self.user = User.objects.create_user(email="checkin@test.com", password="x")
        self.conv = AssistantConversation.objects.create(user=self.user)

    def test_greeting_then_elaborated_feeling_reaches_the_briefing(self):
        from apps.ai.chatgpt_cos.lanes import route_message
        with mock.patch("apps.core.utils.get_user_now", return_value=MORNING):
            r1 = route_message(self.user, "Good morning", self.conv)
            self.assertEqual(cp.read_state(self.conv).get("state"), "check_in")
            r2 = route_message(self.user, PROD, self.conv)
        # The happy path completes — NOT a generic failure (None).
        self.assertIsNotNone(r2, "check-in feeling reply fell through to a generic failure")
        self.assertEqual(r2["lane"], "conversation_brief")
        self.assertTrue(r2["answer"])

    def test_planner_routes_elaborated_feeling_to_brief(self):
        cp.write_state(self.conv, state="check_in", objective="emotional_checkin",
                       last_beth_act="checked_in")
        self.assertEqual(cp.plan(self.user, self.conv, PROD).get("handler"),
                         "brief_after_checkin")
