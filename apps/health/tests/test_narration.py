"""
Sprint 7 — Deterministic Narration Boundary tests.

The most important guarantees: narration is deterministic and adds no new facts,
no causal claims, no recommendations; chronology / confidence / safety class are
preserved; physician-discussion wording appears only when flagged; evidence links
remain intact; and explicit banned language never appears unless already present
in the deterministic observation.
"""

from datetime import timedelta

from django.test import TestCase

from apps.health.medication_events import record_medication_change
from apps.health.models import MedicationEvent
from apps.health.observations import Observation, ObsType, SafetyClass
from apps.health.observations.narration import (
    PHYSICIAN_SUFFIX,
    build_narration_view,
    build_narrations,
    render_narration,
)
from apps.health.observations.prioritization import prioritize_observations

from apps.health.tests.test_medicine_adherence import AdherenceTestMixin


# Words that must never be INTRODUCED by narration (only allowed if the source
# observation already contained them).
BANNED = ("caused", "because", "therefore", "your medication is working",
          "you should", "i recommend", "adjust your medication", "due to",
          "led to")


def _prioritized(obs):
    return prioritize_observations(obs, {})[0]


class NarrationRenderTest(TestCase):
    def test_summary_adds_no_new_facts(self):
        obs = Observation(ObsType.MULTIPLE_DOSE_REDUCTIONS,
                          "3 dose reductions in the last 90 days.",
                          confidence=0.85, domains=("medication",),
                          evidence=({"summary": "Dose changed on 2026-05-01"},),
                          safety_class=SafetyClass.OBSERVATION)
        n = render_narration(_prioritized([obs]))
        # Summary is exactly the observation title (no detail, not physician).
        self.assertEqual(n.summary, "3 dose reductions in the last 90 days.")

    def test_physician_suffix_only_when_flagged(self):
        flagged = Observation(ObsType.WEIGHT_AFTER_TREATMENT_CHANGE,
                              "Weight was lower after a treatment change.",
                              confidence=0.6, domains=("medication", "weight"),
                              evidence=({"summary": "x"},),
                              safety_class=SafetyClass.PHYSICIAN_DISCUSSION,
                              physician_discussion=True)
        plain = Observation(ObsType.MEDICATION_STABLE, "No changes in 120 days.",
                            confidence=0.7, domains=("medication",),
                            evidence=({"summary": "x"},),
                            safety_class=SafetyClass.OBSERVATION)
        n_flag = render_narration(_prioritized([flagged]))
        n_plain = render_narration(_prioritized([plain]))
        self.assertIn(PHYSICIAN_SUFFIX, n_flag.summary)
        self.assertTrue(n_flag.physician_discussion)
        self.assertNotIn(PHYSICIAN_SUFFIX, n_plain.summary)
        self.assertFalse(n_plain.physician_discussion)

    def test_confidence_and_safety_preserved(self):
        obs = Observation(ObsType.ADHERENCE_DECLINING, "Adherence is lower.",
                          confidence=0.62, domains=("medication",),
                          evidence=({"summary": "x"},),
                          safety_class=SafetyClass.OBSERVATION)
        n = render_narration(_prioritized([obs]))
        self.assertEqual(n.confidence, 0.62)        # never upgraded
        self.assertEqual(n.safety_class, SafetyClass.OBSERVATION)  # never weakened

    def test_tone_from_safety_class(self):
        obs = Observation(ObsType.GLUCOSE_AFTER_TREATMENT_CHANGE,
                          "Average glucose was lower around a treatment change.",
                          confidence=0.6, domains=("medication", "glucose"),
                          evidence=({"summary": "x"},),
                          safety_class=SafetyClass.PHYSICIAN_DISCUSSION,
                          physician_discussion=True)
        n = render_narration(_prioritized([obs]))
        self.assertEqual(n.tone, "calm_encouraging")

    def test_evidence_links_intact(self):
        ev = ({"type": "MedicationEvent", "id": 7, "summary": "Dose changed 2026-05-01"},)
        obs = Observation(ObsType.MULTIPLE_DOSE_INCREASES, "2 dose increases.",
                          confidence=0.85, domains=("medication",), evidence=ev,
                          safety_class=SafetyClass.OBSERVATION)
        n = render_narration(_prioritized([obs]))
        self.assertEqual(n.evidence, ev)
        self.assertIn("Dose changed 2026-05-01", n.supporting_facts)

    def test_banned_language_never_introduced(self):
        # A neutral observation must not gain any banned/causal/recommendation word.
        obs = Observation(ObsType.WEIGHT_AFTER_TREATMENT_CHANGE,
                          "Weight was 6 lb lower after a treatment change on 2026-05-01.",
                          detail="Chronological association only — not a cause.",
                          confidence=0.6, domains=("medication", "weight"),
                          evidence=({"summary": "x"},),
                          safety_class=SafetyClass.PHYSICIAN_DISCUSSION,
                          physician_discussion=True)
        n = render_narration(_prioritized([obs]))
        text = n.summary.lower()
        source = (obs.title + " " + obs.detail).lower()
        for word in BANNED:
            if word in text:
                self.assertIn(word, source, f"narration introduced banned '{word}'")


class NarrationDeterminismTest(AdherenceTestMixin, TestCase):
    def setUp(self):
        self.user = self.create_user(email="narr@test.com")

    def test_identical_input_identical_narration(self):
        med = self.create_medicine(self.user, name="Lantus", dose="20 units")
        for prev, new in (("20", "24"), ("24", "28")):
            record_medication_change(
                med, MedicationEvent.EVENT_DOSE_CHANGED,
                previous_value={"dose": f"{prev} units"}, new_value={"dose": f"{new} units"},
            )
        a = build_narrations(self.user)
        b = build_narrations(self.user)
        self.assertEqual([n["summary"] for n in a], [n["summary"] for n in b])
        self.assertTrue(a)

    def test_every_narration_traceable_to_evidence(self):
        med = self.create_medicine(self.user, name="Lantus", dose="20 units")
        for prev, new in (("20", "24"), ("24", "28")):
            record_medication_change(
                med, MedicationEvent.EVENT_DOSE_CHANGED,
                previous_value={"dose": f"{prev} units"}, new_value={"dose": f"{new} units"},
            )
        for n in build_narrations(self.user):
            self.assertTrue(n["evidence"], f"{n['observation_type']} narration lost evidence")

    def test_no_banned_language_across_real_narrations(self):
        from django.utils import timezone as tz
        from apps.health.models import WeightEntry
        from apps.core.utils import get_user_today
        med = self.create_medicine(self.user, name="Mounjaro", dose="5mg")
        ad = get_user_today(self.user) - timedelta(days=10)
        record_medication_change(
            med, MedicationEvent.EVENT_DOSE_CHANGED,
            previous_value={"dose": "5mg"}, new_value={"dose": "7.5mg"}, effective_date=ad,
        )
        WeightEntry.objects.create(user=self.user, value=210, unit="lb",
                                   recorded_at=tz.now() - timedelta(days=15))
        WeightEntry.objects.create(user=self.user, value=204, unit="lb",
                                   recorded_at=tz.now() - timedelta(days=2))
        for n in build_narrations(self.user):
            text = n["summary"].lower()
            for word in ("caused", "because", "therefore", "you should",
                         "i recommend", "your medication is working"):
                self.assertNotIn(word, text)


class NarrationViewUITest(AdherenceTestMixin, TestCase):
    def setUp(self):
        from django.test import Client
        self.client = Client()
        self.user = self.create_user(email="narrui@test.com")
        self.client.force_login(self.user)

    def test_noticed_page_renders(self):
        from django.urls import reverse
        med = self.create_medicine(self.user, name="Lantus", dose="20 units")
        for prev, new in (("20", "24"), ("24", "28")):
            record_medication_change(
                med, MedicationEvent.EVENT_DOSE_CHANGED,
                previous_value={"dose": f"{prev} units"}, new_value={"dose": f"{new} units"},
            )
        resp = self.client.get(reverse("health:medication_noticed"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Noticed")
        self.assertContains(resp, "Deterministic observations")

    def test_noticed_empty_state(self):
        from django.urls import reverse
        resp = self.client.get(reverse("health:medication_noticed"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Nothing notable yet")

    def test_state_exposes_narrations_for_beth(self):
        from apps.core.ai_state.state_builder import build_medicine_state
        med = self.create_medicine(self.user, name="Lantus", dose="20 units")
        for prev, new in (("20", "24"), ("24", "28")):
            record_medication_change(
                med, MedicationEvent.EVENT_DOSE_CHANGED,
                previous_value={"dose": f"{prev} units"}, new_value={"dose": f"{new} units"},
            )
        contract = build_medicine_state(self.user)["_contract"]
        self.assertIn("narrations", contract)
        self.assertIn("narration_groups", contract)
        self.assertTrue(contract["narrations"])
        for n in contract["narrations"]:
            self.assertIn("summary", n)
            self.assertIn("tone", n)
            self.assertIn("safety_class", n)
