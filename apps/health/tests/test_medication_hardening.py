"""
Sprint 9 — Operational hardening tests.

9A caching + ledger invalidation, 9B telemetry snapshot, 9C resilience counter,
9E end-to-end walkthrough across representative medication types.
"""

from datetime import timedelta

from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from apps.health.medication_acquisition import confirm_draft, create_draft_from_scan
from apps.health.medication_events import record_medication_change
from apps.health.models import MedicationEvent, MedicationScanDraft

from apps.health.tests.test_medicine_adherence import AdherenceTestMixin

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                      "LOCATION": "med-hardening"}}


@override_settings(CACHES=LOCMEM)
class ObservationBundleCacheTest(AdherenceTestMixin, TestCase):
    def setUp(self):
        self.user = self.create_user(email="bundlecache@test.com")
        cache.clear()

    def test_bundle_cached_then_invalidated_by_ledger(self):
        from apps.health.observations.bundle import _cache_key, get_observation_bundle

        med = self.create_medicine(self.user, name="Lantus", dose="20 units")
        get_observation_bundle(self.user)
        # 9A — second read comes from cache.
        self.assertIsNotNone(cache.get(_cache_key(self.user.id)))
        # A ledger write busts the cache (event-driven freshness).
        record_medication_change(
            med, MedicationEvent.EVENT_DOSE_CHANGED,
            previous_value={"dose": "20 units"}, new_value={"dose": "24 units"},
        )
        self.assertIsNone(cache.get(_cache_key(self.user.id)))

    def test_bundle_use_cache_false_recomputes(self):
        from apps.health.observations.bundle import get_observation_bundle
        self.create_medicine(self.user, name="Metformin")
        a = get_observation_bundle(self.user)
        b = get_observation_bundle(self.user, use_cache=False)
        self.assertEqual(a["stats"]["approved"], b["stats"]["approved"])


@override_settings(CACHES=LOCMEM)
class TelemetryTest(AdherenceTestMixin, TestCase):
    def setUp(self):
        self.user = self.create_user(email="telem@test.com")
        cache.clear()

    def test_ops_read_is_none_until_computed(self):
        from apps.health.observations.telemetry import (
            compute_medication_intelligence_ops,
            get_medication_intelligence_ops,
        )
        self.assertIsNone(get_medication_intelligence_ops())
        # A confirmed + a pending draft.
        d1 = create_draft_from_scan(self.user, "medicine",
                                    [{"label": "Metformin", "details": {"dosage": "500mg"}}],
                                    scan_confidence=0.8)
        confirm_draft(d1, MedicationScanDraft.ACTION_CREATE)
        create_draft_from_scan(self.user, "supplement",
                               [{"label": "Vitamin D", "details": {"dosage": "2000 IU"}}],
                               scan_confidence=0.6)
        snap = compute_medication_intelligence_ops()
        self.assertEqual(snap["acquisition"]["confirmed"], 1)
        self.assertEqual(snap["acquisition"]["pending_review"], 1)
        self.assertIn("confidence_distribution", snap)
        # Now readable from cache.
        self.assertIsNotNone(get_medication_intelligence_ops())

    def test_physician_counter_increments(self):
        from apps.health.observations.telemetry import (
            PHYSICIAN_COUNTER_KEY,
            record_physician_summary_generated,
        )
        record_physician_summary_generated()
        record_physician_summary_generated()
        self.assertEqual(cache.get(PHYSICIAN_COUNTER_KEY), 2)


class EndToEndWalkthroughTest(AdherenceTestMixin, TestCase):
    """9E — representative medication types flow acquisition → … → physician summary."""

    def setUp(self):
        self.user = self.create_user(email="e2e@test.com")

    def test_full_walkthrough_across_med_types(self):
        from apps.health.models import Intake, Pharmacy, MedicalProvider
        from apps.health.physician_summary import build_physician_summary
        from apps.health.treatment_timeline import build_medication_timeline
        from apps.health.tests.acquisition_fixtures import ACQUISITION_SAMPLES

        # Acquire + confirm every representative type through the pipeline.
        for sample in ACQUISITION_SAMPLES:
            draft = create_draft_from_scan(
                self.user, sample["category"], sample["vision_items"],
                scan_confidence=sample["scan_confidence"],
            )
            self.assertIsNotNone(draft)
            intake = confirm_draft(draft, MedicationScanDraft.ACTION_CREATE)
            self.assertEqual(intake.intake_type, sample["expected_intake_type"])

        # Pharmacy-label samples linked structured records (no duplicates).
        self.assertTrue(Pharmacy.objects.filter(user=self.user).exists())
        self.assertTrue(MedicalProvider.objects.filter(user=self.user).exists())

        # Timeline reflects the started events (no fabrication).
        timeline = build_medication_timeline(self.user)
        self.assertTrue(any(e["kind"] == "started" for e in timeline))

        # Physician summary assembles cleanly with meds + supplements separated.
        s = build_physician_summary(self.user)
        self.assertFalse(s["is_empty"])
        self.assertTrue(s["medications"])
        self.assertTrue(s["supplements"])
        self.assertIn("disclaimer", s["header"])

    def test_duplicate_acquisition_updates_not_duplicates(self):
        from apps.health.medication_acquisition import detect_duplicates
        from apps.health.models import Intake
        self.create_medicine(self.user, name="Atorvastatin", dose="40mg")
        draft = create_draft_from_scan(
            self.user, "medicine",
            [{"label": "Atorvastatin", "details": {"name": "Atorvastatin", "dosage": "40mg"}}],
            scan_confidence=0.7,
        )
        dups = detect_duplicates(self.user, draft)
        self.assertEqual(len(dups), 1)
        confirm_draft(draft, MedicationScanDraft.ACTION_UPDATE,
                      target_intake=Intake.objects.get(user=self.user, name="Atorvastatin"))
        # No duplicate Intake created.
        self.assertEqual(Intake.objects.filter(user=self.user, name="Atorvastatin").count(), 1)
