"""Regression: journal rhythm completion anchors to entry_date, not created day.

Behavioral-truth bug: journaling on June 14 *about* June 13 was completing the
June 14 Evening Journal rhythm (the created day) instead of June 13 (the day
being journaled about). That corrupts adherence, streaks, rhythm compliance,
and CoS coaching.

Fix: apps/journal/signals.py passes ``target_date=instance.entry_date`` to
``auto_complete_routine_schedules``. These tests exercise the FULL signal path
(JournalEntry.save → post_save signal → routine auto-complete).
"""

from datetime import date, time, timedelta
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.journal.models import JournalEntry
from apps.life.models import Routine, RoutineLog, RoutineSchedule
from apps.users.models import TermsAcceptance, User

# Isolate the rhythm-anchor behavior from NLP/Celery signal extraction.
_PATCH_DISPATCH = "apps.journal.signals._dispatch_signal_extraction"


class JournalRhythmAnchorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="journal-anchor@test.com", password="testpass123",
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        prefs = self.user.preferences
        prefs.has_completed_onboarding = True
        # The auto-complete only runs when the AI assistant is enabled.
        prefs.ai_enabled = True
        prefs.personal_assistant_enabled = True
        prefs.save()

        self.routine = Routine.objects.create(
            user=self.user, name="Daily Routine",
            time_of_day="evening", is_active=True,
        )
        self.journal_schedule = RoutineSchedule.objects.create(
            routine=self.routine, name="Evening Journal",
            scheduled_time=time(20, 0), grace_period_minutes=60,
            days_of_week="0,1,2,3,4,5,6", is_active=True,
            routine_type="activity", activity_type="journal",
        )
        self.today = timezone.localdate()
        self.yesterday = self.today - timedelta(days=1)

    def _journal(self, entry_date, body="Reflecting on the day."):
        return JournalEntry.objects.create(
            user=self.user, title="", body=body, entry_date=entry_date,
        )

    def _completed_dates(self):
        return set(
            RoutineLog.objects.filter(
                schedule=self.journal_schedule,
                log_status__in=("completed", "completed_late"),
            ).values_list("scheduled_date", flat=True)
        )

    # ── 1. Backdated journal ──────────────────────────────────────────────
    @patch(_PATCH_DISPATCH)
    def test_backdated_journal_completes_entry_date_not_today(self, _disp):
        """Created today, entry_date=yesterday → yesterday complete, today NOT."""
        self._journal(self.yesterday)

        self.assertTrue(
            RoutineLog.objects.filter(
                schedule=self.journal_schedule, scheduled_date=self.yesterday,
                log_status__in=("completed", "completed_late"),
            ).exists(),
            "Yesterday's Evening Journal rhythm should be complete.",
        )
        self.assertFalse(
            RoutineLog.objects.filter(
                schedule=self.journal_schedule, scheduled_date=self.today,
            ).exists(),
            "Today's rhythm must stay open — the user did not journal for today.",
        )

    # ── 2. Same-day journal (no regression) ───────────────────────────────
    @patch(_PATCH_DISPATCH)
    def test_same_day_journal_completes_today(self, _disp):
        self._journal(self.today)
        self.assertTrue(
            RoutineLog.objects.filter(
                schedule=self.journal_schedule, scheduled_date=self.today,
                log_status__in=("completed", "completed_late"),
            ).exists(),
        )
        self.assertEqual(self._completed_dates(), {self.today})

    # ── 3. Historical edit must not complete today ────────────────────────
    @patch(_PATCH_DISPATCH)
    def test_editing_old_journal_does_not_complete_today(self, _disp):
        entry = self._journal(self.yesterday)
        # Editing (save with created=False) must NOT trigger auto-complete.
        entry.body = "Edited reflection."
        entry.save()

        self.assertFalse(
            RoutineLog.objects.filter(
                schedule=self.journal_schedule, scheduled_date=self.today,
            ).exists(),
            "Editing a past entry must never complete today's rhythm.",
        )
        # Yesterday still has exactly one completion (no duplicate from edit).
        self.assertEqual(
            RoutineLog.objects.filter(
                schedule=self.journal_schedule, scheduled_date=self.yesterday,
            ).count(),
            1,
        )

    # ── 4. Catch-up journaling: both days complete independently ──────────
    @patch(_PATCH_DISPATCH)
    def test_catch_up_completes_both_days_independently(self, _disp):
        self._journal(self.yesterday)
        self._journal(self.today)
        self.assertEqual(self._completed_dates(), {self.yesterday, self.today})

    # ── 5. No double completion on repeated same-day entries ──────────────
    @patch(_PATCH_DISPATCH)
    def test_repeated_same_day_entries_do_not_double_complete(self, _disp):
        self._journal(self.today, body="Morning thoughts.")
        self._journal(self.today, body="Evening thoughts.")
        self.assertEqual(
            RoutineLog.objects.filter(
                schedule=self.journal_schedule, scheduled_date=self.today,
            ).count(),
            1,
            "Idempotency: one RoutineLog per (schedule, date) regardless of "
            "how many journals are written that day.",
        )
