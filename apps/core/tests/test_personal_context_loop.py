# ==============================================================================
# File: apps/core/tests/test_personal_context_loop.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The personal-context loop — current context, memory, evolution
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-09-02
# ==============================================================================
"""A Chief of Staff that cannot use what you told it five minutes ago is not one.

Production: Danny said he was recovering from injured ribs and easing back into exercise.
Minutes later the CoS criticised his reduced workout frequency without reference to the
injury, then told him it could not remember temporary information.

Two independent defects, both structural:

  1. Phase-2 synthesis ACCEPTED `conversation_history` and never used it. Its prompt was
     question + orientation + retrieved evidence, so anything the user had explained about
     his circumstances — which WLJ holds no record of, because circumstance is not a
     measurement — was invisible at the exact moment a judgment was formed.
  2. Nothing described WLJ's memory to the model, so it answered from generic assistant
     priors ("I can't retain information") about a product that has had Personal Knowledge
     since M2.

Certified as a CLASS — no ribs, no injuries, no workouts in the assertions. No provider
calls anywhere.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.model_interface import synthesis
from apps.ai.model_interface.constitution import CONSTITUTION, all_tools
from apps.core.personal_knowledge import service as pk
from apps.core.personal_knowledge.models import (
    FactStatus, Provenance, ReviewState, Sensitivity,
)

User = get_user_model()


class CurrentConversationReachesSynthesisTests(TestCase):
    """Defect 1: stated circumstances must reach the judgment."""

    def test_conversation_context_is_rendered(self):
        out = synthesis.render_conversation_context([
            {"role": "user", "content": "I'm on crutches for a few weeks."},
            {"role": "assistant", "content": "Understood."},
        ])
        self.assertIn("crutches", out)

    def test_the_newest_statements_survive_truncation(self):
        history = [{"role": "user", "content": f"old message {i}"} for i in range(40)]
        history.append({"role": "user", "content": "THE-LATEST-THING"})
        out = synthesis.render_conversation_context(history)
        self.assertIn("THE-LATEST-THING", out)

    def test_the_block_is_bounded(self):
        history = [{"role": "user", "content": "x" * 5000} for _ in range(20)]
        self.assertLessEqual(len(synthesis.render_conversation_context(history)), 2400)

    def test_empty_history_renders_nothing(self):
        self.assertEqual(synthesis.render_conversation_context([]), "")
        self.assertEqual(synthesis.render_conversation_context(None), "")

    def test_synthesis_actually_sends_the_context_to_the_model(self):
        """The whole defect: the parameter existed and was dropped on the floor."""
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

        svc = mock.Mock(client=_Client(), model="gpt-4o")
        synthesis.run_executive_synthesis(
            svc, message="How am I doing?", evidence={}, standing_context={},
            conversation_history=[{"role": "user",
                                   "content": "MARKER-CIRCUMSTANCE happened to me."}])
        sent = "".join(m["content"] for m in captured.get("messages", []))
        self.assertIn("MARKER-CIRCUMSTANCE", sent,
                      "stated circumstances never reached the judgment")

    def test_the_synthesis_system_requires_accounting_for_circumstances(self):
        self.assertIn("ACCOUNT FOR HIS CIRCUMSTANCES", synthesis.SYNTHESIS_SYSTEM)

    def test_circumstance_does_not_override_canonical_measurement(self):
        """Context explains numbers; it never revises them."""
        self.assertIn("do not revise a number because of", synthesis.SYNTHESIS_SYSTEM)
        self.assertIn("measurements stay canonical", synthesis.SYNTHESIS_SYSTEM)

    def test_context_is_labelled_as_context_not_evidence(self):
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
            message="q", evidence={}, standing_context={},
            conversation_history=[{"role": "user", "content": "something"}])
        sent = "".join(m["content"] for m in captured.get("messages", []))
        self.assertIn("CONTEXT, not measurements", sent)


class CapabilityTruthTests(TestCase):
    """Defect 2: never deny a capability WLJ has."""

    def test_the_four_kinds_of_knowing_are_described(self):
        for phrase in ("THIS CONVERSATION", "PERSONAL KNOWLEDGE",
                       "CANONICAL WLJ RECORDS", "NOT YET SAVED"):
            self.assertIn(phrase, CONSTITUTION)

    def test_denying_memory_is_explicitly_forbidden(self):
        self.assertIn("never say you cannot remember personal information", CONSTITUTION)

    def test_honest_absence_is_distinguished_from_inability(self):
        self.assertIn("you have not mentioned that before", CONSTITUTION)

    def test_user_control_is_stated_alongside_the_capability(self):
        i = CONSTITUTION.index("WHAT YOU ACTUALLY REMEMBER")
        block = CONSTITUTION[i:i + 1600]
        self.assertIn("About Me", block)
        self.assertIn("delete", block)


class NaturalLearningTests(TestCase):
    """Ordinary conversation can produce Personal Knowledge — through the ONE authority."""

    def setUp(self):
        from apps.ai.models import AssistantConversation
        self.user = User.objects.create_user(email="loop@contract.test", password="x")
        self.conv = AssistantConversation.get_or_create_active(self.user)
        from apps.ai.model_interface.service import ModelInterfaceService
        self.svc = ModelInterfaceService(self.user)

    def _dispatch(self, args):
        return self.svc._make_dispatch(
            turn_id="t", surface="test", tools_called=[],
            conversation_id=self.conv.id, conversation=self.conv)("remember_about_user", args)

    def test_the_tool_is_exposed_and_named_for_what_it_does(self):
        names = [(t.get("function") or {}).get("name")
                 for t in all_tools(writes_enabled=True)]
        self.assertIn("remember_about_user", names)
        self.assertNotIn("record_interview_knowledge", names,
                         "the old interview-only name would fight natural learning")

    def test_ordinary_conversation_can_record_without_an_interview(self):
        out = self._dispatch({"facts": [
            {"statement": "MARKER-SITUATIONAL I am on crutches for a few weeks.",
             "topic": "health_context"}]})
        self.assertEqual(out["status"], "recorded")
        self.assertEqual(pk.active_facts(self.user).count(), 1)

    def test_it_is_recorded_through_the_canonical_authority_with_honest_provenance(self):
        self._dispatch({"facts": [{"statement": "I run a landscaping business.",
                                   "topic": "work"}]})
        fact = pk.active_facts(self.user).first()
        self.assertEqual(fact.provenance, Provenance.CANDIDATE_ACCEPTED)
        self.assertEqual(fact.review_state, ReviewState.USER_AUTHORED)

    def test_naturally_learned_context_reaches_the_model(self):
        self._dispatch({"facts": [{"statement": "MARKER-REACH I am between jobs.",
                                   "topic": "work"}]})
        standing = "\n".join(f.statement for f in pk.standing_facts(self.user))
        self.assertIn("MARKER-REACH", standing,
                      "learned context never reaches later conversations")

    def test_sensitive_material_is_stored_but_kept_out_of_standing_context(self):
        self._dispatch({"facts": [{"statement": "MARKER-PRIV a private matter.",
                                   "topic": "health_context", "sensitive": True}]})
        self.assertEqual(pk.active_facts(self.user).count(), 1)
        standing = "\n".join(f.statement for f in pk.standing_facts(self.user))
        self.assertNotIn("MARKER-PRIV", standing)

    def test_the_domain_boundary_still_rejects_domain_owned_values(self):
        out = self._dispatch({"facts": [
            {"statement": "Something", "topic": "health_context",
             "attributes": {"weight_lbs": 280}}]})
        self.assertIsInstance(out.get("not_remembered"), list)

    def test_recording_is_bounded_per_turn(self):
        out = self._dispatch({"facts": [
            {"statement": f"Fact number {i} about my life.", "topic": "other"}
            for i in range(30)]})
        self.assertLessEqual(len(out["remembered"]), 8)

    def test_a_failed_write_is_reported_not_swallowed(self):
        with mock.patch("apps.core.personal_knowledge.service.add_fact",
                        side_effect=RuntimeError("db down")):
            out = self._dispatch({"facts": [{"statement": "Durable thing.",
                                             "topic": "other"}]})
        self.assertEqual(out["remembered"], [])
        self.assertTrue(out["not_remembered"])


class EvolvingTruthTests(TestCase):
    """Situational truth must be able to stop being true."""

    def setUp(self):
        from apps.ai.models import AssistantConversation
        from apps.ai.model_interface.service import ModelInterfaceService
        self.user = User.objects.create_user(email="evolve2@contract.test", password="x")
        self.conv = AssistantConversation.get_or_create_active(self.user)
        self.svc = ModelInterfaceService(self.user)

    def _dispatch(self, args):
        return self.svc._make_dispatch(
            turn_id="t", surface="test", tools_called=[],
            conversation_id=self.conv.id, conversation=self.conv)("remember_about_user", args)

    def test_a_changed_fact_supersedes_through_the_existing_lineage(self):
        old = pk.add_fact(self.user, "MARKER-OLD I am recovering and taking it easy.",
                          topic="health_context")
        out = self._dispatch({"supersedes": [
            {"fact_id": old.id, "statement": "MARKER-NEW I am fully recovered."}]})
        old.refresh_from_db()
        self.assertEqual(out["status"], "recorded")
        self.assertEqual(old.fact_status, FactStatus.SUPERSEDED)
        self.assertIsNotNone(old.superseded_by_id)

    def test_the_person_is_not_left_defined_by_the_old_situation(self):
        old = pk.add_fact(self.user, "MARKER-OLD I am recovering and taking it easy.",
                          topic="health_context")
        self._dispatch({"supersedes": [
            {"fact_id": old.id, "statement": "MARKER-NEW I am fully recovered."}]})
        standing = "\n".join(f.statement for f in pk.standing_facts(self.user))
        self.assertIn("MARKER-NEW", standing)
        self.assertNotIn("MARKER-OLD", standing,
                         "the superseded situation still defines him")

    def test_history_survives_supersession(self):
        old = pk.add_fact(self.user, "Old truth.", topic="other")
        self._dispatch({"supersedes": [{"fact_id": old.id, "statement": "New truth."}]})
        old.refresh_from_db()
        self.assertEqual(old.fact_status, FactStatus.SUPERSEDED)

    def test_superseding_a_fact_that_does_not_exist_is_reported_not_invented(self):
        out = self._dispatch({"supersedes": [
            {"fact_id": 99999999, "statement": "Something new."}]})
        self.assertEqual(out["remembered"], [])
        self.assertTrue(out["not_remembered"])

    def test_another_users_fact_cannot_be_superseded(self):
        other = User.objects.create_user(email="other2@contract.test", password="x")
        theirs = pk.add_fact(other, "Their fact.", topic="other")
        out = self._dispatch({"supersedes": [
            {"fact_id": theirs.id, "statement": "Hijacked."}]})
        theirs.refresh_from_db()
        self.assertEqual(theirs.fact_status, FactStatus.ACTIVE)
        self.assertTrue(out["not_remembered"])

    def test_deleted_knowledge_stops_influencing_the_model(self):
        fact = pk.add_fact(self.user, "MARKER-GONE something.", topic="other")
        pk.delete_fact(fact)
        standing = "\n".join(f.statement for f in pk.standing_facts(self.user))
        self.assertNotIn("MARKER-GONE", standing)

    def test_the_tool_asks_rather_than_guessing_on_meaningful_conflict(self):
        tool = next(t["function"] for t in all_tools(writes_enabled=True)
                    if t["function"]["name"] == "remember_about_user")
        desc = tool["description"]
        self.assertIn("has that changed?", desc)
        self.assertIn("Only supersede when he has actually told you it changed", desc)

    def test_trivial_differences_are_not_policed(self):
        tool = next(t["function"] for t in all_tools(writes_enabled=True)
                    if t["function"]["name"] == "remember_about_user")
        self.assertIn("not a change of self", tool["description"])


class SituationalKnowledgeTests(TestCase):
    """Situational does not mean unimportant."""

    def test_the_tool_names_situational_context_as_worth_keeping(self):
        tool = next(t["function"] for t in all_tools(writes_enabled=True)
                    if t["function"]["name"] == "remember_about_user")
        desc = tool["description"]
        self.assertIn("SITUATIONAL", desc)
        self.assertIn("does NOT mean unimportant", desc)

    def test_it_asks_for_statements_that_stay_true_when_read_back(self):
        tool = next(t["function"] for t in all_tools(writes_enabled=True)
                    if t["function"]["name"] == "remember_about_user")
        self.assertIn("stays true when read back", tool["description"])

    def test_domain_owned_values_are_still_excluded(self):
        tool = next(t["function"] for t in all_tools(writes_enabled=True)
                    if t["function"]["name"] == "remember_about_user")
        self.assertIn("a WLJ domain already owns", tool["description"])
