"""
Execution Truth Engine — THE single source of completion truth.

ARCHITECTURAL RULE:
  Every system that needs to know "is X completed today?" MUST call
  get_execution_truth(user). No exceptions.

  This engine answers TWO questions:
    1. "What is expected of the user today?" (from routines + config)
    2. "What has the user actually completed today?" (from execution logs)

  It uses ONLY raw authoritative data:
    - RoutineLog (routine items)
    - Task (tasks)
    - WorkoutSession (workouts)
    - JournalEntry (journal)
    - UserReadingProgress (Bible reading plans)
    - MedicineLog (medications)

  It does NOT use:
    - Cached state / SAE snapshots
    - Domain service summaries
    - Signal engines / streaks / trends
    - NLP or inference of any kind

CROSS-DOMAIN BRIDGES:
  Routine items can satisfy other domains. For example:
    - A routine item named "Prayer Time" → satisfies faith.prayer
    - A routine item named "Bible Reading" → satisfies faith.bible_reading
  These bridges live HERE and ONLY here.

EXPECTATION RULES:
  A domain is "expected" today if:
    - It has a routine item scheduled for today, OR
    - It has an active plan/config (e.g., Bible reading plan)
  If a domain is NOT expected, CoS must not report it as pending.

CONSUMERS (all must use this engine):
  - CoS (cos_fact_statements.py)
  - today_state.py
  - today_execution.py (domain summaries)
  - DailyProgressService (dashboard)
  - Any future completion check
"""

import logging
from datetime import date
from typing import Dict, Optional

from apps.core.utils import get_user_today

logger = logging.getLogger(__name__)


# ── Cross-Domain Bridge Configuration ──────────────────────────
# Routine item names (lowercase) that satisfy faith domain.
# This is the ONLY place this mapping exists in the entire system.
FAITH_PRAYER_NAMES = frozenset({
    'prayer time', 'prayer', 'morning prayer', 'evening prayer',
})
FAITH_BIBLE_NAMES = frozenset({
    'bible reading', 'bible study', 'scripture reading', 'devotional',
})

# Routine item names that map to workout domain
WORKOUT_NAMES = frozenset({
    'workout', 'exercise', 'gym', 'training', 'run', 'running',
    'morning workout', 'evening workout', 'cardio', 'strength training',
    'yoga', 'stretching', 'walk', 'walking', 'hike', 'hiking',
    'swim', 'swimming', 'cycling', 'bike', 'fitness',
})

# Routine item names that map to journal domain
JOURNAL_NAMES = frozenset({
    'journal', 'journaling', 'journal entry', 'daily journal',
    'morning journal', 'evening journal', 'reflection', 'daily reflection',
    'gratitude journal', 'gratitude',
})


def get_execution_truth(user, target_date: Optional[date] = None) -> Dict:
    """
    THE single source of truth for what the user has completed today
    AND what is expected today.

    Returns:
        {
            'date': '2026-03-22',
            'domains': {
                'faith': {
                    'expected': bool,
                    'prayer_expected': bool,
                    'bible_expected': bool,
                    'prayer_completed': bool,
                    'bible_reading_completed': bool,
                    'prayer_source': str,       # 'task', 'routine', or None
                    'bible_source': str,         # 'reading_plan', 'routine', or None
                },
                'workout': {'expected': bool, 'completed': bool},
                'journal': {'expected': bool, 'completed': bool},
            },
            'routines': {
                'total': int,
                'completed': int,
                'fully_complete': bool,
                'items': {routine_name: {total, completed, fully_complete}},
                '_raw_items': dict,  # for internal use by consumers
            },
            'tasks': {
                'total': int,
                'completed': int,
            },
            'medications': {
                'taken': int,
                'expected': int,
                'all_taken': bool,
            },
        }
    """
    if target_date is None:
        target_date = get_user_today(user)

    # Build routines first — we need them for expectation detection
    routines = _check_routines(user, target_date)

    # Derive domain expectations from today's routine items
    expectations = _derive_expectations(user, target_date, routines)

    truth = {
        'date': target_date.isoformat(),
        'domains': {
            'faith': _check_faith(user, target_date, expectations),
            'workout': _check_workout(user, target_date, expectations),
            'journal': _check_journal(user, target_date, expectations),
        },
        'routines': routines,
        'tasks': _check_tasks(user, target_date),
        'medications': _check_medications(user, target_date),
    }

    # ── Cross-Domain Bridge: Routine → Faith ──
    # This is the ONLY place this bridge exists.
    _apply_routine_faith_bridge(truth)

    logger.info(
        "[EXECUTION TRUTH] user=%s date=%s "
        "prayer=%s(exp=%s,src=%s) bible=%s(exp=%s,src=%s) "
        "workout=%s(exp=%s) journal=%s(exp=%s) "
        "routines=%d/%d tasks=%d/%d meds=%d/%d",
        user.id, target_date,
        truth['domains']['faith']['prayer_completed'],
        truth['domains']['faith']['prayer_expected'],
        truth['domains']['faith'].get('prayer_source'),
        truth['domains']['faith']['bible_reading_completed'],
        truth['domains']['faith']['bible_expected'],
        truth['domains']['faith'].get('bible_source'),
        truth['domains']['workout']['completed'],
        truth['domains']['workout']['expected'],
        truth['domains']['journal']['completed'],
        truth['domains']['journal']['expected'],
        truth['routines']['completed'], truth['routines']['total'],
        truth['tasks']['completed'], truth['tasks']['total'],
        truth['medications']['taken'], truth['medications']['expected'],
    )

    return truth


# ── Expectation Derivation ────────────────────────────────────────


def _derive_expectations(user, target_date: date, routines: Dict) -> Dict:
    """
    Determine what domains are expected today based on:
    1. Today's routine items (name-based mapping)
    2. Active configurations (e.g., Bible reading plans)

    Returns dict with expected flags for each domain.
    """
    expectations = {
        'prayer_expected': False,
        'bible_expected': False,
        'workout_expected': False,
        'journal_expected': False,
    }

    # Scan today's routine items (RoutineItem model) for domain-mapped names
    raw_items = routines.get('_raw_items', {})
    for _window, items in raw_items.items():
        for item in items:
            item_name = (item.get('item_name') or '').lower().strip()
            if item_name in FAITH_PRAYER_NAMES:
                expectations['prayer_expected'] = True
            if item_name in FAITH_BIBLE_NAMES:
                expectations['bible_expected'] = True
            if item_name in WORKOUT_NAMES:
                expectations['workout_expected'] = True
            if item_name in JOURNAL_NAMES:
                expectations['journal_expected'] = True

    # Also scan routine Tasks (is_routine=True) — these are a separate
    # data source from RoutineItems and may contain workout/journal/etc.
    # expectations that RoutineItems don't capture.  Use keyword-in-title
    # matching (not exact match) because Task titles can be compound
    # like "Workout and Drink Protein Shake".
    try:
        from apps.life.models import Task
        routine_titles = list(Task.objects.filter(
            user=user, is_routine=True, due_date=target_date,
        ).exclude(
            completion_status='skipped',
        ).values_list('title', flat=True))
        for title in routine_titles:
            title_lower = title.lower()
            if any(kw in title_lower for kw in WORKOUT_NAMES):
                expectations['workout_expected'] = True
            if any(kw in title_lower for kw in JOURNAL_NAMES):
                expectations['journal_expected'] = True
            if any(kw in title_lower for kw in FAITH_PRAYER_NAMES):
                expectations['prayer_expected'] = True
            if any(kw in title_lower for kw in FAITH_BIBLE_NAMES):
                expectations['bible_expected'] = True
    except ImportError:
        pass
    except Exception:
        logger.warning(
            "execution_truth: routine task expectation scan failed",
            exc_info=True,
        )

    # Bible reading plan = bible expected (regardless of routine)
    try:
        from apps.faith.models import UserReadingPlan
        if UserReadingPlan.objects.filter(
            user=user, plan_status='active',
        ).exclude(status='deleted').exists():
            expectations['bible_expected'] = True
    except ImportError:
        pass
    except Exception:
        logger.warning(
            "execution_truth: bible plan check failed", exc_info=True,
        )

    # Faith tasks due today = prayer expected
    try:
        from apps.life.models import Task
        if Task.objects.filter(
            user=user,
            module='faith',
            due_date=target_date,
            is_routine=False,
        ).exclude(status='deleted').exclude(
            completion_status='completed',
        ).exists():
            expectations['prayer_expected'] = True
    except ImportError:
        pass
    except Exception:
        logger.warning(
            "execution_truth: faith task expectation check failed",
            exc_info=True,
        )

    logger.info(
        "[EXECUTION TRUTH EXPECTATIONS] user=%s date=%s "
        "prayer_exp=%s bible_exp=%s workout_exp=%s journal_exp=%s",
        user.id, target_date,
        expectations['prayer_expected'],
        expectations['bible_expected'],
        expectations['workout_expected'],
        expectations['journal_expected'],
    )

    return expectations


# ── Domain Checkers (raw DB queries only) ──────────────────────


def _check_faith(user, target_date: date, expectations: Dict) -> Dict:
    """
    Check faith completion from EXPLICIT records only.

    Sources:
      - UserReadingProgress (Bible reading plan completion)
      - Task with module='faith' (faith-linked tasks)

    NOTE: Routine bridges are applied AFTER this, in _apply_routine_faith_bridge().
    """
    result = {
        'expected': (
            expectations.get('prayer_expected', False)
            or expectations.get('bible_expected', False)
        ),
        'prayer_expected': expectations.get('prayer_expected', False),
        'bible_expected': expectations.get('bible_expected', False),
        'prayer_completed': False,
        'bible_reading_completed': False,
        'prayer_source': None,
        'bible_source': None,
    }

    # Bible reading plan completion
    try:
        from apps.faith.models import UserReadingPlan, UserReadingProgress
        active_plans = UserReadingPlan.objects.filter(
            user=user, plan_status='active',
        ).exclude(status='deleted')
        if active_plans.exists():
            if UserReadingProgress.objects.filter(
                user_plan__in=active_plans,
                is_completed=True,
                completed_at__date=target_date,
            ).exists():
                result['bible_reading_completed'] = True
                result['bible_source'] = 'reading_plan'
    except ImportError:
        pass
    except Exception:
        logger.warning(
            "execution_truth: bible reading check failed", exc_info=True,
        )

    # Faith-linked task completion (prayer)
    try:
        from apps.life.models import Task
        if Task.objects.filter(
            user=user,
            module='faith',
            completion_status='completed',
            completed_at__date=target_date,
        ).exists():
            result['prayer_completed'] = True
            result['prayer_source'] = 'task'
    except ImportError:
        pass
    except Exception:
        logger.warning(
            "execution_truth: faith task check failed", exc_info=True,
        )

    return result


def _check_workout(user, target_date: date, expectations: Dict) -> Dict:
    """Check workout completion from WorkoutSession."""
    result = {
        'expected': expectations.get('workout_expected', False),
        'completed': False,
    }
    try:
        from apps.health.services.workout_queries import WorkoutQueries
        result['completed'] = WorkoutQueries.is_completed_on(user, target_date)
    except ImportError:
        pass
    except Exception:
        logger.warning(
            "execution_truth: workout check failed", exc_info=True,
        )
    # If completed but not expected, it's a bonus — still mark completed
    return result


def _check_journal(user, target_date: date, expectations: Dict) -> Dict:
    """Check journal completion from JournalEntry."""
    result = {
        'expected': expectations.get('journal_expected', False),
        'completed': False,
    }
    try:
        from apps.journal.models import JournalEntry
        result['completed'] = JournalEntry.objects.filter(
            user=user, entry_date=target_date,
        ).exists()
    except ImportError:
        pass
    except Exception:
        logger.warning(
            "execution_truth: journal check failed", exc_info=True,
        )
    return result


def _check_routines(user, target_date: Optional[date] = None) -> Dict:
    """
    Check routine completion from RoutineLog for a specific date.

    When target_date is today, delegates to get_todays_routine_items() for
    full time-window enrichment. For historical dates, queries RoutineLog
    directly so the faith bridge works correctly across the 7-day window.
    """
    result = {
        'total': 0,
        'completed': 0,
        'fully_complete': False,
        'items': {},
        '_raw_items': {},
    }
    try:
        if target_date is None:
            target_date = get_user_today(user)

        user_today = get_user_today(user)

        if target_date == user_today:
            # Today: use the rich routine service for full time-window data
            from apps.life.services._routine_internal import get_todays_routine_items
            routine_data = get_todays_routine_items(user)
            routine_completion = routine_data.get('routine_completion', {})

            total = 0
            completed = 0
            for routine_id, completion in routine_completion.items():
                r_total = completion.get('total_count', 0)
                r_done = completion.get('completed_count', 0)
                r_name = completion.get('name', str(routine_id))
                total += r_total
                completed += r_done
                result['items'][r_name] = {
                    'total': r_total,
                    'completed': r_done,
                    'fully_complete': r_done >= r_total and r_total > 0,
                }

            result['total'] = total
            result['completed'] = completed
            result['fully_complete'] = completed >= total and total > 0
            result['_raw_items'] = routine_data.get('items_by_window', {})
        else:
            # Historical date: query RoutineLog directly for that date.
            # This ensures the faith bridge can detect completed Prayer Time /
            # Bible Reading items on any date, not just today.
            from apps.life.models import Routine, RoutineLog, RoutineSchedule

            day_of_week = target_date.weekday()
            active_routines = Routine.objects.filter(
                user=user, is_active=True,
            ).exclude(status='deleted')

            # Get all schedule items that apply to this day of the week
            schedules = RoutineSchedule.objects.filter(
                routine__in=active_routines,
            ).select_related('routine')

            applicable_schedules = []
            for sched in schedules:
                if sched.days_of_week:
                    try:
                        days = [int(d) for d in sched.days_of_week.split(',') if d.strip()]
                        if day_of_week in days:
                            applicable_schedules.append(sched)
                    except (ValueError, AttributeError):
                        applicable_schedules.append(sched)
                else:
                    # No days restriction = every day
                    applicable_schedules.append(sched)

            schedule_ids = [s.id for s in applicable_schedules]

            # Get logs for that date
            logs = RoutineLog.objects.filter(
                schedule_id__in=schedule_ids,
                scheduled_date=target_date,
            ).select_related('schedule', 'routine_at_time')

            log_by_schedule = {log.schedule_id: log for log in logs}

            total = len(applicable_schedules)
            completed = sum(
                1 for log in logs
                if log.log_status in (
                    RoutineLog.STATUS_COMPLETED,
                    RoutineLog.STATUS_COMPLETED_LATE,
                )
            )

            # Build _raw_items in the same format the bridge expects:
            # { window_name: [{ item_name, is_completed, ... }, ...] }
            raw_items_list = []
            routine_totals = {}
            for sched in applicable_schedules:
                log = log_by_schedule.get(sched.id)
                is_done = (
                    log is not None
                    and log.log_status in (
                        RoutineLog.STATUS_COMPLETED,
                        RoutineLog.STATUS_COMPLETED_LATE,
                    )
                )
                raw_items_list.append({
                    'item_name': sched.name,
                    'is_completed': is_done,
                    'schedule_id': sched.id,
                    'obligation_type': sched.obligation_type,
                })

                # Use write-time anchored routine name for historical accuracy.
                # Falls back to current schedule.routine for pre-migration logs.
                if log and log.routine_at_time_id:
                    r_name = log.routine_at_time.name
                else:
                    r_name = sched.routine.name
                if r_name not in routine_totals:
                    routine_totals[r_name] = {'total': 0, 'completed': 0}
                routine_totals[r_name]['total'] += 1
                if is_done:
                    routine_totals[r_name]['completed'] += 1

            for r_name, counts in routine_totals.items():
                result['items'][r_name] = {
                    'total': counts['total'],
                    'completed': counts['completed'],
                    'fully_complete': counts['completed'] >= counts['total'] and counts['total'] > 0,
                }

            result['total'] = total
            result['completed'] = completed
            result['fully_complete'] = completed >= total and total > 0
            # Place all items under a single 'historical' window key
            result['_raw_items'] = {'historical': raw_items_list}

    except ImportError:
        pass
    except Exception:
        logger.warning(
            "execution_truth: routine check failed", exc_info=True,
        )
    return result


def _check_tasks(user, target_date: date) -> Dict:
    """Check task completion from Task model."""
    result = {
        'total': 0,
        'completed': 0,
        'completed_today_all': 0,
    }
    try:
        from apps.life.models import Task

        # Tasks due today (non-routine)
        today_tasks = Task.objects.filter(
            user=user,
            is_routine=False,
            due_date=target_date,
        ).exclude(status='deleted')
        result['total'] = today_tasks.count()
        result['completed'] = today_tasks.filter(
            completion_status='completed',
        ).count()

        # All tasks completed today (for CoS "tasks completed today" count)
        result['completed_today_all'] = Task.objects.filter(
            user=user,
            completion_status='completed',
            completed_at__date=target_date,
        ).count()
    except ImportError:
        pass
    except Exception:
        logger.warning(
            "execution_truth: task check failed", exc_info=True,
        )
    return result


def _check_medications(user, target_date: date) -> Dict:
    """Check medication adherence from medicine_utils."""
    result = {
        'taken': 0,
        'expected': 0,
        'skipped': 0,
        'all_taken': False,
    }
    try:
        from apps.health.medicine_utils import calculate_medicine_adherence
        adherence = calculate_medicine_adherence(user, target_date, target_date)
        result['expected'] = adherence.get('expected_doses', 0)
        result['taken'] = adherence.get('taken_doses', 0)
        result['skipped'] = adherence.get('skipped_doses', 0)
        result['all_taken'] = (
            result['taken'] >= result['expected']
            if result['expected'] > 0
            else True  # No meds scheduled = satisfied
        )
    except ImportError:
        pass
    except Exception:
        logger.warning(
            "execution_truth: medication check failed", exc_info=True,
        )
    return result


# ── Cross-Domain Bridge ─────────────────────────────────────────


def _apply_routine_faith_bridge(truth: Dict) -> None:
    """
    Bridge routine item completion to faith domain.

    When a routine item named "Prayer Time", "Bible Reading", etc. is
    completed, propagate that to the faith domain. This is the ONLY
    place this bridge exists in the entire system.

    Only upgrades False → True, never downgrades True → False.
    """
    faith = truth['domains']['faith']
    raw_items = truth['routines'].get('_raw_items', {})
    if not raw_items:
        return

    for _window, items in raw_items.items():
        for item in items:
            if not item.get('is_completed'):
                continue
            item_name = (item.get('item_name') or '').lower().strip()
            if item_name in FAITH_PRAYER_NAMES and not faith['prayer_completed']:
                faith['prayer_completed'] = True
                faith['prayer_source'] = 'routine'
                logger.info(
                    "[EXECUTION TRUTH BRIDGE] routine '%s' → "
                    "prayer_completed=True",
                    item.get('item_name'),
                )
            elif (
                item_name in FAITH_BIBLE_NAMES
                and not faith['bible_reading_completed']
            ):
                faith['bible_reading_completed'] = True
                faith['bible_source'] = 'routine'
                logger.info(
                    "[EXECUTION TRUTH BRIDGE] routine '%s' → "
                    "bible_reading_completed=True",
                    item.get('item_name'),
                )
