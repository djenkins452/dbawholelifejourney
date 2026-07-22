# ==============================================================================
# File: apps/ai/tests/test_truth_subject_anchoring.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Conversation-State anchoring + audit-evidence certification
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-22
# ==============================================================================
"""
Gates for the two contributing defects in `docs/WLJ_WEIGHT_YESTERDAY_INVESTIGATION.md`:

  * ANCHORING — the active subject was derived ONLY from `get_entity`, so a factual
    answer from any other truth surface left the next elliptical turn ("Yesterday's?")
    unanchored; it drifted to the Journal domain in 2 of 4 live probes.
  * AUDIT — every turn in a conversation shared one `turn_id`, and the digest for
    `get_foundational_health_facts` recorded only the requested keys, never the values.
"""
from django.test import TestCase

from apps.ai.cos_services import audit as _audit
from apps.ai.model_interface import conversation_state as cs
from apps.ai.model_interface.service import ModelInterfaceService as MIS
from apps.ai.models import AssistantConversation, ToolCallLog
from apps.users.models import User


class SubjectAnchoringTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="anchor@test.com", password="x")

    def test_health_fact_answer_anchors_the_metric_subject(self):
        """The exact miss: a weight answer from the curated surface must anchor weight.

        Built through the REAL envelope wrapper — an earlier version of this helper read
        a `data` key that the canonical envelope does not use (it nests under `value`),
        so anchoring silently never fired in the live path while a hand-built dict passed.
        """
        from apps.ai.model_interface.service import _wrap_truth
        result = _wrap_truth({"weight_yesterday": {
            "status": "ok", "value": 281.5, "domain": "health", "metric": "weight"}},
            source="health_facts")
        subj = MIS._subject_from_truth_result(
            "get_foundational_health_facts", {"keys": ["weight_yesterday"]}, result)
        self.assertIsNotNone(subj)
        self.assertEqual(subj["kind"], "metric")
        self.assertEqual(subj["domain"], "health")
        self.assertEqual(subj["metric"], "weight")

    def test_history_answer_anchors_the_metric_subject(self):
        subj = MIS._subject_from_truth_result(
            "get_history", {"domain": "health", "metric": "weight"}, {"status": "ok"})
        self.assertEqual(subj["ref"], "health.weight")

    def test_analysis_answer_anchors_its_subject(self):
        subj = MIS._subject_from_truth_result(
            "get_analysis", {"domain": "health", "subject": "sleep"}, {"status": "ok"})
        self.assertEqual(subj["kind"], "analysis")
        self.assertEqual(subj["metric"], "sleep")

    def test_failed_retrieval_does_not_anchor(self):
        """A subject must come from truth actually returned, never from an attempt."""
        self.assertIsNone(MIS._subject_from_truth_result(
            "get_history", {"domain": "health", "metric": "weight"},
            {"status": "insufficient_evidence"}))

    def test_non_truth_tool_does_not_anchor(self):
        self.assertIsNone(MIS._subject_from_truth_result(
            "execute_action", {"action": "create_task"}, {"status": "ok"}))

    def test_metric_subject_persists_and_is_readable_next_turn(self):
        conv = AssistantConversation.objects.create(user=self.user, title="t")
        cs.record_turn(conv, retrieved_subject={
            "kind": "metric", "ref": "health.weight", "label": "weight",
            "domain": "health", "metric": "weight"})
        state = cs.read(conv)
        subj = state["active_subject"]
        self.assertEqual(subj["domain"], "health")
        self.assertEqual(subj["metric"], "weight")

    def test_subject_carries_references_only_never_prose(self):
        """Conversation State stores pointers, never model-authored content."""
        conv = AssistantConversation.objects.create(user=self.user, title="t")
        cs.record_turn(conv, retrieved_subject={
            "kind": "metric", "ref": "health.weight", "label": "weight",
            "domain": "health", "metric": "weight",
            "summary": "the user weighed 281.5 lb yesterday and is trending down"})
        subj = cs.read(conv)["active_subject"]
        self.assertNotIn("summary", subj)
        self.assertEqual(set(subj) - {"kind", "ref", "label", "source_turn",
                                      "first_ts", "turns_ago", "domain", "metric"},
                         set())

    def test_metric_subject_lead_instructs_re_retrieval_for_a_new_date(self):
        lead = MIS._conversation_state_lead({"conversation_state": {"active_subject": {
            "kind": "metric", "ref": "health.weight", "label": "weight",
            "domain": "health", "metric": "weight", "turns_ago": 0}}})
        self.assertIn("Yesterday's?", lead)
        self.assertIn("get_history(domain='health', metric='weight'", lead)
        self.assertIn("NEVER reuse the number from an earlier turn", lead)


class GroundingAndSelfConsistencyContractTests(TestCase):
    """The grounding + self-consistency rules must be part of the STANDING constitution
    the model reads every turn — not a question-specific prompt bolted on for one phrase.

    These assert the CONTRACT is delivered. Whether the model then honours it is a
    reasoning/experience certification, measured by live probes (see the milestone
    record in docs/WLJ_WEIGHT_YESTERDAY_INVESTIGATION.md), not by a unit test.
    """

    def test_grounding_rule_is_in_the_standing_constitution(self):
        from apps.ai.model_interface.constitution import CONSTITUTION
        text = CONSTITUTION if isinstance(CONSTITUTION, str) else str(CONSTITUTION)
        self.assertIn("ANSWER GROUNDING", text)
        self.assertIn("when the scope changes, RETRIEVE AGAIN", text)
        self.assertIn("Never carry a number from an earlier turn to a new date", text)

    def test_envelope_reading_rule_is_in_the_standing_constitution(self):
        from apps.ai.model_interface.constitution import CONSTITUTION
        text = CONSTITUTION if isinstance(CONSTITUTION, str) else str(CONSTITUTION)
        self.assertIn("TRUTH ENVELOPE", text)
        self.assertIn("latest_on_or_before", text)
        self.assertIn("Never present a stale value as", text)

    def test_self_consistency_rule_is_in_the_standing_constitution(self):
        """Directly targets "Could you clarify which two numbers?" over visible history."""
        from apps.ai.model_interface.constitution import CONSTITUTION
        text = CONSTITUTION if isinstance(CONSTITUTION, str) else str(CONSTITUTION)
        self.assertIn("SELF-CONSISTENCY", text)
        self.assertIn("do NOT ask them which numbers they mean", text)

    def test_grounding_rule_is_general_not_question_specific(self):
        """The contract must be scoped to EVERY user-specific value, not keyed to one
        question or metric. (Illustrative examples are fine — a rule that only fires for
        a named phrase or metric is not.)"""
        from apps.ai.model_interface.constitution import CONSTITUTION
        text = CONSTITUTION if isinstance(CONSTITUTION, str) else str(CONSTITUTION)
        grounding = text[text.index("ANSWER GROUNDING"):text.index("TRUTH ENVELOPE")]
        self.assertIn("applies to EVERY user-specific value", grounding)
        # Stated as a universal about values/scopes, not a branch on a subject.
        self.assertIn("A value retrieved for one date, period, or record", grounding)


class AuditEvidenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="auditev@test.com", password="x")

    def test_digest_records_the_returned_value_not_just_the_request(self):
        from apps.ai.model_interface.service import _wrap_truth
        envelope = _wrap_truth({"weight_yesterday": {
            "status": "ok", "value": 281.5, "unit": "lb", "semantics": "exact_date",
            "requested_date": "2026-07-21", "observed_on": "2026-07-21",
            "freshness": "current", "authority": "get_domain_history:health.weight"}},
            source="health_facts")
        digest = _audit.truth_digest(
            "get_foundational_health_facts", {"keys": ["weight_yesterday"]}, envelope)
        fact = digest["facts"]["weight_yesterday"]
        self.assertEqual(fact["value"], 281.5)
        self.assertEqual(fact["semantics"], "exact_date")
        self.assertEqual(fact["observed_on"], "2026-07-21")
        self.assertEqual(fact["authority"], "get_domain_history:health.weight")

    def test_digest_records_absence_honestly(self):
        from apps.ai.model_interface.service import _wrap_truth
        envelope = _wrap_truth({"weight_yesterday": {
            "status": "not_recorded", "semantics": "exact_date",
            "requested_date": "2026-07-21"}}, source="health_facts")
        digest = _audit.truth_digest(
            "get_foundational_health_facts", {"keys": ["weight_yesterday"]}, envelope)
        self.assertEqual(digest["facts"]["weight_yesterday"]["status"], "not_recorded")

    def test_digest_never_raises_on_hostile_input(self):
        self.assertIsInstance(_audit.truth_digest("x", None, None), dict)
        self.assertIsInstance(_audit.truth_digest("x", {"a": object()}, {"b": 1}), dict)

    def test_conversation_id_is_recorded_separately_from_turn_id(self):
        _audit.record_tool_call(self.user, kind="truth", tool_name="get_history",
                                turn_id="turn-abc123", conversation_id="42")
        row = ToolCallLog.objects.get(user=self.user)
        self.assertEqual(row.turn_id, "turn-abc123")
        self.assertEqual(row.conversation_id, "42")

    def test_turn_ids_are_unique_per_turn(self):
        """Two turns of ONE conversation must be separable in the ledger."""
        conv = AssistantConversation.objects.create(user=self.user, title="t")
        svc = MIS(self.user)
        seen = set()
        for _ in range(3):
            # Only the id derivation is under test here; no model call is made.
            turn_id = svc._new_turn_id(conv, request_id="")
            seen.add(turn_id)
        self.assertEqual(len(seen), 3)
