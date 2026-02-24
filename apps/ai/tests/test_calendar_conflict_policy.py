# ==============================================================================
# File: tests/test_calendar_conflict_policy.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for Phase 10 Calendar Conflict Policy — no silent
#              double-booking. Validates pre-commit conflict detection, three
#              decision cases, auto-protect, force override, and suggestions.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-24
# ==============================================================================
"""
Calendar Conflict Policy Tests

Phase 10 — pre-commit conflict detection prevents silent double-booking.
Every time overlap requires a user decision before the event is committed.

RUN: python manage.py test apps.ai.tests.test_calendar_conflict_policy -v 2
"""

import datetime as dt
from uuid import uuid4

import pytz
from django.test import TestCase

from apps.calendar_engine.models import CalendarEvent
from apps.calendar_engine.services.calendar_mutation_service import (
    CalendarMutationService,
)
from apps.calendar_engine.services.conflicts import (
    classify_conflict_case,
    detect_all_conflicts,
)
from apps.users.models import User


# ============================================================================
# Helpers
# ============================================================================

NY_TZ = pytz.timezone('America/New_York')


def _dt(year, month, day, hour, minute=0):
    """Quick timezone-aware datetime constructor."""
    return NY_TZ.localize(dt.datetime(year, month, day, hour, minute))


class ConflictPolicyTestMixin:
    """Shared setup for conflict policy tests."""

    def _create_user(self, email='conflict@example.com'):
        user = User.objects.create_user(
            email=email,
            password='testpass123',
            first_name='Test',
        )
        prefs = user.preferences
        prefs.timezone = 'America/New_York'
        prefs.ai_enabled = True
        prefs.ai_data_consent = True
        prefs.personal_assistant_enabled = True
        prefs.personal_assistant_consent = True
        prefs.save()
        return user

    def _create_event(self, user, title='Existing Event',
                      start_dt=None, end_dt=None,
                      is_protected=False, **kwargs):
        """Create a CalendarEvent with explicit start/end."""
        if start_dt is None:
            start_dt = _dt(2026, 3, 2, 10, 0)  # Mon Mar 2, 10:00 AM
        if end_dt is None:
            end_dt = start_dt + dt.timedelta(hours=1)
        return CalendarEvent.objects.create(
            user=user,
            title=title,
            start_dt=start_dt,
            end_dt=end_dt,
            is_protected=is_protected,
            idempotency_key=uuid4().hex,
            **kwargs,
        )


# ============================================================================
# Conflict Detection Unit Tests
# ============================================================================

class DetectAllConflictsTests(ConflictPolicyTestMixin, TestCase):
    """Tests for the detect_all_conflicts() function."""

    def setUp(self):
        self.user = self._create_user()

    def test_overlap_detected(self):
        """Overlapping events are detected."""
        self._create_event(self.user, 'Meeting',
                           start_dt=_dt(2026, 3, 2, 10, 0),
                           end_dt=_dt(2026, 3, 2, 11, 0))

        result = detect_all_conflicts(
            self.user,
            start_dt=_dt(2026, 3, 2, 10, 30),
            end_dt=_dt(2026, 3, 2, 11, 30),
        )

        self.assertTrue(result['has_conflict'])
        self.assertEqual(len(result['conflicts']), 1)
        self.assertEqual(result['conflicts'][0]['title'], 'Meeting')

    def test_no_overlap_no_conflict(self):
        """Non-overlapping events don't trigger conflict."""
        self._create_event(self.user, 'Meeting',
                           start_dt=_dt(2026, 3, 2, 10, 0),
                           end_dt=_dt(2026, 3, 2, 11, 0))

        result = detect_all_conflicts(
            self.user,
            start_dt=_dt(2026, 3, 2, 14, 0),
            end_dt=_dt(2026, 3, 2, 15, 0),
        )

        self.assertFalse(result['has_conflict'])

    def test_canceled_events_ignored(self):
        """Canceled events are not counted as conflicts."""
        self._create_event(self.user, 'Canceled Meeting',
                           start_dt=_dt(2026, 3, 2, 10, 0),
                           end_dt=_dt(2026, 3, 2, 11, 0),
                           status=CalendarEvent.STATUS_CANCELED)

        result = detect_all_conflicts(
            self.user,
            start_dt=_dt(2026, 3, 2, 10, 30),
            end_dt=_dt(2026, 3, 2, 11, 30),
        )

        self.assertFalse(result['has_conflict'])

    def test_exclude_event_id(self):
        """Self-update doesn't count as conflict."""
        event = self._create_event(self.user, 'Meeting',
                                   start_dt=_dt(2026, 3, 2, 10, 0),
                                   end_dt=_dt(2026, 3, 2, 11, 0))

        result = detect_all_conflicts(
            self.user,
            start_dt=_dt(2026, 3, 2, 10, 0),
            end_dt=_dt(2026, 3, 2, 11, 30),
            exclude_event_id=event.pk,
        )

        self.assertFalse(result['has_conflict'])


# ============================================================================
# Conflict Classification Tests
# ============================================================================

class ClassifyConflictCaseTests(TestCase):
    """Tests for classify_conflict_case()."""

    def test_case_a_protected_existing_unprotected_new(self):
        """Case A: existing is protected, new is not."""
        conflicts = [{'is_protected': True, 'title': 'Workout'}]
        self.assertEqual(classify_conflict_case(conflicts, False), 'A')

    def test_case_b_both_protected(self):
        """Case B: both existing and new are protected."""
        conflicts = [{'is_protected': True, 'title': 'Workout'}]
        self.assertEqual(classify_conflict_case(conflicts, True), 'B')

    def test_case_c_neither_protected(self):
        """Case C: neither is protected."""
        conflicts = [{'is_protected': False, 'title': 'Meeting'}]
        self.assertEqual(classify_conflict_case(conflicts, False), 'C')

    def test_mixed_conflicts_with_any_protected(self):
        """If ANY existing is protected, it's A or B."""
        conflicts = [
            {'is_protected': False, 'title': 'Meeting'},
            {'is_protected': True, 'title': 'Workout'},
        ]
        self.assertEqual(classify_conflict_case(conflicts, False), 'A')


# ============================================================================
# CalendarMutationService Conflict Policy Tests
# ============================================================================

class CreateConflictPolicyTests(ConflictPolicyTestMixin, TestCase):
    """Tests for conflict detection in CalendarMutationService.create()."""

    def setUp(self):
        self.user = self._create_user()
        self.service = CalendarMutationService(self.user)

    def test_conflict_detected_blocks_create(self):
        """Create is blocked when overlapping event exists."""
        self._create_event(self.user, 'Existing Meeting',
                           start_dt=_dt(2026, 3, 2, 10, 0),
                           end_dt=_dt(2026, 3, 2, 11, 0))

        result = self.service.create(
            title='New Meeting',
            start_dt=_dt(2026, 3, 2, 10, 30),
            end_dt=_dt(2026, 3, 2, 11, 30),
        )

        self.assertFalse(result.success)
        self.assertTrue(result.requires_decision)
        self.assertIsNotNone(result.conflict_details)
        self.assertEqual(result.conflict_details['case'], 'C')
        self.assertEqual(len(result.conflict_details['conflicts']), 1)
        # Event should NOT have been created
        self.assertEqual(CalendarEvent.objects.filter(title='New Meeting').count(), 0)

    def test_no_conflict_allows_create(self):
        """Create succeeds when no overlap exists."""
        self._create_event(self.user, 'Morning Meeting',
                           start_dt=_dt(2026, 3, 2, 8, 0),
                           end_dt=_dt(2026, 3, 2, 9, 0))

        result = self.service.create(
            title='Afternoon Meeting',
            start_dt=_dt(2026, 3, 2, 14, 0),
            end_dt=_dt(2026, 3, 2, 15, 0),
        )

        self.assertTrue(result.success)
        self.assertFalse(result.requires_decision)
        self.assertIsNotNone(result.event)
        self.assertEqual(result.event.title, 'Afternoon Meeting')

    def test_force_override_bypasses_conflict(self):
        """Create with force=True ignores conflict."""
        self._create_event(self.user, 'Existing Meeting',
                           start_dt=_dt(2026, 3, 2, 10, 0),
                           end_dt=_dt(2026, 3, 2, 11, 0))

        result = self.service.create(
            title='Override Meeting',
            start_dt=_dt(2026, 3, 2, 10, 30),
            end_dt=_dt(2026, 3, 2, 11, 30),
            force=True,
        )

        self.assertTrue(result.success)
        self.assertFalse(result.requires_decision)
        self.assertIsNotNone(result.event)
        self.assertEqual(result.event.title, 'Override Meeting')

    def test_case_a_protected_existing(self):
        """Case A: existing is protected, new is not → case 'A'."""
        self._create_event(self.user, 'Workout',
                           start_dt=_dt(2026, 3, 2, 6, 0),
                           end_dt=_dt(2026, 3, 2, 7, 0),
                           is_protected=True)

        result = self.service.create(
            title='Phone Call',
            start_dt=_dt(2026, 3, 2, 6, 30),
            end_dt=_dt(2026, 3, 2, 7, 30),
        )

        self.assertFalse(result.success)
        self.assertTrue(result.requires_decision)
        self.assertEqual(result.conflict_details['case'], 'A')

    def test_case_b_both_protected(self):
        """Case B: both events are protected → case 'B'."""
        self._create_event(self.user, 'Morning Prayer',
                           start_dt=_dt(2026, 3, 2, 6, 0),
                           end_dt=_dt(2026, 3, 2, 7, 0),
                           is_protected=True)

        # "Bible Study" auto-protects
        result = self.service.create(
            title='Bible Study',
            start_dt=_dt(2026, 3, 2, 6, 30),
            end_dt=_dt(2026, 3, 2, 7, 30),
        )

        self.assertFalse(result.success)
        self.assertTrue(result.requires_decision)
        self.assertEqual(result.conflict_details['case'], 'B')

    def test_suggestions_returned_with_conflict(self):
        """Conflict response includes suggested alternative time slots."""
        self._create_event(self.user, 'Meeting',
                           start_dt=_dt(2026, 3, 2, 10, 0),
                           end_dt=_dt(2026, 3, 2, 11, 0))

        result = self.service.create(
            title='New Event',
            start_dt=_dt(2026, 3, 2, 10, 30),
            end_dt=_dt(2026, 3, 2, 11, 30),
        )

        self.assertFalse(result.success)
        self.assertTrue(result.requires_decision)
        # suggested_alternatives should be present (may be empty if no gaps)
        # but the field should exist
        self.assertIn('suggested_alternatives', result.__dict__)


# ============================================================================
# Auto-Protect Tests
# ============================================================================

class AutoProtectTests(ConflictPolicyTestMixin, TestCase):
    """Tests for auto-protect logic in CalendarMutationService."""

    def setUp(self):
        self.user = self._create_user()
        self.service = CalendarMutationService(self.user)

    def test_auto_protect_workout(self):
        """Event titled 'Morning Workout' gets is_protected=True."""
        result = self.service.create(
            title='Morning Workout',
            start_dt=_dt(2026, 3, 2, 6, 0),
            end_dt=_dt(2026, 3, 2, 7, 0),
        )

        self.assertTrue(result.success)
        self.assertTrue(result.event.is_protected)

    def test_auto_protect_bible_study(self):
        """Event titled 'Bible Study' gets is_protected=True."""
        result = self.service.create(
            title='Bible Study',
            start_dt=_dt(2026, 3, 2, 18, 0),
            end_dt=_dt(2026, 3, 2, 20, 0),
        )

        self.assertTrue(result.success)
        self.assertTrue(result.event.is_protected)

    def test_auto_protect_prayer(self):
        """Event titled 'Prayer Time' gets is_protected=True."""
        result = self.service.create(
            title='Prayer Time',
            start_dt=_dt(2026, 3, 2, 5, 0),
            end_dt=_dt(2026, 3, 2, 5, 30),
        )

        self.assertTrue(result.success)
        self.assertTrue(result.event.is_protected)

    def test_auto_protect_doctor(self):
        """Event titled 'Doctor Appointment' gets is_protected=True."""
        result = self.service.create(
            title='Doctor Appointment',
            start_dt=_dt(2026, 3, 2, 14, 0),
            end_dt=_dt(2026, 3, 2, 15, 0),
        )

        self.assertTrue(result.success)
        self.assertTrue(result.event.is_protected)

    def test_no_auto_protect_generic(self):
        """Generic event does NOT get auto-protected."""
        result = self.service.create(
            title='Team Standup',
            start_dt=_dt(2026, 3, 2, 9, 0),
            end_dt=_dt(2026, 3, 2, 9, 30),
        )

        self.assertTrue(result.success)
        self.assertFalse(result.event.is_protected)

    def test_auto_protect_case_insensitive(self):
        """Auto-protect matching is case-insensitive."""
        result = self.service.create(
            title='MORNING WORKOUT',
            start_dt=_dt(2026, 3, 2, 6, 0),
            end_dt=_dt(2026, 3, 2, 7, 0),
        )

        self.assertTrue(result.success)
        self.assertTrue(result.event.is_protected)


# ============================================================================
# Update Conflict Policy Tests
# ============================================================================

class UpdateConflictPolicyTests(ConflictPolicyTestMixin, TestCase):
    """Tests for conflict detection in CalendarMutationService.update()."""

    def setUp(self):
        self.user = self._create_user()
        self.service = CalendarMutationService(self.user)

    def test_update_conflict_detected(self):
        """Moving event into an occupied slot triggers conflict."""
        # Existing events
        self._create_event(self.user, 'Blocker',
                           start_dt=_dt(2026, 3, 2, 14, 0),
                           end_dt=_dt(2026, 3, 2, 15, 0))
        movable = self._create_event(self.user, 'My Meeting',
                                     start_dt=_dt(2026, 3, 2, 10, 0),
                                     end_dt=_dt(2026, 3, 2, 11, 0))

        result = self.service.update(
            movable.pk,
            start_dt=_dt(2026, 3, 2, 14, 30),
            end_dt=_dt(2026, 3, 2, 15, 30),
        )

        self.assertFalse(result.success)
        self.assertTrue(result.requires_decision)

    def test_update_no_conflict(self):
        """Moving event to an open slot succeeds."""
        movable = self._create_event(self.user, 'My Meeting',
                                     start_dt=_dt(2026, 3, 2, 10, 0),
                                     end_dt=_dt(2026, 3, 2, 11, 0))

        result = self.service.update(
            movable.pk,
            start_dt=_dt(2026, 3, 2, 14, 0),
            end_dt=_dt(2026, 3, 2, 15, 0),
        )

        self.assertTrue(result.success)
        self.assertFalse(result.requires_decision)

    def test_protected_event_cannot_change_day(self):
        """Protected event cannot be moved to a different day."""
        protected = self._create_event(self.user, 'Workout',
                                       start_dt=_dt(2026, 3, 2, 6, 0),
                                       end_dt=_dt(2026, 3, 2, 7, 0),
                                       is_protected=True)

        result = self.service.update(
            protected.pk,
            start_dt=_dt(2026, 3, 3, 6, 0),  # Next day
            end_dt=_dt(2026, 3, 3, 7, 0),
        )

        self.assertFalse(result.success)
        self.assertIn("different day", result.error)

    def test_protected_event_can_change_time_same_day(self):
        """Protected event CAN be moved within the same day."""
        protected = self._create_event(self.user, 'Workout',
                                       start_dt=_dt(2026, 3, 2, 6, 0),
                                       end_dt=_dt(2026, 3, 2, 7, 0),
                                       is_protected=True)

        result = self.service.update(
            protected.pk,
            start_dt=_dt(2026, 3, 2, 7, 0),  # Same day, later
            end_dt=_dt(2026, 3, 2, 8, 0),
        )

        self.assertTrue(result.success)

    def test_update_force_override_bypasses_conflict(self):
        """Update with force=True skips conflict detection."""
        self._create_event(self.user, 'Blocker',
                           start_dt=_dt(2026, 3, 2, 14, 0),
                           end_dt=_dt(2026, 3, 2, 15, 0))
        movable = self._create_event(self.user, 'My Meeting',
                                     start_dt=_dt(2026, 3, 2, 10, 0),
                                     end_dt=_dt(2026, 3, 2, 11, 0))

        result = self.service.update(
            movable.pk,
            force=True,
            start_dt=_dt(2026, 3, 2, 14, 30),
            end_dt=_dt(2026, 3, 2, 15, 30),
        )

        self.assertTrue(result.success)
        self.assertFalse(result.requires_decision)
