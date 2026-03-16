"""
Tests for the Ops Command Center Diagnostic Engine.

Tests the diagnostic scan registry, evidence endpoints, and debug prompt
generation that power the investigation panel flow.

Path: apps/core/ai_observability/tests_diagnostic_engine.py
"""

import json

from django.conf import settings
from django.test import TestCase, RequestFactory, override_settings
from django.utils import timezone

from apps.users.models import User, TermsAcceptance


class DiagnosticEngineUnitTests(TestCase):
    """Test diagnostic_engine.py functions directly."""

    def test_scan_registry_populated(self):
        """All expected scans are registered."""
        from apps.core.ai_observability.diagnostic_engine import DIAGNOSTIC_SCANS

        expected = {
            "INFRASTRUCTURE", "LIFE_IMPACT", "SIGNAL_DROUGHT",
            "ENGINE_STARVATION", "INTELLIGENCE", "SAFETY",
            "COVERAGE", "ERROR_SPIKE",
        }
        self.assertTrue(expected.issubset(set(DIAGNOSTIC_SCANS.keys())))

    def test_get_metric_evidence_infrastructure(self):
        """Metric evidence returns structured data for INFRASTRUCTURE."""
        from apps.core.ai_observability.diagnostic_engine import get_metric_evidence

        result = get_metric_evidence("INFRASTRUCTURE")
        self.assertEqual(result["target"], "INFRASTRUCTURE")
        self.assertIn("score", result)
        self.assertIn("status", result)
        self.assertIn("components", result)
        self.assertIsInstance(result["components"], list)

    def test_get_metric_evidence_life_impact(self):
        """Metric evidence returns structured data for LIFE_IMPACT."""
        from apps.core.ai_observability.diagnostic_engine import get_metric_evidence

        result = get_metric_evidence("LIFE_IMPACT")
        self.assertEqual(result["target"], "LIFE_IMPACT")
        self.assertIn("score", result)
        self.assertIn("components", result)

    def test_get_metric_evidence_all_metrics(self):
        """All 5 maturity metrics return valid evidence."""
        from apps.core.ai_observability.diagnostic_engine import get_metric_evidence

        for target in ["INFRASTRUCTURE", "INTELLIGENCE", "SAFETY", "COVERAGE", "LIFE_IMPACT"]:
            result = get_metric_evidence(target)
            self.assertEqual(result["target"], target, f"Failed for {target}")
            self.assertIn("components", result, f"No components for {target}")

    def test_get_metric_evidence_unknown(self):
        """Unknown metric returns UNKNOWN status."""
        from apps.core.ai_observability.diagnostic_engine import get_metric_evidence

        result = get_metric_evidence("NONEXISTENT")
        self.assertEqual(result["status"], "UNKNOWN")

    def test_run_diagnostic_scan_infrastructure(self):
        """Infrastructure scan returns structured checks."""
        from apps.core.ai_observability.diagnostic_engine import run_diagnostic_scan

        result = run_diagnostic_scan("INFRASTRUCTURE")
        self.assertEqual(result["target"], "INFRASTRUCTURE")
        self.assertIn("status", result)
        self.assertIn("checks", result)
        self.assertIsInstance(result["checks"], list)
        self.assertGreater(len(result["checks"]), 0)
        self.assertIn("root_cause_hypothesis", result)
        self.assertIn("recommended_next_step", result)

        # Each check has required fields
        for check in result["checks"]:
            self.assertIn("name", check)
            self.assertIn("status", check)
            self.assertIn("evidence", check)

    def test_run_diagnostic_scan_life_impact(self):
        """Life Impact scan returns structured checks."""
        from apps.core.ai_observability.diagnostic_engine import run_diagnostic_scan

        result = run_diagnostic_scan("LIFE_IMPACT")
        self.assertEqual(result["target"], "LIFE_IMPACT")
        self.assertIn("checks", result)
        self.assertGreater(len(result["checks"]), 0)

    def test_run_diagnostic_scan_signal_drought(self):
        """Signal Drought scan returns structured checks."""
        from apps.core.ai_observability.diagnostic_engine import run_diagnostic_scan

        result = run_diagnostic_scan("SIGNAL_DROUGHT")
        self.assertEqual(result["target"], "SIGNAL_DROUGHT")
        self.assertIn("checks", result)

    def test_run_diagnostic_scan_engine_starvation(self):
        """Engine Starvation scan returns structured checks."""
        from apps.core.ai_observability.diagnostic_engine import run_diagnostic_scan

        result = run_diagnostic_scan("ENGINE_STARVATION")
        self.assertEqual(result["target"], "ENGINE_STARVATION")
        self.assertIn("checks", result)

    def test_run_diagnostic_scan_unsupported(self):
        """Unsupported target returns UNSUPPORTED status."""
        from apps.core.ai_observability.diagnostic_engine import run_diagnostic_scan

        result = run_diagnostic_scan("NONEXISTENT")
        self.assertEqual(result["status"], "UNSUPPORTED")
        self.assertIn("available_scans", result)

    def test_generate_debug_prompt(self):
        """Debug prompt generation produces markdown with evidence."""
        from apps.core.ai_observability.diagnostic_engine import (
            generate_debug_prompt,
            get_metric_evidence,
            run_diagnostic_scan,
        )

        evidence = get_metric_evidence("INFRASTRUCTURE")
        scan = run_diagnostic_scan("INFRASTRUCTURE")
        prompt = generate_debug_prompt("INFRASTRUCTURE", scan_result=scan, evidence=evidence)

        self.assertIn("WLJ Debugging Prompt", prompt)
        self.assertIn("INFRASTRUCTURE", prompt)
        self.assertIn("DIAGNOSTIC SCAN RESULTS", prompt)
        self.assertIn("INVESTIGATION STEPS", prompt)

    def test_generate_debug_prompt_without_scan(self):
        """Debug prompt works with evidence only (no scan)."""
        from apps.core.ai_observability.diagnostic_engine import (
            generate_debug_prompt,
            get_metric_evidence,
        )

        evidence = get_metric_evidence("SAFETY")
        prompt = generate_debug_prompt("SAFETY", evidence=evidence)

        self.assertIn("WLJ Debugging Prompt", prompt)
        self.assertIn("SAFETY", prompt)

    def test_score_status_mapping(self):
        """Score status helper maps correctly."""
        from apps.core.ai_observability.diagnostic_engine import _score_status

        self.assertEqual(_score_status(95), "OPTIMAL")
        self.assertEqual(_score_status(75), "NOMINAL")
        self.assertEqual(_score_status(50), "DEGRADED")
        self.assertEqual(_score_status(20), "CRITICAL")
        self.assertEqual(_score_status(None), "UNKNOWN")


    def test_get_metric_evidence_signal_drought(self):
        """SIGNAL_DROUGHT evidence returns structured signal health data."""
        from apps.core.ai_observability.diagnostic_engine import get_metric_evidence

        result = get_metric_evidence("SIGNAL_DROUGHT")
        self.assertEqual(result["target"], "SIGNAL_DROUGHT")
        self.assertIn("score", result)
        self.assertIn("status", result)
        self.assertIn("components", result)
        self.assertIsInstance(result["components"], list)

    def test_get_metric_evidence_engine_starvation(self):
        """ENGINE_STARVATION evidence returns structured engine data."""
        from apps.core.ai_observability.diagnostic_engine import get_metric_evidence

        result = get_metric_evidence("ENGINE_STARVATION")
        self.assertEqual(result["target"], "ENGINE_STARVATION")
        self.assertIn("status", result)
        self.assertIn("components", result)

    def test_get_metric_evidence_error_spike(self):
        """ERROR_SPIKE evidence returns structured error rate data."""
        from apps.core.ai_observability.diagnostic_engine import get_metric_evidence

        result = get_metric_evidence("ERROR_SPIKE")
        self.assertEqual(result["target"], "ERROR_SPIKE")
        self.assertIn("status", result)
        self.assertIn("components", result)

    def test_investigate_pipeline_action(self):
        """investigate_pipeline action returns structured result."""
        from apps.core.ai_observability.ops_telemetry import _execute_action

        result = _execute_action("investigate_pipeline", "", "test-trace")
        self.assertIn("status", result)
        self.assertIn("detail", result)
        # Should succeed (not "Unknown action")
        self.assertNotIn("Unknown action", result.get("detail", ""))


class DiagnosticViewTests(TestCase):
    """Test the HTTP endpoints for the diagnostic flow."""

    def setUp(self):
        self.factory = RequestFactory()
        self.admin = User.objects.create_user(
            email="admin@test.com", password="testpass123", is_staff=True,
        )
        TermsAcceptance.objects.create(
            user=self.admin,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.admin.preferences.has_completed_onboarding = True
        self.admin.preferences.save()
        logged_in = self.client.login(email="admin@test.com", password="testpass123")
        assert logged_in, "Admin login failed in setUp"
        # Bypass MFA middleware for tests
        session = self.client.session
        session["mfa_verified"] = True
        session["mfa_verified_at"] = timezone.now().isoformat()
        session.save()

    def test_metric_evidence_endpoint(self):
        """GET /admin-console/ops/metric-evidence/ returns JSON."""
        resp = self.client.get("/admin-console/ops/metric-evidence/?target=INFRASTRUCTURE")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["target"], "INFRASTRUCTURE")
        self.assertIn("components", data)

    def test_metric_evidence_requires_target(self):
        """Missing target param returns 400."""
        resp = self.client.get("/admin-console/ops/metric-evidence/")
        self.assertEqual(resp.status_code, 400)

    def test_metric_evidence_requires_staff(self):
        """Non-staff users get 403."""
        regular = User.objects.create_user(
            email="user@test.com", password="testpass123", is_staff=False,
        )
        TermsAcceptance.objects.create(
            user=regular,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        regular.preferences.has_completed_onboarding = True
        regular.preferences.save()
        self.client.login(email="user@test.com", password="testpass123")
        resp = self.client.get("/admin-console/ops/metric-evidence/?target=INFRASTRUCTURE")
        self.assertEqual(resp.status_code, 403)

    def test_diagnose_endpoint(self):
        """GET /admin-console/ops/diagnose/ returns structured scan."""
        resp = self.client.get("/admin-console/ops/diagnose/?target=INFRASTRUCTURE")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["target"], "INFRASTRUCTURE")
        self.assertIn("checks", data)
        self.assertIn("available_scans", data)
        self.assertIsInstance(data["available_scans"], list)

    def test_diagnose_unsupported_target(self):
        """Unsupported target returns 200 with UNSUPPORTED status."""
        resp = self.client.get("/admin-console/ops/diagnose/?target=FAKE_TARGET")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "UNSUPPORTED")

    def test_debug_prompt_endpoint(self):
        """GET /admin-console/ops/debug-prompt/ returns markdown prompt."""
        resp = self.client.get("/admin-console/ops/debug-prompt/?target=INFRASTRUCTURE")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("prompt", data)
        self.assertIn("WLJ Debugging Prompt", data["prompt"])
        self.assertIn("target", data)

    def test_debug_prompt_requires_target(self):
        """Missing target param returns 400."""
        resp = self.client.get("/admin-console/ops/debug-prompt/")
        self.assertEqual(resp.status_code, 400)

    def test_ops_wall_renders(self):
        """Ops Wall page renders without error."""
        resp = self.client.get("/admin-console/ops/")
        self.assertEqual(resp.status_code, 200)
        # Check that new investigation panel HTML is present
        content = resp.content.decode()
        self.assertIn("investigateOverlay", content)
        self.assertIn("investigatePanel", content)
        self.assertIn("investigateScanBtn", content)

    def test_ops_wall_has_celery_beat_tile(self):
        """Ops Wall includes Celery Beat scheduler tile."""
        resp = self.client.get("/admin-console/ops/")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("schedCardAPS", content)
        self.assertIn("Celery Beat", content)

    def test_scheduler_health_endpoint(self):
        """GET /admin-console/ops/scheduler-health/ returns JSON."""
        resp = self.client.get("/admin-console/ops/scheduler-health/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("scheduler", data)
        self.assertIn("status", data["scheduler"])

    def test_scheduler_restart_requires_post(self):
        """GET to restart endpoint returns 405."""
        resp = self.client.get("/admin-console/ops/scheduler-restart/")
        self.assertEqual(resp.status_code, 405)

    def test_all_scan_targets(self):
        """All registered scan targets return structured results via endpoint."""
        from apps.core.ai_observability.diagnostic_engine import DIAGNOSTIC_SCANS

        for target in DIAGNOSTIC_SCANS:
            resp = self.client.get(f"/admin-console/ops/diagnose/?target={target}")
            self.assertEqual(resp.status_code, 200, f"Failed for {target}")
            data = resp.json()
            self.assertIn("checks", data, f"No checks for {target}")
            self.assertIn("status", data, f"No status for {target}")

    def test_all_metric_evidence_targets(self):
        """All maturity metric targets return evidence via endpoint."""
        for target in ["INFRASTRUCTURE", "INTELLIGENCE", "SAFETY", "COVERAGE", "LIFE_IMPACT"]:
            resp = self.client.get(f"/admin-console/ops/metric-evidence/?target={target}")
            self.assertEqual(resp.status_code, 200, f"Failed for {target}")
            data = resp.json()
            self.assertIn("components", data, f"No components for {target}")
