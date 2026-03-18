"""
Behavior Score Engine — composite score across behavioral domains.

Pure function. No DB writes. Reads from domain adherence output functions.

Domains:
  - medication (weight 1.5)
  - workout (weight 1.0)
  - routine (weight 1.0)

Only includes domains where expected > 0.
"""

import logging
from datetime import timedelta

logger = logging.getLogger(__name__)

# Domain weights for composite scoring
DOMAIN_WEIGHTS = {
    'medication': 1.5,
    'workout': 1.0,
    'routine': 1.0,
}


def compute_behavior_score(user, start_date, end_date):
    """
    Compute composite behavior score across all behavioral domains.

    Pure function — no DB writes.

    Args:
        user: User instance
        start_date: date
        end_date: date

    Returns:
        dict: {
            score: float (0-100) or None,
            domains: [behavior_output, ...],
            domains_missing: [str, ...],
            strongest_domain: str or None,
            weakest_domain: str or None,
        }
    """
    domain_outputs = []
    domains_missing = []

    # ── Medication ──
    try:
        from apps.core.behavior.domain_medication import calculate_medicine_behavior_output
        med_output = calculate_medicine_behavior_output(user, start_date, end_date)
        if med_output and med_output['expected'] > 0:
            domain_outputs.append(med_output)
        else:
            domains_missing.append('medication')
    except Exception as e:
        logger.warning("Behavior score: medication domain failed: %s", e, exc_info=True)
        domains_missing.append('medication')

    # ── Workout ──
    try:
        from apps.core.behavior.domain_workout import calculate_workout_behavior_output
        wk_output = calculate_workout_behavior_output(user, start_date, end_date)
        if wk_output and wk_output['expected'] > 0:
            domain_outputs.append(wk_output)
        else:
            domains_missing.append('workout')
    except Exception as e:
        logger.warning("Behavior score: workout domain failed: %s", e, exc_info=True)
        domains_missing.append('workout')

    # ── Routine ──
    try:
        from apps.core.behavior.domain_routine import calculate_routine_behavior_output
        rt_output = calculate_routine_behavior_output(user, start_date, end_date)
        if rt_output and rt_output['expected'] > 0:
            domain_outputs.append(rt_output)
        else:
            domains_missing.append('routine')
    except Exception as e:
        logger.warning("Behavior score: routine domain failed: %s", e, exc_info=True)
        domains_missing.append('routine')

    # ── Composite score ──
    if not domain_outputs:
        return {
            'score': None,
            'domains': [],
            'domains_missing': domains_missing,
            'strongest_domain': None,
            'weakest_domain': None,
        }

    weighted_sum = 0.0
    weight_total = 0.0
    strongest = None
    weakest = None
    best_adherence = -1
    worst_adherence = 101

    for output in domain_outputs:
        domain = output['domain']
        adherence = output.get('adherence')
        if adherence is None:
            continue
        weight = DOMAIN_WEIGHTS.get(domain, 1.0)
        weighted_sum += adherence * weight
        weight_total += weight

        if adherence > best_adherence:
            best_adherence = adherence
            strongest = domain
        if adherence < worst_adherence:
            worst_adherence = adherence
            weakest = domain

    if weight_total > 0:
        score = round(weighted_sum / weight_total, 1)
    else:
        score = None

    return {
        'score': score,
        'domains': domain_outputs,
        'domains_missing': domains_missing,
        'strongest_domain': strongest,
        'weakest_domain': weakest,
    }


def compute_behavior_score_7d(user):
    """Convenience: 7-day rolling behavior score."""
    from apps.core.utils import get_user_today
    today = get_user_today(user)
    start = today - timedelta(days=7)
    return compute_behavior_score(user, start, today)
