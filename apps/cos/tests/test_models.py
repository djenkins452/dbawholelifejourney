"""
CoS v2 — Phase 1 Tests: Model CRUD and behavior

Tests for: CosReflection, CosPromptSchedule, CosGoalSuggestion, CosAutoShiftLog
"""

import datetime as dt

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

User = get_user_model()


def _create_test_user(email="cosmodel@example.com"):
    from apps.users.models import TermsAcceptance

    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    return user


def _create_calendar_event(user, title="Test Event"):
    from uuid import uuid4

    return CalendarEvent.objects.create(
        user=user,
        title=title,
        start_dt=timezone.now(),
        end_dt=timezone.now() + dt.timedelta(hours=1),
        idempotency_key=uuid4().hex,
    )


# ──────────────────────────────────────────────────────────
# CosReflection Tests
# ──────────────────────────────────────────────────────────


class CosReflectionTests(TestCase):
    """Test CosReflection CRUD and querying."""

    def setUp(self):
        self.user = _create_test_user("refl@example.com")
        self.event = _create_calendar_event(self.user)
        self.ct = ContentType.objects.get_for_model(CalendarEvent)

    def test_create_reflection(self):
        """Can create a reflection attached to a calendar event."""
        refl = CosReflection.objects.create(
            user=self.user,
            content_type=self.ct,
            object_id=self.event.pk,
            text="That was a great workout today.",
            sentiment="positive",
            activity_date=dt.date.today(),
            activity_type="workout",
        )
        self.assertEqual(refl.text, "That was a great workout today.")
        self.assertEqual(refl.sentiment, "positive")
        self.assertEqual(refl.source_entity, self.event)

    def test_reflection_str(self):
        refl = CosReflection.objects.create(
            user=self.user,
            content_type=self.ct,
            object_id=self.event.pk,
            text="Test",
            activity_date=dt.date.today(),
            activity_type="meeting",
        )
        self.assertIn("meeting", str(refl))

    def test_query_by_activity_type(self):
        """Can query reflections by activity type."""
        CosReflection.objects.create(
            user=self.user,
            content_type=self.ct,
            object_id=self.event.pk,
            text="Workout note",
            activity_date=dt.date.today(),
            activity_type="workout",
        )
        CosReflection.objects.create(
            user=self.user,
            content_type=self.ct,
            object_id=self.event.pk,
            text="Meeting note",
            activity_date=dt.date.today(),
            activity_type="meeting",
        )
        workouts = CosReflection.objects.filter(
            user=self.user, activity_type="workout"
        )
        self.assertEqual(workouts.count(), 1)
        self.assertEqual(workouts.first().text, "Workout note")

    def test_query_by_date_range(self):
        """Can query reflections by date for temporal comparisons."""
        yesterday = dt.date.today() - dt.timedelta(days=1)
        today = dt.date.today()
        CosReflection.objects.create(
            user=self.user,
            content_type=self.ct,
            object_id=self.event.pk,
            text="Yesterday was cold and tough",
            activity_date=yesterday,
            activity_type="workout",
            sentiment="negative",
        )
        CosReflection.objects.create(
            user=self.user,
            content_type=self.ct,
            object_id=self.event.pk,
            text="Today was much better",
            activity_date=today,
            activity_type="workout",
            sentiment="positive",
        )
        recent = CosReflection.objects.filter(
            user=self.user,
            activity_type="workout",
            activity_date__gte=yesterday,
        ).order_by("activity_date")
        self.assertEqual(recent.count(), 2)
        self.assertEqual(recent.first().sentiment, "negative")
        self.assertEqual(recent.last().sentiment, "positive")

    def test_indefinite_retention(self):
        """Reflections have no soft-delete — they persist indefinitely."""
        refl = CosReflection.objects.create(
            user=self.user,
            content_type=self.ct,
            object_id=self.event.pk,
            text="Old reflection",
            activity_date=dt.date.today() - dt.timedelta(days=365),
            activity_type="workout",
        )
        # No soft_delete method — TimeStampedModel base, not SoftDeleteModel
        self.assertFalse(hasattr(refl, "soft_delete"))
        self.assertTrue(CosReflection.objects.filter(pk=refl.pk).exists())


# ──────────────────────────────────────────────────────────
# CosPromptSchedule Tests
# ──────────────────────────────────────────────────────────


class CosPromptScheduleTests(TestCase):
    """Test CosPromptSchedule lifecycle."""

    def setUp(self):
        self.user = _create_test_user("prompt@example.com")
        self.event = _create_calendar_event(self.user)
        self.ct = ContentType.objects.get_for_model(CalendarEvent)

    def test_create_pre_prompt(self):
        """Can create a pre-activity prompt."""
        prompt = CosPromptSchedule.objects.create(
            user=self.user,
            content_type=self.ct,
            object_id=self.event.pk,
            timing=CosPromptSchedule.TIMING_PRE,
            scheduled_for=timezone.now() + dt.timedelta(minutes=15),
            activity_type="meeting",
            prompt_text="Your meeting starts in 15 minutes.",
        )
        self.assertEqual(prompt.status, CosPromptSchedule.STATUS_PENDING)
        self.assertEqual(prompt.timing, "pre")

    def test_create_post_prompt(self):
        """Can create a post-activity prompt."""
        prompt = CosPromptSchedule.objects.create(
            user=self.user,
            content_type=self.ct,
            object_id=self.event.pk,
            timing=CosPromptSchedule.TIMING_POST,
            scheduled_for=timezone.now() + dt.timedelta(hours=1),
            activity_type="workout",
            prompt_text="Did you complete your workout?",
        )
        self.assertEqual(prompt.timing, "post")

    def test_mark_delivered(self):
        """mark_delivered() updates status and timestamp."""
        prompt = CosPromptSchedule.objects.create(
            user=self.user,
            content_type=self.ct,
            object_id=self.event.pk,
            timing=CosPromptSchedule.TIMING_PRE,
            scheduled_for=timezone.now(),
            activity_type="meeting",
            prompt_text="Test",
        )
        prompt.mark_delivered()
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, CosPromptSchedule.STATUS_DELIVERED)
        self.assertIsNotNone(prompt.delivered_at)

    def test_mark_responded_positive(self):
        """mark_responded() with positive=True."""
        prompt = CosPromptSchedule.objects.create(
            user=self.user,
            content_type=self.ct,
            object_id=self.event.pk,
            timing=CosPromptSchedule.TIMING_POST,
            scheduled_for=timezone.now(),
            activity_type="workout",
            prompt_text="Did you complete your workout?",
        )
        prompt.mark_delivered()
        prompt.mark_responded(positive=True, text="Yes, felt great!")
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, CosPromptSchedule.STATUS_RESPONDED)
        self.assertTrue(prompt.response_positive)
        self.assertEqual(prompt.response_text, "Yes, felt great!")

    def test_mark_responded_negative_stops(self):
        """mark_responded() with positive=False (user says No → stop)."""
        prompt = CosPromptSchedule.objects.create(
            user=self.user,
            content_type=self.ct,
            object_id=self.event.pk,
            timing=CosPromptSchedule.TIMING_POST,
            scheduled_for=timezone.now(),
            activity_type="workout",
            prompt_text="Did you complete your workout?",
        )
        prompt.mark_responded(positive=False)
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, CosPromptSchedule.STATUS_RESPONDED)
        self.assertFalse(prompt.response_positive)

    def test_mark_expired(self):
        """mark_expired() sets status correctly."""
        prompt = CosPromptSchedule.objects.create(
            user=self.user,
            content_type=self.ct,
            object_id=self.event.pk,
            timing=CosPromptSchedule.TIMING_PRE,
            scheduled_for=timezone.now() - dt.timedelta(hours=2),
            activity_type="meeting",
            prompt_text="Test",
        )
        prompt.mark_expired()
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, CosPromptSchedule.STATUS_EXPIRED)

    def test_cancel(self):
        """cancel() sets status correctly."""
        prompt = CosPromptSchedule.objects.create(
            user=self.user,
            content_type=self.ct,
            object_id=self.event.pk,
            timing=CosPromptSchedule.TIMING_PRE,
            scheduled_for=timezone.now(),
            activity_type="meeting",
            prompt_text="Test",
        )
        prompt.cancel()
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, CosPromptSchedule.STATUS_CANCELED)

    def test_query_pending_due(self):
        """Can query pending prompts that are due."""
        now = timezone.now()
        # Due prompt
        CosPromptSchedule.objects.create(
            user=self.user,
            content_type=self.ct,
            object_id=self.event.pk,
            timing=CosPromptSchedule.TIMING_PRE,
            scheduled_for=now - dt.timedelta(minutes=5),
            activity_type="meeting",
            prompt_text="Due prompt",
        )
        # Future prompt
        CosPromptSchedule.objects.create(
            user=self.user,
            content_type=self.ct,
            object_id=self.event.pk,
            timing=CosPromptSchedule.TIMING_PRE,
            scheduled_for=now + dt.timedelta(hours=1),
            activity_type="meeting",
            prompt_text="Future prompt",
        )
        due = CosPromptSchedule.objects.filter(
            status=CosPromptSchedule.STATUS_PENDING,
            scheduled_for__lte=now,
        )
        self.assertEqual(due.count(), 1)
        self.assertEqual(due.first().prompt_text, "Due prompt")


# ──────────────────────────────────────────────────────────
# CosGoalSuggestion Tests
# ──────────────────────────────────────────────────────────


class CosGoalSuggestionTests(TestCase):
    """Test CosGoalSuggestion throttle and decline tracking."""

    def setUp(self):
        self.user = _create_test_user("goalsug@example.com")

    def test_create_suggestion(self):
        """Can create a goal suggestion."""
        sug = CosGoalSuggestion.objects.create(
            user=self.user,
            theme="fitness_consistency",
            suggestion_text="Consider setting a goal to exercise 3x per week.",
            evidence_summary="You've exercised 5 times in the past 2 weeks.",
        )
        self.assertEqual(sug.status, CosGoalSuggestion.STATUS_SUGGESTED)
        self.assertFalse(sug.opted_out)

    def test_decline_count_tracking(self):
        """get_theme_decline_count() returns correct count."""
        CosGoalSuggestion.objects.create(
            user=self.user,
            theme="sleep",
            suggestion_text="Improve sleep",
            status=CosGoalSuggestion.STATUS_DECLINED,
        )
        CosGoalSuggestion.objects.create(
            user=self.user,
            theme="sleep",
            suggestion_text="Improve sleep v2",
            status=CosGoalSuggestion.STATUS_DECLINED,
        )
        CosGoalSuggestion.objects.create(
            user=self.user,
            theme="sleep",
            suggestion_text="Improve sleep v3",
            status=CosGoalSuggestion.STATUS_ACCEPTED,
        )
        count = CosGoalSuggestion.get_theme_decline_count(self.user, "sleep")
        self.assertEqual(count, 2)

    def test_opted_out_check(self):
        """is_theme_opted_out() works correctly."""
        self.assertFalse(
            CosGoalSuggestion.is_theme_opted_out(self.user, "fitness")
        )
        CosGoalSuggestion.objects.create(
            user=self.user,
            theme="fitness",
            suggestion_text="Exercise more",
            opted_out=True,
        )
        self.assertTrue(
            CosGoalSuggestion.is_theme_opted_out(self.user, "fitness")
        )

    def test_last_suggestion_date(self):
        """last_suggestion_date() returns correct date."""
        self.assertIsNone(
            CosGoalSuggestion.last_suggestion_date(self.user, "hydration")
        )
        CosGoalSuggestion.objects.create(
            user=self.user,
            theme="hydration",
            suggestion_text="Drink more water",
        )
        last = CosGoalSuggestion.last_suggestion_date(self.user, "hydration")
        self.assertEqual(last, dt.date.today())

    def test_different_themes_independent(self):
        """Decline counts are independent per theme."""
        CosGoalSuggestion.objects.create(
            user=self.user,
            theme="sleep",
            suggestion_text="Sleep better",
            status=CosGoalSuggestion.STATUS_DECLINED,
        )
        CosGoalSuggestion.objects.create(
            user=self.user,
            theme="fitness",
            suggestion_text="Exercise more",
            status=CosGoalSuggestion.STATUS_DECLINED,
        )
        self.assertEqual(
            CosGoalSuggestion.get_theme_decline_count(self.user, "sleep"), 1
        )
        self.assertEqual(
            CosGoalSuggestion.get_theme_decline_count(self.user, "fitness"), 1
        )


# ──────────────────────────────────────────────────────────
# CosAutoShiftLog Tests
# ──────────────────────────────────────────────────────────


class CosAutoShiftLogTests(TestCase):
    """Test CosAutoShiftLog creation and querying."""

    def setUp(self):
        self.user = _create_test_user("shift@example.com")
        self.event = _create_calendar_event(self.user)
        self.ct = ContentType.objects.get_for_model(CalendarEvent)

    def test_create_shift_log(self):
        """Can create an auto-shift log entry."""
        now = timezone.now()
        log = CosAutoShiftLog.objects.create(
            user=self.user,
            content_type=self.ct,
            object_id=self.event.pk,
            original_start=now,
            original_end=now + dt.timedelta(hours=1),
            new_start=now + dt.timedelta(minutes=15),
            new_end=now + dt.timedelta(hours=1, minutes=15),
            reason="Conflict with higher-priority meeting",
            shift_type="conflict_avoidance",
            priority_level="low",
            auto_shifted=True,
            user_confirmed=False,
        )
        self.assertTrue(log.auto_shifted)
        self.assertFalse(log.user_confirmed)
        self.assertEqual(log.shift_type, "conflict_avoidance")

    def test_shift_log_str(self):
        now = timezone.now()
        log = CosAutoShiftLog.objects.create(
            user=self.user,
            content_type=self.ct,
            object_id=self.event.pk,
            original_start=now,
            original_end=now + dt.timedelta(hours=1),
            new_start=now + dt.timedelta(minutes=15),
            new_end=now + dt.timedelta(hours=1, minutes=15),
            reason="Test",
            shift_type="conflict_avoidance",
            priority_level="low",
        )
        self.assertIn("conflict_avoidance", str(log))

    def test_query_user_shifts(self):
        """Can query all shifts for a user."""
        now = timezone.now()
        for i in range(3):
            CosAutoShiftLog.objects.create(
                user=self.user,
                content_type=self.ct,
                object_id=self.event.pk,
                original_start=now + dt.timedelta(hours=i),
                original_end=now + dt.timedelta(hours=i + 1),
                new_start=now + dt.timedelta(hours=i, minutes=15),
                new_end=now + dt.timedelta(hours=i + 1, minutes=15),
                reason=f"Shift {i}",
                shift_type="conflict_avoidance",
                priority_level="low",
            )
        self.assertEqual(
            CosAutoShiftLog.objects.filter(user=self.user).count(), 3
        )
