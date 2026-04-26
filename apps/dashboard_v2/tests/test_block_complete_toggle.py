"""
Tests for BlockCompleteToggleAction — Action Center Option C
(time block as primary execution unit).

Covers:
  1. Single-item block (one routine item)
  2. Multi-item block, all from one routine
  3. Mixed-domain block (routine + task + intake dose)
  4. Pure-intake block — must delegate to IntakeGroupLogAction so the
     analytics rollup stays a single window-level action
  5. Action Center group output: every time block carries a parent
     control (group_type='time_block'), regardless of original groups
  6. Idempotency: clicking twice returns the block to the original state
  7. CoS / Action Center alignment: prioritized actions returned by the
     execution_state contract match the Action Center's grouped view
     (one block primary item maps to the same task/routine the
     selectors would pick).
"""

from datetime import date, time, timedelta
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.users.models import User


def _make_user(email):
    from apps.users.models import TermsAcceptance
    user = User.objects.create_user(
        email=email, password="testpass123",
        date_of_birth=date(1990, 1, 1),
    )
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    prefs = user.preferences
    prefs.has_completed_onboarding = True
    prefs.ai_enabled = True
    prefs.ai_data_consent = True
    prefs.ai_data_consent_date = timezone.now()
    prefs.personal_assistant_enabled = True
    prefs.personal_assistant_consent = True
    prefs.personal_assistant_consent_date = timezone.now()
    prefs.save()
    return user


# ══════════════════════════════════════════════════════════════════════
# 1. Pure prioritizer-grouping tests — no DB required.
# ══════════════════════════════════════════════════════════════════════

from django.test import SimpleTestCase

from apps.core.decision_engine.action_prioritizer import (
    build_grouped_action_center,
    time_block_key_for,
)


def _exec_item(*, source_type, source_id, title, scheduled_time,
               group_type='standalone', group_id=None,
               completed=False, importance='flexible',
               is_foundational=False):
    return {
        'source_type': source_type,
        'source_id': source_id,
        'title': title,
        'domain': 'life',
        'importance': importance,
        'time_status': 'overdue' if scheduled_time and scheduled_time < '08:00'
                        else 'upcoming',
        'scheduled_time': scheduled_time,
        'grace_minutes': 0,
        'completion_status': 'done' if completed else 'pending',
        'completed_today': completed,
        'is_actionable': not completed,
        'is_foundational': is_foundational,
        'execution_group_type': group_type,
        'execution_group_id': group_id,
        'parent_title': '',
        'detail_url': '',
        'toggle_url': '',
    }


class GroupedActionCenterShapeTests(SimpleTestCase):
    """Every time block must carry group_type='time_block' regardless of
    original group composition. The dead 'standalone' / homogeneity
    branches are gone."""

    def test_single_item_block_is_time_block(self):
        items = [
            _exec_item(source_type='routine_item', source_id=1,
                       title='Stretch', scheduled_time='07:00',
                       group_type='routine', group_id=10),
        ]
        result = build_grouped_action_center(items, time(7, 30))
        groups = result['groups']
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['group_type'], 'time_block')
        self.assertEqual(groups[0]['time_block_key'], '07:00')
        self.assertTrue(groups[0]['is_time_block'])

    def test_homogeneous_routine_block_still_time_block(self):
        items = [
            _exec_item(source_type='routine_item', source_id=1,
                       title='Stretch', scheduled_time='07:00',
                       group_type='routine', group_id=10),
            _exec_item(source_type='routine_item', source_id=2,
                       title='Shower', scheduled_time='07:00',
                       group_type='routine', group_id=10),
        ]
        result = build_grouped_action_center(items, time(7, 30))
        groups = result['groups']
        self.assertEqual(len(groups), 1)
        # Used to be 'routine' before Option C — now always 'time_block'.
        self.assertEqual(groups[0]['group_type'], 'time_block')
        self.assertIsNone(groups[0]['intake_window_key'])

    def test_pure_intake_block_exposes_intake_window_key(self):
        items = [
            _exec_item(source_type='medication_dose', source_id=11,
                       title='Vitamin D', scheduled_time='08:00',
                       group_type='medication_window',
                       group_id='morning'),
            _exec_item(source_type='medication_dose', source_id=12,
                       title='Fish Oil', scheduled_time='08:00',
                       group_type='medication_window',
                       group_id='morning'),
        ]
        result = build_grouped_action_center(items, time(8, 0))
        groups = result['groups']
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['group_type'], 'time_block')
        self.assertEqual(groups[0]['intake_window_key'], 'morning')

    def test_mixed_block_no_intake_window_key(self):
        items = [
            _exec_item(source_type='routine_item', source_id=1,
                       title='Stretch', scheduled_time='08:00',
                       group_type='routine', group_id=10),
            _exec_item(source_type='medication_dose', source_id=11,
                       title='Vitamin D', scheduled_time='08:00',
                       group_type='medication_window',
                       group_id='morning'),
        ]
        result = build_grouped_action_center(items, time(8, 0))
        groups = result['groups']
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['group_type'], 'time_block')
        self.assertIsNone(groups[0]['intake_window_key'])

    def test_two_routines_at_same_time_no_intake_window_key(self):
        """Previously this would have been 'time_block' with no toggle.
        Now it's still 'time_block' but WITH the unified parent control
        (intake_window_key is None — per-item dispatch path)."""
        items = [
            _exec_item(source_type='routine_item', source_id=1,
                       title='Stretch', scheduled_time='08:00',
                       group_type='routine', group_id=10),
            _exec_item(source_type='routine_item', source_id=2,
                       title='Glucose', scheduled_time='08:00',
                       group_type='routine', group_id=20),
        ]
        result = build_grouped_action_center(items, time(8, 0))
        groups = result['groups']
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['group_type'], 'time_block')
        self.assertIsNone(groups[0]['intake_window_key'])


class TimeBlockKeyExportTests(SimpleTestCase):
    def test_rounds_to_15_min(self):
        self.assertEqual(time_block_key_for(time(8, 0)), '08:00')
        self.assertEqual(time_block_key_for(time(8, 7)), '08:00')
        self.assertEqual(time_block_key_for(time(8, 14)), '08:00')
        self.assertEqual(time_block_key_for(time(8, 15)), '08:15')
        self.assertEqual(time_block_key_for(time(8, 29)), '08:15')
        self.assertEqual(time_block_key_for(time(8, 30)), '08:30')

    def test_none_returns_none(self):
        self.assertIsNone(time_block_key_for(None))


# ══════════════════════════════════════════════════════════════════════
# 2. Endpoint behavior tests — DB-backed.
# ══════════════════════════════════════════════════════════════════════


class BlockCompleteToggleSingleItemTests(TestCase):
    """Block with a single task — clicking parent toggles that one task."""

    def setUp(self):
        self.user = _make_user("block_single@test.com")
        self.client.force_login(self.user)
        self.url = reverse(
            'dashboard_v2:block_complete_toggle',
            kwargs={'block_key': '08:00'},
        )

    def _build_items(self):
        from apps.life.models import Task
        task = Task.objects.create(
            user=self.user,
            title='Email accountant',
            scheduled_time=time(8, 0),
            due_date=date.today(),
            completion_status='pending',
        )
        return task, [{
            'source_type': 'task',
            'source_id': task.pk,
            'title': task.title,
            'domain': 'life',
            'importance': 'flexible',
            'time_status': 'now',
            'scheduled_time': '08:00',
            'grace_minutes': 0,
            'completion_status': 'pending',
            'completed_today': False,
            'is_actionable': True,
            'is_foundational': False,
            'execution_group_type': 'standalone',
            'execution_group_id': None,
        }]

    def test_completes_single_task(self):
        task, items = self._build_items()
        with patch(
            'apps.core.execution.today_execution.build_today_execution',
            return_value={'items': items, 'summaries': {}},
        ):
            resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.completion_status, 'completed')

    def test_idempotent_already_complete_undoes(self):
        """When all items are complete, the parent click toggles them off."""
        from apps.life.models import Task
        task, _items = self._build_items()
        task.mark_complete()
        # Now items reflect completed_today=True
        items = [{
            'source_type': 'task',
            'source_id': task.pk,
            'title': task.title,
            'domain': 'life',
            'importance': 'flexible',
            'time_status': 'now',
            'scheduled_time': '08:00',
            'grace_minutes': 0,
            'completion_status': 'completed',
            'completed_today': True,
            'is_actionable': False,
            'is_foundational': False,
            'execution_group_type': 'standalone',
            'execution_group_id': None,
        }]
        with patch(
            'apps.core.execution.today_execution.build_today_execution',
            return_value={'items': items, 'summaries': {}},
        ):
            resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 200)
        task.refresh_from_db()
        self.assertNotEqual(task.completion_status, 'completed')


class BlockCompleteToggleMixedTests(TestCase):
    """Mixed block: routine item + standalone task at same time.

    The pre-fix bug: clicking the routine checkbox completed only the
    routine items and silently skipped the standalone task. Option C
    must complete every item in the block in one click."""

    def setUp(self):
        self.user = _make_user("block_mixed@test.com")
        self.client.force_login(self.user)
        self.url = reverse(
            'dashboard_v2:block_complete_toggle',
            kwargs={'block_key': '08:00'},
        )

    def test_mixed_block_completes_routine_and_task(self):
        from apps.life.models import Routine, RoutineLog, RoutineSchedule, Task

        routine = Routine.objects.create(
            user=self.user, name='Morning', time_of_day='morning',
        )
        schedule = RoutineSchedule.objects.create(
            routine=routine,
            name='Stretch',
            scheduled_time=time(8, 0),
            importance='flexible',
        )
        task = Task.objects.create(
            user=self.user,
            title='Email',
            scheduled_time=time(8, 0),
            due_date=date.today(),
            completion_status='pending',
        )

        items = [
            {
                'source_type': 'routine_item',
                'source_id': schedule.pk,
                'title': schedule.name,
                'domain': 'life',
                'importance': 'flexible',
                'time_status': 'now',
                'scheduled_time': '08:00',
                'grace_minutes': 0,
                'completion_status': 'pending',
                'completed_today': False,
                'is_actionable': True,
                'is_foundational': False,
                'execution_group_type': 'routine',
                'execution_group_id': routine.pk,
            },
            {
                'source_type': 'task',
                'source_id': task.pk,
                'title': task.title,
                'domain': 'life',
                'importance': 'flexible',
                'time_status': 'now',
                'scheduled_time': '08:00',
                'grace_minutes': 0,
                'completion_status': 'pending',
                'completed_today': False,
                'is_actionable': True,
                'is_foundational': False,
                'execution_group_type': 'standalone',
                'execution_group_id': None,
            },
        ]

        with patch(
            'apps.core.execution.today_execution.build_today_execution',
            return_value={'items': items, 'summaries': {}},
        ):
            resp = self.client.post(self.url)

        self.assertEqual(resp.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.completion_status, 'completed')
        # And the routine item is now complete today (regression for the
        # silent-skip bug — both must complete).
        today = timezone.localdate()
        self.assertTrue(
            RoutineLog.objects.filter(
                schedule=schedule,
                scheduled_date=today,
                log_status__in=('completed', 'completed_late'),
            ).exists(),
            "Routine item must be completed by block-level toggle",
        )


class BlockCompleteToggleIntakeOptimizationTests(TestCase):
    """Pure-intake block must delegate to IntakeGroupLogAction so the
    canonical analytics rollup is preserved."""

    def setUp(self):
        self.user = _make_user("block_intake@test.com")
        self.client.force_login(self.user)
        self.url = reverse(
            'dashboard_v2:block_complete_toggle',
            kwargs={'block_key': '08:00'},
        )

    def test_pure_intake_block_delegates_to_group_log(self):
        items = [
            {
                'source_type': 'medication_dose',
                'source_id': 1,
                'title': 'Vitamin D',
                'domain': 'health',
                'importance': 'foundational',
                'time_status': 'now',
                'scheduled_time': '08:00',
                'grace_minutes': 0,
                'completion_status': 'pending',
                'completed_today': False,
                'is_actionable': True,
                'is_foundational': True,
                'execution_group_type': 'medication_window',
                'execution_group_id': 'morning',
            },
            {
                'source_type': 'medication_dose',
                'source_id': 2,
                'title': 'Fish Oil',
                'domain': 'health',
                'importance': 'foundational',
                'time_status': 'now',
                'scheduled_time': '08:00',
                'grace_minutes': 0,
                'completion_status': 'pending',
                'completed_today': False,
                'is_actionable': True,
                'is_foundational': True,
                'execution_group_type': 'medication_window',
                'execution_group_id': 'morning',
            },
        ]

        with patch(
            'apps.core.execution.today_execution.build_today_execution',
            return_value={'items': items, 'summaries': {}},
        ), patch(
            'apps.dashboard_v2.views.IntakeGroupLogAction.as_view',
        ) as mock_view_factory:
            # The factory returns a callable — our mock makes that
            # callable return a sentinel HttpResponse.
            from django.http import HttpResponse
            mock_callable = mock_view_factory.return_value
            mock_callable.return_value = HttpResponse('intake-delegated', status=200)

            resp = self.client.post(self.url)

            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.content, b'intake-delegated')
            # Confirm we called IntakeGroupLogAction with time_of_day='morning'.
            mock_callable.assert_called_once()
            _args, kwargs = mock_callable.call_args
            self.assertEqual(kwargs.get('time_of_day'), 'morning')


class BlockCompleteToggleEmptyBlockTests(TestCase):
    """Block_key matching no items returns a normal Action Center
    response (not 404 / 500). Defensive behavior."""

    def setUp(self):
        self.user = _make_user("block_empty@test.com")
        self.client.force_login(self.user)

    def test_empty_block_returns_200(self):
        url = reverse(
            'dashboard_v2:block_complete_toggle',
            kwargs={'block_key': '03:00'},  # nothing scheduled at 3 AM
        )
        with patch(
            'apps.core.execution.today_execution.build_today_execution',
            return_value={'items': [], 'summaries': {}},
        ):
            resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)

    def test_malformed_block_key_returns_400(self):
        url = reverse(
            'dashboard_v2:block_complete_toggle',
            kwargs={'block_key': 'notatime'},
        )
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 400)


# ══════════════════════════════════════════════════════════════════════
# 3. Action Center + CoS alignment.
# ══════════════════════════════════════════════════════════════════════


class CosActionCenterAlignmentTests(SimpleTestCase):
    """Same execution items: the prioritizer's grouped view and the
    CoS execution-mode selector resolve the same primary block-level
    action.

    Concretely: the FIRST item the Action Center renders in its first
    'now'-tier group is the same item that get_next_action picks as
    primary."""

    def test_action_center_first_now_block_matches_cos_primary(self):
        from datetime import time as _time
        from apps.core.decision_engine.action_prioritizer import (
            build_grouped_action_center,
        )

        items = [
            _exec_item(source_type='routine_item', source_id=1,
                       title='Measurements', scheduled_time='08:00',
                       group_type='routine', group_id=10),
            _exec_item(source_type='medication_dose', source_id=11,
                       title='Fish Oil', scheduled_time='09:00',
                       group_type='medication_window',
                       group_id='morning', is_foundational=True),
        ]

        # Build grouped Action Center view at 07:55.
        grouped = build_grouped_action_center(items, _time(7, 55))
        now_groups = grouped['phase_groups'].get('now', [])
        self.assertTrue(now_groups, "Expected a 'now' phase block")
        first_block = now_groups[0]
        first_item = first_block['items'][0]

        # Build CoS state with the same items, run execution selector.
        from apps.core.execution.selectors import get_next_action
        from apps.core.decision_engine.action_prioritizer import (
            prioritize_execution_items,
        )

        actions = prioritize_execution_items(items, _time(7, 55))
        active_block = {
            'name': 'morning',
            'start_time': _time(5, 0), 'end_time': _time(10, 0),
            'lead_in_end_time': _time(9, 45),
            'next_block_name': 'mid_morning',
            'next_block_start': _time(10, 0),
            'bounds': {},
        }
        state = {
            'now': _time(7, 55),
            'active_block': active_block,
            'items': items,
            'summaries': {},
            'actions': actions,
            'overdue_actions': [a for a in actions if a['urgency'] == 'overdue'],
            'now_actions':     [a for a in actions if a['urgency'] == 'now'],
            'next_actions':    [a for a in actions if a['urgency'] == 'next'],
            'upcoming_actions':[a for a in actions if a['urgency'] == 'upcoming'],
            'blocked_dependents': {},
        }
        decision = get_next_action(state)

        self.assertIsNotNone(decision['primary_action'])
        self.assertEqual(
            decision['primary_action']['title'],
            first_item['title'],
            "CoS primary action and Action Center first 'now' item must "
            "agree on the same task — same state, same answer.",
        )
