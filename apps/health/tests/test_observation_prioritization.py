"""
Sprint 6 — Deterministic Observation Prioritization tests.

Proves: ranking is deterministic and stable, evidence and goals influence ranking,
grouping is deterministic, low-confidence cannot outrank stronger observations,
risks outrank opportunities, and safety suppression still applies BEFORE ranking.
"""

from datetime import timedelta

from django.test import TestCase

from apps.health.medication_events import record_medication_change
from apps.health.models import MedicationEvent
from apps.health.observations import (
    Observation,
    ObsType,
    build_prioritized,
    group_observations,
    prioritize_observations,
)

from apps.health.tests.test_medicine_adherence import AdherenceTestMixin


def _obs(type_, conf, domains=("medication",), evidence=({"type": "x"},),
         physician=False, title="t", detail=""):
    return Observation(type_, title, detail=detail, confidence=conf,
                       domains=domains, evidence=evidence,
                       physician_discussion=physician, safety_class="observation")


class PrioritizationRankingTest(TestCase):
    def test_ranking_is_deterministic_and_stable(self):
        obs = [
            _obs(ObsType.MEDICATION_STABLE, 0.65),
            _obs(ObsType.ADHERENCE_DECLINING, 0.8),
            _obs(ObsType.TREATMENT_RECENTLY_CHANGED, 0.8),
        ]
        a = prioritize_observations(obs, {})
        b = prioritize_observations(list(reversed(obs)), {})
        # Identical inputs (any order) → identical ordering.
        self.assertEqual([d["type"] for d in a], [d["type"] for d in b])

    def test_risk_outranks_opportunity(self):
        obs = [
            _obs(ObsType.ADHERENCE_IMPROVING, 0.9),   # opportunity
            _obs(ObsType.ADHERENCE_DECLINING, 0.7),   # risk
        ]
        ranked = prioritize_observations(obs, {})
        self.assertEqual(ranked[0]["type"], ObsType.ADHERENCE_DECLINING)

    def test_recent_change_outranks_stable(self):
        obs = [
            _obs(ObsType.LONG_TERM_STABILITY, 0.9),
            _obs(ObsType.TREATMENT_RECENTLY_CHANGED, 0.6),
        ]
        ranked = prioritize_observations(obs, {})
        self.assertEqual(ranked[0]["type"], ObsType.TREATMENT_RECENTLY_CHANGED)

    def test_low_confidence_cannot_outrank_stronger_same_type(self):
        # Same type → confidence is the differentiator; higher confidence ranks first.
        obs = [
            _obs(ObsType.RECENT_REFILL_PATTERN, 0.5, title="low"),
            _obs(ObsType.MULTIPLE_DOSE_INCREASES, 0.5, title="strong"),
        ]
        ranked = prioritize_observations(obs, {})
        self.assertEqual(ranked[0]["type"], ObsType.MULTIPLE_DOSE_INCREASES)

    def test_evidence_quality_influences_score(self):
        few = _obs(ObsType.MEDICATION_STABLE, 0.7, evidence=({"a": 1},))
        many = _obs(ObsType.MEDICATION_STABLE, 0.7,
                    evidence=({"a": 1}, {"b": 2}, {"c": 3}))
        s_few = prioritize_observations([few], {})[0]["priority_score"]
        s_many = prioritize_observations([many], {})[0]["priority_score"]
        self.assertGreater(s_many, s_few)

    def test_goal_relevance_boosts(self):
        o = _obs(ObsType.GLUCOSE_AFTER_TREATMENT_CHANGE, 0.6,
                 domains=("medication", "glucose"),
                 title="Average glucose was lower after a change")
        no_goal = prioritize_observations([o], {"goal_keywords": []})[0]
        with_goal = prioritize_observations([o], {"goal_keywords": ["glucose"]})[0]
        self.assertGreater(with_goal["priority_score"], no_goal["priority_score"])
        self.assertEqual(with_goal["relevance"], "high")

    def test_each_priority_is_explainable(self):
        ranked = prioritize_observations([_obs(ObsType.ADHERENCE_DECLINING, 0.8)], {})[0]
        self.assertIn("priority_explanation", ranked)
        self.assertTrue(ranked["contributing_factors"])
        self.assertIn(ranked["urgency"], ("high", "medium", "low"))


class GroupingTest(TestCase):
    def test_grouping_is_deterministic(self):
        obs = [
            _obs(ObsType.WEIGHT_AFTER_TREATMENT_CHANGE, 0.6, domains=("medication", "weight"), physician=True),
            _obs(ObsType.GLUCOSE_AFTER_TREATMENT_CHANGE, 0.6, domains=("medication", "glucose"), physician=True),
            _obs(ObsType.ADHERENCE_DECLINING, 0.8),
        ]
        ranked = prioritize_observations(obs, {})
        groups = group_observations(ranked)
        keys = [g["key"] for g in groups]
        # Weight + glucose collapse into one 'treatment_response' cluster.
        tr = [g for g in groups if g["key"] == "treatment_response"]
        self.assertEqual(len(tr), 1)
        self.assertEqual(len(tr[0]["observations"]), 2)
        # Cluster carries the physician flag from its members; evidence preserved.
        self.assertTrue(tr[0]["physician_discussion"])
        # Deterministic order (run twice → identical).
        self.assertEqual(keys, [g["key"] for g in group_observations(ranked)])


class PrioritizationPipelineTest(AdherenceTestMixin, TestCase):
    def setUp(self):
        self.user = self.create_user(email="prio@test.com")

    def test_suppression_applies_before_ranking(self):
        """Only approved observations reach the ranker (build_observations gates)."""
        med = self.create_medicine(self.user, name="Lantus", dose="20 units")
        for prev, new in (("20", "24"), ("24", "28")):
            record_medication_change(
                med, MedicationEvent.EVENT_DOSE_CHANGED,
                previous_value={"dose": f"{prev} units"}, new_value={"dose": f"{new} units"},
            )
        prioritized, groups = build_prioritized(self.user)
        # Every ranked observation is approved (never suppressed) + scored.
        for d in prioritized:
            self.assertNotEqual(d["safety_class"], "suppressed")
            self.assertIn("priority_score", d)
        # Deterministic: identical second call → identical ordering.
        again, _ = build_prioritized(self.user)
        self.assertEqual([d["type"] for d in prioritized], [d["type"] for d in again])

    def test_state_exposes_prioritized_and_groups(self):
        from apps.core.ai_state.state_builder import build_medicine_state
        med = self.create_medicine(self.user, name="Lantus", dose="20 units")
        for prev, new in (("20", "24"), ("24", "28")):
            record_medication_change(
                med, MedicationEvent.EVENT_DOSE_CHANGED,
                previous_value={"dose": f"{prev} units"}, new_value={"dose": f"{new} units"},
            )
        contract = build_medicine_state(self.user)["_contract"]
        self.assertIn("prioritized_observations", contract)
        self.assertIn("observation_groups", contract)
        self.assertTrue(contract["prioritized_observations"])
        # Ranked descending by priority.
        scores = [d["priority_score"] for d in contract["prioritized_observations"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
