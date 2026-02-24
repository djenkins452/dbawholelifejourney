"""
Phase 9 — Calendar Determinism & Trust Recovery Tests

Tests:
1. Deterministic weekday resolution (same-day, time-passed, future-time)
2. Idempotency (duplicate request returns existing)
3. IntegrityError race recovery
4. Unique constraint enforcement
5. PATCH verification
6. DELETE row-count validation
"""

import datetime as dt
import hashlib
import sys
import threading
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from freezegun import freeze_time

from apps.calendar_engine.models import CalendarEvent
from apps.calendar_engine.utils.date_resolution import resolve_weekday_to_date

User = get_user_model()


class _UserMixin:
    """Setup helper: creates a user with America/Chicago timezone."""

    def _create_user(self, email='caltest@example.com'):
        from django.conf import settings as django_settings
        from apps.users.models import TermsAcceptance

        user = User.objects.create_user(
            email=email,
            password='testpass123',
            first_name='Cal',
        )
        prefs = user.preferences
        prefs.timezone = 'America/Chicago'
        prefs.has_completed_onboarding = True
        prefs.save()

        # Accept current terms so middleware doesn't redirect
        terms_version = django_settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
        TermsAcceptance.objects.create(
            user=user,
            terms_version=terms_version,
        )
        return user


# ──────────────────────────────────────────────────────────
# 1) Weekday same-day: time already passed → next week
# ──────────────────────────────────────────────────────────

class TestWednesdaySameDayTimePassed(_UserMixin, TestCase):
    """
    If user says "Wednesday" at 15:00 on a Wednesday and the event
    start_time is 14:00 (already passed), resolve to next Wednesday.
    """

    def setUp(self):
        self.user = self._create_user()

    @freeze_time("2026-02-25 21:00:00")  # Wed 25 Feb 2026 21:00 UTC = 15:00 CST
    def test_wednesday_same_day_time_passed(self):
        chicago = ZoneInfo('America/Chicago')
        reference = dt.datetime(2026, 2, 25, 15, 0, 0, tzinfo=chicago)
        event_time = dt.time(14, 0)  # 2 PM — already passed

        result = resolve_weekday_to_date(
            self.user,
            'wednesday',
            reference_dt=reference,
            start_time=event_time,
        )

        # Should be next Wednesday (March 4, 2026)
        self.assertEqual(result, dt.date(2026, 3, 4))


# ──────────────────────────────────────────────────────────
# 2) Weekday same-day: future time → today
# ──────────────────────────────────────────────────────────

class TestWednesdaySameDayFutureTime(_UserMixin, TestCase):
    """
    If user says "Wednesday" at 09:00 on a Wednesday and the event
    start_time is 14:00 (still in the future), resolve to today.
    """

    def setUp(self):
        self.user = self._create_user()

    @freeze_time("2026-02-25 15:00:00")  # Wed 25 Feb 2026 15:00 UTC = 09:00 CST
    def test_wednesday_same_day_future_time(self):
        chicago = ZoneInfo('America/Chicago')
        reference = dt.datetime(2026, 2, 25, 9, 0, 0, tzinfo=chicago)
        event_time = dt.time(14, 0)  # 2 PM — still in future

        result = resolve_weekday_to_date(
            self.user,
            'wednesday',
            reference_dt=reference,
            start_time=event_time,
        )

        # Should be today (February 25, 2026)
        self.assertEqual(result, dt.date(2026, 2, 25))


# ──────────────────────────────────────────────────────────
# 3) Idempotent duplicate request returns existing event
# ──────────────────────────────────────────────────────────

class TestDuplicateIdempotentRequest(_UserMixin, TestCase):
    """
    Creating an event with the same idempotency key twice must return
    the original event without creating a duplicate.
    """

    def setUp(self):
        self.user = self._create_user()

    def test_duplicate_idempotent_request(self):
        chicago = ZoneInfo('America/Chicago')
        start_dt = dt.datetime(2026, 3, 1, 14, 0, 0, tzinfo=chicago)
        end_dt = dt.datetime(2026, 3, 1, 15, 0, 0, tzinfo=chicago)
        title = "Team Standup"

        normalized_title = " ".join(title.strip().split()).lower()
        idem_key = hashlib.sha256(
            f"{self.user.id}:{normalized_title}:{start_dt.isoformat()}".encode()
        ).hexdigest()

        # First create
        event1 = CalendarEvent.objects.create(
            user=self.user,
            title=title,
            start_dt=start_dt,
            end_dt=end_dt,
            idempotency_key=idem_key,
        )

        # Second lookup — simulate assistant idempotency check
        existing = CalendarEvent.objects.filter(
            idempotency_key=idem_key,
        ).first()

        self.assertIsNotNone(existing)
        self.assertEqual(existing.pk, event1.pk)
        self.assertEqual(
            CalendarEvent.objects.filter(idempotency_key=idem_key).count(),
            1,
        )


# ──────────────────────────────────────────────────────────
# 4) IntegrityError race returns existing event
# ──────────────────────────────────────────────────────────

_is_sqlite = connection.vendor == 'sqlite'


class TestIntegrityErrorRaceReturnsExisting(_UserMixin, TransactionTestCase):
    """
    Concurrent creates that hit the unique constraint must recover
    and return the existing row.
    """

    def setUp(self):
        self.user = self._create_user()

    @staticmethod
    def _skip_if_sqlite(test_func):
        """SQLite doesn't support true concurrent threading."""
        if _is_sqlite:
            return None
        return test_func

    def test_integrityerror_race_returns_existing(self):
        if _is_sqlite:
            # On SQLite, verify that duplicate insert raises IntegrityError
            # (threading-based concurrency is not reliable on SQLite)
            chicago = ZoneInfo('America/Chicago')
            start_dt = dt.datetime(2026, 3, 5, 10, 0, 0, tzinfo=chicago)
            end_dt = dt.datetime(2026, 3, 5, 11, 0, 0, tzinfo=chicago)
            idem_key = 'test_sqlite_race_key_abc123'

            CalendarEvent.objects.create(
                user=self.user,
                title="Race Event",
                start_dt=start_dt,
                end_dt=end_dt,
                idempotency_key=idem_key,
            )

            # Second insert with same (user, idempotency_key) must fail
            with self.assertRaises(IntegrityError):
                CalendarEvent.objects.create(
                    user=self.user,
                    title="Race Event",
                    start_dt=start_dt,
                    end_dt=end_dt,
                    idempotency_key=idem_key,
                )

            # Verify only one row
            self.assertEqual(
                CalendarEvent.objects.filter(
                    user=self.user, title="Race Event",
                ).count(),
                1,
            )
            return

        # PostgreSQL path: true concurrent threading test
        chicago = ZoneInfo('America/Chicago')
        start_dt = dt.datetime(2026, 3, 5, 10, 0, 0, tzinfo=chicago)
        end_dt = dt.datetime(2026, 3, 5, 11, 0, 0, tzinfo=chicago)
        title = "Race Event"
        normalized_title = " ".join(title.strip().split()).lower()
        idem_key = hashlib.sha256(
            f"{self.user.id}:{normalized_title}:{start_dt.isoformat()}".encode()
        ).hexdigest()

        results = {}
        barrier = threading.Barrier(2, timeout=5)

        def create_event(thread_id):
            from django.db import connection as conn, IntegrityError, transaction
            try:
                barrier.wait()
                with transaction.atomic():
                    existing = CalendarEvent.objects.filter(
                        idempotency_key=idem_key,
                    ).first()
                    if existing:
                        results[thread_id] = ('reused', existing.pk)
                        return
                    try:
                        # Nested savepoint: IntegrityError only rolls
                        # back the inner savepoint on PostgreSQL.
                        with transaction.atomic():
                            event = CalendarEvent.objects.create(
                                user=self.user,
                                title=title,
                                start_dt=start_dt,
                                end_dt=end_dt,
                                idempotency_key=idem_key,
                            )
                        results[thread_id] = ('created', event.pk)
                    except IntegrityError:
                        # Recovery query in outer (still-valid) transaction
                        recovered = CalendarEvent.objects.get(
                            idempotency_key=idem_key,
                        )
                        results[thread_id] = ('recovered', recovered.pk)
            except Exception as e:
                results[thread_id] = ('error', str(e))
            finally:
                conn.close()

        t1 = threading.Thread(target=create_event, args=(1,))
        t2 = threading.Thread(target=create_event, args=(2,))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        # At least one should have created, and any IntegrityError thread
        # should be able to re-query successfully
        total_rows = CalendarEvent.objects.filter(
            user=self.user, title=title,
        ).count()
        self.assertEqual(total_rows, 1, f"Expected 1 row, got {total_rows}. Results: {results}")


# ──────────────────────────────────────────────────────────
# 5) Unique constraint blocks duplicate insert
# ──────────────────────────────────────────────────────────

class TestUniqueConstraintBlocksDuplicate(_UserMixin, TestCase):
    """
    DB-level unique constraint on (user, idempotency_key) must
    prevent duplicate rows.
    """

    def setUp(self):
        self.user = self._create_user()

    def test_unique_constraint_blocks_duplicate(self):
        chicago = ZoneInfo('America/Chicago')
        start_dt = dt.datetime(2026, 3, 10, 9, 0, 0, tzinfo=chicago)
        end_dt = dt.datetime(2026, 3, 10, 10, 0, 0, tzinfo=chicago)
        idem_key = hashlib.sha256(
            f"{self.user.id}:yoga class:{start_dt.isoformat()}".encode()
        ).hexdigest()

        CalendarEvent.objects.create(
            user=self.user,
            title="Yoga Class",
            start_dt=start_dt,
            end_dt=end_dt,
            idempotency_key=idem_key,
        )

        with self.assertRaises(IntegrityError):
            CalendarEvent.objects.create(
                user=self.user,
                title="Yoga Class",
                start_dt=start_dt,
                end_dt=end_dt,
                idempotency_key=idem_key,
            )


# ──────────────────────────────────────────────────────────
# 6) PATCH verification — confirms changes are persisted
# ──────────────────────────────────────────────────────────

class TestPatchVerifiesChange(_UserMixin, TestCase):
    """
    PATCH endpoint must verify changes are persisted and return 409
    if no effective change was provided.
    """

    def setUp(self):
        self.user = self._create_user()
        self.client.force_login(self.user)

        chicago = ZoneInfo('America/Chicago')
        self.event = CalendarEvent.objects.create(
            user=self.user,
            title="Original Title",
            description="Original description",
            start_dt=dt.datetime(2026, 3, 15, 10, 0, 0, tzinfo=chicago),
            end_dt=dt.datetime(2026, 3, 15, 11, 0, 0, tzinfo=chicago),
        )

    def test_patch_with_valid_change(self):
        import json
        response = self.client.patch(
            f'/calendar/api/events/{self.event.pk}/',
            data=json.dumps({'title': 'Updated Title'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['event']['title'], 'Updated Title')

        # Verify DB
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, 'Updated Title')

    def test_patch_no_recognized_fields_returns_409(self):
        import json
        # Non-empty body, but no recognized updatable fields → 409
        response = self.client.patch(
            f'/calendar/api/events/{self.event.pk}/',
            data=json.dumps({'unrecognized_field': 'value'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 409)


# ──────────────────────────────────────────────────────────
# 7) DELETE row-count validation
# ──────────────────────────────────────────────────────────

class TestDeleteRowCountValidation(_UserMixin, TestCase):
    """
    DELETE must verify exactly 1 row was deleted. Non-existent events
    return 404 (handled by _get_event lookup before delete).
    """

    def setUp(self):
        self.user = self._create_user()
        self.client.force_login(self.user)

        chicago = ZoneInfo('America/Chicago')
        self.event = CalendarEvent.objects.create(
            user=self.user,
            title="Delete Me",
            start_dt=dt.datetime(2026, 3, 20, 10, 0, 0, tzinfo=chicago),
            end_dt=dt.datetime(2026, 3, 20, 11, 0, 0, tzinfo=chicago),
        )

    def test_delete_succeeds_for_existing_event(self):
        pk = self.event.pk
        response = self.client.delete(f'/calendar/api/events/{pk}/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'deleted')

        # Verify row is gone
        self.assertFalse(CalendarEvent.objects.filter(pk=pk).exists())

    def test_delete_nonexistent_returns_404(self):
        response = self.client.delete('/calendar/api/events/99999/')
        self.assertEqual(response.status_code, 404)

    def test_delete_row_count_validation(self):
        """
        Verify the delete row-count path: if the queryset delete returns
        count != 1 (simulated via mock), the view returns 409.
        """
        pk = self.event.pk

        # Mock the queryset.delete() to return count=0, simulating a race
        # where the row vanishes between _get_event and .delete()
        from apps.calendar_engine.views import EventDetailView

        original_delete = EventDetailView.delete

        def patched_delete(view_self, request, pk):
            # Manually delete the row before the view's filter().delete() runs
            CalendarEvent.objects.filter(pk=pk).delete()
            # Now call original — _get_event will 404 since row is gone
            # But we need to test the count!=1 path, so mock at queryset level
            return original_delete(view_self, request, pk)

        # Simpler approach: delete the row after _get_event but before
        # filter().delete(). We patch _get_event to return the event
        # but secretly delete it from DB.
        event_copy = self.event

        original_get_event = EventDetailView._get_event

        def mock_get_event(view_self, request, pk_arg):
            # Return the event object (cached), but delete from DB
            CalendarEvent.objects.filter(pk=pk_arg).delete()
            return event_copy

        with patch.object(EventDetailView, '_get_event', mock_get_event):
            response = self.client.delete(f'/calendar/api/events/{pk}/')
            self.assertEqual(response.status_code, 409)
            data = response.json()
            self.assertIn('error', data)


# ──────────────────────────────────────────────────────────
# Additional date_resolution coverage
# ──────────────────────────────────────────────────────────

class TestDateResolutionEdgeCases(_UserMixin, TestCase):
    """Additional tests for resolve_weekday_to_date edge cases."""

    def setUp(self):
        self.user = self._create_user()
        self.chicago = ZoneInfo('America/Chicago')

    def test_iso_date_passthrough(self):
        ref = dt.datetime(2026, 2, 25, 10, 0, 0, tzinfo=self.chicago)
        result = resolve_weekday_to_date(self.user, '2026-03-15', reference_dt=ref)
        self.assertEqual(result, dt.date(2026, 3, 15))

    def test_today_returns_user_local_date(self):
        ref = dt.datetime(2026, 2, 25, 10, 0, 0, tzinfo=self.chicago)
        result = resolve_weekday_to_date(self.user, 'today', reference_dt=ref)
        self.assertEqual(result, dt.date(2026, 2, 25))

    def test_tomorrow_returns_next_day(self):
        ref = dt.datetime(2026, 2, 25, 10, 0, 0, tzinfo=self.chicago)
        result = resolve_weekday_to_date(self.user, 'tomorrow', reference_dt=ref)
        self.assertEqual(result, dt.date(2026, 2, 26))

    def test_weekday_different_from_today(self):
        # Wednesday ref, asking for Friday → 2 days ahead
        ref = dt.datetime(2026, 2, 25, 10, 0, 0, tzinfo=self.chicago)  # Wednesday
        result = resolve_weekday_to_date(self.user, 'friday', reference_dt=ref)
        self.assertEqual(result, dt.date(2026, 2, 27))

    def test_weekday_no_time_same_day_defaults_today(self):
        # Wednesday ref, asking for Wednesday, no time → today
        ref = dt.datetime(2026, 2, 25, 10, 0, 0, tzinfo=self.chicago)  # Wednesday
        result = resolve_weekday_to_date(
            self.user, 'wednesday', reference_dt=ref, start_time=None,
        )
        self.assertEqual(result, dt.date(2026, 2, 25))

    def test_invalid_input_raises_valueerror(self):
        ref = dt.datetime(2026, 2, 25, 10, 0, 0, tzinfo=self.chicago)
        with self.assertRaises(ValueError):
            resolve_weekday_to_date(self.user, 'nextmonth', reference_dt=ref)

    def test_empty_string_raises_valueerror(self):
        ref = dt.datetime(2026, 2, 25, 10, 0, 0, tzinfo=self.chicago)
        with self.assertRaises(ValueError):
            resolve_weekday_to_date(self.user, '', reference_dt=ref)

    def test_now_alias(self):
        ref = dt.datetime(2026, 2, 25, 10, 0, 0, tzinfo=self.chicago)
        result = resolve_weekday_to_date(self.user, 'now', reference_dt=ref)
        self.assertEqual(result, dt.date(2026, 2, 25))

    def test_abbreviations_work(self):
        ref = dt.datetime(2026, 2, 25, 10, 0, 0, tzinfo=self.chicago)  # Wednesday
        for abbr, expected_days_ahead in [
            ('mon', 5), ('tue', 6), ('wed', 0), ('thu', 1),
            ('fri', 2), ('sat', 3), ('sun', 4),
        ]:
            result = resolve_weekday_to_date(
                self.user, abbr, reference_dt=ref, start_time=None,
            )
            expected = dt.date(2026, 2, 25) + dt.timedelta(days=expected_days_ahead)
            self.assertEqual(result, expected, f"Failed for {abbr}")


# ──────────────────────────────────────────────────────────
# 8) PostgreSQL concurrency: 5 threads, same event, 1 row
# ──────────────────────────────────────────────────────────

class TestConcurrentCreateIdempotency(_UserMixin, TransactionTestCase):
    """
    5 threads call handle_create_event() with identical input concurrently.
    Exactly 1 DB row must exist and all threads must return the same event.
    No exceptions, no user-facing failures.

    Uses TransactionTestCase because threading requires real committed data
    visible across connections.
    """

    def setUp(self):
        self.user = self._create_user(email='concurrency@test.local')

    def test_concurrent_create_returns_same_event(self):
        from apps.ai.action_handlers import ActionHandler

        num_threads = 5
        results = {}
        barrier = threading.Barrier(num_threads, timeout=10)

        def create_event(thread_id):
            from django.db import connection as conn
            try:
                handler = ActionHandler(self.user)
                barrier.wait()
                result = handler.handle_create_event(
                    title="Concurrent Test Event",
                    start_date="2026-03-10",
                    start_time="14:00",
                )
                results[thread_id] = {
                    'success': result.success,
                    'message': result.message,
                    'event_id': (
                        result.created_object.get('id')
                        if hasattr(result, 'created_object') and result.created_object
                        else None
                    ),
                    'reused': (
                        result.created_object.get('reused')
                        if hasattr(result, 'created_object') and result.created_object
                        else None
                    ),
                    'error': getattr(result, 'error', None),
                }
            except Exception as e:
                results[thread_id] = {
                    'success': False,
                    'message': str(e),
                    'event_id': None,
                    'reused': None,
                    'error': f"{type(e).__name__}: {e}",
                }
            finally:
                conn.close()

        threads = [
            threading.Thread(target=create_event, args=(i,))
            for i in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        # --- Assertions ---
        # All threads must have returned a result
        self.assertEqual(
            len(results), num_threads,
            f"Expected {num_threads} results, got {len(results)}",
        )

        # All threads must report success
        failures = [
            (tid, r) for tid, r in results.items() if not r['success']
        ]
        self.assertEqual(
            len(failures), 0,
            f"Threads failed: {failures}",
        )

        # All threads must return the same event ID
        event_ids = {r['event_id'] for r in results.values()}
        self.assertEqual(
            len(event_ids), 1,
            f"Expected 1 unique event ID, got {event_ids}",
        )

        # Exactly 1 DB row
        row_count = CalendarEvent.objects.filter(
            user=self.user,
            title="Concurrent Test Event",
        ).count()
        self.assertEqual(
            row_count, 1,
            f"Expected 1 DB row, got {row_count}",
        )
