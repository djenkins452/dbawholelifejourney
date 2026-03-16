"""
Tests for Validator Gate Monitoring (Ops Wall 2.0 — Phase 3).

Tests cover:
  - ValidatorMetric model creation
  - validate_response() metric recording
  - compute_validator_health() aggregation logic
  - _detect_validator_spike() SAME detector
  - _cache_validator_health() caching behavior
  - _get_validator_health() cache-read + fallback
  - OpsAnomaly model accepts VALIDATOR_SPIKE type

Project: Whole Life Journey
Path: apps/core/ai_observability/tests_validator_health.py
"""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone


class ValidatorMetricModelTests(TestCase):
    """Test ValidatorMetric model CRUD."""

    def test_create_pass_metric(self):
        """Should create a ValidatorMetric with 'pass' outcome."""
        from apps.core.ai_observability.models import ValidatorMetric

        metric = ValidatorMetric.objects.create(
            outcome="pass",
            policy="none",
            duration_ms=5,
            user_id=1,
        )
        self.assertEqual(metric.outcome, "pass")
        self.assertEqual(metric.policy, "none")
        self.assertIsNotNone(metric.created_at)

    def test_create_block_metric(self):
        """Should create a ValidatorMetric with 'block' outcome."""
        from apps.core.ai_observability.models import ValidatorMetric

        metric = ValidatorMetric.objects.create(
            outcome="block",
            policy="structural",
            duration_ms=3,
        )
        self.assertEqual(metric.outcome, "block")
        self.assertEqual(metric.policy, "structural")

    def test_create_crash_metric(self):
        """Should create a ValidatorMetric with 'crash' outcome."""
        from apps.core.ai_observability.models import ValidatorMetric

        metric = ValidatorMetric.objects.create(
            outcome="crash",
            policy="crash",
            duration_ms=1,
        )
        self.assertEqual(metric.outcome, "crash")

    def test_str_representation(self):
        """__str__ should include outcome and policy."""
        from apps.core.ai_observability.models import ValidatorMetric

        metric = ValidatorMetric.objects.create(
            outcome="block",
            policy="action_claim",
            duration_ms=7,
        )
        self.assertIn("block", str(metric))
        self.assertIn("action_claim", str(metric))


class ValidateResponseMetricTests(TestCase):
    """Test that validate_response() records ValidatorMetric rows."""

    def test_pass_records_metric(self):
        """Clean response should record a 'pass' metric."""
        from apps.core.ai_governance.validator_gate import validate_response
        from apps.core.ai_observability.models import ValidatorMetric

        result = validate_response("Hello, how are you today?")
        self.assertFalse(result["blocked"])

        metric = ValidatorMetric.objects.latest("created_at")
        self.assertEqual(metric.outcome, "pass")
        self.assertEqual(metric.policy, "none")
        self.assertGreaterEqual(metric.duration_ms, 0)

    def test_structural_block_records_metric(self):
        """Structural violation should record a 'block' metric."""
        from apps.core.ai_governance.validator_gate import validate_response
        from apps.core.ai_observability.models import ValidatorMetric

        # Use a known banned term (from language_rules.py)
        with patch(
            "apps.core.ai_governance.validator_gate._get_banned_terms",
            return_value=["SUPPRESSION_STORM"],
        ):
            result = validate_response("SUPPRESSION_STORM is happening")
        self.assertTrue(result["blocked"])

        metric = ValidatorMetric.objects.latest("created_at")
        self.assertEqual(metric.outcome, "block")
        self.assertEqual(metric.policy, "structural")

    def test_action_claim_block_records_metric(self):
        """Unverifiable action claim should record a 'block' metric."""
        from apps.core.ai_governance.validator_gate import validate_response
        from apps.core.ai_observability.models import ValidatorMetric

        result = validate_response(
            "I've scheduled that for tomorrow at 3pm.",
            action_executed=False,
        )
        self.assertTrue(result["blocked"])

        metric = ValidatorMetric.objects.latest("created_at")
        self.assertEqual(metric.outcome, "block")
        self.assertEqual(metric.policy, "action_claim")

    def test_crash_records_metric(self):
        """Validator crash should record a 'crash' metric."""
        from apps.core.ai_governance.validator_gate import validate_response
        from apps.core.ai_observability.models import ValidatorMetric

        with patch(
            "apps.core.ai_governance.validator_gate._validate_response_inner",
            side_effect=RuntimeError("boom"),
        ):
            result = validate_response("test response")
        self.assertTrue(result["blocked"])
        self.assertIn("VALIDATOR_CRASH", result["violations"][0])

        metric = ValidatorMetric.objects.latest("created_at")
        self.assertEqual(metric.outcome, "crash")
        self.assertEqual(metric.policy, "crash")


class ComputeValidatorHealthTests(TestCase):
    """Test compute_validator_health() aggregation."""

    def _create_metric(self, outcome="pass", policy="none", hours_ago=0):
        """Helper to create a ValidatorMetric with adjustable created_at."""
        from apps.core.ai_observability.models import ValidatorMetric

        obj = ValidatorMetric.objects.create(
            outcome=outcome,
            policy=policy,
            duration_ms=5,
        )
        if hours_ago > 0:
            target = timezone.now() - timedelta(hours=hours_ago)
            ValidatorMetric.objects.filter(pk=obj.pk).update(created_at=target)
            obj.refresh_from_db()
        return obj

    def test_empty_returns_no_data(self):
        """No metrics should return status 'no_data'."""
        from apps.core.ai_observability.ops_telemetry import compute_validator_health

        result = compute_validator_health()
        self.assertEqual(result["total_1h"], 0)
        self.assertEqual(result["status"], "no_data")

    def test_healthy_status(self):
        """All passes should return 'healthy'."""
        from apps.core.ai_observability.ops_telemetry import compute_validator_health

        for _ in range(10):
            self._create_metric("pass", "none", hours_ago=0)

        result = compute_validator_health()
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["total_1h"], 10)
        self.assertEqual(result["block_rate_1h"], 0.0)

    def test_degraded_status(self):
        """Block rate > 5% should return 'degraded'."""
        from apps.core.ai_observability.ops_telemetry import compute_validator_health

        # 9 passes + 1 block = 10% block rate
        for _ in range(9):
            self._create_metric("pass")
        self._create_metric("block", "structural")

        result = compute_validator_health()
        self.assertEqual(result["status"], "degraded")
        self.assertGreater(result["block_rate_1h"], 0.05)

    def test_critical_status_high_block_rate(self):
        """Block rate > 25% should return 'critical'."""
        from apps.core.ai_observability.ops_telemetry import compute_validator_health

        # 3 passes + 3 blocks = 50% block rate
        for _ in range(3):
            self._create_metric("pass")
        for _ in range(3):
            self._create_metric("block", "structural")

        result = compute_validator_health()
        self.assertEqual(result["status"], "critical")

    def test_critical_status_crashes(self):
        """Crashes should trigger 'critical' if >= 2 in 24h."""
        from apps.core.ai_observability.ops_telemetry import compute_validator_health

        for _ in range(8):
            self._create_metric("pass")
        self._create_metric("crash", "crash")
        self._create_metric("crash", "crash")

        result = compute_validator_health()
        self.assertEqual(result["status"], "critical")
        self.assertEqual(result["crash_count_24h"], 2)

    def test_by_policy_breakdown(self):
        """by_policy_24h should count violations by policy type."""
        from apps.core.ai_observability.ops_telemetry import compute_validator_health

        for _ in range(5):
            self._create_metric("pass")
        self._create_metric("block", "structural")
        self._create_metric("block", "structural")
        self._create_metric("block", "action_claim")

        result = compute_validator_health()
        self.assertEqual(result["by_policy_24h"].get("structural"), 2)
        self.assertEqual(result["by_policy_24h"].get("action_claim"), 1)

    def test_windows_respect_time(self):
        """Metrics outside the window should not be counted."""
        from apps.core.ai_observability.ops_telemetry import compute_validator_health

        # Create old metrics (outside 1h)
        for _ in range(5):
            self._create_metric("block", "structural", hours_ago=2)

        # Create recent metrics
        for _ in range(5):
            self._create_metric("pass", hours_ago=0)

        result = compute_validator_health()
        self.assertEqual(result["total_1h"], 5)
        self.assertEqual(result["blocks_1h"], 0)
        self.assertEqual(result["block_rate_1h"], 0.0)
        # But 24h should include both
        self.assertEqual(result["total_24h"], 10)
        self.assertEqual(result["blocks_24h"], 5)

    def test_result_structure(self):
        """Return value should have all expected keys."""
        from apps.core.ai_observability.ops_telemetry import compute_validator_health

        self._create_metric("pass")
        result = compute_validator_health()

        expected_keys = [
            "total_1h", "total_24h", "total_7d",
            "blocks_1h", "blocks_24h",
            "block_rate_1h", "block_rate_24h", "block_rate_7d",
            "crash_count_24h", "avg_duration_ms",
            "by_policy_24h", "status",
        ]
        for key in expected_keys:
            self.assertIn(key, result, f"Missing key: {key}")


class DetectValidatorSpikeTests(TestCase):
    """Test _detect_validator_spike() SAME detector."""

    def _create_metric(self, outcome="pass", policy="none", hours_ago=0):
        from apps.core.ai_observability.models import ValidatorMetric

        obj = ValidatorMetric.objects.create(
            outcome=outcome,
            policy=policy,
            duration_ms=5,
        )
        if hours_ago > 0:
            target = timezone.now() - timedelta(hours=hours_ago)
            ValidatorMetric.objects.filter(pk=obj.pk).update(created_at=target)
            obj.refresh_from_db()
        return obj

    def test_no_anomaly_when_healthy(self):
        """No spike should be detected when block rate is low."""
        from apps.core.ai_observability.same_engine import _detect_validator_spike

        for _ in range(10):
            self._create_metric("pass")

        now = timezone.now()
        anomalies = _detect_validator_spike(now)
        spike_anomalies = [a for a in anomalies if a["anomaly_type"] == "VALIDATOR_SPIKE"]
        self.assertEqual(len(spike_anomalies), 0)

    def test_no_anomaly_when_low_volume(self):
        """No spike should trigger with < 5 validations."""
        from apps.core.ai_observability.same_engine import _detect_validator_spike

        # 2 blocks out of 3 = 66% but volume too low
        self._create_metric("block", "structural")
        self._create_metric("block", "structural")
        self._create_metric("pass")

        now = timezone.now()
        anomalies = _detect_validator_spike(now)
        self.assertEqual(len(anomalies), 0)

    def test_p2_for_moderate_spike(self):
        """Block rate 10-25% with volume >= 5 should generate P2."""
        from apps.core.ai_observability.same_engine import _detect_validator_spike

        # 8 passes + 2 blocks = 20% block rate
        for _ in range(8):
            self._create_metric("pass")
        for _ in range(2):
            self._create_metric("block", "structural")

        now = timezone.now()
        anomalies = _detect_validator_spike(now)
        spike = [a for a in anomalies if a["anomaly_type"] == "VALIDATOR_SPIKE"]
        self.assertEqual(len(spike), 1)
        self.assertEqual(spike[0]["severity"], "P2")

    def test_p1_for_high_spike(self):
        """Block rate > 25% should generate P1."""
        from apps.core.ai_observability.same_engine import _detect_validator_spike

        # 3 passes + 3 blocks = 50%
        for _ in range(3):
            self._create_metric("pass")
        for _ in range(3):
            self._create_metric("block", "structural")

        now = timezone.now()
        anomalies = _detect_validator_spike(now)
        spike = [a for a in anomalies if a["anomaly_type"] == "VALIDATOR_SPIKE"]
        self.assertEqual(len(spike), 1)
        self.assertEqual(spike[0]["severity"], "P1")

    def test_p1_for_crash_in_1h(self):
        """Any crash in 1h should generate P1 even with low block rate."""
        from apps.core.ai_observability.same_engine import _detect_validator_spike

        for _ in range(9):
            self._create_metric("pass")
        self._create_metric("crash", "crash")

        now = timezone.now()
        anomalies = _detect_validator_spike(now)
        spike = [a for a in anomalies if a["anomaly_type"] == "VALIDATOR_SPIKE"]
        self.assertEqual(len(spike), 1)
        self.assertEqual(spike[0]["severity"], "P1")
        self.assertIn("crashes", spike[0]["summary"])

    def test_no_anomaly_for_empty_data(self):
        """No data should produce no anomalies."""
        from apps.core.ai_observability.same_engine import _detect_validator_spike

        anomalies = _detect_validator_spike(timezone.now())
        self.assertEqual(len(anomalies), 0)


class OpsAnomalyValidatorSpikeTests(TestCase):
    """Test OpsAnomaly model accepts VALIDATOR_SPIKE type."""

    def test_validator_spike_anomaly_creation(self):
        """Should create OpsAnomaly with VALIDATOR_SPIKE type."""
        from apps.core.ai_observability.models import OpsAnomaly

        anomaly = OpsAnomaly.objects.create(
            anomaly_type="VALIDATOR_SPIKE",
            severity="P2",
            engine_name="VGE",
            summary="Validator block rate spike: 15% (3/20 in 1h)",
            evidence={"block_rate_1h": 0.15, "blocks_1h": 3, "total_1h": 20},
            suggested_actions=[
                {"action": "investigate_validator", "label": "Review blocked responses"},
            ],
            original_severity="P2",
        )
        self.assertEqual(anomaly.anomaly_type, "VALIDATOR_SPIKE")
        self.assertTrue(anomaly.is_active)


class CacheValidatorHealthTests(TestCase):
    """Test validator health caching and retrieval."""

    def _create_metric(self, outcome="pass", policy="none"):
        from apps.core.ai_observability.models import ValidatorMetric

        ValidatorMetric.objects.create(
            outcome=outcome,
            policy=policy,
            duration_ms=5,
        )

    def test_cache_validator_health_stores_data(self):
        """_cache_validator_health() should store result in Django cache."""
        from django.core.cache import cache

        from apps.core.ai_observability.same_engine import _cache_validator_health

        self._create_metric("pass")
        _cache_validator_health()

        cached = cache.get("wlj:ops:validator_health")
        self.assertIsNotNone(cached)
        self.assertIn("status", cached)
        self.assertIn("total_1h", cached)

    def test_get_validator_health_reads_cache(self):
        """_get_validator_health() should return cached data when available."""
        from django.core.cache import cache

        from apps.core.ai_observability.ops_telemetry import _get_validator_health

        test_data = {"status": "healthy", "total_1h": 42}
        cache.set("wlj:ops:validator_health", test_data, timeout=120)

        result = _get_validator_health()
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["total_1h"], 42)

    def test_get_validator_health_returns_none_on_empty_cache(self):
        """_get_validator_health() returns None when cache is empty (no live fallback)."""
        from django.core.cache import cache

        from apps.core.ai_observability.ops_telemetry import _get_validator_health

        cache.delete("wlj:ops:validator_health")
        self._create_metric("pass")

        # No live fallback — returns None until SAME populates cache
        result = _get_validator_health()
        self.assertIsNone(result)
