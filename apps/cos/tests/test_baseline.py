"""
CoS v2 — Phase 0 Baseline Regression Tests

These tests capture the EXISTING behavior of calendar and journal modules
before CoS v2 changes are made. If any of these fail after a CoS v2 change,
it means existing functionality has regressed.

Categories:
1. Calendar: create, duplicate prevention (idempotency + semantic + recurrence),
   conflict detection, protected event rules
2. Journal: create, same-date multiple entries, soft delete lifecycle
3. Feature flag: cos_v2_enabled defaults to False
"""

import datetime as dt
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.calendar_engine.models import CalendarEvent, RecurrenceRule
from apps.calendar_engine.services.calendar_mutation_service import (
    CalendarMutationService,
)
from apps.calendar_engine.services.conflicts import detect_all_conflicts
from apps.journal.models import JournalEntry

User = get_user_model()


def _create_test_user(email="cosbaseline@example.com"):
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
# Feature Flag Baseline
# ──────────────────────────────────────────────────────────


class CosV2FeatureFlagTests(TestCase):
    """Verify the CoS v2 feature flag exists and defaults correctly."""

    def setUp(self):
        self.user = _create_test_user("cosflag@example.com")

    def test_cos_v2_disabled_by_default(self):
        """cos_v2_enabled must default to False for all users."""
        self.assertFalse(self.user.preferences.cos_v2_enabled)

    def test_cos_v2_can_be_enabled(self):
        """cos_v2_enabled can be toggled on."""
        self.user.preferences.cos_v2_enabled = True
        self.user.preferences.save()
        self.user.preferences.refresh_from_db()
        self.assertTrue(self.user.preferences.cos_v2_enabled)


# ──────────────────────────────────────────────────────────
# Calendar Baseline — Create + Duplicate Prevention
# ──────────────────────────────────────────────────────────


class CalendarCreateBaselineTests(TestCase):
    """Baseline: CalendarMutationService.create produces correct events."""

    def setUp(self):
        self.user = _create_test_user("calcreate@example.com")
        self.svc = CalendarMutationService(self.user)
        self.now = timezone.now().replace(second=0, microsecond=0)

    def test_create_basic_event(self):
        """A manual event is created with correct fields."""
        result = self.svc.create(
            title="Team Standup",
            start_dt=self.now,
            end_dt=self.now + dt.timedelta(minutes=30),
        )
        self.assertTrue(result.success)
        self.assertFalse(result.reused)
        self.assertEqual(result.event.title, "Team Standup")
        self.assertEqual(result.event.user, self.user)
        self.assertEqual(result.event.status, CalendarEvent.STATUS_SCHEDULED)

    def test_idempotency_returns_existing(self):
        """Creating with the same idempotency_key returns existing event."""
        key = uuid4().hex
        r1 = self.svc.create(
            title="Meeting",
            start_dt=self.now,
            end_dt=self.now + dt.timedelta(hours=1),
            idempotency_key=key,
        )
        r2 = self.svc.create(
            title="Meeting",
            start_dt=self.now,
            end_dt=self.now + dt.timedelta(hours=1),
            idempotency_key=key,
        )
        self.assertTrue(r2.reused)
        self.assertEqual(r1.event.pk, r2.event.pk)
        # Only 1 event in DB
        self.assertEqual(
            CalendarEvent.objects.filter(user=self.user, title="Meeting").count(),
            1,
        )

    def test_semantic_duplicate_blocked(self):
        """Same title + start_dt (different idempotency key) = semantic dup."""
        start = self.now + dt.timedelta(hours=2)
        r1 = self.svc.create(
            title="Gym Session",
            start_dt=start,
            end_dt=start + dt.timedelta(hours=1),
            force=True,
        )
        r2 = self.svc.create(
            title="Gym Session",
            start_dt=start,
            end_dt=start + dt.timedelta(minutes=45),
            force=True,
        )
        self.assertTrue(r2.reused)
        self.assertEqual(r1.event.pk, r2.event.pk)

    def test_semantic_duplicate_case_insensitive(self):
        """Semantic dup check is case-insensitive."""
        start = self.now + dt.timedelta(hours=3)
        r1 = self.svc.create(
            title="Bible Study",
            start_dt=start,
            end_dt=start + dt.timedelta(hours=1),
            force=True,
        )
        r2 = self.svc.create(
            title="bible study",
            start_dt=start,
            end_dt=start + dt.timedelta(hours=1),
            force=True,
        )
        self.assertTrue(r2.reused)
        self.assertEqual(r1.event.pk, r2.event.pk)

    def test_different_start_creates_new_event(self):
        """Same title but different start_dt = NOT a duplicate."""
        start1 = self.now + dt.timedelta(hours=4)
        start2 = self.now + dt.timedelta(hours=5)
        r1 = self.svc.create(
            title="Workout",
            start_dt=start1,
            end_dt=start1 + dt.timedelta(hours=1),
            force=True,
        )
        r2 = self.svc.create(
            title="Workout",
            start_dt=start2,
            end_dt=start2 + dt.timedelta(hours=1),
            force=True,
        )
        self.assertFalse(r2.reused)
        self.assertNotEqual(r1.event.pk, r2.event.pk)


# ──────────────────────────────────────────────────────────
# Calendar Baseline — Conflict Detection
# ──────────────────────────────────────────────────────────


class CalendarConflictBaselineTests(TestCase):
    """Baseline: conflict detection finds overlapping events."""

    def setUp(self):
        self.user = _create_test_user("calconflict@example.com")
        self.svc = CalendarMutationService(self.user)
        self.base = timezone.now().replace(
            hour=10, minute=0, second=0, microsecond=0
        )

    def test_overlapping_events_detected(self):
        """Two overlapping events are detected as conflicts."""
        # Create first event 10:00-11:00
        self.svc.create(
            title="Meeting A",
            start_dt=self.base,
            end_dt=self.base + dt.timedelta(hours=1),
            force=True,
        )
        # Check conflict for 10:30-11:30
        result = detect_all_conflicts(
            self.user,
            self.base + dt.timedelta(minutes=30),
            self.base + dt.timedelta(hours=1, minutes=30),
        )
        self.assertTrue(result["has_conflict"])
        self.assertEqual(len(result["conflicts"]), 1)

    def test_non_overlapping_no_conflict(self):
        """Non-overlapping events are not conflicts."""
        # Create event 10:00-11:00
        self.svc.create(
            title="Meeting A",
            start_dt=self.base,
            end_dt=self.base + dt.timedelta(hours=1),
            force=True,
        )
        # Check for 11:00-12:00 (adjacent, not overlapping)
        result = detect_all_conflicts(
            self.user,
            self.base + dt.timedelta(hours=1),
            self.base + dt.timedelta(hours=2),
        )
        self.assertFalse(result["has_conflict"])

    def test_create_blocked_by_conflict_without_force(self):
        """Creating an overlapping event without force returns conflict info."""
        # Create first event
        self.svc.create(
            title="Existing Meeting",
            start_dt=self.base,
            end_dt=self.base + dt.timedelta(hours=1),
            force=True,
        )
        # Try to create overlapping event without force
        result = self.svc.create(
            title="New Meeting",
            start_dt=self.base + dt.timedelta(minutes=30),
            end_dt=self.base + dt.timedelta(hours=1, minutes=30),
            force=False,
        )
        # Should fail (not created) due to conflict
        self.assertFalse(result.success)
        self.assertIsNone(result.event)


# ──────────────────────────────────────────────────────────
# Calendar Baseline — Recurrence Duplicate Detection
# ──────────────────────────────────────────────────────────


class CalendarRecurrenceDupBaselineTests(TestCase):
    """Baseline: recurring event duplicate detection works."""

    def setUp(self):
        self.user = _create_test_user("calrecur@example.com")
        self.svc = CalendarMutationService(self.user)
        # Create a weekly recurring event: Monday 6:15 AM
        # Find next Monday
        now = timezone.now().replace(hour=6, minute=15, second=0, microsecond=0)
        days_until_monday = (7 - now.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        self.monday = now + dt.timedelta(days=days_until_monday)
        self.base_event = CalendarEvent.objects.create(
            user=self.user,
            title="Workout",
            start_dt=self.monday,
            end_dt=self.monday + dt.timedelta(hours=1),
            idempotency_key=uuid4().hex,
            status=CalendarEvent.STATUS_SCHEDULED,
        )
        RecurrenceRule.objects.create(
            event=self.base_event,
            frequency=RecurrenceRule.FREQ_WEEKLY,
            byweekday=[0],  # Monday = 0 (ISO)
        )

    def test_recurring_dup_detected(self):
        """Creating 'Workout' on a date covered by recurrence returns existing."""
        # Try to create on the same Monday
        result = self.svc.create(
            title="Workout",
            start_dt=self.monday,
            end_dt=self.monday + dt.timedelta(hours=1),
            force=True,
        )
        self.assertTrue(result.reused)
        self.assertEqual(result.event.pk, self.base_event.pk)

    def test_different_title_not_dup(self):
        """Creating a different-titled event on same Monday is NOT a dup."""
        result = self.svc.create(
            title="Running",
            start_dt=self.monday,
            end_dt=self.monday + dt.timedelta(hours=1),
            force=True,
        )
        self.assertFalse(result.reused)
        self.assertNotEqual(result.event.pk, self.base_event.pk)


# ──────────────────────────────────────────────────────────
# Journal Baseline — Create + Same-Date Behavior
# ──────────────────────────────────────────────────────────


class JournalCreateBaselineTests(TestCase):
    """Baseline: Journal entry creation works correctly."""

    def setUp(self):
        self.user = _create_test_user("journalbase@example.com")
        self.today = dt.date.today()

    def test_create_journal_entry(self):
        """Basic journal entry creation works."""
        entry = JournalEntry.objects.create(
            user=self.user,
            title="Morning Thoughts",
            body="Today I reflected on gratitude.",
            entry_date=self.today,
        )
        self.assertEqual(entry.title, "Morning Thoughts")
        self.assertEqual(entry.user, self.user)
        self.assertIsNotNone(entry.created_at)

    def test_word_count_computed_on_save(self):
        """Word count is auto-computed when saving."""
        entry = JournalEntry.objects.create(
            user=self.user,
            title="Word Count Test",
            body="one two three four five",
            entry_date=self.today,
        )
        self.assertEqual(entry.word_count, 5)

    def test_multiple_entries_same_date_allowed(self):
        """Currently, multiple entries on the same date are allowed (pre-CoS v2)."""
        entry1 = JournalEntry.objects.create(
            user=self.user,
            title="Morning Entry",
            body="Morning thoughts",
            entry_date=self.today,
        )
        entry2 = JournalEntry.objects.create(
            user=self.user,
            title="Evening Entry",
            body="Evening reflections",
            entry_date=self.today,
        )
        self.assertNotEqual(entry1.pk, entry2.pk)
        count = JournalEntry.objects.filter(
            user=self.user, entry_date=self.today
        ).count()
        self.assertEqual(count, 2)

    def test_soft_delete_lifecycle(self):
        """Journal entries use soft delete, not hard delete."""
        entry = JournalEntry.objects.create(
            user=self.user,
            title="To Delete",
            body="This will be soft-deleted",
            entry_date=self.today,
        )
        pk = entry.pk
        entry.soft_delete()
        # Should not appear in default queryset
        self.assertFalse(JournalEntry.objects.filter(pk=pk).exists())
        # But should exist in all_objects
        self.assertTrue(JournalEntry.all_objects.filter(pk=pk).exists())

    def test_entry_auto_title_on_empty(self):
        """If title is empty, it auto-generates from entry_date on save."""
        entry = JournalEntry(
            user=self.user,
            title="",
            body="No title provided",
            entry_date=self.today,
        )
        entry.save()
        # Title should be auto-generated (non-empty)
        self.assertTrue(len(entry.title) > 0)
