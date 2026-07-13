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
        # The reported bug: other sources sync, Steps never arrives.
        WeightEntry.objects.create(
            user=self.user, source="apple_health", value=286,
            recorded_at=self.now,
        )
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

    def test_stale_steps_raises_issue(self):
        self._steps(5)  # last steps 5 days ago; steps stale_after_days=2
        st = build_health_sync_status(self.user, now=self.now)
        steps = next(d for d in st["data_types"] if d["key"] == "steps")
        self.assertEqual(steps["status"], "stale")
        self.assertTrue(any("has not synced" in i["message"] for i in st["issues"]))

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
