"""
Tests for CoS Performance Diagnostics (Ops Wall 2.0 — Phase 4).

Tests cover:
  - compute_cos_performance() aggregation logic
  - _get_cos_performance() cache-read + fallback
  - _cache_cos_performance() caching behavior
  - Status thresholds (healthy/degraded/critical/no_data)
  - Slowest builders breakdown
  - Cache hit rate heuristic
  - P50/P95 percentile computation

Project: Whole Life Journey
Path: apps/core/ai_observability/tests_cos_performance.py
"""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone


class ComputeCosPerformanceTests(TestCase):
    """Test compute_cos_performance() aggregation."""

    def _create_snapshot(self, stages=None, meta=None, total_ms=1000, hours_ago=0):
        """Helper to create a ChatLatencySnapshot with adjustable data."""
        from apps.core.ai_observability.models import ChatLatencySnapshot

        obj = ChatLatencySnapshot.objects.create(
            stages=stages or {},
            meta=meta or {},
            total_ms=total_ms,
            user_id=1,
        )
        if hours_ago > 0:
            target = timezone.now() - timedelta(hours=hours_ago)
            ChatLatencySnapshot.objects.filter(pk=obj.pk).update(created_at=target)
            obj.refresh_from_db()
        return obj

    def test_empty_returns_no_data(self):
        """No snapshots should return status 'no_data'."""
        from apps.core.ai_observability.ops_telemetry import compute_cos_performance

        result = compute_cos_performance()
        self.assertEqual(result["sample_count_24h"], 0)
        self.assertEqual(result["status"], "no_data")
        self.assertIsNone(result["p50_context_build_ms"])
        self.assertIsNone(result["p95_context_build_ms"])
        self.assertIsNone(result["p95_ttft_ms"])
        self.assertIsNone(result["cache_hit_rate"])
        self.assertEqual(result["slowest_builders"], [])

    def test_healthy_status(self):
        """P95 context build < 2000ms should return 'healthy'."""
        from apps.core.ai_observability.ops_telemetry import compute_cos_performance

        for _ in range(10):
            self._create_snapshot(
                stages={"COS_CONTEXT_BUILD_TOTAL": 500, "LLM_REQUEST": 800},
                meta={"prompt_tokens": 1500},
                total_ms=1300,
            )

        result = compute_cos_performance()
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["sample_count_24h"], 10)
        self.assertIsNotNone(result["p50_context_build_ms"])
        self.assertIsNotNone(result["p95_context_build_ms"])
        self.assertLessEqual(result["p95_context_build_ms"], 2000)

    def test_degraded_status(self):
        """P95 context build 2000-5000ms should return 'degraded'."""
        from apps.core.ai_observability.ops_telemetry import compute_cos_performance

        # All builds at 3000ms — P95 will be 3000ms (degraded range: 2000-5000)
        for _ in range(10):
            self._create_snapshot(
                stages={"COS_CONTEXT_BUILD_TOTAL": 3000},
                total_ms=4000,
            )

        result = compute_cos_performance()
        self.assertEqual(result["status"], "degraded")

    def test_critical_status(self):
        """P95 context build > 5000ms should return 'critical'."""
        from apps.core.ai_observability.ops_telemetry import compute_cos_performance

        # All slow — P95 will be above 5000
        for _ in range(10):
            self._create_snapshot(
                stages={"COS_CONTEXT_BUILD_TOTAL": 6000},
                total_ms=8000,
            )

        result = compute_cos_performance()
        self.assertEqual(result["status"], "critical")
        self.assertGreater(result["p95_context_build_ms"], 5000)

    def test_cache_hit_rate_heuristic(self):
        """Snapshots with COS_CONTEXT_BUILD_TOTAL < 100ms should count as cache hits."""
        from apps.core.ai_observability.ops_telemetry import compute_cos_performance

        # 5 cache hits (< 100ms) + 5 cache misses (> 100ms)
        for _ in range(5):
            self._create_snapshot(
                stages={"COS_CONTEXT_BUILD_TOTAL": 50},
                total_ms=900,
            )
        for _ in range(5):
            self._create_snapshot(
                stages={"COS_CONTEXT_BUILD_TOTAL": 500},
                total_ms=1500,
            )

        result = compute_cos_performance()
        self.assertEqual(result["cache_hit_rate"], 0.5)

    def test_cache_hit_rate_all_hits(self):
        """All fast builds should give cache_hit_rate = 1.0."""
        from apps.core.ai_observability.ops_telemetry import compute_cos_performance

        for _ in range(5):
            self._create_snapshot(
                stages={"COS_CONTEXT_BUILD_TOTAL": 30},
                total_ms=800,
            )

        result = compute_cos_performance()
        self.assertEqual(result["cache_hit_rate"], 1.0)

    def test_p95_ttft(self):
        """P95 TTFT should come from LLM_REQUEST stage."""
        from apps.core.ai_observability.ops_telemetry import compute_cos_performance

        for _ in range(10):
            self._create_snapshot(
                stages={
                    "COS_CONTEXT_BUILD_TOTAL": 300,
                    "LLM_REQUEST": 1200,
                },
                total_ms=1500,
            )

        result = compute_cos_performance()
        self.assertIsNotNone(result["p95_ttft_ms"])
        self.assertGreater(result["p95_ttft_ms"], 0)

    def test_avg_prompt_tokens(self):
        """avg_prompt_tokens should average meta.prompt_tokens across snapshots."""
        from apps.core.ai_observability.ops_telemetry import compute_cos_performance

        self._create_snapshot(
            stages={"COS_CONTEXT_BUILD_TOTAL": 200},
            meta={"prompt_tokens": 1000},
            total_ms=1200,
        )
        self._create_snapshot(
            stages={"COS_CONTEXT_BUILD_TOTAL": 200},
            meta={"prompt_tokens": 2000},
            total_ms=1200,
        )

        result = compute_cos_performance()
        self.assertEqual(result["avg_prompt_tokens"], 1500)

    def test_avg_total_ms(self):
        """avg_total_ms should average total_ms across snapshots."""
        from apps.core.ai_observability.ops_telemetry import compute_cos_performance

        self._create_snapshot(
            stages={"COS_CONTEXT_BUILD_TOTAL": 200},
            total_ms=1000,
        )
        self._create_snapshot(
            stages={"COS_CONTEXT_BUILD_TOTAL": 200},
            total_ms=2000,
        )

        result = compute_cos_performance()
        self.assertEqual(result["avg_total_ms"], 1500)

    def test_slowest_builders(self):
        """slowest_builders should return top 5 builders by avg duration."""
        from apps.core.ai_observability.ops_telemetry import compute_cos_performance

        for _ in range(5):
            self._create_snapshot(
                stages={
                    "COS_CONTEXT_BUILD_TOTAL": 500,
                    "COS_BUILDER_HEALTH": 200,
                    "COS_BUILDER_JOURNAL": 150,
                    "COS_BUILDER_GOALS": 80,
                    "COS_BUILDER_FAITH": 40,
                    "COS_BUILDER_ROUTINES": 20,
                    "COS_BUILDER_FINANCE": 10,
                },
                total_ms=1000,
            )

        result = compute_cos_performance()
        builders = result["slowest_builders"]
        self.assertEqual(len(builders), 5)
        # Should be sorted descending by avg_ms
        self.assertEqual(builders[0]["name"], "HEALTH")
        self.assertEqual(builders[0]["avg_ms"], 200.0)
        self.assertEqual(builders[1]["name"], "JOURNAL")
        self.assertEqual(builders[-1]["name"], "ROUTINES")

    def test_windows_respect_time(self):
        """Snapshots outside 24h window should not be counted."""
        from apps.core.ai_observability.ops_telemetry import compute_cos_performance

        # Old snapshot (26h ago)
        self._create_snapshot(
            stages={"COS_CONTEXT_BUILD_TOTAL": 6000},
            total_ms=8000,
            hours_ago=26,
        )

        # Recent snapshot
        self._create_snapshot(
            stages={"COS_CONTEXT_BUILD_TOTAL": 300},
            total_ms=1200,
        )

        result = compute_cos_performance()
        # Should only see 1 snapshot (the recent one), status should be healthy
        self.assertEqual(result["sample_count_24h"], 1)
        self.assertEqual(result["status"], "healthy")

    def test_result_structure(self):
        """Return value should have all expected keys."""
        from apps.core.ai_observability.ops_telemetry import compute_cos_performance

        self._create_snapshot(
            stages={"COS_CONTEXT_BUILD_TOTAL": 200},
            total_ms=1000,
        )
        result = compute_cos_performance()

        expected_keys = [
            "sample_count_24h",
            "p50_context_build_ms",
            "p95_context_build_ms",
            "p95_ttft_ms",
            "cache_hit_rate",
            "avg_prompt_tokens",
            "avg_total_ms",
            "slowest_builders",
            "status",
        ]
        for key in expected_keys:
            self.assertIn(key, result, f"Missing key: {key}")


class CacheCosPerformanceTests(TestCase):
    """Test CoS performance caching and retrieval."""

    def _create_snapshot(self, stages=None, total_ms=1000):
        from apps.core.ai_observability.models import ChatLatencySnapshot

        ChatLatencySnapshot.objects.create(
            stages=stages or {"COS_CONTEXT_BUILD_TOTAL": 200},
            meta={},
            total_ms=total_ms,
            user_id=1,
        )

    def test_cache_cos_performance_stores_data(self):
        """_cache_cos_performance() should store result in Django cache."""
        from django.core.cache import cache

        from apps.core.ai_observability.same_engine import _cache_cos_performance

        self._create_snapshot()
        _cache_cos_performance()

        cached = cache.get("wlj:ops:cos_performance")
        self.assertIsNotNone(cached)
        self.assertIn("status", cached)
        self.assertIn("sample_count_24h", cached)

    def test_get_cos_performance_reads_cache(self):
        """_get_cos_performance() should return cached data when available."""
        from django.core.cache import cache

        from apps.core.ai_observability.ops_telemetry import _get_cos_performance

        test_data = {"status": "healthy", "sample_count_24h": 42}
        cache.set("wlj:ops:cos_performance", test_data, timeout=120)

        result = _get_cos_performance()
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["sample_count_24h"], 42)

    def test_get_cos_performance_fallback_on_empty_cache(self):
        """_get_cos_performance() should compute live when cache is empty."""
        from django.core.cache import cache

        from apps.core.ai_observability.ops_telemetry import _get_cos_performance

        cache.delete("wlj:ops:cos_performance")
        self._create_snapshot()

        result = _get_cos_performance()
        self.assertIsNotNone(result)
        self.assertIn("status", result)
