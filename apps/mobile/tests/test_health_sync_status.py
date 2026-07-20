"""
Tests for the deterministic Health Sync status platform truth.

Covers:
  * `health_ingest` persists a per-metric-type result breakdown on the run.
  * `/api/mobile/health/sync-status/` returns the rich `sync_health` payload.
  * `build_health_sync_status` reports the truth for the reported bug
    (Steps enabled but no records arrive), healthy sources, staleness, and the
    human sync summary — all from persisted records, never fabricated.
"""
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.health.models import GlucoseEntry, StepsEntry, WeightEntry
from apps.health.services.health_sync_status import build_health_sync_status
from apps.mobile.models import HealthIngestionRun, MobileAPIToken, MobileDevice

User = get_user_model()


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"])
class HealthSyncTelemetryTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email="sync@example.com", password="x")
        self.device = MobileDevice.objects.create(user=self.user, device_id="dev-uuid")
        self.token, self.raw_token = MobileAPIToken.create_token(
            user=self.user, device=self.device
        )
        self.today = timezone.now().date().isoformat()

    def _headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_token}"}

    def _ingest(self, metrics):
        resp = self.client.post(
            "/api/mobile/health/ingest/",
            data=json.dumps({"metrics": metrics}),
            content_type="application/json",
            **self._headers(),
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.json()

    # ---- per-type telemetry on the run ----
    def test_ingest_records_per_type_results(self):
        self._ingest([
            {"type": "weight", "date": self.today, "value": 286.4, "unit": "lbs",
             "source": "apple_health", "sync_id": "w1"},
            {"type": "steps", "date": self.today, "value": 8500,
             "source": "apple_health", "sync_id": "s1"},
            {"type": "steps", "date": self.today, "value": 8500,
             "source": "apple_health", "sync_id": "s1"},  # duplicate -> skipped
        ])
        run = HealthIngestionRun.objects.filter(user=self.user).latest("created_at")
        results = run.metric_type_results
        self.assertEqual(results["weight"]["created"], 1)
        self.assertEqual(results["steps"]["created"], 1)
        self.assertEqual(results["steps"]["skipped"], 1)

    def test_ingest_records_failed_per_type(self):
        # Missing value -> the steps handler raises -> counted as failed.
        self._ingest([
            {"type": "steps", "date": self.today, "source": "apple_health", "sync_id": "bad"},
        ])
        run = HealthIngestionRun.objects.filter(user=self.user).latest("created_at")
        self.assertEqual(run.metric_type_results["steps"]["failed"], 1)

    # ---- client_debug capture (generic device→server diagnostic channel) ----
    def test_ingest_stores_client_debug(self):
        resp = self.client.post(
            "/api/mobile/health/ingest/",
            data=json.dumps({
                "metrics": [{"type": "weight", "date": self.today, "value": 200,
                             "unit": "lbs", "source": "apple_health", "sync_id": "w1"}],
                "client_debug": {"steps": {"raw_samples": 412, "built": 7, "sent": 7}},
            }),
            content_type="application/json",
            **self._headers(),
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        run = HealthIngestionRun.objects.filter(user=self.user).latest("created_at")
        self.assertEqual(run.client_debug["steps"]["raw_samples"], 412)

    # ---- heart-rate ingest must never fabricate a future timestamp ----
    def test_heart_rate_preserves_real_sample_time(self):
        """When the payload carries a real sample instant, it is stored verbatim —
        never discarded for a noon default."""
        from apps.health.models import HeartRateEntry
        sample = (timezone.now() - timedelta(hours=3)).replace(microsecond=0)
        self._ingest([
            {"type": "heart_rate", "date": self.today, "resting_hr": 57,
             "recorded_at": sample.isoformat(), "source": "apple_health", "sync_id": "hr1"},
        ])
        hr = HeartRateEntry.objects.get(sync_id="hr1")
        self.assertEqual(hr.recorded_at, sample)

    def test_heart_rate_date_only_is_never_in_the_future(self):
        """A date-only daily aggregate must never land in the future (the noon-default
        bug). With no sample time, recorded_at is clamped to no later than now."""
        from apps.health.models import HeartRateEntry
        self._ingest([
            {"type": "heart_rate", "date": self.today, "resting_hr": 60,
             "source": "apple_health", "sync_id": "hr2"},
        ])
        hr = HeartRateEntry.objects.get(sync_id="hr2")
        self.assertLessEqual(hr.recorded_at, timezone.now())

    def test_heart_rate_self_heals_noon_default_on_resync(self):
        """A legacy noon/future-defaulted row heals to the real sample time when Apple
        Health re-pushes the same sample."""
        from apps.health.models import HeartRateEntry
        stale_noon = timezone.make_aware(
            timezone.datetime.combine(timezone.now().date(), timezone.datetime.min.time().replace(hour=12))
        )
        HeartRateEntry.objects.create(
            user=self.user, source="apple_health", bpm=60, context="resting",
            recorded_at=stale_noon, sync_id="hr3",
        )
        real = (timezone.now() - timedelta(hours=5)).replace(microsecond=0)
        self._ingest([
            {"type": "heart_rate", "date": self.today, "resting_hr": 60,
             "recorded_at": real.isoformat(), "source": "apple_health", "sync_id": "hr3"},
        ])
        hr = HeartRateEntry.objects.get(sync_id="hr3")
        self.assertEqual(hr.recorded_at, real)

    # ---- the endpoint exposes the rich truth ----
    def test_sync_status_returns_sync_health(self):
        self._ingest([
            {"type": "steps", "date": self.today, "value": 8500,
             "source": "apple_health", "sync_id": "s1"},
        ])
        resp = self.client.get("/api/mobile/health/sync-status/", **self._headers())
        self.assertEqual(resp.status_code, 200, resp.content)
        health = resp.json()["sync_health"]
        self.assertIn("data_types", health)
        steps = next(d for d in health["data_types"] if d["key"] == "steps")
        self.assertEqual(steps["status"], "healthy")


class BuildHealthSyncStatusTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="status@example.com", password="x")
        self.now = timezone.now()
        self.today = self.now.date()

    def _steps(self, days_ago, count=8000):
        return StepsEntry.objects.create(
            user=self.user, source="apple_health", count=count,
            logged_date=self.today - timedelta(days=days_ago),
        )

    def test_steps_no_data_is_visible_and_actionable(self):
        # The reported bug: sync verifiably works (a run completed with weight), yet
        # Steps never arrives. Only then may WLJ claim Steps is missing and offer the
        # Health-settings fix — the claim rests on a completed run, not record presence.
        WeightEntry.objects.create(
            user=self.user, source="apple_health", value=286,
            recorded_at=self.now,
        )
        run = HealthIngestionRun.objects.create(user=self.user, metrics_received=1)
        run.mark_completed(1, 0, 0, type_results={"weight": {"created": 1, "updated": 0,
                                                             "skipped": 0, "failed": 0}})
        st = build_health_sync_status(self.user, now=self.now)
        steps = next(d for d in st["data_types"] if d["key"] == "steps")
        self.assertEqual(steps["status"], "no_data")
        self.assertEqual(steps["message"], "No records received")
        # And it surfaces as the single actionable issue (sync is otherwise active).
        self.assertTrue(any(i["key"] == "steps" for i in st["issues"]))

    def test_no_issue_when_nothing_synced_yet(self):
        # A brand-new account shouldn't be spammed with per-type issues.
        st = build_health_sync_status(self.user, now=self.now)
        self.assertEqual(st["issues"], [])
        self.assertEqual(st["active_types_count"], 0)

    def test_healthy_and_summary(self):
        self._steps(0)
        run = HealthIngestionRun.objects.create(user=self.user, metrics_received=1)
        run.mark_completed(1, 0, 0, type_results={"steps": {"created": 1, "updated": 0, "skipped": 0, "failed": 0}})
        st = build_health_sync_status(self.user, now=self.now)
        steps = next(d for d in st["data_types"] if d["key"] == "steps")
        self.assertEqual(steps["status"], "healthy")
        self.assertTrue(any(x["key"] == "steps" for x in st["last_sync_summary"]["imported"]))
        self.assertEqual(st["newest_data"]["key"], "steps")

    def test_old_steps_records_alone_never_raise_a_sync_issue(self):
        """Redesigned 2026-07-17: record age is ACTIVITY, never proof of a sync fault.

        Steps 5 days old (cadence 2d) used to render "Steps has not synced in 5 days".
        With a healthy recent ingestion run, the honest truth is: importing fine, just
        no recent records.
        """
        self._steps(5)
        run = HealthIngestionRun.objects.create(user=self.user, metrics_received=1)
        run.mark_completed(0, 0, 1, type_results={"steps": {"created": 0, "updated": 0,
                                                            "skipped": 1, "failed": 0}})
        st = build_health_sync_status(self.user, now=self.now)
        steps = next(d for d in st["data_types"] if d["key"] == "steps")
        self.assertEqual(steps["status"], "idle")
        self.assertEqual(steps["import_health"], "ok")
        self.assertEqual(steps["source_activity"], "none_recently")
        self.assertEqual(st["overall_health"]["status"], "healthy")
        self.assertFalse(any(i["key"] == "steps" for i in st["issues"]))
        for i in st["issues"]:
            self.assertNotIn("has not synced", i["message"])

    def test_irregular_source_is_idle_not_stale(self):
        # Weight is irregular by nature — an old weigh-in is not a "stale" alarm.
        WeightEntry.objects.create(
            user=self.user, source="apple_health", value=286,
            recorded_at=self.now - timedelta(days=20),
        )
        st = build_health_sync_status(self.user, now=self.now)
        weight = next(d for d in st["data_types"] if d["key"] == "weight")
        self.assertEqual(weight["status"], "idle")
        self.assertFalse(any(i["key"] == "weight" for i in st["issues"]))

    # ── Truth bug 1: a future timestamp must never be surfaced as "newest data" ──
    def test_future_dated_record_is_never_surfaced_as_future(self):
        """A noon-defaulted heart-rate row synced in the morning lands in the FUTURE.
        The Health Sync truth must never present that future instant — it clamps to the
        moment the row was actually received (created_at), never later than ``now``."""
        from apps.health.models import HeartRateEntry
        # A completed run so the account is otherwise healthy.
        run = HealthIngestionRun.objects.create(user=self.user, metrics_received=1)
        run.mark_completed(1, 0, 0, type_results={"heart_rate": {"created": 1, "updated": 0,
                                                                  "skipped": 0, "failed": 0}})
        future_noon = self.now.replace(hour=12, minute=0, second=0, microsecond=0)
        if future_noon <= self.now:                      # test running after noon
            future_noon = self.now + timedelta(hours=6)
        hr = HeartRateEntry.objects.create(
            user=self.user, source="apple_health", bpm=58,
            context="resting", recorded_at=future_noon,
        )
        st = build_health_sync_status(self.user, now=self.now)
        heart = next(d for d in st["data_types"] if d["key"] == "heart_rate")
        # The displayed instant is clamped into the past (never later than now), and the
        # fabricated future value is never surfaced.
        self.assertIsNotNone(heart["last_record_at"])
        self.assertLessEqual(heart["last_record_at"], self.now.isoformat())
        self.assertNotEqual(heart["last_record_at"], hr.recorded_at.isoformat())
        self.assertGreaterEqual(heart["days_since_last_record"], 0)
        # And the account-level "newest_data" surface is likewise never in the future.
        if st["newest_data"]:
            self.assertLessEqual(st["newest_data"]["at"], self.now.isoformat())

    # ── Truth bug 2: "healthy" requires a VERIFIED completed sync, not records ──
    def test_records_without_a_completed_run_are_not_healthy(self):
        """Records exist but no ingestion run ever completed → status must be "setup"
        (Not yet synced) with last_sync None (Never) — never "healthy"/"Never" together."""
        WeightEntry.objects.create(
            user=self.user, source="apple_health", value=200, recorded_at=self.now,
        )
        st = build_health_sync_status(self.user, now=self.now)
        self.assertEqual(st["active_types_count"], 1)          # a record IS present
        self.assertEqual(st["overall_health"]["status"], "setup")
        self.assertIsNone(st["last_sync"])                     # → client shows "Never"

    def test_in_flight_run_is_not_yet_healthy(self):
        """A run that is still processing (never marked completed) is not proof of sync."""
        WeightEntry.objects.create(
            user=self.user, source="apple_health", value=200, recorded_at=self.now,
        )
        HealthIngestionRun.objects.create(
            user=self.user, metrics_received=1, status="processing",
        )
        st = build_health_sync_status(self.user, now=self.now)
        self.assertEqual(st["overall_health"]["status"], "setup")
        self.assertIsNone(st["last_sync"])

    def test_completed_run_is_healthy_with_a_real_last_sync(self):
        """A completed run → healthy AND a concrete last_sync. The badge and
        "Last synced" derive from the SAME run, so they always agree."""
        self._steps(0)
        run = HealthIngestionRun.objects.create(user=self.user, metrics_received=1)
        run.mark_completed(1, 0, 0, type_results={"steps": {"created": 1, "updated": 0,
                                                            "skipped": 0, "failed": 0}})
        st = build_health_sync_status(self.user, now=self.now)
        self.assertEqual(st["overall_health"]["status"], "healthy")
        self.assertIsNotNone(st["last_sync"])
        self.assertEqual(st["last_sync"]["ingestion_id"], run.id)
        self.assertIn(st["last_sync"]["status"], ("completed", "partial"))

    def test_earlier_success_survives_a_later_in_flight_run(self):
        """If the latest run is in-flight but an earlier run completed, the account has
        verifiably synced — stay healthy, and last_sync points at the earlier success."""
        self._steps(0)
        done = HealthIngestionRun.objects.create(user=self.user, metrics_received=1)
        done.mark_completed(1, 0, 0, type_results={"steps": {"created": 1, "updated": 0,
                                                            "skipped": 0, "failed": 0}})
        HealthIngestionRun.objects.create(
            user=self.user, metrics_received=1, status="processing",
        )
        st = build_health_sync_status(self.user, now=self.now)
        self.assertEqual(st["overall_health"]["status"], "healthy")
        self.assertEqual(st["last_sync"]["ingestion_id"], done.id)
