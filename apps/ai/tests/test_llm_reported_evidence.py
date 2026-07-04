# ==============================================================================
# File: apps/ai/tests/test_llm_reported_evidence.py
# Description: The CONVERSATIONAL (LLM) path must see today's conversation-reported
#   evidence. Root cause of the production contradiction: the LLM reads cos_context,
#   which did not contain the subjective/accomplishment evidence merged into
#   interpret(). Now format_cos_system_injection (the LLM system prompt) renders a
#   "TODAY'S REPORTED EVIDENCE" block read LIVE from executive_evidence — so the path
#   that talks to Danny reflects the same evolving executive picture. This certifies
#   the PROMPT contains the evidence (what the LLM then does with it is the model's job,
#   and the block instructs it explicitly).
# ==============================================================================
from datetime import date, datetime, timezone as _tz
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from apps.ai.chatgpt_cos import executive_evidence as ev
from apps.core.ai_orchestrator.cos_context import format_cos_system_injection

User = get_user_model()
TODAY = date(2026, 7, 4)
_TODAY = "apps.core.utils.get_user_today"


class LLMReportedEvidenceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="llmev@test.com", password="x")
        cache.clear()

    def _injection(self):
        # The real LLM prompt builder; it reads the evidence LIVE from the user.
        return format_cos_system_injection({"_user": self.user, "user_id": self.user.id})

    def test_prompt_includes_accomplishments_and_subjective(self):
        with mock.patch(_TODAY, return_value=TODAY):
            ev.record_subjective(self.user, "positive")
            ev.record_accomplishment(self.user, "made up 2 missed workouts (Wednesday, Friday)")
            inj = self._injection()
        self.assertIn("TODAY'S REPORTED EVIDENCE", inj)
        self.assertIn("made up 2 missed workouts", inj)
        self.assertIn("refreshed", inj.lower())          # feeling GOOD / refreshed
        self.assertIn("ahead of plan", inj.lower())
        self.assertIn("own it", inj.lower())             # own the miss if challenged

    def test_no_evidence_no_block(self):
        with mock.patch(_TODAY, return_value=TODAY):
            inj = self._injection()
        self.assertNotIn("TODAY'S REPORTED EVIDENCE", inj)

    def test_full_routed_sequence_reaches_the_llm_prompt(self):
        # The ACTUAL routed path records the evidence; a subsequent LLM prompt sees it.
        from apps.ai.models import AssistantConversation
        from apps.ai.chatgpt_cos.lanes import route_message
        conv = AssistantConversation.objects.create(user=self.user)
        clock = datetime(2026, 7, 4, 19, 0, tzinfo=_tz.utc)
        with mock.patch(_TODAY, return_value=TODAY), \
                mock.patch("apps.core.utils.get_user_now", return_value=clock):
            r = route_message(
                self.user,
                "I was full of energy and made up Wednesday and Friday workouts", conv)
            self.assertEqual(r["lane"], "accomplishment")
            inj = self._injection()
        self.assertIn("made up 2 missed workouts", inj)
        self.assertIn("refreshed", inj.lower())          # "full of energy" → positive
