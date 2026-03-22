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

    # ── Fail-safe logging ──
    for output in domain_outputs:
        d_name = output['domain']
        d_expected = output.get('expected', 0)
        d_completed = output.get('completed', 0)
        d_late = output.get('late', 0)
        d_missed = output.get('missed', 0)

        # Warn if schedule exists but zero logs ever created
        if d_expected > 0 and d_completed == 0 and d_late == 0 and output.get('skipped', 0) == 0:
            logger.warning(
                "BEHAVIOR_NO_LOGS domain=%s user=%s expected=%d — "
                "schedule has obligations but no compliance logs exist",
                d_name, user.id, d_expected,
            )

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


def compute_adherence_summary(user):
    """
    Compute a complete 7-day adherence summary with delta and gap analysis.

    Returns:
        dict: {
            'score': float (0-100) or None,
            'delta': int — change from yesterday's 7-day score,
            'delta_direction': str — 'up', 'down', or 'flat',
            'top_gap': str or None — human-readable top limiter,
            'domains': list — per-domain behavior outputs,
            'strongest': str or None,
            'weakest': str or None,
            'total_expected': int,
            'total_completed': int,
        }
    """
    from apps.core.utils import get_user_today
    today = get_user_today(user)

    # Today's 7-day score
    current = compute_behavior_score(user, today - timedelta(days=7), today)

    # Yesterday's 7-day score (for delta)
    yesterday = today - timedelta(days=1)
    previous = compute_behavior_score(user, yesterday - timedelta(days=7), yesterday)

    current_score = current.get('score')
    previous_score = previous.get('score')

    # Delta
    if current_score is not None and previous_score is not None:
        delta = round(current_score - previous_score)
        if delta > 0:
            delta_direction = 'up'
        elif delta < 0:
            delta_direction = 'down'
        else:
            delta_direction = 'flat'
    else:
        delta = 0
        delta_direction = 'flat'

    # Gap analysis + per-domain enrichment
    top_gap = None
    max_missed = 0
    total_expected = 0
    total_completed = 0

    _domain_labels = {
        'medication': 'medication doses',
        'workout': 'workouts',
        'routine': 'routine items',
    }

    # Build previous domain lookup for per-domain delta
    _prev_domains = {}
    for pd in previous.get('domains', []):
        _prev_domains[pd['domain']] = pd.get('adherence')

    # Per-domain scores for template access
    domain_scores = {}

    for d in current.get('domains', []):
        domain_name = d['domain']
        expected = d.get('expected', 0)
        completed = d.get('completed', 0)
        late = d.get('late', 0)
        missed = d.get('missed', 0)
        adherence = d.get('adherence')
        total_expected += expected
        total_completed += completed + late

        if missed > max_missed:
            max_missed = missed
            domain_label = _domain_labels.get(domain_name, domain_name)
            top_gap = f"Missed {missed} {domain_label} this week"

        # Per-domain delta
        prev_adh = _prev_domains.get(domain_name)
        if adherence is not None and prev_adh is not None:
            d_delta = round(adherence - prev_adh)
        else:
            d_delta = 0

        # Per-domain gap
        d_gap = None
        if missed > 0:
            d_label = _domain_labels.get(domain_name, domain_name)
            d_gap = f"Missed {missed} {d_label}"

        domain_scores[domain_name] = {
            'score': round(adherence) if adherence is not None else None,
            'delta': d_delta,
            'delta_direction': 'up' if d_delta > 0 else ('down' if d_delta < 0 else 'flat'),
            'top_gap': d_gap,
            'expected': expected,
            'completed': completed + late,
            'missed': missed,
            'label': _domain_labels.get(domain_name, domain_name).replace(' ', ' ').title(),
        }

    # ── Fastest path: single highest-impact action ──
    fastest_path = None
    if total_expected > 0 and current_score is not None:
        fastest_path = _compute_fastest_path(
            user, today, current_score, total_expected, total_completed,
        )

    return {
        'score': current_score,
        'delta': delta,
        'delta_direction': delta_direction,
        'top_gap': top_gap,
        'domain_scores': domain_scores,
        'domains': current.get('domains', []),
        'strongest': current.get('strongest_domain'),
        'weakest': current.get('weakest_domain'),
        'total_expected': total_expected,
        'total_completed': total_completed,
        'fastest_path': fastest_path,
    }


def _compute_fastest_path(user, today, current_score, total_expected, total_completed):
    """
    Find the single action that increases adherence score the most.

    Reads today's pending execution items and calculates per-item impact
    on the 7-day adherence score. For routine blocks (multiple items in
    one routine), groups them as a single action with combined impact.

    Returns:
        dict: {
            'action': str — action title,
            'impact': int — percentage points gained,
            'projected_score': int — new score after completion,
            'source': str — 'routine', 'task', 'medicine', etc.
        }
        or None if no actionable items
    """
    try:
        from apps.core.execution.today_execution import build_today_execution
    except ImportError:
        return None

    exec_data = build_today_execution(user)
    items = exec_data.get('items', [])

    if not items or total_expected == 0:
        return None

    # Score per completed action = (1.0 weight / total_expected) * 100
    per_item_impact = 100.0 / total_expected

    # Group routine items by parent routine for block scoring
    candidates = []
    routine_groups = {}

    for item in items:
        if not item.get('is_actionable', False):
            continue
        if item.get('completed_today'):
            continue

        source_type = item.get('source_type', '')

        if source_type == 'routine_item':
            parent = item.get('parent_title') or item.get('title', '')
            if parent not in routine_groups:
                routine_groups[parent] = {
                    'title': parent,
                    'count': 0,
                    'source': 'routine',
                }
            routine_groups[parent]['count'] += 1
        elif source_type == 'medication_dose':
            parent = item.get('parent_title') or 'Medications'
            if parent not in routine_groups:
                routine_groups[parent] = {
                    'title': parent,
                    'count': 0,
                    'source': 'medicine',
                }
            routine_groups[parent]['count'] += 1
        else:
            # Individual task
            candidates.append({
                'title': item.get('title', 'Task'),
                'count': 1,
                'source': source_type or 'task',
            })

    # Add grouped routine/medicine candidates
    candidates.extend(routine_groups.values())

    if not candidates:
        return None

    # Score each candidate
    best = None
    best_impact = 0

    for c in candidates:
        impact = round(c['count'] * per_item_impact)
        if impact > best_impact:
            best_impact = impact
            best = c

    if not best or best_impact <= 0:
        return None

    projected = min(100, round(current_score + best_impact))

    return {
        'action': best['title'],
        'impact': best_impact,
        'projected_score': projected,
        'source': best['source'],
    }


def get_missed_items_detail(user):
    """
    Get per-item missed details for the last 7 days, grouped by parent.

    Returns:
        list[dict]: [
            {
                'group': str — routine name or domain label,
                'items': [
                    {'name': str, 'missed': int, 'total': int}
                ],
                'total_missed': int,
            },
            ...
        ]
    Sorted by total_missed descending (worst first).
    """
    from apps.core.utils import get_user_today
    from datetime import timedelta as _td

    today = get_user_today(user)
    start = today - _td(days=7)

    groups = {}

    # ── Routine items ──
    try:
        from apps.life.models import Routine, RoutineSchedule, RoutineLog

        active_routines = Routine.objects.filter(
            user=user, is_active=True, status='active',
        ).prefetch_related('items')

        for routine in active_routines:
            for schedule in routine.items.filter(is_active=True):
                # Count expected days in range
                expected = 0
                day = start
                while day <= today:
                    if schedule.specific_date:
                        if schedule.specific_date == day:
                            expected += 1
                    elif schedule.applies_to_day(day.weekday()):
                        expected += 1
                    day += _td(days=1)

                if expected == 0:
                    continue

                # Count completions
                completed = RoutineLog.objects.filter(
                    schedule=schedule,
                    scheduled_date__gte=start,
                    scheduled_date__lte=today,
                    log_status__in=('completed', 'completed_late'),
                ).count()

                missed = max(0, expected - completed)
                if missed > 0:
                    group_name = routine.name
                    if group_name not in groups:
                        groups[group_name] = {
                            'group': group_name,
                            'items': [],
                            'total_missed': 0,
                        }
                    groups[group_name]['items'].append({
                        'name': schedule.name,
                        'missed': missed,
                        'total': expected,
                    })
                    groups[group_name]['total_missed'] += missed
    except Exception:
        logger.debug("Missed items: routine query failed", exc_info=True)

    # ── Workouts ──
    try:
        from apps.health.models import WorkoutSession
        from apps.core.ai_state.state_engine import get_module_state

        health_state = get_module_state(user, 'health') or {}
        workout_days = health_state.get('workout_days_per_week', 0)
        if workout_days > 0:
            actual = WorkoutSession.objects.filter(
                user=user,
                date__gte=start,
                date__lte=today,
            ).exclude(status='deleted').count()
            missed = max(0, workout_days - actual)
            if missed > 0:
                groups['Workouts'] = {
                    'group': 'Workouts',
                    'items': [{'name': 'Workout', 'missed': missed, 'total': workout_days}],
                    'total_missed': missed,
                }
    except Exception:
        logger.debug("Missed items: workout query failed", exc_info=True)

    # Sort by total_missed descending
    result = sorted(groups.values(), key=lambda g: g['total_missed'], reverse=True)
    return result


def get_missed_items_raw(user):
    """
    Get every individual missed/late/skipped occurrence for last 7 days.

    Returns a list of dicts, most recent first, each with:
        - date: date
        - routine_name: str
        - item_name: str
        - scheduled_time: str or None
        - status: str ('missed', 'completed_late', 'skipped')

    This is the full raw audit trail — no aggregation.
    """
    from apps.core.utils import get_user_today
    from datetime import timedelta as _td

    today = get_user_today(user)
    start = today - _td(days=7)

    raw_items = []

    try:
        from apps.life.models import Routine, RoutineLog

        active_routines = Routine.objects.filter(
            user=user, is_active=True, status='active',
        ).prefetch_related('items')

        for routine in active_routines:
            for schedule in routine.items.filter(is_active=True):
                # Find all expected dates
                expected_dates = set()
                day = start
                while day <= today:
                    if schedule.specific_date:
                        if schedule.specific_date == day:
                            expected_dates.add(day)
                    elif schedule.applies_to_day(day.weekday()):
                        expected_dates.add(day)
                    day += _td(days=1)

                if not expected_dates:
                    continue

                # Get all logs for this schedule in range
                logs = {
                    log.scheduled_date: log
                    for log in RoutineLog.objects.filter(
                        schedule=schedule,
                        scheduled_date__gte=start,
                        scheduled_date__lte=today,
                    )
                }

                sched_time = (
                    schedule.scheduled_time.strftime('%H:%M')
                    if schedule.scheduled_time else None
                )

                for d in sorted(expected_dates, reverse=True):
                    log = logs.get(d)
                    if log is None:
                        raw_items.append({
                            'date': d,
                            'routine_name': routine.name,
                            'item_name': schedule.name,
                            'scheduled_time': sched_time,
                            'status': 'missed',
                        })
                    elif log.log_status == 'completed_late':
                        raw_items.append({
                            'date': d,
                            'routine_name': routine.name,
                            'item_name': schedule.name,
                            'scheduled_time': sched_time,
                            'status': 'completed_late',
                        })
                    elif log.log_status == 'skipped':
                        raw_items.append({
                            'date': d,
                            'routine_name': routine.name,
                            'item_name': schedule.name,
                            'scheduled_time': sched_time,
                            'status': 'skipped',
                        })
                    # completed → not a miss, skip
    except Exception:
        logger.debug("Missed items raw: query failed", exc_info=True)

    # Sort by date descending (most recent first)
    raw_items.sort(key=lambda x: x['date'], reverse=True)
    return raw_items
