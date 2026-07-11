"""
OPS-4 — OpenAI Upstream Health Monitor tests.

Proves the passive recorder + degradation state machine:
  * no traffic  → IDLE,
  * successes   → HEALTHY with availability + latency,
  * consecutive failures → OUTAGE (attributable to the upstream, not WLJ),
  * elevated error rate / tripped breaker → DEGRADED,
  * a success resets the consecutive-failure counter and stamps last_success.

Uses the real Django cache (LocMemCache in tests), exercised through the same
per-minute bucket keys production uses.

Path: apps/core/tests/test_upstream_health.py
"""

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.ai_observability import upstream_health as uh


class UpstreamHealthTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_idle_when_no_traffic(self):
        out = uh.get_upstream_health_telemetry()
        self.assertEqual(out["status"], "IDLE")
        self.assertEqual(out["total_calls"], 0)
        self.assertIsNone(out["availability_pct"])

    def test_success_is_healthy_with_latency(self):
        for _ in range(5):
            uh.record_llm_outcome(success=True, latency_ms=800)
        out = uh.get_upstream_health_telemetry()
        self.assertEqual(out["status"], "HEALTHY")
        self.assertEqual(out["total_calls"], 5)
        self.assertEqual(out["availability_pct"], 100.0)
        self.assertEqual(out["avg_latency_ms"], 800)
        self.assertIsNotNone(out["last_success_at"])
        self.assertEqual(out["consecutive_failures"], 0)

    def test_consecutive_failures_is_outage(self):
        for _ in range(uh.CONSECUTIVE_OUTAGE):
            uh.record_llm_outcome(success=False, error_class="APITimeoutError")
        out = uh.get_upstream_health_telemetry()
        self.assertEqual(out["status"], "OUTAGE")
        self.assertGreaterEqual(out["consecutive_failures"], uh.CONSECUTIVE_OUTAGE)
        self.assertEqual(out["last_error"], "APITimeoutError")

    def test_elevated_error_rate_is_degraded(self):
        # 8 ok + 4 err in-window → 33% error rate, but only 4 consecutive-safe
        # because the last call is a success (resets consecutive).
        for _ in range(4):
            uh.record_llm_outcome(success=False, error_class="RateLimitError")
        for _ in range(8):
            uh.record_llm_outcome(success=True, latency_ms=500)
        out = uh.get_upstream_health_telemetry()
        # Error rate 4/12 = 33% ≥ 25% → DEGRADED (consecutive reset by successes).
        self.assertEqual(out["status"], "DEGRADED")
        self.assertEqual(out["consecutive_failures"], 0)

    def test_breaker_active_forces_degraded(self):
        uh.record_llm_outcome(success=True, latency_ms=300)
        cache.set("openai_rate_limited", True, timeout=120)
        out = uh.get_upstream_health_telemetry()
        self.assertTrue(out["breaker_active"])
        self.assertEqual(out["status"], "DEGRADED")

    def test_success_resets_consecutive_failures(self):
        uh.record_llm_outcome(success=False, error_class="APIError")
        uh.record_llm_outcome(success=False, error_class="APIError")
        uh.record_llm_outcome(success=True, latency_ms=200)
        out = uh.get_upstream_health_telemetry()
        # A success clears the consecutive-failure streak (no longer OUTAGE)...
        self.assertEqual(out["consecutive_failures"], 0)
        # ...but the trailing window still shows 2/3 errors, so the service is
        # correctly still DEGRADED until fresh successes dilute the rate.
        self.assertEqual(out["status"], "DEGRADED")

    def test_recovery_to_healthy_after_successes(self):
        uh.record_llm_outcome(success=False, error_class="APIError")
        for _ in range(9):
            uh.record_llm_outcome(success=True, latency_ms=200)
        out = uh.get_upstream_health_telemetry()
        # 1/10 = 10% error rate < 25% → back to HEALTHY.
        self.assertEqual(out["status"], "HEALTHY")
        self.assertEqual(out["consecutive_failures"], 0)

    def test_recorder_never_raises(self):
        # Even with odd inputs the recorder must be fire-and-forget.
        try:
            uh.record_llm_outcome(success=False, latency_ms=None,
                                  error_class=None, status_code=None)
        except Exception as e:  # pragma: no cover
            self.fail(f"record_llm_outcome raised: {e}")
