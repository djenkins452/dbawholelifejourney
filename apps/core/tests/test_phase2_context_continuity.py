# ==============================================================================
# File: apps/core/tests/test_phase2_context_continuity.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Context available to Phase 1 must survive into Phase 2
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-09-02
# ==============================================================================
"""Nothing may vanish silently at the Phase-1 → Phase-2 boundary.

Phase 2 used to RECONSTRUCT a partial prompt from a hand-listed subset of the envelope, so
every new context type had to remember to opt in — and whatever forgot simply disappeared.
Measured before the fix: **5 of 8 envelope keys were lost**, including the user's own
persona and any pending confirmation. That is what let a stated injury vanish before the
judgment that criticised the user's activity.

The boundary now carries the whole situation, and an omission must be DECLARED with a
reason. This file is the gate: add a context type, and it survives by default or this
fails.

No provider calls.
"""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.model_interface import synthesis

User = get_user_model()

# A representative FULL envelope — every key the builder can emit.
FULL_CONTEXT = {
    "ai_relationship": {"persona": {"name": "Texas Rancher", "key": "texas_rancher"},
                        "persona_instructions": "Talk plainly."},
    "deterministic_understanding": {"biggest_risk": "PRE-DECIDED VERDICT",
                                    "primary_challenge": "PRE-DECIDED VERDICT"},
    "current_context": {"current_screen": {"location": {"url": "/health/"}}},
    "conversation_state": {"pending_clarification": {"tool": "mutate_task",
                                                     "target": "MARKER-CLARIFY"},
                           "completed_actions": [{"target": "MARKER-DONE"}]},
    "interview": {"status": "active", "areas": []},
    "personal_truth": {"facts": [{"statement": "MARKER-PK easing back into exercise"}]},
    "missions": {"m1": {"title": "MARKER-MISSION"}},
    "execution_state": {"remaining": [{"title": "MARKER-EXEC"}]},
    "current_action": {"title": "MARKER-ACTION"},
    "pending_confirmations": [{"confirmation_id": "MARKER-CONF", "summary": "x"}],
}


class BoundaryCoverageTests(TestCase):
    """THE gate: nothing disappears without being declared."""

    def test_nothing_is_silently_lost(self):
        cov = synthesis.orientation_coverage(FULL_CONTEXT)
        self.assertEqual(cov["silently_lost"], [], (
            "context reached Phase 1 and vanished before Phase 2 without being declared "
            "in synthesis.INTENTIONALLY_OMITTED. Either carry it, or declare it WITH A "
            "REASON — silence is how the injury disappeared."))

    def test_every_declared_omission_states_a_reason(self):
        for key, reason in synthesis.INTENTIONALLY_OMITTED.items():
            with self.subTest(key=key):
                self.assertTrue(reason and len(reason) > 40,
                                f"{key} is omitted without a real justification")

    def test_a_new_context_type_survives_by_default(self):
        """The design property: the default is 'it carries', not 'it is dropped'."""
        ctx = dict(FULL_CONTEXT, some_future_context={"marker": "MARKER-FUTURE"})
        cov = synthesis.orientation_coverage(ctx)
        self.assertIn("some_future_context", cov["carried"])
        self.assertEqual(cov["silently_lost"], [])

    def test_empty_values_are_not_reported_as_lost(self):
        cov = synthesis.orientation_coverage(dict(FULL_CONTEXT, missions={}))
        self.assertNotIn("missions", cov["silently_lost"])


class WhatMustSurviveTests(TestCase):
    """The specific things whose loss caused production incidents."""

    def setUp(self):
        self.orientation = synthesis.build_orientation(FULL_CONTEXT)

    def _carries(self, marker):
        return marker in self.orientation

    def test_personal_knowledge_survives(self):
        self.assertTrue(self._carries("MARKER-PK"))

    def test_the_users_persona_survives(self):
        """Phase 2 rewrites the ANSWER — losing the persona meant it stopped sounding
        like the assistant the user chose."""
        self.assertTrue(self._carries("Texas Rancher"))

    def test_unresolved_clarification_survives(self):
        self.assertTrue(self._carries("MARKER-CLARIFY"))

    def test_completed_actions_survive(self):
        self.assertTrue(self._carries("MARKER-DONE"))

    def test_pending_confirmations_survive(self):
        self.assertTrue(self._carries("MARKER-CONF"))

    def test_current_action_survives(self):
        self.assertTrue(self._carries("MARKER-ACTION"))

    def test_execution_state_survives(self):
        self.assertTrue(self._carries("MARKER-EXEC"))

    def test_domain_evidence_still_reaches_phase_2_separately(self):
        """Evidence rides its own block; the orientation must not have displaced it."""
        rendered = synthesis.render_evidence([
            {"tool": "get_history", "args": {"domain": "health", "metric": "workouts"},
             "result": {"status": "ready", "summary": "MARKER-EVIDENCE"}}])
        self.assertIn("MARKER-EVIDENCE", rendered)


class DeliberateOmissionTests(TestCase):
    """What must NOT cross the boundary, and why."""

    def test_wljs_own_verdict_is_still_withheld(self):
        """Constitution I.3 -> I.4: handed a pre-decided verdict the model narrates it as
        its own with no evidence lineage to defend."""
        orientation = synthesis.build_orientation(FULL_CONTEXT)
        self.assertNotIn("PRE-DECIDED VERDICT", orientation)
        self.assertIn("deterministic_understanding", synthesis.INTENTIONALLY_OMITTED)

    def test_the_interview_does_not_reach_synthesis(self):
        self.assertIn("interview", synthesis.INTENTIONALLY_OMITTED)
        self.assertNotIn("interview", json.loads(
            synthesis.build_orientation(FULL_CONTEXT)))


class ConversationContextTests(TestCase):
    """The rib class itself: what he said this turn must reach the judgment."""

    def test_stated_circumstances_reach_phase_2(self):
        out = synthesis.render_conversation_context([
            {"role": "user", "content": "MARKER-CIRCUMSTANCE I am easing back in."}])
        self.assertIn("MARKER-CIRCUMSTANCE", out)

    def test_the_full_prompt_carries_situation_evidence_and_circumstance(self):
        """One assembled prompt, all three layers present."""
        from unittest import mock
        captured = {}

        class _Resp:
            choices = [type("C", (), {"message": type("M", (), {"content": "ok"})()})()]
            usage = None

        class _Client:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kw):
                        captured.update(kw)
                        return _Resp()

        synthesis.run_executive_synthesis(
            mock.Mock(client=_Client(), model="gpt-4o"),
            message="How am I doing?",
            evidence=[{"tool": "get_history",
                       "args": {"domain": "health", "metric": "workouts"},
                       "result": {"status": "ready", "summary": "MARKER-EVIDENCE"}}],
            standing_context=FULL_CONTEXT,
            conversation_history=[{"role": "user",
                                   "content": "MARKER-CIRCUMSTANCE I am easing back in."}])
        sent = "".join(m["content"] for m in captured.get("messages", []))
        for marker in ("MARKER-CIRCUMSTANCE", "MARKER-EVIDENCE", "MARKER-PK",
                       "Texas Rancher", "MARKER-CLARIFY"):
            with self.subTest(marker=marker):
                self.assertIn(marker, sent)
        self.assertNotIn("PRE-DECIDED VERDICT", sent)


class CurrentSituationBlockTests(TestCase):
    """One ordered block replaced eight competing ones — without losing content."""

    def setUp(self):
        from apps.ai.models import AssistantConversation
        from apps.ai.model_interface import conversation_state as cs
        from apps.core.personal_knowledge import service as pk
        self.user = User.objects.create_user(email="sit@contract.test", password="x")
        p = self.user.preferences
        for f in ("ai_enabled", "ai_data_consent", "personal_assistant_enabled",
                  "personal_assistant_consent", "use_model_interface"):
            if hasattr(p, f):
                setattr(p, f, True)
        p.ai_coaching_style = "california_chill"
        p.save()
        # The persona registry is data; a test DB has no fixtures loaded, and a missing
        # row would silently drop the voice block and make this suite look like a
        # regression it is not.
        from apps.ai.models import CoachingStyle
        CoachingStyle.objects.get_or_create(
            key="california_chill",
            defaults=dict(name="California Chill", description="Relaxed.",
                          prompt_instructions="Keep it relaxed and positive.",
                          is_active=True))
        self.user = User.objects.get(pk=self.user.pk)
        self.conv = AssistantConversation.get_or_create_active(self.user)
        pk.add_fact(self.user, "MARKER-PK easing back into exercise.",
                    topic="health_context")
        cs.set_pending_clarification(self.conv, tool_name="mutate_task",
                                     question="Which scope?", target="MARKER-CLARIFY")
        cs.record_completed_action(self.conv, tool_name="log_food",
                                   summary="Logged it.", target="MARKER-DONE")

    def _block(self):
        from apps.ai.model_interface.service import ModelInterfaceService
        svc = ModelInterfaceService(self.user)
        return svc._current_situation(
            svc.build_standing_context(conversation=self.conv, writes_enabled=True))

    def test_there_is_exactly_one_situation_heading(self):
        self.assertEqual(self._block().count("=== CURRENT SITUATION"), 1)

    def test_the_old_competing_headings_are_gone(self):
        block = self._block()
        for old in ("=== ACTIVE CONVERSATION STATE", "=== YOUR VOICE",
                    "=== ON SCREEN RIGHT NOW", "=== WHAT MATTERS RIGHT NOW",
                    "=== THE USER'S STANDING PROFILE",
                    "=== FILE(S) THE USER ATTACHED"):
            self.assertNotIn(old, block,
                             f"{old} still competes as its own top-level heading")

    def test_unresolved_intent_comes_before_persona(self):
        """Order is the point: a short reply attaches to the open question first."""
        block = self._block()
        self.assertLess(block.index("AWAITING THEIR ANSWER"), block.index("YOUR VOICE"))

    def test_no_content_was_lost_in_consolidation(self):
        block = self._block()
        for marker in ("AWAITING THEIR ANSWER", "MARKER-CLARIFY", "ALREADY DONE",
                       "MARKER-DONE", "YOUR VOICE"):
            with self.subTest(marker=marker):
                self.assertIn(marker, block)

    def test_the_block_is_absent_when_there_is_no_situation(self):
        other = User.objects.create_user(email="empty@contract.test", password="x")
        from apps.ai.model_interface.service import ModelInterfaceService
        svc = ModelInterfaceService(other)
        self.assertEqual(svc._current_situation({}), "")


class UntouchedSurfaceTests(TestCase):
    """This task consolidated salience. It did not prune capability or policy."""

    def test_the_tool_schema_was_not_pruned(self):
        from apps.ai.model_interface.constitution import all_tools
        self.assertGreaterEqual(len(all_tools(writes_enabled=True)), 40)

    def test_the_constitution_was_not_pruned(self):
        from apps.ai.model_interface.constitution import CONSTITUTION
        self.assertGreater(len(CONSTITUTION), 60000)

    def test_grounding_policy_is_still_stated(self):
        from apps.ai.model_interface.constitution import CONSTITUTION
        for invariant in ("NEVER REPORT AN ACTION YOU DID NOT EXECUTE",
                          "EXACT TARGET INTEGRITY",
                          "CURRENT TRUTH OUTRANKS HISTORY"):
            self.assertIn(invariant, CONSTITUTION)
