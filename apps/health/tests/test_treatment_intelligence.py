"""
Sprint 10 — Treatment Intelligence foundation tests.

Proves Treatment Intelligence composes OVER Medication Intelligence: models +
canonical ownership, plan↔intake / plan↔goal linking, the treatment state builder
(reads ledger + cached observations + live domain metrics, no recompute), the
dashboard, telemetry, empty states, and the inherited safety guardrails.
"""

from datetime import date, timedelta

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.health.medication_events import record_medication_change
from apps.health.models import (
    Intake,
    MedicalCondition,
    MedicationEvent,
    TreatmentGoal,
    TreatmentPlan,
    WeightEntry,
)
from apps.health.treatment_intelligence import build_treatment_state

from apps.health.tests.test_medicine_adherence import AdherenceTestMixin

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                      "LOCATION": "tx-intel"}}


class TreatmentModelTest(AdherenceTestMixin, TestCase):
    def setUp(self):
        self.user = self.create_user(email="txmodel@test.com")

    def test_models_create_and_link(self):
        cond = MedicalCondition.objects.create(user=self.user, name="Type 2 Diabetes")
        plan = TreatmentPlan.objects.create(
            user=self.user, name="Diabetes management", condition=cond,
            started_date=date(2026, 1, 1),
        )
        med = self.create_medicine(self.user, name="Metformin")
        plan.intakes.add(med)
        goal = TreatmentGoal.objects.create(
            treatment_plan=plan, name="Improve A1C",
            metric_key=TreatmentGoal.METRIC_A1C, direction=TreatmentGoal.DIRECTION_LOWER,
        )
        # Relations resolve; the plan groups (does not own) the intake.
        self.assertEqual(plan.condition, cond)
        self.assertIn(med, plan.intakes.all())
        self.assertIn(med, Intake.objects.filter(treatment_plans=plan))
        self.assertEqual(plan.goals.first(), goal)
        # The Intake itself is unchanged — Treatment Intelligence owns no med truth.
        med.refresh_from_db()
        self.assertEqual(med.name, "Metformin")


class TreatmentStateTest(AdherenceTestMixin, TestCase):
    def setUp(self):
        self.user = self.create_user(email="txstate@test.com")

    def _plan_with_med(self):
        plan = TreatmentPlan.objects.create(user=self.user, name="Diabetes management")
        med = self.create_medicine(self.user, name="Lantus", dose="20 units")
        plan.intakes.add(med)
        return plan, med

    def test_state_composes_meds_goals_and_watching(self):
        plan, med = self._plan_with_med()
        TreatmentGoal.objects.create(
            treatment_plan=plan, name="Support weight loss",
            metric_key=TreatmentGoal.METRIC_WEIGHT, direction=TreatmentGoal.DIRECTION_LOWER,
        )
        WeightEntry.objects.create(user=self.user, value=205, unit="lb",
                                   recorded_at=timezone.now())
        state = build_treatment_state(self.user)
        self.assertTrue(state["has_plans"])
        p = state["active_plans"][0]
        self.assertIn("Lantus", p["medications"])
        self.assertEqual(len(p["goals"]), 1)
        # Tracked outcome READ live from the canonical Weight domain.
        watched = {w["metric"]: w["current_value"] for w in p["watching"]}
        self.assertIn("Weight", watched)
        self.assertIn("205", watched["Weight"])

    def test_recent_changes_come_from_ledger_not_recomputed(self):
        plan, med = self._plan_with_med()
        record_medication_change(
            med, MedicationEvent.EVENT_DOSE_CHANGED,
            previous_value={"dose": "20 units"}, new_value={"dose": "24 units"},
        )
        p = build_treatment_state(self.user)["active_plans"][0]
        self.assertTrue(any("Lantus" in c["medicine"] for c in p["recent_changes"]))
        # Treatment state carries NO adherence recompute — it owns no med math.
        self.assertNotIn("adherence", p)
        self.assertNotIn("adherence_7d", p)

    def test_empty_state(self):
        state = build_treatment_state(self.user)
        self.assertFalse(state["has_plans"])
        self.assertEqual(state["active_plans"], [])

    def test_beth_state_exposes_treatment_plans(self):
        from apps.core.ai_state.state_builder import build_medicine_state
        self._plan_with_med()
        contract = build_medicine_state(self.user)["_contract"]
        self.assertIn("treatment_plans", contract)
        self.assertTrue(contract["treatment_plans"]["has_plans"])


class TreatmentSafetyTest(AdherenceTestMixin, TestCase):
    """10G — Treatment Intelligence inherits the medication safety rules."""

    def setUp(self):
        self.user = self.create_user(email="txsafe@test.com")

    def test_no_clinical_claim_language_in_state(self):
        plan = TreatmentPlan.objects.create(
            user=self.user, name="Diabetes management",
            goal_narrative="Track glucose and weight over time.",
        )
        med = self.create_medicine(self.user, name="Mounjaro", dose="5mg")
        plan.intakes.add(med)
        TreatmentGoal.objects.create(treatment_plan=plan, name="Support weight loss",
                                     metric_key=TreatmentGoal.METRIC_WEIGHT)
        state = build_treatment_state(self.user)
        p = state["active_plans"][0]
        text = " ".join([p["summary"], p["goal_narrative"]]
                        + [o["summary"] for o in p["observations"]]).lower()
        banned = ("caused", "because", "therefore", "you should", "i recommend",
                  "adjust your", "your medication is working", "diagnos",
                  "is working", "effective treatment")
        for word in banned:
            self.assertNotIn(word, text, f"clinical/causal phrasing '{word}' in treatment state")

    def test_does_not_create_duplicate_med_models(self):
        """Composition only — no shadow medication/adherence/history tables."""
        plan = TreatmentPlan.objects.create(user=self.user, name="Plan")
        med = self.create_medicine(self.user, name="Metformin")
        plan.intakes.add(med)
        # The plan references the canonical Intake + ledger; it stores none of it.
        self.assertEqual(plan.intakes.count(), 1)
        self.assertEqual(Intake.objects.filter(user=self.user).count(), 1)


@override_settings(CACHES=LOCMEM)
class TreatmentTelemetryTest(AdherenceTestMixin, TestCase):
    def setUp(self):
        self.user = self.create_user(email="txtel@test.com")
        cache.clear()

    def test_ops_snapshot(self):
        from apps.health.treatment_intelligence import (
            compute_treatment_intelligence_ops,
            get_treatment_intelligence_ops,
        )
        self.assertIsNone(get_treatment_intelligence_ops())
        # A plan with no goals + no intakes.
        TreatmentPlan.objects.create(user=self.user, name="Bare plan")
        snap = compute_treatment_intelligence_ops()
        self.assertEqual(snap["active_plans"], 1)
        self.assertEqual(snap["plans_without_goals"], 1)
        self.assertEqual(snap["plans_without_interventions"], 1)
        self.assertIsNotNone(get_treatment_intelligence_ops())


class TreatmentDashboardUITest(AdherenceTestMixin, TestCase):
    def setUp(self):
        self.client = Client()
        self.user = self.create_user(email="txui@test.com")
        self.client.force_login(self.user)

    def test_dashboard_renders_plan(self):
        from django.urls import reverse
        plan = TreatmentPlan.objects.create(user=self.user, name="Diabetes management")
        med = self.create_medicine(self.user, name="Metformin")
        plan.intakes.add(med)
        resp = self.client.get(reverse("health:treatment_dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Treatment Plans")
        self.assertContains(resp, "Diabetes management")
        self.assertContains(resp, "Metformin")

    def test_dashboard_empty_state(self):
        from django.urls import reverse
        resp = self.client.get(reverse("health:treatment_dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "No treatment plans yet")
