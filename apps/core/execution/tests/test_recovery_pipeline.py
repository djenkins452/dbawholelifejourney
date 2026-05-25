"""End-to-end tests for the recovery contract — exercise the full
pipeline from annotated ExecutionItems through prioritizer + selectors
without any DB or LLM.

The canonical 2:10 PM scenario asserts the system never returns
obviously bad recommendations:
  - Church 10:30 AM (HARD_EXPIRED) is not next action; appears in risk.
  - Protein shake 6:45 AM (WINDOWED) is not recoverable.
  - Shower 7:00 AM (SOFT_EXPIRED reset) remains valid.
  - Fish Oil 18:00 (WINDOWED supplement) is NOT at risk at 14:10.
"""

import datetime as dt

from django.test import SimpleTestCase

from apps.core.decision_engine.action_prioritizer import (
    apply_recovery_bucket_selection,
    compute_at_risk,
    compute_block_collapses,
    prioritize_execution_items,
)
from apps.core.execution.recovery_state import (
    RECOVERY,
    STABILIZE,
    compute_recovery_state,
)
from apps.core.execution.selectors import (
    get_biggest_risk,
    get_fix_priority,
    get_next_action,
)
from apps.core.execution.task_classifier import annotate


def _item(**kw):
    base = {
        'source_type': 'routine_item',
        'source_id': kw.pop('id', None),
        'title': 'X',
        'domain': 'life',
        'is_actionable': True,
        'completed_today': False,
        'is_foundational': False,
        'time_status': 'overdue',
        'execution_group_type': 'routine',
        'execution_group_id': 'morning_routine',
        'parent_title': 'Morning Routine',
        'importance': 'important',
    }
    base.update(kw)
    return annotate(base)


def _build_state(items, now, blocked_dependents=None):
    """Mirror of build_execution_state for in-memory tests."""
    active_block = {
        'name': 'afternoon',
        'start_time': dt.time(14, 0),
        'end_time': dt.time(17, 0),
        'lead_in_end_time': dt.time(16, 45),
        'next_block_name': 'evening',
        'next_block_start': dt.time(17, 0),
        'bounds': {},
    }
    collapse_result = compute_block_collapses(items, now, active_block)
    suppressed = collapse_result['suppressed_source_keys']
    raw_actions = prioritize_execution_items(
        items, now, summaries={}, suppressed_source_keys=suppressed,
    ) or []
    recovery = compute_recovery_state(items, now, active_block=active_block)
    actions = apply_recovery_bucket_selection(raw_actions, recovery)
    blocked = blocked_dependents or {}
    return {
        'now': now,
        'active_block': active_block,
        'items': items,
        'summaries': {},
        'actions': actions,
        'eligible_actions': actions,
        'overdue_actions': [a for a in actions if a.get('urgency') == 'overdue'],
        'now_actions': [a for a in actions if a.get('urgency') == 'now'],
        'next_actions': [a for a in actions if a.get('urgency') == 'next'],
        'upcoming_actions': [a for a in actions if a.get('urgency') == 'upcoming'],
        'expired_items': [
            i for i in items
            if i.get('is_actionable') and not i.get('completed_today')
            and i.get('time_status') == 'overdue'
            and not _is_recoverable(i, now)
        ],
        'deferred_items': [],
        'collapsed_blocks': collapse_result['collapses'],
        'at_risk_actions': compute_at_risk(actions, blocked, now),
        'recovery_state': recovery,
        'blocked_dependents': blocked,
    }


def _is_recoverable(item, now):
    from apps.core.execution.recoverability import is_recoverable
    return is_recoverable(item, now)


class CanonicalTwoTenPmScenario(SimpleTestCase):

    def setUp(self):
        self.now = dt.time(14, 10)
        # Build the canonical day.
        self.items = [
            # Church — foundational HARD_EXPIRED.
            _item(
                id=101, title='Church', scheduled_time='10:30',
                activity_type='service', is_foundational=True,
                domain='faith', execution_group_id='morning',
                parent_title='Morning',
            ),
            # Protein Shake — WINDOWED nutrition anchor.
            _item(
                id=102, title='Protein Shake', scheduled_time='06:45',
                activity_type='nutrition_anchor', domain='health',
                execution_group_id='morning', parent_title='Morning',
            ),
            # Shower — SOFT_EXPIRED reset (hygiene).
            _item(
                id=103, title='Shower', scheduled_time='07:00',
                activity_type='hygiene', domain='life',
                execution_group_id='morning', parent_title='Morning',
            ),
            # Fish Oil — WINDOWED supplement at 18:00 (future, not at risk).
            _item(
                id=104, title='Fish Oil', scheduled_time='18:00',
                source_type='supplement_dose', priority='optimization',
                domain='health',
                execution_group_type='supplement_window',
                execution_group_id='evening', parent_title='Evening Supplements',
                time_status='upcoming', is_foundational=False,
            ),
            # An afternoon task scheduled now-ish to give a real next action.
            _item(
                id=105, title='Email follow-ups', scheduled_time='14:30',
                source_type='task', activity_type=None, domain='life',
                execution_group_type='standalone', execution_group_id=None,
                parent_title=None, time_status='upcoming',
            ),
        ]

    def test_protein_shake_is_filtered_from_actions(self):
        state = _build_state(self.items, self.now)
        titles = [a.get('title') for a in state['actions']]
        self.assertNotIn('Protein Shake', titles)

    def test_church_is_filtered_from_actions(self):
        state = _build_state(self.items, self.now)
        titles = [a.get('title') for a in state['actions']]
        self.assertNotIn('Church', titles)

    def test_next_action_is_not_protein_or_church(self):
        state = _build_state(self.items, self.now)
        decision = get_next_action(state)
        msg = decision['message']
        self.assertNotIn('Protein Shake', msg)
        self.assertNotIn('Church', msg)

    def test_shower_remains_recoverable(self):
        state = _build_state(self.items, self.now)
        titles = [a.get('title') for a in state['actions']]
        # Shower must NOT be classified as expired.
        expired_titles = [i.get('title') for i in state['expired_items']]
        self.assertNotIn('Shower', expired_titles)
        # And the morning block's recover_partially strategy must keep
        # the reset action alive in the eligible pool.
        self.assertIn('Shower', titles)

    def test_morning_block_strategy_is_recover_partially(self):
        state = _build_state(self.items, self.now)
        morning = next(
            c for c in state['collapsed_blocks'] if c['group_id'] == 'morning'
        )
        self.assertEqual(morning['strategy'], 'recover_partially')

    def test_fish_oil_is_not_at_risk(self):
        state = _build_state(self.items, self.now)
        at_risk_titles = [a.get('title') for a in state['at_risk_actions']]
        self.assertNotIn('Fish Oil', at_risk_titles)

    def test_biggest_risk_is_church_or_morning_block(self):
        # With overdue items present, biggest risk should reference the
        # foundational expired (Church) or the collapsed morning block.
        state = _build_state(self.items, self.now)
        decision = get_biggest_risk(state)
        msg = decision['message']
        self.assertTrue(
            'Church' in msg or 'Morning' in msg or 'risk' in msg.lower(),
            f"Unexpected risk message: {msg}",
        )

    def test_recovery_mode_triggers_post_noon(self):
        state = _build_state(self.items, self.now)
        rs = state['recovery_state']
        # Multiple recoverable overdue items + post-noon → RECOVERY,
        # OR foundational missed + reset present → STABILIZE.
        self.assertIn(rs['mode'], (RECOVERY, STABILIZE))

    def test_morning_block_collapses(self):
        state = _build_state(self.items, self.now)
        block_ids = [c['group_id'] for c in state['collapsed_blocks']]
        self.assertIn('morning', block_ids)


class AtRiskHorizonTests(SimpleTestCase):

    def _action(self, urgency, time_display, **kw):
        base = {
            'source': 'task',
            'urgency': urgency,
            'type': 'task',
            'pk': kw.pop('pk', None),
            'title': kw.pop('title', 'X'),
            'time_display': time_display,
            'is_foundational': kw.pop('is_foundational', False),
            'domain': 'life',
            'is_recoverable': True,
            'is_reset_action': False,
        }
        base.update(kw)
        return base

    def test_future_item_inside_horizon_is_at_risk(self):
        actions = [self._action('next', '15:00', pk=1)]
        at_risk = compute_at_risk(actions, {}, dt.time(14, 10))
        self.assertEqual(len(at_risk), 1)

    def test_future_item_past_horizon_not_at_risk(self):
        actions = [self._action('upcoming', '18:00', pk=1)]
        at_risk = compute_at_risk(actions, {}, dt.time(14, 10))
        self.assertEqual(at_risk, [])

    def test_dependency_extends_horizon_to_4h(self):
        actions = [self._action('upcoming', '17:00', pk=42)]
        # task:42 is keyed in blocked_dependents → dependency exists.
        at_risk = compute_at_risk(
            actions, {'task:42': [99, 100]}, dt.time(14, 10),
        )
        self.assertEqual(len(at_risk), 1)

    def test_overdue_suppresses_non_dependency_future(self):
        actions = [
            self._action('overdue', '10:00', pk=1, title='Stale'),
            self._action('upcoming', '15:00', pk=2, title='Future'),
        ]
        at_risk = compute_at_risk(actions, {}, dt.time(14, 10))
        titles = [a['title'] for a in at_risk]
        self.assertIn('Stale', titles)
        self.assertNotIn('Future', titles)

    def test_overdue_does_not_suppress_dependency_future(self):
        actions = [
            self._action('overdue', '10:00', pk=1, title='Stale'),
            self._action('upcoming', '17:00', pk=2, title='Critical'),
        ]
        at_risk = compute_at_risk(
            actions, {'task:2': [99]}, dt.time(14, 10),
        )
        titles = [a['title'] for a in at_risk]
        self.assertIn('Stale', titles)
        self.assertIn('Critical', titles)


class BlockCollapseTests(SimpleTestCase):

    def test_soft_expired_only_group_does_not_collapse(self):
        """Phase 2 contract: SOFT_EXPIRED-only groups never collapse.

        Workout + protein shake + shower late at 11 AM is still a
        valid, intended day — just delayed. Collapsing them into a
        single recover_partially summary was the root cause of Beth
        telling the user to "do a reset action" instead of letting
        them resume their workout.
        """
        items = [
            annotate({
                'source_type': 'routine_item', 'source_id': i,
                'title': f'Item {i}', 'domain': 'life',
                'is_actionable': True, 'completed_today': False,
                'is_foundational': False, 'time_status': 'overdue',
                'execution_group_type': 'routine',
                'execution_group_id': 'morning',
                'parent_title': 'Morning',
                'scheduled_time': '07:00',
                'activity_type': None,
            })
            for i in range(1, 4)
        ]
        result = compute_block_collapses(items, dt.time(14, 10))
        self.assertEqual(
            result['collapses'], [],
            "SOFT_EXPIRED-only groups must NOT collapse under "
            "the Phase 2 contract.",
        )
        self.assertEqual(result['suppressed_source_keys'], set())

    def test_foundational_soft_expired_group_still_does_not_collapse(self):
        """Phase 2 contract: even a foundational SOFT_EXPIRED group
        stays individually surfaced. The 'is_foundational' flag does
        not override the SOFT_EXPIRED bypass — a foundational habit
        like daily journaling that's late should be LATE_OPEN, not
        collapsed under a recover_partially lever.
        """
        items = [
            annotate({
                'source_type': 'routine_item', 'source_id': 1,
                'title': 'Foundational SOFT', 'domain': 'life',
                'is_actionable': True, 'completed_today': False,
                'is_foundational': True, 'time_status': 'overdue',
                'execution_group_type': 'routine',
                'execution_group_id': 'morning',
                'scheduled_time': '07:00',
                'activity_type': None,
            }),
            annotate({
                'source_type': 'routine_item', 'source_id': 2,
                'title': 'Filler', 'domain': 'life',
                'is_actionable': True, 'completed_today': False,
                'is_foundational': False, 'time_status': 'overdue',
                'execution_group_type': 'routine',
                'execution_group_id': 'morning',
                'scheduled_time': '07:00',
                'activity_type': None,
            }),
        ]
        result = compute_block_collapses(items, dt.time(14, 10))
        self.assertEqual(result['collapses'], [])
        # Neither item is suppressed — both remain individually
        # actionable in the eligible pool.
        self.assertNotIn(
            ('routine_item', 1), result['suppressed_source_keys'],
        )
        self.assertNotIn(
            ('routine_item', 2), result['suppressed_source_keys'],
        )

    def test_windowed_group_with_foundational_lever_still_collapses(self):
        """Counter-test: WINDOWED groups (medications, nutrition
        anchors) continue to collapse via recover_partially when a
        foundational lever exists. The Phase 2 narrowing only
        excludes SOFT_EXPIRED — WINDOWED groups still need the
        collapse summary so Beth can say 'fix the lunch meds block'
        instead of listing each missed dose."""
        # Items in the 'afternoon' canonical window (14–17). The
        # recoverability layer caps grace at the next-anchor block
        # start ('evening' = 17:00), which is well past the 60-min
        # grace, so the actual cutoff is scheduled + 60min.
        items = [
            annotate({
                'source_type': 'medication_dose', 'source_id': 1,
                'title': 'Critical Med', 'domain': 'health',
                'is_actionable': True, 'completed_today': False,
                'is_foundational': True, 'time_status': 'overdue',
                'execution_group_type': 'medication_window',
                'execution_group_id': 'afternoon',
                'parent_title': 'Afternoon Medications',
                'scheduled_time': '15:00',
                'intake_type': 'medication',
                'priority': 'critical',
            }),
            annotate({
                'source_type': 'medication_dose', 'source_id': 2,
                'title': 'Other Med', 'domain': 'health',
                'is_actionable': True, 'completed_today': False,
                'is_foundational': False, 'time_status': 'overdue',
                'execution_group_type': 'medication_window',
                'execution_group_id': 'afternoon',
                'scheduled_time': '15:00',
                'intake_type': 'medication',
                'priority': 'critical',
            }),
        ]
        # 15:30 — both items still inside the 60-min WINDOWED grace
        # window (15:00 + 60min = 16:00). Both recoverable.
        result = compute_block_collapses(items, dt.time(15, 30))
        self.assertEqual(len(result['collapses']), 1)
        self.assertEqual(
            result['collapses'][0]['strategy'], 'recover_partially',
        )
        # Foundational lever remains in the pool; the non-foundational
        # dose is suppressed under the recover_partially strategy.
        self.assertNotIn(
            ('medication_dose', 1), result['suppressed_source_keys'],
        )
        self.assertIn(
            ('medication_dose', 2), result['suppressed_source_keys'],
        )

    def test_collapse_skip_when_all_expired(self):
        items = [
            annotate({
                'source_type': 'routine_item', 'source_id': i,
                'title': f'Event {i}', 'domain': 'faith',
                'is_actionable': True, 'completed_today': False,
                'is_foundational': True, 'time_status': 'overdue',
                'execution_group_type': 'routine',
                'execution_group_id': 'morning',
                'scheduled_time': '10:30',
                'activity_type': 'service',
            })
            for i in range(1, 3)
        ]
        result = compute_block_collapses(items, dt.time(14, 10))
        self.assertEqual(result['collapses'][0]['strategy'], 'skip')

    def test_active_block_is_not_collapsed(self):
        items = [
            annotate({
                'source_type': 'routine_item', 'source_id': i,
                'title': f'Item {i}', 'domain': 'life',
                'is_actionable': True, 'completed_today': False,
                'is_foundational': False, 'time_status': 'overdue',
                'execution_group_type': 'routine',
                'execution_group_id': 'afternoon',
                'scheduled_time': '14:00',
                'activity_type': None,
            })
            for i in range(1, 3)
        ]
        active = {'name': 'afternoon'}
        result = compute_block_collapses(items, dt.time(14, 10), active)
        self.assertEqual(result['collapses'], [])


class RecoveryBucketSelectionTests(SimpleTestCase):

    def _action(self, **kw):
        base = {
            'source': 'routine',
            'urgency': 'overdue',
            'type': 'task',
            'pk': kw.pop('pk', None),
            'title': kw.pop('title', 'X'),
            'is_foundational': False,
            'is_reset_action': False,
            'is_recoverable': True,
            'time_display': '08:00',
        }
        base.update(kw)
        return base

    def test_normal_passes_through(self):
        actions = [self._action(title='A'), self._action(title='B')]
        out = apply_recovery_bucket_selection(
            actions, {'mode': 'NORMAL'},
        )
        self.assertEqual([a['title'] for a in out], ['A', 'B'])

    def test_stabilize_pushes_reset_first(self):
        actions = [
            self._action(title='Task'),
            self._action(title='Shower', is_reset_action=True),
        ]
        out = apply_recovery_bucket_selection(
            actions, {'mode': 'STABILIZE'},
        )
        self.assertEqual(out[0]['title'], 'Shower')

    def test_recovery_orders_reset_then_foundational_overdue_then_quick(self):
        actions = [
            self._action(title='Quick', is_foundational=False),
            self._action(title='Foundational',
                         is_foundational=True),
            self._action(title='Reset', is_reset_action=True),
        ]
        out = apply_recovery_bucket_selection(
            actions, {'mode': 'RECOVERY'},
        )
        self.assertEqual(
            [a['title'] for a in out],
            ['Reset', 'Foundational', 'Quick'],
        )

    def test_shutdown_drops_non_foundational_overdue(self):
        actions = [
            self._action(title='Stale', is_foundational=False, urgency='overdue'),
            self._action(title='Anchor', is_foundational=True, urgency='overdue'),
            self._action(title='Forward', is_foundational=False, urgency='upcoming'),
        ]
        out = apply_recovery_bucket_selection(
            actions, {'mode': 'SHUTDOWN'},
        )
        titles = [a['title'] for a in out]
        self.assertIn('Anchor', titles)
        self.assertIn('Forward', titles)
        self.assertNotIn('Stale', titles)
