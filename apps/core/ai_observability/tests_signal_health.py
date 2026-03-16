"""
Tests for Signal Health Diagnostics (Ops Wall 2.0 — Phase 2).

Tests cover:
  - compute_signal_health() aggregation logic
  - _detect_signal_drought() SAME detector
  - _detect_signal_low_diversity() SAME detector
  - _cache_signal_health() caching behavior
  - _get_signal_health() cache-read + fallback
  - OpsAnomaly model accepts new anomaly types

Project: Whole Life Journey
Path: apps/core/ai_observability/tests_signal_health.py
"""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone


class SignalHealthTestMixin:
    """Common setup for signal health tests — creates a user and seed data."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.user = User.objects.create_user(
            email="signaltest@example.com", password="testpass123"
        )
        self.now = timezone.now()

    def _create_insight(self, module, insight_type="default_type", hours_ago=0):
        from apps.core.ai_insights.models import Insight

        obj = Insight.objects.create(
            user=self.user,
            module=module,
            insight_type=insight_type,
            title="Test insight",
            message="Test message",
            explain_why="Test reason",
            dedupe_key=f"test-{module}-{insight_type}-{hours_ago}-{timezone.now().timestamp()}",
        )
        if hours_ago > 0:
            target = self.now - timedelta(hours=hours_ago)
            Insight.objects.filter(pk=obj.pk).update(created_at=target)
            obj.refresh_from_db()
        return obj

    def _create_prediction(self, module, prediction_type="default_pred", hours_ago=0):
        from apps.core.ai_predictions.models import Prediction

        obj = Prediction.objects.create(
            user=self.user,
            module=module,
            prediction_type=prediction_type,
            predicted_date=self.now + timedelta(days=1),
            confidence_score=0.8,
            explanation="Test prediction",
            dedupe_key=f"test-pred-{module}-{prediction_type}-{hours_ago}-{timezone.now().timestamp()}",
        )
        if hours_ago > 0:
            target = self.now - timedelta(hours=hours_ago)
            Prediction.objects.filter(pk=obj.pk).update(created_at=target)
            obj.refresh_from_db()
        return obj

    def _create_guidance(self, module, guidance_type="default_guidance", hours_ago=0):
        from apps.core.ai_guidance.models import GuidanceItem

        obj = GuidanceItem.objects.create(
            user=self.user,
            module=module,
            guidance_type=guidance_type,
            title="Test guidance",
            message="Test message",
            dedupe_key=f"test-guid-{module}-{guidance_type}-{hours_ago}-{timezone.now().timestamp()}",
        )
        if hours_ago > 0:
            target = self.now - timedelta(hours=hours_ago)
            GuidanceItem.objects.filter(pk=obj.pk).update(created_at=target)
            obj.refresh_from_db()
        return obj


class ComputeSignalHealthTests(SignalHealthTestMixin, TestCase):
    """Test compute_signal_health() aggregation."""

    def test_empty_returns_registry_domains_as_silent(self):
        """No intelligence data should return all registry domains as silent."""
        from apps.core.ai_observability.ops_telemetry import compute_signal_health
        from apps.core.domain_registry.registry import registry as domain_registry

        result = compute_signal_health()
        registry_count = domain_registry.domain_count
        self.assertEqual(result["domains_active"], 0)
        self.assertEqual(result["domains_silent"], registry_count)
        # All registry domains should be present
        for name in domain_registry.get_names():
            self.assertIn(name, result["domains"])
            self.assertEqual(result["domains"][name]["status"], "silent")

    def test_healthy_domain(self):
        """Domain with recent, diverse signals should be 'healthy'."""
        from apps.core.ai_observability.ops_telemetry import compute_signal_health

        # Create recent signals with multiple types
        self._create_insight("health", "weight_trend", hours_ago=2)
        self._create_insight("health", "sleep_quality", hours_ago=4)
        self._create_insight("health", "medication_adherence", hours_ago=6)

        result = compute_signal_health()
        self.assertIn("health", result["domains"])
        health = result["domains"]["health"]
        self.assertEqual(health["status"], "healthy")
        self.assertGreater(health["volume_24h"], 0)
        self.assertGreaterEqual(health["distinct_types_7d"], 2)
        self.assertIsNotNone(health["freshness_hours"])
        self.assertLess(health["freshness_hours"], 24)

    def test_stale_domain(self):
        """Domain with signals only >24h old should be 'stale'."""
        from apps.core.ai_observability.ops_telemetry import compute_signal_health

        self._create_insight("purpose", "goal_progress", hours_ago=30)
        self._create_insight("purpose", "goal_progress", hours_ago=36)

        result = compute_signal_health()
        self.assertIn("purpose", result["domains"])
        purpose = result["domains"]["purpose"]
        # stale: freshness > 24h or distinct_types < 2
        self.assertIn(purpose["status"], ["stale", "silent"])

    def test_silent_domain(self):
        """Domain with signals >72h old should be 'silent'."""
        from apps.core.ai_observability.ops_telemetry import compute_signal_health

        self._create_insight("finance", "budget_alert", hours_ago=100)

        result = compute_signal_health()
        self.assertIn("finance", result["domains"])
        self.assertEqual(result["domains"]["finance"]["status"], "silent")
        # All domains without recent signals are silent (includes registry domains)
        self.assertGreaterEqual(result["domains_silent"], 1)

    def test_stalest_domain_tracked(self):
        """stalest_domain should identify the domain with oldest signal."""
        from apps.core.ai_observability.ops_telemetry import compute_signal_health

        self._create_insight("health", "weight_trend", hours_ago=2)
        self._create_insight("purpose", "goal_progress", hours_ago=100)

        result = compute_signal_health()
        self.assertEqual(result["stalest_domain"], "purpose")
        self.assertGreater(result["stalest_hours"], 90)

    def test_multiple_models_merge(self):
        """Signals from Insight + Prediction in same module should merge."""
        from apps.core.ai_observability.ops_telemetry import compute_signal_health

        self._create_insight("health", "weight_trend", hours_ago=1)
        self._create_prediction("health", "weight_forecast", hours_ago=2)

        result = compute_signal_health()
        health = result["domains"]["health"]
        self.assertGreaterEqual(health["volume_24h"], 2)
        # distinct types should include both insight_type and prediction_type
        self.assertGreaterEqual(health["distinct_types_7d"], 2)

    def test_freshness_hours_calculation(self):
        """freshness_hours should accurately reflect time since last signal."""
        from apps.core.ai_observability.ops_telemetry import compute_signal_health

        self._create_insight("health", "test", hours_ago=5)

        result = compute_signal_health()
        health = result["domains"]["health"]
        # Should be approximately 5 hours (allow some tolerance for test execution)
        self.assertAlmostEqual(health["freshness_hours"], 5.0, delta=0.5)

    def test_domains_active_count(self):
        """domains_active should count non-silent domains."""
        from apps.core.ai_observability.ops_telemetry import compute_signal_health
        from apps.core.domain_registry.registry import registry as domain_registry

        # health: healthy (recent + diverse)
        self._create_insight("health", "weight", hours_ago=1)
        self._create_insight("health", "sleep", hours_ago=2)
        # purpose: silent (freshness 100h > 72h threshold)
        self._create_insight("purpose", "progress", hours_ago=100)

        result = compute_signal_health()
        self.assertEqual(result["domains_active"], 1)  # health only
        # All other registry domains (incl purpose) are silent
        registry_count = domain_registry.domain_count
        self.assertEqual(result["domains_silent"], registry_count - 1)

    def test_result_structure(self):
        """Return value should have all expected keys."""
        from apps.core.ai_observability.ops_telemetry import compute_signal_health

        self._create_insight("health", "test", hours_ago=1)
        result = compute_signal_health()

        self.assertIn("domains_active", result)
        self.assertIn("domains_silent", result)
        self.assertIn("stalest_domain", result)
        self.assertIn("stalest_hours", result)
        self.assertIn("domains", result)

        domain = result["domains"]["health"]
        self.assertIn("last_signal_at", domain)
        self.assertIn("freshness_hours", domain)
        self.assertIn("volume_24h", domain)
        self.assertIn("volume_7d", domain)
        self.assertIn("distinct_types_7d", domain)
        self.assertIn("status", domain)


class DetectSignalDroughtTests(SignalHealthTestMixin, TestCase):
    """Test _detect_signal_drought() SAME detector.

    Severity model (breadth-based, not per-domain freshness):
      0   drought domains → no anomaly
      1-2 drought domains → P3 (informational — likely user inactivity)
      3+  drought domains → P2 (possible pipeline failure)

    Detector returns at most ONE aggregated anomaly.
    """

    def test_no_anomaly_for_recent_signals(self):
        """Domains with recent signals should not trigger drought."""
        from apps.core.ai_observability.same_engine import _detect_signal_drought

        self._create_insight("health", "test", hours_ago=2)
        anomalies = _detect_signal_drought(self.now)
        self.assertEqual(len(anomalies), 0)

    def test_p3_for_single_domain_drought(self):
        """Single domain in drought → P3 (likely user inactivity)."""
        from apps.core.ai_observability.same_engine import _detect_signal_drought

        self._create_insight("health", "test", hours_ago=60)
        anomalies = _detect_signal_drought(self.now)
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0]["severity"], "P3")
        self.assertEqual(anomalies[0]["evidence"]["domain"], "health")
        self.assertIn("health", anomalies[0]["summary"])

    def test_p3_for_two_domain_drought(self):
        """Two domains in drought → still P3 (likely user inactivity)."""
        from apps.core.ai_observability.same_engine import _detect_signal_drought

        self._create_insight("health", "test", hours_ago=60)
        self._create_insight("purpose", "test", hours_ago=200)
        anomalies = _detect_signal_drought(self.now)
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0]["severity"], "P3")
        # Aggregated anomaly includes all drought domains
        self.assertEqual(anomalies[0]["evidence"]["domain_count"], 2)
        self.assertIsInstance(anomalies[0]["evidence"]["drought_domains"], list)

    def test_p2_for_broad_drought(self):
        """3+ domains in drought → P2 (possible pipeline failure)."""
        from apps.core.ai_observability.same_engine import _detect_signal_drought

        self._create_insight("health", "test", hours_ago=60)
        self._create_insight("purpose", "test", hours_ago=200)
        self._create_insight("faith", "test", hours_ago=100)
        anomalies = _detect_signal_drought(self.now)
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0]["severity"], "P2")
        self.assertEqual(anomalies[0]["evidence"]["domain_count"], 3)

    def test_single_aggregated_anomaly(self):
        """Multiple drought domains produce exactly ONE anomaly, not N."""
        from apps.core.ai_observability.same_engine import _detect_signal_drought

        self._create_insight("health", "test", hours_ago=60)
        self._create_insight("purpose", "test", hours_ago=200)
        self._create_insight("faith", "test", hours_ago=100)
        self._create_insight("journal", "test", hours_ago=72)
        anomalies = _detect_signal_drought(self.now)
        self.assertEqual(len(anomalies), 1)
        # Stalest domain is used for backward-compat top-level fields
        self.assertEqual(anomalies[0]["evidence"]["domain"], "purpose")

    def test_no_anomaly_for_unused_domain(self):
        """Domains with zero signals ever should not trigger drought."""
        from apps.core.ai_observability.same_engine import _detect_signal_drought

        # No data at all — should return no anomalies
        anomalies = _detect_signal_drought(self.now)
        self.assertEqual(len(anomalies), 0)

    def test_escalation_exempt(self):
        """SIGNAL_DROUGHT should be exempt from time-based escalation."""
        from apps.core.ai_observability.same_engine import ESCALATION_EXEMPT_TYPES

        self.assertIn("SIGNAL_DROUGHT", ESCALATION_EXEMPT_TYPES)


class DetectSignalLowDiversityTests(SignalHealthTestMixin, TestCase):
    """Test _detect_signal_low_diversity() SAME detector."""

    def test_no_anomaly_for_diverse_signals(self):
        """Domain with diverse signal types should not trigger."""
        from apps.core.ai_observability.same_engine import _detect_signal_low_diversity

        for i in range(10):
            self._create_insight("health", f"type_{i}", hours_ago=i)
        anomalies = _detect_signal_low_diversity(self.now)
        health_low = [
            a for a in anomalies if a["evidence"].get("domain") == "health"
        ]
        self.assertEqual(len(health_low), 0)

    def test_p2_for_single_type_high_volume(self):
        """Domain with 1 type and volume >= 10 should trigger P2."""
        from apps.core.ai_observability.same_engine import _detect_signal_low_diversity

        for i in range(12):
            self._create_insight("health", "same_type", hours_ago=i)
        anomalies = _detect_signal_low_diversity(self.now)
        health_low = [
            a for a in anomalies
            if a["anomaly_type"] == "SIGNAL_LOW_DIVERSITY"
            and a["evidence"].get("domain") == "health"
        ]
        self.assertEqual(len(health_low), 1)
        self.assertEqual(health_low[0]["severity"], "P2")

    def test_no_anomaly_for_low_volume(self):
        """Domain with few signals (even 1 type) shouldn't trigger."""
        from apps.core.ai_observability.same_engine import _detect_signal_low_diversity

        for i in range(3):
            self._create_insight("health", "same_type", hours_ago=i)
        anomalies = _detect_signal_low_diversity(self.now)
        health_low = [
            a for a in anomalies if a["evidence"].get("domain") == "health"
        ]
        self.assertEqual(len(health_low), 0)


class OpsAnomalyTypeTests(TestCase):
    """Test OpsAnomaly model accepts new signal health anomaly types."""

    def test_signal_drought_anomaly_creation(self):
        """Should create OpsAnomaly with SIGNAL_DROUGHT type."""
        from apps.core.ai_observability.models import OpsAnomaly

        anomaly = OpsAnomaly.objects.create(
            anomaly_type="SIGNAL_DROUGHT",
            severity="P2",
            engine_name="",
            summary="Signal drought in 'health' — no signals for 60h",
            evidence={"domain": "health", "freshness_hours": 60},
            suggested_actions=[{"action": "investigate_pipeline", "label": "Check health pipeline"}],
            original_severity="P2",
        )
        self.assertEqual(anomaly.anomaly_type, "SIGNAL_DROUGHT")
        self.assertTrue(anomaly.is_active)

    def test_signal_low_diversity_anomaly_creation(self):
        """Should create OpsAnomaly with SIGNAL_LOW_DIVERSITY type."""
        from apps.core.ai_observability.models import OpsAnomaly

        anomaly = OpsAnomaly.objects.create(
            anomaly_type="SIGNAL_LOW_DIVERSITY",
            severity="P2",
            engine_name="",
            summary="Signal diversity collapse in 'goals'",
            evidence={"domain": "goals", "distinct_types_7d": 1, "volume_7d": 15},
            suggested_actions=[],
            original_severity="P2",
        )
        self.assertEqual(anomaly.anomaly_type, "SIGNAL_LOW_DIVERSITY")


class CacheSignalHealthTests(SignalHealthTestMixin, TestCase):
    """Test signal health caching and retrieval."""

    def test_cache_signal_health_stores_data(self):
        """_cache_signal_health() should store result in Django cache."""
        from django.core.cache import cache

        from apps.core.ai_observability.same_engine import _cache_signal_health

        self._create_insight("health", "test", hours_ago=1)
        _cache_signal_health()

        cached = cache.get("wlj:ops:signal_health")
        self.assertIsNotNone(cached)
        self.assertIn("domains", cached)
        self.assertIn("health", cached["domains"])

    def test_get_signal_health_reads_cache(self):
        """_get_signal_health() should return cached data when available."""
        from django.core.cache import cache

        from apps.core.ai_observability.ops_telemetry import _get_signal_health

        test_data = {"domains_active": 5, "domains": {"test": {}}}
        cache.set("wlj:ops:signal_health", test_data, timeout=120)

        result = _get_signal_health()
        self.assertEqual(result["domains_active"], 5)

    def test_get_signal_health_returns_none_on_empty_cache(self):
        """_get_signal_health() returns None when cache is empty (no live fallback)."""
        from django.core.cache import cache

        from apps.core.ai_observability.ops_telemetry import _get_signal_health

        cache.delete("wlj:ops:signal_health")
        self._create_insight("health", "test", hours_ago=1)

        result = _get_signal_health()
        self.assertIsNone(result)
