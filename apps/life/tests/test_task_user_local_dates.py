# ==============================================================================
# File: apps/life/tests/test_task_user_local_dates.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: User-local temporal certification for the canonical Task authority
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-23
# ==============================================================================
"""
User-Local Temporal Semantics — Task slice.

PROVEN DEFECT (2026-07-23): `TaskQueries.overdue/due_today/due_tomorrow/due_future`
documented "user timezone" but defaulted to `timezone.localdate()` — the SERVER date
(settings.TIME_ZONE = UTC). At 8 PM Pacific (03:00 UTC the next day):

    due_today(user) -> ["Due on the user's tomorrow"]     # wrong day
    overdue(user)   -> ["Due on the user's today"]        # nothing IS overdue

Real consumers relied on that default — the CoS executive context
(`executive_interpretation`) and `situation_computer`. "Due today" and "overdue" are
judgements about the USER's calendar, so they now resolve through
`apps.core.truth.calendar_day`.

Category B (user-local calendar truth) per the temporal-use classification.
"""
from datetime import date, datetime, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone as dj_tz

from apps.core.truth import calendar_day as cal
from apps.life.models import Task
from apps.life.services.task_queries import TaskQueries
from apps.users.models import User

ZONES = ["UTC", "America/New_York", "America/Chicago", "America/Denver",
         "America/Los_Angeles", "Pacific/Honolulu", "Europe/London",
         "Asia/Kolkata", "Australia/Sydney"]


def _user(email, tz_name):
    u = User.objects.create_user(email=email, password="x")
    u.preferences.timezone = tz_name
    u.preferences.save()
    return u


def _at(utc_iso):
    return mock.patch.object(
        dj_tz, "now",
        return_value=datetime.fromisoformat(utc_iso).replace(tzinfo=ZoneInfo("UTC")))


class TaskDayQueriesAreUserLocalTests(TestCase):

    def test_evening_before_utc_midnight_uses_the_users_day(self):
        """THE proven defect: 8 PM Pacific, UTC already tomorrow."""
        u = _user("pt@test.com", "America/Los_Angeles")
        t_today = Task.objects.create(user=u, title="user-today",
                                      due_date=date(2026, 7, 22))
        Task.objects.create(user=u, title="user-tomorrow", due_date=date(2026, 7, 23))
        with _at("2026-07-23T03:00:00"):
            self.assertEqual(cal.today(u), date(2026, 7, 22))
            self.assertEqual(dj_tz.localdate(), date(2026, 7, 23))   # server disagrees
            self.assertEqual([t.title for t in TaskQueries.due_today(u)], ["user-today"])
            self.assertEqual(list(TaskQueries.overdue(u)), [])
            self.assertEqual([t.title for t in TaskQueries.due_tomorrow(u)],
                             ["user-tomorrow"])
        self.assertTrue(Task.objects.filter(pk=t_today.pk).exists())

    def test_after_the_users_midnight_the_day_advances_once(self):
        u = _user("pt2@test.com", "America/Los_Angeles")
        Task.objects.create(user=u, title="jul22", due_date=date(2026, 7, 22))
        Task.objects.create(user=u, title="jul23", due_date=date(2026, 7, 23))
        with _at("2026-07-23T08:00:00"):          # 01:00 PT on the 23rd
            self.assertEqual(cal.today(u), date(2026, 7, 23))
            self.assertEqual([t.title for t in TaskQueries.due_today(u)], ["jul23"])
            self.assertEqual([t.title for t in TaskQueries.overdue(u)], ["jul22"])

    def test_ahead_of_utc_zone(self):
        """Sydney is ahead: its local day rolls over BEFORE UTC's."""
        u = _user("syd@test.com", "Australia/Sydney")
        Task.objects.create(user=u, title="syd-today", due_date=date(2026, 7, 23))
        with _at("2026-07-22T22:00:00"):          # 08:00 on the 23rd in Sydney
            self.assertEqual(cal.today(u), date(2026, 7, 23))
            self.assertEqual([t.title for t in TaskQueries.due_today(u)], ["syd-today"])

    def test_every_zone_gets_its_own_due_today(self):
        with _at("2026-07-23T02:00:00"):
            for tz_name in ZONES:
                u = _user(f"z_{tz_name.replace('/', '_')}@test.com", tz_name)
                local = cal.today(u)
                Task.objects.create(user=u, title="mine", due_date=local)
                self.assertEqual([t.title for t in TaskQueries.due_today(u)],
                                 ["mine"], tz_name)

    def test_explicit_as_of_is_still_honored(self):
        """The fix changes only the DEFAULT; an explicit date must win."""
        u = _user("explicit@test.com", "America/Los_Angeles")
        Task.objects.create(user=u, title="jul01", due_date=date(2026, 7, 1))
        with _at("2026-07-23T03:00:00"):
            self.assertEqual([t.title for t in TaskQueries.due_today(
                u, as_of=date(2026, 7, 1))], ["jul01"])

    def test_dst_and_calendar_edges(self):
        u = _user("dst@test.com", "America/New_York")
        Task.objects.create(user=u, title="springfwd", due_date=date(2026, 3, 8))
        with _at("2026-03-09T02:00:00"):          # 22:00 Mar 8 EDT
            self.assertEqual([t.title for t in TaskQueries.due_today(u)], ["springfwd"])
        Task.objects.create(user=u, title="nye", due_date=date(2026, 12, 31))
        with _at("2027-01-01T04:00:00"):          # 23:00 Dec 31 EST
            self.assertEqual([t.title for t in TaskQueries.due_today(u)], ["nye"])
        Task.objects.create(user=u, title="leap", due_date=date(2028, 2, 29))
        with _at("2028-03-01T04:00:00"):          # 23:00 Feb 29 EST
            self.assertEqual([t.title for t in TaskQueries.due_today(u)], ["leap"])

    def test_month_rollover(self):
        u = _user("month@test.com", "America/Denver")
        Task.objects.create(user=u, title="jul31", due_date=date(2026, 7, 31))
        with _at("2026-08-01T04:00:00"):          # 22:00 Jul 31 MDT
            self.assertEqual([t.title for t in TaskQueries.due_today(u)], ["jul31"])
            self.assertEqual(list(TaskQueries.overdue(u)), [])


class InstantVersusDayAttributionTests(TestCase):
    """PHASE 5 — the absolute instant is preserved; the CALENDAR ATTRIBUTION is derived."""

    def test_a_record_keeps_its_utc_instant_but_attributes_to_the_local_day(self):
        u = _user("instant@test.com", "America/New_York")
        # 2026-07-24T03:00Z == 2026-07-23 11:00 PM EDT
        created = datetime(2026, 7, 24, 3, 0, tzinfo=ZoneInfo("UTC"))
        task = Task.objects.create(user=u, title="late night",
                                   due_date=date(2026, 7, 23))
        Task.objects.filter(pk=task.pk).update(created_at=created)
        task.refresh_from_db()

        # The stored instant is untouched — still July 24 in UTC.
        self.assertEqual(task.created_at.astimezone(ZoneInfo("UTC")).date(),
                         date(2026, 7, 24))
        # Its USER-LOCAL calendar attribution is July 23.
        self.assertEqual(task.created_at.astimezone(cal.tz(u)).date(),
                         date(2026, 7, 23))
        # And a calendar-relative question at 11:05 PM local resolves to July 23.
        with _at("2026-07-24T03:05:00"):
            self.assertEqual(cal.today(u), date(2026, 7, 23))
            self.assertEqual([t.title for t in TaskQueries.due_today(u)],
                             ["late night"])

    def test_precision_and_timezone_are_not_rewritten(self):
        u = _user("precision@test.com", "Asia/Kolkata")
        created = datetime(2026, 7, 24, 3, 0, 45, 123456, tzinfo=ZoneInfo("UTC"))
        task = Task.objects.create(user=u, title="precise", due_date=date(2026, 7, 24))
        Task.objects.filter(pk=task.pk).update(created_at=created)
        task.refresh_from_db()
        self.assertEqual(task.created_at.astimezone(ZoneInfo("UTC")), created)
        self.assertIsNotNone(task.created_at.tzinfo)
        self.assertEqual(task.created_at.astimezone(ZoneInfo("UTC")).microsecond, 123456)


class HistorySearchWindowTests(TestCase):
    """Category C — a rolling window in CALENDAR days anchors to the user's day."""

    def test_rolling_window_anchors_to_the_users_today(self):
        from apps.ai.cos_services.history_search import _parse_timeframe
        u = _user("hs@test.com", "America/Los_Angeles")
        with _at("2026-07-23T03:00:00"):          # 8 PM Jul 22 PT
            start, end = _parse_timeframe("7d", u)
            self.assertEqual(end, date(2026, 7, 22))       # the USER's today
            self.assertEqual(start, date(2026, 7, 15))
            # Without a user it falls back to the server date (documented behaviour).
            self.assertEqual(_parse_timeframe("7d")[1], date(2026, 7, 23))

    def test_named_window_also_anchors_locally(self):
        from apps.ai.cos_services.history_search import _parse_timeframe
        u = _user("hs2@test.com", "America/Los_Angeles")
        with _at("2026-07-23T03:00:00"):
            self.assertEqual(_parse_timeframe("week", u)[1], date(2026, 7, 22))


class TaskSurfaceAgreementTests(TestCase):
    """PHASE 6 — every surface for the task slice agrees on the same user-local day.

    Canonical query producer · SAE snapshot projection · model-facing domain-state tool ·
    date-scoped history retrieval. Run at a boundary instant where the server date
    DISAGREES with the user's, so any surface still using the server clock fails here.
    """

    def setUp(self):
        self.user = _user("agree@test.com", "America/Los_Angeles")
        # user-local Jul 22 (PT) while UTC is already Jul 23
        self.local_day = date(2026, 7, 22)
        Task.objects.create(user=self.user, title="due-today",
                            due_date=self.local_day)
        Task.objects.create(user=self.user, title="due-tomorrow",
                            due_date=self.local_day + timedelta(days=1))

    def test_all_task_surfaces_agree_on_the_users_day(self):
        from apps.ai.cos_services.domain_state import get_domain_state
        from apps.core.ai_state.state_engine import rebuild_user_state

        with _at("2026-07-23T03:00:00"):
            self.assertEqual(cal.today(self.user), self.local_day)
            self.assertNotEqual(dj_tz.localdate(), self.local_day)   # server disagrees

            canonical = sorted(TaskQueries.due_today(self.user)
                               .values_list("title", flat=True))
            rebuild_user_state(self.user)
            env = get_domain_state(self.user, "life")
            snapshot = sorted(env["state"].get("tasks_due_today") or [])

            self.assertEqual(canonical, ["due-today"])
            self.assertEqual(snapshot, ["due-today"],
                             f"snapshot disagrees with the canonical producer: {snapshot}")
            # The snapshot declares the very day it describes, and it is the user's.
            self.assertEqual(env["state"]["day_state_date"], self.local_day.isoformat())
            self.assertEqual(env["day_freshness"], "current")
            self.assertEqual(env["user_local_date"], self.local_day.isoformat())
            self.assertEqual(env["timezone"], "America/Los_Angeles")

    def test_overdue_agrees_across_canonical_and_snapshot(self):
        from apps.ai.cos_services.domain_state import get_domain_state
        from apps.core.ai_state.state_engine import rebuild_user_state
        with _at("2026-07-23T03:00:00"):
            rebuild_user_state(self.user)
            env = get_domain_state(self.user, "life")
            self.assertEqual(list(TaskQueries.overdue(self.user)), [])
            # Nothing is overdue on the user's day — the snapshot must say the same.
            self.assertFalse(env["state"].get("overdue_tasks_detail"))
