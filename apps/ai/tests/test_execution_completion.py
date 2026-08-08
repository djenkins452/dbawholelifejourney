# Blocker #14 Layer 2: the completion ROUTER records an execution item on the day it ACTUALLY
# happened (retroactive), reusing existing per-domain writes — and is HONEST by construction:
# `recorded` only when a write succeeded, else needs_info / already_complete / unsupported.
# It must NEVER report success it did not perform (the medication false-claim it replaces).
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.model_interface.constitution import all_tools
from apps.core.execution.execution_completion import complete_execution_item

User = get_user_model()


class ExecutionCompletionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="cei2@test.com", password="x")

    def _yesterday(self):
        from apps.core.utils import get_user_today
        return get_user_today(self.user) - timedelta(days=1)

    def test_action_is_write_enabled_only(self):
        write_names = [t["function"]["name"] for t in all_tools(writes_enabled=True)]
        read_names = [t["function"]["name"] for t in all_tools(writes_enabled=False)]
        self.assertIn("complete_execution_item", write_names)
        self.assertNotIn("complete_execution_item", read_names)

    def test_journal_needs_its_content_not_a_bare_check(self):
        r = complete_execution_item(self.user, "journal", "Journal", self._yesterday())
        self.assertEqual(r["status"], "needs_info")

    def test_journal_with_content_creates_entry_dated_to_that_day(self):
        # The reconciliation workflow: given the content, WLJ creates the entry dated to
        # the ACTUAL day (never today), which — single source of truth — completes that
        # day's journal automatically. No second recording mechanism.
        from apps.journal.models import JournalEntry
        from apps.journal.services.journal_queries import JournalQueries
        y = self._yesterday()
        r = complete_execution_item(self.user, "journal", "Journal", y,
                                    content="Grateful for the week; hopeful about next.")
        self.assertEqual(r["status"], "recorded")
        entry = JournalEntry.objects.get(user=self.user, id=r["detail"]["entry_id"])
        self.assertEqual(entry.entry_date, y)                      # dated to that day, not today
        self.assertTrue(JournalQueries.has_entry_on(self.user, y))  # reconciles that day
        # idempotent: a bare re-check now sees the entry and reports already_complete
        r2 = complete_execution_item(self.user, "journal", "Journal", y)
        self.assertEqual(r2["status"], "already_complete")

    def test_unknown_or_undata_item_is_honest_never_false_recorded(self):
        for kind, title in [("medications", "Medications"), ("task", "Ghost task"),
                            ("prayer", "Prayer Time"), ("something", "X")]:
            r = complete_execution_item(self.user, kind, title, self._yesterday())
            self.assertIn(r["status"], ("unsupported", "already_complete"))
            self.assertNotEqual(r["status"], "recorded")  # never claim success without a write

    def test_workout_records_on_the_actual_day_then_already_complete(self):
        from apps.health.models import WorkoutSession
        y = self._yesterday()
        r1 = complete_execution_item(self.user, "workout", "Workout", y)
        self.assertEqual(r1["status"], "recorded")
        self.assertTrue(WorkoutSession.objects.filter(user=self.user, date=y).exists())
        r2 = complete_execution_item(self.user, "workout", "Workout", y)
        self.assertEqual(r2["status"], "already_complete")   # idempotent, no duplicate

    def test_medications_record_the_days_doses_retroactively(self):
        # Reuse the single-source dose enumerator; verify a taken IntakeLog lands on the
        # ACTUAL day (scheduled_date == yesterday), never today.
        y = self._yesterday()
        from datetime import time
        from apps.health.models import Intake, IntakeSchedule, IntakeLog
        med = Intake.objects.create(user=self.user, name="ZZZ-Med", purpose="test",
                                    intake_type="medication", start_date=y)
        sched = IntakeSchedule.objects.create(intake=med, scheduled_time=time(8, 0),
                                              time_of_day="morning")
        with mock.patch(
            "apps.health.medicine_utils.get_expected_dose_entries",
            return_value=[(med.id, sched.id, y)],
        ):
            r = complete_execution_item(self.user, "medications", "Medications", y)
        self.assertEqual(r["status"], "recorded")
        log = IntakeLog.objects.filter(user=self.user, intake=med, scheduled_date=y).first()
        self.assertIsNotNone(log)
        self.assertIn(log.log_status, (IntakeLog.STATUS_TAKEN, IntakeLog.STATUS_LATE))
        # taken_at anchored to the actual day, not "now"
        self.assertEqual(log.taken_at.date(), y)
