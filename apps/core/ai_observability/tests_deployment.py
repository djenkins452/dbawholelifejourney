"""
OPS-9 — Deployment & version health tests.

Verifies deterministic running-version facts, self-observed deploy detection
(SHA-change), migration-status reuse (partial-deploy signal), and the cache guard.
No external polling is performed.
"""
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.ai_observability import deployment_monitor as dm


class RunningVersionTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_running_version_facts(self):
        with mock.patch.dict("os.environ", {
            "RAILWAY_GIT_COMMIT_SHA": "abc1234def567890",
            "RAILWAY_ENVIRONMENT": "production",
        }):
            r = dm._running_version()
        self.assertEqual(r["commit_sha"], "abc1234def567890")
        self.assertEqual(r["commit_short"], "abc1234def56")
        self.assertEqual(r["environment"], "production")
        self.assertTrue(r["is_railway"])
        self.assertIn(".", r["django_version"])
        self.assertIn(".", r["python_version"])

    def test_local_defaults_when_no_railway(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            r = dm._running_version()
        self.assertEqual(r["commit_sha"], "development")
        self.assertEqual(r["environment"], "local")
        self.assertFalse(r["is_railway"])


class DeployDetectionTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_first_observation_records_marker(self):
        now = timezone.now()
        d = dm._deploy_detection(now, "sha_one")
        self.assertEqual(d["previous_sha"], None)
        self.assertIsNotNone(d["current_first_observed"])
        self.assertIsNotNone(d["observed_for_s"])

    def test_sha_change_records_transition(self):
        dm._deploy_detection(timezone.now(), "sha_one")
        d = dm._deploy_detection(timezone.now(), "sha_two_abcdef")
        # previous_sha is the old SHA (short), proving deploy-transition detection.
        self.assertEqual(d["previous_sha"], "sha_one")

    def test_same_sha_keeps_first_seen(self):
        d1 = dm._deploy_detection(timezone.now(), "sha_stable")
        d2 = dm._deploy_detection(timezone.now(), "sha_stable")
        self.assertEqual(d1["current_first_observed"], d2["current_first_observed"])
        self.assertIsNone(d2["previous_sha"])


class DeploymentTelemetryTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_section_shape(self):
        r = dm.get_deployment_telemetry()
        for key in ("status", "running", "deploy", "migrations", "external_note", "measured_at"):
            self.assertIn(key, r)

    def test_all_applied_is_healthy(self):
        # Test DB has every migration applied → HEALTHY, deploy "fully succeeded".
        r = dm.get_deployment_telemetry()
        self.assertEqual(r["migrations"]["status"], "HEALTHY")
        self.assertEqual(r["status"], "HEALTHY")

    def test_unapplied_migrations_is_critical(self):
        cache.clear()
        with mock.patch.object(dm, "_migration_status",
                               return_value={"status": "CRITICAL", "unapplied": 3}):
            r = dm.get_deployment_telemetry()
        self.assertEqual(r["status"], "CRITICAL")  # partial deploy

    def test_cache_guard(self):
        dm.get_deployment_telemetry()
        with mock.patch.object(dm, "_running_version") as m:
            dm.get_deployment_telemetry()
            m.assert_not_called()

    def test_no_external_poll_note_present(self):
        r = dm.get_deployment_telemetry()
        self.assertIn("Railway-side", r["external_note"])
