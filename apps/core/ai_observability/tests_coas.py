"""
COAS — Tests for CoS Operational Awareness System.

Tests health scoring, state-change alerting, diagnostic prompt generation,
snapshot persistence, and defensive error handling.

Project: Whole Life Journey
Path: apps/core/ai_observability/tests_coas.py
"""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.core.ai_observability.health_scoring import (
    _FRESHNESS_TASKS,
    _SUBSYSTEM_WEIGHTS,
    compute_all_scores,
    compute_engine_health,
    compute_intelligence_freshness,
    compute_scheduler_health,
    compute_system_health,
    save_health_snapshot,
)
from apps.core.ai_observability.models import (
    COASHealthSnapshot,
    EngineRun,
    OperationalAlert,
    OpsAnomaly,
    SchedulerHeartbeat,
)
from apps.core.ai_observability.operational_alerts import (
    THRESHOLD_ALERT,
    THRESHOLD_CRITICAL,
    THRESHOLD_HEALTHY,
    _classify_severity,
    check_and_alert,
)
from apps.core.ai_scheduler.scheduler_models import ScheduledIntelligenceTask


# =============================================================================
# SCHEDULER HEALTH SCORING
# =============================================================================


class SchedulerHealthTests(TestCase):
    """Tests for compute_scheduler_health()."""

    def setUp(self):
        """Create baseline healthy heartbeats."""
        now = timezone.now()
        SchedulerHeartbeat.objects.update_or_create(
            scheduler_name="ISE",
            defaults={
                "last_tick_at": now,
                "expected_interval_seconds": 300,
            },
        )
        SchedulerHeartbeat.objects.update_or_create(
            scheduler_name="SAME",
            defaults={
                "last_tick_at": now,
                "expected_interval_seconds": 60,
            },
        )

    @patch("apps.core.scheduler_health.get_scheduler_status")
    def test_all_healthy_baseline(self, mock_status):
        """All heartbeats ALIVE, APScheduler running, no failed tasks = 100."""
        mock_status.return_value = {"running": True}
        result = compute_scheduler_health()
        self.assertEqual(result["score"], 100)

    @patch("apps.core.scheduler_health.get_scheduler_status")
    def test_ise_offline(self, mock_status):
        """ISE OFFLINE should drop score by 40."""
        mock_status.return_value = {"running": True}
        # Make ISE heartbeat stale (offline = drift > 3x interval)
        SchedulerHeartbeat.objects.filter(scheduler_name="ISE").update(
            last_tick_at=timezone.now() - timedelta(seconds=1500),  # 5x 300s
        )
        result = compute_scheduler_health()
        self.assertEqual(result["details"]["ise"]["status"], "OFFLINE")
        self.assertEqual(result["details"]["ise"]["penalty"], 40)
        self.assertLessEqual(result["score"], 60)

    @patch("apps.core.scheduler_health.get_scheduler_status")
    def test_ise_delayed(self, mock_status):
        """ISE DELAYED should drop score by 15."""
        mock_status.return_value = {"running": True}
        # Drift between 1.5x and 3x interval
        SchedulerHeartbeat.objects.filter(scheduler_name="ISE").update(
            last_tick_at=timezone.now() - timedelta(seconds=600),  # 2x 300s
        )
        result = compute_scheduler_health()
        self.assertEqual(result["details"]["ise"]["status"], "DELAYED")
        self.assertEqual(result["details"]["ise"]["penalty"], 15)

    @patch("apps.core.scheduler_health.get_scheduler_status")
    def test_apscheduler_not_running(self, mock_status):
        """APScheduler not running should drop score by 20."""
        mock_status.return_value = {"running": False}
        result = compute_scheduler_health()
        self.assertEqual(result["details"]["apscheduler"]["penalty"], 20)
        self.assertEqual(result["score"], 80)

    @patch("apps.core.scheduler_health.get_scheduler_status")
    def test_failed_tasks(self, mock_status):
        """Failed ISE tasks should drop score by 3 each, capped at 15."""
        mock_status.return_value = {"running": True}
        for i in range(6):
            ScheduledIntelligenceTask.objects.create(
                task_name=f"failed_task_{i}",
                is_active=True,
                last_status="failed",
                run_interval_seconds=300,
            )
        result = compute_scheduler_health()
        # 6 * 3 = 18 but capped at 15
        self.assertEqual(result["details"]["failed_tasks"]["penalty"], 15)
        self.assertEqual(result["score"], 85)

    @patch("apps.core.scheduler_health.get_scheduler_status")
    def test_missing_heartbeat_data(self, mock_status):
        """Missing heartbeats should not crash, treated as OFFLINE."""
        mock_status.return_value = {"running": True}
        SchedulerHeartbeat.objects.all().delete()
        result = compute_scheduler_health()
        self.assertIsNotNone(result["score"])
        # Both ISE and SAME OFFLINE = -40 + -30 = 30
        self.assertEqual(result["score"], 30)


# =============================================================================
# ENGINE HEALTH SCORING
# =============================================================================


class EngineHealthTests(TestCase):
    """Tests for compute_engine_health()."""

    @patch("apps.core.ai_observability.heartbeat.get_latest_heartbeats")
    def test_all_ok_baseline(self, mock_hb):
        """All engines OK, no errors, no anomalies = 100."""
        mock_hb.return_value = {
            "UAL": {"status": "OK"},
            "SAE": {"status": "OK"},
            "PIE": {"status": "OK"},
        }
        result = compute_engine_health()
        self.assertEqual(result["score"], 100)

    @patch("apps.core.ai_observability.heartbeat.get_latest_heartbeats")
    def test_error_rate_20_percent(self, mock_hb):
        """20% error rate should drop score by 20."""
        mock_hb.return_value = {"UAL": {"status": "OK"}}
        now = timezone.now()
        for i in range(80):
            EngineRun.objects.create(
                trace_id=f"t{i}",
                engine_name="UAL",
                phase=1,
                started_at=now - timedelta(minutes=5),
                status="success",
                duration_ms=10,
            )
        for i in range(20):
            EngineRun.objects.create(
                trace_id=f"e{i}",
                engine_name="UAL",
                phase=1,
                started_at=now - timedelta(minutes=5),
                status="error",
                duration_ms=10,
            )
        result = compute_engine_health()
        self.assertEqual(result["details"]["error_rate_30m"]["penalty"], 20)

    @patch("apps.core.ai_observability.heartbeat.get_latest_heartbeats")
    def test_p1_anomalies_capped(self, mock_hb):
        """P1 anomalies should drop 10 each, capped at 20."""
        mock_hb.return_value = {"UAL": {"status": "OK"}}
        for i in range(3):
            OpsAnomaly.objects.create(
                severity="P1",
                anomaly_type="MISSED_RUN",
                summary=f"Test anomaly {i}",
                is_active=True,
            )
        result = compute_engine_health()
        # 3 * 10 = 30 but capped at 20
        self.assertEqual(result["details"]["p1_anomalies"]["penalty"], 20)

    @patch("apps.core.ai_observability.heartbeat.get_latest_heartbeats")
    def test_mixed_heartbeat_statuses(self, mock_hb):
        """Mix of OK and non-OK heartbeats."""
        mock_hb.return_value = {
            "UAL": {"status": "OK"},
            "SAE": {"status": "MISSED"},
            "PIE": {"status": "OK"},
            "DNE": {"status": "ERROR"},
        }
        result = compute_engine_health()
        # 2/4 OK = 50%, penalty = (1 - 0.5) * 50 = 25
        self.assertEqual(result["details"]["heartbeats"]["penalty"], 25)


# =============================================================================
# INTELLIGENCE FRESHNESS SCORING
# =============================================================================


class IntelligenceFreshnessTests(TestCase):
    """Tests for compute_intelligence_freshness()."""

    def setUp(self):
        """Create all expected freshness tasks as fresh."""
        now = timezone.now()
        for task_name, config in _FRESHNESS_TASKS.items():
            ScheduledIntelligenceTask.objects.create(
                task_name=task_name,
                is_active=True,
                last_status="success",
                last_run_at=now,
                run_interval_seconds=config["expected_seconds"],
            )

    def test_all_fresh_baseline(self):
        """All tasks just ran = 100."""
        result = compute_intelligence_freshness()
        self.assertEqual(result["score"], 100)

    def test_stale_briefings(self):
        """Briefings 2x overdue get partial penalty."""
        ScheduledIntelligenceTask.objects.filter(
            task_name="generate_daily_briefings"
        ).update(
            last_run_at=timezone.now() - timedelta(hours=48),  # 2x 24h
        )
        result = compute_intelligence_freshness()
        # ratio = 2.0, fraction = (2.0 - 1.5) / 1.5 = 0.333
        # penalty = int(25 * 0.333) = 8
        details = result["details"]["generate_daily_briefings"]
        self.assertEqual(details["status"], "STALE")
        self.assertGreater(details["penalty"], 0)
        self.assertLess(details["penalty"], 25)  # Partial, not full
        self.assertLess(result["score"], 100)

    def test_critical_staleness(self):
        """4x overdue = full weight penalty."""
        ScheduledIntelligenceTask.objects.filter(
            task_name="run_pie_synthetic"
        ).update(
            last_run_at=timezone.now() - timedelta(minutes=20),  # 4x 5min
        )
        result = compute_intelligence_freshness()
        details = result["details"]["run_pie_synthetic"]
        self.assertEqual(details["status"], "CRITICAL")
        self.assertEqual(details["penalty"], 20)  # Full weight

    def test_never_run_task(self):
        """Task that never ran gets full weight penalty."""
        ScheduledIntelligenceTask.objects.filter(
            task_name="refresh_guidance"
        ).update(last_run_at=None)
        result = compute_intelligence_freshness()
        details = result["details"]["refresh_guidance"]
        self.assertEqual(details["status"], "NEVER_RUN")
        self.assertEqual(details["penalty"], 20)

    def test_missing_task(self):
        """Missing task gets full weight penalty but no crash."""
        ScheduledIntelligenceTask.objects.filter(
            task_name="deliver_intelligence_notifications"
        ).delete()
        result = compute_intelligence_freshness()
        self.assertIsNotNone(result["score"])
        details = result["details"]["deliver_intelligence_notifications"]
        self.assertEqual(details["status"], "NOT_FOUND")
        self.assertEqual(details["penalty"], 20)

    def test_disabled_task_zero_penalty(self):
        """Disabled task (is_active=False) gets zero penalty."""
        ScheduledIntelligenceTask.objects.filter(
            task_name="run_prie_synthetic"
        ).update(is_active=False)
        result = compute_intelligence_freshness()
        details = result["details"]["run_prie_synthetic"]
        self.assertEqual(details["status"], "DISABLED")
        self.assertEqual(details["penalty"], 0)


# =============================================================================
# OVERALL SYSTEM HEALTH
# =============================================================================


class SystemHealthTests(TestCase):
    """Tests for compute_system_health() and compute_all_scores()."""

    def test_weighted_average(self):
        """Verify weighted average formula."""
        result = compute_system_health(
            scheduler_score=80,
            engine_score=90,
            freshness_score=100,
        )
        # 80*0.3 + 90*0.4 + 100*0.3 = 24 + 36 + 30 = 90
        self.assertEqual(result["score"], 90)

    def test_all_perfect(self):
        """100 across the board = 100 overall."""
        result = compute_system_health(100, 100, 100)
        self.assertEqual(result["score"], 100)

    def test_none_scorer_excluded(self):
        """Failed scorer (None) excluded, weights renormalized."""
        result = compute_system_health(
            scheduler_score=None,  # Failed
            engine_score=80,
            freshness_score=60,
        )
        # Only engine (0.4) and freshness (0.3) = 0.7 total
        # Renormalized: engine = 0.4/0.7, freshness = 0.3/0.7
        # = 80 * 0.571 + 60 * 0.429 = 45.71 + 25.71 = 71
        self.assertIsNotNone(result["score"])
        expected = int(80 * (0.4 / 0.7) + 60 * (0.3 / 0.7))
        self.assertEqual(result["score"], expected)

    def test_all_none(self):
        """All scorers failed = None overall."""
        result = compute_system_health(None, None, None)
        self.assertIsNone(result["score"])


class HealthSnapshotTests(TestCase):
    """Tests for save_health_snapshot()."""

    def test_save_creates_snapshot(self):
        """First call creates a snapshot."""
        scores = {
            "scheduler": {"score": 95, "details": {}},
            "engine": {"score": 88, "details": {}},
            "freshness": {"score": 100, "details": {}},
            "overall": {"score": 93, "components": {}},
        }
        snapshot = save_health_snapshot(scores)
        self.assertEqual(snapshot.scheduler_score, 95)
        self.assertEqual(snapshot.engine_score, 88)
        self.assertEqual(snapshot.overall_score, 93)
        self.assertEqual(COASHealthSnapshot.objects.count(), 1)

    def test_save_updates_existing(self):
        """Second call updates existing snapshot (single-row)."""
        scores1 = {
            "scheduler": {"score": 95, "details": {}},
            "engine": {"score": 88, "details": {}},
            "freshness": {"score": 100, "details": {}},
            "overall": {"score": 93, "components": {}},
        }
        save_health_snapshot(scores1)

        scores2 = {
            "scheduler": {"score": 50, "details": {}},
            "engine": {"score": 40, "details": {}},
            "freshness": {"score": 60, "details": {}},
            "overall": {"score": 48, "components": {}},
        }
        snapshot = save_health_snapshot(scores2)
        self.assertEqual(snapshot.scheduler_score, 50)
        self.assertEqual(COASHealthSnapshot.objects.count(), 1)


# =============================================================================
# OPERATIONAL ALERTS — STATE-CHANGE LOGIC
# =============================================================================


class ClassifySeverityTests(TestCase):
    """Tests for _classify_severity()."""

    def test_healthy(self):
        self.assertIsNone(_classify_severity(100))
        self.assertIsNone(_classify_severity(80))

    def test_warning(self):
        self.assertEqual(_classify_severity(79), "warning")
        self.assertEqual(_classify_severity(60), "warning")

    def test_alert(self):
        self.assertEqual(_classify_severity(59), "alert")
        self.assertEqual(_classify_severity(40), "alert")

    def test_critical(self):
        self.assertEqual(_classify_severity(39), "critical")
        self.assertEqual(_classify_severity(0), "critical")


class StateChangeAlertTests(TestCase):
    """Tests for check_and_alert() state-change logic."""

    def _make_scores(self, scheduler=100, engine=100, freshness=100, overall=None):
        """Helper to build a scores dict."""
        if overall is None:
            overall = int(scheduler * 0.3 + engine * 0.4 + freshness * 0.3)
        return {
            "scheduler": {"score": scheduler, "details": {}},
            "engine": {"score": engine, "details": {}},
            "freshness": {"score": freshness, "details": {}},
            "overall": {"score": overall, "components": {}},
        }

    def test_healthy_no_alerts(self):
        """All scores >= 80 should create no alerts."""
        scores = self._make_scores(100, 100, 100)
        alerts = check_and_alert(scores)
        self.assertEqual(len(alerts), 0)
        self.assertEqual(OperationalAlert.objects.count(), 0)

    def test_first_degradation_creates_alert(self):
        """First time score drops below threshold creates alert."""
        scores = self._make_scores(scheduler=50)
        alerts = check_and_alert(scores)
        self.assertTrue(len(alerts) > 0)
        sched_alert = OperationalAlert.objects.filter(subsystem="scheduler").first()
        self.assertIsNotNone(sched_alert)
        self.assertEqual(sched_alert.severity, "alert")
        self.assertEqual(sched_alert.status, "open")

    def test_same_severity_no_duplicate(self):
        """Same severity persisting should NOT create a duplicate alert."""
        scores = self._make_scores(scheduler=50)
        alerts1 = check_and_alert(scores)
        self.assertTrue(len(alerts1) > 0)

        # Run again with same scores
        alerts2 = check_and_alert(scores)
        # No new alerts for scheduler (same severity persists)
        sched_alerts = [a for a in alerts2 if a.subsystem == "scheduler"]
        self.assertEqual(len(sched_alerts), 0)
        # Only 1 scheduler alert total
        self.assertEqual(
            OperationalAlert.objects.filter(
                subsystem="scheduler", status="open"
            ).count(),
            1,
        )

    def test_severity_worsens(self):
        """Severity worsening should create new alert and close old."""
        # First: alert level
        scores1 = self._make_scores(scheduler=50)
        check_and_alert(scores1)
        old_alert = OperationalAlert.objects.filter(
            subsystem="scheduler", status="open"
        ).first()
        self.assertEqual(old_alert.severity, "alert")

        # Worsen to critical
        scores2 = self._make_scores(scheduler=30)
        alerts = check_and_alert(scores2)
        sched_new = [a for a in alerts if a.subsystem == "scheduler"]
        self.assertEqual(len(sched_new), 1)
        self.assertEqual(sched_new[0].severity, "critical")

        # Old alert should be resolved
        old_alert.refresh_from_db()
        self.assertEqual(old_alert.status, "resolved")

    def test_recovery_resolves_alert(self):
        """Score recovering to healthy should resolve open alert."""
        # Create alert
        scores1 = self._make_scores(scheduler=50)
        check_and_alert(scores1)
        self.assertEqual(
            OperationalAlert.objects.filter(
                subsystem="scheduler", status="open"
            ).count(),
            1,
        )

        # Recover
        scores2 = self._make_scores(scheduler=95)
        check_and_alert(scores2)

        # Alert should be resolved
        self.assertEqual(
            OperationalAlert.objects.filter(
                subsystem="scheduler", status="open"
            ).count(),
            0,
        )
        resolved = OperationalAlert.objects.filter(
            subsystem="scheduler", status="resolved"
        ).first()
        self.assertIsNotNone(resolved)
        self.assertIsNotNone(resolved.resolved_at)

    def test_warning_no_chat_injection(self):
        """Warning level (60-79) should create record but NOT inject chat."""
        scores = self._make_scores(scheduler=70)
        alerts = check_and_alert(scores)
        sched_alerts = [a for a in alerts if a.subsystem == "scheduler"]
        self.assertEqual(len(sched_alerts), 1)
        self.assertEqual(sched_alerts[0].severity, "warning")
        # No last_notified_at means no chat injection
        self.assertIsNone(sched_alerts[0].last_notified_at)

    def test_critical_has_diagnostic_prompt(self):
        """Critical alerts should have diagnostic_prompt_text populated."""
        scores = self._make_scores(scheduler=30)
        alerts = check_and_alert(scores)
        sched_alerts = [a for a in alerts if a.subsystem == "scheduler"]
        self.assertTrue(len(sched_alerts) > 0)
        self.assertTrue(len(sched_alerts[0].diagnostic_prompt_text) > 0)
        self.assertIn("COAS Critical Alert", sched_alerts[0].diagnostic_prompt_text)

    def test_alert_level_no_diagnostic_prompt(self):
        """Alert level (40-59) should NOT have diagnostic prompt."""
        scores = self._make_scores(scheduler=50)
        alerts = check_and_alert(scores)
        sched_alerts = [a for a in alerts if a.subsystem == "scheduler"]
        self.assertTrue(len(sched_alerts) > 0)
        self.assertEqual(sched_alerts[0].diagnostic_prompt_text, "")

    def test_warning_level_no_diagnostic_prompt(self):
        """Warning level should NOT have diagnostic prompt."""
        scores = self._make_scores(scheduler=70)
        alerts = check_and_alert(scores)
        sched_alerts = [a for a in alerts if a.subsystem == "scheduler"]
        self.assertTrue(len(sched_alerts) > 0)
        self.assertEqual(sched_alerts[0].diagnostic_prompt_text, "")

    def test_null_score_skipped(self):
        """Subsystem with None score (scorer failed) should be skipped."""
        scores = {
            "scheduler": {"score": None, "details": {"error": "test"}},
            "engine": {"score": 100, "details": {}},
            "freshness": {"score": 100, "details": {}},
            "overall": {"score": 100, "components": {}},
        }
        alerts = check_and_alert(scores)
        sched_alerts = [a for a in alerts if a.subsystem == "scheduler"]
        self.assertEqual(len(sched_alerts), 0)


# =============================================================================
# DEFENSIVE / EDGE CASE TESTS
# =============================================================================


class DefensiveTests(TestCase):
    """Tests for defensive behavior when components fail."""

    @patch("apps.core.ai_observability.health_scoring._compute_scheduler_health_inner")
    def test_one_scorer_fails_others_work(self, mock_sched):
        """One scorer exception should not crash compute_all_scores()."""
        mock_sched.side_effect = Exception("DB connection lost")

        # Create freshness tasks so freshness scorer works
        now = timezone.now()
        for task_name, config in _FRESHNESS_TASKS.items():
            ScheduledIntelligenceTask.objects.create(
                task_name=task_name,
                is_active=True,
                last_status="success",
                last_run_at=now,
                run_interval_seconds=config["expected_seconds"],
            )

        scores = compute_all_scores()

        # Scheduler failed
        self.assertIsNone(scores["scheduler"]["score"])
        self.assertIn("error", scores["scheduler"]["details"])

        # Engine and freshness should still have scores
        self.assertIsNotNone(scores["engine"]["score"])
        self.assertIsNotNone(scores["freshness"]["score"])

        # Overall should still compute (renormalized without scheduler)
        self.assertIsNotNone(scores["overall"]["score"])

    def test_no_staff_users_no_crash(self):
        """Alert injection with no staff users should not crash."""
        from apps.core.ai_observability.operational_alerts import _inject_admin_alert

        alert = OperationalAlert.objects.create(
            subsystem="scheduler",
            severity="alert",
            health_score=50,
            message="Test alert",
        )
        # Should log warning but not raise
        _inject_admin_alert("Test message", alert)

    def test_compute_all_scores_with_empty_db(self):
        """compute_all_scores with completely empty DB should not crash."""
        scores = compute_all_scores()
        # Should return results, not crash
        self.assertIn("scheduler", scores)
        self.assertIn("engine", scores)
        self.assertIn("freshness", scores)
        self.assertIn("overall", scores)
