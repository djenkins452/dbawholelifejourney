"""
OPS-2 — Storage / Volume Monitor tests.

Proves:
  * each probe returns a self-contained dict and never raises,
  * SQLite (dev) degrades Postgres sizing to UNAVAILABLE with a reason,
  * the overall roll-up takes the worst MEASURED state and ignores UNAVAILABLE,
  * thresholds map utilization to HEALTHY / WARNING / CRITICAL,
  * get_storage_telemetry persists a daily StorageSnapshot and computes growth.

Path: apps/core/tests/test_storage_monitor.py
"""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.core.ai_observability import storage_monitor as sm
from apps.core.ai_observability.models import StorageSnapshot


class ThresholdTests(TestCase):
    def test_status_from_util(self):
        self.assertEqual(sm._status_from_util(0.10), "HEALTHY")
        self.assertEqual(sm._status_from_util(0.74), "HEALTHY")
        self.assertEqual(sm._status_from_util(0.75), "WARNING")
        self.assertEqual(sm._status_from_util(0.89), "WARNING")
        self.assertEqual(sm._status_from_util(0.90), "CRITICAL")
        self.assertEqual(sm._status_from_util(None), "UNKNOWN")

    def test_pct(self):
        self.assertEqual(sm._pct(50, 100), 50.0)
        self.assertIsNone(sm._pct(50, 0))
        self.assertIsNone(sm._pct(None, 100))


class ProbeTests(TestCase):
    def test_postgres_probe_unavailable_on_sqlite(self):
        # Dev test DB is SQLite → clear UNAVAILABLE with a reason, never a crash.
        with patch.object(sm.connection, "vendor", "sqlite"):
            out = sm._probe_postgres()
        self.assertEqual(out["status"], "UNAVAILABLE")
        self.assertIn("reason", out)
        self.assertIsNone(out["bytes"])

    def test_postgres_probe_thresholds(self):
        class _Cur:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def execute(self, *a): pass
            def fetchone(self): return (sm.PG_WARN_BYTES + 1,)
        with patch.object(sm.connection, "vendor", "postgresql"), \
             patch.object(sm.connection, "cursor", return_value=_Cur()):
            out = sm._probe_postgres()
        self.assertEqual(out["status"], "WARNING")
        self.assertEqual(out["bytes"], sm.PG_WARN_BYTES + 1)

    def test_redis_probe_unavailable_without_redis(self):
        with patch.object(sm, "_get_redis_url", return_value="memory://"):
            out = sm._probe_redis()
        self.assertEqual(out["status"], "UNAVAILABLE")
        self.assertIsNone(out["used_bytes"])

    def test_disk_probe_returns_usage(self):
        out = sm._probe_disk()
        # On any real filesystem this measures; on failure it degrades cleanly.
        self.assertIn(out["status"], {"HEALTHY", "WARNING", "CRITICAL", "UNAVAILABLE"})
        if out["status"] != "UNAVAILABLE":
            self.assertGreater(out["total_bytes"], 0)


class OverallStatusTests(TestCase):
    def test_worst_measured_wins_and_unavailable_ignored(self):
        resources = [
            {"status": "HEALTHY"},
            {"status": "WARNING"},
            {"status": "UNAVAILABLE"},
        ]
        self.assertEqual(sm._overall_status(resources), "WARNING")

    def test_all_unavailable_is_unavailable(self):
        resources = [{"status": "UNAVAILABLE"}, {"status": "UNAVAILABLE"}]
        self.assertEqual(sm._overall_status(resources), "UNAVAILABLE")

    def test_critical_beats_warning(self):
        resources = [{"status": "WARNING"}, {"status": "CRITICAL"}]
        self.assertEqual(sm._overall_status(resources), "CRITICAL")


class TelemetryTests(TestCase):
    def setUp(self):
        sm.cache.delete(sm._TELEMETRY_CACHE_KEY)

    def test_telemetry_persists_daily_snapshot(self):
        with patch.object(sm, "_probe_postgres", return_value={"status": "HEALTHY", "bytes": 1000}), \
             patch.object(sm, "_probe_redis", return_value={"status": "HEALTHY", "used_bytes": 500, "max_bytes": 2000, "evicted_keys": 0}), \
             patch.object(sm, "_probe_disk", return_value={"status": "HEALTHY", "used_bytes": 10, "total_bytes": 100}):
            out = sm.get_storage_telemetry()
        self.assertEqual(out["status"], "HEALTHY")
        self.assertEqual(StorageSnapshot.objects.count(), 1)
        snap = StorageSnapshot.objects.get()
        self.assertEqual(snap.db_bytes, 1000)
        self.assertEqual(snap.redis_used_bytes, 500)

    def test_growth_trend_from_history(self):
        today = timezone.now().date()
        StorageSnapshot.objects.create(
            snapshot_date=today - timedelta(days=10),
            measured_at=timezone.now() - timedelta(days=10),
            db_bytes=1000,
        )
        StorageSnapshot.objects.create(
            snapshot_date=today,
            measured_at=timezone.now(),
            db_bytes=3000,
        )
        growth = sm._db_growth(timezone.now())
        self.assertIsNotNone(growth)
        self.assertEqual(growth["delta_bytes"], 2000)
        self.assertEqual(growth["per_day_bytes"], 200)

    def test_growth_none_with_insufficient_history(self):
        StorageSnapshot.objects.create(
            snapshot_date=timezone.now().date(),
            measured_at=timezone.now(),
            db_bytes=1000,
        )
        self.assertIsNone(sm._db_growth(timezone.now()))
