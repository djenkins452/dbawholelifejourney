# ==============================================================================
# File: apps/ai/tests/test_p31_conversation_planning.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: P31 Phase 1 — Executive Conversation Planning. MULTI-TURN scenario
#   coverage (real dialogue, not isolated intents), all deterministic with OpenAI
#   DISABLED: morning check-in first (no task dump), check-in -> adaptive briefing,
#   and conversation REPAIR on critique (no jump to unrelated facts). Validates
#   ACTUAL rendered responses + conversation STATE transitions.
# ==============================================================================
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase

from apps.ai.chatgpt_cos.lanes import route_message
from apps.ai.chatgpt_cos import acceptance_rules as ar
from apps.ai.chatgpt_cos import conversation_planner as cp

User = get_user_model()
_C = "apps.ai.services.ai_service._call_api"
_CT = "apps.ai.services.ai_service._call_api_with_tools"
_AGENDA_WORDS = ("coming up", "next up", "highest priority", "scheduled", "begin ",
                 "first up", "your agenda")


class ActClassifierTests(SimpleTestCase):
    def test_greeting_detection(self):
        for g in ("Good morning", "good morning Beth", "morning", "hey Beth", "hello"):
            self.assertTrue(cp.is_greeting(g), g)
        for n in ("what is my weight?", "how is my mission going?"):
            self.assertFalse(cp.is_greeting(n), n)

    def test_critique_detection(self):
        for c in ("Does that sound right to you?", "Are you sure?", "that was not first class",
                  "that doesn't sound right", "double check that", "really?"):
            self.assertTrue(cp.is_critique(c), c)
        for n in ("what should I do today?", "good morning"):
            self.assertFalse(cp.is_critique(n), n)


class _ConvMixin:
    def setUp(self):
        from apps.users.models import TermsAcceptance
        from apps.ai.models import AssistantConversation
        self.u = User.objects.create_user(email="p31@example.com", password="x")
        TermsAcceptance.objects.create(
            user=self.u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.u.preferences.has_completed_onboarding = True
        self.u.preferences.save()
        self.conv = AssistantConversation.objects.create(user=self.u, is_active=True)

    def _say(self, msg, beth_reply_role="assistant"):
        """Route one user turn with OpenAI DISABLED, persisting the turn pair so the
        planner sees real conversation history on the next turn."""
        from apps.ai.models import AssistantMessage
        AssistantMessage.objects.create(conversation=self.conv, role="user", content=msg)
        with mock.patch(_C, side_effect=RuntimeError("openai down")), \
             mock.patch(_CT, side_effect=RuntimeError("openai down")):
            res = route_message(self.u, msg, self.conv)
        if res:
            AssistantMessage.objects.create(conversation=self.conv, role="assistant",
                                            content=res.get("answer") or "")
        return res

    def _state(self):
        self.conv.refresh_from_db()
        return cp.read_state(self.conv)


class MorningCheckinScenarioTests(_ConvMixin, TestCase):
    def test_good_morning_checks_in_first_no_task_dump(self):
        res = self._say("Good morning")
        self.assertIsNotNone(res)
        self.assertEqual(res["lane"], "conversation_checkin")
        ans = res["answer"].lower()
        self.assertIn("danny", ans)                       # greets naturally
        self.assertIn("feel", ans)                        # asks how he's feeling
        self.assertFalse(ar.is_failure_message(ans))      # works with OpenAI disabled
        for w in _AGENDA_WORDS:                            # NO task/agenda dump
            self.assertNotIn(w, ans, f"check-in dumped the agenda ({w!r})")
        self.assertEqual(self._state().get("state"), "check_in")

    def test_checkin_response_then_briefs(self):
        self._say("Good morning")
        res = self._say("I'm okay, a bit tired")          # a feeling/state response
        self.assertIsNotNone(res)
        self.assertEqual(res["lane"], "conversation_brief")
        self.assertTrue(res["answer"].strip())
        self.assertFalse(ar.is_failure_message(res["answer"]))
        self.assertEqual(self._state().get("state"), "briefing")

    def test_adaptive_to_negative_feeling(self):
        self._say("Good morning")
        res = self._say("honestly exhausted and stressed")
        low = res["answer"].lower()
        # P32: low energy -> executive recovery framing, not a task dump
        self.assertTrue("recovery day" in low or "protect your energy" in low, low[:200])

    def test_checkin_followed_by_direct_question_is_answered(self):
        self._say("Good morning")
        # a fresh question during check-in should be answered, not force a brief
        res = self._say("what is my biggest health risk?")
        self.assertIsNotNone(res)
        self.assertEqual(res["lane"], "personal_reasoning")


class RepairScenarioTests(_ConvMixin, TestCase):
    def test_critique_after_briefing_repairs_no_unrelated_fact(self):
        # seed a prior Beth briefing-style answer
        from apps.ai.models import AssistantMessage
        AssistantMessage.objects.create(
            conversation=self.conv, role="assistant",
            content="Coming up today you have Drink Protein Shake at 6:45 AM. "
                    "Your highest priority is Drink Protein Shake.")
        res = self._say("Does that sound right to you?")
        self.assertIsNotNone(res)
        self.assertEqual(res["lane"], "conversation_repair")
        ans = res["answer"].lower()
        # P32: a self-aware repair OWNS the miss and re-briefs (does not ask
        # Danny to diagnose, does not dump an unrelated fact).
        self.assertIn("you're right", ans)
        self.assertNotIn("tell me exactly what", ans)
        self.assertNotIn("0 g protein", ans)              # NOT an unrelated fact dump
        self.assertNotIn("protein today", ans)
        self.assertFalse(ar.is_failure_message(ans))
        self.assertEqual(self._state().get("state"), "repair")

    def test_critique_with_no_prior_answer_is_not_repair(self):
        # first message of a conversation, no prior Beth answer -> not a repair
        res = self._say("are you sure?")
        # falls through to normal handling (not the repair lane)
        self.assertTrue(res is None or res.get("lane") != "conversation_repair")


class StateAndSafetyTests(_ConvMixin, TestCase):
    def test_non_greeting_non_critique_does_not_intervene(self):
        res = self._say("what is my current weight?")
        self.assertNotIn(res.get("lane"), ("conversation_checkin", "conversation_repair"))

    def test_no_past_item_framed_as_coming_up_in_brief(self):
        # the post-check-in brief is the TIME-AWARE deterministic agenda; with no
        # scheduled items it must never fabricate a "begin now" / "coming up".
        self._say("Good morning")
        res = self._say("fine")
        ans = res["answer"].lower()
        # build_daily_agenda is time-aware; assert no contradictory "begin"+past framing
        self.assertFalse("begin workout" in ans and "this morning" in ans)
