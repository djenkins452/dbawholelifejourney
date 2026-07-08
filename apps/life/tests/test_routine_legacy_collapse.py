# ==============================================================================
# File: apps/life/tests/test_routine_legacy_collapse.py
# Description: COMMIT 2 — legacy dual-defined routine cleanup + multi-day resolution.
#   Proves existing data obeys the single-source invariant: collapse_dual_defined_routines
#   makes RoutineSchedule the one definition, cancels stale twin CalendarEvents, and
#   soft-deletes/stops the Task twin — so a legacy record can no longer produce a calendar
#   event that disagrees with Beth. resolve_routine_occurrences resolves the whole visible
#   range from RoutineSchedule + RoutineLog (the same source Beth reads).
# ==============================================================================
import datetime
from datetime import time as dtime, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.users.models import TermsAcceptance

User = get_user_model()


def _mkuser(email):
    u = User.objects.create_user(email=email, password="x")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


def _routine(user, name="Workout", t=dtime(6, 15), days='0,1,2,3,4,5,6'):
    from apps.life.models import Routine, RoutineSchedule
    r = Routine.objects.create(user=user, name=name, is_active=True)
    s = RoutineSchedule.objects.create(
        routine=r, name=name, scheduled_time=t, grace_period_minutes=30,
        days_of_week=days, is_active=True)
    return r, s


def _twin_task(user, title="Workout", t=dtime(6, 15)):
    from apps.life.models import Task
    today = timezone.localdate()
    return Task.objects.create(
        user=user, title=title, status='active', is_routine=True, is_recurring=True,
        recurrence_pattern='daily', due_date=today, start_date=today, scheduled_time=t)


def _twin_calendar_event(user, task, t=dtime(6, 15)):
    from apps.calendar_engine.models import CalendarEvent
    from uuid import uuid4
    today = timezone.localdate()
    start = timezone.make_aware(datetime.datetime.combine(today, t))
    return CalendarEvent.objects.create(
        user=user, title=task.title,
        start_dt=start, end_dt=start + timedelta(minutes=30),
        event_kind=CalendarEvent.KIND_EXECUTION_BLOCK,
        source_type=CalendarEvent.SOURCE_TASK, source_id=str(task.pk),
        status=CalendarEvent.STATUS_SCHEDULED, idempotency_key=uuid4().hex)


class CollapseTests(TestCase):
    def test_case_a_dual_defined_cancels_twin_keeps_schedule(self):
        from apps.life.models import Task, RoutineSchedule
        from apps.calendar_engine.models import CalendarEvent
        from apps.life.services.routine_cleanup import collapse_dual_defined_routines
        u = _mkuser("a@test.com")
        _, sched = _routine(u)
        task = _twin_task(u)
        ev = _twin_calendar_event(u, task)

        counts = collapse_dual_defined_routines(u)

        # Canonical definition preserved; NO new schedule created (twin already existed).
        self.assertTrue(RoutineSchedule.objects.filter(pk=sched.pk, is_active=True).exists())
        self.assertEqual(counts['schedules_created'], 0)
        # Twin CalendarEvent cancelled; Task twin soft-deleted (out of the active manager).
        ev.refresh_from_db()
        self.assertEqual(ev.status, CalendarEvent.STATUS_CANCELED)
        self.assertFalse(Task.objects.filter(pk=task.pk).exists())
        # ≥1: the manual twin AND the one the Task's own post_save signal projected
        # (the real dual-definition mechanism) are both cancelled — none left scheduled.
        self.assertGreaterEqual(counts['events_canceled'], 1)
        self.assertEqual(CalendarEvent.objects.filter(
            source_id=str(task.pk),
            status=CalendarEvent.STATUS_SCHEDULED).count(), 0)

    def test_case_b_task_only_creates_canonical_schedule(self):
        from apps.life.models import Task, RoutineSchedule
        from apps.life.services.routine_cleanup import collapse_dual_defined_routines
        u = _mkuser("b@test.com")
        task = _twin_task(u, title="Evening Walk", t=dtime(18, 0))

        counts = collapse_dual_defined_routines(u)

        self.assertEqual(counts['schedules_created'], 1)
        self.assertTrue(RoutineSchedule.objects.filter(
            routine__user=u, name__iexact="Evening Walk", is_active=True).exists())
        self.assertFalse(Task.objects.filter(pk=task.pk).exists())

    def test_idempotent(self):
        from apps.life.models import RoutineSchedule
        from apps.life.services.routine_cleanup import collapse_dual_defined_routines
        u = _mkuser("idem@test.com")
        _twin_task(u, title="Stretch", t=dtime(7, 0))
        first = collapse_dual_defined_routines(u)
        second = collapse_dual_defined_routines(u)
        self.assertEqual(first['schedules_created'], 1)
        self.assertEqual(second['routines'], 0)          # nothing left to collapse
        self.assertEqual(RoutineSchedule.objects.filter(
            routine__user=u, name__iexact="Stretch").count(), 1)  # no duplicate


class MultiDayResolutionTests(TestCase):
    def test_routinelog_override_applies_per_date(self):
        from apps.life.models import RoutineLog
        from apps.life.services.routine_resolution import resolve_routine_occurrences
        u = _mkuser("md@test.com")
        routine, sched = _routine(u, t=dtime(6, 15))       # daily
        today = timezone.localdate()
        tomorrow = today + timedelta(days=1)
        # One-day override on TOMORROW only.
        RoutineLog.objects.create(
            user=u, schedule=sched, scheduled_date=tomorrow,
            log_status='rescheduled', rescheduled_time=dtime(12, 0),
            routine_at_time=routine)

        occ = resolve_routine_occurrences(u, today, tomorrow)
        by_date = {o['date']: o for o in occ if o['name'] == 'Workout'}
        self.assertEqual(by_date[today]['time'], dtime(6, 15))       # template
        self.assertEqual(by_date[tomorrow]['time'], dtime(12, 0))    # overridden
        self.assertEqual(by_date[tomorrow]['status'], 'rescheduled')


class LegacyNoDisagreementTests(TestCase):
    def test_after_collapse_calendar_and_beth_agree_no_stale_twin(self):
        from apps.life.models import RoutineLog
        from apps.calendar_engine.models import CalendarEvent
        from apps.calendar_engine.views import _get_events_in_range
        from apps.life.services.routine_cleanup import collapse_dual_defined_routines
        u = _mkuser("nodis@test.com")
        routine, sched = _routine(u, t=dtime(6, 15))
        task = _twin_task(u)
        _twin_calendar_event(u, task)                       # stale twin at 6:15
        today = timezone.localdate()
        RoutineLog.objects.create(                          # resolved occurrence → 12:00
            user=u, schedule=sched, scheduled_date=today,
            log_status='rescheduled', rescheduled_time=dtime(12, 0),
            routine_at_time=routine)

        day_start = timezone.make_aware(datetime.datetime.combine(today, dtime.min))
        day_end = timezone.make_aware(datetime.datetime.combine(today, dtime.max))

        # BEFORE collapse: the stale twin (6:15) is a direct event and wins the dedup.
        before = [e for e in _get_events_in_range(u, day_start, day_end)
                  if 'workout' in e['title'].lower()]
        self.assertTrue(any('T06:15' in e['start_dt'] for e in before))

        collapse_dual_defined_routines(u)

        # AFTER collapse: twin cancelled → calendar resolves the SAME 12:00 as Beth.
        after = [e for e in _get_events_in_range(u, day_start, day_end)
                 if 'workout' in e['title'].lower()]
        self.assertTrue(after, "workout missing from calendar after collapse")
        self.assertTrue(all('T06:15' not in e['start_dt'] for e in after),
                        "stale 6:15 twin still on the calendar")
        self.assertTrue(any('T12:00' in e['start_dt'] for e in after))
        self.assertEqual(
            CalendarEvent.objects.filter(
                source_id=str(task.pk),
                status=CalendarEvent.STATUS_SCHEDULED).count(), 0)
