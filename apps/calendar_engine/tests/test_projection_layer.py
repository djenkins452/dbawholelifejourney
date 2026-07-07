"""
Calendar Projection Layer tests (Phases 0–3).

Covers the Calendar Projection Law invariants:
  - TimeProjection splits time into committed / due / constraints lanes.
  - Editing routes to the OWNING domain (never the cache); native edits in place.
  - RecurrenceException is now applied (was a dead no-op before 2026-07-07).
  - AvailabilityBlock recurrence + Outlook this/future/series semantics.
  - Manual events stay calendar-native (no auto-Task manufactured).
  - Projection reads stay within a query budget (F5 request-path safety).

Governing doc: docs/WLJ_CALENDAR_PROJECTION_ARCHITECTURE.md
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
    AvailabilityException,
    CalendarEvent,
    RecurrenceException,
    RecurrenceRule,
)
from apps.calendar_engine.services.editor_route import resolve_editor_route
from apps.calendar_engine.services.recurrence_engine import expand_occurrences
from apps.calendar_engine.services.time_projection import (
    TimeProjection,
    LANE_COMMITTED,
    LANE_DUE,
    LANE_CONSTRAINT,
)

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


def _today_range():
    tz = timezone.get_current_timezone()
    today = timezone.localdate()
    start = timezone.make_aware(dt.datetime.combine(today, dt.time.min), tz)
    end = timezone.make_aware(dt.datetime.combine(today, dt.time.max), tz)
    return today, start, end


# ──────────────────────────────────────────────────────────
# Recurrence exception application (the dead-model fix)
# ──────────────────────────────────────────────────────────

class RecurrenceExceptionTests(TestCase):
    def setUp(self):
        self.user = _user()
        tz = timezone.get_current_timezone()
        anchor = timezone.make_aware(
            dt.datetime.combine(timezone.localdate(), dt.time(9, 0)), tz,
        )
        self.event = _ce(
            user=self.user, title="Daily Standup",
            start_dt=anchor, end_dt=anchor + dt.timedelta(minutes=30),
        )
        self.rule = RecurrenceRule.objects.create(
            event=self.event, frequency=RecurrenceRule.FREQ_DAILY, interval=1,
            timezone=TZ,
        )

    def test_cancel_exception_removes_occurrence(self):
        tz = timezone.get_current_timezone()
        start = timezone.make_aware(dt.datetime.combine(timezone.localdate(), dt.time.min), tz)
        end = start + dt.timedelta(days=7)  # covers 7 daily 09:00 occurrences

        occ_before = self.event.recurrence.get_occurrences(start, end)
        self.assertEqual(len(occ_before), 7)

        # Cancel the 3rd occurrence.
        target = occ_before[2][0]
        RecurrenceException.objects.create(
            event=self.event, original_start_dt=target, is_canceled=True,
        )
        occ_after = self.event.recurrence.get_occurrences(start, end)
        self.assertEqual(len(occ_after), 6)
        starts = [o[0] for o in occ_after]
        self.assertNotIn(target, starts)

    def test_move_exception_relocates_occurrence(self):
        tz = timezone.get_current_timezone()
        start = timezone.make_aware(dt.datetime.combine(timezone.localdate(), dt.time.min), tz)
        end = start + dt.timedelta(days=3)

        occ = self.event.recurrence.get_occurrences(start, end)
        target = occ[1][0]
        moved_start = target + dt.timedelta(hours=5)
        RecurrenceException.objects.create(
            event=self.event, original_start_dt=target,
            new_start_dt=moved_start, new_end_dt=moved_start + dt.timedelta(minutes=30),
        )
        occ_after = self.event.recurrence.get_occurrences(start, end)
        starts = [o[0] for o in occ_after]
        self.assertIn(moved_start, starts)
        self.assertNotIn(target, starts)


# ──────────────────────────────────────────────────────────
# Editor routing — edit the owner, never the cache
# ──────────────────────────────────────────────────────────

class EditorRouteTests(TestCase):
    def test_task_routes_to_owning_domain(self):
        route = resolve_editor_route("task", "42")
        self.assertFalse(route.edit_in_place)
        self.assertIsNotNone(route.url)
        self.assertIn("/42/", route.url)

    def test_native_event_edits_in_place(self):
        route = resolve_editor_route("none", "")
        self.assertTrue(route.edit_in_place)
        self.assertIsNone(route.url)

    def test_availability_edits_in_place(self):
        route = resolve_editor_route("availability", is_availability=True)
        self.assertTrue(route.edit_in_place)

    def test_unknown_source_is_non_navigable(self):
        route = resolve_editor_route("mystery", "1")
        self.assertFalse(route.edit_in_place)
        self.assertIsNone(route.url)

    def test_landing_route_for_indirect_source(self):
        route = resolve_editor_route("medicine_schedule", "9")
        self.assertFalse(route.edit_in_place)
        self.assertIsNotNone(route.url)  # domain landing, not per-object


# ──────────────────────────────────────────────────────────
# TimeProjection lanes
# ──────────────────────────────────────────────────────────

class ProjectionLaneTests(TestCase):
    def setUp(self):
        self.user = _user()
        self.today, self.start, self.end = _today_range()
        tz = timezone.get_current_timezone()
        noon = timezone.make_aware(dt.datetime.combine(self.today, dt.time(12, 0)), tz)

        # committed: a manual timed event
        _ce(user=self.user, title="Lunch with Sam", start_dt=noon,
            end_dt=noon + dt.timedelta(hours=1), event_kind=CalendarEvent.KIND_MANUAL)

        # due: a deadline marker (due, no execution time)
        eod = timezone.make_aware(dt.datetime.combine(self.today, dt.time(23, 59)), tz)
        _ce(user=self.user, title="Due: Repair Refrigerator", start_dt=eod,
            end_dt=eod + dt.timedelta(minutes=1), is_all_day=True,
            event_kind=CalendarEvent.KIND_DEADLINE_MARKER,
            source_type=CalendarEvent.SOURCE_TASK, source_id="777")

        # constraint: an availability block
        work_start = timezone.make_aware(dt.datetime.combine(self.today, dt.time(8, 0)), tz)
        AvailabilityBlock.objects.create(
            user=self.user, label="Work", kind=AvailabilityBlock.KIND_UNAVAILABLE,
            start_dt=work_start, end_dt=work_start + dt.timedelta(hours=9), timezone=TZ,
        )

    def test_lanes_are_separated(self):
        result = TimeProjection.for_range(self.user, self.start, self.end)
        self.assertEqual(len(result.committed), 1)
        self.assertEqual(len(result.due), 1)
        self.assertEqual(len(result.constraints), 1)
        self.assertEqual(result.committed[0].lane, LANE_COMMITTED)
        self.assertEqual(result.due[0].lane, LANE_DUE)
        self.assertEqual(result.constraints[0].lane, LANE_CONSTRAINT)

    def test_due_block_carries_owning_route(self):
        result = TimeProjection.for_range(self.user, self.start, self.end)
        due = result.due[0]
        self.assertEqual(due.source_type, "task")
        self.assertFalse(due.editor_route["edit_in_place"])
        self.assertIsNotNone(due.editor_route["url"])

    def test_no_fabricated_time_on_timeline(self):
        # The deadline marker must NOT appear in the committed (timeline) lane.
        result = TimeProjection.for_range(self.user, self.start, self.end)
        committed_titles = [b.title for b in result.committed]
        self.assertNotIn("Due: Repair Refrigerator", committed_titles)


# ──────────────────────────────────────────────────────────
# Availability recurrence + Outlook semantics
# ──────────────────────────────────────────────────────────

class AvailabilityTests(TestCase):
    def setUp(self):
        self.user = _user()
        tz = timezone.get_current_timezone()
        # Anchor on a Monday for deterministic weekly expansion.
        monday = timezone.localdate() - dt.timedelta(days=timezone.localdate().weekday())
        self.anchor = timezone.make_aware(dt.datetime.combine(monday, dt.time(7, 30)), tz)
        self.block = AvailabilityBlock.objects.create(
            user=self.user, label="Work", kind=AvailabilityBlock.KIND_UNAVAILABLE,
            start_dt=self.anchor, end_dt=self.anchor + dt.timedelta(hours=10, minutes=30),
            frequency=AvailabilityBlock.FREQ_WEEKLY, byweekday=[1, 2, 3, 4, 5], timezone=TZ,
        )

    def test_weekly_expansion(self):
        start = self.anchor - dt.timedelta(hours=1)
        end = self.anchor + dt.timedelta(days=6)
        occ = self.block.get_occurrences(start, end)
        # Mon–Fri within a 7-day window = 5 occurrences.
        self.assertEqual(len(occ), 5)

    def test_cancel_occurrence(self):
        from apps.calendar_engine.services import availability_service as svc
        start = self.anchor - dt.timedelta(hours=1)
        end = self.anchor + dt.timedelta(days=6)
        occ = self.block.get_occurrences(start, end)
        svc.cancel_occurrence(self.block, occ[2][0])  # cancel Wednesday
        self.assertEqual(len(self.block.get_occurrences(start, end)), 4)

    def test_split_future(self):
        from apps.calendar_engine.services import availability_service as svc
        # Split at Wednesday: original keeps Mon/Tue, new block owns Wed onward.
        wed = self.anchor + dt.timedelta(days=2)
        new_block = svc.split_future(self.block, wed, label="Work (new hours)")
        self.block.refresh_from_db()
        self.assertIsNotNone(self.block.until_dt)
        self.assertLess(self.block.until_dt, wed)
        self.assertEqual(new_block.label, "Work (new hours)")
        self.assertEqual(new_block.start_dt, wed)

    def test_one_off_block(self):
        tz = timezone.get_current_timezone()
        s = timezone.make_aware(dt.datetime.combine(timezone.localdate(), dt.time(14, 0)), tz)
        b = AvailabilityBlock.objects.create(
            user=self.user, label="PTO", kind=AvailabilityBlock.KIND_UNAVAILABLE,
            start_dt=s, end_dt=s + dt.timedelta(hours=2), timezone=TZ,
        )
        self.assertFalse(b.is_recurring)
        occ = b.get_occurrences(s - dt.timedelta(hours=1), s + dt.timedelta(hours=3))
        self.assertEqual(len(occ), 1)


# ──────────────────────────────────────────────────────────
# Manual events stay calendar-native (auto-Task retired)
# ──────────────────────────────────────────────────────────

class NativeEventTests(TestCase):
    def test_manual_event_creates_no_backing_task(self):
        from apps.calendar_engine.services.calendar_mutation_service import CalendarMutationService
        from apps.life.models import Task

        user = _user()
        tz = timezone.get_current_timezone()
        start = timezone.make_aware(
            dt.datetime.combine(timezone.localdate(), dt.time(15, 0)), tz,
        )
        before = Task.objects.filter(user=user).count()
        result = CalendarMutationService(user).create(
            title="Solo Calendar Event", start_dt=start,
            end_dt=start + dt.timedelta(hours=1), force=True,
        )
        self.assertTrue(result.success)
        self.assertEqual(result.event.source_type, CalendarEvent.SOURCE_NONE)
        self.assertEqual(Task.objects.filter(user=user).count(), before)


# ──────────────────────────────────────────────────────────
# F5 — projection stays within a query budget
# ──────────────────────────────────────────────────────────

class ProjectionQueryBudgetTests(TestCase):
    def test_week_projection_query_budget(self):
        user = _user()
        tz = timezone.get_current_timezone()
        base = timezone.make_aware(
            dt.datetime.combine(timezone.localdate(), dt.time(9, 0)), tz,
        )
        # Seed a mix: recurring event, several one-offs, availability blocks.
        rec = _ce(user=user, title="Standup", start_dt=base,
                  end_dt=base + dt.timedelta(minutes=15))
        RecurrenceRule.objects.create(event=rec, frequency=RecurrenceRule.FREQ_DAILY,
                                      interval=1, timezone=TZ)
        for i in range(5):
            s = base + dt.timedelta(days=i, hours=2)
            _ce(user=user, title=f"Event {i}", start_dt=s, end_dt=s + dt.timedelta(hours=1))
        AvailabilityBlock.objects.create(
            user=user, label="Work", kind=AvailabilityBlock.KIND_UNAVAILABLE,
            start_dt=base, end_dt=base + dt.timedelta(hours=9),
            frequency=AvailabilityBlock.FREQ_WEEKLY, byweekday=[1, 2, 3, 4, 5], timezone=TZ,
        )

        start = base - dt.timedelta(hours=9)
        end = base + dt.timedelta(days=6)

        with CaptureQueriesContext(connection) as ctx:
            result = TimeProjection.for_range(user, start, end)
            _ = result.to_dict()
        # Bounded: direct + recurring + availability. Profile COUNT (SQLite hides
        # Postgres N+1). Ceiling is generous but catches per-occurrence blowups.
        self.assertLess(len(ctx.captured_queries), 15,
                        f"projection issued {len(ctx.captured_queries)} queries")
        self.assertTrue(result.committed)
        self.assertTrue(result.constraints)


# ──────────────────────────────────────────────────────────
# HTTP smoke — new endpoints wire up
# ──────────────────────────────────────────────────────────

class EndpointSmokeTests(TestCase):
    def setUp(self):
        self.user = _user()
        self.client.force_login(self.user)

    def test_projection_endpoint(self):
        resp = self.client.get("/calendar/api/projection/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        for key in ("committed", "due", "constraints"):
            self.assertIn(key, data)

    def test_availability_crud_roundtrip(self):
        tz = timezone.get_current_timezone()
        s = timezone.make_aware(dt.datetime.combine(timezone.localdate(), dt.time(9, 0)), tz)
        e = s + dt.timedelta(hours=8)
        create = self.client.post(
            "/calendar/api/availability/",
            data={
                "label": "Work", "kind": "unavailable",
                "start_dt": s.isoformat(), "end_dt": e.isoformat(),
                "frequency": "weekly", "byweekday": [1, 2, 3, 4, 5],
            },
            content_type="application/json",
        )
        self.assertEqual(create.status_code, 201)
        block_id = create.json()["block"]["id"]

        listing = self.client.get("/calendar/api/availability/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.json()["blocks"]), 1)

        delete = self.client.delete(
            f"/calendar/api/availability/{block_id}/",
            data={"scope": "series"}, content_type="application/json",
        )
        self.assertEqual(delete.status_code, 200)
        self.assertEqual(len(self.client.get("/calendar/api/availability/").json()["blocks"]), 0)

    def test_availability_page_renders(self):
        resp = self.client.get("/calendar/availability/")
        self.assertEqual(resp.status_code, 200)
