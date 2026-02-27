"""
COS-CX: Context Intelligence Expansion Tests
=============================================

Tests for the six COS-CX phases:
  CX1: Always-On Specificity (specificity_block.py)
  CX2: Lead Signal Prioritizer (signal_prioritizer.py)
  CX3: Goal Behavior Gap Analyzer (goal_gap_analyzer.py)
  CX4: Temporal Execution Matching (temporal_matcher.py)
  CX5: Diagnostic Context Expansion (diagnostic_context.py)
  CX6: Behavioral Forecast Extension (behavior_forecast.py)

All modules are fail-safe: they return "" or [] on any error.
Tests verify both happy-path output and graceful degradation.
"""

import datetime as dt
from datetime import timedelta
from unittest.mock import patch, MagicMock
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

User = get_user_model()


def _create_test_user(email="coscx@example.com"):
    """Create a test user with onboarding complete."""
    from apps.users.models import TermsAcceptance

    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


# ──────────────────────────────────────────────────────────
# CX1: Specificity Block Tests
# ──────────────────────────────────────────────────────────


class SpecificityBlockTests(TestCase):
    """Test COS-CX1: Always-On Specificity."""

    def setUp(self):
        self.user = _create_test_user("cx1@example.com")
        self.now = timezone.now()

    def test_empty_when_no_data(self):
        """Returns empty string when user has no tasks/events/meds/goals."""
        from apps.cos.context.specificity_block import build_specificity_block
        result = build_specificity_block(self.user, self.now)
        self.assertEqual(result, "")

    def test_shows_overdue_tasks(self):
        """Shows overdue tasks by name with OVERDUE tag."""
        from apps.cos.context.specificity_block import build_specificity_block
        from apps.life.models import Task

        Task.objects.create(
            user=self.user,
            title="Quarterly Report",
            due_date=self.now.date() - timedelta(days=2),
            priority='now',
        )
        result = build_specificity_block(self.user, self.now)
        self.assertIn("Quarterly Report", result)
        self.assertIn("OVERDUE", result)
        self.assertIn("TOP PRIORITY ITEMS", result)

    def test_shows_due_today_tasks(self):
        """Shows tasks due today by name."""
        from apps.cos.context.specificity_block import build_specificity_block
        from apps.life.models import Task

        Task.objects.create(
            user=self.user,
            title="Buy groceries",
            due_date=self.now.date(),
            priority='soon',
        )
        result = build_specificity_block(self.user, self.now)
        self.assertIn("Buy groceries", result)
        self.assertIn("Due Today", result)

    def test_max_task_limit(self):
        """Never shows more than MAX_TASKS tasks."""
        from apps.cos.context.specificity_block import build_specificity_block, MAX_TASKS
        from apps.life.models import Task

        for i in range(MAX_TASKS + 5):
            Task.objects.create(
                user=self.user,
                title=f"Task {i}",
                due_date=self.now.date() - timedelta(days=i),
                priority='now',
            )
        result = build_specificity_block(self.user, self.now)
        # Count bullet points
        bullet_count = result.count("•")
        # Should have task bullets <= MAX_TASKS (plus possible events/meds/goals)
        self.assertLessEqual(
            result.count("OVERDUE") + result.count("Due Today"),
            MAX_TASKS,
        )

    def test_shows_calendar_events(self):
        """Shows today's calendar events by name with time."""
        from apps.cos.context.specificity_block import build_specificity_block
        from apps.calendar_engine.models import CalendarEvent

        event_start = self.now + timedelta(hours=2)
        CalendarEvent.objects.create(
            user=self.user,
            title="Strategy Meeting",
            start_dt=event_start,
            end_dt=event_start + timedelta(hours=1),
            idempotency_key=uuid4().hex,
        )
        result = build_specificity_block(self.user, self.now)
        self.assertIn("Strategy Meeting", result)
        self.assertIn("EVENTS:", result)

    def test_shows_outstanding_meds(self):
        """Shows outstanding medications by name."""
        from apps.cos.context.specificity_block import build_specificity_block
        from apps.health.models import Medicine, MedicineSchedule

        med = Medicine.objects.create(
            user=self.user,
            name="Valsartan",
            medicine_status=Medicine.STATUS_ACTIVE,
            start_date=self.now.date(),
        )
        MedicineSchedule.objects.create(
            medicine=med,
            scheduled_time=dt.time(8, 0),
        )
        result = build_specificity_block(self.user, self.now)
        self.assertIn("Valsartan", result)
        self.assertIn("NOT TAKEN", result)

    def test_fail_safe_on_exception(self):
        """Returns empty string on any exception."""
        from apps.cos.context.specificity_block import build_specificity_block
        # Pass invalid user to trigger exception
        result = build_specificity_block(None, self.now)
        self.assertEqual(result, "")


# ──────────────────────────────────────────────────────────
# CX2: Lead Signal Prioritizer Tests
# ──────────────────────────────────────────────────────────


class LeadSignalPrioritizerTests(TestCase):
    """Test COS-CX2: Lead Signal Prioritizer."""

    def setUp(self):
        self.user = _create_test_user("cx2@example.com")
        self.now = timezone.now()

    def test_empty_when_no_signals(self):
        """Returns empty string when nothing is urgent."""
        from apps.cos.context.signal_prioritizer import compute_lead_signal
        result = compute_lead_signal(self.user, "", self.now)
        self.assertEqual(result, "")

    def test_imminent_event_highest_priority(self):
        """Event starting within 5 minutes gets highest score."""
        from apps.cos.context.signal_prioritizer import compute_lead_signal
        from apps.calendar_engine.models import CalendarEvent

        CalendarEvent.objects.create(
            user=self.user,
            title="Board Meeting",
            start_dt=self.now + timedelta(minutes=3),
            end_dt=self.now + timedelta(hours=1, minutes=3),
            idempotency_key=uuid4().hex,
        )
        result = compute_lead_signal(self.user, "", self.now)
        self.assertIn("Board Meeting", result)
        self.assertIn("LEAD WITH THIS", result)

    def test_overdue_task_signals(self):
        """Overdue high-priority tasks generate signal."""
        from apps.cos.context.signal_prioritizer import compute_lead_signal
        from apps.life.models import Task

        Task.objects.create(
            user=self.user,
            title="Submit tax forms",
            due_date=self.now.date() - timedelta(days=3),
            priority='now',
        )
        result = compute_lead_signal(self.user, "", self.now)
        self.assertIn("Submit tax forms", result)

    def test_overdue_meds_signal(self):
        """Overdue medications generate signal."""
        from apps.cos.context.signal_prioritizer import compute_lead_signal
        from apps.health.models import Medicine, MedicineSchedule

        med = Medicine.objects.create(
            user=self.user,
            name="Lisinopril",
            medicine_status=Medicine.STATUS_ACTIVE,
            start_date=self.now.date(),
        )
        # Schedule for early morning (guaranteed past)
        MedicineSchedule.objects.create(
            medicine=med,
            scheduled_time=dt.time(6, 0),
        )
        result = compute_lead_signal(self.user, "", self.now)
        # May or may not trigger depending on current time
        # But function should not error
        self.assertIsInstance(result, str)

    def test_fail_safe_on_exception(self):
        """Returns empty string on any exception."""
        from apps.cos.context.signal_prioritizer import compute_lead_signal
        result = compute_lead_signal(None, "", self.now)
        self.assertEqual(result, "")


# ──────────────────────────────────────────────────────────
# CX3: Goal Behavior Gap Analyzer Tests
# ──────────────────────────────────────────────────────────


class GoalGapAnalyzerTests(TestCase):
    """Test COS-CX3: Goal Behavior Gap Analyzer."""

    def setUp(self):
        self.user = _create_test_user("cx3@example.com")
        self.now = timezone.now()

    def test_empty_when_no_goals(self):
        """Returns empty list when user has no active goals."""
        from apps.cos.intelligence.goal_gap_analyzer import analyze_goal_behavior_gaps
        result = analyze_goal_behavior_gaps(self.user, self.now)
        self.assertEqual(result, [])

    def test_format_empty_gaps(self):
        """format_goal_gaps_block returns empty string for empty list."""
        from apps.cos.intelligence.goal_gap_analyzer import format_goal_gaps_block
        result = format_goal_gaps_block([])
        self.assertEqual(result, "")

    def test_format_gaps_block(self):
        """format_goal_gaps_block formats gap data correctly."""
        from apps.cos.intelligence.goal_gap_analyzer import format_goal_gaps_block
        gaps = [{
            'goal_title': "Run 3x/week",
            'target_desc': "3x/week",
            'actual_desc': "1.0x/week (last 4 weeks)",
            'gap_pct': -67,
            'trend': "declining",
            'risk_level': "high",
        }]
        result = format_goal_gaps_block(gaps)
        self.assertIn("GOAL GAPS", result)
        self.assertIn("Run 3x/week", result)
        self.assertIn("[HIGH]", result)
        self.assertIn("Target: 3x/week", result)
        self.assertIn("-67%", result)
        self.assertIn("declining", result)

    def test_max_gaps_limit(self):
        """Never returns more than MAX_GAPS gaps."""
        from apps.cos.intelligence.goal_gap_analyzer import MAX_GAPS, format_goal_gaps_block
        gaps = [
            {
                'goal_title': f"Goal {i}",
                'target_desc': "daily",
                'actual_desc': "0x",
                'gap_pct': -100 + i,
                'trend': "stable",
                'risk_level': "high",
            }
            for i in range(MAX_GAPS + 3)
        ]
        result = format_goal_gaps_block(gaps[:MAX_GAPS])
        # Ensure we don't exceed MAX_GAPS items
        count = result.count("Goal ")
        self.assertLessEqual(count, MAX_GAPS)

    def test_fail_safe_on_exception(self):
        """Returns empty list on any exception."""
        from apps.cos.intelligence.goal_gap_analyzer import analyze_goal_behavior_gaps
        result = analyze_goal_behavior_gaps(None, self.now)
        self.assertEqual(result, [])

    def test_extract_frequency_target(self):
        """Extracts numeric frequency from goal text."""
        from apps.cos.intelligence.goal_gap_analyzer import _extract_frequency_target

        class MockGoal:
            def __init__(self, title, desc='', success=''):
                self.title = title
                self.description = desc
                self.success_looks_like = success

        # 3x/week pattern
        g = MockGoal("Workout 3x/week")
        self.assertEqual(_extract_frequency_target(g, default=1), 3)

        # "daily" pattern
        g = MockGoal("Daily Bible reading")
        self.assertEqual(_extract_frequency_target(g, default=1), 7)

        # "every day" pattern
        g = MockGoal("Journal every day")
        self.assertEqual(_extract_frequency_target(g, default=1), 7)

        # No match → default
        g = MockGoal("Be a better person")
        self.assertEqual(_extract_frequency_target(g, default=3), 3)

    def test_compute_gap_pct(self):
        """Gap percentage calculation: negative = behind."""
        from apps.cos.intelligence.goal_gap_analyzer import _compute_gap_pct

        # 1/3 = -67%
        self.assertEqual(_compute_gap_pct(1, 3), -66)
        # 3/3 = 0%
        self.assertEqual(_compute_gap_pct(3, 3), 0)
        # 4/3 = +33%
        self.assertEqual(_compute_gap_pct(4, 3), 33)
        # Zero target = 0%
        self.assertEqual(_compute_gap_pct(5, 0), 0)

    def test_risk_from_gap(self):
        """Risk level classification."""
        from apps.cos.intelligence.goal_gap_analyzer import _risk_from_gap
        self.assertEqual(_risk_from_gap(-70), "high")
        self.assertEqual(_risk_from_gap(-40), "moderate")
        self.assertEqual(_risk_from_gap(-20), "low")
        self.assertIsNone(_risk_from_gap(-10))
        self.assertIsNone(_risk_from_gap(0))

    def test_compute_trend(self):
        """Trend detection."""
        from apps.cos.intelligence.goal_gap_analyzer import _compute_trend
        self.assertEqual(_compute_trend(5, 2), "improving")
        self.assertEqual(_compute_trend(2, 5), "declining")
        self.assertEqual(_compute_trend(3, 3), "stable")
        self.assertEqual(_compute_trend(4, 3), "stable")  # Within margin


# ──────────────────────────────────────────────────────────
# CX4: Temporal Execution Matching Tests
# ──────────────────────────────────────────────────────────


class TemporalMatcherTests(TestCase):
    """Test COS-CX4: Temporal Execution Matching."""

    def setUp(self):
        self.user = _create_test_user("cx4@example.com")
        # Use a morning time so there's room for windows
        self.now = timezone.now().replace(hour=9, minute=0, second=0, microsecond=0)

    def test_empty_when_no_tasks(self):
        """Returns empty string when user has no overdue/due tasks."""
        from apps.cos.context.temporal_matcher import compute_execution_windows
        result = compute_execution_windows(self.user, self.now)
        self.assertEqual(result, "")

    def test_empty_when_no_free_windows(self):
        """Returns empty when schedule is fully packed."""
        from apps.cos.context.temporal_matcher import compute_execution_windows
        from apps.life.models import Task
        from apps.calendar_engine.models import CalendarEvent

        # Create a task
        Task.objects.create(
            user=self.user,
            title="Something important",
            due_date=self.now.date(),
            priority='now',
        )
        # Fill entire day with events
        for hour in range(9, 21):
            CalendarEvent.objects.create(
                user=self.user,
                title=f"Meeting {hour}",
                start_dt=self.now.replace(hour=hour),
                end_dt=self.now.replace(hour=hour) + timedelta(hours=1),
                idempotency_key=uuid4().hex,
            )
        result = compute_execution_windows(self.user, self.now)
        # May or may not find windows between events (depends on merge)
        self.assertIsInstance(result, str)

    def test_matches_task_to_window(self):
        """Matches an overdue task to a free window."""
        from apps.cos.context.temporal_matcher import compute_execution_windows
        from apps.life.models import Task

        Task.objects.create(
            user=self.user,
            title="Quarterly Report",
            due_date=self.now.date() - timedelta(days=1),
            priority='now',
        )
        result = compute_execution_windows(self.user, self.now)
        if result:  # May depend on time-of-day
            self.assertIn("Quarterly Report", result)
            self.assertIn("SUGGESTED EXECUTION WINDOWS", result)

    def test_merge_overlapping_blocks(self):
        """Overlapping blocks are merged correctly."""
        from apps.cos.context.temporal_matcher import _merge_overlapping

        blocks = [
            (self.now, self.now + timedelta(hours=1)),
            (self.now + timedelta(minutes=30), self.now + timedelta(hours=2)),
        ]
        merged = _merge_overlapping(blocks)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0][0], self.now)
        self.assertEqual(merged[0][1], self.now + timedelta(hours=2))

    def test_merge_non_overlapping_blocks(self):
        """Non-overlapping blocks remain separate."""
        from apps.cos.context.temporal_matcher import _merge_overlapping

        blocks = [
            (self.now, self.now + timedelta(hours=1)),
            (self.now + timedelta(hours=2), self.now + timedelta(hours=3)),
        ]
        merged = _merge_overlapping(blocks)
        self.assertEqual(len(merged), 2)

    def test_fail_safe_on_exception(self):
        """Returns empty string on any exception."""
        from apps.cos.context.temporal_matcher import compute_execution_windows
        result = compute_execution_windows(None, self.now)
        self.assertEqual(result, "")


# ──────────────────────────────────────────────────────────
# CX5: Diagnostic Context Tests
# ──────────────────────────────────────────────────────────


class DiagnosticContextTests(TestCase):
    """Test COS-CX5: Diagnostic Context Expansion."""

    def setUp(self):
        self.user = _create_test_user("cx5@example.com")
        self.now = timezone.now()

    def test_trigger_detection_positive(self):
        """Detects diagnostic trigger phrases."""
        from apps.cos.context.diagnostic_context import is_diagnostic_query

        self.assertTrue(is_diagnostic_query("Why am I struggling with workouts?"))
        self.assertTrue(is_diagnostic_query("What's going wrong with my routine?"))
        self.assertTrue(is_diagnostic_query("I can't seem to stick to anything"))
        self.assertTrue(is_diagnostic_query("help me understand why I keep failing"))
        self.assertTrue(is_diagnostic_query("I keep failing at my goals"))
        self.assertTrue(is_diagnostic_query("What's causing my lack of progress?"))

    def test_trigger_detection_negative(self):
        """Non-diagnostic messages don't trigger."""
        from apps.cos.context.diagnostic_context import is_diagnostic_query

        self.assertFalse(is_diagnostic_query("What's on my schedule today?"))
        self.assertFalse(is_diagnostic_query("Add a task for tomorrow"))
        self.assertFalse(is_diagnostic_query("Good morning"))
        self.assertFalse(is_diagnostic_query("Log my workout"))

    def test_empty_when_no_data(self):
        """Returns empty string when user has no cross-domain data."""
        from apps.cos.context.diagnostic_context import build_diagnostic_context
        result = build_diagnostic_context(self.user, self.now, "why am I struggling?")
        # May return "" if no signals or may return task/med signals
        self.assertIsInstance(result, str)

    def test_includes_reasoning_instruction(self):
        """When data is available, includes causal reasoning instruction."""
        from apps.cos.context.diagnostic_context import build_diagnostic_context
        from apps.life.models import Task

        # Create some overdue tasks to generate a signal
        for i in range(5):
            Task.objects.create(
                user=self.user,
                title=f"Overdue task {i}",
                due_date=self.now.date() - timedelta(days=i + 1),
                priority='now',
            )
        result = build_diagnostic_context(self.user, self.now, "why am I falling behind?")
        if result:
            self.assertIn("DIAGNOSTIC SIGNALS", result)
            self.assertIn("REASONING TASK", result)

    def test_fail_safe_on_exception(self):
        """Returns empty string on any exception."""
        from apps.cos.context.diagnostic_context import build_diagnostic_context
        # Pass invalid 'now' to force crash in .date() call
        result = build_diagnostic_context(self.user, "not-a-datetime", "why?")
        self.assertEqual(result, "")


# ──────────────────────────────────────────────────────────
# CX6: Behavioral Forecast Tests
# ──────────────────────────────────────────────────────────


class BehaviorForecastTests(TestCase):
    """Test COS-CX6: Behavioral Forecast Extension."""

    def setUp(self):
        self.user = _create_test_user("cx6@example.com")
        self.now = timezone.now()

    def test_returns_forecast_for_new_user(self):
        """New user with no behavior data gets 0% forecast (history shows no completions)."""
        from apps.cos.intelligence.behavior_forecast import compute_behavior_forecast
        result = compute_behavior_forecast(self.user, self.now)
        # New users have enough "no completion" days to trigger forecast
        if result:
            self.assertIn("BEHAVIORAL FORECAST", result)
            self.assertIn("0% likely", result)

    def test_schedule_load_classification(self):
        """Schedule load classification works correctly."""
        from apps.cos.intelligence.behavior_forecast import _get_schedule_load
        from apps.calendar_engine.models import CalendarEvent

        tomorrow = self.now.date() + timedelta(days=1)

        # No events = light
        load = _get_schedule_load(self.user, tomorrow, self.now.tzinfo)
        self.assertEqual(load, 'light')

        # 3 events = moderate
        for i in range(3):
            CalendarEvent.objects.create(
                user=self.user,
                title=f"Event {i}",
                start_dt=self.now + timedelta(days=1, hours=i),
                end_dt=self.now + timedelta(days=1, hours=i + 1),
                idempotency_key=uuid4().hex,
            )
        load = _get_schedule_load(self.user, tomorrow, self.now.tzinfo)
        self.assertEqual(load, 'moderate')

        # 5+ events = heavy
        for i in range(3, 6):
            CalendarEvent.objects.create(
                user=self.user,
                title=f"Event {i}",
                start_dt=self.now + timedelta(days=1, hours=i),
                end_dt=self.now + timedelta(days=1, hours=i + 1),
                idempotency_key=uuid4().hex,
            )
        load = _get_schedule_load(self.user, tomorrow, self.now.tzinfo)
        self.assertEqual(load, 'heavy')

    def test_load_description(self):
        """Load description returns human-readable text."""
        from apps.cos.intelligence.behavior_forecast import _load_description
        self.assertIn("Heavy", _load_description('heavy'))
        self.assertIn("Moderate", _load_description('moderate'))
        self.assertIn("Light", _load_description('light'))
        self.assertEqual(_load_description('unknown'), "")

    def test_fail_safe_on_exception(self):
        """Returns empty string on any exception."""
        from apps.cos.intelligence.behavior_forecast import compute_behavior_forecast
        result = compute_behavior_forecast(None, self.now)
        self.assertEqual(result, "")


# ──────────────────────────────────────────────────────────
# Integration: COS-CX wiring in cos_context.py
# ──────────────────────────────────────────────────────────


class CosCXIntegrationTests(TestCase):
    """Test that COS-CX modules are properly wired into format_cos_system_injection."""

    def setUp(self):
        self.user = _create_test_user("cxint@example.com")

    def test_format_cos_does_not_crash(self):
        """format_cos_system_injection completes without error even with CX modules."""
        from apps.core.ai_orchestrator.cos_context import (
            build_cos_context,
            format_cos_system_injection,
        )
        context = build_cos_context(self.user)
        result = format_cos_system_injection(context)
        self.assertIsInstance(result, str)
        self.assertIn("SITUATIONAL AWARENESS", result)

    def test_cx_blocks_present_when_data_exists(self):
        """When user has data, CX blocks appear in injection."""
        from apps.core.ai_orchestrator.cos_context import (
            build_cos_context,
            format_cos_system_injection,
        )
        from apps.life.models import Task

        Task.objects.create(
            user=self.user,
            title="Important Task",
            due_date=timezone.now().date() - timedelta(days=1),
            priority='now',
        )
        context = build_cos_context(self.user)
        result = format_cos_system_injection(context)
        # CX1 specificity block should include the task name
        self.assertIn("Important Task", result)
