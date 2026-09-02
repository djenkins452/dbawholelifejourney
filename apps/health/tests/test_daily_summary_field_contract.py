"""Contract: every key the daily summary builder emits must be a real model field.

`build_for_date` upserts with `update_or_create(defaults=data)`, and Django raises
FieldError for any key that is not a field — fatally, for the whole build. A 2026-04-04
change added `intensity_breakdown` and `activity_sessions` to `_collect_workouts`'s
return without adding columns, so the daily health summary could not be built for ANY
day containing a workout. Nothing read either key; they were computed and discarded on
the way to crashing the build.

This walks the collectors directly rather than asserting the two names, so a third
stray key fails here instead of in a Celery worker.
"""
from datetime import timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.health.models import DailyHealthSummary, WorkoutSession
from apps.users.models import TermsAcceptance

User = get_user_model()


class DailySummaryEmitsOnlyModelFields(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="dhs-fields@example.com", password="testpass123")
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.today = timezone.localdate()
        self.model_fields = {f.name for f in DailyHealthSummary._meta.get_fields()}

    def _seed_a_normal_day(self):
        now = timezone.now()
        WorkoutSession.objects.create(
            user=self.user, date=self.today, name="Push Day",
            session_mode="activity", workout_type="Running", intensity="high",
            duration_minutes=30, calories_burned=300,
            started_at=now - timedelta(minutes=30), completed_at=now)

    def test_collect_workouts_emits_only_model_fields(self):
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder

        self._seed_a_normal_day()
        emitted = DailyHealthSummaryBuilder()._collect_workouts(self.user, self.today)
        unknown = sorted(set(emitted) - self.model_fields)
        self.assertEqual(
            unknown, [],
            f"_collect_workouts emits keys DailyHealthSummary has no column for: "
            f"{unknown}. They are written via update_or_create(defaults=...), so each "
            f"one makes the whole build raise FieldError.",
        )

    def test_build_for_date_survives_a_day_with_a_workout(self):
        """The ordinary case: a completed workout must not break the summary."""
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder

        self._seed_a_normal_day()
        summary = DailyHealthSummaryBuilder().build_for_date(self.user, self.today)
        self.assertIsNotNone(summary)
        self.assertEqual(summary.workout_count, 1)
        self.assertEqual(summary.workout_minutes, 30)
