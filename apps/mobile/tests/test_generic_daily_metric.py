"""
End-to-end ingest tests for the generic HealthKit fact store (HealthKitDailyMetric).

The generic store is the governed home for HealthKit quantity types that have no
bespoke domain model (cycling/swimming distance, swim strokes, Apple Move time,
wheelchair distance/pushes, downhill snow-sports distance, …). It is discriminated by
``metric_key`` and upserts idempotently per (user, metric_key, metric_date, source).

These tests drive the REAL mobile ingest endpoint (/api/mobile/health/ingest/) so the
full path is proven: payload → dispatch (HEALTH_METRIC_HANDLERS) → process_generic_daily_metric
→ validation → persistence → idempotency → provenance. No dedicated coverage existed
for this store before (only the Swift↔Django agreement contract), so this closes the gap.
"""

import json
from decimal import Decimal

from django.test import Client, TestCase

from apps.health.models import HealthKitDailyMetric
from apps.mobile.models import MobileAPIToken, MobileDevice
from apps.users.models import User

# Every metric_key currently routed to the generic fact store, with a sensible unit.
GENERIC_KEYS = [
    ("cycling_distance", "mi"),
    ("swimming_distance", "m"),
    ("swimming_strokes", "strokes"),
    ("move_minutes", "min"),
    ("wheelchair_distance", "mi"),
    ("push_count", "pushes"),
    ("snow_sports_distance", "mi"),
]


class GenericDailyMetricIngestTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="generic_metric@example.com", password="testpass123",
        )
        self.device = MobileDevice.objects.create(
            user=self.user, device_id="generic-metric-device",
        )
        self.token, self.raw_token = MobileAPIToken.create_token(
            user=self.user, device=self.device,
        )

    def _auth_headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_token}"}

    def _ingest(self, metric):
        response = self.client.post(
            "/api/mobile/health/ingest/",
            data=json.dumps({"metrics": [metric]}),
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["errors"], [])
        return data

    def _metric(self, key, unit, *, value, date="2024-02-10", source="apple_health", sync_id=None):
        return {
            "type": key, "date": date, "value": value, "unit": unit,
            "source": source, "sync_id": sync_id or f"{key}-{date}",
        }

    def test_every_generic_key_ingests_and_persists(self):
        """Each generic metric_key routes through the dispatch map and lands one row
        in HealthKitDailyMetric with value/unit/date/source provenance preserved."""
        for key, unit in GENERIC_KEYS:
            result = self._ingest(self._metric(key, unit, value=12.5))
            self.assertEqual(result["created"], 1, f"{key} should create a row")
            row = HealthKitDailyMetric.objects.get(user=self.user, metric_key=key)
            self.assertEqual(row.value, Decimal("12.500"))
            self.assertEqual(row.unit, unit)
            self.assertEqual(str(row.metric_date), "2024-02-10")
            self.assertEqual(row.source, "apple_health")

    def test_idempotent_repeat_converges_to_skipped(self):
        """Same payload three times: created, then skipped, then skipped."""
        metric = self._metric("wheelchair_distance", "mi", value=1.42)
        self.assertEqual(self._ingest(metric)["created"], 1)
        self.assertEqual(self._ingest(metric)["skipped"], 1)
        third = self._ingest(metric)
        self.assertEqual(third["created"], 0)
        self.assertEqual(third["skipped"], 1)
        self.assertEqual(
            HealthKitDailyMetric.objects.filter(
                user=self.user, metric_key="wheelchair_distance").count(),
            1, "idempotent upsert must never duplicate the (user, key, date, source) row",
        )

    def test_changed_value_updates_in_place(self):
        """A new value for the same (key, date, source) updates the existing row."""
        self._ingest(self._metric("push_count", "pushes", value=100))
        result = self._ingest(self._metric("push_count", "pushes", value=250))
        self.assertEqual(result["updated"], 1)
        row = HealthKitDailyMetric.objects.get(user=self.user, metric_key="push_count")
        self.assertEqual(row.value, Decimal("250.000"))
        self.assertEqual(
            HealthKitDailyMetric.objects.filter(user=self.user, metric_key="push_count").count(), 1)

    def test_distinct_keys_same_day_coexist(self):
        """Different metric_keys on the same day are independent rows (no collision)."""
        self._ingest(self._metric("cycling_distance", "mi", value=8))
        self._ingest(self._metric("snow_sports_distance", "mi", value=3))
        self.assertEqual(
            HealthKitDailyMetric.objects.filter(user=self.user, metric_date="2024-02-10").count(), 2)

    def test_distinct_sources_coexist(self):
        """The same key+date from different sources are distinct facts (provenance)."""
        self._ingest(self._metric("cycling_distance", "mi", value=8,
                                   source="apple_health", sync_id="cyc-apple"))
        self._ingest(self._metric("cycling_distance", "mi", value=9,
                                   source="manual", sync_id="cyc-manual"))
        self.assertEqual(
            HealthKitDailyMetric.objects.filter(
                user=self.user, metric_key="cycling_distance").count(), 2)

    def test_missing_value_is_rejected_not_persisted(self):
        """A payload without a value must error (not silently persist a null fact)."""
        response = self.client.post(
            "/api/mobile/health/ingest/",
            data=json.dumps({"metrics": [{
                "type": "wheelchair_distance", "date": "2024-02-10",
                "unit": "mi", "source": "apple_health", "sync_id": "bad-1",
            }]}),
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["created"], 0)
        self.assertTrue(data["errors"], "a value-less generic metric must surface an error")
        self.assertFalse(
            HealthKitDailyMetric.objects.filter(
                user=self.user, metric_key="wheelchair_distance").exists())
