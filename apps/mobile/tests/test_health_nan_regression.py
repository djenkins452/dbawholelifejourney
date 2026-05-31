"""
Regression test for the NaN ingestion crash introduced by the decimal-idempotency fix.

The decimal-idempotency change converted handler inputs from float() to
Decimal(str(value)). Apple HealthKit occasionally emits NaN for derived metrics.
Float NaN compares False in range guards, so before the change a NaN value passed
validation and was stored silently (Postgres numeric accepts NaN) — the sync
"completed successfully". After the change, the range guard performs a Decimal
ordering comparison (e.g. `Decimal('NaN') < 5`), which signals InvalidOperation,
so the whole metric crashed with "Internal error: InvalidOperation" and the sync
reported 1 error / 0 created / 0 updated.

The fix drops NaN-bearing metrics cleanly as "skipped" before dispatch. These
tests assert the sync completes with NO error and a valid metric in the same
batch is still processed.
"""

import json

from django.test import Client, TestCase

from apps.health.models import WeightEntry
from apps.mobile.models import MobileAPIToken, MobileDevice
from apps.users.models import User

NAN = float("nan")
D = "2024-01-15"


class HealthIngestNaNRegressionTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email="nan-regress@example.com", password="x")
        self.device = MobileDevice.objects.create(user=self.user, device_id="nan-regress-dev")
        self.token, self.raw_token = MobileAPIToken.create_token(user=self.user, device=self.device)

    def _ingest(self, metrics):
        response = self.client.post(
            "/api/mobile/health/ingest/",
            # allow_nan=True (json default) so NaN reaches the server like a permissive client
            data=json.dumps({"metrics": metrics}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_token}",
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_nan_weight_skipped_not_errored(self):
        data = self._ingest([
            {"type": "weight", "date": D, "value": NAN, "unit": "lb", "sync_id": "wn"},
        ])
        self.assertEqual(data["errors"], [])
        self.assertEqual(data["created"], 0)
        self.assertEqual(data["updated"], 0)
        self.assertEqual(data["skipped"], 1)
        self.assertFalse(WeightEntry.objects.filter(user=self.user).exists())

    def test_nan_metrics_skipped_across_handlers(self):
        data = self._ingest([
            {"type": "weight", "date": D, "value": NAN, "unit": "lb", "sync_id": "wn"},
            {"type": "hrv", "date": D, "hrv_value": NAN, "sync_id": "hn"},
            {"type": "vo2_max", "date": D, "vo2_max_value": NAN, "sync_id": "vn"},
            {"type": "walking_speed", "date": D, "walking_speed_value": NAN, "sync_id": "wsn"},
        ])
        self.assertEqual(data["errors"], [])
        self.assertEqual(data["created"], 0)
        self.assertEqual(data["updated"], 0)
        self.assertEqual(data["skipped"], 4)

    def test_nan_does_not_block_valid_metric_in_same_batch(self):
        data = self._ingest([
            {"type": "weight", "date": D, "value": NAN, "unit": "lb", "sync_id": "wn"},
            {"type": "weight", "date": D, "value": 185.3, "unit": "lb", "sync_id": "wok"},
        ])
        self.assertEqual(data["errors"], [])
        self.assertEqual(data["created"], 1)
        self.assertEqual(data["skipped"], 1)
        entry = WeightEntry.objects.get(user=self.user)
        self.assertEqual(str(entry.value), "185.3")
