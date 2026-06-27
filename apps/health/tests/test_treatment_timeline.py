"""
Sprint 4 — Treatment Timeline service tests.

Deterministic, evidence-first treatment history: ordering, dose-change
classification, provider changes, acquisition entries, summaries, evidence
references, empty timelines, and the no-duplicate / no-fabrication guarantees.
"""

from datetime import date, timedelta

from django.test import TestCase

from apps.health.medication_events import record_medication_change
from apps.health.models import Intake, MedicationEvent
from apps.health.treatment_timeline import (
    build_medication_timeline,
    build_treatment_summary,
)

from apps.health.tests.test_medicine_adherence import AdherenceTestMixin


class TimelineServiceTest(AdherenceTestMixin, TestCase):
    def setUp(self):
        self.user = self.create_user(email="timeline@test.com")

    def test_empty_timeline(self):
        self.assertEqual(build_medication_timeline(self.user), [])

    def test_started_event_appears_with_evidence(self):
        med = self.create_medicine(self.user, name="Metformin")
        entries = build_medication_timeline(self.user)
        started = [e for e in entries if e["kind"] == "started"]
        self.assertEqual(len(started), 1)
        e = started[0]
        self.assertEqual(e["title"], "Started Metformin")
        self.assertEqual(e["domain"], "medication")
        # 4F — evidence references the canonical MedicationEvent.
        self.assertEqual(e["evidence"]["type"], "MedicationEvent")
        self.assertIn("id", e["evidence"])

    def test_timeline_is_chronological_then_newest_first_option(self):
        med = self.create_medicine(self.user, name="Lantus", start_date=date(2026, 1, 1))
        med.pause("travel")
        med.resume()
        asc = build_medication_timeline(self.user)
        self.assertEqual(asc[0]["kind"], "started")          # oldest first
        desc = build_medication_timeline(self.user, newest_first=True)
        self.assertEqual(desc[0]["kind"], "resumed")          # newest first

    def test_dose_change_classified_increase_decrease(self):
        med = self.create_medicine(self.user, name="Lantus", dose="20 units")
        record_medication_change(
            med, MedicationEvent.EVENT_DOSE_CHANGED,
            previous_value={"dose": "20 units"}, new_value={"dose": "24 units"},
        )
        record_medication_change(
            med, MedicationEvent.EVENT_DOSE_CHANGED,
            previous_value={"dose": "24 units"}, new_value={"dose": "18 units"},
        )
        kinds = [e["kind"] for e in build_medication_timeline(self.user, intake=med)]
        self.assertIn("dose_increased", kinds)
        self.assertIn("dose_decreased", kinds)

    def test_provider_change_appears(self):
        med = self.create_medicine(self.user, name="Atorvastatin")
        record_medication_change(
            med, MedicationEvent.EVENT_PROVIDER_CHANGED,
            new_value={"provider": "Dr. New"},
        )
        kinds = [e["kind"] for e in build_medication_timeline(self.user, intake=med)]
        self.assertIn("provider_changed", kinds)

    def test_acquisition_confirmed_entry(self):
        from apps.health.medication_acquisition import create_manual_draft, confirm_draft
        from apps.health.models import MedicationScanDraft
        draft = create_manual_draft(self.user, {"name": "Vitamin D", "dose": "2000 IU"})
        confirm_draft(draft, MedicationScanDraft.ACTION_CREATE)
        kinds = [e["kind"] for e in build_medication_timeline(self.user)]
        self.assertIn("acquisition_confirmed", kinds)

    def test_no_duplicate_started_events_in_timeline(self):
        med = self.create_medicine(self.user, name="Solo")
        started = [
            e for e in build_medication_timeline(self.user, intake=med)
            if e["kind"] == "started"
        ]
        self.assertEqual(len(started), 1)

    def test_no_fabricated_history(self):
        """Timeline contains only recorded events — nothing invented."""
        med = self.create_medicine(self.user, name="Clean")
        entries = build_medication_timeline(self.user, intake=med)
        # Only the 'started' event exists; no phantom dose changes etc.
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["kind"], "started")


class TreatmentSummaryTest(AdherenceTestMixin, TestCase):
    def setUp(self):
        self.user = self.create_user(email="summary@test.com")

    def test_overall_summary_deterministic(self):
        self.create_medicine(self.user, name="Med A", start_date=date(2026, 1, 1))
        s = build_treatment_summary(self.user)
        self.assertIsNotNone(s["treatment_started_date"])
        self.assertGreaterEqual(s["treatment_duration_days"], 0)
        self.assertEqual(s["active_medication_count"], 1)
        self.assertIn(s["treatment_momentum"], ("stable", "adjusting", "actively_changing"))

    def test_per_intake_summary_dose_changes_and_provider(self):
        from apps.core.utils import get_user_today
        med = self.create_medicine(
            self.user, name="Lantus", dose="20 units",
            start_date=get_user_today(self.user) - timedelta(days=40),
        )
        record_medication_change(
            med, MedicationEvent.EVENT_DOSE_CHANGED,
            previous_value={"dose": "20 units"}, new_value={"dose": "24 units"},
        )
        s = build_treatment_summary(self.user, intake=med)
        self.assertEqual(s["dose_change_count"], 1)
        self.assertEqual(s["treatment_duration_days"], 40)
        self.assertIsInstance(s["provider_history"], list)
        self.assertIsInstance(s["longest_stable_period_days"], int)

    def test_momentum_stable_when_no_recent_changes(self):
        # A med started long ago with no recent changes → stable.
        self.create_medicine(self.user, name="Old", start_date=date(2025, 1, 1))
        # The backfill-less started event is dated 2025; >90d ago.
        s = build_treatment_summary(self.user)
        self.assertEqual(s["treatment_momentum"], "stable")


class CrossDomainTimelineTest(AdherenceTestMixin, TestCase):
    """Sprint 4C — medication events aligned with other domains (ordering only)."""

    def setUp(self):
        self.user = self.create_user(email="xdomain@test.com")

    def test_cross_domain_entries_owned_by_domain_with_evidence(self):
        from datetime import datetime
        from django.utils import timezone as tz
        from apps.health.models import WeightEntry, GlucoseEntry
        from apps.core.utils import get_user_today
        from apps.health.treatment_timeline import build_cross_domain_timeline

        today = get_user_today(self.user)
        WeightEntry.objects.create(user=self.user, value=210, unit="lb",
                                   recorded_at=tz.now())
        GlucoseEntry.objects.create(user=self.user, value=110, unit="mg/dL",
                                    recorded_at=tz.now())
        entries = build_cross_domain_timeline(
            self.user, today.replace(day=1), today,
        )
        domains = {e["domain"] for e in entries}
        self.assertIn("weight", domains)
        self.assertIn("glucose", domains)
        for e in entries:
            # Each entry stays owned by its source domain + has evidence.
            self.assertIn(e["evidence"]["type"], ("WeightEntry", "GlucoseEntry"))

    def test_full_timeline_merges_and_orders(self):
        from django.utils import timezone as tz
        from apps.health.models import WeightEntry
        from apps.health.treatment_timeline import build_full_timeline

        med = self.create_medicine(self.user, name="Metformin")
        WeightEntry.objects.create(user=self.user, value=205, unit="lb",
                                   recorded_at=tz.now())
        entries = build_full_timeline(self.user)
        domains = {e["domain"] for e in entries}
        self.assertIn("medication", domains)
        self.assertIn("weight", domains)
        # Sorted (newest first by default) — timestamps non-increasing.
        ts = [e["timestamp"] for e in entries if e["timestamp"]]
        self.assertEqual(ts, sorted(ts, reverse=True))

    def test_full_timeline_without_cross_domain(self):
        from apps.health.treatment_timeline import build_full_timeline
        self.create_medicine(self.user, name="Solo")
        entries = build_full_timeline(self.user, include_cross_domain=False)
        self.assertTrue(all(e["domain"] == "medication" for e in entries))


class BethTimelineStateTest(AdherenceTestMixin, TestCase):
    """Sprint 4E — treatment-history summary is in canonical state for Beth."""

    def setUp(self):
        self.user = self.create_user(email="bethtl@test.com")

    def test_state_exposes_treatment_history(self):
        from apps.core.ai_state.state_builder import build_medicine_state
        from apps.core.utils import get_user_today
        med = self.create_medicine(
            self.user, name="Lantus", dose="20 units",
            start_date=get_user_today(self.user) - timedelta(days=30),
        )
        record_medication_change(
            med, MedicationEvent.EVENT_DOSE_CHANGED,
            previous_value={"dose": "20 units"}, new_value={"dose": "24 units"},
        )
        history = build_medicine_state(self.user)["_contract"]["treatment"]["history"]
        self.assertGreaterEqual(history["treatment_duration_days"], 30)
        self.assertEqual(history["total_dose_changes"], 1)
        self.assertIn(history["treatment_momentum"], ("stable", "adjusting", "actively_changing"))
        self.assertIsNotNone(history["most_recent_change"])
