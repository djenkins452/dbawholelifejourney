"""
Dependency Gating — Single source of truth for "is this task blocked?"

Canonical rule:
    A Task is BLOCKED when:
      1. depends_on_key is set, AND
      2. hide_until_ready is True, AND
      3. the prerequisite is not yet complete.

Blocked tasks must not appear in:
  - Today Engine (apps/core/today/today_engine.py)
  - Execution contract (apps/core/execution/today_execution.py)
  - CoS facts / next_action / locked fact statements

Both the Today Engine and the execution contract call is_task_blocked(task, truth)
at collection time. No other module applies gating. No logic duplication.

Prerequisite resolution is routing-aware:
  - "task:{pk}"           → Task.completion_status == 'completed'
  - "routine:{schedule_id}" → execution truth 'routines._raw_items' is_completed
  - "domain:{name}"       → execution truth 'domains[name].completed'

Dangling / unresolvable references fail OPEN (not blocked). If the prereq
cannot be located, the dependency is treated as vacuously satisfied rather
than permanently gating the dependent item.
"""

import logging

logger = logging.getLogger(__name__)


def is_task_blocked(task, truth) -> bool:
    """Return True if this Task should be hidden due to an unmet dependency.

    Args:
        task: Task model instance (must have depends_on_key, hide_until_ready).
        truth: dict from get_execution_truth(user) — used to resolve routine
               and domain prerequisites.

    Returns:
        True if the task is blocked and should be excluded from the
        actionable list. False otherwise.
    """
    key = getattr(task, 'depends_on_key', '') or ''
    if not key:
        return False
    if not getattr(task, 'hide_until_ready', True):
        return False
    return not _prereq_completed(key, truth)


def _prereq_completed(key: str, truth) -> bool:
    """Resolve whether the prerequisite identified by `key` is complete.

    Unknown prefixes, malformed keys, and missing targets fail OPEN
    (return True → not blocking).
    """
    if not key or ':' not in key:
        return True

    prefix, _, ident = key.partition(':')
    prefix = prefix.strip().lower()
    ident = ident.strip()
    if not ident:
        return True

    if prefix == 'task':
        return _task_prereq_completed(ident)
    if prefix == 'routine':
        return _routine_prereq_completed(ident, truth)
    if prefix == 'domain':
        return _domain_prereq_completed(ident, truth)

    # Unknown prefix — fail open
    return True


def _task_prereq_completed(ident: str) -> bool:
    """Look up a Task prerequisite by pk and check completion_status."""
    try:
        pk = int(ident)
    except (TypeError, ValueError):
        return True
    try:
        from apps.life.models import Task
        prereq = (
            Task.objects.filter(pk=pk).only('completion_status').first()
        )
    except ImportError:
        return True
    except Exception:
        logger.warning(
            "[DEPENDENCY GATING] Task prereq lookup failed pk=%s", pk,
            exc_info=True,
        )
        return True
    if prereq is None:
        return True  # Dangling ref — fail open
    return prereq.completion_status == 'completed'


def _routine_prereq_completed(ident: str, truth) -> bool:
    """Look up a RoutineSchedule completion via execution truth.

    truth['routines']['_raw_items'] is keyed by window; each entry has a
    'schedule_id' and 'is_completed' flag derived from the canonical
    execution truth engine (which bridges domain logs → routine completion).
    """
    try:
        schedule_id = int(ident)
    except (TypeError, ValueError):
        return True
    if not isinstance(truth, dict):
        return True
    raw_items = (
        truth.get('routines', {}).get('_raw_items', {}) or {}
    )
    for _window, items in raw_items.items():
        for item in items or []:
            if item.get('schedule_id') == schedule_id:
                return bool(item.get('is_completed'))
    # Not found in today's routine items — fail open
    return True


def _domain_prereq_completed(name: str, truth) -> bool:
    """Look up a domain-level completion rollup.

    Supported names mirror truth['domains'] keys: 'workout', 'journal',
    'faith', and the sub-flags 'prayer'/'bible_reading' (which live under
    truth['domains']['faith']).
    """
    if not isinstance(truth, dict):
        return True
    domains = truth.get('domains', {}) or {}

    # Direct match: 'workout', 'journal', 'faith'
    if name in domains:
        entry = domains[name]
        if isinstance(entry, dict):
            return bool(entry.get('completed'))
        return bool(entry)

    # Faith sub-flags
    faith = domains.get('faith', {}) or {}
    if name == 'prayer':
        return bool(faith.get('prayer_completed'))
    if name == 'bible_reading':
        return bool(faith.get('bible_reading_completed'))

    # Unknown domain — fail open
    return True
