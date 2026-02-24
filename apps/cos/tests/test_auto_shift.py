"""
CoS v2 — Phase 8 Tests: Priority + Time-of-Day Auto-Shifting

Tests:
1. Priority determination: protected=high, activity-type-based defaults
2. Time suitability: per-activity-type windows
3. Time clamping: too early→earliest, too late→next day
4. Shift proposal: conflict avoidance, slot finding
5. Auto-shift gate: only low-priority auto-shifts
6. Protected event gate: never auto-shifted
7. Shift execution: CalendarEvent updated + audit log created
8. Confirmation gate: medium/high requires user_confirmed=True
9. Shift history and event-specific log queries
10. Max shift distance enforcement
"""

import datetime as dt
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils import timezone

from apps.calendar_engine.models import CalendarEvent
from apps.cos.models import CosAutoShiftLog
from apps.cos.services.auto_shift_service import (
    ACTIVITY_PRIORITY,
    AUTO_SHIFT_PRIORITIES,
    CosAutoShiftService,
    MAX_SHIFT_HOURS,
    TIME_SUITABILITY,
)

User = get_user_model()


def _create_test_user(email="cosshift@example.com"):
    from apps.users.models import TermsAcceptance

    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


def _create_event(user, title, start_dt=None, duration_hours=1, is_protected=False):
    """Create a calendar event."""
    if not start_dt:
        start_dt = timezone.now() + dt.timedelta(hours=2)
    end_dt = start_dt + dt.timedelta(hours=duration_hours)
    return CalendarEvent.objects.create(
        user=user,
        title=title,
        start_dt=start_dt,
        end_dt=end_dt,
        is_protected=is_protected,
        idempotency_key=uuid4().hex,
    )


def _make_time(hour, minute=0, days_offset=0):
    """Create a timezone-aware datetime at a specific hour today+offset."""
    base = timezone.now().replace(
        hour=hour, minute=minute, second=0, microsecond=0,
    )
    return base + dt.timedelta(days=days_offset)


# ──────────────────────────────────────────────────────────
# Priority Determination Tests
# ──────────────────────────────────────────────────────────


class PriorityDeterminationTests(TestCase):
    """Test event priority determination."""

    def setUp(self):
        self.user = _create_test_user("priority@example.com")
        self.svc = CosAutoShiftService(self.user)

    def test_protected_event_is_high(self):
        """Protected events are always high priority."""
        event = _create_event(self.user, "Daily Workout", is_protected=True)
        self.assertEqual(self.svc.determine_priority(event), "high")

    def test_meeting_is_high(self):
        """Meetings default to high priority."""
        event = _create_event(self.user, "Team Meeting")
        self.assertEqual(self.svc.determine_priority(event), "high")

    def test_workout_is_medium(self):
        """Workouts default to medium priority."""
        event = _create_event(self.user, "Morning Workout")
        self.assertEqual(self.svc.determine_priority(event), "medium")

    def test_prayer_is_low(self):
        """Prayer defaults to low priority."""
        event = _create_event(self.user, "Evening Prayer")
        self.assertEqual(self.svc.determine_priority(event), "low")

    def test_journaling_is_low(self):
        """Journaling defaults to low priority."""
        event = _create_event(self.user, "Journal Writing Session")
        self.assertEqual(self.svc.determine_priority(event), "low")

    def test_unknown_title_is_medium(self):
        """Unknown activity types default to medium."""
        event = _create_event(self.user, "Something Random")
        self.assertEqual(self.svc.determine_priority(event), "medium")

    def test_can_auto_shift_low_only(self):
        """Only low-priority events can be auto-shifted."""
        low = _create_event(self.user, "Evening Prayer")
        med = _create_event(self.user, "Morning Workout")
        high = _create_event(self.user, "Team Meeting")

        self.assertTrue(self.svc.can_auto_shift(low))
        self.assertFalse(self.svc.can_auto_shift(med))
        self.assertFalse(self.svc.can_auto_shift(high))


# ──────────────────────────────────────────────────────────
# Time Suitability Tests
# ──────────────────────────────────────────────────────────


class TimeSuitabilityTests(TestCase):
    """Test time-of-day suitability rules."""

    def setUp(self):
        self.user = _create_test_user("timesuite@example.com")
        self.svc = CosAutoShiftService(self.user)

    def test_workout_suitable_morning(self):
        """Workout at 7am is suitable."""
        self.assertTrue(
            self.svc.is_time_suitable(_make_time(7), "workout")
        )

    def test_workout_not_suitable_late_night(self):
        """Workout at 11pm is NOT suitable."""
        self.assertFalse(
            self.svc.is_time_suitable(_make_time(23), "workout")
        )

    def test_meeting_suitable_business_hours(self):
        """Meeting at 10am is suitable."""
        self.assertTrue(
            self.svc.is_time_suitable(_make_time(10), "meeting")
        )

    def test_meeting_not_suitable_early_morning(self):
        """Meeting at 6am is NOT suitable."""
        self.assertFalse(
            self.svc.is_time_suitable(_make_time(6), "meeting")
        )

    def test_prayer_suitable_early(self):
        """Prayer at 5am is suitable."""
        self.assertTrue(
            self.svc.is_time_suitable(_make_time(5), "prayer")
        )

    def test_therapy_daytime_only(self):
        """Therapy at 3pm is suitable, at 7pm is not."""
        self.assertTrue(
            self.svc.is_time_suitable(_make_time(15), "therapy")
        )
        self.assertFalse(
            self.svc.is_time_suitable(_make_time(19), "therapy")
        )

    def test_get_time_window(self):
        """Returns correct window for known activity types."""
        self.assertEqual(self.svc.get_time_window("workout"), (5, 21))
        self.assertEqual(self.svc.get_time_window("meeting"), (8, 20))
        self.assertEqual(self.svc.get_time_window("prayer"), (5, 22))

    def test_unknown_type_uses_default(self):
        """Unknown activity types use default window."""
        self.assertEqual(
            self.svc.get_time_window("unknown"),
            TIME_SUITABILITY["default"],
        )


# ──────────────────────────────────────────────────────────
# Time Clamping Tests
# ──────────────────────────────────────────────────────────


class TimeClampingTests(TestCase):
    """Test time clamping to suitable windows."""

    def setUp(self):
        self.user = _create_test_user("clamp@example.com")
        self.svc = CosAutoShiftService(self.user)

    def test_clamp_too_early(self):
        """Too-early time gets clamped to earliest hour."""
        early = _make_time(3)  # 3am
        clamped = self.svc.clamp_to_suitable_time(early, "workout")
        self.assertEqual(clamped.hour, 5)  # workout earliest

    def test_clamp_too_late(self):
        """Too-late time gets clamped to earliest NEXT DAY."""
        late = _make_time(23)  # 11pm
        clamped = self.svc.clamp_to_suitable_time(late, "workout")
        self.assertEqual(clamped.hour, 5)
        self.assertEqual(clamped.date(), late.date() + dt.timedelta(days=1))

    def test_suitable_time_unchanged(self):
        """Time within window is not changed."""
        ok_time = _make_time(10)
        clamped = self.svc.clamp_to_suitable_time(ok_time, "workout")
        self.assertEqual(clamped.hour, 10)


# ──────────────────────────────────────────────────────────
# Shift Proposal Tests
# ──────────────────────────────────────────────────────────


class ShiftProposalTests(TestCase):
    """Test shift proposal generation."""

    def setUp(self):
        self.user = _create_test_user("proposal@example.com")
        self.svc = CosAutoShiftService(self.user)

    def test_low_priority_can_auto_shift(self):
        """Low-priority event proposal has can_auto_shift=True."""
        start = _make_time(10)
        event = _create_event(self.user, "Evening Prayer", start_dt=start)
        proposal = self.svc.propose_shift(
            event,
            conflicting_end=start + dt.timedelta(hours=1),
        )
        self.assertTrue(proposal["can_auto_shift"])
        self.assertFalse(proposal["requires_confirmation"])
        self.assertIsNotNone(proposal["proposed_start"])

    def test_high_priority_requires_confirmation(self):
        """High-priority event proposal requires confirmation."""
        start = _make_time(10)
        event = _create_event(self.user, "Team Meeting", start_dt=start)
        proposal = self.svc.propose_shift(
            event,
            conflicting_end=start + dt.timedelta(hours=1),
        )
        self.assertFalse(proposal["can_auto_shift"])
        self.assertTrue(proposal["requires_confirmation"])

    def test_protected_event_rejected(self):
        """Protected event proposal has rejection reason."""
        start = _make_time(10)
        event = _create_event(
            self.user, "Fixed Event", start_dt=start, is_protected=True,
        )
        proposal = self.svc.propose_shift(event)
        self.assertFalse(proposal["can_auto_shift"])
        self.assertIn("Protected", proposal["rejection_reason"])

    def test_proposal_respects_time_suitability(self):
        """Proposed time must be within suitable window."""
        # Prayer at 10am with conflict — should shift to suitable time
        start = _make_time(10)
        event = _create_event(self.user, "Evening Prayer", start_dt=start)
        proposal = self.svc.propose_shift(
            event,
            conflicting_end=start + dt.timedelta(hours=1),
        )
        if proposal["proposed_start"]:
            earliest, latest = TIME_SUITABILITY.get("prayer", TIME_SUITABILITY["default"])
            self.assertGreaterEqual(proposal["proposed_start"].hour, earliest)
            self.assertLessEqual(proposal["proposed_start"].hour, latest)

    def test_proposal_includes_activity_type(self):
        """Proposal includes detected activity type."""
        event = _create_event(self.user, "Morning Workout", start_dt=_make_time(8))
        proposal = self.svc.propose_shift(event)
        self.assertEqual(proposal["activity_type"], "workout")


# ──────────────────────────────────────────────────────────
# Shift Execution Tests
# ──────────────────────────────────────────────────────────


class ShiftExecutionTests(TestCase):
    """Test actual event shifting and audit logging."""

    def setUp(self):
        self.user = _create_test_user("execute@example.com")
        self.svc = CosAutoShiftService(self.user)

    def test_execute_low_priority_shift(self):
        """Low-priority event shifts successfully."""
        start = _make_time(10)
        event = _create_event(self.user, "Evening Prayer", start_dt=start)
        new_start = start + dt.timedelta(hours=1)
        new_end = new_start + dt.timedelta(hours=1)

        result = self.svc.execute_shift(
            event, new_start, new_end,
            reason="Conflict with meeting",
            shift_type="conflict_avoidance",
        )
        self.assertTrue(result["success"])
        self.assertIsNotNone(result["log"])
        self.assertEqual(result["log"].priority_level, "low")
        self.assertTrue(result["log"].auto_shifted)
        self.assertFalse(result["log"].user_confirmed)

    def test_execute_creates_audit_log(self):
        """Shift creates CosAutoShiftLog entry."""
        start = _make_time(10)
        event = _create_event(self.user, "Prayer Time", start_dt=start)
        new_start = start + dt.timedelta(hours=1)
        new_end = new_start + dt.timedelta(hours=1)

        result = self.svc.execute_shift(
            event, new_start, new_end,
            reason="Conflict avoidance",
            shift_type="conflict_avoidance",
        )

        logs = CosAutoShiftLog.objects.filter(user=self.user)
        self.assertEqual(logs.count(), 1)
        log = logs.first()
        self.assertEqual(log.original_start, start)
        self.assertEqual(log.new_start, new_start)
        self.assertEqual(log.reason, "Conflict avoidance")
        self.assertEqual(log.shift_type, "conflict_avoidance")

    def test_medium_priority_blocked_without_confirmation(self):
        """Medium-priority event blocked without user_confirmed."""
        start = _make_time(10)
        event = _create_event(self.user, "Morning Workout", start_dt=start)
        new_start = start + dt.timedelta(hours=1)
        new_end = new_start + dt.timedelta(hours=1)

        result = self.svc.execute_shift(
            event, new_start, new_end,
            reason="Test",
        )
        self.assertFalse(result["success"])
        self.assertIn("requires user confirmation", result["error"])

    def test_medium_priority_allowed_with_confirmation(self):
        """Medium-priority event allowed with user_confirmed=True."""
        start = _make_time(10)
        event = _create_event(self.user, "Morning Workout", start_dt=start)
        new_start = start + dt.timedelta(hours=1)
        new_end = new_start + dt.timedelta(hours=1)

        result = self.svc.execute_shift(
            event, new_start, new_end,
            reason="User approved",
            user_confirmed=True,
        )
        self.assertTrue(result["success"])
        self.assertTrue(result["log"].user_confirmed)
        self.assertFalse(result["log"].auto_shifted)

    def test_execute_updates_event_times(self):
        """Event start_dt and end_dt are actually updated."""
        start = _make_time(10)
        event = _create_event(self.user, "Meditation", start_dt=start)
        new_start = start + dt.timedelta(hours=2)
        new_end = new_start + dt.timedelta(hours=1)

        self.svc.execute_shift(event, new_start, new_end, reason="Test")

        event.refresh_from_db()
        self.assertEqual(event.start_dt, new_start)
        self.assertEqual(event.end_dt, new_end)


# ──────────────────────────────────────────────────────────
# Shift History Tests
# ──────────────────────────────────────────────────────────


class ShiftHistoryTests(TestCase):
    """Test shift history queries."""

    def setUp(self):
        self.user = _create_test_user("history@example.com")
        self.svc = CosAutoShiftService(self.user)

    def test_get_shift_history(self):
        """Returns recent shift logs."""
        start = _make_time(10)
        event = _create_event(self.user, "Prayer", start_dt=start)
        new_start = start + dt.timedelta(hours=1)
        self.svc.execute_shift(
            event, new_start, new_start + dt.timedelta(hours=1),
            reason="Test",
        )

        history = self.svc.get_shift_history(days=7)
        self.assertEqual(history.count(), 1)

    def test_get_shifts_for_event(self):
        """Returns shift logs for a specific event."""
        start = _make_time(10)
        event1 = _create_event(self.user, "Prayer 1", start_dt=start)
        event2 = _create_event(
            self.user, "Meditation",
            start_dt=start + dt.timedelta(hours=3),
        )

        new_start = start + dt.timedelta(hours=1)
        self.svc.execute_shift(
            event1, new_start, new_start + dt.timedelta(hours=1),
            reason="Test 1",
        )
        new_start2 = start + dt.timedelta(hours=4)
        self.svc.execute_shift(
            event2, new_start2, new_start2 + dt.timedelta(hours=1),
            reason="Test 2",
        )

        logs1 = self.svc.get_shifts_for_event(event1)
        logs2 = self.svc.get_shifts_for_event(event2)
        self.assertEqual(logs1.count(), 1)
        self.assertEqual(logs2.count(), 1)


# ──────────────────────────────────────────────────────────
# Max Shift Distance Tests
# ──────────────────────────────────────────────────────────


class MaxShiftDistanceTests(TestCase):
    """Test maximum shift distance enforcement."""

    def setUp(self):
        self.user = _create_test_user("distance@example.com")
        self.svc = CosAutoShiftService(self.user)

    def test_proposal_within_max_distance(self):
        """Shifts within MAX_SHIFT_HOURS are accepted."""
        start = _make_time(10)
        event = _create_event(self.user, "Meditation", start_dt=start)
        conflicting_end = start + dt.timedelta(hours=1)

        proposal = self.svc.propose_shift(
            event, conflicting_end=conflicting_end,
        )
        if proposal["proposed_start"]:
            delta_hours = abs(
                (proposal["proposed_start"] - start).total_seconds()
            ) / 3600
            self.assertLessEqual(delta_hours, MAX_SHIFT_HOURS)
