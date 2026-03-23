"""
Expected Map — Single source of truth for what is expected on a given day.

Consumes Execution Truth Engine (ETE) outputs and returns a flat map
keyed by signal-type domain key. Signal computers use this to set
the `expected` and `state` fields on SignalSnapshot.

Architecture rule: raw data → ETE → expected_map → signal computers
This module ONLY reads ETE — no duplication of expectation logic.
"""
import logging

logger = logging.getLogger(__name__)

# Maps signal_type → expected_map key.
# Used by signal computers and zero-fill to look up their expected flag.
SIGNAL_EXPECTED_KEYS = {
    'health_activity': 'workout',
    'health_biometrics': 'biometrics',
    'medication_adherence': 'medication',
    'nutrition_compliance': 'nutrition',
    'faith_practice': 'faith',
    'mental_reflection': 'journal',
    'cognitive_fitness': 'brain_training',
    'productivity_progress': 'tasks',
    'relational_engagement': 'relationships',
}


def get_expected_map(user, date=None):
    """
    Returns expected actions by domain for a given day.
    Sourced exclusively from the Execution Truth Engine.

    Returns:
        dict mapping domain key → bool. Keys match SIGNAL_EXPECTED_KEYS values.
    """
    from apps.core.execution.execution_truth_engine import get_execution_truth

    try:
        truth = get_execution_truth(user, date)
    except Exception as e:
        logger.warning(
            "Expected map: ETE call failed for user %s on %s: %s",
            user.pk, date, e, exc_info=True,
        )
        # Fail-safe: assume nothing expected (all signals → not_expected)
        return {v: False for v in set(SIGNAL_EXPECTED_KEYS.values())}

    faith = truth.get('domains', {}).get('faith', {})

    return {
        'workout': truth.get('domains', {}).get('workout', {}).get('expected', False),
        'journal': truth.get('domains', {}).get('journal', {}).get('expected', False),
        'faith': (
            faith.get('prayer_expected', False)
            or faith.get('bible_expected', False)
        ),
        'medication': (truth.get('medications', {}).get('expected', 0) or 0) > 0,
        'tasks': (truth.get('tasks', {}).get('total', 0) or 0) > 0,
        # Not tracked by ETE — default False (no routine-based expectation)
        'biometrics': False,
        'nutrition': False,
        'brain_training': False,
        'relationships': False,
    }
