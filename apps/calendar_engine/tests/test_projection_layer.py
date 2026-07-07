"""
Calendar projection + Availability Blocks tests.

Covers the reduced Calendar evolution (no new projection/registry/service layers):
  - RecurrenceRule.expand() applies RecurrenceException (was a dead no-op before
    2026-07-07) — the one calendar-native recurrence engine.
  - AvailabilityBlock recurrence + Outlook this/future/series edits via JSON
    exceptions and model methods.
  - _get_events_in_range projects availability into the existing event stream,
    flagged event_kind='availability'; due items are never given a fake time.
  - Manual events stay calendar-native (no auto-Task manufactured).
  - Existing endpoints (/api/today/, availability CRUD) work end-to-end.

Governing note: docs/WLJ_CALENDAR_PROJECTION_ARCHITECTURE.md
"""
import datetime as dt
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.utils import timezone

from apps.calendar_engine.models import (
    AvailabilityBlock,
    CalendarEvent,
    RecurrenceException,
    RecurrenceRule,
)
from apps.calendar_engine.views import _get_events_in_range

User = get_user_model()
TZ = "America/Chicago"


def _user(email=None):
    from apps.users.models import TermsAcceptance
    email = email or f"proj_{uuid4().hex[:8]}@example.com"
    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.timezone = TZ
    user.preferences.save()
    return user


def _ce(**kwargs):
    kwargs.setdefault("idempotency_key", uuid4().hex)
    return CalendarEvent.objects.create(**kwargs)


def _range(days=1):
    tz = timezone.get_current_timezone()
    today = timezone.localdate()
    start = timezone.make_aware(dt.datetime.combine(today, dt.time.min), tz)
    end = timezone.make_aware(dt.datetime.combine(today + dt.timedelta(days=days - 1), dt.time.max), tz)
    return today, start, end


# ── RecurrenceException is applied (the dead-model fix) ──

class RecurrenceExceptionTests(TestCase):
    def setUp(self):
        self.user = _user()
        tz = timezone.get_current_timezone()
        anchor = timezone.make_aware(
            dt.datetime.combine(timezone.localdate(), dt.time(9, 0)), tz,
        )
        self.event = _ce(user=self.user, title="Daily Standup",
                         start_dt=anchor, end_dt=anchor + dt.timedelta(minutes=30))
        self.rule = RecurrenceRule.objects.create(
            event=self.event, frequency=RecurrenceRule.FREQ_DAILY, interval=1, timezone=TZ,
        )
        self.win_start = timezone.make_aware(
            dt.datetime.combine(timezone.localdate(), dt.time.min), tz)
        self.win_end = self.win_start + dt.timedelta(days=7)

    def test_cancel_exception_removes_occurrence(self):
        occ = self.event.recurrence.get_occurrences(self.win_start, self.win_end)
        self.assertEqual(len(occ), 7)
        RecurrenceException.objects.create(
            event=self.event, original_start_dt=occ[2][0], is_canceled=True)
        after = self.event.recurrence.get_occurrences(self.win_start, self.win_end)
        self.assertEqual(len(after), 6)
        self.assertNotIn(occ[2][0], [o[0] for o in after])

    def test_move_exception_relocates_occurrence(self):
        occ = self.event.recurrence.get_occurrences(self.win_start, self.win_end)
        target = occ[1][0]
        moved = target + dt.timedelta(hours=5)
        RecurrenceException.objects.create(
            event=self.event, original_start_dt=target,
            new_start_dt=moved, new_end_dt=moved + dt.timedelta(minutes=30))
        after = [o[0] for o in self.event.recurrence.get_occurrences(self.win_start, self.win_end)]
        self.assertIn(moved, after)
        self.assertNotIn(target, after)


# ── AvailabilityBlock recurrence + Outlook edits ──

class AvailabilityTests(TestCase):
    def setUp(self):
        self.user = _user()
        tz = timezone.get_current_timezone()
        monday = timezone.localdate() - dt.timedelta(days=timezone.localdate().weekday())
        self.anchor = timezone.make_aware(dt.datetime.combine(monday, dt.time(7, 30)), tz)
        self.block = AvailabilityBlock.objects.create(
            user=self.user, label="Work", kind=AvailabilityBlock.KIND_UNAVAILABLE,
            start_dt=self.anchor, end_dt=self.anchor + dt.timedelta(hours=10, minutes=30),
            frequency=AvailabilityBlock.FREQ_WEEKLY, byweekday=[1, 2, 3, 4, 5], timezone=TZ)
        self.win_start = self.anchor - dt.timedelta(hours=1)
        self.win_end = self.anchor + dt.timedelta(days=6)

    def test_weekly_expansion(self):
        self.assertEqual(len(self.block.get_occurrences(self.win_start, self.win_end)), 5)

    def test_one_off_block(self):
        tz = timezone.get_current_timezone()
        s = timezone.make_aware(dt.datetime.combine(timezone.localdate(), dt.time(14, 0)), tz)
        b = AvailabilityBlock.objects.create(
            user=self.user, label="PTO", kind=AvailabilityBlock.KIND_UNAVAILABLE,
            start_dt=s, end_dt=s + dt.timedelta(hours=2), timezone=TZ)
        self.assertFalse(b.is_recurring)
        self.assertEqual(len(b.get_occurrences(s - dt.timedelta(hours=1), s + dt.timedelta(hours=3))), 1)

    def test_cancel_occurrence_json(self):
        occ = self.block.get_occurrences(self.win_start, self.win_end)
        self.block.cancel_occurrence(occ[2][0])  # cancel Wednesday
        self.assertEqual(len(self.block.exceptions), 1)
        self.assertEqual(len(self.block.get_occurrences(self.win_start, self.win_end)), 4)

    def test_move_occurrence_json(self):
        occ = self.block.get_occurrences(self.win_start, self.win_end)
        target = occ[1][0]
        moved = target + dt.timedelta(hours=2)
        self.block.move_occurrence(target, moved, moved + dt.timedelta(hours=1))
        after = [o[0] for o in self.block.get_occurrences(self.win_start, self.win_end)]
        self.assertIn(moved, after)
        self.assertNotIn(target, after)

    def test_split_future(self):
        wed = self.anchor + dt.timedelta(days=2)
        new_block = self.block.split_future(wed, label="Work (new hours)")
        self.block.refresh_from_db()
        self.assertIsNotNone(self.block.until_dt)
        self.assertLess(self.block.until_dt, wed)
        self.assertEqual(new_block.label, "Work (new hours)")
        self.assertEqual(new_block.start_dt, wed)


# ── Availability projects into the existing event stream ──

class ProjectionStreamTests(TestCase):
    def setUp(self):
        self.user = _user()
        self.today, self.start, self.end = _range()
        tz = timezone.get_current_timezone()
        noon = timezone.make_aware(dt.datetime.combine(self.today, dt.time(12, 0)), tz)
        _ce(user=self.user, title="Lunch", start_dt=noon, end_dt=noon + dt.timedelta(hours=1))
        eod = timezone.make_aware(dt.datetime.combine(self.today, dt.time(23, 59)), tz)
        _ce(user=self.user, title="Due: Repair Fridge", start_dt=eod,
            end_dt=eod + dt.timedelta(minutes=1), is_all_day=True,
            event_kind=CalendarEvent.KIND_DEADLINE_MARKER,
            source_type=CalendarEvent.SOURCE_TASK, source_id="777")
        work = timezone.make_aware(dt.datetime.combine(self.today, dt.time(8, 0)), tz)
        AvailabilityBlock.objects.create(
            user=self.user, label="Work", kind=AvailabilityBlock.KIND_UNAVAILABLE,
            start_dt=work, end_dt=work + dt.timedelta(hours=9), timezone=TZ)

    def test_stream_includes_availability_and_flags_kinds(self):
        events = _get_events_in_range(self.user, self.start, self.end)
        kinds = {e["event_kind"] for e in events}
        self.assertIn("availability", kinds)
        self.assertIn(CalendarEvent.KIND_DEADLINE_MARKER, kinds)
        avail = [e for e in events if e["event_kind"] == "availability"][0]
        self.assertEqual(avail["source_type"], "availability")
        self.assertFalse(avail["is_available"])


# ── Manual events stay calendar-native (auto-Task retired) ──

class NativeEventTests(TestCase):
    def test_manual_event_creates_no_backing_task(self):
        from apps.calendar_engine.services.calendar_mutation_service import CalendarMutationService
        from apps.life.models import Task
        user = _user()
        tz = timezone.get_current_timezone()
        start = timezone.make_aware(dt.datetime.combine(timezone.localdate(), dt.time(15, 0)), tz)
        before = Task.objects.filter(user=user).count()
        result = CalendarMutationService(user).create(
            title="Solo Calendar Event", start_dt=start,
            end_dt=start + dt.timedelta(hours=1), force=True)
        self.assertTrue(result.success)
        self.assertEqual(result.event.source_type, CalendarEvent.SOURCE_NONE)
        self.assertEqual(Task.objects.filter(user=user).count(), before)


# ── Endpoint smoke + query budget ──

class EndpointTests(TestCase):
    def setUp(self):
        self.user = _user()
        self.client.force_login(self.user)

    def test_today_endpoint_includes_availability(self):
        tz = timezone.get_current_timezone()
        s = timezone.make_aware(dt.datetime.combine(timezone.localdate(), dt.time(8, 0)), tz)
        AvailabilityBlock.objects.create(
            user=self.user, label="Work", kind=AvailabilityBlock.KIND_UNAVAILABLE,
            start_dt=s, end_dt=s + dt.timedelta(hours=9), timezone=TZ)
        resp = self.client.get("/calendar/api/today/")
        self.assertEqual(resp.status_code, 200)
        kinds = {e["event_kind"] for e in resp.json()["events"]}
        self.assertIn("availability", kinds)

    def test_availability_crud_roundtrip(self):
        tz = timezone.get_current_timezone()
        s = timezone.make_aware(dt.datetime.combine(timezone.localdate(), dt.time(9, 0)), tz)
        e = s + dt.timedelta(hours=8)
        create = self.client.post(
            "/calendar/api/availability/",
            data={"label": "Work", "kind": "unavailable",
                  "start_dt": s.isoformat(), "end_dt": e.isoformat(),
                  "frequency": "weekly", "byweekday": [1, 2, 3, 4, 5]},
            content_type="application/json")
        self.assertEqual(create.status_code, 201)
        block_id = create.json()["block"]["id"]
        self.assertEqual(len(self.client.get("/calendar/api/availability/").json()["blocks"]), 1)
        delete = self.client.delete(
            f"/calendar/api/availability/{block_id}/",
            data={"scope": "series"}, content_type="application/json")
        self.assertEqual(delete.status_code, 200)
        self.assertEqual(len(self.client.get("/calendar/api/availability/").json()["blocks"]), 0)

    def test_availability_page_renders(self):
        self.assertEqual(self.client.get("/calendar/availability/").status_code, 200)

    def _mk_work_block(self):
        """Create Work Mon–Fri 7:30–18:00 recurring unavailable via the API."""
        tz = timezone.get_current_timezone()
        today = timezone.localdate()
        monday = today - dt.timedelta(days=today.weekday())
        s = timezone.make_aware(dt.datetime.combine(monday, dt.time(7, 30)), tz)
        e = timezone.make_aware(dt.datetime.combine(monday, dt.time(18, 0)), tz)
        resp = self.client.post(
            "/calendar/api/availability/",
            data={"label": "Work", "kind": "unavailable",
                  "start_dt": s.isoformat(), "end_dt": e.isoformat(),
                  "frequency": "weekly", "byweekday": [1, 2, 3, 4, 5]},
            content_type="application/json")
        self.assertEqual(resp.status_code, 201)
        return resp.json()["block"]["id"]

    def _occurrences(self, block_id, days=14):
        resp = self.client.get(f"/calendar/api/availability/{block_id}/occurrences/?days={days}")
        self.assertEqual(resp.status_code, 200)
        return resp.json()["occurrences"]

    def _weekday(self, iso):  # 0=Mon
        return dt.date.fromisoformat(iso[:10]).weekday()

    def test_scenario_delete_one_friday(self):
        """Delete only THIS Friday → Mondays remain, future Fridays remain."""
        bid = self._mk_work_block()
        occ = self._occurrences(bid)
        fridays = [o for o in occ if self._weekday(o["start_dt"]) == 4]
        self.assertGreaterEqual(len(fridays), 2)
        first_friday = fridays[0]["start_dt"]

        resp = self.client.delete(
            f"/calendar/api/availability/{bid}/",
            data={"scope": "occurrence", "occurrence_start": first_friday},
            content_type="application/json")
        self.assertEqual(resp.status_code, 200)

        after = self._occurrences(bid)
        self.assertNotIn(first_friday, [o["start_dt"] for o in after])
        # future Friday + all Mondays still present
        self.assertTrue([o for o in after if self._weekday(o["start_dt"]) == 4])
        self.assertEqual(len([o for o in after if self._weekday(o["start_dt"]) == 0]), 2)

    def test_scenario_modify_one_tuesday(self):
        """Modify one Tuesday's time → next Tuesday unchanged, series intact."""
        bid = self._mk_work_block()
        occ = self._occurrences(bid)
        tuesdays = [o for o in occ if self._weekday(o["start_dt"]) == 1]
        first_tue = tuesdays[0]["start_dt"]
        day = first_tue[:10]

        resp = self.client.patch(
            f"/calendar/api/availability/{bid}/",
            data={"scope": "occurrence", "occurrence_start": first_tue,
                  "start_dt": day + "T09:00", "end_dt": day + "T17:00"},
            content_type="application/json")
        self.assertEqual(resp.status_code, 200)

        after = self._occurrences(bid)
        moved = [o for o in after if o["start_dt"][:10] == day]
        self.assertEqual(len(moved), 1)
        self.assertEqual(moved[0]["start_dt"][11:16], "09:00")
        # next Tuesday still at 07:30, series length unchanged
        next_tue = [o for o in after if self._weekday(o["start_dt"]) == 1 and o["start_dt"][:10] != day]
        self.assertTrue(next_tue)
        self.assertEqual(next_tue[0]["start_dt"][11:16], "07:30")
        self.assertEqual(len(after), len(occ))

    def test_scenario_this_and_future_delete(self):
        """End the series from a date forward → earlier occurrences remain."""
        bid = self._mk_work_block()
        occ = self._occurrences(bid)
        boundary = occ[5]["start_dt"]  # some mid occurrence
        resp = self.client.delete(
            f"/calendar/api/availability/{bid}/",
            data={"scope": "future", "occurrence_start": boundary},
            content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        after = self._occurrences(bid)
        self.assertEqual(len(after), 5)  # only the 5 before the boundary

    def test_range_query_budget(self):
        tz = timezone.get_current_timezone()
        base = timezone.make_aware(dt.datetime.combine(timezone.localdate(), dt.time(9, 0)), tz)
        rec = _ce(user=self.user, title="Standup", start_dt=base, end_dt=base + dt.timedelta(minutes=15))
        RecurrenceRule.objects.create(event=rec, frequency=RecurrenceRule.FREQ_DAILY, interval=1, timezone=TZ)
        AvailabilityBlock.objects.create(
            user=self.user, label="Work", kind=AvailabilityBlock.KIND_UNAVAILABLE,
            start_dt=base, end_dt=base + dt.timedelta(hours=9),
            frequency=AvailabilityBlock.FREQ_WEEKLY, byweekday=[1, 2, 3, 4, 5], timezone=TZ)
        start = base - dt.timedelta(hours=9)
        end = base + dt.timedelta(days=6)
        with CaptureQueriesContext(connection) as ctx:
            _get_events_in_range(self.user, start, end)
        # Bounded: direct + recurring + availability. Profile COUNT (SQLite hides
        # Postgres N+1). Generous ceiling that still catches per-occurrence blowups.
        self.assertLess(len(ctx.captured_queries), 12,
                        f"range read issued {len(ctx.captured_queries)} queries")
