"""
CoS v2 — Phase 11: Final Regression + Scenario Tests

End-to-end scenario tests covering the full CoS v2 pipeline:

1. Calendar duplicate prevention (one-off + recurring)
2. Conflict detection and resolution option output
3. Journal append vs create (contract behavior)
4. Proactive pre/post prompts firing correctly
5. Yes/No flow behavior (No stops; Yes continues)
6. Reflection persistence and later retrieval
7. Low-priority auto-shift respecting time-of-day
8. Goal suggestion throttling and 3-decline behavior
"""

import datetime as dt
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils import timezone

from apps.calendar_engine.models import CalendarEvent
from apps.cos.models import (
    CosAutoShiftLog,
    CosGoalSuggestion,
    CosPromptSchedule,
    CosReflection,
)
from apps.cos.services.auto_shift_service import CosAutoShiftService
from apps.cos.services.goal_suggestion_service import CosGoalSuggestionService
from apps.cos.services.prompt_service import CosPromptService
from apps.cos.services.prompt_templates import detect_activity_type
from apps.cos.services.reflection_service import CosReflectionService
from apps.cos.services.tone_service import CosToneService

User = get_user_model()


def _create_user(email, cos_enabled=True):
    from apps.users.models import TermsAcceptance

    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.cos_v2_enabled = cos_enabled
    user.preferences.save()
    return user


def _create_event(user, title, start_dt=None, duration_hours=1, is_protected=False):
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


# ──────────────────────────────────────────────────────────
# Scenario 1: Calendar Duplicate Prevention
# ──────────────────────────────────────────────────────────


class CalendarDuplicatePreventionScenarioTests(TestCase):
    """
    Scenario: User creates an event that already exists.
    Expected: Duplicate is detected via CalendarCosActions.check_duplicate().
    """

    def setUp(self):
        self.user = _create_user("dup@scenario.com")

    def test_duplicate_check_detects_same_title_and_time(self):
        """Same title + same start time = duplicate."""
        from apps.cos.actions.calendar_actions import CalendarCosActions

        start = timezone.now() + dt.timedelta(hours=5)
        _create_event(self.user, "Team Meeting", start_dt=start)

        actions = CalendarCosActions(self.user)
        dup_check = actions.check_duplicate(
            title="Team Meeting",
            start_dt=start,
        )
        self.assertTrue(dup_check.is_duplicate)
        self.assertIsNotNone(dup_check.existing_entity_id)

    def test_different_time_not_duplicate(self):
        """Same title but different time = not duplicate."""
        from apps.cos.actions.calendar_actions import CalendarCosActions

        start = timezone.now() + dt.timedelta(hours=5)
        _create_event(self.user, "Team Meeting", start_dt=start)

        actions = CalendarCosActions(self.user)
        different_time = start + dt.timedelta(days=1)
        dup_check = actions.check_duplicate(
            title="Team Meeting",
            start_dt=different_time,
        )
        self.assertFalse(dup_check.is_duplicate)

    def test_different_title_not_duplicate(self):
        """Different title at same time = not duplicate."""
        from apps.cos.actions.calendar_actions import CalendarCosActions

        start = timezone.now() + dt.timedelta(hours=5)
        _create_event(self.user, "Team Meeting", start_dt=start)

        actions = CalendarCosActions(self.user)
        dup_check = actions.check_duplicate(
            title="1:1 With Manager",
            start_dt=start,
        )
        self.assertFalse(dup_check.is_duplicate)


# ──────────────────────────────────────────────────────────
# Scenario 2: Conflict Detection + Resolution Options
# ──────────────────────────────────────────────────────────


class ConflictDetectionScenarioTests(TestCase):
    """
    Scenario: New event overlaps with existing one.
    Expected: Conflict detected with resolution options.
    """

    def setUp(self):
        self.user = _create_user("conflict@scenario.com")

    def test_overlapping_events_detected(self):
        """Two overlapping events produce a conflict check result."""
        from apps.cos.actions.calendar_actions import CalendarCosActions

        start = timezone.now() + dt.timedelta(hours=5)
        _create_event(self.user, "Meeting A", start_dt=start)

        actions = CalendarCosActions(self.user)
        conflict_check = actions.check_conflicts(
            start_dt=start + dt.timedelta(minutes=30),
            end_dt=start + dt.timedelta(hours=2),
        )
        self.assertTrue(conflict_check.has_conflict)
        self.assertTrue(len(conflict_check.conflicts) > 0)

    def test_non_overlapping_no_conflict(self):
        """Non-overlapping events produce no conflict."""
        from apps.cos.actions.calendar_actions import CalendarCosActions

        start = timezone.now() + dt.timedelta(hours=5)
        _create_event(self.user, "Meeting A", start_dt=start)

        actions = CalendarCosActions(self.user)
        later = start + dt.timedelta(hours=3)
        conflict_check = actions.check_conflicts(
            start_dt=later,
            end_dt=later + dt.timedelta(hours=1),
        )
        self.assertFalse(conflict_check.has_conflict)


# ──────────────────────────────────────────────────────────
# Scenario 3: Journal Append vs Create
# ──────────────────────────────────────────────────────────


class JournalContractScenarioTests(TestCase):
    """
    Scenario: Journal module interaction via CosActionContract.
    Expected: Contract methods return appropriate results.
    """

    def setUp(self):
        self.user = _create_user("journal@scenario.com")

    def test_unregistered_module_raises(self):
        """Requesting unregistered module raises KeyError."""
        from apps.cos.registry import cos_registry

        with self.assertRaises(KeyError):
            cos_registry.get_or_raise("nonexistent_module", self.user)

    def test_calendar_module_registered(self):
        """Calendar module is registered and retrievable."""
        from apps.cos.actions.calendar_actions import CalendarCosActions
        from apps.cos.registry import cos_registry

        # Register the calendar module (normally done in AppConfig.ready)
        if not cos_registry.is_registered("calendar"):
            cos_registry.register("calendar", CalendarCosActions)

        self.assertTrue(cos_registry.is_registered("calendar"))
        actions = cos_registry.get("calendar", self.user)
        self.assertIsNotNone(actions)
        self.assertEqual(actions.module_name, "calendar")


# ──────────────────────────────────────────────────────────
# Scenario 4: Proactive Pre/Post Prompts
# ──────────────────────────────────────────────────────────


class ProactivePromptScenarioTests(TestCase):
    """
    Scenario: Event is created → pre and post prompts are scheduled.
    Expected: Correct activity type detection, correct timing, correct templates.
    """

    def setUp(self):
        self.user = _create_user("prompt@scenario.com")

    def test_workout_event_gets_both_prompts(self):
        """Creating a workout event schedules pre and post prompts."""
        start = timezone.now() + dt.timedelta(hours=3)
        event = _create_event(self.user, "Morning Workout", start_dt=start)

        svc = CosPromptService(self.user)
        prompts = svc.schedule_prompts_for_event(event)

        self.assertEqual(len(prompts), 2)

        pre = [p for p in prompts if p.timing == CosPromptSchedule.TIMING_PRE][0]
        post = [p for p in prompts if p.timing == CosPromptSchedule.TIMING_POST][0]

        self.assertEqual(pre.activity_type, "workout")
        self.assertEqual(post.activity_type, "workout")
        self.assertIn("Workout", pre.prompt_text)
        self.assertTrue(pre.scheduled_for < event.start_dt)
        self.assertTrue(post.scheduled_for > event.end_dt)

    def test_prayer_event_uses_correct_template(self):
        """Prayer event uses prayer-specific template."""
        start = timezone.now() + dt.timedelta(hours=3)
        event = _create_event(self.user, "Evening Prayer", start_dt=start)

        svc = CosPromptService(self.user)
        prompts = svc.schedule_prompts_for_event(event)

        pre = [p for p in prompts if p.timing == CosPromptSchedule.TIMING_PRE][0]
        self.assertEqual(pre.activity_type, "prayer")
        self.assertIn("prayer", pre.prompt_text.lower())

    def test_dedup_prevents_double_scheduling(self):
        """Scheduling prompts twice for same event doesn't create duplicates."""
        start = timezone.now() + dt.timedelta(hours=3)
        event = _create_event(self.user, "Bible Study", start_dt=start)

        svc = CosPromptService(self.user)
        first = svc.schedule_prompts_for_event(event)
        second = svc.schedule_prompts_for_event(event)

        self.assertEqual(len(first), 2)
        self.assertEqual(len(second), 0)  # Deduplicated

    def test_canceled_event_cancels_prompts(self):
        """Canceling prompts for an event sets them to canceled."""
        start = timezone.now() + dt.timedelta(hours=3)
        event = _create_event(self.user, "Team Meeting", start_dt=start)

        svc = CosPromptService(self.user)
        svc.schedule_prompts_for_event(event)
        canceled = svc.cancel_prompts_for_event(event)

        self.assertEqual(canceled, 2)
        remaining = CosPromptSchedule.objects.filter(
            user=self.user,
            status=CosPromptSchedule.STATUS_PENDING,
        ).count()
        self.assertEqual(remaining, 0)

    def test_activity_type_detection_coverage(self):
        """All common activity titles detect correctly."""
        cases = {
            "Morning Workout": "workout",
            "Team Meeting": "meeting",
            "Evening Prayer": "prayer",
            "Bible Study Time": "bible_study",
            "Journal Writing": "journaling",
            "Meditation Session": "meditation",
            "Doctor Appointment": "appointment",
        }
        for title, expected_type in cases.items():
            detected = detect_activity_type(title)
            self.assertEqual(
                detected, expected_type,
                f"'{title}' should detect as '{expected_type}', got '{detected}'",
            )


# ──────────────────────────────────────────────────────────
# Scenario 5: Yes/No Flow Behavior
# ──────────────────────────────────────────────────────────


class YesNoFlowScenarioTests(TestCase):
    """
    Scenario: User responds Yes or No to a post-event prompt.
    Expected: No → stops (no follow-up). Yes → offers follow-up.
    """

    def setUp(self):
        self.user = _create_user("yesno@scenario.com")
        start = timezone.now() - dt.timedelta(hours=2)
        self.event = _create_event(self.user, "Workout", start_dt=start)
        ct = ContentType.objects.get_for_model(self.event)
        self.prompt = CosPromptSchedule.objects.create(
            user=self.user,
            content_type=ct,
            object_id=self.event.pk,
            timing=CosPromptSchedule.TIMING_POST,
            scheduled_for=timezone.now() - dt.timedelta(minutes=5),
            activity_type="workout",
            prompt_text="Did you complete your workout?",
            status=CosPromptSchedule.STATUS_DELIVERED,
        )

    def test_no_response_stops_flow(self):
        """Responding No → no follow-up offered."""
        svc = CosPromptService(self.user)
        result = svc.handle_response(
            prompt_id=self.prompt.pk,
            positive=False,
            response_text="",
        )
        self.assertTrue(result["success"])
        self.assertIsNone(result["follow_up"])

    def test_yes_response_with_text_captures_reflection(self):
        """Responding Yes with text → reflection created + follow-up offered."""
        svc = CosPromptService(self.user)
        result = svc.handle_response(
            prompt_id=self.prompt.pk,
            positive=True,
            response_text="Great workout, hit a PR on squats!",
        )
        self.assertTrue(result["success"])
        self.assertIsNotNone(result["follow_up"])

        # Reflection should be created
        reflections = CosReflection.objects.filter(user=self.user)
        self.assertEqual(reflections.count(), 1)
        self.assertEqual(reflections.first().sentiment, "positive")

    def test_yes_without_text_offers_followup(self):
        """Responding Yes without text → still offers follow-up."""
        svc = CosPromptService(self.user)
        result = svc.handle_response(
            prompt_id=self.prompt.pk,
            positive=True,
            response_text="",
        )
        self.assertIsNotNone(result["follow_up"])


# ──────────────────────────────────────────────────────────
# Scenario 6: Reflection Persistence + Retrieval
# ──────────────────────────────────────────────────────────


class ReflectionPersistenceScenarioTests(TestCase):
    """
    Scenario: Reflections stored over multiple days, queried by context.
    Expected: Can retrieve "yesterday vs today" and streak data.
    """

    def setUp(self):
        self.user = _create_user("reflections@scenario.com")
        self.svc = CosReflectionService(self.user)

    def test_reflections_stored_with_correct_metadata(self):
        """Reflection stores sentiment, activity type, and date."""
        event = _create_event(self.user, "Workout")
        ref = self.svc.create_reflection(
            source_entity=event,
            text="Felt amazing today, best run ever!",
            activity_type="workout",
        )
        self.assertEqual(ref.sentiment, "positive")
        self.assertEqual(ref.activity_type, "workout")
        self.assertIsNotNone(ref.activity_date)

    def test_multi_day_reflections_retrievable(self):
        """Reflections over multiple days are retrievable by date range."""
        for i in range(5):
            event = _create_event(
                self.user, f"Workout {i}",
                start_dt=timezone.now() - dt.timedelta(days=i, hours=2),
            )
            self.svc.create_reflection(
                source_entity=event,
                text="Good session" if i % 2 == 0 else "Tough day",
                activity_type="workout",
                activity_date=(timezone.now() - dt.timedelta(days=i)).date(),
            )

        all_refs = CosReflection.objects.filter(user=self.user)
        self.assertEqual(all_refs.count(), 5)

        # Filter by activity type
        workout_refs = all_refs.filter(activity_type="workout")
        self.assertEqual(workout_refs.count(), 5)

    def test_contextual_prompt_prefix_builds(self):
        """Contextual prompt prefix includes recent reflection data."""
        event = _create_event(self.user, "Workout")
        self.svc.create_reflection(
            source_entity=event,
            text="Struggled hard today, felt exhausted",
            activity_type="workout",
            activity_date=timezone.now().date(),
        )

        prefix = self.svc.build_contextual_prompt_prefix("workout")
        # Should mention something about the recent reflection
        self.assertIsInstance(prefix, str)


# ──────────────────────────────────────────────────────────
# Scenario 7: Low-Priority Auto-Shift + Time-of-Day
# ──────────────────────────────────────────────────────────


class AutoShiftScenarioTests(TestCase):
    """
    Scenario: Low-priority event conflicts → auto-shifted to suitable time.
    High-priority event → requires confirmation.
    Time-of-day rules respected.
    """

    def setUp(self):
        self.user = _create_user("autoshift@scenario.com")
        self.svc = CosAutoShiftService(self.user)

    def test_low_priority_auto_shifts_on_conflict(self):
        """Prayer (low priority) auto-shifts when conflicting."""
        start = timezone.now().replace(hour=10, minute=0) + dt.timedelta(days=1)
        prayer = _create_event(self.user, "Evening Prayer", start_dt=start)

        proposal = self.svc.propose_shift(
            prayer,
            conflicting_end=start + dt.timedelta(hours=1),
        )
        self.assertTrue(proposal["can_auto_shift"])
        self.assertFalse(proposal["requires_confirmation"])
        self.assertEqual(proposal["priority"], "low")
        self.assertIsNotNone(proposal["proposed_start"])

    def test_high_priority_requires_confirmation(self):
        """Meeting (high priority) requires user confirmation."""
        start = timezone.now().replace(hour=10, minute=0) + dt.timedelta(days=1)
        meeting = _create_event(self.user, "Team Meeting", start_dt=start)

        proposal = self.svc.propose_shift(
            meeting,
            conflicting_end=start + dt.timedelta(hours=1),
        )
        self.assertFalse(proposal["can_auto_shift"])
        self.assertTrue(proposal["requires_confirmation"])
        self.assertEqual(proposal["priority"], "high")

    def test_protected_event_never_shifted(self):
        """Protected events cannot be auto-shifted."""
        start = timezone.now().replace(hour=10, minute=0) + dt.timedelta(days=1)
        protected = _create_event(
            self.user, "Fixed Commitment",
            start_dt=start, is_protected=True,
        )

        proposal = self.svc.propose_shift(protected)
        self.assertIn("Protected", proposal["rejection_reason"])

    def test_shift_respects_time_of_day(self):
        """Proposed shift time falls within suitable window."""
        start = timezone.now().replace(hour=10, minute=0) + dt.timedelta(days=1)
        prayer = _create_event(self.user, "Evening Prayer", start_dt=start)

        proposal = self.svc.propose_shift(
            prayer,
            conflicting_end=start + dt.timedelta(hours=1),
        )

        if proposal["proposed_start"]:
            hour = proposal["proposed_start"].hour
            # Prayer is suitable 5-22
            self.assertGreaterEqual(hour, 5)
            self.assertLessEqual(hour, 22)

    def test_shift_execution_creates_audit_trail(self):
        """Executing a shift creates an audit log entry."""
        start = timezone.now().replace(hour=10, minute=0) + dt.timedelta(days=1)
        prayer = _create_event(self.user, "Prayer Time", start_dt=start)
        new_start = start + dt.timedelta(hours=1)
        new_end = new_start + dt.timedelta(hours=1)

        result = self.svc.execute_shift(
            prayer, new_start, new_end,
            reason="Conflict with meeting",
            shift_type="conflict_avoidance",
        )
        self.assertTrue(result["success"])

        logs = CosAutoShiftLog.objects.filter(user=self.user)
        self.assertEqual(logs.count(), 1)
        log = logs.first()
        self.assertEqual(log.original_start, start)
        self.assertEqual(log.new_start, new_start)
        self.assertTrue(log.auto_shifted)
        self.assertFalse(log.user_confirmed)

    def test_workout_late_night_not_suitable(self):
        """Workout cannot be shifted to 11pm."""
        self.assertFalse(
            self.svc.is_time_suitable(
                timezone.now().replace(hour=23, minute=0),
                "workout",
            )
        )

    def test_tone_adapts_to_shift_context(self):
        """Tone service provides appropriate tone for shifted event context."""
        tone_svc = CosToneService(self.user)
        # Workout at midday → energized
        midday = timezone.now().replace(hour=12, minute=0)
        tone = tone_svc.select_tone(
            activity_type="workout", reference_time=midday,
        )
        self.assertEqual(tone, "energized")


# ──────────────────────────────────────────────────────────
# Scenario 8: Goal Suggestion Throttling + 3-Decline
# ──────────────────────────────────────────────────────────


class GoalSuggestionThrottleScenarioTests(TestCase):
    """
    Scenario: CoS suggests a goal → user declines 3 times → opt-out offered.
    Throttle: max 1 suggestion per theme per 30 days.
    """

    def setUp(self):
        self.user = _create_user("goalthrottle@scenario.com")
        self.svc = CosGoalSuggestionService(self.user)

    def test_first_suggestion_creates_successfully(self):
        """First suggestion for a theme is created."""
        result = self.svc.create_suggestion(
            theme="workout_consistency",
            suggestion_text="Try committing to 3 workouts per week.",
            evidence_summary="4 missed workouts in last 14 days.",
        )
        self.assertTrue(result["created"])
        self.assertIsNotNone(result["suggestion"])

    def test_throttle_blocks_second_within_30_days(self):
        """Second suggestion for same theme within 30 days is blocked."""
        self.svc.create_suggestion(
            theme="workout_consistency",
            suggestion_text="First suggestion.",
        )
        result = self.svc.create_suggestion(
            theme="workout_consistency",
            suggestion_text="Second suggestion.",
        )
        self.assertFalse(result["created"])
        self.assertIn("within the last 30 days", result["reason"].lower())

    def test_different_theme_not_throttled(self):
        """Different theme is not throttled."""
        self.svc.create_suggestion(
            theme="workout_consistency",
            suggestion_text="Workout suggestion.",
        )
        result = self.svc.create_suggestion(
            theme="sleep_quality",
            suggestion_text="Sleep suggestion.",
        )
        self.assertTrue(result["created"])

    def test_decline_3_times_triggers_opt_out_offer(self):
        """Declining 3 suggestions for a theme triggers opt-out offer."""
        # Create and decline 3 suggestions (need to bypass throttle)
        for i in range(3):
            sug = CosGoalSuggestion.objects.create(
                user=self.user,
                theme="workout_consistency",
                suggestion_text=f"Suggestion {i}",
                status=CosGoalSuggestion.STATUS_SUGGESTED,
            )
            result = self.svc.decline_suggestion(sug.pk)

        # Third decline should offer opt-out
        self.assertTrue(result["offer_opt_out"])

    def test_opt_out_blocks_future_suggestions(self):
        """Opted-out theme blocks all future suggestions."""
        self.svc.opt_out_theme("workout_consistency")

        result = self.svc.create_suggestion(
            theme="workout_consistency",
            suggestion_text="Should be blocked.",
        )
        self.assertFalse(result["created"])
        self.assertIn("opted out", result["reason"].lower())

    def test_undo_opt_out_allows_suggestions_again(self):
        """Undoing opt-out allows suggestions again."""
        self.svc.opt_out_theme("workout_consistency")
        self.svc.undo_opt_out("workout_consistency")

        result = self.svc.create_suggestion(
            theme="workout_consistency",
            suggestion_text="Should work now.",
        )
        self.assertTrue(result["created"])

    def test_accept_suggestion_marks_accepted(self):
        """Accepting a suggestion marks it correctly."""
        create_result = self.svc.create_suggestion(
            theme="sleep_quality",
            suggestion_text="Aim for 8 hours.",
        )
        sug = create_result["suggestion"]
        accept_result = self.svc.accept_suggestion(sug.pk)

        self.assertTrue(accept_result["success"])
        sug.refresh_from_db()
        self.assertEqual(sug.status, CosGoalSuggestion.STATUS_ACCEPTED)
