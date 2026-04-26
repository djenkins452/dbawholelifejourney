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
        primary. Spec format: 'Next: Measurements. Do this now.'"""
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
        self.assertEqual(
            result['message'], 'Next: Measurements. Do this now.',
        )

    def test_5_30_overdue_at_noon_NOT_in_execution(self):
        """Regression: at noon (lunch block), an overdue 5:30 AM
        prayer must NOT be the Execution-mode primary. It belongs in
        Risk/Fix only."""
        # Lunch block (12-14)
        ab = {
            'name': 'lunch',
            'start_time': datetime.time(12, 0),
            'end_time': datetime.time(14, 0),
            'lead_in_end_time': datetime.time(13, 45),
            'next_block_name': 'afternoon',
            'next_block_start': datetime.time(14, 0),
            'bounds': {},
        }
        actions = [
            _action('Morning Prayer', 'overdue', time_display='05:30',
                    source='faith', is_foundational=True),
        ]
        state = _state(actions, now=datetime.time(12, 0), active_block=ab)

        result = get_next_action(state)
        # The 5:30 AM item is two blocks back from lunch — NOT
        # Execution-eligible. With nothing else current, Execution
        # should report "Nothing pending right now."
        self.assertIsNone(result['primary_action'])
        self.assertNotIn('Morning Prayer', result['message'])

    def test_clear_state_returns_forward_hint(self):
        actions = [
            _action('Evening Review', 'upcoming', time_display='18:00',
                    source='routine'),
        ]
        state = _state(actions, now=datetime.time(8, 0))

        result = get_next_action(state)
        self.assertEqual(result['mode'], 'execution')
        self.assertIsNone(result['primary_action'])
        # Forward hint: identifies the item, but does NOT instruct
        # "Do this now" (since it's not yet actionable).
        self.assertEqual(
            result['message'], 'Next: Evening Review.',
        )

    def test_no_actions_says_pending(self):
        result = get_next_action(_state([]))
        self.assertEqual(result['mode'], 'execution')
        self.assertIsNone(result['primary_action'])
        self.assertEqual(result['message'], 'Nothing pending right now.')


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
        # Spec format: "Biggest risk: X. Fix this next." — no minute
        # math, no time suffix, no reason text.
        self.assertEqual(
            result['message'],
            'Biggest risk: Morning Meds. Fix this next.',
        )

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
        self.assertEqual(result['message'], 'No risks right now.')

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
        self.assertEqual(
            result['message'],
            'Biggest risk: Foundational Now Item. Fix this next.',
        )


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
        # Update Spreadsheet (pk=20) unblocks 3 dependents.
        state = _state(actions, blocked_dependents={
            'task:10': [101],
            'task:20': [201, 202, 203],
        })

        result = get_fix_priority(state)
        self.assertEqual(result['mode'], 'fix')
        self.assertEqual(
            result['primary_action']['title'], 'Update Spreadsheet',
        )
        # Spec: "Fix this first: X." — no impact text.
        self.assertEqual(
            result['message'],
            'Fix this first: Update Spreadsheet.',
        )

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
        self.assertEqual(result['message'], 'Nothing to fix.')

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
        self.assertEqual(
            result['message'], 'Fix this first: Morning Walk.',
        )


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
        self.assertEqual(
            result['message'],
            'Biggest risk: Morning Meds. Fix this next.',
        )

    def test_fix_picks_highest_unblock_overdue(self):
        result = get_fix_priority(self.state)
        self.assertEqual(result['mode'], 'fix')
        self.assertEqual(
            result['primary_action']['title'], 'File Receipts',
        )
        self.assertEqual(
            result['message'], 'Fix this first: File Receipts.',
        )

    def test_three_modes_produce_distinct_messages(self):
        """The three messages must be visibly different. No blending.
        Spec openers (per CoS Strict Mode Isolation):
            Execution: 'Next: ...'
            Risk:      'Biggest risk: ...'
            Fix:       'Fix this first: ...'
        """
        e = get_next_action(self.state)['message']
        r = get_biggest_risk(self.state)['message']
        f = get_fix_priority(self.state)['message']

        self.assertNotEqual(e, r)
        self.assertNotEqual(r, f)
        self.assertNotEqual(e, f)
        self.assertTrue(e.startswith('Next:'), f"Got: {e!r}")
        self.assertTrue(r.startswith('Biggest risk:'), f"Got: {r!r}")
        self.assertTrue(f.startswith('Fix this first:'), f"Got: {f!r}")
        # No time math anywhere.
        for msg in (e, r, f):
            self.assertNotRegex(
                msg, r'\d+\s*(min|minutes)\b',
                f"Time-math language leaked into: {msg!r}",
            )

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


# ══════════════════════════════════════════════════════════════════════
# STRICT MODE ISOLATION — midday past-action regression
# ══════════════════════════════════════════════════════════════════════

class StrictModeIsolationMiddayTests(SimpleTestCase):
    """The user spec scenario:
        At midday with early-morning missed items —
        Execution: shows current valid action ONLY.
        Risk:      shows missed morning item.
        Fix:       shows ONE recovery action.
    """

    def setUp(self):
        # 12:00 noon, lunch block (12-14).
        self.lunch_block = {
            'name': 'lunch',
            'start_time': datetime.time(12, 0),
            'end_time': datetime.time(14, 0),
            'lead_in_end_time': datetime.time(13, 45),
            'next_block_name': 'afternoon',
            'next_block_start': datetime.time(14, 0),
            'bounds': {},
        }
        self.actions = [
            # 5:30 AM prayer — overdue, 6+ hours stale, in 'morning' block
            # (two blocks back from lunch). MUST NOT appear in Execution.
            _action('Morning Prayer', 'overdue', time_display='05:30',
                    source='faith', is_foundational=True,
                    atype='task', pk=11),
            # 12:30 PM lunch break — current valid action.
            _action('Eat Lunch', 'now', time_display='12:30',
                    source='routine', is_foundational=False,
                    atype='task', pk=22),
        ]
        self.state = _state(
            self.actions, now=datetime.time(12, 0),
            active_block=self.lunch_block,
            blocked_dependents={},
        )

    def test_execution_shows_current_valid_action_only(self):
        """Execution must pick 12:30 lunch, NOT the 5:30 AM prayer."""
        result = get_next_action(self.state)
        self.assertEqual(result['mode'], 'execution')
        self.assertEqual(
            result['primary_action']['title'], 'Eat Lunch',
        )
        self.assertEqual(result['message'], 'Next: Eat Lunch. Do this now.')
        self.assertNotIn('Morning Prayer', result['message'])
        # No time math.
        self.assertNotRegex(
            result['message'], r'\d+\s*(min|minutes)\b',
        )

    def test_risk_surfaces_missed_morning_item(self):
        """Risk picks the foundational overdue from morning."""
        result = get_biggest_risk(self.state)
        self.assertEqual(result['mode'], 'risk')
        self.assertEqual(
            result['primary_action']['title'], 'Morning Prayer',
        )
        self.assertEqual(
            result['message'],
            'Biggest risk: Morning Prayer. Fix this next.',
        )
        # No time math, no reason text.
        self.assertNotRegex(
            result['message'], r'\d+\s*(min|minutes)\b',
        )
        self.assertNotIn('—', result['message'])  # no reason em-dash

    def test_fix_surfaces_recovery_action(self):
        """Fix picks the missed morning prayer (only overdue item)."""
        result = get_fix_priority(self.state)
        self.assertEqual(result['mode'], 'fix')
        self.assertEqual(
            result['primary_action']['title'], 'Morning Prayer',
        )
        self.assertEqual(
            result['message'], 'Fix this first: Morning Prayer.',
        )
        # No impact text, no time math.
        self.assertNotIn('unlock', result['message'])
        self.assertNotRegex(
            result['message'], r'\d+\s*(min|minutes)\b',
        )

    def test_three_modes_distinct_at_midday(self):
        """Headline guarantee: same midday state → three distinct lines.
        No blending, no overlap."""
        e = get_next_action(self.state)['message']
        r = get_biggest_risk(self.state)['message']
        f = get_fix_priority(self.state)['message']

        self.assertEqual(e, 'Next: Eat Lunch. Do this now.')
        self.assertEqual(r, 'Biggest risk: Morning Prayer. Fix this next.')
        self.assertEqual(f, 'Fix this first: Morning Prayer.')

        # Execution must NOT mention the missed morning item.
        self.assertNotIn('Morning Prayer', e)
        # Risk and Fix point to it; Execution does not.
        self.assertIn('Morning Prayer', r)
        self.assertIn('Morning Prayer', f)
