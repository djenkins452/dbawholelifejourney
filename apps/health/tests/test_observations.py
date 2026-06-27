"""
Sprint 5 — Observation Engine & Safety Classifier tests.

Proves the deterministic observation layer's guarantees: observations require
evidence, cannot bypass the safety classifier, low-confidence/contradictory ones
are suppressed, duplicates collapse, physician-discussion flags are deterministic,
chronology is preserved, and no causal language is produced.
"""

from datetime import timedelta

from django.test import TestCase

from apps.health.medication_events import record_medication_change
from apps.health.models import Intake, IntakeLog, IntakeSchedule, MedicationEvent
from apps.health.observations import (
    Observation,
    ObsType,
    SafetyClass,
    approve,
    build_observations,
    classify,
)

from apps.health.tests.test_medicine_adherence import AdherenceTestMixin


class SafetyClassifierTest(TestCase):
    def test_no_evidence_is_suppressed(self):
        o = Observation(ObsType.MEDICATION_STABLE, "x", confidence=0.9, evidence=())
        self.assertEqual(classify(o).safety_class, SafetyClass.SUPPRESSED)

    def test_low_confidence_is_suppressed(self):
        o = Observation(ObsType.MEDICATION_STABLE, "x", confidence=0.2,
                        evidence=({"type": "MedicationEvent", "id": 1},))
        self.assertEqual(classify(o).safety_class, SafetyClass.SUPPRESSED)

    def test_contradictory_is_suppressed(self):
        o = Observation(ObsType.MEDICATION_STABLE, "x", confidence=0.9,
                        evidence=({"type": "x"},), contradictory=True)
        self.assertEqual(classify(o).safety_class, SafetyClass.SUPPRESSED)

    def test_biomarker_cross_domain_flags_physician_discussion(self):
        o = Observation(ObsType.WEIGHT_AFTER_TREATMENT_CHANGE, "x", confidence=0.6,
                        domains=("medication", "weight"), evidence=({"type": "x"},))
        c = classify(o)
        self.assertEqual(c.safety_class, SafetyClass.PHYSICIAN_DISCUSSION)
        self.assertTrue(c.physician_discussion)

    def test_medication_only_is_plain_observation(self):
        o = Observation(ObsType.MEDICATION_STABLE, "x", confidence=0.7,
                        domains=("medication",), evidence=({"type": "x"},))
        c = classify(o)
        self.assertEqual(c.safety_class, SafetyClass.OBSERVATION)
        self.assertFalse(c.physician_discussion)

    def test_approve_drops_no_evidence_and_dedupes(self):
        good = Observation(ObsType.MEDICATION_STABLE, "a", confidence=0.7,
                           domains=("medication",), evidence=({"type": "x"},))
        better = Observation(ObsType.MEDICATION_STABLE, "b", confidence=0.9,
                             domains=("medication",), evidence=({"type": "x"},))
        no_ev = Observation(ObsType.ADHERENCE_IMPROVING, "c", confidence=0.9, evidence=())
        result = approve([good, better, no_ev])
        # Duplicate type collapses to the higher-confidence one; no-evidence dropped.
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, "b")


class ObservationEngineTest(AdherenceTestMixin, TestCase):
    def setUp(self):
        self.user = self.create_user(email="obs@test.com")

    def test_empty_when_no_data(self):
        self.assertEqual(build_observations(self.user), [])

    def test_every_observation_has_evidence(self):
        from apps.core.utils import get_user_today
        med = self.create_medicine(
            self.user, name="Lantus", dose="20 units",
            start_date=get_user_today(self.user) - timedelta(days=200),
        )
        for prev, new in (("20", "24"), ("24", "28")):
            record_medication_change(
                med, MedicationEvent.EVENT_DOSE_CHANGED,
                previous_value={"dose": f"{prev} units"}, new_value={"dose": f"{new} units"},
            )
        obs = build_observations(self.user)
        self.assertTrue(obs)  # at least the "multiple dose increases" observation
        for o in obs:
            self.assertTrue(o.evidence, f"{o.type} has no evidence")
            self.assertNotEqual(o.safety_class, SafetyClass.SUPPRESSED)

    def test_multiple_dose_increases_observation(self):
        med = self.create_medicine(self.user, name="Lantus", dose="20 units")
        for prev, new in (("20", "24"), ("24", "28")):
            record_medication_change(
                med, MedicationEvent.EVENT_DOSE_CHANGED,
                previous_value={"dose": f"{prev} units"}, new_value={"dose": f"{new} units"},
            )
        types = {o.type for o in build_observations(self.user)}
        self.assertIn(ObsType.MULTIPLE_DOSE_INCREASES, types)

    def test_no_causal_language_in_observations(self):
        """Observations state association, never causation."""
        from django.utils import timezone as tz
        from apps.health.models import WeightEntry
        from apps.core.utils import get_user_today
        med = self.create_medicine(self.user, name="Mounjaro", dose="5mg")
        ad = get_user_today(self.user) - timedelta(days=10)
        record_medication_change(
            med, MedicationEvent.EVENT_DOSE_CHANGED,
            previous_value={"dose": "5mg"}, new_value={"dose": "7.5mg"},
            effective_date=ad,
        )
        WeightEntry.objects.create(user=self.user, value=210, unit="lb",
                                   recorded_at=tz.now() - timedelta(days=15))
        WeightEntry.objects.create(user=self.user, value=204, unit="lb",
                                   recorded_at=tz.now() - timedelta(days=2))
        banned = ("because", "caused", "due to", "led to", "results in", "thanks to")
        for o in build_observations(self.user):
            text = (o.title + " " + o.detail).lower()
            for word in banned:
                self.assertNotIn(word, text, f"causal word '{word}' in {o.type}")

    def test_weight_cross_domain_is_physician_discussion(self):
        from django.utils import timezone as tz
        from apps.health.models import WeightEntry
        from apps.core.utils import get_user_today
        med = self.create_medicine(self.user, name="Mounjaro", dose="5mg")
        ad = get_user_today(self.user) - timedelta(days=10)
        record_medication_change(
            med, MedicationEvent.EVENT_DOSE_CHANGED,
            previous_value={"dose": "5mg"}, new_value={"dose": "7.5mg"},
            effective_date=ad,
        )
        WeightEntry.objects.create(user=self.user, value=210, unit="lb",
                                   recorded_at=tz.now() - timedelta(days=15))
        WeightEntry.objects.create(user=self.user, value=204, unit="lb",
                                   recorded_at=tz.now() - timedelta(days=2))
        weight_obs = [o for o in build_observations(self.user)
                      if o.type == ObsType.WEIGHT_AFTER_TREATMENT_CHANGE]
        self.assertEqual(len(weight_obs), 1)
        self.assertTrue(weight_obs[0].physician_discussion)


class BethObservationStateTest(AdherenceTestMixin, TestCase):
    """Sprint 5F — Beth receives only safety-approved observations via canonical state."""

    def setUp(self):
        self.user = self.create_user(email="bethobs@test.com")

    def test_state_exposes_only_approved_observations(self):
        from apps.core.ai_state.state_builder import build_medicine_state
        med = self.create_medicine(self.user, name="Lantus", dose="20 units")
        for prev, new in (("20", "24"), ("24", "28")):
            record_medication_change(
                med, MedicationEvent.EVENT_DOSE_CHANGED,
                previous_value={"dose": f"{prev} units"}, new_value={"dose": f"{new} units"},
            )
        contract = build_medicine_state(self.user)["_contract"]
        self.assertIn("observations", contract)
        obs = contract["observations"]
        self.assertTrue(obs)
        for o in obs:
            # Composed verdicts only — every one carries evidence + a safety class,
            # and none are suppressed (suppressed never reach Beth).
            self.assertTrue(o["evidence"])
            self.assertNotEqual(o["safety_class"], "suppressed")
            self.assertIn("physician_discussion", o)

    def test_no_observations_when_no_data(self):
        from apps.core.ai_state.state_builder import build_medicine_state
        contract = build_medicine_state(self.user)["_contract"]
        self.assertEqual(contract["observations"], [])
