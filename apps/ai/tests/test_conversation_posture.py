# ==============================================================================
# File: apps/ai/tests/test_conversation_posture.py
# Description: CONVERSATIONAL NEED / POSTURE (Phase 2). A Chief of Staff first works out
#   WHAT KIND of conversation this is, then chooses posture + depth — she does not answer
#   every opener with a full executive briefing. A user who is BEHIND/OVERWHELMED gets
#   help (problem-solving), not a briefing; a user WORRIED ABOUT A PERSON gets listening,
#   not executive priorities. Greeting/execution/briefing openers are unchanged.
# ==============================================================================
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase

from apps.ai.chatgpt_cos import conversation_planner as cp

User = get_user_model()
_C = "apps.ai.services.ai_service._call_api"
_CT = "apps.ai.services.ai_service._call_api_with_tools"


def _mkuser(email):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="x")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class NeedClassifierTests(SimpleTestCase):
    def test_problem_solving_openers(self):
        for m in ("I'm really tired today. I already feel behind.",
                  "I'm swamped today.", "so much to do and no time",
                  "good morning, I'm overwhelmed", "I'm falling behind on everything"):
            self.assertEqual(cp.classify_need(m), cp.NEED_PROBLEM_SOLVING, m)

    def test_personal_concern_openers(self):
        for m in ("I'm worried about Haley.", "I'm anxious about my daughter.",
                  "I'm really concerned about my mom right now."):
            self.assertEqual(cp.classify_need(m), cp.NEED_PERSONAL_CONCERN, m)

    def test_health_or_goal_worries_stay_on_their_normal_path(self):
        for m in ("I'm worried about my weight lately.",
                  "I'm anxious about my France goal.",
                  "worried about my glucose"):
            self.assertIsNone(cp.classify_need(m), m)

    def test_neutral_openers_are_not_reclassified(self):
        for m in ("Good morning.", "I feel great today.", "What is my biggest risk?",
                  "How am I doing today?", "I'm tired but okay"):
            self.assertIsNone(cp.classify_need(m), m)

    def test_concern_object_extraction(self):
        self.assertEqual(cp.concern_object("I'm worried about Haley."), "Haley")
        self.assertEqual(cp.concern_object("I'm anxious about my daughter"), "my daughter")


class PostureRoutingTests(TestCase):
    def setUp(self):
        from apps.ai.models import AssistantConversation
        self.u = _mkuser("posture@example.com")
        self.conv = AssistantConversation.objects.create(user=self.u, is_active=True)

    def _route(self, msg):
        from apps.ai.chatgpt_cos.lanes import route_message
        from apps.ai.models import AssistantMessage
        AssistantMessage.objects.create(conversation=self.conv, role="user", content=msg)
        with mock.patch(_C, side_effect=RuntimeError("down")), \
             mock.patch(_CT, side_effect=RuntimeError("down")):
            res = route_message(self.u, msg, self.conv)
        if res:
            AssistantMessage.objects.create(conversation=self.conv, role="assistant",
                                            content=res.get("answer") or "")
        return res

    def test_problem_opener_offers_help_not_a_briefing(self):
        res = self._route("I'm really tired today. I already feel behind.")
        self.assertEqual(res["lane"], "problem_solving")
        ans = res["answer"].lower()
        self.assertIn("lighter", ans)
        self.assertTrue("move" in ans or "simplify" in ans or "let go" in ans)
        # NOT the executive briefing machinery.
        self.assertNotIn("looking at everything together", ans)
        self.assertNotIn("through-line", ans)

    def test_personal_concern_engages_the_person_not_priorities(self):
        res = self._route("I'm worried about Haley.")
        self.assertEqual(res["lane"], "personal_concern")
        ans = res["answer"].lower()
        self.assertIn("haley", ans)
        self.assertIn("what's going on", ans)          # invites them to talk
        # The executive concern has CHANGED — no protein / workout / mission talk, and no
        # priorities at all. Minimal, then stop.
        for off_topic in ("protein", "workout", "france", "backlog", "sleep", "priority"):
            self.assertNotIn(off_topic, ans)

    def test_bare_greeting_still_opens_with_the_check_in(self):
        res = self._route("Good morning.")
        self.assertEqual(res["lane"], "conversation_checkin")

    def test_positive_opener_gets_orientation_then_stops(self):
        # A volunteered self-report is ORIENTED, not briefed: it hands the conversation
        # back with a question and does NOT enumerate every domain.
        res = self._route("I feel great today. Knocked out a few things already.")
        self.assertEqual(res["lane"], "self_report")
        ans = res["answer"]
        self.assertTrue(ans.rstrip().endswith("?"))          # hands it back with a question
        self.assertIn("what do you need from me", ans.lower())
        low = ans.lower()
        # Not the full report machinery.
        self.assertNotIn("looking at everything together", low)
        self.assertNotIn("through-line", low)
        self.assertNotIn("the rest of what's on your list", low)

    def test_explicit_briefing_request_still_gets_the_full_read(self):
        # Briefing is still available — when the user asks for the picture.
        res = self._route("How am I doing today?")
        self.assertIsNotNone(res)
        ans = (res.get("answer") or "").lower()
        # The full read does more than orient — it doesn't just hand back a question.
        self.assertNotIn("what do you need from me", ans)
