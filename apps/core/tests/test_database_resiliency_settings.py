"""
Locks in the production-resiliency contract for the default Postgres connection.

These settings exist because of a real production incident: idle Gunicorn-worker
connections were being torn down server-side by Railway / pgbouncer while Django
still considered them fresh (CONN_MAX_AGE=600 matched the server's idle window),
producing "SSL SYSCALL error: EOF detected" → "connection already closed" on
the /api/notifications/count/ polling endpoint roughly every minute.

The fix had three parts and any one of them silently regressing would let the
incident recur:

  1. CONN_MAX_AGE must stay well below Railway's idle horizon.
  2. CONN_HEALTH_CHECKS must remain enabled.
  3. libpq TCP keepalives must be configured so the kernel surfaces dead peers
     in ~minutes, not the ~2-hour kernel default — otherwise CONN_HEALTH_CHECKS'
     SELECT 1 can succeed against a socket the server has already closed and
     the next real query fails.

This test asserts all three, but only when Postgres is the configured engine
(i.e., production-like). SQLite dev environments are unaffected.
"""

from django.conf import settings
from django.test import SimpleTestCase


class DatabaseResiliencySettingsTests(SimpleTestCase):
    """Guard the Postgres connection-resiliency contract."""

    def setUp(self):
        self.default = settings.DATABASES["default"]
        self.engine = self.default.get("ENGINE", "")
        self.is_postgres = "postgresql" in self.engine

    def test_conn_max_age_safely_below_server_idle_window(self):
        """
        CONN_MAX_AGE must be < ~300s — well clear of Railway's ~600s idle
        timeout. Sitting at parity (600) caused the stale-reuse race that
        produced the production SSL EOF errors.
        """
        if not self.is_postgres:
            self.skipTest("CONN_MAX_AGE bound only applies to Postgres deployments")
        conn_max_age = self.default.get("CONN_MAX_AGE")
        self.assertIsNotNone(conn_max_age, "CONN_MAX_AGE must be explicitly set")
        self.assertLessEqual(
            conn_max_age,
            300,
            f"CONN_MAX_AGE={conn_max_age} is dangerously close to Railway's "
            f"~600s server-side idle timeout. Keep it ≤300s (recommended 60) "
            f"so we never reuse a connection the server has already torn down.",
        )
        self.assertGreater(
            conn_max_age,
            0,
            "Set CONN_MAX_AGE to a small positive value (e.g. 60) to amortise "
            "connection setup. Disabling persistence entirely is a perf tax "
            "this app does not need to pay.",
        )

    def test_conn_health_checks_enabled(self):
        """
        CONN_HEALTH_CHECKS=True makes Django run SELECT 1 at request start to
        verify a persistent connection before reusing it. Disabling this is
        the textbook cause of stale-connection 500s.
        """
        if not self.is_postgres:
            self.skipTest("CONN_HEALTH_CHECKS only meaningful for Postgres")
        self.assertIs(
            self.default.get("CONN_HEALTH_CHECKS"),
            True,
            "CONN_HEALTH_CHECKS must be True so Django probes persistent "
            "connections before reuse. Removing this re-opens the stale-"
            "connection failure mode CONN_MAX_AGE alone cannot prevent.",
        )

    def test_libpq_tcp_keepalives_configured(self):
        """
        Without libpq keepalives, the Linux kernel takes ~2 hours
        (tcp_keepalive_time) to notice a dead peer. That gives the health
        check's SELECT 1 a wide window in which it can succeed against a
        socket the server has already closed, after which the next real
        query fails. With these settings the kernel reports a dead peer
        within ~80s (30s idle + 5×10s probes).
        """
        if not self.is_postgres:
            self.skipTest("libpq keepalives only apply to Postgres connections")
        options = self.default.get("OPTIONS", {})
        self.assertEqual(
            options.get("keepalives"),
            1,
            "OPTIONS['keepalives']=1 is required to opt into TCP keepalives.",
        )
        keepalives_idle = options.get("keepalives_idle")
        self.assertIsNotNone(keepalives_idle, "OPTIONS['keepalives_idle'] required")
        self.assertLessEqual(
            keepalives_idle,
            60,
            f"keepalives_idle={keepalives_idle} is too long. Keep ≤60 so a "
            f"connection that died during an idle window is detected before "
            f"the next request tries to use it.",
        )
        self.assertIn(
            "keepalives_interval",
            options,
            "OPTIONS['keepalives_interval'] required",
        )
        self.assertIn(
            "keepalives_count",
            options,
            "OPTIONS['keepalives_count'] required",
        )
