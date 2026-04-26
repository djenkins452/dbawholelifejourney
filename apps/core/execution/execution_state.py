"""
Execution State Builder — single composed input for all CoS decision modes.

Wraps existing pieces (today_execution + active_block + prioritizer) into
one dict shaped for deterministic selectors. No new compute, no new
engine — composition only.

Consumed by:
    apps.core.execution.selectors :: get_next_action(state)
    apps.core.execution.selectors :: get_biggest_risk(state)
    apps.core.execution.selectors :: get_fix_priority(state)

This is the *single* input contract for all three CoS decision modes.
Selectors must read ONLY from this dict — no DB queries, no LLM, no raw
data reasoning inside selectors.

Returned shape:
    {
        "now": datetime.time,
        "active_block": dict (from get_active_block),
        "items": list[ExecutionItem dict],   # raw execution contract items
        "summaries": dict,                   # raw execution contract summaries
        "actions": list[action dict],        # prioritized actions (with urgency)
        "overdue_actions": list[action dict],
        "now_actions":     list[action dict],   # urgency == 'now'
        "next_actions":    list[action dict],   # urgency == 'next'
        "upcoming_actions":list[action dict],   # urgency == 'upcoming'
        "blocked_dependents": dict[str, list[int]],
            # depends_on_key -> [Task pks blocked by this key]
            # Used by get_fix_priority to compute downstream unblock impact.
    }
"""

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


def build_execution_state(user, now=None) -> dict:
    """
    Build the unified execution state dict consumed by all CoS modes.

    Args:
        user: User instance.
        now: datetime.datetime or datetime.time. Defaults to user's local
             current time (resolved via get_user_now).

    Returns:
        dict — see module docstring for shape.
    """
    import datetime as _dt
    from apps.core.execution.today_execution import build_today_execution
    from apps.core.execution.active_block import get_active_block
    from apps.core.decision_engine.action_prioritizer import (
        prioritize_execution_items,
    )

    if now is None:
        from apps.core.utils import get_user_now
        try:
            now = get_user_now(user)
        except Exception:
            now = _dt.datetime.now()

    if isinstance(now, _dt.datetime):
        now_time = now.time()
    else:
        now_time = now

    exec_contract = build_today_execution(user)
    items = exec_contract.get('items', []) or []
    summaries = exec_contract.get('summaries', {}) or {}

    actions = prioritize_execution_items(
        items, now_time, summaries=summaries,
    ) or []

    active_block = get_active_block(user, now=now, execution_items=items)

    overdue = [a for a in actions if a.get('urgency') == 'overdue']
    now_a = [a for a in actions if a.get('urgency') == 'now']
    next_a = [a for a in actions if a.get('urgency') == 'next']
    upcoming = [a for a in actions if a.get('urgency') == 'upcoming']

    blocked_dependents = _compute_blocked_dependents(user)

    return {
        "now": now_time,
        "active_block": active_block,
        "items": items,
        "summaries": summaries,
        "actions": actions,
        "overdue_actions": overdue,
        "now_actions": now_a,
        "next_actions": next_a,
        "upcoming_actions": upcoming,
        "blocked_dependents": blocked_dependents,
    }


def _compute_blocked_dependents(user) -> dict:
    """
    Build a dict mapping depends_on_key -> [Task pks blocked by it] for
    the user's pending tasks today.

    Used by get_fix_priority to compute "if I clear this, what unblocks?"
    without the selectors touching the DB themselves.

    Returns dict[str, list[int]]; never raises.
    """
    mapping = defaultdict(list)
    try:
        from apps.life.models import Task
        # Pending tasks with a non-empty depends_on_key.
        qs = (
            Task.objects.filter(user=user)
            .exclude(completion_status='completed')
            .exclude(depends_on_key='')
            .values_list('pk', 'depends_on_key', 'hide_until_ready')
        )
        for pk, key, hide_until_ready in qs:
            if not key:
                continue
            # Honor hide_until_ready — fix-mode only counts dependents
            # that are *actually* gated.
            if not hide_until_ready:
                continue
            mapping[key].append(pk)
    except Exception:
        logger.warning(
            "[EXECUTION STATE] blocked_dependents lookup failed user=%s",
            getattr(user, 'id', None), exc_info=True,
        )
    return dict(mapping)
