"""Tests for the chronological Action Center timeline (X1).

The Action Center is a daily execution timeline. Chronological time
controls vertical ordering. Urgency / foundationality / recovery
state surface as per-item emphasis metadata only — they MUST NOT
influence vertical order.
"""

import datetime as dt

from django.test import SimpleTestCase

from apps.core.decision_engine.action_prioritizer import (
    RECOVERY_BANNER_COPY,
    _compute_emphasis,
    build_chronological_timeline,
)


def _exec_item(*, source_type='routine_item', source_id, title,
               scheduled_time, completed=False, foundational=False,
               time_status=None, group_type='routine',
               group_id='morning', activity_type=None):
    """Build an ExecutionItem dict matching the contract from
    today_execution.py. Mirrors the test fixtures in
    apps/dashboard_v2/tests/test_block_complete_toggle.py."""
    if time_status is None:
        time_status = (
            'overdue'
            if scheduled_time and scheduled_time < '08:00' and not completed
            else 'upcoming'
        )
    return {
        'source_type': source_type,
        'source_id': source_id,
        'title': title,
        'domain': 'life',
        'importance': 'important',
        'time_status': time_status,
        'scheduled_time': scheduled_time,
        'grace_minutes': 0,
        'completion_status': 'completed' if completed else 'pending',
        'completed_today': completed,
        'is_actionable': not completed,
        'is_foundational': foundational,
        'execution_group_type': group_type,
        'execution_group_id': group_id,
        'parent_title': 'Morning Routine',
        'detail_url': '',
        'toggle_url': '',
        'activity_type': activity_type,
    }


class TimelineChronologicalOrderTests(SimpleTestCase):
    """The strongest invariant of the new model: time controls order."""

    def test_blocks_in_strict_chronological_order(self):
        items = [
            _exec_item(source_id=1, title='Wake up',        scheduled_time='05:30'),
            _exec_item(source_id=2, title='Splash water',   scheduled_time='05:45'),
            _exec_item(source_id=3, title='Morning stretch',scheduled_time='09:00'),
            _exec_item(source_id=4, title='Lunch break',    scheduled_time='13:00'),
        ]
        out = build_chronological_timeline(items, dt.time(9, 0))
        block_keys = [b['block_key'] for b in out['timeline']]
        self.assertEqual(block_keys, ['05:30', '05:45', '09:00', '13:00'])

    def test_overdue_block_appears_before_now_block(self):
        # The user's 9 AM regression: 5:30/5:45 overdue, 9:00 now.
        # Both end up in the timeline; chronological order is preserved.
        items = [
            _exec_item(source_id=1, title='5:30 AM item', scheduled_time='05:30'),
            _exec_item(source_id=2, title='9:00 AM item', scheduled_time='09:00'),
        ]
        out = build_chronological_timeline(items, dt.time(9, 0))
        order = [b['time_display'] for b in out['timeline']]
        self.assertEqual(order, ['5:30 AM', '9:00 AM'])

    def test_future_block_never_above_past_block(self):
        # Even with foundationality + completion mixed, the order is
        # the times. This is the chronological-trust invariant.
        items = [
            _exec_item(source_id=1, title='5:30 AM (foundational future-feel)',
                       scheduled_time='05:30', foundational=True),
            _exec_item(source_id=2, title='13:00 PM (now-tier)',
                       scheduled_time='13:00'),
        ]
        out = build_chronological_timeline(items, dt.time(13, 0))
        order = [b['time_display'] for b in out['timeline']]
        self.assertEqual(order, ['5:30 AM', '1:00 PM'])

    def test_within_block_items_chronological(self):
        items = [
            _exec_item(source_id=1, title='B', scheduled_time='07:00'),
            _exec_item(source_id=2, title='A', scheduled_time='07:00',
                       foundational=True),
        ]
        out = build_chronological_timeline(items, dt.time(7, 30))
        # Same block, foundational first (tie-broken on foundational desc),
        # so 'A' (foundational) appears before 'B'. Within-block order
        # is NOT chronological-only here — it's effective_time then
        # foundational, then title. Effective_time is identical → fall
        # through to foundational; that's allowed because it's intra-
        # block (same time slot).
        self.assertEqual(out['timeline'][0]['items'][0]['title'], 'A')
        self.assertEqual(out['timeline'][0]['items'][1]['title'], 'B')

    def test_foundational_does_not_reorder_across_blocks(self):
        items = [
            _exec_item(source_id=1, title='Early non-foundational',
                       scheduled_time='05:30', foundational=False),
            _exec_item(source_id=2, title='Later foundational',
                       scheduled_time='10:00', foundational=True),
        ]
        out = build_chronological_timeline(items, dt.time(11, 0))
        # Time wins. Foundational does not jump 10:00 above 05:30.
        order = [b['time_display'] for b in out['timeline']]
        self.assertEqual(order, ['5:30 AM', '10:00 AM'])

    def test_chronological_trust_invariant_strictly_monotonic(self):
        # Builder enforces this defensively via a final sort.
        items = [
            _exec_item(source_id=i, title=f'i{i}', scheduled_time=t)
            for i, t in enumerate(['07:00', '11:00', '05:30', '13:00',
                                   '08:15', '09:00'], start=1)
        ]
        out = build_chronological_timeline(items, dt.time(9, 0))
        eff = [b['effective_time'] for b in out['timeline']]
        for a, b in zip(eff, eff[1:]):
            self.assertLessEqual(a, b)


class TimelineFlexibleAndCompletedTests(SimpleTestCase):

    def test_flexible_items_separated_from_timeline(self):
        items = [
            _exec_item(source_id=1, title='Timed', scheduled_time='09:00'),
            _exec_item(source_id=2, title='Unscheduled',
                       scheduled_time=None,
                       group_type='standalone', group_id=None),
        ]
        out = build_chronological_timeline(items, dt.time(9, 0))
        timeline_titles = [
            i['title'] for b in out['timeline'] for i in b['items']
        ]
        flexible_titles = [i['title'] for i in out['flexible_items']]
        self.assertIn('Timed', timeline_titles)
        self.assertNotIn('Unscheduled', timeline_titles)
        self.assertIn('Unscheduled', flexible_titles)

    def test_completed_items_inline_in_their_time_block(self):
        items = [
            _exec_item(source_id=1, title='Morning workout',
                       scheduled_time='06:00', completed=True),
            _exec_item(source_id=2, title='Evening reflection',
                       scheduled_time='20:00'),
        ]
        out = build_chronological_timeline(items, dt.time(14, 0))
        # Completed 6 AM item still appears in its 06:00 block — NOT
        # in a separate Completed Earlier section. Inline continuity.
        block_keys = [b['block_key'] for b in out['timeline']]
        self.assertIn('06:00', block_keys)
        morning = next(b for b in out['timeline'] if b['block_key'] == '06:00')
        self.assertEqual(morning['items'][0]['title'], 'Morning workout')
        self.assertTrue(morning['items'][0]['completed'])


class EmphasisMetadataTests(SimpleTestCase):

    def test_overdue_emphasis(self):
        e = _compute_emphasis({
            'urgency': 'overdue', 'is_foundational': False,
            'completed': False, 'expired': False, 'is_reset_action': False,
        })
        self.assertEqual(e['ring'], 'overdue')
        self.assertEqual(e['tone'], 'warning')
        self.assertEqual(e['badge'], 'past due')
        self.assertFalse(e['recovery_dim'])

    def test_now_emphasis(self):
        e = _compute_emphasis({
            'urgency': 'now', 'is_foundational': False,
            'completed': False, 'expired': False, 'is_reset_action': False,
        })
        self.assertEqual(e['ring'], 'now')
        self.assertEqual(e['tone'], 'active')

    def test_completed_emphasis(self):
        e = _compute_emphasis({
            'urgency': 'overdue', 'is_foundational': True,
            'completed': True, 'expired': False, 'is_reset_action': False,
        })
        # Completion wins — muted/completed, no overdue ring.
        self.assertEqual(e['tone'], 'muted')
        self.assertEqual(e['badge'], 'completed')

    def test_expired_emphasis(self):
        e = _compute_emphasis({
            'urgency': 'overdue', 'is_foundational': True,
            'completed': False, 'expired': True, 'is_reset_action': False,
        })
        self.assertEqual(e['ring'], 'expired')
        self.assertEqual(e['badge'], 'expired')
        self.assertEqual(e['tone'], 'muted')

    def test_foundational_pending_emphasis(self):
        e = _compute_emphasis({
            'urgency': 'upcoming', 'is_foundational': True,
            'completed': False, 'expired': False, 'is_reset_action': False,
        })
        self.assertEqual(e['ring'], 'foundational')
        self.assertEqual(e['badge'], 'foundational')

    def test_reset_action_emphasis(self):
        e = _compute_emphasis({
            'urgency': 'upcoming', 'is_foundational': False,
            'completed': False, 'expired': False, 'is_reset_action': True,
        })
        self.assertEqual(e['badge'], 'reset')

    def test_recovery_dim_in_recovery_mode_for_non_foundational_overdue(self):
        e = _compute_emphasis({
            'urgency': 'overdue', 'is_foundational': False,
            'completed': False, 'expired': False, 'is_reset_action': False,
        }, recovery_mode='RECOVERY')
        self.assertTrue(e['recovery_dim'])
        self.assertEqual(e['tone'], 'muted')

    def test_recovery_dim_not_applied_to_foundational(self):
        e = _compute_emphasis({
            'urgency': 'overdue', 'is_foundational': True,
            'completed': False, 'expired': False, 'is_reset_action': False,
        }, recovery_mode='RECOVERY')
        # Foundational items keep their warning emphasis even in RECOVERY.
        self.assertFalse(e['recovery_dim'])
        self.assertEqual(e['tone'], 'warning')


class RecoveryBannerTests(SimpleTestCase):

    def test_normal_mode_no_banner(self):
        items = [_exec_item(source_id=1, title='X', scheduled_time='09:00')]
        out = build_chronological_timeline(
            items, dt.time(9, 0),
            recovery_state={'mode': 'NORMAL'},
        )
        self.assertIsNone(out['recovery_state']['banner_text'])

    def test_recovery_mode_banner_text(self):
        items = [_exec_item(source_id=1, title='X', scheduled_time='09:00')]
        out = build_chronological_timeline(
            items, dt.time(13, 0),
            recovery_state={'mode': 'RECOVERY',
                            'recoverable_overdue_count': 3},
        )
        self.assertEqual(
            out['recovery_state']['banner_text'],
            'Rebuild the day forward.',
        )
        self.assertEqual(out['recovery_state']['banner_severity'], 'warning')

    def test_stabilize_mode_banner_text(self):
        items = [_exec_item(source_id=1, title='X', scheduled_time='09:00')]
        out = build_chronological_timeline(
            items, dt.time(11, 0),
            recovery_state={'mode': 'STABILIZE'},
        )
        self.assertEqual(
            out['recovery_state']['banner_text'],
            'Take a reset action first.',
        )

    def test_shutdown_mode_banner_text(self):
        items = [_exec_item(source_id=1, title='X', scheduled_time='09:00')]
        out = build_chronological_timeline(
            items, dt.time(21, 0),
            recovery_state={'mode': 'SHUTDOWN'},
        )
        self.assertEqual(
            out['recovery_state']['banner_text'],
            'Focus on closing the day cleanly.',
        )

    def test_banner_copy_table_covers_all_modes(self):
        for mode in ('NORMAL', 'RECOVERY', 'STABILIZE', 'SHUTDOWN'):
            self.assertIn(mode, RECOVERY_BANNER_COPY)


class CollapsedBlockAnnotationTests(SimpleTestCase):

    def test_in_collapsed_block_propagated_to_items(self):
        items = [
            _exec_item(source_id=1, title='Item in collapse',
                       scheduled_time='06:00', foundational=True),
            _exec_item(source_id=2, title='Item not in collapse',
                       scheduled_time='13:00'),
        ]
        collapsed = [{
            'group_type': 'routine',
            'group_id': 'morning',
            'parent_title': 'Morning Routine',
            'item_count': 1,
            'recoverable_count': 1,
            'expired_count': 0,
            'has_foundational_recoverable': True,
            'strategy': 'recover_partially',
            'item_source_ids': [('routine_item', 1)],
        }]
        out = build_chronological_timeline(
            items, dt.time(14, 0),
            collapsed_blocks=collapsed,
        )
        in_collapse = next(
            i for b in out['timeline'] for i in b['items']
            if i['title'] == 'Item in collapse'
        )
        not_in_collapse = next(
            i for b in out['timeline'] for i in b['items']
            if i['title'] == 'Item not in collapse'
        )
        self.assertTrue(in_collapse['in_collapsed_block'])
        self.assertEqual(in_collapse['collapsed_block_strategy'], 'recover_partially')
        self.assertFalse(not_in_collapse['in_collapsed_block'])


class TimelineVersionTests(SimpleTestCase):

    def test_timeline_version_marker(self):
        items = [_exec_item(source_id=1, title='X', scheduled_time='09:00')]
        out = build_chronological_timeline(items, dt.time(9, 0))
        self.assertEqual(out['timeline_version'], 'v2_chronological')

    def test_phase_groups_preserved_for_backward_compat(self):
        items = [_exec_item(source_id=1, title='X', scheduled_time='09:00')]
        out = build_chronological_timeline(items, dt.time(9, 0))
        self.assertIn('phase_groups', out)
        # Standard buckets still present.
        for k in ('now', 'upcoming', 'later', 'flexible', 'done'):
            self.assertIn(k, out['phase_groups'])
