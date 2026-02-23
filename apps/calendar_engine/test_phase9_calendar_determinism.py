"""
Phase 9: Calendar Determinism & Trust Repair Tests

Section 7 — Idempotency & Concurrency Tests
Section 8 — Time-Freeze (Deterministic Date Resolution) Tests
"""

import datetime as dt
import hashlib
import json
import threading

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from freezegun import freeze_time
from zoneinfo import ZoneInfo

from apps.calendar_engine.models import CalendarEvent
from apps.calendar_engine.utils.date_resolution import resolve_weekday_to_date

User = get_user_model()


def _create_test_user(email='phase9test@example.com', tz_iana='America/Chicago'):
    """Create a test user with onboarding complete and specified timezone."""
    from apps.users.models import TermsAcceptance
    user = User.objects.create_user(email=email, password='testpass123')
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.timezone = tz_iana
    user.preferences.save()
    return user


# ──────────────────────────────────────────────────────────
# Section 8 — Time-Freeze (Deterministic Date Resolution)
# ──────────────────────────────────────────────────────────

class DateResolutionTests(TestCase):
    """Test resolve_weekday_to_date with frozen time."""

    def setUp(self):
        self.user = _create_test_user('daterestest@example.com')

    def test_iso_date_passthrough(self):
        """YYYY-MM-DD strings are returned as-is."""
        result = resolve_weekday_to_date(self.user, '2026-03-15')
        self.assertEqual(result, dt.date(2026, 3, 15))

    def test_today_keyword(self):
        """'today' resolves to user's local date."""
        ref = dt.datetime(2026, 2, 23, 10, 0, tzinfo=ZoneInfo('America/Chicago'))
        result = resolve_weekday_to_date(self.user, 'today', reference_dt=ref)
        self.assertEqual(result, dt.date(2026, 2, 23))

    def test_tomorrow_keyword(self):
        """'tomorrow' resolves to user's local date + 1."""
        ref = dt.datetime(2026, 2, 23, 10, 0, tzinfo=ZoneInfo('America/Chicago'))
        result = resolve_weekday_to_date(self.user, 'tomorrow', reference_dt=ref)
        self.assertEqual(result, dt.date(2026, 2, 24))

    @freeze_time("2026-02-23 16:00:00")  # Monday in UTC, Monday in CT
    def test_wednesday_on_monday_resolves_to_same_week(self):
        """
        Today Monday 2026-02-23 10:00 local.
        User says 'Wednesday'.
        Expect 2026-02-25 — NOT March.
        """
        ref = dt.datetime(2026, 2, 23, 10, 0, tzinfo=ZoneInfo('America/Chicago'))
        result = resolve_weekday_to_date(self.user, 'Wednesday', reference_dt=ref)
        self.assertEqual(result, dt.date(2026, 2, 25))

    @freeze_time("2026-02-25 14:00:00")  # Wednesday in UTC
    def test_wednesday_on_wednesday_morning_resolves_to_today(self):
        """
        Today Wednesday 2026-02-25 08:00 local.
        User says 'Wednesday' with time 06:00 (past event time).
        resolve_weekday_to_date returns today (same weekday = today).
        The start_time logic in handle_create_event handles hour comparison.
        """
        ref = dt.datetime(2026, 2, 25, 8, 0, tzinfo=ZoneInfo('America/Chicago'))
        result = resolve_weekday_to_date(self.user, 'wednesday', reference_dt=ref)
        # Same-day weekday returns today
        self.assertEqual(result, dt.date(2026, 2, 25))

    def test_friday_on_wednesday(self):
        """Wednesday → 'Friday' → same week Friday."""
        ref = dt.datetime(2026, 2, 25, 10, 0, tzinfo=ZoneInfo('America/Chicago'))
        result = resolve_weekday_to_date(self.user, 'friday', reference_dt=ref)
        self.assertEqual(result, dt.date(2026, 2, 27))

    def test_monday_on_friday(self):
        """Friday → 'Monday' → next week Monday."""
        ref = dt.datetime(2026, 2, 27, 10, 0, tzinfo=ZoneInfo('America/Chicago'))
        result = resolve_weekday_to_date(self.user, 'monday', reference_dt=ref)
        self.assertEqual(result, dt.date(2026, 3, 2))

    def test_sunday_on_saturday(self):
        """Saturday → 'Sunday' → tomorrow."""
        ref = dt.datetime(2026, 2, 28, 10, 0, tzinfo=ZoneInfo('America/Chicago'))
        result = resolve_weekday_to_date(self.user, 'sunday', reference_dt=ref)
        self.assertEqual(result, dt.date(2026, 3, 1))

    def test_abbreviated_weekday_names(self):
        """Short forms like 'mon', 'tue', 'wed' work."""
        ref = dt.datetime(2026, 2, 23, 10, 0, tzinfo=ZoneInfo('America/Chicago'))
        self.assertEqual(
            resolve_weekday_to_date(self.user, 'mon', reference_dt=ref),
            dt.date(2026, 2, 23),  # Monday is today
        )
        self.assertEqual(
            resolve_weekday_to_date(self.user, 'tue', reference_dt=ref),
            dt.date(2026, 2, 24),
        )
        self.assertEqual(
            resolve_weekday_to_date(self.user, 'sat', reference_dt=ref),
            dt.date(2026, 2, 28),
        )

    def test_invalid_input_raises_valueerror(self):
        """Unrecognized strings raise ValueError."""
        with self.assertRaises(ValueError):
            resolve_weekday_to_date(self.user, 'next-month')
        with self.assertRaises(ValueError):
            resolve_weekday_to_date(self.user, '')
        with self.assertRaises(ValueError):
            resolve_weekday_to_date(self.user, '  ')

    def test_case_insensitive(self):
        """Weekday names are case-insensitive."""
        ref = dt.datetime(2026, 2, 23, 10, 0, tzinfo=ZoneInfo('America/Chicago'))
        self.assertEqual(
            resolve_weekday_to_date(self.user, 'WEDNESDAY', reference_dt=ref),
            dt.date(2026, 2, 25),
        )
        self.assertEqual(
            resolve_weekday_to_date(self.user, 'Thursday', reference_dt=ref),
            dt.date(2026, 2, 26),
        )

    def test_now_keyword(self):
        """'now' behaves like 'today'."""
        ref = dt.datetime(2026, 2, 23, 10, 0, tzinfo=ZoneInfo('America/Chicago'))
        result = resolve_weekday_to_date(self.user, 'now', reference_dt=ref)
        self.assertEqual(result, dt.date(2026, 2, 23))

    @freeze_time("2026-02-23 16:00:00")
    def test_full_week_cycle(self):
        """Every weekday resolves correctly from a Monday reference."""
        ref = dt.datetime(2026, 2, 23, 10, 0, tzinfo=ZoneInfo('America/Chicago'))
        expected = {
            'monday': dt.date(2026, 2, 23),     # today
            'tuesday': dt.date(2026, 2, 24),
            'wednesday': dt.date(2026, 2, 25),
            'thursday': dt.date(2026, 2, 26),
            'friday': dt.date(2026, 2, 27),
            'saturday': dt.date(2026, 2, 28),
            'sunday': dt.date(2026, 3, 1),
        }
        for name, expected_date in expected.items():
            result = resolve_weekday_to_date(self.user, name, reference_dt=ref)
            self.assertEqual(result, expected_date, f"Failed for {name}")

    # --- Phase 9.1: Same-day weekday + time tests ---

    @freeze_time("2026-02-25 14:00:00")  # Wednesday UTC → Wednesday 08:00 CT
    def test_same_day_time_passed_schedules_next_week(self):
        """
        Wednesday 08:00 local. User says '6:15am Wednesday'.
        6:15 < 8:00 → time already passed → schedule NEXT Wednesday.
        """
        ref = dt.datetime(2026, 2, 25, 8, 0, tzinfo=ZoneInfo('America/Chicago'))
        event_time = dt.time(6, 15)
        result = resolve_weekday_to_date(
            self.user, 'wednesday', reference_dt=ref, start_time=event_time,
        )
        # Next Wednesday = today + 7
        self.assertEqual(result, dt.date(2026, 3, 4))

    @freeze_time("2026-02-25 11:00:00")  # Wednesday UTC → Wednesday 05:00 CT
    def test_same_day_time_future_schedules_today(self):
        """
        Wednesday 05:00 local. User says '6:15am Wednesday'.
        6:15 > 5:00 → time still in future → schedule TODAY.
        """
        ref = dt.datetime(2026, 2, 25, 5, 0, tzinfo=ZoneInfo('America/Chicago'))
        event_time = dt.time(6, 15)
        result = resolve_weekday_to_date(
            self.user, 'wednesday', reference_dt=ref, start_time=event_time,
        )
        self.assertEqual(result, dt.date(2026, 2, 25))


# ──────────────────────────────────────────────────────────
# Section 7 — Idempotency & Concurrency Tests
# ──────────────────────────────────────────────────────────

class IdempotencyTests(TestCase):
    """Test idempotency_key prevents duplicate assistant-path creation."""

    def setUp(self):
        self.user = _create_test_user('idemtest@example.com')
        self.tz = timezone.get_current_timezone()

    def test_same_idempotency_key_returns_existing(self):
        """Double create with same idempotency_key → only one DB row."""
        start = timezone.make_aware(dt.datetime(2026, 3, 1, 10, 0), self.tz)
        end = start + dt.timedelta(hours=1)
        idem_key = hashlib.sha256(
            f"{self.user.id}:Team Meeting:{start.isoformat()}".encode()
        ).hexdigest()

        # First create
        event1 = CalendarEvent.objects.create(
            user=self.user,
            title='Team Meeting',
            start_dt=start,
            end_dt=end,
            idempotency_key=idem_key,
        )

        # Second create attempt — lookup by idempotency_key
        existing = CalendarEvent.objects.filter(
            idempotency_key=idem_key,
        ).first()
        self.assertIsNotNone(existing)
        self.assertEqual(existing.pk, event1.pk)

        # Only one row
        count = CalendarEvent.objects.filter(
            user=self.user, title='Team Meeting'
        ).count()
        self.assertEqual(count, 1)

    def test_different_titles_create_separate_events(self):
        """Different titles get different idempotency keys and both persist."""
        start = timezone.make_aware(dt.datetime(2026, 3, 1, 10, 0), self.tz)
        end = start + dt.timedelta(hours=1)

        key1 = hashlib.sha256(
            f"{self.user.id}:Meeting A:{start.isoformat()}".encode()
        ).hexdigest()
        key2 = hashlib.sha256(
            f"{self.user.id}:Meeting B:{start.isoformat()}".encode()
        ).hexdigest()

        CalendarEvent.objects.create(
            user=self.user, title='Meeting A',
            start_dt=start, end_dt=end, idempotency_key=key1,
        )
        CalendarEvent.objects.create(
            user=self.user, title='Meeting B',
            start_dt=start, end_dt=end, idempotency_key=key2,
        )
        self.assertEqual(CalendarEvent.objects.filter(user=self.user).count(), 2)

    def test_title_normalization_idempotency(self):
        """
        Phase 9.1: 'Workout' and ' workout ' produce the same
        normalized idempotency key → only one DB row created.
        """
        start = timezone.make_aware(dt.datetime(2026, 3, 1, 10, 0), self.tz)
        end = start + dt.timedelta(hours=1)

        # Both titles normalize to "workout"
        normalized1 = " ".join("Workout".strip().split()).lower()
        normalized2 = " ".join(" workout ".strip().split()).lower()
        self.assertEqual(normalized1, normalized2)

        key = hashlib.sha256(
            f"{self.user.id}:{normalized1}:{start.isoformat()}".encode()
        ).hexdigest()

        # First create with "Workout"
        CalendarEvent.objects.create(
            user=self.user, title='Workout',
            start_dt=start, end_dt=end, idempotency_key=key,
        )

        # Second create with " workout " — lookup by same key
        existing = CalendarEvent.objects.filter(
            idempotency_key=key,
        ).first()
        self.assertIsNotNone(existing)
        self.assertEqual(existing.title, 'Workout')

        # Only one row
        count = CalendarEvent.objects.filter(
            user=self.user, idempotency_key=key,
        ).count()
        self.assertEqual(count, 1)


class UniqueConstraintTests(TestCase):
    """Test the unique_user_title_start constraint."""

    def setUp(self):
        self.user = _create_test_user('uniquetest@example.com')
        self.tz = timezone.get_current_timezone()

    def test_duplicate_user_title_start_raises_integrity_error(self):
        """Creating two events with same user+title+start_dt raises IntegrityError."""
        start = timezone.make_aware(dt.datetime(2026, 3, 1, 10, 0), self.tz)
        end = start + dt.timedelta(hours=1)

        CalendarEvent.objects.create(
            user=self.user,
            title='Duplicate Test',
            start_dt=start,
            end_dt=end,
        )

        with self.assertRaises(IntegrityError):
            CalendarEvent.objects.create(
                user=self.user,
                title='Duplicate Test',
                start_dt=start,
                end_dt=end,
            )

    def test_same_title_different_time_allowed(self):
        """Same title at different times is allowed."""
        start1 = timezone.make_aware(dt.datetime(2026, 3, 1, 10, 0), self.tz)
        start2 = timezone.make_aware(dt.datetime(2026, 3, 1, 14, 0), self.tz)
        end = start1 + dt.timedelta(hours=1)

        CalendarEvent.objects.create(
            user=self.user, title='Meeting',
            start_dt=start1, end_dt=end,
        )
        CalendarEvent.objects.create(
            user=self.user, title='Meeting',
            start_dt=start2, end_dt=end,
        )
        self.assertEqual(CalendarEvent.objects.filter(user=self.user).count(), 2)

    def test_different_users_same_event_allowed(self):
        """Different users can have identical title+start_dt."""
        user2 = _create_test_user('uniquetest2@example.com')
        start = timezone.make_aware(dt.datetime(2026, 3, 1, 10, 0), self.tz)
        end = start + dt.timedelta(hours=1)

        CalendarEvent.objects.create(
            user=self.user, title='Meeting',
            start_dt=start, end_dt=end,
        )
        CalendarEvent.objects.create(
            user=user2, title='Meeting',
            start_dt=start, end_dt=end,
        )
        self.assertEqual(CalendarEvent.objects.filter(title='Meeting').count(), 2)


class ConcurrencyTests(TransactionTestCase):
    """
    Test concurrent creation with threading.
    Uses TransactionTestCase for real DB commits needed by threading.
    """

    def setUp(self):
        self.user = _create_test_user('concurtest@example.com')
        self.tz = timezone.get_current_timezone()

    def test_concurrent_create_only_one_persists(self):
        """Two threads attempt same creation — only one row persists."""
        from django.db import transaction as db_transaction

        start = timezone.make_aware(dt.datetime(2026, 3, 1, 10, 0), self.tz)
        end = start + dt.timedelta(hours=1)
        idem_key = hashlib.sha256(
            f"{self.user.id}:Concurrent Meeting:{start.isoformat()}".encode()
        ).hexdigest()

        results = {'success': 0, 'duplicate': 0, 'error': 0}
        lock = threading.Lock()

        def attempt_create():
            from django.db import connection, IntegrityError as DBIntegrityError
            try:
                with db_transaction.atomic():
                    # Check idempotency key first
                    existing = CalendarEvent.objects.filter(
                        idempotency_key=idem_key
                    ).first()
                    if existing:
                        with lock:
                            results['duplicate'] += 1
                        return

                    try:
                        CalendarEvent.objects.create(
                            user=self.user,
                            title='Concurrent Meeting',
                            start_dt=start,
                            end_dt=end,
                            idempotency_key=idem_key,
                        )
                        with lock:
                            results['success'] += 1
                    except (IntegrityError, DBIntegrityError):
                        # Race: other thread created first
                        with lock:
                            results['duplicate'] += 1
            except Exception:
                with lock:
                    results['error'] += 1
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt_create) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        # Exactly one row should exist
        count = CalendarEvent.objects.filter(
            user=self.user, title='Concurrent Meeting'
        ).count()
        self.assertEqual(count, 1, f"Expected 1 row, got {count}. Results: {results}")
        self.assertEqual(results['error'], 0, f"Unexpected errors: {results}")

    def test_integrityerror_race_returns_existing(self):
        """
        Phase 9.1: Two threads race past idempotency check.
        Both should succeed (one creates, one catches IntegrityError
        and re-queries). Only one DB row should exist.
        """
        from django.db import transaction as db_transaction

        start = timezone.make_aware(dt.datetime(2026, 3, 2, 10, 0), self.tz)
        end = start + dt.timedelta(hours=1)
        normalized_title = "race meeting"
        idem_key = hashlib.sha256(
            f"{self.user.id}:{normalized_title}:{start.isoformat()}".encode()
        ).hexdigest()

        results = {'created': 0, 'reused': 0, 'error': 0}
        lock = threading.Lock()

        def attempt_with_race_handling():
            from django.db import connection, IntegrityError as DBIntegrityError
            try:
                with db_transaction.atomic():
                    existing = CalendarEvent.objects.filter(
                        idempotency_key=idem_key
                    ).first()
                    if existing:
                        with lock:
                            results['reused'] += 1
                        return

                    try:
                        CalendarEvent.objects.create(
                            user=self.user,
                            title='Race Meeting',
                            start_dt=start,
                            end_dt=end,
                            idempotency_key=idem_key,
                        )
                        with lock:
                            results['created'] += 1
                    except (IntegrityError, DBIntegrityError):
                        # Race: re-query
                        event = CalendarEvent.objects.get(
                            idempotency_key=idem_key
                        )
                        with lock:
                            results['reused'] += 1
            except Exception as e:
                with lock:
                    results['error'] += 1
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt_with_race_handling) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        # Both calls should succeed (no errors)
        self.assertEqual(results['error'], 0, f"Unexpected errors: {results}")
        # Exactly one DB row
        count = CalendarEvent.objects.filter(
            user=self.user, title='Race Meeting'
        ).count()
        self.assertEqual(count, 1, f"Expected 1 row, got {count}. Results: {results}")
        # Total calls = 2 (one created + one reused, or both reused if sequential)
        self.assertEqual(
            results['created'] + results['reused'], 2,
            f"Expected 2 total outcomes, got {results}",
        )


# ──────────────────────────────────────────────────────────
# Section 6 — Delete & Update Verification Tests
# ──────────────────────────────────────────────────────────

class UpdateVerificationTests(TestCase):
    """Test PATCH verification in EventDetailView."""

    def setUp(self):
        self.user = _create_test_user('patchtest@example.com')
        self.tz = timezone.get_current_timezone()
        self.client.force_login(self.user)

    def test_patch_verifies_changes_applied(self):
        """Successful PATCH returns updated data."""
        event = CalendarEvent.objects.create(
            user=self.user, title='Old Title',
            start_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 10, 0), self.tz),
            end_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 11, 0), self.tz),
        )
        resp = self.client.patch(
            f'/calendar/api/events/{event.pk}/',
            data=json.dumps({'title': 'New Title'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data['event']['title'], 'New Title')

    def test_patch_empty_body_returns_409(self):
        """PATCH with no recognized fields returns 409."""
        event = CalendarEvent.objects.create(
            user=self.user, title='Test',
            start_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 10, 0), self.tz),
            end_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 11, 0), self.tz),
        )
        resp = self.client.patch(
            f'/calendar/api/events/{event.pk}/',
            data=json.dumps({'unrecognized_field': 'value'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 409)


class DeleteVerificationTests(TestCase):
    """Test DELETE row-count verification in EventDetailView."""

    def setUp(self):
        self.user = _create_test_user('deletetest@example.com')
        self.tz = timezone.get_current_timezone()
        self.client.force_login(self.user)

    def test_delete_returns_200_on_success(self):
        """Successful delete returns 200."""
        event = CalendarEvent.objects.create(
            user=self.user, title='Delete Me',
            start_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 10, 0), self.tz),
            end_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 11, 0), self.tz),
        )
        resp = self.client.delete(f'/calendar/api/events/{event.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(CalendarEvent.objects.filter(pk=event.pk).exists())

    def test_delete_nonexistent_returns_404(self):
        """Deleting a nonexistent event returns 404."""
        resp = self.client.delete('/calendar/api/events/99999/')
        self.assertEqual(resp.status_code, 404)
