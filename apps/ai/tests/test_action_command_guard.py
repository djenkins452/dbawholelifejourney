# ==============================================================================
# File: apps/ai/tests/test_action_command_guard.py
# Description: LAYER-2 ACTION-COMMAND GUARD. The subject-keyword retrieval lanes
#   (workout_history / sleep_history / weight_history) match a bare domain word
#   ("workout", "sleep", "weight") and used to hijack ACTION commands that merely name
#   the subject — production: "I want to move my workout to 5pm today only" → answered
#   "I don't see a completed workout today" by workout_history, so the reschedule command
#   never reached the action/tool path. The guard makes those lanes decline commands
#   (move/reschedule/skip/cancel/set/…) while still answering true history QUESTIONS.
# ==============================================================================
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase

from apps.ai.chatgpt_cos.date_reference import is_action_command
from apps.users.models import TermsAcceptance

User = get_user_model()
_C = "apps.ai.services.ai_service._call_api"
_CT = "apps.ai.services.ai_service._call_api_with_tools"


def _mkuser(email):
    u = User.objects.create_user(email=email, password="x")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class ActionCommandDetectorTests(SimpleTestCase):
    def test_commands_are_actions(self):
        for m in ("I want to move my workout to 5pm today only.",
                  "reschedule my workout to 5pm", "shift my workout to noon",
                  "change my workout time to 6", "skip my workout today",
                  "cancel my workout", "set my weight to 180", "log my weight at 180",
                  "defer the workout", "complete my workout"):
            self.assertTrue(is_action_command(m), m)

    def test_questions_are_not_actions(self):
        for m in ("did you see my workout?", "did I complete my workout today?",
                  "how much did I lift?", "what did I sleep on 7/1?",
                  "what was my weight on July 1?", "when did I move it?",
                  "how long was my workout?", "is my weight down?"):
            self.assertFalse(is_action_command(m), m)


class LaneDeclineTests(TestCase):
    def setUp(self):
        self.u = _mkuser("guard@test.com")

    def test_workout_history_declines_command_answers_question(self):
        from apps.ai.chatgpt_cos import workout_history
        # Command → declines (lets the reschedule path own it).
        self.assertIsNone(
            workout_history.answer(self.u, "I want to move my workout to 5pm today only."))
        # True history question → still answered (no data → honest "don't see" dict).
        res = workout_history.answer(self.u, "did you see my workout?")
        self.assertIsNotNone(res)
        self.assertEqual(res.get("lane"), "workout_history")

    def test_sleep_and_weight_lanes_decline_commands(self):
        from apps.ai.chatgpt_cos import sleep_history, weight_history
        self.assertIsNone(weight_history.answer(self.u, "log my weight at 180"))
        self.assertIsNone(weight_history.answer(self.u, "set my weight to 180"))
        self.assertIsNone(sleep_history.answer(self.u, "skip my workout and move sleep"))
        # A true historical weight question is NOT blocked by the guard (guard=False);
        # it may still return None for lack of data, but it's not command-declined.
        self.assertFalse(is_action_command("what was my weight on 7/1?"))
        self.assertFalse(is_action_command("what did I sleep on 7/1?"))


class RoutingTests(TestCase):
    def setUp(self):
        from apps.ai.models import AssistantConversation
        self.u = _mkuser("route@test.com")
        self.conv = AssistantConversation.objects.create(user=self.u, is_active=True)

    def test_reschedule_command_not_owned_by_history_lane(self):
        from apps.ai.chatgpt_cos.lanes import route_message
        from apps.ai.models import AssistantMessage
        msg = "I want to move my workout to 5pm today only."
        AssistantMessage.objects.create(conversation=self.conv, role="user", content=msg)
        with mock.patch(_C, side_effect=RuntimeError("no llm")), \
             mock.patch(_CT, side_effect=RuntimeError("no tools")):
            res = route_message(self.u, msg, self.conv)
        # The turn must NOT be answered by a keyword history lane; it falls through so the
        # action/tool path (reschedule) owns it (route_message returns None → tool loop).
        if res is not None:
            self.assertNotIn(res.get("lane"),
                             ("workout_history", "sleep_history", "weight_history"))
            self.assertNotIn("completed workout", (res.get("answer") or "").lower())
