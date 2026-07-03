# ==============================================================================
# File: apps/ai/tests/test_conversation_state_management.py
# Description: Conversation STATE MANAGEMENT — an interrupted or failed personal
#   interaction must not contaminate the next unrelated conversation. Regression
#   for the reported sequence: a personal CHECK-IN begins → user responds → a
#   TEMPORARY FAILURE leaves the check-in state pending → the user starts a
#   completely UNRELATED general conversation → Beth must transition to it, NOT
#   stay trapped in personal coaching. Natural multi-turn threads across entry
#   points. No OpenAI (the general call is mocked); routing is deterministic.
# ==============================================================================
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.ai.chatgpt_cos import conversation_planner as cp
from apps.ai.chatgpt_cos.lanes import route_message

User = get_user_model()


class FakeConversation:
    """Minimal conversation stand-in — the planner + memory only need a mutable
    ``.metadata`` dict and a no-op ``.save()`` (no DB row required)."""

    def __init__(self, metadata=None):
        self.metadata = dict(metadata or {})

    def save(self, update_fields=None):
        pass


def _mock_general(system, message, **kw):
    return f"[GENERAL] {message}"


# ── Unit — the check-in state machine self-heals on a pivot ────────────────

class CheckInStateMachineUnitTests(SimpleTestCase):
    def _checkin_pending(self):
        return FakeConversation(
            {"conversation_state": {"state": "check_in", "last_beth_act": "checked_in",
                                    "turn": 1}})

    def test_plausible_feeling_detection(self):
        for m in ("tired", "I'm doing ok", "pretty good", "stressed about work",
                  "not great honestly", "meh", "a bit low today", "good"):
            self.assertTrue(cp._is_plausible_feeling(m), m)
        # Questions / new subjects / general-knowledge are NOT feelings.
        for m in ("Who was Jezebel?", "How come the Bible has four gospels?",
                  "Tell me about the Roman Empire", "What's the capital of France?",
                  "The Roman Empire was vast and lasted centuries across three continents"):
            self.assertFalse(cp._is_plausible_feeling(m), m)

    def test_feeling_reply_briefs(self):
        conv = self._checkin_pending()
        p = cp.plan(_FakeUser(), conv, "I'm doing ok")
        self.assertEqual(p["handler"], "brief_after_checkin")
        self.assertEqual(cp.read_state(conv).get("state"), "briefing")

    def test_question_pivot_abandons_checkin(self):
        conv = self._checkin_pending()
        p = cp.plan(_FakeUser(), conv, "Who was Jezebel?")
        self.assertEqual(p["handler"], "route")           # not brief_after_checkin
        self.assertEqual(cp.read_state(conv), {})          # state cleared

    def test_unrelated_statement_pivot_abandons_checkin(self):
        conv = self._checkin_pending()
        p = cp.plan(_FakeUser(), conv, "The Roman Empire was vast and spanned centuries")
        self.assertEqual(p["handler"], "route")
        self.assertEqual(cp.read_state(conv), {})

    def test_clear_state_removes_pending(self):
        conv = self._checkin_pending()
        cp.clear_state(conv)
        self.assertNotIn("conversation_state", conv.metadata)


class _FakeUser:
    id = 999
    preferences = None
    is_authenticated = True


# ── End-to-end — natural multi-turn threads across entry points ────────────

class ConversationStateManagementE2ETests(TestCase):
    def setUp(self):
        from apps.users.models import TermsAcceptance
        self.user = User.objects.create_user(
            email="statemgmt@test.com", password="pw12345!")
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        self.conv = FakeConversation()

    def _route(self, msg):
        return route_message(self.user, msg, self.conv)

    @mock.patch("apps.ai.services.ai_service._call_api", side_effect=_mock_general)
    def test_checkin_entry_then_feeling_briefs(self, _m):
        # ENTRY POINT: a greeting opens a personal check-in.
        r1 = self._route("Good morning")
        self.assertEqual(r1["lane"], "conversation_checkin")
        self.assertEqual(cp.read_state(self.conv).get("state"), "check_in")
        # A genuine feeling reply hands off to the executive briefing.
        r2 = self._route("I'm doing ok, a bit tired")
        self.assertEqual(r2["lane"], "conversation_brief")

    @mock.patch("apps.ai.services.ai_service._call_api", side_effect=_mock_general)
    def test_failed_checkin_then_unrelated_general_is_not_trapped(self, _m):
        # 1) The personal check-in begins.
        r1 = self._route("Good morning")
        self.assertEqual(r1["lane"], "conversation_checkin")
        self.assertEqual(cp.read_state(self.conv).get("state"), "check_in")

        # 2-3) The user's feeling reply hits a TEMPORARY FAILURE — the failing turn
        #      does not advance the state, so it stays pending at "check_in".
        #      (Simulated by leaving the pending state in place.)
        self.assertEqual(cp.read_state(self.conv).get("state"), "check_in")

        # 4) The user starts a COMPLETELY UNRELATED general conversation.
        r2 = self._route("Who was Jezebel?")

        # 5) Beth transitions to it — NOT trapped in personal coaching — and the
        #    stale check-in state is abandoned.
        self.assertEqual(r2["lane"], "general_conversation")
        self.assertIn("[GENERAL]", r2["answer"])
        self.assertEqual(cp.read_state(self.conv), {})

    @mock.patch("apps.ai.services.ai_service._call_api", side_effect=_mock_general)
    def test_pending_checkin_then_unrelated_statement_is_not_trapped(self, _m):
        self._route("Good morning")
        # A non-question unrelated statement is still a pivot — it must NOT be
        # briefed as if it were the feeling reply.
        r = self._route("The Roman Empire lasted for centuries across three continents")
        self.assertNotEqual(r["lane"] if r else "", "conversation_brief")
        self.assertEqual(cp.read_state(self.conv), {})

    @mock.patch("apps.ai.services.ai_service._call_api", side_effect=_mock_general)
    def test_general_question_with_no_active_checkin_routes_general(self, _m):
        # Baseline: with no pending state, a general question is unaffected.
        r = self._route("Who was Abraham Lincoln?")
        self.assertEqual(r["lane"], "general_conversation")

    @mock.patch("apps.ai.services.ai_service._call_api", side_effect=_mock_general)
    def test_full_recovery_sequence_checkin_fail_pivot_then_new_checkin(self, _m):
        # The whole arc: check-in → (failed) → unrelated general → later a fresh
        # greeting opens a clean check-in again (no contamination either way).
        self._route("Good morning")
        self._route("Who was Jezebel?")                  # pivot abandons check-in
        self.assertEqual(cp.read_state(self.conv), {})
        r = self._route("Good morning")                   # a clean new check-in
        self.assertEqual(r["lane"], "conversation_checkin")
        self.assertEqual(cp.read_state(self.conv).get("state"), "check_in")
