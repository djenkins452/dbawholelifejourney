# ==============================================================================
# File: apps/ai/tests/test_action_promotion.py
# Description: ACTION PROMOTION (command/query separation, authoritative). When the
#   Conductor classifies speech_act=action, it DECLINES the lane loop and hands the turn to
#   the tool/action path — so an executive command reaches the action path instead of being
#   hijacked by a retrieval (workout_history) or reasoning (personal_reasoning) lane. Strictly
#   an ownership promotion (no handler/tool/truth change). Retrieval and reasoning turns are
#   NOT promoted — they still route through the lanes.
# ==============================================================================
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.chatgpt_cos.classifier import classify
from apps.users.models import TermsAcceptance

User = get_user_model()
_C = "apps.ai.services.ai_service._call_api"
_CT = "apps.ai.services.ai_service._call_api_with_tools"
_ACTION_MSG = "I want to move my workout to 5pm today only."


def _mkuser(email):
    u = User.objects.create_user(email=email, password="x")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class ActionPromotionTests(TestCase):
    def setUp(self):
        from apps.ai.models import AssistantConversation
        self.u = _mkuser("promote@test.com")
        self.conv = AssistantConversation.objects.create(user=self.u, is_active=True)

    def _route(self, msg):
        from apps.ai.chatgpt_cos.lanes import route_message
        from apps.ai.models import AssistantMessage
        AssistantMessage.objects.create(conversation=self.conv, role="user", content=msg)
        with mock.patch(_C, side_effect=RuntimeError("no llm")), \
             mock.patch(_CT, side_effect=RuntimeError("no tools")):
            return route_message(self.u, msg, self.conv)

    def test_action_command_reaches_action_path_not_a_lane(self):
        # (1) classifies as action; (2)+(3)+(4) route_message declines the lane loop →
        # returns None → the caller's tool/action path (reschedule) owns the turn. No lane
        # result means neither workout_history nor personal_reasoning owned it.
        self.assertEqual(classify(_ACTION_MSG).speech_act, "action")
        res = self._route(_ACTION_MSG)
        self.assertIsNone(
            res, f"action command was owned by a lane: {res and res.get('lane')}")

    def test_workout_history_would_have_owned_without_promotion(self):
        # Guard proof: the bare-word retrieval lane still MATCHES "workout" — it is the
        # promotion (not the lane) that keeps it from owning the command.
        from apps.ai.chatgpt_cos import workout_history
        # As a history QUESTION it still answers…
        self.assertIsNotNone(workout_history.answer(self.u, "did you see my workout?"))
        # …and the action command routes past it (None ⇒ action path).
        self.assertIsNone(self._route(_ACTION_MSG))

    def test_retrieval_question_still_routes_to_its_lane(self):
        # (5) a genuine retrieval is NOT promoted; it still routes to the history lane.
        self.assertEqual(classify("did you see my workout?").speech_act, "retrieval")
        res = self._route("did you see my workout?")
        self.assertIsNotNone(res)
        self.assertEqual(res.get("lane"), "workout_history")

    def test_reasoning_message_not_promoted_as_action(self):
        # (6) a reasoning-mode message is NOT classified action (so never action-promoted).
        c = classify("I'm having a hard time breaking the 289 mark")
        self.assertNotEqual(c.speech_act, "action")
        self.assertEqual(c.speech_act, "reasoning_mode")

    def test_framed_and_imperative_commands_both_reach_action_path(self):
        for m in ("move my workout to 5pm",
                  "reschedule my workout to 5pm",
                  "can you move my workout to 5pm",
                  "cancel my 3pm meeting"):
            self.assertEqual(classify(m).speech_act, "action", m)
            self.assertIsNone(self._route(m), m)
