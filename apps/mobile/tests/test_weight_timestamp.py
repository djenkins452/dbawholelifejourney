"""HealthKit weight sync must PRESERVE the real sample timestamp, not default to noon.

Production bug: a 5:53 AM Apple Health weigh-in was stored at 12:00 PM (the sync parser
discarded the ISO8601 time with .date(), then the handler defaulted to noon). At 6:32 AM
that noon record was future-dated, so the assistant refused to answer today's weight.
"""
from datetime import datetime, time

from django.test import TestCase
from django.utils import timezone

from apps.health.models import WeightEntry
from apps.mobile.views import process_health_metric
from apps.users.models import User

_SAMPLE = "2026-07-06T05:53:00-04:00"          # the real Apple Health sample instant
_INSTANT = datetime.fromisoformat(_SAMPLE)


class WeightTimestampTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="wt@example.com", password="x")

    def _weight(self, date, value=285.7, sync_id="w1"):
        return {"type": "weight", "date": date, "value": value, "unit": "lb",
                "source": "apple_health", "sync_id": sync_id}

    def test_iso_sample_time_is_preserved_not_noon(self):
        self.assertEqual(process_health_metric(self.user, self._weight(_SAMPLE)), "created")
        e = WeightEntry.objects.get(user=self.user)
        self.assertEqual(e.recorded_at, _INSTANT)                       # exact sample instant
        self.assertNotEqual(timezone.localtime(e.recorded_at).hour, 12)  # NOT a noon default

    def test_date_only_payload_still_defaults_to_noon(self):
        # A genuinely date-only (legacy/manual) entry has no time — noon is the safe policy.
        process_health_metric(self.user, self._weight("2026-07-06", sync_id="d1"))
        e = WeightEntry.objects.get(user=self.user)
        self.assertEqual(timezone.localtime(e.recorded_at).hour, 12)

    def test_resync_self_heals_a_legacy_noon_entry(self):
        # A legacy noon row, then Apple Health re-pushes the real sample → time corrected.
        process_health_metric(self.user, self._weight("2026-07-06", sync_id="w1"))
        e = WeightEntry.objects.get(user=self.user)
        self.assertEqual(timezone.localtime(e.recorded_at).hour, 12)
        process_health_metric(self.user, self._weight(_SAMPLE, sync_id="w1"))   # re-sync
        self.assertEqual(WeightEntry.objects.filter(user=self.user).count(), 1)  # no duplicate
        e.refresh_from_db()
        self.assertEqual(e.recorded_at, _INSTANT)

    def test_no_duplicate_on_repeated_sync(self):
        process_health_metric(self.user, self._weight(_SAMPLE, sync_id="w1"))
        process_health_metric(self.user, self._weight(_SAMPLE, sync_id="w1"))
        self.assertEqual(WeightEntry.objects.filter(user=self.user).count(), 1)

    def test_real_time_is_never_overwritten_with_noon(self):
        # Once a real time is stored, a later date-only payload must not clobber it to noon.
        process_health_metric(self.user, self._weight(_SAMPLE, sync_id="w1"))
        process_health_metric(self.user, self._weight("2026-07-06", sync_id="w1"))
        e = WeightEntry.objects.get(user=self.user)
        self.assertEqual(e.recorded_at, _INSTANT)

    def test_other_metrics_keep_their_own_timestamp(self):
        # Regression: glucose already parses its own per-sample time — still preserved.
        from apps.health.models import GlucoseEntry
        process_health_metric(self.user, {
            "type": "blood_glucose", "date": "2026-07-06T07:15:00-04:00",
            "glucose_value": 113, "unit": "mg/dL", "source": "apple_health",
            "sync_id": "g1"})
        g = GlucoseEntry.objects.get(user=self.user)
        self.assertEqual(g.recorded_at, datetime.fromisoformat("2026-07-06T07:15:00-04:00"))
