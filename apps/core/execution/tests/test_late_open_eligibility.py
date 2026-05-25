"""End-to-end regression tests for the recovery redesign (Phases 1-3).

These cover the user-approved scenarios from the 2026-05-25 design
review:

    A. Delayed workout still surfaces as next_action / NORMAL mode
    B. Perfect Amino does NOT outrank a late workout (the original
       failure that triggered the redesign)
    C. Critical medication still escalates correctly
    D. Missed appointment is EXPIRED_HARD and not surfaced
    E. Streaming/non-streaming parity sanity (same state → same pick)
    F. UI + Beth alignment (execution_status propagates through)

The tests assemble the full pipeline in-memory: annotate items →
classify → execution_status → prioritize → recovery_state →
bucket_select → block_eligibility → selector.
"""

import datetime as dt

from django.test import SimpleTestCase

from apps.core.decision_engine.action_prioritizer import (
    apply_recovery_bucket_selection,
    compute_at_risk,
    compute_block_collapses,
    prioritize_execution_items,
)
from apps.core.execution.active_block import is_item_in_active_block
from apps.core.execution.execution_status import (
    EXPIRED_HARD,
    LATE_OPEN,
    annotate_execution_status,
)
from apps.core.execution.recovery_state import (
    NORMAL,
    RECOVERY,
    STABILIZE,
    compute_recovery_state,
)
from apps.core.execution.selectors import (
    get_biggest_risk,
    get_next_action,
)
from apps.core.execution.task_classifier import annotate


def _routine(item_id, title, *, scheduled_time, completed=False,
             activity_type=None, foundational=False,
             group_id='morning_routine'):
    return annotate({
        'source_type': 'routine_item',
        'source_id': item_id,
        'title': title,
        'domain': 'life',
        'is_actionable': not completed,
        'completed_today': completed,
        'is_foundational': foundational,
        'time_status': 'overdue',
        'scheduled_time': scheduled_time,
        'execution_group_type': 'routine',
        'execution_group_id': group_id,
        'parent_title': group_id.replace('_', ' ').title(),
        'importance': 'foundational' if foundational else 'important',
        'activity_type': activity_type,
    })


def _supplement(dose_id, name, *, scheduled_time, priority='optimization',
                window='afternoon', status='upcoming', foundational=False):
    return annotate({
        'source_type': 'supplement_dose',
        'source_id': dose_id,
        'title': name,
        'domain': 'health',
        'is_actionable': status != 'taken',
        'completed_today': status == 'taken',
        'is_foundational': foundational,
        'time_status': status if status in ('overdue', 'upcoming') else 'upcoming',
        'scheduled_time': scheduled_time,
        'completion_status': status,
        'execution_group_type': 'supplement_window',
        'execution_group_id': window,
        'parent_title': f'{window.title()} Supplements',
        'importance': 'foundational' if foundational else 'standard',
        'intake_type': 'supplement',
        'priority': priority,
    })


def _medication(dose_id, name, *, scheduled_time, priority='critical',
                window='lunch', status='overdue'):
    return annotate({
        'source_type': 'medication_dose',
        'source_id': dose_id,
        'title': name,
        'domain': 'health',
        'is_actionable': status != 'taken',
        'completed_today': status == 'taken',
        'is_foundational': priority == 'critical',
        'time_status': status,
        'scheduled_time': scheduled_time,
        'completion_status': status,
        'execution_group_type': 'medication_window',
        'execution_group_id': window,
        'parent_title': f'{window.title()} Medications',
        'importance': 'foundational' if priority == 'critical' else 'standard',
        'intake_type': 'medication',
        'priority': priority,
    })


def _build_state(items, now, active_block=None):
    """In-memory mirror of build_execution_state."""
    for it in items:
        annotate_execution_status(it, now)
    if active_block is None:
        active_block = {
            'name': 'mid_morning',
            'start_time': dt.time(10, 0),
            'end_time': dt.time(12, 0),
            'lead_in_end_time': dt.time(11, 45),
            'next_block_name': 'lunch',
            'next_block_start': dt.time(12, 0),
            'bounds': {},
        }
    collapse_result = compute_block_collapses(items, now, active_block)
    raw_actions = prioritize_execution_items(
        items, now, summaries={},
        suppressed_source_keys=collapse_result['suppressed_source_keys'],
    ) or []
    recovery = compute_recovery_state(
        items, now, active_block=active_block,
    )
    actions = apply_recovery_bucket_selection(raw_actions, recovery)

    def _block_eligible(a):
        if a.get('execution_status') == LATE_OPEN:
            return True
        return is_item_in_active_block(
            {
                'scheduled_time': a.get('time_display'),
                'time_status': (
                    'overdue' if a.get('urgency') == 'overdue' else None
                ),
            },
            active_block,
            now,
        )

    eligible = [a for a in actions if _block_eligible(a)]
    return {
        'now': now,
        'active_block': active_block,
        'items': items,
        'summaries': {},
        'actions': actions,
        'eligible_actions': eligible,
        'overdue_actions': [a for a in actions if a.get('urgency') == 'overdue'],
        'now_actions': [a for a in actions if a.get('urgency') == 'now'],
        'next_actions': [a for a in actions if a.get('urgency') == 'next'],
        'upcoming_actions': [a for a in actions if a.get('urgency') == 'upcoming'],
        'expired_items': [],
        'deferred_items': [],
        'collapsed_blocks': collapse_result['collapses'],
        'at_risk_actions': compute_at_risk(actions, {}, now),
        'recovery_state': recovery,
        'blocked_dependents': {},
    }


# ══════════════════════════════════════════════════════════════════════
# SCENARIO A — Delayed workout
# ══════════════════════════════════════════════════════════════════════

class ScenarioADelayedWorkout(SimpleTestCase):
    """6:15 AM workout, 11:13 AM current time."""

    def setUp(self):
        self.now = dt.time(11, 13)
        self.items = [
            _routine(
                1, 'Workout', scheduled_time='06:15',
                activity_type='workout', foundational=False,
            ),
        ]
        self.state = _build_state(self.items, self.now)

    def test_workout_status_is_late_open(self):
        statuses = {i['title']: i['execution_status'] for i in self.items}
        self.assertEqual(statuses['Workout'], LATE_OPEN)

    def test_workout_remains_eligible(self):
        titles = [a.get('title') for a in self.state['eligible_actions']]
        self.assertIn('Workout', titles)

    def test_recovery_mode_is_normal(self):
        self.assertEqual(self.state['recovery_state']['mode'], NORMAL)

    def test_next_action_is_workout(self):
        decision = get_next_action(self.state)
        self.assertEqual(decision['primary_action']['title'], 'Workout')
        self.assertEqual(decision['reason'], 'current')


# ══════════════════════════════════════════════════════════════════════
# SCENARIO B — Perfect Amino bug reproduction
# ══════════════════════════════════════════════════════════════════════

class ScenarioBPerfectAminoBug(SimpleTestCase):
    """5:45 AM morning Perfect Amino completed; 1:00 PM next dose;
    workout / shake / shower late but still intended for today.
    Current time 11:13 AM. Beth must NOT recommend Perfect Amino.
    """

    def setUp(self):
        self.now = dt.time(11, 13)
        self.items = [
            # Morning Perfect Amino dose — already taken.
            _supplement(
                10, 'Perfect Amino', scheduled_time='05:45',
                window='morning', status='taken',
            ),
            # Next Perfect Amino dose — 1:00 PM (107 min away).
            _supplement(
                11, 'Perfect Amino', scheduled_time='13:00',
                window='afternoon', status='upcoming',
            ),
            # Late-but-still-planned items the user intended for today.
            _routine(
                20, 'Workout', scheduled_time='06:15',
                activity_type='workout',
            ),
            _routine(
                21, 'Protein Shake', scheduled_time='07:30',
                activity_type='nutrition_anchor',
                group_id='breakfast_routine',
            ),
            _routine(
                22, 'Shower', scheduled_time='07:00',
                activity_type='hygiene',
                group_id='hygiene_routine',
            ),
        ]
        self.state = _build_state(self.items, self.now)

    def test_perfect_amino_not_in_next_action(self):
        decision = get_next_action(self.state)
        msg = decision.get('message', '')
        primary = (decision.get('primary_action') or {}).get('title', '')
        follow = (decision.get('follow_on') or {}).get('title', '')
        self.assertNotIn('Perfect Amino', primary)
        self.assertNotIn('Perfect Amino', follow)
        self.assertNotIn('Perfect Amino', msg)

    def test_late_open_items_outrank_future_supplement(self):
        decision = get_next_action(self.state)
        chosen = (decision.get('primary_action') or {}).get('title', '')
        self.assertIn(
            chosen, {'Workout', 'Protein Shake', 'Shower'},
            f"Expected a LATE_OPEN item to win, got {chosen!r}",
        )

    def test_recovery_mode_is_normal_not_recovery(self):
        # Two late SOFT_EXPIRED items would have flipped the old
        # contract to RECOVERY. New contract: NORMAL.
        rs = self.state['recovery_state']
        self.assertEqual(rs['mode'], NORMAL)
        self.assertEqual(rs.get('escalation_overdue_count', 0), 0)

    def test_optimization_supplement_not_in_action_pool(self):
        # The future-dose Perfect Amino is >15 min out — must be
        # filtered from actions entirely.
        titles = [a.get('title') for a in self.state['actions']]
        self.assertNotIn('Perfect Amino', titles)


# ══════════════════════════════════════════════════════════════════════
# SCENARIO C — Critical medication (safety preserved)
# ══════════════════════════════════════════════════════════════════════

class ScenarioCCriticalMedication(SimpleTestCase):
    """Critical foundational medication missed. Must still escalate."""

    def test_critical_medication_inside_grace_is_at_risk(self):
        now = dt.time(13, 30)
        items = [
            _medication(
                30, 'Insulin', scheduled_time='13:00',
                priority='critical', status='overdue',
                window='lunch',
            ),
        ]
        for it in items:
            annotate_execution_status(it, now)
        statuses = {i['title']: i['execution_status'] for i in items}
        self.assertEqual(statuses['Insulin'], 'AT_RISK')

    def test_two_foundational_meds_after_noon_trigger_recovery(self):
        # Two foundational WINDOWED items past scheduled, still inside
        # grace → AT_RISK each → escalation_overdue_count >= 2 → RECOVERY.
        now = dt.time(13, 0)
        items = [
            _medication(
                40, 'Insulin', scheduled_time='12:30',
                priority='critical', status='overdue', window='lunch',
            ),
            _medication(
                41, 'Metformin', scheduled_time='12:30',
                priority='critical', status='overdue', window='lunch',
            ),
        ]
        state = _build_state(items, now)
        self.assertEqual(state['recovery_state']['mode'], RECOVERY)


# ══════════════════════════════════════════════════════════════════════
# SCENARIO D — Hard appointment missed
# ══════════════════════════════════════════════════════════════════════

class ScenarioDMissedAppointment(SimpleTestCase):

    def test_missed_appointment_is_expired_hard(self):
        now = dt.time(11, 0)
        items = [
            _routine(
                50, 'Dentist', scheduled_time='09:00',
                activity_type='appointment', foundational=True,
            ),
        ]
        for it in items:
            annotate_execution_status(it, now)
        self.assertEqual(items[0]['execution_status'], EXPIRED_HARD)

    def test_missed_appointment_not_in_next_action(self):
        now = dt.time(11, 0)
        items = [
            _routine(
                51, 'Dentist', scheduled_time='09:00',
                activity_type='appointment', foundational=True,
            ),
            # A real candidate so the selector has something else to pick.
            _routine(
                52, 'Workout', scheduled_time='06:15',
                activity_type='workout',
            ),
        ]
        state = _build_state(items, now)
        decision = get_next_action(state)
        primary = (decision.get('primary_action') or {}).get('title', '')
        self.assertNotEqual(primary, 'Dentist')


# ══════════════════════════════════════════════════════════════════════
# SCENARIO E — Streaming/non-streaming parity
# ══════════════════════════════════════════════════════════════════════

class ScenarioEParity(SimpleTestCase):
    """Both /api/chat/ and /api/chat/stream/ go through the same
    deterministic selector contract. Parity at the state layer means
    parity at the chat layer — same input dict → same pick.
    """

    def test_same_state_yields_same_next_action(self):
        now = dt.time(11, 13)
        items = [
            _routine(
                60, 'Workout', scheduled_time='06:15',
                activity_type='workout',
            ),
        ]
        state_a = _build_state(items, now)
        state_b = _build_state(list(items), now)
        decision_a = get_next_action(state_a)
        decision_b = get_next_action(state_b)
        self.assertEqual(decision_a['message'], decision_b['message'])
        self.assertEqual(
            (decision_a.get('primary_action') or {}).get('title'),
            (decision_b.get('primary_action') or {}).get('title'),
        )


# ══════════════════════════════════════════════════════════════════════
# SCENARIO F — UI + Beth alignment
# ══════════════════════════════════════════════════════════════════════

class ScenarioFUIAlignment(SimpleTestCase):
    """The execution_status field must propagate from raw items
    through the prioritizer to every action so the UI and Beth read
    from the same source. If they disagree, that's the alignment bug
    from the Visual Truth Contract."""

    def test_execution_status_propagates_to_action(self):
        now = dt.time(11, 13)
        items = [
            _routine(
                70, 'Workout', scheduled_time='06:15',
                activity_type='workout',
            ),
        ]
        state = _build_state(items, now)
        workout_actions = [
            a for a in state['actions'] if a.get('title') == 'Workout'
        ]
        self.assertTrue(workout_actions)
        self.assertEqual(
            workout_actions[0].get('execution_status'), LATE_OPEN,
            "Workout action must carry the same execution_status as the "
            "underlying item — otherwise Beth and the UI can diverge.",
        )

    def test_late_open_workout_present_in_eligible_actions(self):
        now = dt.time(11, 13)
        items = [
            _routine(
                71, 'Workout', scheduled_time='06:15',
                activity_type='workout',
            ),
        ]
        state = _build_state(items, now)
        eligible_titles = [
            a.get('title') for a in state['eligible_actions']
        ]
        self.assertIn(
            'Workout', eligible_titles,
            "LATE_OPEN workout must survive the block-eligibility "
            "gate — this is the Perfect Amino root cause guard.",
        )
