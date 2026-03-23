"""
Ops Stream Payload Builder — Resilience Tests.

Covers:
  - _build_section() error isolation and freshness metadata
  - build_ops_stream_payload() section-level fault tolerance
  - Stale carry-forward from previous cached payload
  - _build_telemetry summary accuracy
  - _section_meta presence for all sections

Project: Whole Life Journey
Path: apps/core/ai_observability/tests_payload_builder.py
"""

from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.ai_observability.ops_telemetry import (
    OPS_STREAM_CACHE_KEY,
    _build_section,
    build_ops_stream_payload,
)


class BuildSectionTests(TestCase):
    """Tests for the _build_section() error isolation wrapper."""

    def test_successful_section_returns_data_and_meta(self):
        """A successful builder returns its data with healthy meta."""
        data, meta = _build_section("test_section", lambda: {"key": "value"})
        self.assertEqual(data, {"key": "value"})
        self.assertEqual(meta["source"], "test_section")
        self.assertFalse(meta["stale"])
        self.assertFalse(meta["degraded"])
        self.assertIn("computed_at", meta)
        self.assertIn("build_ms", meta)

    def test_none_return_marks_degraded(self):
        """A builder that returns None is marked degraded."""
        data, meta = _build_section("empty_section", lambda: None)
        self.assertIsNone(data)
        self.assertFalse(meta["stale"])
        self.assertTrue(meta["degraded"])

    def test_exception_marks_stale_and_degraded(self):
        """A builder that throws is caught and marked stale + degraded."""
        def broken_builder():
            raise RuntimeError("DB connection lost")

        data, meta = _build_section("broken_section", broken_builder)
        self.assertIsNone(data)
        self.assertTrue(meta["stale"])
        self.assertTrue(meta["degraded"])
        self.assertIn("DB connection lost", meta["error"])
        self.assertEqual(meta["source"], "broken_section")

    def test_builder_with_args(self):
        """Builder receives positional and keyword arguments."""
        def builder_with_args(a, b, key=None):
            return {"a": a, "b": b, "key": key}

        data, meta = _build_section("args_test", builder_with_args, 1, 2, key="val")
        self.assertEqual(data, {"a": 1, "b": 2, "key": "val"})
        self.assertFalse(meta["degraded"])

    def test_build_ms_is_non_negative(self):
        """build_ms should always be a non-negative integer."""
        data, meta = _build_section("timing_test", lambda: {})
        self.assertIsInstance(meta["build_ms"], int)
        self.assertGreaterEqual(meta["build_ms"], 0)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class BuildOpsStreamPayloadTests(TestCase):
    """Tests for the full payload builder with error isolation."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    @patch("apps.core.ai_observability.ops_telemetry._build_engine_cards")
    @patch("apps.core.ai_observability.ops_telemetry._get_latest_narrative")
    @patch("apps.core.ai_observability.ops_telemetry._get_active_anomalies")
    @patch("apps.core.ai_observability.ops_telemetry._get_latest_integrity")
    @patch("apps.core.ai_observability.ops_telemetry._get_scheduler_heartbeats")
    @patch("apps.core.ai_observability.ops_telemetry._get_eae_ops_telemetry")
    @patch("apps.core.ai_observability.ops_telemetry._get_scheduler_health")
    @patch("apps.core.ai_observability.ops_telemetry._get_celery_health")
    @patch("apps.core.ai_observability.ops_telemetry._get_learning_health")
    @patch("apps.core.ai_observability.ops_telemetry._get_health_intelligence_telemetry")
    @patch("apps.core.ai_observability.ops_telemetry._get_coas_health")
    @patch("apps.core.ai_observability.ops_telemetry._get_aafr_metrics")
    @patch("apps.core.ai_observability.ops_telemetry._get_complexity_score")
    @patch("apps.core.ai_observability.ops_telemetry._get_domain_event_telemetry")
    @patch("apps.core.ai_observability.ops_telemetry._get_chat_latency_telemetry")
    @patch("apps.core.ai_observability.ops_telemetry._get_intelligence_pipeline_health")
    @patch("apps.core.ai_observability.ops_telemetry._get_signal_health")
    @patch("apps.core.ai_observability.ops_telemetry._get_validator_health")
    @patch("apps.core.ai_observability.ops_telemetry._get_cos_performance")
    @patch("apps.core.ai_observability.ops_telemetry._get_api_health_telemetry")
    @patch("apps.core.ai_observability.ops_telemetry._get_email_intelligence_telemetry")
    @patch("apps.core.ai_observability.ops_feed.get_recent_feed")
    @patch("apps.core.ai_observability.heartbeat.get_latest_heartbeats")
    @patch("apps.core.ai_observability.heartbeat.get_cadence_config")
    def test_payload_includes_section_meta_for_all_sections(self, *mocks):
        """Every section should have a corresponding _section_meta entry."""
        # All mocks return empty dicts by default
        for m in mocks:
            m.return_value = {}

        payload = build_ops_stream_payload()

        self.assertIn("_section_meta", payload)
        meta = payload["_section_meta"]

        expected_sections = [
            "engine_cards", "narrative", "anomalies", "feed", "integrity",
            "scheduler_heartbeats", "eae_telemetry", "scheduler_health",
            "celery_health", "learning_health", "health_intelligence",
            "coas_health", "aafr", "complexity", "domain_events",
            "chat_latency", "pipeline_health", "signal_health",
            "validator_health", "cos_performance", "api_health",
            "email_intelligence",
        ]
        for section in expected_sections:
            self.assertIn(section, meta, f"Missing _section_meta for '{section}'")
            self.assertIn("computed_at", meta[section])
            self.assertIn("build_ms", meta[section])
            self.assertIn("stale", meta[section])
            self.assertIn("degraded", meta[section])

    @patch("apps.core.ai_observability.ops_telemetry._build_engine_cards")
    @patch("apps.core.ai_observability.ops_telemetry._get_latest_narrative")
    @patch("apps.core.ai_observability.ops_telemetry._get_active_anomalies")
    @patch("apps.core.ai_observability.ops_telemetry._get_latest_integrity")
    @patch("apps.core.ai_observability.ops_telemetry._get_scheduler_heartbeats")
    @patch("apps.core.ai_observability.ops_telemetry._get_eae_ops_telemetry")
    @patch("apps.core.ai_observability.ops_telemetry._get_scheduler_health")
    @patch("apps.core.ai_observability.ops_telemetry._get_celery_health")
    @patch("apps.core.ai_observability.ops_telemetry._get_learning_health")
    @patch("apps.core.ai_observability.ops_telemetry._get_health_intelligence_telemetry")
    @patch("apps.core.ai_observability.ops_telemetry._get_coas_health")
    @patch("apps.core.ai_observability.ops_telemetry._get_aafr_metrics")
    @patch("apps.core.ai_observability.ops_telemetry._get_complexity_score")
    @patch("apps.core.ai_observability.ops_telemetry._get_domain_event_telemetry")
    @patch("apps.core.ai_observability.ops_telemetry._get_chat_latency_telemetry")
    @patch("apps.core.ai_observability.ops_telemetry._get_intelligence_pipeline_health")
    @patch("apps.core.ai_observability.ops_telemetry._get_signal_health")
    @patch("apps.core.ai_observability.ops_telemetry._get_validator_health")
    @patch("apps.core.ai_observability.ops_telemetry._get_cos_performance")
    @patch("apps.core.ai_observability.ops_telemetry._get_api_health_telemetry")
    @patch("apps.core.ai_observability.ops_telemetry._get_email_intelligence_telemetry")
    @patch("apps.core.ai_observability.ops_feed.get_recent_feed")
    @patch("apps.core.ai_observability.heartbeat.get_latest_heartbeats")
    @patch("apps.core.ai_observability.heartbeat.get_cadence_config")
    def test_single_section_failure_does_not_break_payload(self, *mocks):
        """If one section throws, the rest should still build successfully."""
        for m in mocks:
            m.return_value = {}

        # Make signal_health throw — it's the 8th mock from the end
        # Mocks are passed in reverse order of decoration
        # _get_signal_health is the 7th from the bottom → index 7
        mocks[7].side_effect = RuntimeError("Redis down")

        payload = build_ops_stream_payload()

        # Payload should still exist and be cached
        self.assertIsNotNone(payload)
        cached = cache.get(OPS_STREAM_CACHE_KEY)
        self.assertIsNotNone(cached)

        # The failed section should be None
        self.assertIsNone(payload["signal_health"])

        # Other sections should be fine
        self.assertIsNotNone(payload.get("engine_cards"))

        # Build telemetry should report the degraded section
        telemetry = payload["_build_telemetry"]
        self.assertGreaterEqual(telemetry["sections_degraded"], 1)

    @patch("apps.core.ai_observability.ops_telemetry._build_engine_cards")
    @patch("apps.core.ai_observability.ops_telemetry._get_latest_narrative")
    @patch("apps.core.ai_observability.ops_telemetry._get_active_anomalies")
    @patch("apps.core.ai_observability.ops_telemetry._get_latest_integrity")
    @patch("apps.core.ai_observability.ops_telemetry._get_scheduler_heartbeats")
    @patch("apps.core.ai_observability.ops_telemetry._get_eae_ops_telemetry")
    @patch("apps.core.ai_observability.ops_telemetry._get_scheduler_health")
    @patch("apps.core.ai_observability.ops_telemetry._get_celery_health")
    @patch("apps.core.ai_observability.ops_telemetry._get_learning_health")
    @patch("apps.core.ai_observability.ops_telemetry._get_health_intelligence_telemetry")
    @patch("apps.core.ai_observability.ops_telemetry._get_coas_health")
    @patch("apps.core.ai_observability.ops_telemetry._get_aafr_metrics")
    @patch("apps.core.ai_observability.ops_telemetry._get_complexity_score")
    @patch("apps.core.ai_observability.ops_telemetry._get_domain_event_telemetry")
    @patch("apps.core.ai_observability.ops_telemetry._get_chat_latency_telemetry")
    @patch("apps.core.ai_observability.ops_telemetry._get_intelligence_pipeline_health")
    @patch("apps.core.ai_observability.ops_telemetry._get_signal_health")
    @patch("apps.core.ai_observability.ops_telemetry._get_validator_health")
    @patch("apps.core.ai_observability.ops_telemetry._get_cos_performance")
    @patch("apps.core.ai_observability.ops_telemetry._get_api_health_telemetry")
    @patch("apps.core.ai_observability.ops_telemetry._get_email_intelligence_telemetry")
    @patch("apps.core.ai_observability.ops_feed.get_recent_feed")
    @patch("apps.core.ai_observability.heartbeat.get_latest_heartbeats")
    @patch("apps.core.ai_observability.heartbeat.get_cadence_config")
    def test_stale_carry_forward_on_section_failure(self, *mocks):
        """When a section fails, previous payload data is carried forward as stale."""
        for m in mocks:
            m.return_value = {}

        # First build: signal_health returns real data
        mocks[7].return_value = {"status": "healthy", "domains": []}
        payload_1 = build_ops_stream_payload()
        self.assertEqual(payload_1["signal_health"], {"status": "healthy", "domains": []})

        # Second build: signal_health throws
        mocks[7].side_effect = RuntimeError("Redis timeout")
        payload_2 = build_ops_stream_payload()

        # Should carry forward previous data
        self.assertEqual(payload_2["signal_health"], {"status": "healthy", "domains": []})
        meta = payload_2["_section_meta"]["signal_health"]
        self.assertTrue(meta["stale"])
        self.assertFalse(meta["degraded"])  # Not degraded because we carried forward
        self.assertTrue(meta.get("carry_forward"))

    @patch("apps.core.ai_observability.ops_telemetry._build_engine_cards")
    @patch("apps.core.ai_observability.ops_telemetry._get_latest_narrative")
    @patch("apps.core.ai_observability.ops_telemetry._get_active_anomalies")
    @patch("apps.core.ai_observability.ops_telemetry._get_latest_integrity")
    @patch("apps.core.ai_observability.ops_telemetry._get_scheduler_heartbeats")
    @patch("apps.core.ai_observability.ops_telemetry._get_eae_ops_telemetry")
    @patch("apps.core.ai_observability.ops_telemetry._get_scheduler_health")
    @patch("apps.core.ai_observability.ops_telemetry._get_celery_health")
    @patch("apps.core.ai_observability.ops_telemetry._get_learning_health")
    @patch("apps.core.ai_observability.ops_telemetry._get_health_intelligence_telemetry")
    @patch("apps.core.ai_observability.ops_telemetry._get_coas_health")
    @patch("apps.core.ai_observability.ops_telemetry._get_aafr_metrics")
    @patch("apps.core.ai_observability.ops_telemetry._get_complexity_score")
    @patch("apps.core.ai_observability.ops_telemetry._get_domain_event_telemetry")
    @patch("apps.core.ai_observability.ops_telemetry._get_chat_latency_telemetry")
    @patch("apps.core.ai_observability.ops_telemetry._get_intelligence_pipeline_health")
    @patch("apps.core.ai_observability.ops_telemetry._get_signal_health")
    @patch("apps.core.ai_observability.ops_telemetry._get_validator_health")
    @patch("apps.core.ai_observability.ops_telemetry._get_cos_performance")
    @patch("apps.core.ai_observability.ops_telemetry._get_api_health_telemetry")
    @patch("apps.core.ai_observability.ops_telemetry._get_email_intelligence_telemetry")
    @patch("apps.core.ai_observability.ops_feed.get_recent_feed")
    @patch("apps.core.ai_observability.heartbeat.get_latest_heartbeats")
    @patch("apps.core.ai_observability.heartbeat.get_cadence_config")
    def test_build_telemetry_summary(self, *mocks):
        """_build_telemetry should have accurate section counts and timings."""
        for m in mocks:
            m.return_value = {}

        payload = build_ops_stream_payload()

        telemetry = payload["_build_telemetry"]
        self.assertIn("total_ms", telemetry)
        self.assertEqual(telemetry["sections_ok"], 22)
        self.assertEqual(telemetry["sections_degraded"], 0)
        self.assertIn("section_timings", telemetry)
        self.assertEqual(len(telemetry["section_timings"]), 22)
