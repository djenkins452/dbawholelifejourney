"""
CoS v2 — Phase 2 Tests: CalendarCosActions + Conflict Resolution Options

Tests:
1. CalendarCosActions CRUD: create, retrieve, update, delete, summarise
2. Duplicate detection via check_duplicate (semantic + recurrence)
3. Conflict detection via check_conflicts with resolution options
4. Resolution option generator: shift, next_available, shorten, force
5. Reflection hook: capture_reflection_hook
"""

import datetime as dt
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils import timezone

from apps.calendar_engine.models import CalendarEvent, RecurrenceRule
from apps.calendar_engine.services.calendar_mutation_service import (
    CalendarMutationService,
)
from apps.cos.actions.calendar_actions import (
    CalendarCosActions,
    generate_resolution_options,
)
from apps.cos.contracts import ActionResult, ConflictCheck, DuplicateCheck
from apps.cos.models import CosReflection

User = get_user_model()


def _create_test_user(email="calcosactions@example.com"):
    from apps.users.models import TermsAcceptance

    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


def _ce(user, title, start_dt, end_dt, **kwargs):
    """Helper: create a CalendarEvent."""
    kwargs.setdefault("idempotency_key", uuid4().hex)
    kwargs.setdefault("status", CalendarEvent.STATUS_SCHEDULED)
    return CalendarEvent.objects.create(
        user=user, title=title, start_dt=start_dt, end_dt=end_dt, **kwargs
    )


# ──────────────────────────────────────────────────────────
# CalendarCosActions — Basic CRUD
# ──────────────────────────────────────────────────────────


class CalendarCosActionsCreateTests(TestCase):
    """Test CalendarCosActions.create()."""

    def setUp(self):
        self.user = _create_test_user("calcreate2@example.com")
        self.actions = CalendarCosActions(user=self.user)
        self.now = timezone.now().replace(second=0, microsecond=0)

    def test_module_name(self):
        self.assertEqual(self.actions.module_name, "calendar")

    def test_create_basic(self):
        """Create returns ActionResult with entity."""
        result = self.actions.create(
            title="Team Meeting",
            start_dt=self.now + dt.timedelta(hours=5),
            end_dt=self.now + dt.timedelta(hours=6),
            force=True,
        )
        self.assertIsInstance(result, ActionResult)
        self.assertTrue(result.success)
        self.assertIsNotNone(result.entity)
        self.assertEqual(result.entity.title, "Team Meeting")

    def test_create_duplicate_returns_reused(self):
        """Creating a duplicate returns reused=True."""
        start = self.now + dt.timedelta(hours=7)
        r1 = self.actions.create(
            title="Standup",
            start_dt=start,
            end_dt=start + dt.timedelta(minutes=30),
            force=True,
        )
        r2 = self.actions.create(
            title="Standup",
            start_dt=start,
            end_dt=start + dt.timedelta(minutes=30),
            force=True,
        )
        self.assertTrue(r2.reused)
        self.assertEqual(r1.entity_id, r2.entity_id)

    def test_create_conflict_returns_decision(self):
        """Creating with conflict returns requires_decision + options."""
        start = self.now + dt.timedelta(hours=10)
        # Create blocking event
        _ce(self.user, "Existing Meeting", start, start + dt.timedelta(hours=1))
        # Try to create overlapping
        result = self.actions.create(
            title="New Meeting",
            start_dt=start + dt.timedelta(minutes=30),
            end_dt=start + dt.timedelta(hours=1, minutes=30),
            force=False,
        )
        self.assertFalse(result.success)
        self.assertTrue(result.requires_decision)
        self.assertIsNotNone(result.decision_options)
        self.assertTrue(len(result.decision_options) > 0)
        # Should have at least force_create option
        actions = [o["action"] for o in result.decision_options]
        self.assertIn("force_create", actions)


class CalendarCosActionsRetrieveTests(TestCase):
    """Test CalendarCosActions.retrieve()."""

    def setUp(self):
        self.user = _create_test_user("calretrieve@example.com")
        self.actions = CalendarCosActions(user=self.user)
        self.now = timezone.now().replace(second=0, microsecond=0)

    def test_retrieve_existing(self):
        event = _ce(
            self.user, "My Event",
            self.now, self.now + dt.timedelta(hours=1),
        )
        result = self.actions.retrieve(entity_id=event.pk)
        self.assertTrue(result.success)
        self.assertEqual(result.entity_id, event.pk)

    def test_retrieve_nonexistent(self):
        result = self.actions.retrieve(entity_id=999999)
        self.assertFalse(result.success)
        self.assertIn("not found", result.error)

    def test_retrieve_deleted_event_fails(self):
        """Deleted events are not retrievable."""
        event = _ce(
            self.user, "Deleted Event",
            self.now, self.now + dt.timedelta(hours=1),
        )
        event.soft_delete()
        result = self.actions.retrieve(entity_id=event.pk)
        self.assertFalse(result.success)


class CalendarCosActionsUpdateTests(TestCase):
    """Test CalendarCosActions.update()."""

    def setUp(self):
        self.user = _create_test_user("calupdate@example.com")
        self.actions = CalendarCosActions(user=self.user)
        self.now = timezone.now().replace(second=0, microsecond=0)

    def test_update_title(self):
        event = _ce(
            self.user, "Original Title",
            self.now + dt.timedelta(hours=12),
            self.now + dt.timedelta(hours=13),
        )
        result = self.actions.update(
            entity_id=event.pk, title="Updated Title"
        )
        self.assertTrue(result.success)
        event.refresh_from_db()
        self.assertEqual(event.title, "Updated Title")

    def test_update_nonexistent(self):
        result = self.actions.update(entity_id=999999, title="No Event")
        self.assertFalse(result.success)


class CalendarCosActionsDeleteTests(TestCase):
    """Test CalendarCosActions.delete()."""

    def setUp(self):
        self.user = _create_test_user("caldelete@example.com")
        self.actions = CalendarCosActions(user=self.user)
        self.now = timezone.now().replace(second=0, microsecond=0)

    def test_delete_event(self):
        event = _ce(
            self.user, "To Delete",
            self.now, self.now + dt.timedelta(hours=1),
        )
        result = self.actions.delete(entity_id=event.pk)
        self.assertTrue(result.success)
        event.refresh_from_db()
        self.assertEqual(event.status, CalendarEvent.STATUS_CANCELED)

    def test_delete_nonexistent(self):
        result = self.actions.delete(entity_id=999999)
        self.assertFalse(result.success)


class CalendarCosActionsSummariseTests(TestCase):
    """Test CalendarCosActions.summarise()."""

    def setUp(self):
        self.user = _create_test_user("calsum@example.com")
        self.actions = CalendarCosActions(user=self.user)
        self.now = timezone.now().replace(second=0, microsecond=0)

    def test_summarise_today(self):
        """Summarise returns today's events."""
        today_start = self.now.replace(hour=14, minute=0)
        _ce(self.user, "Afternoon Meeting", today_start, today_start + dt.timedelta(hours=1))
        result = self.actions.summarise(date=self.now.date())
        self.assertTrue(result.success)
        self.assertGreaterEqual(result.metadata["event_count"], 1)

    def test_summarise_empty_day(self):
        """Summarise on a day with no events returns empty."""
        future = (self.now + dt.timedelta(days=30)).date()
        result = self.actions.summarise(date=future)
        self.assertTrue(result.success)
        self.assertEqual(result.metadata["event_count"], 0)


# ──────────────────────────────────────────────────────────
# Duplicate Detection
# ──────────────────────────────────────────────────────────


class CalendarDuplicateCheckTests(TestCase):
    """Test CalendarCosActions.check_duplicate()."""

    def setUp(self):
        self.user = _create_test_user("caldup@example.com")
        self.actions = CalendarCosActions(user=self.user)
        self.now = timezone.now().replace(second=0, microsecond=0)

    def test_no_duplicate(self):
        result = self.actions.check_duplicate(
            title="Brand New Event",
            start_dt=self.now + dt.timedelta(hours=20),
        )
        self.assertIsInstance(result, DuplicateCheck)
        self.assertFalse(result.is_duplicate)

    def test_semantic_duplicate(self):
        start = self.now + dt.timedelta(hours=21)
        _ce(self.user, "Existing Event", start, start + dt.timedelta(hours=1))
        result = self.actions.check_duplicate(
            title="Existing Event", start_dt=start,
        )
        self.assertTrue(result.is_duplicate)
        self.assertEqual(result.match_type, "semantic")

    def test_recurrence_duplicate(self):
        """Recurrence dup detected for matching title + occurrence time."""
        now = timezone.now().replace(hour=6, minute=15, second=0, microsecond=0)
        days_until_monday = (7 - now.weekday()) % 7 or 7
        monday = now + dt.timedelta(days=days_until_monday)
        event = _ce(self.user, "Workout", monday, monday + dt.timedelta(hours=1))
        RecurrenceRule.objects.create(
            event=event,
            frequency=RecurrenceRule.FREQ_WEEKLY,
            byweekday=[1],  # ISO Monday = 1
        )
        result = self.actions.check_duplicate(
            title="Workout", start_dt=monday,
        )
        # The semantic check will catch this first since it's the same start_dt
        self.assertTrue(result.is_duplicate)

    def test_missing_args_returns_no_dup(self):
        """Missing title or start_dt returns no duplicate."""
        result = self.actions.check_duplicate(title="No Time")
        self.assertFalse(result.is_duplicate)


# ──────────────────────────────────────────────────────────
# Conflict Detection + Resolution Options
# ──────────────────────────────────────────────────────────


class CalendarConflictCheckTests(TestCase):
    """Test CalendarCosActions.check_conflicts()."""

    def setUp(self):
        self.user = _create_test_user("calconf@example.com")
        self.actions = CalendarCosActions(user=self.user)
        self.base = timezone.now().replace(
            hour=10, minute=0, second=0, microsecond=0
        ) + dt.timedelta(days=1)  # Tomorrow to avoid edge cases

    def test_no_conflict(self):
        result = self.actions.check_conflicts(
            start_dt=self.base,
            end_dt=self.base + dt.timedelta(hours=1),
        )
        self.assertIsInstance(result, ConflictCheck)
        self.assertFalse(result.has_conflict)

    def test_conflict_detected_with_resolutions(self):
        """Conflict returns resolution options."""
        _ce(self.user, "Existing", self.base, self.base + dt.timedelta(hours=1))
        result = self.actions.check_conflicts(
            start_dt=self.base + dt.timedelta(minutes=30),
            end_dt=self.base + dt.timedelta(hours=1, minutes=30),
        )
        self.assertTrue(result.has_conflict)
        self.assertTrue(len(result.conflicts) > 0)
        self.assertTrue(len(result.suggested_resolutions) > 0)

    def test_resolution_always_includes_force(self):
        """Resolution options always include force_create."""
        _ce(self.user, "Blocker", self.base, self.base + dt.timedelta(hours=1))
        result = self.actions.check_conflicts(
            start_dt=self.base + dt.timedelta(minutes=30),
            end_dt=self.base + dt.timedelta(hours=1, minutes=30),
        )
        actions = [o["action"] for o in result.suggested_resolutions]
        self.assertIn("force_create", actions)

    def test_missing_args_returns_no_conflict(self):
        result = self.actions.check_conflicts()
        self.assertFalse(result.has_conflict)


# ──────────────────────────────────────────────────────────
# Resolution Option Generator — Detailed Tests
# ──────────────────────────────────────────────────────────


class ResolutionOptionGeneratorTests(TestCase):
    """Test generate_resolution_options() in isolation."""

    def setUp(self):
        self.user = _create_test_user("resopt@example.com")
        self.base = timezone.now().replace(
            hour=10, minute=0, second=0, microsecond=0
        ) + dt.timedelta(days=1)

    def test_shift_after_conflict_offered(self):
        """Shift-after-conflict option offered when slot after conflict is free."""
        conflict_start = self.base
        conflict_end = self.base + dt.timedelta(hours=1)
        conflicts = [{
            "id": 1,
            "title": "Existing",
            "start_dt": conflict_start.isoformat(),
            "end_dt": conflict_end.isoformat(),
            "is_protected": False,
        }]
        # Propose: 10:30 - 11:30 (overlaps existing 10:00-11:00)
        proposed_start = self.base + dt.timedelta(minutes=30)
        proposed_end = self.base + dt.timedelta(hours=1, minutes=30)

        options = generate_resolution_options(
            self.user, proposed_start, proposed_end, conflicts, "C",
        )
        actions = [o["action"] for o in options]
        self.assertIn("shift_after_conflict", actions)
        # The shifted slot should start at 11:00 (when conflict ends)
        shift_opt = next(o for o in options if o["action"] == "shift_after_conflict")
        self.assertEqual(shift_opt["new_start_dt"], conflict_end.isoformat())

    def test_shorten_option_offered(self):
        """Shorten option offered when there's meaningful time before conflict."""
        # Existing event: 10:30 - 11:30
        conflict_start = self.base + dt.timedelta(minutes=30)
        conflict_end = self.base + dt.timedelta(hours=1, minutes=30)
        conflicts = [{
            "id": 1,
            "title": "Existing",
            "start_dt": conflict_start.isoformat(),
            "end_dt": conflict_end.isoformat(),
            "is_protected": False,
        }]
        # Propose: 10:00 - 11:00 (overlaps at 10:30)
        proposed_start = self.base
        proposed_end = self.base + dt.timedelta(hours=1)

        options = generate_resolution_options(
            self.user, proposed_start, proposed_end, conflicts, "C",
        )
        actions = [o["action"] for o in options]
        self.assertIn("shorten", actions)
        # Shortened should end at 10:30 (30 min)
        shorten_opt = next(o for o in options if o["action"] == "shorten")
        self.assertEqual(shorten_opt["new_end_dt"], conflict_start.isoformat())

    def test_shorten_not_offered_when_too_short(self):
        """Shorten not offered when less than 15 min before conflict."""
        # Existing: 10:10 - 11:00
        conflict_start = self.base + dt.timedelta(minutes=10)
        conflicts = [{
            "id": 1,
            "title": "Existing",
            "start_dt": conflict_start.isoformat(),
            "end_dt": (self.base + dt.timedelta(hours=1)).isoformat(),
            "is_protected": False,
        }]
        # Propose: 10:00 - 11:00 (only 10 min before conflict)
        options = generate_resolution_options(
            self.user, self.base,
            self.base + dt.timedelta(hours=1), conflicts, "C",
        )
        actions = [o["action"] for o in options]
        self.assertNotIn("shorten", actions)

    def test_force_create_always_present(self):
        """force_create is always the last option."""
        conflicts = [{
            "id": 1,
            "title": "Existing",
            "start_dt": self.base.isoformat(),
            "end_dt": (self.base + dt.timedelta(hours=1)).isoformat(),
            "is_protected": True,
        }]
        options = generate_resolution_options(
            self.user, self.base,
            self.base + dt.timedelta(hours=1), conflicts, "A",
        )
        self.assertEqual(options[-1]["action"], "force_create")

    def test_all_options_have_required_fields(self):
        """Every option has action, label, description."""
        conflicts = [{
            "id": 1,
            "title": "Existing",
            "start_dt": self.base.isoformat(),
            "end_dt": (self.base + dt.timedelta(hours=1)).isoformat(),
            "is_protected": False,
        }]
        options = generate_resolution_options(
            self.user,
            self.base + dt.timedelta(minutes=30),
            self.base + dt.timedelta(hours=1, minutes=30),
            conflicts,
            "C",
        )
        for opt in options:
            self.assertIn("action", opt)
            self.assertIn("label", opt)
            self.assertIn("description", opt)


# ──────────────────────────────────────────────────────────
# Reflection Hook
# ──────────────────────────────────────────────────────────


class CalendarReflectionHookTests(TestCase):
    """Test CalendarCosActions.capture_reflection_hook()."""

    def setUp(self):
        self.user = _create_test_user("calrefl@example.com")
        self.actions = CalendarCosActions(user=self.user)
        self.now = timezone.now().replace(second=0, microsecond=0)
        self.event = _ce(
            self.user, "Workout",
            self.now, self.now + dt.timedelta(hours=1),
        )

    def test_capture_reflection(self):
        """Reflection is stored and attached to the event."""
        success = self.actions.capture_reflection_hook(
            entity_id=self.event.pk,
            reflection_text="Great workout today, felt strong.",
            activity_type="workout",
            sentiment="positive",
        )
        self.assertTrue(success)
        ct = ContentType.objects.get_for_model(CalendarEvent)
        reflection = CosReflection.objects.get(
            user=self.user,
            content_type=ct,
            object_id=self.event.pk,
        )
        self.assertEqual(reflection.text, "Great workout today, felt strong.")
        self.assertEqual(reflection.sentiment, "positive")
        self.assertEqual(reflection.activity_type, "workout")

    def test_capture_reflection_nonexistent_event(self):
        """Reflection capture for nonexistent event returns False."""
        success = self.actions.capture_reflection_hook(
            entity_id=999999,
            reflection_text="Should fail",
        )
        self.assertFalse(success)

    def test_supports_reflections(self):
        self.assertTrue(self.actions.supports_reflections())

    def test_supports_proactive_prompts(self):
        self.assertTrue(self.actions.supports_proactive_prompts())
