# ==============================================================================
# File: apps/ai/tests/test_classifier.py
# Description: THE CONDUCTOR — Classifier (Step 2a, SHADOW). Verifies the 9-level speech-act
#   classifier labels each turn's move and the capability that SHOULD own it, with a
#   confidence, deterministically and without touching routing. The headline case is the
#   Executive-Accountability turn ("you let me slide on…") — the classifier must call it
#   META (→ repair), which is exactly the mis-ownership the shadow log will surface, since
#   the live router answers it as a goals question.
# ==============================================================================
from unittest import mock
import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase

from apps.ai.chatgpt_cos import classifier as clf

User = get_user_model()


class SpeechActTests(SimpleTestCase):
    def _act(self, msg, **kw):
        return clf.classify(msg, **kw)

    def test_accountability_critique_is_meta(self):
        c = self._act("I noticed you let me slide on Bike Ride/Pickleball, Empty "
                      "Dishwasher, Journal.", has_prior=True)
        self.assertEqual(c.speech_act, "meta")
        self.assertEqual(c.expected_owner, "meta")     # family vocab == speech act
        self.assertEqual(c.confidence, "high")

    def test_screen_question(self):
        self.assertEqual(self._act("What page am I on?").speech_act, "screen")
        self.assertEqual(self._act("summarize this", page_context={"x": 1}).speech_act, "screen")

    def test_meta_prior_turn_and_correction(self):
        self.assertEqual(self._act("that's not what I meant", has_prior=True).speech_act, "meta")
        self.assertEqual(self._act("read your last response", has_prior=True).speech_act, "meta")

    def test_continuation_needs_prior(self):
        self.assertEqual(self._act("why?", has_prior=True).speech_act, "continuation")
        # No prior turn → not a continuation (nothing to continue).
        self.assertNotEqual(self._act("why?", has_prior=False).speech_act, "continuation")

    def test_reconciliation_and_correction(self):
        self.assertEqual(self._act("I already did that this morning").speech_act, "correction")
        self.assertEqual(self._act("actually it's cardio today").speech_act, "correction")

    def test_reasoning_mode_struggle(self):
        c = self._act("I'm having a hard time breaking the 289 mark")
        self.assertEqual(c.speech_act, "reasoning_mode")

    def test_retrieval_personal_fact(self):
        self.assertEqual(self._act("How much water have I had today?").speech_act, "retrieval")
        self.assertEqual(self._act("what is my weight?").speech_act, "retrieval")

    def test_orientation_greeting_and_agenda(self):
        self.assertEqual(self._act("Good evening").speech_act, "orientation")
        self.assertEqual(self._act("what do I need to know?").speech_act, "orientation")

    def test_general_knowledge(self):
        self.assertEqual(self._act("who was Jezebel?").speech_act, "general")

    def test_precedence_meta_beats_retrieval_keyword(self):
        # "why did you start with my sleep" — a question mentioning 'my', but it's META
        # (about her turn), which must win over the retrieval form.
        c = self._act("why did you start with my sleep when it is 7:28pm?", has_prior=True)
        self.assertEqual(c.speech_act, "meta")

    def test_confidence_always_present_and_never_raises(self):
        for m in ("", None, "   ", "asdfghjkl", "🤔"):
            c = self._act(m)
            self.assertIn(c.confidence, ("high", "medium", "low"))
            self.assertTrue(c.speech_act)


class OwnerFamilyTests(SimpleTestCase):
    def test_maps_lanes_to_families(self):
        self.assertEqual(clf.owner_family("personal_reasoning"), "reasoning_mode")
        self.assertEqual(clf.owner_family("conversation_repair"), "meta")
        self.assertEqual(clf.owner_family("foundational_facts"), "retrieval")
        self.assertEqual(clf.owner_family("day_continuity"), "orientation")
        self.assertEqual(clf.owner_family("page_reference"), "screen")
        self.assertEqual(clf.owner_family("nonexistent_lane"), "unknown")


class ShadowIsRecordOnlyTests(TestCase):
    """The classifier runs and logs, but the current router still answers — no behavior
    change. Proven by: routing still returns, and COS_CLASSIFY is emitted."""
    def setUp(self):
        from apps.ai.models import AssistantConversation
        from apps.users.models import TermsAcceptance
        self.u = User.objects.create_user(email="clf@example.com", password="x")
        TermsAcceptance.objects.create(
            user=self.u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.u.preferences.has_completed_onboarding = True
        self.u.preferences.save()
        self.conv = AssistantConversation.objects.create(user=self.u, is_active=True)

    def test_classify_is_logged_and_routing_unchanged(self):
        from apps.ai.chatgpt_cos.lanes import route_message
        from apps.ai.models import AssistantMessage
        msg = "I noticed you let me slide on Empty Dishwasher and Journal."
        AssistantMessage.objects.create(conversation=self.conv, role="assistant",
                                        content="Here's your day.")  # a prior turn exists
        AssistantMessage.objects.create(conversation=self.conv, role="user", content=msg)
        with mock.patch("apps.ai.services.ai_service._call_api", side_effect=RuntimeError("x")), \
             mock.patch("apps.ai.services.ai_service._call_api_with_tools", side_effect=RuntimeError("x")), \
             mock.patch("apps.core.utils.get_user_now",
                        return_value=datetime.datetime(2026, 7, 3, 19, 0, tzinfo=datetime.timezone.utc)), \
             self.assertLogs("apps.ai.chatgpt_cos", level="INFO") as logs:
            route_message(self.u, msg, self.conv)
        blob = "\n".join(logs.output)
        self.assertIn("COS_CLASSIFY", blob)
        self.assertIn("speech_act=meta", blob)        # the shadow flags it as meta…
        self.assertIn("COS_CLASSIFY_MATCH", blob)      # …and records agree=… vs the winner
