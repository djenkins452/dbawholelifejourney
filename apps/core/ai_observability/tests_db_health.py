"""
OPS-5 — Database health monitor tests.

Verifies the four probes and the telemetry section against the real (Postgres)
test DB where deterministic, mocks the non-Postgres degradation path, and confirms
the roll-up + cache guard. Telemetry-only (no anomaly/recovery), request-path-safe.
"""
from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from apps.core.ai_observability import db_health_monitor as dbh


class DbHealthProbeTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_connections_probe_reports_pool(self):
        result = dbh._probe_connections()
        # On the Postgres test DB the pool is nearly empty → HEALTHY.
        self.assertIn(result["status"], ("HEALTHY", "WARNING", "CRITICAL", "UNAVAILABLE"))
        if result["status"] != "UNAVAILABLE":
            self.assertIn("total", result)
            self.assertIn("max_connections", result)
            self.assertIsInstance(result["total"], int)

    def test_long_running_probe_healthy_when_idle(self):
        result = dbh._probe_long_running()
        if result["status"] != "UNAVAILABLE":
            self.assertIn("max_secs", result)
            self.assertIn("over_threshold", result)
            # No deliberately-slow queries in a test run.
            self.assertEqual(result["status"], "HEALTHY")

    def test_dead_tuples_probe_shape(self):
        result = dbh._probe_dead_tuples()
        if result["status"] != "UNAVAILABLE":
            self.assertIn("worst_dead_ratio_pct", result)
            self.assertIn("top_tables", result)
            self.assertIsInstance(result["top_tables"], list)

    def test_migrations_probe_all_applied(self):
        # The test runner applies every migration → all_applied True, HEALTHY.
        result = dbh._probe_migrations()
        self.assertEqual(result["status"], "HEALTHY")
        self.assertTrue(result["all_applied"])
        self.assertEqual(result["unapplied"], 0)

    def test_migrations_probe_flags_unapplied(self):
        fake_plan = [(mock.Mock(app_label="core", name="9999_fake"), False)]
        with mock.patch(
            "django.db.migrations.executor.MigrationExecutor.migration_plan",
            return_value=fake_plan,
        ):
            result = dbh._probe_migrations()
        self.assertEqual(result["status"], "CRITICAL")
        self.assertFalse(result["all_applied"])
        self.assertEqual(result["unapplied"], 1)

    def test_non_postgres_pg_probes_degrade_unavailable(self):
        fake_conn = mock.MagicMock()
        fake_conn.vendor = "sqlite"
        with mock.patch.object(dbh, "connection", fake_conn):
            self.assertEqual(dbh._probe_connections()["status"], "UNAVAILABLE")
            self.assertEqual(dbh._probe_long_running()["status"], "UNAVAILABLE")
            self.assertEqual(dbh._probe_dead_tuples()["status"], "UNAVAILABLE")


class DbHealthTelemetryTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_section_shape(self):
        result = dbh.get_db_health_telemetry()
        for key in ("status", "connections", "long_running", "dead_tuples",
                    "migrations", "measured_at"):
            self.assertIn(key, result)

    def test_cache_guard(self):
        dbh.get_db_health_telemetry()
        # Second call must hit the cache, not re-probe.
        with mock.patch.object(dbh, "_probe_connections") as m:
            dbh.get_db_health_telemetry()
            m.assert_not_called()

    def test_overall_status_is_worst_measured(self):
        cache.clear()
        with mock.patch.object(dbh, "_probe_migrations",
                               return_value={"status": "CRITICAL", "unapplied": 1}):
            result = dbh.get_db_health_telemetry()
        self.assertEqual(result["status"], "CRITICAL")
