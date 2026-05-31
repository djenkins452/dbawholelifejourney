"""
Idempotency regression tests for HealthKit decimal ingestion.

HealthKit sends full-precision doubles (e.g. 185.3482284) but the health
models store quantized DecimalFields (e.g. 185.3). Before normalize_for_storage
was added, the handler compared the raw incoming value against the already-
quantized stored value, so unchanged data was re-saved and counted as "updated"
on every sync — it never converged.

These tests submit the SAME full-precision payload three times and assert:
  sync #1 -> created
  sync #2 -> skipped
  sync #3 -> skipped

with the stored value quantized to the field's precision.
"""

import json
from decimal import Decimal

from django.test import Client, TestCase

from apps.health.models import (
    DietaryNutrientEntry,
    MobilityEntry,
    StepsEntry,
    WaterEntry,
    WeightEntry,
)
from apps.mobile.models import MobileAPIToken, MobileDevice
from apps.users.models import User


class HealthIngestionIdempotencyTests(TestCase):
    """Repeated syncs of unchanged decimal data must converge to skipped."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="idempotency@example.com",
            password="testpass123",
        )
        self.device = MobileDevice.objects.create(
            user=self.user,
            device_id="idempotency-device-uuid",
        )
        self.token, self.raw_token = MobileAPIToken.create_token(
            user=self.user,
            device=self.device,
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

    def _assert_converges(self, metric):
        """First sync creates; second and third are no-ops (skipped)."""
        first = self._ingest(metric)
        self.assertEqual(first["created"], 1)
        self.assertEqual(first["updated"], 0)

        second = self._ingest(metric)
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["updated"], 0)
        self.assertEqual(second["skipped"], 1)

        third = self._ingest(metric)
        self.assertEqual(third["created"], 0)
        self.assertEqual(third["updated"], 0)
        self.assertEqual(third["skipped"], 1)

    def test_weight_converges(self):
        # WeightEntry.value is decimal_places=1
        self._assert_converges({
            "type": "weight",
            "date": "2024-01-15",
            "value": 185.3482284,
            "unit": "lb",
            "source": "apple_health",
            "sync_id": "weight-idem-1",
        })
        entry = WeightEntry.objects.get(user=self.user)
        self.assertEqual(entry.value, Decimal("185.3"))

    def test_distance_converges(self):
        # StepsEntry.distance_miles is decimal_places=2
        self._assert_converges({
            "type": "distance",
            "date": "2024-01-15",
            "distance_value": 3.14159265,
            "distance_unit": "mi",
            "source": "apple_health",
            "sync_id": "distance-idem-1",
        })
        entry = StepsEntry.objects.get(user=self.user, logged_date="2024-01-15")
        self.assertEqual(entry.distance_miles, Decimal("3.14"))

    def test_water_converges(self):
        # WaterEntry.amount is decimal_places=1
        self._assert_converges({
            "type": "water",
            "date": "2024-01-15",
            "water_amount": 64.7333333,
            "water_unit": "oz",
            "source": "apple_health",
            "sync_id": "water-idem-1",
        })
        entry = WaterEntry.objects.get(user=self.user)
        self.assertEqual(entry.amount, Decimal("64.7"))

    def test_dietary_nutrient_converges(self):
        # DietaryNutrientEntry.protein_g is decimal_places=2
        self._assert_converges({
            "type": "dietary_nutrients",
            "date": "2024-01-15",
            "protein_g": 55.6789012,
            "carbohydrates_g": 210.4444444,
            "source": "apple_health",
            "sync_id": "nutrient-idem-1",
        })
        entry = DietaryNutrientEntry.objects.get(user=self.user, metric_date="2024-01-15")
        self.assertEqual(entry.protein_g, Decimal("55.68"))
        self.assertEqual(entry.carbohydrates_g, Decimal("210.44"))

    def test_mobility_walking_speed_converges(self):
        # MobilityEntry.walking_speed is decimal_places=2
        self._assert_converges({
            "type": "walking_speed",
            "date": "2024-01-15",
            "walking_speed_value": 1.234567,
            "source": "apple_health",
            "sync_id": "mobility-idem-1",
        })
        entry = MobilityEntry.objects.get(user=self.user, metric_date="2024-01-15")
        self.assertEqual(entry.walking_speed, Decimal("1.23"))
