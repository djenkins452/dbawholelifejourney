"""
Ops Command Center — Executive Synthesis tests.

Proves the deterministic reduction over existing telemetry:
  * a fully-healthy payload → HEALTHY, customer impact None, no incidents,
  * a degraded upstream → DEGRADED/CRITICAL with the right customer-impact phrase,
  * score deductions are itemized from integrity components + anomalies,
  * the single highest-priority recommendation is chosen deterministically,
  * incidents are enriched (cause, confidence, affected, root-cause chain),
  * customer impact takes the WORST of section + anomaly impacts,
  * plain-English summary + narrative are assembled from state (no invention),
  * trends classify direction from the KPI history.

Path: apps/core/tests/test_ops_executive.py
"""

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.ai_observability import ops_executive as ex


def _healthy_sections():
    return {
        "integrity": {"score": 100, "posture": "OPTIMAL", "components": {}},
        "anomalies": [],
        "chat_queue": {"status": "HEALTHY", "queue_depth": 0},
        "upstream_health": {"status": "HEALTHY", "avg_latency_ms": 700, "error_rate_pct": 0.0},
        "storage": {"status": "HEALTHY", "postgres": {"status": "HEALTHY"},
                    "redis": {"status": "HEALTHY"}, "disk": {"status": "HEALTHY"}},
        "api_health": {"status": "HEALTHY", "error_rate_pct": 0.0},
        "scheduler_health": {"status": "HEALTHY"},
    }


class HealthyPathTests(TestCase):
    def setUp(self):
        cache.delete(ex._KPI_HISTORY_KEY)

    def test_all_healthy(self):
        out = ex.build_executive_summary(_healthy_sections())
        self.assertEqual(out["overall_status"], "HEALTHY")
        self.assertEqual(out["customer_impact"], "None")
        self.assertEqual(out["active_incident_count"], 0)
        self.assertIsNone(out["recommended_action"])
        self.assertIn("WLJ is operational.", out["summary_lines"])
        self.assertTrue(out["narrative"])


class DegradedUpstreamTests(TestCase):
    def setUp(self):
        cache.delete(ex._KPI_HISTORY_KEY)

    def test_upstream_outage_is_critical_high_impact(self):
        s = _healthy_sections()
        s["upstream_health"] = {"status": "OUTAGE", "avg_latency_ms": None, "error_rate_pct": 100.0}
        out = ex.build_executive_summary(s)
        self.assertEqual(out["overall_status"], "CRITICAL")
        self.assertEqual(out["customer_impact"], "High")
        self.assertIn("AI chat unavailable", out["customer_impact_phrases"])

    def test_upstream_degraded_is_medium_impact(self):
        s = _healthy_sections()
        s["integrity"] = {"score": 88, "posture": "NOMINAL", "components": {}}
        s["upstream_health"] = {"status": "DEGRADED", "avg_latency_ms": 9000, "error_rate_pct": 30.0}
        out = ex.build_executive_summary(s)
        self.assertEqual(out["overall_status"], "DEGRADED")
        self.assertEqual(out["customer_impact"], "Medium")
        self.assertIn("Slower or failing AI responses", out["customer_impact_phrases"])


class ScoreExplanationTests(TestCase):
    def setUp(self):
        cache.delete(ex._KPI_HISTORY_KEY)

    def test_deductions_from_components_and_anomalies(self):
        s = _healthy_sections()
        s["integrity"] = {
            "score": 90,
            "posture": "NOMINAL",
            "components": {
                "scheduler_health": {"penalty": 5, "ise": {"status": "DELAYED"},
                                     "same": {"status": "OK"}},
                "engine_health": {"penalty": 0, "ok_count": 46, "total": 46},
                "error_spike": {"penalty": 3},
            },
        }
        s["anomalies"] = [
            {"id": 1, "severity": "P2", "engine_name": "SAE",
             "anomaly_type": "ERROR_SPIKE", "summary": "SAE errors",
             "suggested_actions": [], "created_at": timezone.now().isoformat(),
             "first_detected": "5m ago", "escalation_count": 0},
        ]
        out = ex.build_executive_summary(s)
        labels = [d["label"] for d in out["score"]["deductions"]]
        # Per-anomaly deduction present…
        self.assertTrue(any("Error Spike" in lbl for lbl in labels))
        # …and structural penalties present.
        self.assertTrue(any("Scheduler degraded" in lbl for lbl in labels))
        self.assertTrue(any("Engine error rate" in lbl for lbl in labels))
        # All deductions are negative.
        self.assertTrue(all(d["points"] < 0 for d in out["score"]["deductions"]))


class RecommendationTests(TestCase):
    def setUp(self):
        cache.delete(ex._KPI_HISTORY_KEY)

    def test_highest_priority_incident_chosen(self):
        now = timezone.now()
        s = _healthy_sections()
        s["integrity"] = {"score": 70, "posture": "DEGRADED", "components": {}}
        s["anomalies"] = [
            {"id": 10, "severity": "P3", "engine_name": "PIE",
             "anomaly_type": "SIGNAL_DROUGHT", "summary": "PIE drought",
             "suggested_actions": [{"action": "x", "label": "Check PIE"}],
             "created_at": now.isoformat(), "first_detected": "2m ago",
             "escalation_count": 0},
            {"id": 11, "severity": "P1", "engine_name": "SAE",
             "anomaly_type": "ERROR_SPIKE", "summary": "SAE spike",
             "suggested_actions": [{"action": "rerun_engine", "label": "Re-run SAE now"}],
             "created_at": now.isoformat(), "first_detected": "8m ago",
             "escalation_count": 1},
        ]
        out = ex.build_executive_summary(s)
        rec = out["recommended_action"]
        self.assertIsNotNone(rec)
        # P1 SAE beats P3 PIE.
        self.assertEqual(rec["engine"], "SAE")
        self.assertEqual(rec["severity_label"], "Critical")
        self.assertGreaterEqual(rec["confidence"], 90)
        # Only ONE recommendation is surfaced.
        self.assertIn("incident_id", rec)

    def test_incident_enrichment_fields(self):
        now = timezone.now()
        s = _healthy_sections()
        s["storage"] = {"status": "CRITICAL", "postgres": {"status": "HEALTHY"},
                        "redis": {"status": "CRITICAL"}, "disk": {"status": "HEALTHY"}}
        s["anomalies"] = [
            {"id": 20, "severity": "P2", "engine_name": "SAE",
             "anomaly_type": "ERROR_SPIKE", "summary": "SAE errors",
             "evidence": {"task_name": "sae.rebuild"},
             "suggested_actions": [{"action": "rerun_engine", "label": "Re-run SAE"}],
             "created_at": now.isoformat(), "first_detected": "3m ago",
             "escalation_count": 0},
        ]
        out = ex.build_executive_summary(s)
        inc = out["incidents"][0]
        for key in ("severity_label", "likely_cause", "confidence",
                    "affected_components", "customer_impact", "suggested_action",
                    "status", "recovery_state", "root_cause_chain", "duration"):
            self.assertIn(key, inc)
        # Root-cause chain correlated Redis (currently CRITICAL) into the chain.
        self.assertTrue(any("Redis" in step for step in inc["root_cause_chain"]))


class TrendTests(TestCase):
    def setUp(self):
        cache.delete(ex._KPI_HISTORY_KEY)

    def test_score_trend_declining(self):
        # Feed a descending score history across cycles.
        for score in (100, 98, 95, 90, 82):
            s = _healthy_sections()
            s["integrity"] = {"score": score, "posture": "NOMINAL", "components": {}}
            out = ex.build_executive_summary(s)
        self.assertIn(out["score"]["trend"]["semantic"],
                      ("declining", "rapidly_declining"))

    def test_classify_trend_stable(self):
        t = ex._classify_trend([90, 91, 90, 90], "up_good")
        self.assertEqual(t["semantic"], "stable")

    def test_classify_trend_improving_when_errors_fall(self):
        t = ex._classify_trend([40, 30, 10, 2], "up_bad")
        self.assertEqual(t["semantic"], "improving")
