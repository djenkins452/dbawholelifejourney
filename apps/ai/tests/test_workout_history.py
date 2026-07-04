# ==============================================================================
# File: apps/ai/tests/test_workout_history.py
# Description: WI-3 — WORKOUT ENTITY COMPLETENESS. Workout retrieval treated like
#   Sleep & Weight. Origin: "Did you see my workout?", "Over 40,000 lbs total", "did I
#   work out on 7/2?" were search failures. Now they read the canonical completed-
#   workout truth (existence, total volume, duration) for the referenced day (default
#   today) — deterministic, honest when a day has no completed workout.
# ==============================================================================
from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.ai.chatgpt_cos import workout_history as wo

User = get_user_model()
TODAY = date(2026, 7, 4)
_TODAY = "apps.core.utils.get_user_today"


class _FakeSession:
    def __init__(self, name, volume, duration):
        self.name = name
        self.total_volume = volume
        self.duration_minutes = duration


class WorkoutHistoryCompositionTests(TestCase):
    """Composition + intent + date resolution, isolated from the exercise/set schema
    by mocking the canonical query."""

    def setUp(self):
        self.user = User.objects.create_user(email="wo@test.com", password="x")

    def _answer(self, msg, sessions):
        from apps.health.services.workout_queries import WorkoutQueries
        with mock.patch(_TODAY, return_value=TODAY), \
                mock.patch.object(WorkoutQueries, "completed_on", return_value=sessions):
            return wo.answer(self.user, msg)

    def test_did_you_see_my_workout_defaults_to_today(self):
        a = self._answer("Did you see my workout?", [_FakeSession("Push Day", 40200, 62)])
        self.assertEqual(a["lane"], "workout_history")
        self.assertEqual(a["workout_date"], "2026-07-04")
        self.assertIn("Yes, I see your workout today", a["answer"])
        self.assertIn("Push Day", a["answer"])
        self.assertIn("40,200 lb", a["answer"])

    def test_volume_phrase_without_workout_word(self):
        a = self._answer("Over 40,000 lbs total", [_FakeSession("Push Day", 40200, 62)])
        self.assertEqual(a["lane"], "workout_history")
        self.assertIn("40,200 lb of total volume", a["answer"])

    def test_duration_intent(self):
        a = self._answer("How long did I work out today?", [_FakeSession("", 40200, 62)])
        self.assertIn("62 minutes", a["answer"])

    def test_no_completed_workout_is_honest(self):
        a = self._answer("did you see my workout", [])
        self.assertIn("don't see a completed workout today", a["answer"].lower())

    def test_non_workout_question_declined(self):
        with mock.patch(_TODAY, return_value=TODAY):
            self.assertIsNone(wo.answer(self.user, "what was my weight on 7/1"))

    def test_explicit_date_resolves(self):
        a = self._answer("did I work out on 7/2?", [_FakeSession("Legs", 30000, 45)])
        self.assertEqual(a["workout_date"], "2026-07-02")


class WorkoutHistoryRealQueryTests(TestCase):
    """One end-to-end check through the real canonical query (existence + duration;
    volume needs the exercise/set schema and is covered above by composition)."""

    def setUp(self):
        from apps.health.models import WorkoutSession
        self.user = User.objects.create_user(email="wo2@test.com", password="x")
        WorkoutSession.objects.create(
            user=self.user, date=TODAY, name="Morning Lift",
            duration_minutes=55, completed_at=timezone.now())

    def test_finds_todays_completed_workout(self):
        with mock.patch(_TODAY, return_value=TODAY):
            a = wo.answer(self.user, "can you see that I worked out today?")
        self.assertEqual(a["lane"], "workout_history")
        self.assertIn("Morning Lift", a["answer"])
        self.assertIn("55 min", a["answer"])
