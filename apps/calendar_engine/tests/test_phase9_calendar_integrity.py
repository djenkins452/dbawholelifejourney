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
from uuid import uuid4
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
from apps.calendar_engine.utils.idempotency import compute_idempotency_key

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
# 4) IntegrityError race returns existing event (SQLite path)
# ──────────────────────────────────────────────────────────

_is_sqlite = connection.vendor == 'sqlite'


class TestIntegrityErrorRaceReturnsExisting(_UserMixin, TransactionTestCase):
    """Duplicate insert with same (user, idempotency_key) must raise IntegrityError."""

    def setUp(self):
        self.user = self._create_user()

    def test_integrityerror_on_duplicate_key(self):
        chicago = ZoneInfo('America/Chicago')
        start_dt = dt.datetime(2026, 3, 5, 10, 0, 0, tzinfo=chicago)
        end_dt = dt.datetime(2026, 3, 5, 11, 0, 0, tzinfo=chicago)
        idem_key = 'test_race_key_abc123'

        CalendarEvent.objects.create(
            user=self.user,
            title="Race Event",
            start_dt=start_dt,
            end_dt=end_dt,
            idempotency_key=idem_key,
        )

        with self.assertRaises(IntegrityError):
            CalendarEvent.objects.create(
                user=self.user,
                title="Race Event",
                start_dt=start_dt,
                end_dt=end_dt,
                idempotency_key=idem_key,
            )

        self.assertEqual(
            CalendarEvent.objects.filter(user=self.user, title="Race Event").count(),
            1,
        )


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
        idem_key = compute_idempotency_key(
            self.user.id, "Yoga Class", start_dt, end_dt=end_dt,
        )

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
        start_dt = dt.datetime(2026, 3, 15, 10, 0, 0, tzinfo=chicago)
        end_dt = dt.datetime(2026, 3, 15, 11, 0, 0, tzinfo=chicago)
        self.event = CalendarEvent.objects.create(
            user=self.user,
            title="Original Title",
            description="Original description",
            start_dt=start_dt,
            end_dt=end_dt,
            idempotency_key=compute_idempotency_key(
                self.user.id, "Original Title", start_dt, end_dt=end_dt,
            ),
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
        start_dt = dt.datetime(2026, 3, 20, 10, 0, 0, tzinfo=chicago)
        end_dt = dt.datetime(2026, 3, 20, 11, 0, 0, tzinfo=chicago)
        self.event = CalendarEvent.objects.create(
            user=self.user,
            title="Delete Me",
            start_dt=start_dt,
            end_dt=end_dt,
            idempotency_key=compute_idempotency_key(
                self.user.id, "Delete Me", start_dt, end_dt=end_dt,
            ),
        )

    def test_delete_succeeds_for_existing_event(self):
        pk = self.event.pk
        response = self.client.delete(f'/calendar/api/events/{pk}/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'deleted')

        # Verify event is soft-deleted (status=canceled, deleted_at set)
        event = CalendarEvent.objects.get(pk=pk)
        self.assertEqual(event.status, CalendarEvent.STATUS_CANCELED)
        self.assertIsNotNone(event.deleted_at)

    def test_delete_nonexistent_returns_404(self):
        response = self.client.delete('/calendar/api/events/99999/')
        self.assertEqual(response.status_code, 404)

    def test_delete_row_count_validation(self):
        """
        Verify the delete row-count path: if the queryset delete returns
        count != 1 (simulated via mock), the view returns 409.
        """
        pk = self.event.pk

        from apps.calendar_engine.views import EventDetailView

        event_copy = self.event

        original_get_event = EventDetailView._get_event

        def mock_get_event(view_self, request, pk_arg):
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
        ref = dt.datetime(2026, 2, 25, 10, 0, 0, tzinfo=self.chicago)
        result = resolve_weekday_to_date(self.user, 'friday', reference_dt=ref)
        self.assertEqual(result, dt.date(2026, 2, 27))

    def test_weekday_no_time_same_day_defaults_today(self):
        ref = dt.datetime(2026, 2, 25, 10, 0, 0, tzinfo=self.chicago)
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
        ref = dt.datetime(2026, 2, 25, 10, 0, 0, tzinfo=self.chicago)
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
# 8) Forced IntegrityError concurrency — Section 4 + 5
# ──────────────────────────────────────────────────────────

class TestForcedIntegrityErrorRecovery(_UserMixin, TransactionTestCase):
    """
    5 threads attempt CalendarEvent.objects.create with identical
    (user, idempotency_key). A barrier AFTER filter().first() but
    BEFORE create() guarantees all threads enter the create path
    simultaneously.

    Acceptance criteria:
    - At least 1 thread hits IntegrityError
    - Recovery path executes (get by user + idempotency_key)
    - No 'current transaction is aborted' leakage
    - DB rows == 1
    - All threads succeed
    - Post-recovery ORM query executes inside outer atomic (Section 5)
    """

    def setUp(self):
        self.user = self._create_user(email='forced_race@test.local')

    def test_forced_integrity_error_recovery(self):
        if _is_sqlite:
            self.skipTest("SQLite single-writer lock prevents true concurrency")

        chicago = ZoneInfo('America/Chicago')
        start_dt = dt.datetime(2026, 4, 1, 9, 0, 0, tzinfo=chicago)
        end_dt = dt.datetime(2026, 4, 1, 10, 0, 0, tzinfo=chicago)
        idem_key = compute_idempotency_key(
            self.user.id, "Forced Race Event", start_dt, end_dt=end_dt,
        )

        num_threads = 5
        # Barrier placed AFTER idempotency check, BEFORE create
        pre_create_barrier = threading.Barrier(num_threads, timeout=10)
        results = {}

        def worker(tid):
            from django.db import connection as conn, IntegrityError, transaction
            try:
                with transaction.atomic():
                    # Idempotency check — user-scoped
                    existing = CalendarEvent.objects.filter(
                        user=self.user,
                        idempotency_key=idem_key,
                    ).first()

                    if existing:
                        # Section 5: post-query inside outer atomic
                        count = CalendarEvent.objects.filter(
                            user=self.user,
                        ).count()
                        results[tid] = {
                            'status': 'reused',
                            'pk': existing.pk,
                            'integrity_error': False,
                            'post_query_ok': True,
                            'post_query_count': count,
                        }
                        return

                    # ── SYNC POINT: all threads pass check → NONE exists ──
                    pre_create_barrier.wait()

                    try:
                        # Nested savepoint
                        with transaction.atomic():
                            event = CalendarEvent.objects.create(
                                user=self.user,
                                title="Forced Race Event",
                                start_dt=start_dt,
                                end_dt=end_dt,
                                idempotency_key=idem_key,
                            )
                        # Section 5: post-create query inside outer atomic
                        count = CalendarEvent.objects.filter(
                            user=self.user,
                        ).count()
                        results[tid] = {
                            'status': 'created',
                            'pk': event.pk,
                            'integrity_error': False,
                            'post_query_ok': True,
                            'post_query_count': count,
                        }
                    except IntegrityError:
                        # Recovery — user-scoped, inside outer (still-valid) atomic
                        recovered = CalendarEvent.objects.get(
                            user=self.user,
                            idempotency_key=idem_key,
                        )
                        # Section 5: post-recovery ORM query proves
                        # no transaction-aborted leakage
                        count = CalendarEvent.objects.filter(
                            user=self.user,
                        ).count()
                        results[tid] = {
                            'status': 'integrity_recovered',
                            'pk': recovered.pk,
                            'integrity_error': True,
                            'post_query_ok': True,
                            'post_query_count': count,
                        }
            except Exception as e:
                results[tid] = {
                    'status': 'error',
                    'pk': None,
                    'integrity_error': False,
                    'post_query_ok': False,
                    'error': f"{type(e).__name__}: {e}",
                }
            finally:
                conn.close()

        threads = [
            threading.Thread(target=worker, args=(i,))
            for i in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        # All threads returned
        self.assertEqual(len(results), num_threads)

        # Zero errors
        errors = [r for r in results.values() if r['status'] == 'error']
        self.assertEqual(len(errors), 0, f"Errors: {errors}")

        # At least 1 IntegrityError occurred
        integrity_hits = [r for r in results.values() if r['integrity_error']]
        self.assertGreaterEqual(
            len(integrity_hits), 1,
            f"Expected ≥1 IntegrityError, got 0. Results: {results}",
        )

        # Exactly 1 DB row
        row_count = CalendarEvent.objects.filter(
            user=self.user, idempotency_key=idem_key,
        ).count()
        self.assertEqual(row_count, 1)

        # All threads report same PK
        pks = {r['pk'] for r in results.values()}
        self.assertEqual(len(pks), 1, f"Expected 1 PK, got {pks}")

        # Section 5: all threads successfully ran post-recovery query
        for tid, r in results.items():
            self.assertTrue(
                r['post_query_ok'],
                f"Thread {tid} failed post-recovery query: {r}",
            )

        # Print proof for deliverable
        created = sum(1 for r in results.values() if r['status'] == 'created')
        recovered = sum(1 for r in results.values() if r['status'] == 'integrity_recovered')
        reused = sum(1 for r in results.values() if r['status'] == 'reused')
        sys.stdout.write(
            f"\n  [PROOF] Threads: {num_threads}, Created: {created}, "
            f"IntegrityError recovered: {recovered}, Reused: {reused}, "
            f"DB rows: {row_count}, Errors: {len(errors)}\n"
        )


# ──────────────────────────────────────────────────────────
# 9) Provider-backed idempotency: title-edit stability
# ──────────────────────────────────────────────────────────

class TestProviderBackedTitleStability(_UserMixin, TransactionTestCase):
    """
    Provider-backed events (source_id set) must produce the same
    idempotency key regardless of title changes. Re-calling
    handle_create_event with a new title but same source_id must
    reuse the existing row — no new row created.
    """

    def setUp(self):
        self.user = self._create_user(email='provider_title@test.local')

    def test_title_edit_reuses_existing_row(self):
        """
        1. Create event with source_type='task', source_id='42', title='Original'
        2. Re-call with same source_type/source_id but title='Renamed'
        3. Assert: same row reused, no new row, DB count == 1
        """
        from apps.ai.action_handlers import ActionHandler

        handler = ActionHandler(self.user)

        # First call — creates the event
        result1 = handler.handle_create_event(
            title="Original Task Title",
            start_date="2026-04-15",
            start_time="10:00",
            source_type='task',
            source_id='42',
        )
        self.assertTrue(result1.success, f"First create failed: {result1.message}")
        event_id_1 = (
            result1.created_object.get('id')
            if hasattr(result1, 'created_object') and result1.created_object
            else None
        )

        # Second call — same source, different title
        result2 = handler.handle_create_event(
            title="Renamed Task Title",
            start_date="2026-04-15",
            start_time="10:00",
            source_type='task',
            source_id='42',
        )
        self.assertTrue(result2.success, f"Second create failed: {result2.message}")
        event_id_2 = (
            result2.created_object.get('id')
            if hasattr(result2, 'created_object') and result2.created_object
            else None
        )

        # Same event reused
        self.assertEqual(event_id_1, event_id_2, "Expected same event PK")

        # Only 1 row in DB for this source
        row_count = CalendarEvent.objects.filter(
            user=self.user, source_type='task', source_id='42',
        ).count()
        self.assertEqual(row_count, 1, f"Expected 1 row, got {row_count}")

        sys.stdout.write(
            f"\n  [PROOF] Provider title-edit stability: "
            f"event_id_1={event_id_1}, event_id_2={event_id_2}, "
            f"DB rows=1, same_pk={event_id_1 == event_id_2}\n"
        )

    def test_idempotency_key_ignores_title_for_source_backed(self):
        """
        Direct unit test: compute_idempotency_key with source_id
        produces identical keys regardless of title.
        """
        chicago = ZoneInfo('America/Chicago')
        start = dt.datetime(2026, 5, 1, 9, 0, 0, tzinfo=chicago)

        key1 = compute_idempotency_key(
            self.user.id, "Original Title", start,
            source_type='goal', source_id='99',
        )
        key2 = compute_idempotency_key(
            self.user.id, "Completely Different Title", start,
            source_type='goal', source_id='99',
        )
        key3 = compute_idempotency_key(
            self.user.id, "", start,
            source_type='goal', source_id='99',
        )

        self.assertEqual(key1, key2, "Keys must match regardless of title")
        self.assertEqual(key1, key3, "Keys must match even with empty title")

    def test_manual_event_key_still_uses_title(self):
        """
        Manual events (no source_id) must still include title in the key.
        Different titles → different keys.
        """
        chicago = ZoneInfo('America/Chicago')
        start = dt.datetime(2026, 5, 1, 9, 0, 0, tzinfo=chicago)

        key1 = compute_idempotency_key(
            self.user.id, "Title A", start,
        )
        key2 = compute_idempotency_key(
            self.user.id, "Title B", start,
        )

        self.assertNotEqual(key1, key2, "Manual events must differ by title")


# ──────────────────────────────────────────────────────────
# 10) ActionHandler integration concurrency (high-level)
# ──────────────────────────────────────────────────────────

class TestConcurrentCreateIdempotency(_UserMixin, TransactionTestCase):
    """
    5 threads call handle_create_event() with identical input.
    All must succeed. 1 DB row.
    """

    def setUp(self):
        self.user = self._create_user(email='concurrency@test.local')

    def test_concurrent_create_returns_same_event(self):
        if _is_sqlite:
            self.skipTest("SQLite single-writer lock prevents true concurrency")

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
                }
            except Exception as e:
                results[thread_id] = {
                    'success': False,
                    'message': str(e),
                    'event_id': None,
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

        self.assertEqual(len(results), num_threads)

        failures = [
            (tid, r) for tid, r in results.items() if not r['success']
        ]
        self.assertEqual(len(failures), 0, f"Threads failed: {failures}")

        event_ids = {r['event_id'] for r in results.values()}
        self.assertEqual(len(event_ids), 1)

        row_count = CalendarEvent.objects.filter(
            user=self.user, title="Concurrent Test Event",
        ).count()
        self.assertEqual(row_count, 1)
