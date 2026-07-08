# ==============================================================================
# File: apps/ai/tests/test_action_speech_act_shadow.py
# Description: COMMAND/QUERY SEPARATION — the `action` speech act (Conductor Classifier,
#   SHADOW phase). `action` is the WRITE side the taxonomy was missing (retrieval is the
#   read side); a command was falling through `fallback` → the lane loop, where a
#   subject/reasoning lane hijacked it. This validates the classifier now labels commands
#   `action` — CONSERVATIVELY (precision ≫ recall, per the rollout mandate: a question is
#   NEVER an action) — and that this is shadow only (no routing change; only `meta` is
#   promoted).
# ==============================================================================
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase

from apps.ai.chatgpt_cos.classifier import classify
from apps.users.models import TermsAcceptance

User = get_user_model()

# Real executive commands (writes) — must classify as `action`.
COMMANDS = [
    "I want to move my workout to 5pm today only.",
    "reschedule my workout to 5pm",
    "move my workout to 5pm",
    "change my workout to 6",
    "cancel my 3pm meeting",
    "skip my workout today",
    "complete my workout",
    "add eggs to my grocery list",
    "delete that task",
    "remind me to call mom at 4",
    "push it an hour",
    "log my weight at 180",
    "set a reminder for 5pm",
    "please move my workout to 5pm",
    "can you reschedule my workout to 5pm",
    "bring my workout forward to noon",
]

# NOT commands — must NEVER classify as `action` (precision is the rollout requirement).
NOT_COMMANDS = [
    # questions that contain action verbs
    "did you see my workout?",
    "should I cancel my gym membership?",
    "what happens if I skip today?",
    "how do I add a task?",
    "when did I move it?",
    "did I complete my workout today?",
    # retrieval / history
    "what did I sleep on 7/1?",
    "what was my weight on July 1?",
    # narrative / statements (verb not a command)
    "I moved to a new house last week",
    "the change in my weight was 2 lbs",
    "change is hard",
    "my motivation is gone",
    # meta (about Beth's turn) — higher precedence, not an action
    "you let me slide on bike ride and journal",
]


class ActionPrecisionRecallTests(SimpleTestCase):
    def test_commands_classify_as_action(self):
        misses = [m for m in COMMANDS if classify(m).speech_act != "action"]
        self.assertEqual(misses, [], f"commands not classified action: {misses}")

    def test_non_commands_never_action(self):
        # Precision: a false positive would let the action path steal a genuine question.
        fps = [(m, classify(m).speech_act) for m in NOT_COMMANDS
               if classify(m).speech_act == "action"]
        self.assertEqual(fps, [], f"false-positive actions (must be zero): {fps}")

    def test_confidence_high_for_imperative_medium_for_framed(self):
        self.assertEqual(classify("move my workout to 5pm").confidence, "high")
        self.assertEqual(
            classify("can you move my workout to 5pm").confidence, "medium")


class ShadowNoOpTests(TestCase):
    """`action` is classified (logged) but NOT yet promoted — routing is unchanged; only
    `meta` short-circuits. Proves the shadow phase changes no behavior."""

    def setUp(self):
        from apps.ai.models import AssistantConversation
        u = User.objects.create_user(email="shadow@test.com", password="x")
        TermsAcceptance.objects.create(
            user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        u.preferences.has_completed_onboarding = True
        u.preferences.save()
        self.u = u
        self.conv = AssistantConversation.objects.create(user=u, is_active=True)

    def test_action_is_classified_but_not_routed(self):
        from apps.ai.chatgpt_cos.lanes import route_message
        from apps.ai.models import AssistantMessage
        msg = "I want to move my workout to 5pm today only."
        # Classifier sees it as an action…
        self.assertEqual(classify(msg).speech_act, "action")
        # …but nothing routes on `action` yet (no `action` lane/owner exists).
        AssistantMessage.objects.create(conversation=self.conv, role="user", content=msg)
        with mock.patch("apps.ai.services.ai_service._call_api",
                        side_effect=RuntimeError("no llm")), \
             mock.patch("apps.ai.services.ai_service._call_api_with_tools",
                        side_effect=RuntimeError("no tools")):
            res = route_message(self.u, msg, self.conv)
        if res is not None:
            self.assertNotEqual(res.get("lane"), "action")
