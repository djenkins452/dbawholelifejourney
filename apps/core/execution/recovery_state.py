"""
Deterministic recovery-state machine for the WLJ recovery contract.

Computes a single RecoveryState dict per build_execution_state call.
Inputs are already in scope: classified items, summaries, active_block,
now. PURE module — no DB, no LLM, no side effects.

Mode rules (evaluated in order; first match wins):

    SHUTDOWN     now.hour >= SHUTDOWN_TRIGGER_HOUR
                 AND (recoverable_overdue + expired) >= SHUTDOWN_OVERDUE_THRESHOLD

    RECOVERY     now.hour >= RECOVERY_TRIGGER_HOUR
                 AND recoverable_overdue >= RECOVERY_OVERDUE_THRESHOLD

    STABILIZE    missed_foundational >= 1
                 AND a reset action exists in the eligible pool
                 (item.is_reset_action is True AND is_recoverable)

    NORMAL       default

day_narrative is derived deterministically from mode + counts + clock:

    on_track             NORMAL with no overdue
    behind_recoverable   overdue items present, all recoverable
    behind_reset_required STABILIZE mode
    day_lost_salvage     RECOVERY mode (post-noon, multiple overdue)
    evening_closeout     SHUTDOWN mode

recommended_strategy is a string code (not prose):

    continue_schedule | recover_morning | shutdown_evening | stabilize_then_resume
"""

import datetime as _dt

from .constants import (
    RECOVERY_OVERDUE_THRESHOLD,
    RECOVERY_TRIGGER_HOUR,
    SHUTDOWN_OVERDUE_THRESHOLD,
    SHUTDOWN_TRIGGER_HOUR,
)
from .execution_status import (
    AT_RISK,
    EXPIRED_HARD,
    EXPIRED_WINDOWED,
    LATE_OPEN,
)
from .recoverability import is_recoverable
from .task_classifier import FLEXIBLE, HARD_EXPIRED, SOFT_EXPIRED, WINDOWED


# ── Mode constants ──────────────────────────────────────────────────
NORMAL = "NORMAL"
RECOVERY = "RECOVERY"
STABILIZE = "STABILIZE"
SHUTDOWN = "SHUTDOWN"

# ── Day narratives ──────────────────────────────────────────────────
NARR_ON_TRACK = "on_track"
NARR_BEHIND_RECOVERABLE = "behind_recoverable"
NARR_BEHIND_RESET_REQUIRED = "behind_reset_required"
NARR_DAY_LOST_SALVAGE = "day_lost_salvage"
NARR_EVENING_CLOSEOUT = "evening_closeout"

# ── Strategies ──────────────────────────────────────────────────────
STRAT_CONTINUE = "continue_schedule"
STRAT_RECOVER = "recover_morning"
STRAT_SHUTDOWN = "shutdown_evening"
STRAT_STABILIZE = "stabilize_then_resume"


def _now_time(now):
    if isinstance(now, _dt.datetime):
        return now.time()
    return now or _dt.time(12, 0)


def _is_open_item(item):
    """An item is 'open' if it's actionable and not yet completed."""
    if item.get("completed_today"):
        return False
    return bool(item.get("is_actionable", False))


def compute_recovery_state(items, now, summaries=None, active_block=None):
    """Compute a RecoveryState dict from classified ExecutionItems.

    Args:
        items: list of ExecutionItem dicts (already annotated with
               task_class / recovery_grace_minutes / is_reset_action).
        now: datetime.time or datetime.datetime.
        summaries: optional execution summaries (unused in v1; reserved).
        active_block: optional active_block dict from get_active_block().

    Returns:
        dict shaped for state["recovery_state"] consumption:
            {
                'mode': 'NORMAL' | 'RECOVERY' | 'STABILIZE' | 'SHUTDOWN',
                'reason': str,
                'missed_foundational_count': int,
                'recoverable_overdue_count': int,
                'expired_count': int,
                'current_window_status': str,
                'recommended_strategy': str,
                'day_narrative': str,
                'reset_action_available': bool,
            }
    """
    now_time = _now_time(now)

    # ── Counts ─────────────────────────────────────────────────────
    open_items = [i for i in (items or []) if _is_open_item(i)]
    overdue_open = [i for i in open_items if i.get("time_status") == "overdue"]

    recoverable_overdue = [i for i in overdue_open if is_recoverable(i, now_time)]
    expired = [i for i in overdue_open if not is_recoverable(i, now_time)]

    # Foundational items that are missed AND not recoverable — these
    # still drive the narrative and risk/fix priority even though the
    # action itself can no longer be done.
    missed_foundational = [
        i for i in expired
        if i.get("is_foundational")
        and (i.get("task_class") or FLEXIBLE) != FLEXIBLE
    ]

    # ── Execution-status–aware escalation count ────────────────────
    # RECOVERY mode MUST only escalate on items that genuinely
    # threaten the day's safety / health intent. The prior contract
    # counted any late item — that incorrectly treated a delayed
    # workout / shower / protein shake (SOFT_EXPIRED LATE_OPEN) as
    # equivalent to a missed insulin dose (foundational WINDOWED
    # AT_RISK / EXPIRED_WINDOWED), forcing the mode into RECOVERY
    # and triggering "rebuild the day" reactions when nothing was
    # actually breaking.
    #
    # New contract (Phase 2):
    #   escalation_overdue = foundational items in AT_RISK or
    #                        EXPIRED_WINDOWED state only.
    #
    # Hard-expired foundational items (missed appointments) are
    # surfaced via missed_foundational_count for STABILIZE, but the
    # action itself is gone so they do NOT pump the RECOVERY counter
    # — Beth cannot help the user "recover" something that is over.
    def _status_of(item):
        return item.get("execution_status")

    escalation_overdue = []
    for i in overdue_open:
        if not i.get("is_foundational"):
            continue
        cls = i.get("task_class") or FLEXIBLE
        # SOFT_EXPIRED LATE_OPEN never escalates — late but still
        # planned today. FLEXIBLE items have no real "late".
        if cls in (SOFT_EXPIRED, FLEXIBLE):
            continue
        status = _status_of(i)
        if status in (AT_RISK, EXPIRED_WINDOWED):
            escalation_overdue.append(i)
            continue
        # Defensive fallback: if execution_status wasn't annotated
        # (legacy callers / failures), fall back to the
        # task_class + recoverability inference for WINDOWED items
        # only. SOFT_EXPIRED never falls back into escalation.
        if status is None and cls == WINDOWED:
            escalation_overdue.append(i)

    # Reset-action availability: only items the user could actually do.
    reset_available = any(
        i.get("is_reset_action") and is_recoverable(i, now_time)
        for i in open_items
    )

    counts = {
        "missed_foundational_count": len(missed_foundational),
        "recoverable_overdue_count": len(recoverable_overdue),
        "expired_count": len(expired),
        "escalation_overdue_count": len(escalation_overdue),
        "current_window_status": (active_block or {}).get("name") or "no_block",
        "reset_action_available": reset_available,
    }

    # ── Mode resolution ────────────────────────────────────────────
    hour = now_time.hour
    # SHUTDOWN preserves its prior signal (any late or expired item in
    # the evening) — the user did not include SHUTDOWN in the Phase 2
    # narrowing. Evening "stop trying to catch up" semantics stay.
    total_overdue_signal = len(recoverable_overdue) + len(expired)

    if (
        hour >= SHUTDOWN_TRIGGER_HOUR
        and total_overdue_signal >= SHUTDOWN_OVERDUE_THRESHOLD
    ):
        mode = SHUTDOWN
        strategy = STRAT_SHUTDOWN
        narrative = NARR_EVENING_CLOSEOUT
        reason = (
            f"Late ({hour:02d}:00) with {total_overdue_signal} unresolved "
            f"items — preserve tomorrow."
        )
    elif (
        hour >= RECOVERY_TRIGGER_HOUR
        and len(escalation_overdue) >= RECOVERY_OVERDUE_THRESHOLD
    ):
        # RECOVERY now requires *foundational* WINDOWED items to be
        # genuinely at-risk / expired. A bunch of late SOFT_EXPIRED
        # workouts/showers/journals can no longer flip the mode.
        mode = RECOVERY
        strategy = STRAT_RECOVER
        narrative = NARR_DAY_LOST_SALVAGE
        reason = (
            f"Past noon with {len(escalation_overdue)} foundational item(s) "
            f"at risk — rebuild the day forward."
        )
    elif counts["missed_foundational_count"] >= 1 and reset_available:
        mode = STABILIZE
        strategy = STRAT_STABILIZE
        narrative = NARR_BEHIND_RESET_REQUIRED
        reason = (
            f"{counts['missed_foundational_count']} foundational item(s) "
            f"missed — reset before resuming."
        )
    else:
        mode = NORMAL
        strategy = STRAT_CONTINUE
        if overdue_open:
            narrative = NARR_BEHIND_RECOVERABLE
            reason = f"{len(overdue_open)} overdue item(s) — still on schedule."
        else:
            narrative = NARR_ON_TRACK
            reason = "On track."

    return {
        "mode": mode,
        "reason": reason,
        "missed_foundational_count": counts["missed_foundational_count"],
        "recoverable_overdue_count": counts["recoverable_overdue_count"],
        "expired_count": counts["expired_count"],
        "escalation_overdue_count": counts["escalation_overdue_count"],
        "current_window_status": counts["current_window_status"],
        "recommended_strategy": strategy,
        "day_narrative": narrative,
        "reset_action_available": reset_available,
    }
