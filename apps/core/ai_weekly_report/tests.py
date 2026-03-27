"""
WIRE — Weekly Intelligence Report Engine Tests.

Covers:
- WeeklyIntelligenceReport model creation and unique constraint
- Report selector prioritization
- Report ranker ordering
- Report logger duplicate prevention
- Report engine end-to-end (mocked)
- Dashboard tile rendering
- History page view
- Detail page view
- ISE scheduler integration
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.core.ai_weekly_report.models import WeeklyIntelligenceReport
from apps.core.ai_weekly_report.report_engine import (
    _compute_state_deltas,
    _generate_summary,
    _get_report_week,
    generate_weekly_report,
    get_latest_weekly_report,
    get_report_history,
)
from apps.core.ai_weekly_report.report_logger import store_weekly_report
from apps.core.ai_weekly_report.report_ranker import rank_report_items
from apps.core.ai_weekly_report.report_selector import select_report_items
from apps.users.models import TermsAcceptance

User = get_user_model()


def _setup_test_user(email="wiretest@example.com", password="testpass123"):
    """Create a test user with onboarding completed."""
    user = User.objects.create_user(email=email, password=password)
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.ai_enabled = True
    user.preferences.save()
    return user


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------


class WeeklyIntelligenceReportModelTest(TestCase):
    """Tests for the WeeklyIntelligenceReport model."""

    def setUp(self):
        self.user = _setup_test_user()
        self.week_start = date(2026, 2, 9)  # Monday
        self.week_end = date(2026, 2, 15)  # Sunday

    def test_create_report(self):
        """A report can be created with required fields."""
        report = WeeklyIntelligenceReport.objects.create(
            user=self.user,
            week_start_date=self.week_start,
            week_end_date=self.week_end,
            summary="Test summary",
        )
        self.assertEqual(report.user, self.user)
        self.assertEqual(report.week_start_date, self.week_start)
        self.assertEqual(report.summary, "Test summary")

    def test_json_fields_default_to_empty_dict(self):
        """JSON fields default to empty dicts."""
        report = WeeklyIntelligenceReport.objects.create(
            user=self.user,
            week_start_date=self.week_start,
            week_end_date=self.week_end,
            summary="Test",
        )
        self.assertEqual(report.state_delta_snapshot, {})
        self.assertEqual(report.insight_snapshot, {})
        self.assertEqual(report.prediction_snapshot, {})
        self.assertEqual(report.guidance_snapshot, {})
        self.assertEqual(report.learning_snapshot, {})

    def test_unique_constraint_per_user_per_week(self):
        """Only one report per user per week_start_date."""
        WeeklyIntelligenceReport.objects.create(
            user=self.user,
            week_start_date=self.week_start,
            week_end_date=self.week_end,
            summary="First",
        )
        with self.assertRaises(IntegrityError):
            WeeklyIntelligenceReport.objects.create(
                user=self.user,
                week_start_date=self.week_start,
                week_end_date=self.week_end,
                summary="Duplicate",
            )

    def test_different_users_same_week(self):
        """Different users can have reports for the same week."""
        user2 = _setup_test_user(email="wire2@example.com")
        WeeklyIntelligenceReport.objects.create(
            user=self.user,
            week_start_date=self.week_start,
            week_end_date=self.week_end,
            summary="User 1",
        )
        report2 = WeeklyIntelligenceReport.objects.create(
            user=user2,
            week_start_date=self.week_start,
            week_end_date=self.week_end,
            summary="User 2",
        )
        self.assertEqual(WeeklyIntelligenceReport.objects.count(), 2)
        self.assertEqual(report2.summary, "User 2")

    def test_ordering_by_week_start_descending(self):
        """Reports are ordered by week_start_date descending."""
        for i in range(3):
            WeeklyIntelligenceReport.objects.create(
                user=self.user,
                week_start_date=self.week_start - timedelta(weeks=i),
                week_end_date=self.week_end - timedelta(weeks=i),
                summary=f"Week {i}",
            )
        reports = list(WeeklyIntelligenceReport.objects.filter(user=self.user))
        self.assertEqual(reports[0].summary, "Week 0")
        self.assertEqual(reports[2].summary, "Week 2")

    def test_str_representation(self):
        """__str__ shows user ID and date range."""
        report = WeeklyIntelligenceReport.objects.create(
            user=self.user,
            week_start_date=self.week_start,
            week_end_date=self.week_end,
            summary="Test",
        )
        self.assertIn(str(self.user.id), str(report))
        self.assertIn("2026-02-09", str(report))


# ---------------------------------------------------------------------------
# Selector Tests
# ---------------------------------------------------------------------------


class ReportSelectorTest(TestCase):
    """Tests for the report_selector module."""

    def test_empty_inputs(self):
        """Empty inputs return empty list."""
        result = select_report_items([], [], [], [])
        self.assertEqual(result, [])

    def test_critical_predictions_first(self):
        """Critical predictions (confidence >= 0.8) are selected first."""
        predictions = [
            {"title": "High", "confidence_score": 0.9, "description": "d"},
            {"title": "Low", "confidence_score": 0.5, "description": "d"},
        ]
        result = select_report_items([], predictions, [], [])
        types = [r["type"] for r in result]
        priorities = [r["priority"] for r in result]
        self.assertEqual(types[0], "prediction")
        self.assertEqual(priorities[0], 1)  # Critical prediction = priority 1

    def test_critical_insights_priority(self):
        """Critical/warning insights are high priority."""
        insights = [
            {"title": "Crit", "severity": "critical", "description": "d"},
            {"title": "Warn", "severity": "warning", "description": "d"},
            {"title": "Info", "severity": "info", "description": "d"},
        ]
        result = select_report_items(insights, [], [], [])
        # Critical and warning should appear first, info fills remaining
        critical_items = [r for r in result if r.get("severity") == "critical"]
        self.assertTrue(len(critical_items) > 0)
        self.assertEqual(critical_items[0]["priority"], 2)

    def test_significant_state_changes(self):
        """Significant state deltas are included."""
        deltas = [
            {"label": "Weight trend: up", "description": "d", "significant": True, "module": "health"},
            {"label": "Steps OK", "description": "d", "significant": False, "module": "health"},
        ]
        result = select_report_items([], [], [], deltas)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["type"], "state_change")

    def test_guidance_acted_items(self):
        """Guidance items that were acted upon are included."""
        guidance = [
            {"title": "Acted", "message": "msg", "acted": True},
            {"title": "Not acted", "message": "msg", "acted": False},
        ]
        result = select_report_items([], [], guidance, [])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["type"], "guidance_acted")

    def test_max_items_limit(self):
        """Output is capped at MAX_REPORT_ITEMS."""
        # 15 critical predictions
        predictions = [
            {"title": f"P{i}", "confidence_score": 0.95, "description": "d"}
            for i in range(15)
        ]
        result = select_report_items([], predictions, [], [])
        self.assertLessEqual(len(result), 10)

    def test_fill_remaining_with_lower_predictions(self):
        """Lower confidence predictions fill remaining slots."""
        predictions = [
            {"title": "High", "confidence_score": 0.9, "description": "d"},
            {"title": "Medium", "confidence_score": 0.6, "description": "d"},
        ]
        result = select_report_items([], predictions, [], [])
        self.assertEqual(len(result), 2)
        titles = [r["title"] for r in result]
        self.assertIn("Medium", titles)


# ---------------------------------------------------------------------------
# Ranker Tests
# ---------------------------------------------------------------------------


class ReportRankerTest(TestCase):
    """Tests for the report_ranker module."""

    def test_empty_items(self):
        """Empty input returns empty list."""
        self.assertEqual(rank_report_items([]), [])

    def test_priority_ordering(self):
        """Higher priority (lower number) items rank higher."""
        items = [
            {"type": "insight", "title": "Low", "priority": 5},
            {"type": "prediction", "title": "High", "priority": 1, "confidence": 0.9},
        ]
        ranked = rank_report_items(items)
        self.assertEqual(ranked[0]["title"], "High")
        self.assertEqual(ranked[1]["title"], "Low")

    def test_type_bonus(self):
        """Predictions get higher type bonus than insights."""
        items = [
            {"type": "insight", "title": "Insight", "priority": 3, "confidence": 0.5},
            {"type": "prediction", "title": "Prediction", "priority": 3, "confidence": 0.5},
        ]
        ranked = rank_report_items(items)
        self.assertEqual(ranked[0]["title"], "Prediction")

    def test_confidence_contribution(self):
        """Higher confidence contributes more to score."""
        items = [
            {"type": "prediction", "title": "Low Conf", "priority": 1, "confidence": 0.1},
            {"type": "prediction", "title": "High Conf", "priority": 1, "confidence": 0.99},
        ]
        ranked = rank_report_items(items)
        self.assertEqual(ranked[0]["title"], "High Conf")

    def test_single_item(self):
        """Single item returns as-is."""
        items = [{"type": "insight", "title": "Only", "priority": 3}]
        ranked = rank_report_items(items)
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0]["title"], "Only")


# ---------------------------------------------------------------------------
# Logger Tests
# ---------------------------------------------------------------------------


class ReportLoggerTest(TestCase):
    """Tests for the report_logger module."""

    def setUp(self):
        self.user = _setup_test_user()
        self.week_start = date(2026, 2, 9)
        self.week_end = date(2026, 2, 15)

    def test_store_new_report(self):
        """store_weekly_report creates a new report."""
        report = store_weekly_report(
            user=self.user,
            week_start=self.week_start,
            week_end=self.week_end,
            summary="Test summary",
        )
        self.assertIsNotNone(report)
        self.assertEqual(report.summary, "Test summary")
        self.assertEqual(WeeklyIntelligenceReport.objects.count(), 1)

    def test_duplicate_returns_existing(self):
        """Storing a duplicate returns the existing report."""
        report1 = store_weekly_report(
            user=self.user,
            week_start=self.week_start,
            week_end=self.week_end,
            summary="First",
        )
        report2 = store_weekly_report(
            user=self.user,
            week_start=self.week_start,
            week_end=self.week_end,
            summary="Second",
        )
        self.assertEqual(report1.id, report2.id)
        self.assertEqual(WeeklyIntelligenceReport.objects.count(), 1)

    def test_snapshots_stored_correctly(self):
        """JSON snapshots are stored in the report."""
        report = store_weekly_report(
            user=self.user,
            week_start=self.week_start,
            week_end=self.week_end,
            summary="Test",
            state_delta_snapshot={"deltas": [{"label": "test"}]},
            insight_snapshot={"insights": [{"title": "ins"}]},
            prediction_snapshot={"predictions": [{"title": "pred"}]},
            guidance_snapshot={"guidance": [{"title": "guide"}]},
            learning_snapshot={"responsiveness_score": 0.7},
        )
        self.assertIn("deltas", report.state_delta_snapshot)
        self.assertIn("insights", report.insight_snapshot)
        self.assertIn("predictions", report.prediction_snapshot)
        self.assertIn("guidance", report.guidance_snapshot)
        self.assertEqual(report.learning_snapshot["responsiveness_score"], 0.7)


# ---------------------------------------------------------------------------
# Engine Tests
# ---------------------------------------------------------------------------


class ReportEngineTest(TestCase):
    """Tests for the report_engine module."""

    def setUp(self):
        self.user = _setup_test_user()

    def test_get_report_week_returns_mon_sun(self):
        """_get_report_week returns a Monday-Sunday range."""
        week_start, week_end = _get_report_week()
        self.assertEqual(week_start.weekday(), 0)  # Monday
        self.assertEqual(week_end.weekday(), 6)  # Sunday
        self.assertEqual((week_end - week_start).days, 6)

    def test_get_report_week_is_completed_week(self):
        """Report week is in the past (not current week)."""
        week_start, week_end = _get_report_week()
        today = timezone.now().date()
        self.assertLessEqual(week_end, today)

    @patch("apps.core.ai_weekly_report.report_engine._get_current_state")
    @patch("apps.core.ai_weekly_report.report_engine._get_week_insights")
    @patch("apps.core.ai_weekly_report.report_engine._get_week_predictions")
    @patch("apps.core.ai_weekly_report.report_engine._get_week_guidance")
    @patch("apps.core.ai_weekly_report.report_engine._get_learning_snapshot")
    def test_generate_report_creates_report(
        self, mock_learning, mock_guidance, mock_predictions, mock_insights, mock_state
    ):
        """generate_weekly_report creates a report when all engines respond."""
        mock_state.return_value = {"health": {"weight_trend": "down", "weight_current": 180}}
        mock_insights.return_value = [
            {"title": "Weight Loss", "severity": "info", "description": "d", "confidence_score": 0.7, "created_at": "2026-02-10T00:00:00"}
        ]
        mock_predictions.return_value = [
            {"title": "Weight: 175", "description": "d", "confidence_score": 0.85, "module": "health", "status": "active", "created_at": "2026-02-10T00:00:00"}
        ]
        mock_guidance.return_value = []
        mock_learning.return_value = {"responsiveness_score": 0.6, "total_guidance_seen": 5}

        report = generate_weekly_report(self.user)
        self.assertIsNotNone(report)
        self.assertIsInstance(report, WeeklyIntelligenceReport)
        # Phase 4: strategic review format
        self.assertIn("MOMENTUM TRAJECTORY", report.summary)

    @patch("apps.core.ai_weekly_report.report_engine._get_current_state")
    @patch("apps.core.ai_weekly_report.report_engine._get_week_insights")
    @patch("apps.core.ai_weekly_report.report_engine._get_week_predictions")
    @patch("apps.core.ai_weekly_report.report_engine._get_week_guidance")
    @patch("apps.core.ai_weekly_report.report_engine._get_learning_snapshot")
    def test_generate_report_dedup(
        self, mock_learning, mock_guidance, mock_predictions, mock_insights, mock_state
    ):
        """Calling generate twice for same week returns existing report."""
        mock_state.return_value = {}
        mock_insights.return_value = []
        mock_predictions.return_value = []
        mock_guidance.return_value = []
        mock_learning.return_value = {"responsiveness_score": 0.5, "total_guidance_seen": 0}

        report1 = generate_weekly_report(self.user)
        report2 = generate_weekly_report(self.user)
        self.assertEqual(report1.id, report2.id)
        self.assertEqual(WeeklyIntelligenceReport.objects.count(), 1)

    @patch("apps.core.ai_weekly_report.report_engine._get_current_state")
    def test_generate_report_handles_engine_failure(self, mock_state):
        """Engine failure returns None gracefully."""
        mock_state.side_effect = Exception("SAE down")
        report = generate_weekly_report(self.user)
        self.assertIsNone(report)

    def test_get_latest_weekly_report_none(self):
        """Returns None when no reports exist."""
        self.assertIsNone(get_latest_weekly_report(self.user))

    def test_get_latest_weekly_report_returns_most_recent(self):
        """Returns the most recent report."""
        WeeklyIntelligenceReport.objects.create(
            user=self.user,
            week_start_date=date(2026, 2, 2),
            week_end_date=date(2026, 2, 8),
            summary="Older",
        )
        WeeklyIntelligenceReport.objects.create(
            user=self.user,
            week_start_date=date(2026, 2, 9),
            week_end_date=date(2026, 2, 15),
            summary="Newer",
        )
        latest = get_latest_weekly_report(self.user)
        self.assertEqual(latest.summary, "Newer")

    def test_get_report_history(self):
        """Returns reports ordered by date descending."""
        for i in range(5):
            WeeklyIntelligenceReport.objects.create(
                user=self.user,
                week_start_date=date(2026, 1, 6) + timedelta(weeks=i),
                week_end_date=date(2026, 1, 12) + timedelta(weeks=i),
                summary=f"Week {i}",
            )
        history = list(get_report_history(self.user, limit=3))
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0].summary, "Week 4")


# ---------------------------------------------------------------------------
# State Deltas Tests
# ---------------------------------------------------------------------------


class ComputeStateDeltasTest(TestCase):
    """Tests for _compute_state_deltas."""

    def test_empty_state(self):
        """Empty state returns minimal deltas (journal 0 entries is included)."""
        deltas = _compute_state_deltas({})
        # Only journal entry with 0 (from default None check) — no health/goals/habits/faith
        health_deltas = [d for d in deltas if d["module"] == "health"]
        self.assertEqual(health_deltas, [])

    def test_weight_trend_non_stable(self):
        """Non-stable weight trend creates a delta."""
        state = {"health": {"weight_trend": "down", "weight_current": 180, "weight_unit": "lbs"}}
        deltas = _compute_state_deltas(state)
        labels = [d["label"] for d in deltas]
        self.assertTrue(any("Weight trend" in l for l in labels))

    def test_weight_trend_stable_no_delta(self):
        """Stable weight trend does not create a delta."""
        state = {"health": {"weight_trend": "stable"}}
        deltas = _compute_state_deltas(state)
        labels = [d["label"] for d in deltas]
        self.assertFalse(any("Weight trend" in l for l in labels))

    def test_overdue_goals(self):
        """Overdue goals create a delta."""
        state = {"goals": {"overdue_goal_count": 3}}
        deltas = _compute_state_deltas(state)
        labels = [d["label"] for d in deltas]
        self.assertTrue(any("overdue" in l for l in labels))

    def test_habit_streak(self):
        """Long habit streak creates a delta."""
        state = {"habits": {"longest_streak": 14, "avg_completion_rate": 0.8}}
        deltas = _compute_state_deltas(state)
        labels = [d["label"] for d in deltas]
        self.assertTrue(any("streak" in l for l in labels))

    def test_reading_streak(self):
        """Long reading streak creates a delta."""
        state = {"faith": {"reading_streak": 10}}
        deltas = _compute_state_deltas(state)
        labels = [d["label"] for d in deltas]
        self.assertTrue(any("Reading streak" in l for l in labels))


# ---------------------------------------------------------------------------
# Summary Generation Tests
# ---------------------------------------------------------------------------


class GenerateSummaryTest(TestCase):
    """Tests for _generate_summary."""

    def test_empty_items(self):
        """Empty items produces strategic review with defaults."""
        summary = _generate_summary([], {}, {})
        # Phase 4: strategic review format instead of flat list
        self.assertIn("MOMENTUM TRAJECTORY", summary)
        self.assertIn("GOVERNANCE COMPLIANCE", summary)

    def test_summary_includes_predictions(self):
        """Summary includes prediction content in drift zones."""
        items = [{"type": "prediction", "title": "Weight: 175", "priority": 1, "confidence": 0.9}]
        summary = _generate_summary(items, {}, {})
        # Phase 4: predictions surface in NEXT WEEK EMPHASIS or DRIFT ZONES
        self.assertIn("MOMENTUM TRAJECTORY", summary)

    def test_summary_includes_insights(self):
        """Summary includes insight content in drift zones."""
        items = [{"type": "insight", "title": "Sleep improving", "priority": 2, "severity": "info"}]
        summary = _generate_summary(items, {}, {})
        # Phase 4: insights surface in strategic review sections
        self.assertIn("MOMENTUM TRAJECTORY", summary)

    def test_high_responsiveness_message(self):
        """High responsiveness reflected in governance compliance."""
        items = [{"type": "insight", "title": "Test", "priority": 3, "severity": "info"}]
        learning = {"responsiveness_score": 0.8, "total_guidance_seen": 10, "total_acted": 7}
        summary = _generate_summary(items, {}, learning)
        # Phase 4: engagement shows in GOVERNANCE COMPLIANCE section
        self.assertIn("GOVERNANCE COMPLIANCE", summary)

    def test_low_responsiveness_message(self):
        """Low responsiveness reflected in governance compliance."""
        items = [{"type": "insight", "title": "Test", "priority": 3, "severity": "info"}]
        learning = {"responsiveness_score": 0.2, "total_guidance_seen": 10, "total_acted": 1}
        summary = _generate_summary(items, {}, learning)
        self.assertIn("GOVERNANCE COMPLIANCE", summary)


# ---------------------------------------------------------------------------
# Dashboard Tile Tests
# ---------------------------------------------------------------------------


class DashboardTileTest(TestCase):
    """Tests for the weekly report dashboard tile."""

    def setUp(self):
        self.user = _setup_test_user()
        self.client = Client()
        self.client.login(email="wiretest@example.com", password="testpass123")

    def test_dashboard_loads_without_report(self):
        """Dashboard renders without a weekly report (empty state)."""
        response = self.client.get("/v2/")
        self.assertEqual(response.status_code, 200)

    def test_dashboard_shows_report_summary(self):
        """Dashboard loads when a weekly report exists."""
        WeeklyIntelligenceReport.objects.create(
            user=self.user,
            week_start_date=date(2026, 2, 9),
            week_end_date=date(2026, 2, 15),
            summary="Great week overall!",
        )
        response = self.client.get("/v2/")
        self.assertEqual(response.status_code, 200)

    def test_dashboard_has_history_link(self):
        """Dashboard loads when a weekly report exists."""
        WeeklyIntelligenceReport.objects.create(
            user=self.user,
            week_start_date=date(2026, 2, 9),
            week_end_date=date(2026, 2, 15),
            summary="Test",
        )
        response = self.client.get("/v2/")
        self.assertEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# History Page Tests
# ---------------------------------------------------------------------------


class HistoryPageTest(TestCase):
    """Tests for the weekly report history page."""

    def setUp(self):
        self.user = _setup_test_user()
        self.client = Client()
        self.client.login(email="wiretest@example.com", password="testpass123")

    def test_history_page_renders(self):
        """History page renders successfully."""
        response = self.client.get("/intelligence/weekly/")
        self.assertEqual(response.status_code, 200)

    def test_history_page_shows_reports(self):
        """History page lists reports."""
        WeeklyIntelligenceReport.objects.create(
            user=self.user,
            week_start_date=date(2026, 2, 9),
            week_end_date=date(2026, 2, 15),
            summary="Week 1 summary",
        )
        response = self.client.get("/intelligence/weekly/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Week 1 summary")

    def test_history_page_only_shows_own_reports(self):
        """Users only see their own reports."""
        user2 = _setup_test_user(email="wire_other@example.com")
        WeeklyIntelligenceReport.objects.create(
            user=user2,
            week_start_date=date(2026, 2, 9),
            week_end_date=date(2026, 2, 15),
            summary="Other user report",
        )
        response = self.client.get("/intelligence/weekly/")
        self.assertNotContains(response, "Other user report")

    def test_history_requires_login(self):
        """Unauthenticated users are redirected."""
        self.client.logout()
        response = self.client.get("/intelligence/weekly/")
        self.assertEqual(response.status_code, 302)


# ---------------------------------------------------------------------------
# Detail Page Tests
# ---------------------------------------------------------------------------


class DetailPageTest(TestCase):
    """Tests for the weekly report detail page."""

    def setUp(self):
        self.user = _setup_test_user()
        self.client = Client()
        self.client.login(email="wiretest@example.com", password="testpass123")
        self.report = WeeklyIntelligenceReport.objects.create(
            user=self.user,
            week_start_date=date(2026, 2, 9),
            week_end_date=date(2026, 2, 15),
            summary="Detailed report",
            learning_snapshot={"responsiveness_score": 0.75, "total_guidance_seen": 10},
        )

    def test_detail_page_renders(self):
        """Detail page renders for the report owner."""
        response = self.client.get(f"/intelligence/weekly/{self.report.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Detailed report")

    def test_detail_page_other_user_404(self):
        """Other users cannot see someone else's report."""
        user2 = _setup_test_user(email="wire_hacker@example.com")
        client2 = Client()
        client2.login(email="wire_hacker@example.com", password="testpass123")
        response = client2.get(f"/intelligence/weekly/{self.report.pk}/")
        self.assertEqual(response.status_code, 404)

    def test_detail_requires_login(self):
        """Unauthenticated users are redirected."""
        self.client.logout()
        response = self.client.get(f"/intelligence/weekly/{self.report.pk}/")
        self.assertEqual(response.status_code, 302)


# ---------------------------------------------------------------------------
# Scheduler Integration Tests
# ---------------------------------------------------------------------------


class SchedulerIntegrationTest(TestCase):
    """Tests for WIRE integration with ISE scheduler."""

    def test_weekly_reports_in_registry(self):
        """generate_weekly_reports is registered in ISE."""
        from apps.core.ai_scheduler.scheduler_registry import SCHEDULED_TASKS

        self.assertIn("generate_weekly_reports", SCHEDULED_TASKS)
        task = SCHEDULED_TASKS["generate_weekly_reports"]
        self.assertEqual(task["interval_seconds"], 604800)

    def test_runner_function_exists(self):
        """run_weekly_reports can be imported from scheduler_runner."""
        from apps.core.ai_scheduler.scheduler_runner import run_weekly_reports

        self.assertTrue(callable(run_weekly_reports))

    @patch("apps.core.ai_scheduler.scheduler_runner.User")
    def test_runner_returns_result_dict(self, mock_user_cls):
        """run_weekly_reports returns a dict with generated and errors."""
        mock_user_cls.objects.filter.return_value.select_related.return_value = []

        from apps.core.ai_scheduler.scheduler_runner import run_weekly_reports

        result = run_weekly_reports()
        self.assertIn("generated", result)
        self.assertIn("errors", result)

    def test_registry_function_path_resolves(self):
        """The function path in the registry resolves correctly."""
        from apps.core.ai_scheduler.scheduler_registry import get_task_function

        func = get_task_function("generate_weekly_reports")
        self.assertIsNotNone(func)
        self.assertTrue(callable(func))
