"""Telemetry-truth proof: ingested Apple-Health data flips the Health Sync registry
status off ``no_data`` — across every model-sharing pattern the registry uses.

This validates the Phase A registry expansion against REAL ingested data (the contract
test proves it runs on an empty account; this proves it tells the truth once data
arrives). It exercises:
  * a core daily type on its own model (steps → StepsEntry.count),
  * a shared-FIELD type on a rollup model (exercise_minutes → StepsEntry.exercise_minutes),
  * a discriminator/field type on a shared model (walking_speed → MobilityEntry.walking_speed),
  * a nightly-rollup type (sleep → SleepEntry) with full sleep-STAGE ingestion end to end,
  * idempotent re-sync (second identical push is skipped).
"""
from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.health.models import SleepEntry, StepsEntry
from apps.health.services.health_sync_status import build_health_sync_status
from apps.mobile.views import process_health_metric
from apps.users.models import TermsAcceptance, User


class HealthSyncTelemetryTruthTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="hk_telemetry@test.com", password="x")
        TermsAcceptance.objects.create(
            user=self.user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.today = timezone.localdate().isoformat()

    def _status_for(self, status, key):
        return next(d for d in status["data_types"] if d["key"] == key)

    def test_ingested_types_report_active_across_sharing_patterns(self):
        # Core daily type (its own model).
        self.assertEqual(process_health_metric(self.user, {
            "type": "steps", "date": self.today, "value": 8200,
            "source": "apple_health", "sync_id": "steps-1",
        }), "created")
        # Shared FIELD on the same rollup model (StepsEntry.exercise_minutes) — this
        # updates the SAME StepsEntry row `steps` created for the day, so the result is
        # "updated" (one daily row holds both) — still a persist, which is the point.
        self.assertIn(process_health_metric(self.user, {
            "type": "exercise_minutes", "date": self.today, "exercise_minutes_value": 42,
            "source": "apple_health", "sync_id": "exmin-1",
        }), ("created", "updated"))
        # Discriminated/field type on a shared model (MobilityEntry.walking_speed).
        self.assertIn(process_health_metric(self.user, {
            "type": "walking_speed", "date": self.today, "walking_speed_value": 3.1,
            "source": "apple_health", "sync_id": "wspeed-1",
        }), ("created", "updated"))

        status = build_health_sync_status(self.user)

        # Every ingested type reports NON-no_data (telemetry now reflects reality).
        for key in ("steps", "exercise_minutes", "walking_speed"):
            self.assertNotEqual(
                self._status_for(status, key)["status"], "no_data",
                f"{key} was ingested but telemetry still says no_data",
            )
        # A DIFFERENT StepsEntry field that was NOT ingested stays no_data — proving
        # presence_filter correctly distinguishes types that share a model.
        self.assertEqual(self._status_for(status, "flights_climbed")["status"], "no_data")

        # Category grouping reflects the active counts.
        by_cat = {c["key"]: c for c in status["categories"]}
        self.assertGreaterEqual(by_cat["activity"]["active_count"], 2)  # steps + exercise_minutes
        self.assertGreaterEqual(by_cat["mobility"]["active_count"], 1)  # walking_speed
        self.assertGreaterEqual(status["active_types_count"], 3)

    def test_sleep_stages_persist_end_to_end(self):
        metric = {
            "type": "sleep", "date": "2026-07-11", "total_minutes": 470,
            "deep_minutes": 78, "rem_minutes": 96, "light_minutes": 260, "awake_minutes": 36,
            "bedtime": "2026-07-10T22:07:00Z", "wake_time": "2026-07-11T05:57:00Z",
            "source": "apple_health", "sync_id": "sleep-2026-07-11",
        }
        self.assertEqual(process_health_metric(self.user, metric), "created")

        entry = SleepEntry.objects.get(user=self.user, source="apple_health")
        self.assertEqual(entry.stage_deep_minutes, 78)
        self.assertEqual(entry.stage_rem_minutes, 96)
        self.assertEqual(entry.stage_light_minutes, 260)
        self.assertEqual(entry.stage_awake_minutes, 36)
        # asleep = total in bed - awake
        self.assertEqual(entry.asleep_duration_minutes, 470 - 36)

    def test_height_and_waist_ingest_to_body_composition(self):
        """Gap closure: height + waist flow to BodyCompositionEntry (metric_name-keyed),
        the same canonical row a manual entry writes, and report active telemetry."""
        from apps.health.models import BodyCompositionEntry

        self.assertEqual(process_health_metric(self.user, {
            "type": "height", "date": self.today, "value": 70, "unit": "in",
            "source": "apple_health", "sync_id": "height-x",
        }), "created")
        self.assertEqual(process_health_metric(self.user, {
            "type": "waist", "date": self.today, "value": 34, "unit": "in",
            "source": "apple_health", "sync_id": "waist-x",
        }), "created")

        self.assertTrue(BodyCompositionEntry.objects.filter(
            user=self.user, metric_name="height", source="apple_health").exists())
        self.assertTrue(BodyCompositionEntry.objects.filter(
            user=self.user, metric_name="waist", source="apple_health").exists())

        status = build_health_sync_status(self.user)
        self.assertNotEqual(self._status_for(status, "height")["status"], "no_data")
        self.assertNotEqual(self._status_for(status, "waist")["status"], "no_data")

        # Idempotent: same date+value → skipped (body-comp keys on metric_name+date).
        self.assertEqual(process_health_metric(self.user, {
            "type": "height", "date": self.today, "value": 70, "unit": "in",
            "source": "apple_health", "sync_id": "height-x",
        }), "skipped")

    def test_resync_is_idempotent(self):
        metric = {
            "type": "sleep", "date": "2026-07-11", "total_minutes": 470,
            "deep_minutes": 78, "rem_minutes": 96, "light_minutes": 260, "awake_minutes": 36,
            "bedtime": "2026-07-10T22:07:00Z", "wake_time": "2026-07-11T05:57:00Z",
            "source": "apple_health", "sync_id": "sleep-2026-07-11",
        }
        self.assertEqual(process_health_metric(self.user, metric), "created")
        # Same payload again → no duplicate, no change.
        self.assertEqual(process_health_metric(self.user, dict(metric)), "skipped")
        self.assertEqual(SleepEntry.objects.filter(user=self.user).count(), 1)
        # A changed stage → recognized as an update, still one row.
        changed = dict(metric, deep_minutes=90)
        self.assertEqual(process_health_metric(self.user, changed), "updated")
        self.assertEqual(SleepEntry.objects.filter(user=self.user).count(), 1)
