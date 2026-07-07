# ==============================================================================
# File: apps/ai/tests/test_intent_evolution.py
# Description: CONVERSATIONAL INTENT EVOLUTION — Status → Diagnosis (Phase 2 Executive
#   Reasoning). A conversation's MISSION can stay the same while the KIND of reasoning
#   evolves. Production failure: "How's my France goal?" (status) → "I'm having a hard
#   time breaking 289, it's not falling off like the beginning" was answered as another
#   status summary that drifted to prayer/other goals, because the self_report lane read
#   it as a mood. Here: a diagnostic shift is recognized (domain-agnostically), routes into
#   grounded diagnosis over deterministic truth, and beats the self-report/summary lanes.
#   Planning/Decision are scaffolded (recognized, NOT wired live).
# ==============================================================================
from unittest import mock
import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase

from apps.ai.chatgpt_cos import reasoning_mode as rm

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


class ModeClassifierTests(SimpleTestCase):
    """Domain-agnostic: the SAME struggle/plateau/confusion cues fire across every domain."""

    def test_diagnosis_across_domains(self):
        for m in (
            "I am having a hard time breaking the 289 mark. It is not falling off like the "
            "beginning of my journey.",
            "My glucose has been weird lately.",
            "I don't understand why this project is slipping.",
            "My motivation just isn't there anymore.",
            "I'm stuck at the same weight for weeks.",
            "why isn't my savings growing like before",
        ):
            self.assertEqual(rm.classify_mode(m), rm.DIAGNOSIS, m)

    def test_status_and_neutral_are_not_diagnosis(self):
        for m in ("How is my France goal looking?", "what's my weight today?",
                  "good morning", "how am I doing on my goals?"):
            self.assertNotEqual(rm.classify_mode(m), rm.DIAGNOSIS, m)

    def test_planning_and_decision_recognized_but_scaffolded(self):
        # The ladder EXISTS conceptually — recognized — but these are NOT diagnosis and are
        # not yet wired to a lane.
        self.assertEqual(rm.classify_mode("ok what should I do about it?"), rm.PLANNING)
        self.assertEqual(rm.classify_mode("should I drop the goal or push harder?"),
                         rm.DECISION)
        self.assertFalse(rm.is_diagnostic_shift("what should I do about it?"))


class DiagnosticRoutingTests(TestCase):
    def setUp(self):
        from apps.ai.models import AssistantConversation
        self.u = _mkuser("diagnosis@example.com")
        self.conv = AssistantConversation.objects.create(user=self.u, is_active=True)
        self.systems = []

    def _fake_llm(self, system, message, **kw):
        self.systems.append(system or "")
        return ("Let's dig into that. Early on the weight came off faster because the gap "
                "was bigger; lately the rate has flattened. What changed around then?")

    def _route(self, msg):
        from apps.ai.chatgpt_cos.lanes import route_message
        from apps.ai.models import AssistantMessage
        AssistantMessage.objects.create(conversation=self.conv, role="user", content=msg)
        with mock.patch(_C, side_effect=self._fake_llm), \
             mock.patch(_CT, side_effect=RuntimeError("no tools")), \
             mock.patch("apps.core.utils.get_user_now", return_value=datetime.datetime(
                 2026, 7, 3, 9, 0, tzinfo=datetime.timezone.utc)):
            res = route_message(self.u, msg, self.conv)
        if res and res.get("answer"):
            AssistantMessage.objects.create(conversation=self.conv, role="assistant",
                                            content=res["answer"])
        return res

    def test_weight_plateau_routes_to_diagnosis_not_self_report(self):
        r = self._route("I am having a hard time breaking the 289 mark. "
                        "It is not falling off like the beginning of my journey.")
        self.assertEqual(r["lane"], "diagnostic")           # NOT self_report / brief
        self.assertEqual(r["reasoning"]["mode"], "diagnosis")
        self.assertEqual(r["reasoning"]["domain"], "health")
        # The diagnostic posture was used (investigate what changed, don't summarize).
        self.assertTrue(any("understand why" in s.lower() for s in self.systems))
        self.assertTrue(any("do not give a status summary" in s.lower()
                            for s in self.systems))

    def test_status_question_is_not_hijacked(self):
        # A pure status question must NOT be captured by the diagnostic lane.
        r = self._route("How am I doing on my goals overall?")
        self.assertNotEqual((r or {}).get("lane"), "diagnostic")

    def test_ungroundable_diagnosis_declines(self):
        # A diagnostic shift with no groundable subject (no domain, no prior topic) falls
        # through — the lane must not fabricate a diagnosis.
        r = self._route("I don't understand why everything feels off.")
        self.assertNotEqual((r or {}).get("lane"), "diagnostic")
