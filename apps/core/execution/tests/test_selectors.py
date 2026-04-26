"""
Tests for the three CoS decision-mode selectors.

Verifies:
- All three selectors consume the same `state` shape from
  build_execution_state (no parallel engines).
- Same state, three distinct outputs (mode separation).
- Execution mode honors the active-block + overdue/now eligibility
  contract (regression for the 07:55 Measurements/Fish Oil bug).
- Risk mode prioritizes foundational + overdue, then oldest overdue,
  then domain weight.
- Fix mode prioritizes overdue items by downstream unblock count
  (using state['blocked_dependents']).
"""

import datetime

from django.test import SimpleTestCase

from apps.core.execution.selectors import (
    get_biggest_risk,
    get_fix_priority,
    get_next_action,
    select,
)


def _action(title, urgency, *, time_display='', source='routine',
            is_foundational=False, atype='task', pk=None,
            commitment_level='important'):
    return {
        'source': source,
        'urgency': urgency,
        'type': atype,
        'pk': pk,
        'title': title,
        'source_url': '',
        'can_complete': True,
        'is_foundational': is_foundational,
        'commitment_level': commitment_level,
        'goal_name': '',
        'time_of_day': None,
        'time_display': time_display,
    }


def _state(actions, *, now=datetime.time(8, 0), active_block=None,
           blocked_dependents=None):
    """Build a state dict mirroring build_execution_state output shape."""
    if active_block is None:
        # Default: morning canonical block
        active_block = {
            'name': 'morning',
            'start_time': datetime.time(5, 0),
            'end_time': datetime.time(10, 0),
            'lead_in_end_time': datetime.time(9, 45),
            'next_block_name': 'mid_morning',
            'next_block_start': datetime.time(10, 0),
            'bounds': {},
        }
    return {
        'now': now,
        'active_block': active_block,
        'items': [],
        'summaries': {},
        'actions': actions,
        'overdue_actions': [a for a in actions if a['urgency'] == 'overdue'],
        'now_actions':     [a for a in actions if a['urgency'] == 'now'],
        'next_actions':    [a for a in actions if a['urgency'] == 'next'],
        'upcoming_actions':[a for a in actions if a['urgency'] == 'upcoming'],
        'blocked_dependents': blocked_dependents or {},
    }


# ══════════════════════════════════════════════════════════════════════
# EXECUTION MODE
# ══════════════════════════════════════════════════════════════════════

class ExecutionModeTests(SimpleTestCase):

    def test_07_55_measurements_wins_over_fish_oil(self):
        """Regression: at 07:55, Measurements (08:00, urgency=now) is
        primary; Fish Oil (09:00, urgency=next) is follow-on only."""
        actions = [
            _action('Measurements', 'now', time_display='08:00',
                    source='routine'),
            _action('Fish Oil', 'next', time_display='09:00',
                    source='intake', is_foundational=True),
        ]
        state = _state(actions, now=datetime.time(7, 55))

        result = get_next_action(state)
        self.assertEqual(result['mode'], 'execution')
        self.assertEqual(result['primary_action']['title'], 'Measurements')
        self.assertTrue(
            result['message'].startswith('Start with Measurements'),
            f"Got: {result['message']!r}",
        )
        # Fish Oil may appear as follow-on but must NOT be primary.
        self.assertNotEqual(
            result['primary_action']['title'], 'Fish Oil',
        )

    def test_clear_state_returns_forward_hint(self):
        actions = [
            _action('Evening Review', 'upcoming', time_display='18:00',
                    source='routine'),
        ]
        state = _state(actions, now=datetime.time(8, 0))

        result = get_next_action(state)
        self.assertEqual(result['mode'], 'execution')
        self.assertIsNone(result['primary_action'])
        self.assertIn("clear right now", result['message'].lower())

    def test_no_actions_says_complete(self):
        result = get_next_action(_state([]))
        self.assertEqual(result['mode'], 'execution')
        self.assertIsNone(result['primary_action'])
        self.assertIn('All items are complete', result['message'])


# ══════════════════════════════════════════════════════════════════════
# RISK MODE
# ══════════════════════════════════════════════════════════════════════

class RiskModeTests(SimpleTestCase):

    def test_foundational_overdue_beats_non_foundational_overdue(self):
        actions = [
            _action('Stretch', 'overdue', time_display='07:30',
                    source='routine', is_foundational=False),
            _action('Morning Meds', 'overdue', time_display='08:00',
                    source='medication', is_foundational=True),
        ]
        state = _state(actions, now=datetime.time(9, 0))

        result = get_biggest_risk(state)
        self.assertEqual(result['mode'], 'risk')
        self.assertEqual(result['primary_action']['title'], 'Morning Meds')
        self.assertIn('Foundational', result['reason'])

    def test_oldest_overdue_wins_when_both_foundational(self):
        actions = [
            _action('Morning Meds', 'overdue', time_display='08:00',
                    source='medication', is_foundational=True),
            _action('Wake-up Prayer', 'overdue', time_display='06:00',
                    source='faith', is_foundational=True),
        ]
        state = _state(actions, now=datetime.time(10, 0))

        result = get_biggest_risk(state)
        # Earlier scheduled time = longer overdue ⇒ wins.
        self.assertEqual(result['primary_action']['title'], 'Wake-up Prayer')

    def test_domain_weight_breaks_tie(self):
        """Same foundationality + same time → health domain beats journal."""
        actions = [
            _action('Journal', 'overdue', time_display='08:00',
                    source='journal', is_foundational=True),
            _action('Glucose Reading', 'overdue', time_display='08:00',
                    source='health', is_foundational=True),
        ]
        state = _state(actions, now=datetime.time(9, 0))

        result = get_biggest_risk(state)
        self.assertEqual(
            result['primary_action']['title'], 'Glucose Reading',
        )

    def test_no_overdue_no_now_returns_empty(self):
        actions = [
            _action('Late thing', 'upcoming', time_display='20:00',
                    source='routine'),
        ]
        state = _state(actions, now=datetime.time(8, 0))
        result = get_biggest_risk(state)
        self.assertIsNone(result['primary_action'])
        self.assertIn('nothing at risk', result['message'].lower())

    def test_no_overdue_falls_back_to_now_window(self):
        actions = [
            _action('Foundational Now Item', 'now', time_display='08:00',
                    source='medication', is_foundational=True),
        ]
        state = _state(actions, now=datetime.time(8, 0))
        result = get_biggest_risk(state)
        self.assertEqual(
            result['primary_action']['title'], 'Foundational Now Item',
        )
        self.assertIn('about to slip', result['reason'].lower())


# ══════════════════════════════════════════════════════════════════════
# FIX MODE
# ══════════════════════════════════════════════════════════════════════

class FixModeTests(SimpleTestCase):

    def test_picks_overdue_with_most_unblock_count(self):
        actions = [
            _action('File Receipts', 'overdue', time_display='08:00',
                    source='task', atype='task', pk=10,
                    commitment_level='flexible'),
            _action('Update Spreadsheet', 'overdue', time_display='08:30',
                    source='task', atype='task', pk=20,
                    commitment_level='flexible'),
        ]
        # Update Spreadsheet (pk=20) unblocks 3 dependents; File Receipts (pk=10) unblocks 1.
        state = _state(actions, blocked_dependents={
            'task:10': [101],
            'task:20': [201, 202, 203],
        })

        result = get_fix_priority(state)
        self.assertEqual(result['mode'], 'fix')
        self.assertEqual(
            result['primary_action']['title'], 'Update Spreadsheet',
        )
        self.assertIn('unlock 3', result['message'])

    def test_simplest_quick_win_when_no_unblocks(self):
        """When no items unblock anything, pick the simplest commitment level."""
        actions = [
            _action('Hard Foundational', 'overdue', time_display='08:00',
                    source='task', atype='task', pk=1,
                    commitment_level='foundational'),
            _action('Quick Flex', 'overdue', time_display='08:30',
                    source='task', atype='task', pk=2,
                    commitment_level='flexible'),
        ]
        state = _state(actions, blocked_dependents={})

        result = get_fix_priority(state)
        self.assertEqual(result['primary_action']['title'], 'Quick Flex')

    def test_no_overdue_returns_empty(self):
        actions = [
            _action('On track', 'now', time_display='08:00',
                    source='routine'),
        ]
        state = _state(actions, blocked_dependents={})

        result = get_fix_priority(state)
        self.assertIsNone(result['primary_action'])
        self.assertIn('Nothing to fix', result['message'])

    def test_routine_unblock_via_routine_key(self):
        """A routine item unblocks via 'routine:{pk}' canonical key."""
        actions = [
            _action('Morning Walk', 'overdue', time_display='07:00',
                    source='routine', atype='task', pk=42),
        ]
        state = _state(actions, blocked_dependents={
            'routine:42': [501, 502],
        })

        result = get_fix_priority(state)
        self.assertEqual(result['primary_action']['title'], 'Morning Walk')
        self.assertIn('unlock 2', result['message'])


# ══════════════════════════════════════════════════════════════════════
# MODE SEPARATION — same state, three distinct outputs
# ══════════════════════════════════════════════════════════════════════

class ModeSeparationTests(SimpleTestCase):
    """The headline guarantee: same input → three different answers."""

    def setUp(self):
        # A realistic morning at 09:00 with a mixed load:
        #   - Foundational + overdue medication from earlier (highest risk)
        #   - A pending routine in the now-window (next action to do)
        #   - An overdue task that unblocks 3 downstream tasks (best fix)
        self.actions = [
            # Highest risk: foundational + overdue from earliest time.
            _action('Morning Meds', 'overdue', time_display='07:30',
                    source='medication', is_foundational=True,
                    atype='medicine_group'),
            # Next thing to do: in the now-window.
            _action('Glucose Check', 'now', time_display='09:00',
                    source='routine', is_foundational=False,
                    atype='task', pk=99),
            # Best fix: overdue task that unblocks 3 dependents.
            _action('File Receipts', 'overdue', time_display='08:30',
                    source='task', is_foundational=False,
                    atype='task', pk=20,
                    commitment_level='flexible'),
        ]
        self.state = _state(
            self.actions, now=datetime.time(9, 0),
            blocked_dependents={'task:20': [201, 202, 203]},
        )

    def test_execution_picks_overdue_item_in_active_block(self):
        result = get_next_action(self.state)
        self.assertEqual(result['mode'], 'execution')
        self.assertIsNotNone(result['primary_action'])
        # Execution mode follows urgency → time. Overdue beats now;
        # earliest overdue wins. 07:30 Morning Meds is earliest.
        self.assertEqual(
            result['primary_action']['title'], 'Morning Meds',
        )

    def test_risk_picks_foundational_overdue(self):
        result = get_biggest_risk(self.state)
        self.assertEqual(result['mode'], 'risk')
        self.assertEqual(
            result['primary_action']['title'], 'Morning Meds',
        )
        self.assertIn('Foundational', result['reason'])

    def test_fix_picks_highest_unblock_overdue(self):
        result = get_fix_priority(self.state)
        self.assertEqual(result['mode'], 'fix')
        self.assertEqual(
            result['primary_action']['title'], 'File Receipts',
        )
        self.assertIn('unlock 3', result['message'])

    def test_three_modes_produce_distinct_messages(self):
        """The three messages must be visibly different. No blending."""
        e = get_next_action(self.state)['message']
        r = get_biggest_risk(self.state)['message']
        f = get_fix_priority(self.state)['message']

        self.assertNotEqual(e, r)
        self.assertNotEqual(r, f)
        self.assertNotEqual(e, f)
        # And each must use its mode's signature opener.
        self.assertTrue(e.startswith('Start with'))
        self.assertTrue(r.startswith('Your biggest risk'))
        self.assertTrue(f.startswith('Start by fixing'))

    def test_select_dispatch_routes_correctly(self):
        e = select('execution', self.state)
        r = select('risk', self.state)
        f = select('fix', self.state)
        self.assertEqual(e['mode'], 'execution')
        self.assertEqual(r['mode'], 'risk')
        self.assertEqual(f['mode'], 'fix')

    def test_select_unknown_mode_defaults_to_execution(self):
        result = select('mystery', self.state)
        self.assertEqual(result['mode'], 'execution')
