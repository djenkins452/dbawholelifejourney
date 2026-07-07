# ==============================================================================
# File: apps/ai/tests/test_mission_persistence.py
# Description: CONVERSATIONAL MISSION PERSISTENCE + EXECUTIVE THINKING PARTNERSHIP
#   (Phase 2 Executive Reasoning). A Chief of Staff establishes a mission for the
#   conversation and interprets EVERY subsequent message inside it until the mission is
#   completed, reframed, or replaced — she does not restart reasoning after each message.
#
#   Production failure this covers: "I'm overwhelmed" → (offer to help) → "anything I can
#   move that isn't a supplement?" was answered as a literal supplement search, and
#   "mostly it's work stuff you don't know about" restarted the script instead of pivoting
#   to a thinking partner. Here: the load-easing mission persists across follow-ups, and an
#   external-work reveal reframes Beth into an executive thinking partner (acknowledge →
#   stop optimizing WLJ → one good question → no WLJ context → capture only after items
#   emerge).
# ==============================================================================
from unittest import mock
import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase

from apps.ai.chatgpt_cos import conversation_planner as cp
from apps.ai.chatgpt_cos import lanes

User = get_user_model()
_C = "apps.ai.services.ai_service._call_api"
_CT = "apps.ai.services.ai_service._call_api_with_tools"
_RHYTHM = "apps.core.cos_briefing.rhythm_api.get_remaining_rhythm_items"
_NOW = "apps.core.utils.get_user_now"
TASKS = [{"title": "Call the plumber", "source_type": "task", "scheduled_time": "11:00"},
         {"title": "Fish Oil", "source_type": "supplement_dose", "scheduled_time": "09:30"},
         {"title": "Dentist appointment", "source_type": "appointment",
          "scheduled_time": "14:00"}]


def _mkuser(email):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="x")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class MissionDeltaTests(SimpleTestCase):
    """The delta classifier is the whole capability: does a message CONTINUE the mission,
    REFRAME it (problem is external), or REPLACE it (explicit pivot)?"""

    def test_load_easing_followup_continues(self):
        for m in ("Is there anything I can move that are not supplements or medicine?",
                  "what else can I move?", "anything else I can drop?",
                  "can we simplify the afternoon?", "yes please", "go ahead"):
            self.assertEqual(cp.mission_delta(None, m), cp.MISSION_CONTINUE, m)

    def test_external_work_reveal_reframes(self):
        for m in ("Mostly it is work stuff that you don't know about that I am overwhelmed with",
                  "honestly it's work — stuff you don't know about",
                  "it's not in here, it's my job",
                  "the real problem is at work"):
            self.assertEqual(cp.mission_delta(None, m), cp.MISSION_REFRAME_EXTERNAL, m)

    def test_explicit_wlj_pivot_or_greeting_replaces(self):
        for m in ("what's my weight today?", "how am I doing on my mission?",
                  "good morning", "what's on my calendar?"):
            self.assertEqual(cp.mission_delta(None, m), cp.MISSION_REPLACE, m)

    def test_critique_is_not_mission_continuation(self):
        # Feedback about Beth's turn must fall through to repair, never the load read.
        for m in ("that's wrong", "that's not what I meant", "are you sure about that?"):
            self.assertEqual(cp.mission_delta(None, m), cp.MISSION_REPLACE, m)


class ThinkingPartnerDeltaTests(SimpleTestCase):
    def test_thinking_continues_by_default(self):
        for m in ("the biggest thing is the board deck", "I have three deadlines colliding",
                  "my boss keeps adding to it", "I don't even know where to start"):
            self.assertEqual(cp.thinking_partner_delta(m), cp.MISSION_CONTINUE, m)

    def test_wlj_pivot_or_resolution_replaces(self):
        for m in ("what's my sleep last night?", "thanks, that helps", "I'm good now",
                  "ok that makes sense, thank you"):
            self.assertEqual(cp.thinking_partner_delta(m), cp.MISSION_REPLACE, m)


class EmergedWorkItemsTests(SimpleTestCase):
    def test_detects_concrete_items(self):
        self.assertTrue(lanes._emerged_work_items(
            "I need to finish the report and get back to the client"))
        self.assertTrue(lanes._emerged_work_items("the deck is due by Friday"))

    def test_ignores_pure_feeling(self):
        self.assertFalse(lanes._emerged_work_items("I just feel completely swamped"))
        self.assertFalse(lanes._emerged_work_items("it's a lot"))


class MissionRoutingTests(TestCase):
    """End-to-end through route_message: the mission persists across turns and reframes."""

    def setUp(self):
        from apps.ai.models import AssistantConversation
        self.u = _mkuser("mission@example.com")
        self.conv = AssistantConversation.objects.create(user=self.u, is_active=True)
        self.systems = []                 # captured LLM system prompts

    def _fake_llm(self, system, message, **kw):
        self.systems.append(system or "")
        return "What feels most urgent about it right now?"

    def _route(self, msg):
        from apps.ai.chatgpt_cos.lanes import route_message
        from apps.ai.models import AssistantMessage
        AssistantMessage.objects.create(conversation=self.conv, role="user", content=msg)
        with mock.patch(_C, side_effect=self._fake_llm), \
             mock.patch(_CT, side_effect=RuntimeError("no tools")), \
             mock.patch(_RHYTHM, return_value=TASKS), \
             mock.patch(_NOW, return_value=datetime.datetime(
                 2026, 7, 3, 9, 0, tzinfo=datetime.timezone.utc)):
            res = route_message(self.u, msg, self.conv)
        if res and res.get("answer"):
            AssistantMessage.objects.create(conversation=self.conv, role="assistant",
                                            content=res["answer"])
        return res

    def test_full_mission_persistence_and_reframe(self):
        # 1) Establish the mission.
        r1 = self._route("I feel good, just a little overwhelmed with so much to do.")
        self.assertEqual(r1["lane"], "problem_solving")

        # 2) A load-easing follow-up is interpreted INSIDE the mission — NOT a literal
        #    supplement search.
        r2 = self._route("Is there anything I can move that are not supplements or medicine?")
        self.assertEqual(r2["lane"], "problem_solving")
        self.assertIn("current version", r2["answer"].lower())   # re-read today's load

        # 3) The real problem is external → REFRAME to a thinking partner.
        r3 = self._route("Mostly it is work stuff that you don't know about "
                         "that I am overwhelmed with.")
        self.assertEqual(r3["lane"], "thinking_partner")
        ans3 = r3["answer"].lower()
        self.assertIn("outside wlj", ans3)                       # acknowledges the pivot
        self.assertTrue(ans3.rstrip().endswith("?"))             # ends with one question
        for off in ("supplement", "medicine", "protein", "france", "sleep", "prayer"):
            self.assertNotIn(off, ans3)                          # no unrelated WLJ context

        # 4) Continued thinking-partner turn with concrete work items → capture offered.
        r4 = self._route("The biggest thing is the board deck — I need to finish it by Friday.")
        self.assertEqual(r4["lane"], "thinking_partner")
        self.assertIn("capture", r4["answer"].lower())
        # The LLM was sandboxed as a thinking partner with no personal data.
        self.assertTrue(any("thinking partner" in s.lower() for s in self.systems))
        self.assertTrue(any("do not reference" in s.lower() for s in self.systems))

    def test_reframe_entry_does_not_offer_capture(self):
        self._route("I'm so overwhelmed, buried in things to do.")
        r = self._route("It's mostly work stuff you don't know about.")
        self.assertEqual(r["lane"], "thinking_partner")
        self.assertNotIn("capture", r["answer"].lower())         # conversation first

    def test_explicit_wlj_pivot_ends_the_mission(self):
        self._route("I'm overwhelmed with everything today.")
        self._route("It's work stuff you don't know about.")     # now thinking_partner
        self.assertEqual(cp.read_state(self.conv).get("state"), "thinking_partner")
        r = self._route("Actually, what's my weight today?")
        self.assertNotEqual((r or {}).get("lane"), "thinking_partner")
        self.assertNotEqual(cp.read_state(self.conv).get("state"), "thinking_partner")
