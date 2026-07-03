# ==============================================================================
# File: apps/ai/tests/test_conversation_continuity_general.py
# Description: Conversation Continuity as a first-class CoS capability. An ACTIVE
#   conversation continues until the user EXPLICITLY changes subject — personal
#   coaching must NEVER interrupt an unrelated active discussion. Regression built
#   from a natural multi-turn EXTERNAL/general thread (not isolated prompts):
#   "Who was Jezebel?" → "How come the Bible has Matthew, Mark, Luke, and John?"
#   must CONTINUE the general thread, not abandon it for personal sleep coaching.
#   Origin: real production Beth conversation. No OpenAI (the general call is
#   mocked); routing is deterministic.
# ==============================================================================
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.ai.chatgpt_cos.lanes import (
    route_message, _general_continuity_lane,
    _is_explicit_personal_request, _is_continuation,
)

User = get_user_model()


class FakeConversation:
    """Minimal conversation stand-in — record_last_answer / get_last_answer only
    need a mutable ``.metadata`` dict and a no-op ``.save()``."""

    def __init__(self, metadata=None):
        self.metadata = dict(metadata or {})

    def save(self, update_fields=None):
        pass


class _FakeUser:
    id = 999
    preferences = None
    is_authenticated = True


def _mock_general(system, message, **kw):
    # A distinct, identifiable general answer per turn — its presence proves the
    # GENERAL lane produced the turn (never personal coaching).
    return f"[GENERAL] {message}"


# ── Unit — the continuity intent logic ────────────────────────────────────

class GeneralContinuityUnitTests(SimpleTestCase):
    def _thread(self, answer="Jezebel was a queen of ancient Israel."):
        return FakeConversation(
            {"last_answer": {"lane": "general_conversation", "answer": answer}})

    def test_explicit_personal_request_detection(self):
        # The ONLY things that end an active general thread.
        for m in ("How's my sleep been?", "what's on my calendar today",
                  "what's next?", "how am I doing", "plan my day",
                  "what needs my attention"):
            self.assertTrue(_is_explicit_personal_request(m), m)
        # General inquiries are NOT personal requests.
        for m in ("How come the Bible has Matthew, Mark, Luke, and John?",
                  "Who wrote them?", "Tell me more about the gospels.",
                  "What is the capital of France?", "Why do we have four seasons?"):
            self.assertFalse(_is_explicit_personal_request(m), m)

    def test_continuation_detection(self):
        # Genuine ELLIPTICAL / REFERENTIAL follow-ups only.
        for m in ("Who wrote them?", "tell me more", "and the Old Testament?",
                  "Why is that?", "What else did she do?", "why?", "and him?"):
            self.assertTrue(_is_continuation(m), m)
        # A SELF-CONTAINED new question is NOT a continuation (routes normally) —
        # continuity is never a catch-all.
        for m in ("How come the Bible has four gospels?", "What is diabetes?",
                  "Explain photosynthesis.", "Who wrote Hamlet?",
                  "How is my health?", "What is my next milestone?",
                  "I'm tired.", "ok thanks", "sounds good"):
            self.assertFalse(_is_continuation(m), m)

    @mock.patch("apps.ai.services.ai_service._call_api", side_effect=_mock_general)
    def test_claims_referential_followup(self, _m):
        conv = self._thread()
        res = _general_continuity_lane(
            _FakeUser(), "Why is that term associated with seduction?", conv)
        self.assertIsNotNone(res)
        self.assertEqual(res["lane"], "general_continuity")
        self.assertIn("[GENERAL]", res["answer"])

    @mock.patch("apps.ai.services.ai_service._call_api", side_effect=_mock_general)
    def test_does_not_claim_self_contained_new_question(self, _m):
        # Even with an active general thread, a complete new question is NOT a
        # continuation — general_continuity yields (Run #71 over-claim fix).
        conv = self._thread()
        for q in ("Explain photosynthesis.", "What is diabetes?",
                  "How is my health?", "What is my next milestone?"):
            self.assertIsNone(_general_continuity_lane(_FakeUser(), q, conv), q)

    def test_declines_explicit_personal_pivot(self):
        # A genuine personal pivot is always honoured — continuity yields.
        self.assertIsNone(
            _general_continuity_lane(_FakeUser(), "How's my sleep been?", self._thread()))
        self.assertIsNone(
            _general_continuity_lane(_FakeUser(), "What's next on my schedule?", self._thread()))

    def test_declines_without_active_general_thread(self):
        personal = FakeConversation(
            {"last_answer": {"lane": "foundational_facts", "answer": "Your weight is 250 lb."}})
        self.assertIsNone(
            _general_continuity_lane(_FakeUser(), "Who wrote the gospels?", personal))
        self.assertIsNone(
            _general_continuity_lane(_FakeUser(), "Who wrote the gospels?", None))

    def test_declines_personal_statement_not_an_inquiry(self):
        self.assertIsNone(
            _general_continuity_lane(_FakeUser(), "I'm feeling tired today.", self._thread()))


# ── End-to-end — natural multi-turn threads through the real router ────────

class GeneralConversationContinuityE2ETests(TestCase):
    def setUp(self):
        from apps.users.models import TermsAcceptance
        self.user = User.objects.create_user(
            email="continuity@test.com", password="pw12345!")
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        self.conv = FakeConversation()

    def _route(self, msg):
        return route_message(self.user, msg, self.conv)

    @mock.patch("apps.ai.services.ai_service._call_api", side_effect=_mock_general)
    def test_general_thread_continues_not_personal_coaching(self, _m):
        # THE reported case, as a natural two-turn conversation.
        r1 = self._route("Who was Jezebel?")
        self.assertEqual(r1["lane"], "general_conversation")

        r2 = self._route(
            "How come the Bible has books of Matthew, Mark, Luke, and John?")
        # Stays on the GENERAL-knowledge path — NOT abandoned for sleep coaching.
        # (A complete new general question routes to general_conversation; only a
        # referential follow-up would be general_continuity.)
        self.assertIn(r2["lane"], ("general_conversation", "general_continuity"))
        self.assertIn("[GENERAL]", r2["answer"])
        self.assertNotIn("sleep", r2["answer"].lower())

    @mock.patch("apps.ai.services.ai_service._call_api", side_effect=_mock_general)
    def test_general_thread_chains_across_multiple_followups(self, _m):
        self._route("Who was King David?")
        turns = [
            self._route("How did he become king?"),
            self._route("Who wrote about him?"),
            self._route("Tell me more."),
        ]
        for r in turns:
            self.assertEqual(r["lane"], "general_continuity")

    @mock.patch("apps.ai.chatgpt_cos.reasoning.answer_reasoning_question",
                return_value={"answer": "[REASONING]", "lane": "personal_reasoning"})
    @mock.patch("apps.ai.services.ai_service._call_api", side_effect=_mock_general)
    def test_explicit_personal_pivot_leaves_general_thread(self, _m, _r):
        # The user EXPLICITLY changes subject to something personal — the general
        # thread ends and normal (personal) routing resumes.
        self._route("Who was Jezebel?")
        r = self._route("How's my sleep been lately?")
        self.assertNotIn(r["lane"], ("general_continuity", "general_conversation"))

    @mock.patch("apps.ai.services.ai_service._call_api", side_effect=_mock_general)
    def test_first_general_question_unaffected(self, _m):
        # No active thread yet → the first general question routes as before.
        r = self._route("Who was Abraham Lincoln?")
        self.assertEqual(r["lane"], "general_conversation")


# ── Acceptance Run #71 — general_continuity must NOT over-claim ─────────────

class Run71OverClaimRegressionTests(TestCase):
    """The release-blocking regression: even with a prior general answer left on
    the conversation (the acceptance-harness condition), a self-contained new
    question — general, boundary, or WLJ-owned personal truth — must route to its
    correct owner, NEVER be captured by general_continuity's outage fallback."""

    def setUp(self):
        from apps.users.models import TermsAcceptance
        self.user = User.objects.create_user(
            email="run71@test.com", password="pw12345!")
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        # A prior general answer persists on the conversation (exactly what
        # exposed the over-claim in Run #71).
        self.conv = FakeConversation({"last_answer": {
            "lane": "general_conversation", "answer": "Jezebel was a queen."}})

    def _route(self, msg):
        return route_message(self.user, msg, self.conv)

    @mock.patch("apps.ai.services.ai_service._call_api", side_effect=_mock_general)
    def test_class1_first_turn_general_routes_general_not_continuity(self, _m):
        for q in ("Explain photosynthesis.", "Who wrote Hamlet?",
                  "What is compound interest?", "What is a REST API?",
                  "Explain the difference between weather and climate.",
                  "What is Delphi?", "What is a CTE in SQL?"):
            self.assertEqual(self._route(q)["lane"], "general_conversation", q)

    @mock.patch("apps.ai.chatgpt_cos.reasoning.answer_reasoning_question",
                return_value=None)
    @mock.patch("apps.ai.services.ai_service._call_api", side_effect=_mock_general)
    def test_class2_boundary_general_concepts_route_general(self, _m, _r):
        for q in ("What is diabetes?",
                  "What is a milestone in project management?"):
            r = self._route(q)
            # tool_loop (None) is the general/external fallback — acceptable.
            lane = r.get("lane") if r else "tool_loop"
            # Must NOT be stale continuity and must NOT be personal coaching.
            self.assertNotIn(lane, ("general_continuity", "personal_reasoning",
                                    "cos_briefing", "next_rhythm",
                                    "conversation_brief"), q)

    @mock.patch("apps.ai.chatgpt_cos.reasoning.answer_reasoning_question",
                return_value={"answer": "Your health is on track.",
                              "lane": "personal_reasoning"})
    @mock.patch("apps.ai.services.ai_service._call_api", side_effect=_mock_general)
    def test_class3_personal_truth_reaches_deterministic_not_outage(self, _m, _r):
        for q in ("How is my health?", "How is my diabetes doing?",
                  "What is my next milestone?"):
            r = self._route(q)
            self.assertNotIn(r["lane"], ("general_continuity", "general_conversation"), q)
            self.assertNotIn("external knowledge service",
                             (r.get("answer") or "").lower(), q)

    @mock.patch("apps.ai.services.ai_service._call_api", side_effect=_mock_general)
    def test_true_referential_continuity_still_preserved(self, _m):
        # Jezebel is already the active thread (setUp) — a referential follow-up
        # DOES continue it.
        r = self._route("Why is that term associated with seduction?")
        self.assertEqual(r["lane"], "general_continuity")
