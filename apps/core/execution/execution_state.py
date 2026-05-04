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
        "actions": list[action dict],        # prioritized + filtered + bucket-ordered
        "eligible_actions": list[action dict],   # alias of actions, for selector clarity
        "overdue_actions": list[action dict],
        "now_actions":     list[action dict],   # urgency == 'now'
        "next_actions":    list[action dict],   # urgency == 'next'
        "upcoming_actions":list[action dict],   # urgency == 'upcoming'
        "expired_items":   list[ExecutionItem dict],   # not recoverable
        "deferred_items":  list[ExecutionItem dict],   # suppressed by collapse 'defer'
        "collapsed_blocks": list[BlockCollapse dict],  # see action_prioritizer.compute_block_collapses
        "at_risk_actions": list[action dict],          # see compute_at_risk
        "recovery_state":  dict (from compute_recovery_state),
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
    from apps.core.execution.recoverability import is_recoverable
    from apps.core.execution.recovery_state import compute_recovery_state
    from apps.core.decision_engine.action_prioritizer import (
        apply_recovery_bucket_selection,
        compute_at_risk,
        compute_block_collapses,
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

    active_block = get_active_block(user, now=now, execution_items=items)

    # ── Block collapses come first; their suppression set feeds the
    #    prioritizer so suppressed items never enter the action pool.
    collapse_result = compute_block_collapses(items, now_time, active_block)
    suppressed_keys = collapse_result.get('suppressed_source_keys') or set()
    collapsed_blocks = collapse_result.get('collapses') or []
    deferred_items = [
        i for i in items
        if (i.get('source_type'), i.get('source_id')) in suppressed_keys
        and is_recoverable(i, now_time)
    ]

    # ── Expired items: open + non-recoverable. Foundational expired
    #    items still drive risk/fix selection upstream of this list.
    expired_items = [
        i for i in items
        if i.get('is_actionable')
        and not i.get('completed_today')
        and not is_recoverable(i, now_time)
    ]

    # ── Prioritize with recovery filtering applied.
    raw_actions = prioritize_execution_items(
        items, now_time, summaries=summaries,
        suppressed_source_keys=suppressed_keys,
    ) or []

    # ── Recovery state derived from the FULL item set (not the
    #    filtered action list) so missed-foundational drives the mode.
    recovery_state = compute_recovery_state(
        items, now_time, summaries=summaries, active_block=active_block,
    )

    # ── Recovery-mode bucket selection re-orders / trims the action list.
    actions = apply_recovery_bucket_selection(raw_actions, recovery_state)

    # ── Active-block eligibility filter for EXECUTION mode. Stale
    #    recoverable items (e.g., a 5:30 AM SOFT_EXPIRED prayer at
    #    noon) live in Risk/Fix only; they must NOT be the next action.
    from apps.core.execution.active_block import is_item_in_active_block

    def _block_eligible(a):
        return is_item_in_active_block(
            {
                'scheduled_time': a.get('time_display'),
                'time_status': (
                    'overdue' if a.get('urgency') == 'overdue' else None
                ),
            },
            active_block,
            now_time,
        )

    eligible_actions = [a for a in actions if _block_eligible(a)]

    blocked_dependents = _compute_blocked_dependents(user)
    at_risk_actions = compute_at_risk(actions, blocked_dependents, now_time)

    overdue = [a for a in actions if a.get('urgency') == 'overdue']
    now_a = [a for a in actions if a.get('urgency') == 'now']
    next_a = [a for a in actions if a.get('urgency') == 'next']
    upcoming = [a for a in actions if a.get('urgency') == 'upcoming']

    return {
        "now": now_time,
        "active_block": active_block,
        "items": items,
        "summaries": summaries,
        "actions": actions,
        "eligible_actions": eligible_actions,
        "overdue_actions": overdue,
        "now_actions": now_a,
        "next_actions": next_a,
        "upcoming_actions": upcoming,
        "expired_items": expired_items,
        "deferred_items": deferred_items,
        "collapsed_blocks": collapsed_blocks,
        "at_risk_actions": at_risk_actions,
        "recovery_state": recovery_state,
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
