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
        "timing": dict (from compute_execution_timing),   # calculations, facts only
        "execution_phase": dict (from compute_execution_phase),  # day phase, facts only
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


def build_execution_state(user, now=None, execution_contract=None) -> dict:
    """
    Build the unified execution state dict consumed by all CoS modes.

    Args:
        user: User instance.
        now: datetime.datetime or datetime.time. Defaults to user's local
             current time (resolved via get_user_now).
        execution_contract: Optional pre-fetched dict from
            ``build_today_execution(user)``. Passed by the v3 dashboard
            composer so the rhythm + executive_summary + gauges all
            share ONE truth fetch per request (Phase 2 dedup — saves
            ~60 redundant queries per dashboard render). When omitted
            (any other caller) the function fetches its own contract.

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

    exec_contract = execution_contract if execution_contract is not None else build_today_execution(user)
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
    #    recoverable items (e.g., a 5:30 AM HARD_EXPIRED service at
    #    noon) live in Risk/Fix only; they must NOT be the next action.
    #
    #    Phase 3 exception: SOFT_EXPIRED items in LATE_OPEN status stay
    #    eligible all day. A 6:15 AM workout at 11:13 AM is still a
    #    real candidate for "what should I do now?" — the user just
    #    delayed it. Evicting it forces the selector to pick the next
    #    future anchor (e.g. a 1:00 PM optimization supplement), which
    #    is the exact bug we are fixing.
    from apps.core.execution.active_block import is_item_in_active_block
    from apps.core.execution.execution_status import LATE_OPEN as _LATE_OPEN

    def _block_eligible(a):
        # LATE_OPEN bypass — SOFT_EXPIRED items past their schedule
        # remain meaningfully completable until end-of-day, regardless
        # of which canonical block we are currently in.
        if a.get('execution_status') == _LATE_OPEN:
            return True
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

    # Completed-today bucket — reconciled in build_today_execution (single producer),
    # so a task here can never also be in overdue/now/next/upcoming. Non-actionable by
    # construction, so it never entered the prioritized `actions` above.
    completed = [i for i in items if i.get('completed_today')]

    # Deterministic timing CALCULATIONS (facts only — minutes late / buffer / earliest
    # completion / latest safe start / fits-before-anchor / required pace). The
    # conversational model reads these and JUDGES the situation; WLJ never labels it.
    from apps.core.execution.timing import compute_execution_timing
    timing = compute_execution_timing(
        {"items": items}, now if isinstance(now, _dt.datetime) else now_time,
    )

    # Deterministic DAY EXECUTION PHASE (facts only — where the user actually is in
    # today's execution: before their first commitment, underway, behind, ahead,
    # winding down, done). This is the SINGLE fact every surface consumes so no
    # surface (dashboard / CoS / notifications / widgets / voice) ever re-decides
    # whether the day has begun. Never a verdict — the narrator interprets it.
    execution_phase = compute_execution_phase(
        user, now if isinstance(now, _dt.datetime) else now_time,
        items=items, overdue_actions=overdue, now_actions=now_a,
        completed_today=completed, next_actions=next_a, upcoming_actions=upcoming,
        active_block=active_block, recovery_state=recovery_state,
    )

    return {
        "now": now_time,
        "timing": timing,
        "execution_phase": execution_phase,
        "active_block": active_block,
        "items": items,
        "summaries": summaries,
        "actions": actions,
        "eligible_actions": eligible_actions,
        "overdue_actions": overdue,
        "now_actions": now_a,
        "next_actions": next_a,
        "upcoming_actions": upcoming,
        "completed_today": completed,
        "expired_items": expired_items,
        "deferred_items": deferred_items,
        "collapsed_blocks": collapsed_blocks,
        "at_risk_actions": at_risk_actions,
        "recovery_state": recovery_state,
        "blocked_dependents": blocked_dependents,
    }


def compute_execution_phase(
    user, now, *, items, overdue_actions, now_actions, completed_today,
    next_actions, upcoming_actions, active_block=None, recovery_state=None,
) -> dict:
    """The deterministic DAY EXECUTION PHASE — where the user actually is in today's
    execution, as FACTS only (no verdict, no coaching, no recommendation).

    This is the single source every surface consumes for "has the day begun / are they
    before their first commitment / underway / behind / ahead / winding down / done."
    It exists so the Executive Briefing (and CoS, notifications, widgets, voice…) can
    NEVER infer today's state from the clock alone or from a weekly trend — the exact
    fabrication that produced "Slow start" at 4:56 AM before the day had begun.

    Phase precedence (execution truth beats the clock):
        day_complete           — no remaining actionable work (and the day has begun,
                                 or it's already evening/night)
        behind                 — one or more commitments are overdue right now
        before_first_commitment— nothing done, nothing overdue, and the first scheduled
                                 commitment is still in the future
        ahead                  — a future-scheduled commitment was completed early
        underway / midday /
        afternoon / winding_down — the day is begun and on-track; framed by the canonical
                                 daypart clock phase (reused, never re-bucketed here)

    Returns a facts dict:
        {
          "phase": <one of the above | "unknown">,
          "day_begun": bool, "day_complete": bool,
          "before_first_commitment": bool, "underway": bool, "behind": bool,
          "ahead": bool, "midday": bool, "afternoon": bool, "winding_down": bool,
          "first_commitment": {"title","time","minutes_until"} | None,
          "minutes_until_first_commitment": int | None,
          "completed_count": int, "overdue_count": int, "remaining_count": int,
          "clock_phase": "morning|midday|evening|night", "hour": int | None,
        }

    Never raises: on any failure returns a neutral "unknown" phase so a consumer degrades
    to non-fabricating wording rather than inventing the day's state.
    """
    try:
        from apps.core.execution.timing import (
            earliest_future_commitment, completed_ahead_of_schedule,
        )
        from apps.core.truth import daypart

        completed_count = len(completed_today or [])
        overdue_count = len(overdue_actions or [])
        now_count = len(now_actions or [])
        remaining_count = (
            overdue_count + now_count
            + len(next_actions or []) + len(upcoming_actions or [])
        )

        first = earliest_future_commitment(items, now)
        ahead_count = completed_ahead_of_schedule(items, now)

        # Reuse the canonical clock authority — no second bucketing of the day.
        dp = daypart.resolve(user, now if _is_dt(now) else None)
        clock_phase = dp.get("phase")
        hour = dp.get("hour")

        day_begun = completed_count > 0 or overdue_count > 0 or now_count > 0

        if remaining_count == 0 and (day_begun or clock_phase in ("evening", "night")):
            phase = "day_complete"
        elif overdue_count > 0:
            phase = "behind"
        elif not day_begun and first is not None:
            phase = "before_first_commitment"
        elif not day_begun and first is None:
            phase = "day_complete" if clock_phase in ("evening", "night") else "before_first_commitment"
        elif ahead_count > 0:
            phase = "ahead"
        elif clock_phase == "morning":
            phase = "underway"
        elif clock_phase == "midday":
            phase = "afternoon" if (hour is not None and hour >= 14) else "midday"
        elif clock_phase == "evening":
            phase = "winding_down"
        else:  # night, on-track, work remaining
            phase = "winding_down"

        return {
            "phase": phase,
            "day_begun": day_begun,
            "day_complete": phase == "day_complete",
            "before_first_commitment": phase == "before_first_commitment",
            "underway": phase == "underway",
            "behind": phase == "behind",
            "ahead": phase == "ahead",
            "midday": phase == "midday",
            "afternoon": phase == "afternoon",
            "winding_down": phase == "winding_down",
            "first_commitment": first,
            "minutes_until_first_commitment": (first or {}).get("minutes_until"),
            "completed_count": completed_count,
            "overdue_count": overdue_count,
            "remaining_count": remaining_count,
            "clock_phase": clock_phase,
            "hour": hour,
        }
    except Exception:  # pragma: no cover - defensive; never fabricate the day's state
        logger.warning(
            "[EXECUTION STATE] execution_phase compute failed user=%s",
            getattr(user, "id", None), exc_info=True,
        )
        return {"phase": "unknown", "day_begun": False, "day_complete": False,
                "before_first_commitment": False, "underway": False, "behind": False,
                "ahead": False, "midday": False, "afternoon": False,
                "winding_down": False, "first_commitment": None,
                "minutes_until_first_commitment": None, "completed_count": 0,
                "overdue_count": 0, "remaining_count": 0, "clock_phase": None,
                "hour": None}


def _is_dt(value) -> bool:
    """True when ``value`` is a datetime (not a bare time)."""
    import datetime as _dt
    return isinstance(value, _dt.datetime)


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
