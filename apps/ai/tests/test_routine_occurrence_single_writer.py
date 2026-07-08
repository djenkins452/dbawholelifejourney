# ==============================================================================
# File: apps/ai/tests/test_routine_occurrence_single_writer.py
# Description: SINGLE-SOURCE EXECUTION — a routine occurrence has ONE writer and ONE
#   resolved reader. A routine's occurrence time is owned by RoutineSchedule + its
#   one-day RoutineLog override, which build_today_execution (Beth/dashboard/overdue)
#   reads. "Move my workout to lunch today" used to route through mutate_task →
#   Task.scheduled_time / CalendarEvent, so the calendar showed 12:00 while Beth's brief
#   still read 6:15. The guard in handle_mutate_task redirects a same-day routine time
#   move to reschedule_routine_item() → RoutineLog, never a divergent Task time; the
#   resolved occurrence then reports the same new time everywhere. Non-routine task
#   reschedules are untouched.
#
#   NOTE: reschedule_routine_item validates "new time must be later than the user's
#   current local time" (it is a move-to-later-today operation). Tests pin the clock to
#   09:00 so a move to 12:00 is valid and deterministic regardless of when they run.
# ==============================================================================
import datetime
from contextlib import ExitStack
from datetime import time as dtime
from unittest import mock

from django.conf import settings
from django.test import TestCase

from apps.users.models import User, TermsAcceptance

_CLOCK_MODULES = ("apps.core.utils", "apps.life.services._routine_internal")


def _mkuser(email):
    u = User.objects.create_user(email=email, password="x")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class RoutineOccurrenceSingleWriterTests(TestCase):
    def setUp(self):
        from apps.life.models import Routine, RoutineSchedule
        from apps.ai.action_handlers import ActionHandler
        self.user = _mkuser("occ@test.com")
        self.handler = ActionHandler(self.user)
        self.today = self.handler._get_user_today()
        self.routine = Routine.objects.create(user=self.user, name="Fitness")
        # specific_date=today → unambiguously applies today (no weekday coupling).
        self.schedule = RoutineSchedule.objects.create(
            routine=self.routine, name="Workout",
            scheduled_time=dtime(6, 15), specific_date=self.today,
        )

    def _clock_0900(self):
        """Pin every routine clock to 09:00 today so a move to 12:00 is 'later'."""
        now = datetime.datetime.combine(
            self.today, dtime(9, 0), tzinfo=datetime.timezone.utc)
        stack = ExitStack()
        for mod in _CLOCK_MODULES:
            stack.enter_context(mock.patch(f"{mod}.get_user_now", return_value=now))
            stack.enter_context(
                mock.patch(f"{mod}.get_user_today", return_value=self.today))
        return stack

    def test_move_writes_routinelog_not_task(self):
        from apps.life.models import Task, RoutineLog
        # A stray Task twin also named "Workout" — the guard must prefer the routine
        # (canonical) and leave the Task untouched (the dual-definition case).
        twin = Task.objects.create(
            user=self.user, title="Workout", status='active',
            is_routine=True, scheduled_time=dtime(6, 15),
        )
        with self._clock_0900():
            result = self.handler.handle_mutate_task(
                action='update', task_query='workout', new_scheduled_time='12:00')

        # 1) The move was redirected to the routine occurrence writer.
        self.assertTrue(result.success, getattr(result, 'message', ''))
        self.assertEqual(result.action_type, 'reschedule_routine_item')

        # 2) The one-day override is written to RoutineLog (the canonical occurrence).
        log = RoutineLog.objects.get(schedule=self.schedule, scheduled_date=self.today)
        self.assertEqual(log.log_status, 'rescheduled')
        self.assertEqual(log.rescheduled_time, dtime(12, 0))

        # 3) The Task twin's time is NOT changed — no divergent second writer.
        twin.refresh_from_db()
        self.assertEqual(twin.scheduled_time, dtime(6, 15))

    def test_resolved_occurrence_reads_the_new_time(self):
        # Beth/dashboard/overdue all read the resolved occurrence; prove it now reports
        # 12:00 (the single canonical override), not the 6:15 template.
        from apps.life.services._routine_internal import get_todays_routine_items
        with self._clock_0900():
            self.handler.handle_mutate_task(
                action='update', task_query='workout', new_scheduled_time='12:00')
            res = get_todays_routine_items(self.user)

        entries = [e for w in res.get('items_by_window', {}).values() for e in w
                   if 'workout' in (e.get('item_name', '') or '').lower()]
        self.assertTrue(entries, "workout not found in resolved occurrence")
        w = entries[0]
        self.assertEqual(w.get('status'), 'rescheduled')
        self.assertEqual(w.get('scheduled_time'), '12:00 PM')   # resolved display time

    def test_non_routine_task_reschedule_still_mutates_the_task(self):
        from apps.life.models import Task
        task = Task.objects.create(
            user=self.user, title="Call the dentist", status='active',
            due_date=self.today, scheduled_time=dtime(9, 0),
        )
        with self._clock_0900():
            result = self.handler.handle_mutate_task(
                action='update', task_query='dentist', new_scheduled_time='15:00')
        self.assertTrue(result.success, getattr(result, 'message', ''))
        self.assertNotEqual(result.action_type, 'reschedule_routine_item')
        task.refresh_from_db()
        self.assertEqual(task.scheduled_time, dtime(15, 0))

    def test_end_to_end_beth_dashboard_overdue_calendar_agree(self):
        """The whole point: after 'move workout to lunch today', every execution surface
        resolves the SAME 12:00 from the one occurrence — no surface disagrees."""
        import datetime
        from django.utils import timezone
        from apps.core.execution.today_execution import build_today_execution
        from apps.calendar_engine.views import _get_events_in_range

        with self._clock_0900():
            r = self.handler.handle_mutate_task(
                action='update', task_query='workout', new_scheduled_time='12:00')
        self.assertTrue(r.success, getattr(r, 'message', ''))

        # Beth + dashboard + overdue all read build_today_execution — resolves 12:00.
        contract = build_today_execution(self.user)
        routine = [i for i in contract.get('items', [])
                   if i.get('source_type') == 'routine_item'
                   and 'workout' in (i.get('title', '') or '').lower()]
        self.assertTrue(routine, "workout missing from the execution contract")
        self.assertEqual(routine[0].get('scheduled_time'), '12:00')

        # The calendar consumes the SAME resolved occurrence — also 12:00, not 6:15.
        day_start = timezone.make_aware(
            datetime.datetime.combine(self.today, datetime.time.min))
        day_end = timezone.make_aware(
            datetime.datetime.combine(self.today, datetime.time.max))
        events = _get_events_in_range(self.user, day_start, day_end)
        cal = [e for e in events if e.get('source_type') == 'routine'
               and 'workout' in (e.get('title', '') or '').lower()]
        self.assertTrue(cal, "workout missing from the calendar feed")
        self.assertIn('T12:00', cal[0]['start_dt'])         # resolved time, not 06:15


class RoutineSingleDefinitionContractTests(TestCase):
    """CI contract: routines have ONE definition (RoutineSchedule), ONE writer
    (RoutineLog), and are deduped from the task readers — no competing representations."""

    def setUp(self):
        from apps.ai.action_handlers import ActionHandler
        self.user = _mkuser("contract@test.com")
        self.handler = ActionHandler(self.user)

    def test_create_routine_makes_routineschedule_not_task(self):
        from apps.life.models import Task, RoutineSchedule
        result = self.handler.handle_create_routine_task(
            title="Evening Walk", scheduled_time="18:00", recurrence_pattern="daily")
        self.assertTrue(result.success, getattr(result, 'message', ''))
        # Canonical definition created…
        self.assertTrue(RoutineSchedule.objects.filter(
            routine__user=self.user, name="Evening Walk").exists())
        # …and NO dual Task(is_routine, is_recurring) definition.
        self.assertFalse(
            Task.objects.filter(user=self.user, is_routine=True).exists(),
            "create_routine_task must not create a Task(is_routine) twin")
        self.assertEqual(result.created_object.get('model'), 'RoutineSchedule')

    def test_execution_reader_excludes_is_routine_tasks(self):
        # Both the overdue and due-today task collectors must drop is_routine tasks so a
        # legacy Task twin can never double-show alongside a RoutineSchedule occurrence.
        import inspect
        from apps.core.execution import today_execution
        src = inspect.getsource(today_execution._collect_task_items)
        # Two guards — one per loop (overdue + due_today).
        self.assertEqual(src.count("if t.is_routine:"), 2,
                         "both task loops must exclude is_routine (read-time dedup)")
