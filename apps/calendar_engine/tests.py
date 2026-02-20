"""
Calendar Engine Tests.

Covers: projections, conflicts, suggestions, metrics, NLP parser, API endpoints.
"""

import datetime as dt
import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory
from django.utils import timezone

from apps.calendar_engine.models import (
    CalendarEvent,
    CalendarOverrideLog,
    RecurrenceRule,
    RecurrenceException,
)
from apps.calendar_engine.services import conflicts, metrics, suggestions
from apps.calendar_engine.services.nlp_parse import parse_quick_add
from apps.calendar_engine.services.projection import (
    delete_task_events,
    upsert_execution_block_for_task,
    upsert_from_goal,
    upsert_from_habit,
    upsert_from_task,
)

User = get_user_model()


def _create_test_user(email='caltest@example.com'):
    """Create a test user with onboarding complete."""
    from apps.users.models import TermsAcceptance
    user = User.objects.create_user(email=email, password='testpass123')
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


def _ensure_domains():
    """Ensure default LifeDomains exist."""
    from apps.purpose.models import LifeDomain
    defaults = [
        ('Faith', 'faith', '#6366f1'),
        ('Health', 'health', '#10b981'),
        ('Family', 'family', '#f59e0b'),
        ('Work', 'work', '#3b82f6'),
        ('Finances', 'finances', '#8b5cf6'),
    ]
    for name, slug, color in defaults:
        LifeDomain.objects.get_or_create(
            slug=slug,
            defaults={'name': name, 'color': color, 'is_active': True},
        )


# ──────────────────────────────────────────────────────────
# Projection Tests
# ──────────────────────────────────────────────────────────

class TaskProjectionTests(TestCase):
    def setUp(self):
        self.user = _create_test_user()
        _ensure_domains()

    def test_upsert_creates_deadline_marker(self):
        from apps.life.models import Task
        task = Task.objects.create(
            user=self.user,
            title='Ship feature X',
            due_date=dt.date(2026, 3, 1),
        )
        event = upsert_from_task(task)
        self.assertIsNotNone(event)
        self.assertEqual(event.event_kind, CalendarEvent.KIND_DEADLINE_MARKER)
        self.assertEqual(event.source_type, CalendarEvent.SOURCE_TASK)
        self.assertEqual(event.source_id, str(task.pk))
        self.assertIn('Ship feature X', event.title)

    def test_upsert_updates_on_date_change(self):
        from apps.life.models import Task
        task = Task.objects.create(
            user=self.user,
            title='Ship feature X',
            due_date=dt.date(2026, 3, 1),
        )
        event1 = upsert_from_task(task)

        # Change due date
        task.due_date = dt.date(2026, 3, 15)
        task.save()
        event2 = upsert_from_task(task)

        self.assertEqual(event1.pk, event2.pk)  # Same event, updated
        self.assertEqual(event2.start_dt.date(), dt.date(2026, 3, 15))

    def test_upsert_deletes_when_no_due_date(self):
        from apps.life.models import Task
        task = Task.objects.create(
            user=self.user,
            title='Ship feature X',
            due_date=dt.date(2026, 3, 1),
        )
        upsert_from_task(task)
        self.assertEqual(CalendarEvent.objects.filter(source_id=str(task.pk)).count(), 1)

        task.due_date = None
        task.save()
        upsert_from_task(task)
        self.assertEqual(CalendarEvent.objects.filter(source_id=str(task.pk)).count(), 0)

    def test_drag_updates_task_due_date(self):
        """Acceptance criterion #2: dragging a deadline marker updates the task due_date."""
        from apps.life.models import Task
        task = Task.objects.create(
            user=self.user,
            title='Important Task',
            due_date=dt.date(2026, 3, 1),
        )
        event = upsert_from_task(task)

        # Simulate drag via the move view
        self.client.force_login(self.user)
        new_start = timezone.make_aware(
            dt.datetime(2026, 3, 10, 23, 59), timezone.get_current_timezone()
        )
        new_end = new_start + dt.timedelta(minutes=1)

        resp = self.client.post(
            f'/calendar/api/events/{event.pk}/move/',
            data=json.dumps({
                'new_start_dt': new_start.isoformat(),
                'new_end_dt': new_end.isoformat(),
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)

        task.refresh_from_db()
        self.assertEqual(task.due_date, dt.date(2026, 3, 10))

    def test_execution_block_creation(self):
        from apps.life.models import Task
        task = Task.objects.create(
            user=self.user,
            title='Ship feature X',
            due_date=dt.date(2026, 3, 1),
        )
        start = timezone.now()
        end = start + dt.timedelta(hours=2)
        event = upsert_execution_block_for_task(task, start, end)

        self.assertEqual(event.event_kind, CalendarEvent.KIND_EXECUTION_BLOCK)
        self.assertEqual(event.source_type, CalendarEvent.SOURCE_TASK)


class GoalProjectionTests(TestCase):
    def setUp(self):
        self.user = _create_test_user('goaltest@example.com')
        _ensure_domains()

    def test_upsert_creates_goal_marker(self):
        from apps.purpose.models import LifeGoal
        goal = LifeGoal.objects.create(
            user=self.user,
            title='Run a marathon',
            target_date=dt.date(2026, 6, 1),
        )
        events = upsert_from_goal(goal)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].source_type, CalendarEvent.SOURCE_GOAL)
        self.assertIn('Run a marathon', events[0].title)


class HabitProjectionTests(TestCase):
    def setUp(self):
        self.user = _create_test_user('habittest@example.com')
        _ensure_domains()

    def test_upsert_creates_recurring_habit_event(self):
        from apps.purpose.models import HabitGoal
        habit = HabitGoal.objects.create(
            user=self.user,
            name='Morning Workout',
            purpose='Stay healthy',
            start_date=dt.date(2026, 1, 1),
            end_date=dt.date(2026, 12, 31),
            frequency_type='daily',
            measurement_type='binary',
        )
        event = upsert_from_habit(habit)
        self.assertIsNotNone(event)
        self.assertTrue(event.is_protected)
        self.assertTrue(hasattr(event, 'recurrence'))
        self.assertEqual(event.recurrence.frequency, RecurrenceRule.FREQ_DAILY)


# ──────────────────────────────────────────────────────────
# Conflict Detection Tests
# ──────────────────────────────────────────────────────────

class ConflictTests(TestCase):
    def setUp(self):
        self.user = _create_test_user('conflicttest@example.com')
        _ensure_domains()

    def test_protected_overlap_returns_conflict(self):
        """Acceptance criterion #5: conflict prompt on protected time."""
        tz = timezone.get_current_timezone()
        # Create a protected event (e.g. workout)
        protected = CalendarEvent.objects.create(
            user=self.user,
            title='Morning Workout',
            start_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 6, 0), tz),
            end_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 7, 0), tz),
            event_kind=CalendarEvent.KIND_MANUAL,
            is_protected=True,
        )

        # Check overlap
        result = conflicts.check_conflicts(
            self.user,
            timezone.make_aware(dt.datetime(2026, 3, 1, 6, 30), tz),
            timezone.make_aware(dt.datetime(2026, 3, 1, 7, 30), tz),
        )
        self.assertTrue(result['conflict'])
        self.assertIn('Morning Workout', result['conflict_message'])
        self.assertEqual(len(result['conflicting_events']), 1)

    def test_no_conflict_outside_protected(self):
        tz = timezone.get_current_timezone()
        CalendarEvent.objects.create(
            user=self.user,
            title='Morning Workout',
            start_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 6, 0), tz),
            end_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 7, 0), tz),
            event_kind=CalendarEvent.KIND_MANUAL,
            is_protected=True,
        )

        result = conflicts.check_conflicts(
            self.user,
            timezone.make_aware(dt.datetime(2026, 3, 1, 8, 0), tz),
            timezone.make_aware(dt.datetime(2026, 3, 1, 9, 0), tz),
        )
        self.assertFalse(result['conflict'])

    def test_override_logged(self):
        tz = timezone.get_current_timezone()
        protected = CalendarEvent.objects.create(
            user=self.user,
            title='Workout',
            start_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 6, 0), tz),
            end_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 7, 0), tz),
            event_kind=CalendarEvent.KIND_MANUAL,
            is_protected=True,
        )
        moved = CalendarEvent.objects.create(
            user=self.user,
            title='Meeting',
            start_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 6, 30), tz),
            end_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 7, 30), tz),
            event_kind=CalendarEvent.KIND_MANUAL,
        )
        log = conflicts.log_override(self.user, moved, protected, reason='Urgent meeting')
        self.assertIsNotNone(log)
        self.assertEqual(CalendarOverrideLog.objects.count(), 1)


# ──────────────────────────────────────────────────────────
# Smart Gap Detection Tests
# ──────────────────────────────────────────────────────────

class GapDetectionTests(TestCase):
    def setUp(self):
        self.user = _create_test_user('gaptest@example.com')
        _ensure_domains()

    def test_finds_gap_when_available(self):
        """Acceptance criterion #6: detect 90-min gap."""
        tz = timezone.get_current_timezone()
        target_date = dt.date(2026, 3, 2)

        # Create events leaving a gap from 10am-12pm
        CalendarEvent.objects.create(
            user=self.user,
            title='Morning Block',
            start_dt=timezone.make_aware(dt.datetime(2026, 3, 2, 6, 0), tz),
            end_dt=timezone.make_aware(dt.datetime(2026, 3, 2, 10, 0), tz),
        )
        CalendarEvent.objects.create(
            user=self.user,
            title='Afternoon Block',
            start_dt=timezone.make_aware(dt.datetime(2026, 3, 2, 12, 0), tz),
            end_dt=timezone.make_aware(dt.datetime(2026, 3, 2, 22, 0), tz),
        )

        gaps = suggestions.find_gaps_for_day(self.user, target_date)
        self.assertTrue(len(gaps) >= 1)
        # 10am-12pm = 120 min gap
        self.assertTrue(any(g['duration_minutes'] >= 90 for g in gaps))

    def test_suggestion_generated_for_due_task(self):
        """Acceptance criterion #6: suggest execution block for task due soon."""
        from apps.life.models import Task
        tz = timezone.get_current_timezone()
        target_date = timezone.localdate() + dt.timedelta(days=1)

        # Create a task due in 5 days
        task = Task.objects.create(
            user=self.user,
            title='Write proposal',
            due_date=timezone.localdate() + dt.timedelta(days=5),
        )

        # Leave the day wide open (no events)
        result = suggestions.generate_suggestions(self.user, target_date)
        self.assertTrue(len(result) >= 1)
        self.assertEqual(result[0]['source_type'], 'task')
        self.assertEqual(result[0]['source_id'], str(task.pk))

    def test_accept_creates_execution_block(self):
        """Acceptance criterion #6: one-click accept creates execution block."""
        from apps.life.models import Task
        task = Task.objects.create(
            user=self.user,
            title='Write proposal',
            due_date=timezone.localdate() + dt.timedelta(days=5),
        )

        self.client.force_login(self.user)
        start = timezone.now() + dt.timedelta(hours=1)
        end = start + dt.timedelta(minutes=90)

        resp = self.client.post(
            '/calendar/api/suggestions/accept/',
            data=json.dumps({
                'source_type': 'task',
                'source_id': str(task.pk),
                'start_dt': start.isoformat(),
                'end_dt': end.isoformat(),
                'title': f'Work on: {task.title}',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(CalendarEvent.objects.filter(
            source_type=CalendarEvent.SOURCE_TASK,
            source_id=str(task.pk),
            event_kind=CalendarEvent.KIND_EXECUTION_BLOCK,
        ).exists())


# ──────────────────────────────────────────────────────────
# Domain Imbalance Tests
# ──────────────────────────────────────────────────────────

class DomainBalanceTests(TestCase):
    def setUp(self):
        self.user = _create_test_user('balancetest@example.com')
        _ensure_domains()

    def test_percentages_add_up(self):
        """Acceptance criterion #7: percentages add to 100%."""
        from apps.purpose.models import LifeDomain
        tz = timezone.get_current_timezone()

        work = LifeDomain.objects.get(slug='work')
        health = LifeDomain.objects.get(slug='health')

        # 2 hours work, 1 hour health
        CalendarEvent.objects.create(
            user=self.user, title='Work', domain=work,
            start_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 9, 0), tz),
            end_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 11, 0), tz),
        )
        CalendarEvent.objects.create(
            user=self.user, title='Gym', domain=health,
            start_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 7, 0), tz),
            end_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 8, 0), tz),
        )

        start = timezone.make_aware(dt.datetime(2026, 3, 1, 0, 0), tz)
        end = timezone.make_aware(dt.datetime(2026, 3, 1, 23, 59), tz)
        result = metrics.compute_domain_percentages(self.user, start, end)

        total_pct = sum(item['percentage'] for item in result)
        self.assertAlmostEqual(total_pct, 100.0, places=0)

        # Work should be ~66.7%, Health ~33.3%
        work_item = next(i for i in result if i['name'] == 'Work')
        health_item = next(i for i in result if i['name'] == 'Health')
        self.assertGreater(work_item['percentage'], health_item['percentage'])

    def test_balance_api(self):
        """Acceptance criterion #7: API returns balance data."""
        self.client.force_login(self.user)
        resp = self.client.get('/calendar/api/metrics/balance/?period=today')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertIn('balance', data)
        self.assertEqual(data['period'], 'today')


# ──────────────────────────────────────────────────────────
# NLP Parser Tests
# ──────────────────────────────────────────────────────────

class NLPParseTests(TestCase):
    def test_parse_recurring_bible_study(self):
        """Acceptance criterion #4: recurring Bible Study via NLP."""
        result = parse_quick_add('Bible Study Wednesdays 6pm-8pm')
        self.assertTrue(result['is_recurring'])
        self.assertIn(3, result['weekdays'])  # Wednesday = ISO 3
        self.assertEqual(result['start_time'], dt.time(18, 0))
        self.assertEqual(result['end_time'], dt.time(20, 0))
        self.assertEqual(result['domain_slug'], 'faith')

    def test_parse_gym_session(self):
        result = parse_quick_add('Recurring gym session Mon/Wed/Fri 5:30am-6:30am')
        self.assertTrue(result['is_recurring'])
        self.assertIn(1, result['weekdays'])  # Monday
        self.assertIn(3, result['weekdays'])  # Wednesday
        self.assertIn(5, result['weekdays'])  # Friday
        self.assertEqual(result['start_time'], dt.time(5, 30))
        self.assertEqual(result['end_time'], dt.time(6, 30))
        self.assertEqual(result['domain_slug'], 'health')

    def test_parse_team_meeting(self):
        result = parse_quick_add('Team meeting tomorrow 2pm-3pm')
        self.assertIsNotNone(result['date'])
        self.assertEqual(result['start_time'], dt.time(14, 0))
        self.assertEqual(result['end_time'], dt.time(15, 0))
        self.assertEqual(result['domain_slug'], 'work')

    def test_nlp_create_api(self):
        """Acceptance criterion #4: create recurring event via NLP API."""
        user = _create_test_user('nlptest@example.com')
        _ensure_domains()
        self.client.force_login(user)

        resp = self.client.post(
            '/calendar/api/nlp_create/',
            data=json.dumps({'text': 'Bible Study Wednesdays 6pm-8pm'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)
        data = json.loads(resp.content)
        self.assertIn('event', data)
        self.assertTrue(data['parsed']['is_recurring'])

        # Verify recurrence rule was created
        event_id = data['event']['id']
        event = CalendarEvent.objects.get(pk=event_id)
        self.assertTrue(hasattr(event, 'recurrence'))


# ──────────────────────────────────────────────────────────
# Recurrence Tests
# ──────────────────────────────────────────────────────────

class RecurrenceTests(TestCase):
    def setUp(self):
        self.user = _create_test_user('recurtest@example.com')

    def test_weekly_occurrences(self):
        tz = timezone.get_current_timezone()
        event = CalendarEvent.objects.create(
            user=self.user,
            title='Weekly Meeting',
            start_dt=timezone.make_aware(dt.datetime(2026, 3, 2, 10, 0), tz),  # Monday
            end_dt=timezone.make_aware(dt.datetime(2026, 3, 2, 11, 0), tz),
        )
        rule = RecurrenceRule.objects.create(
            event=event,
            frequency=RecurrenceRule.FREQ_WEEKLY,
            interval=1,
        )

        range_start = timezone.make_aware(dt.datetime(2026, 3, 1, 0, 0), tz)
        range_end = timezone.make_aware(dt.datetime(2026, 3, 31, 23, 59), tz)
        occurrences = rule.get_occurrences(range_start, range_end)

        # Should have ~4-5 occurrences in March
        self.assertGreaterEqual(len(occurrences), 4)
        # Each should be 1 hour
        for start, end in occurrences:
            self.assertEqual((end - start).total_seconds(), 3600)


# ──────────────────────────────────────────────────────────
# API Endpoint Tests
# ──────────────────────────────────────────────────────────

class APITests(TestCase):
    def setUp(self):
        self.user = _create_test_user('apitest@example.com')
        _ensure_domains()
        self.client.force_login(self.user)

    def test_today_timeline(self):
        """Acceptance criterion #3: CoS opens to today timeline."""
        resp = self.client.get('/calendar/api/today/')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertIn('events', data)
        self.assertIn('date', data)

    def test_range_query(self):
        resp = self.client.get('/calendar/api/range/?start=2026-03-01&end=2026-03-07')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertIn('events', data)

    def test_create_manual_event(self):
        resp = self.client.post(
            '/calendar/api/events/',
            data=json.dumps({
                'title': 'Manual Event',
                'start_dt': '2026-03-01T10:00:00',
                'end_dt': '2026-03-01T11:00:00',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)
        data = json.loads(resp.content)
        self.assertEqual(data['event']['title'], 'Manual Event')

    def test_event_detail_get(self):
        tz = timezone.get_current_timezone()
        event = CalendarEvent.objects.create(
            user=self.user, title='Test',
            start_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 10, 0), tz),
            end_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 11, 0), tz),
        )
        resp = self.client.get(f'/calendar/api/events/{event.pk}/')
        self.assertEqual(resp.status_code, 200)

    def test_event_patch(self):
        tz = timezone.get_current_timezone()
        event = CalendarEvent.objects.create(
            user=self.user, title='Old Title',
            start_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 10, 0), tz),
            end_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 11, 0), tz),
        )
        resp = self.client.patch(
            f'/calendar/api/events/{event.pk}/',
            data=json.dumps({'title': 'New Title'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        event.refresh_from_db()
        self.assertEqual(event.title, 'New Title')

    def test_event_delete(self):
        tz = timezone.get_current_timezone()
        event = CalendarEvent.objects.create(
            user=self.user, title='Delete Me',
            start_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 10, 0), tz),
            end_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 11, 0), tz),
        )
        resp = self.client.delete(f'/calendar/api/events/{event.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(CalendarEvent.objects.filter(pk=event.pk).exists())

    def test_dashboard_view_loads(self):
        """Acceptance criterion #3: dashboard page loads."""
        resp = self.client.get('/calendar/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Time Command Center')

    def test_move_with_conflict_returns_409(self):
        """Acceptance criterion #5: move into protected time returns 409 conflict."""
        tz = timezone.get_current_timezone()
        # Protected event
        CalendarEvent.objects.create(
            user=self.user, title='Workout', is_protected=True,
            start_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 6, 0), tz),
            end_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 7, 0), tz),
        )
        # Event to move
        event = CalendarEvent.objects.create(
            user=self.user, title='Meeting',
            start_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 10, 0), tz),
            end_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 11, 0), tz),
        )

        resp = self.client.post(
            f'/calendar/api/events/{event.pk}/move/',
            data=json.dumps({
                'new_start_dt': '2026-03-01T06:30:00',
                'new_end_dt': '2026-03-01T07:30:00',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 409)
        data = json.loads(resp.content)
        self.assertTrue(data['conflict'])

    def test_move_with_override(self):
        """Acceptance criterion #5: override confirmed allows move."""
        tz = timezone.get_current_timezone()
        CalendarEvent.objects.create(
            user=self.user, title='Workout', is_protected=True,
            start_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 6, 0), tz),
            end_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 7, 0), tz),
        )
        event = CalendarEvent.objects.create(
            user=self.user, title='Meeting',
            start_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 10, 0), tz),
            end_dt=timezone.make_aware(dt.datetime(2026, 3, 1, 11, 0), tz),
        )

        resp = self.client.post(
            f'/calendar/api/events/{event.pk}/move/',
            data=json.dumps({
                'new_start_dt': '2026-03-01T06:30:00',
                'new_end_dt': '2026-03-01T07:30:00',
                'override': True,
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        event.refresh_from_db()
        self.assertEqual(event.start_dt.hour, 6)
        self.assertEqual(CalendarOverrideLog.objects.count(), 1)
