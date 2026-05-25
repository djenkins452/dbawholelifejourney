"""
Execution Status — deterministic per-item state classification.

Single source of truth for the question:

    "What execution state is this item in *right now*?"

Computed once from (task_class, scheduled_time, grace, foundational,
current_time, completion state) and reused across:

  - recovery_state mode triggers (only foundational AT_RISK /
    EXPIRED_WINDOWED items escalate; LATE_OPEN never escalates).
  - active_block eligibility (LATE_OPEN items remain eligible all day).
  - selectors (no logic — they read this status from the action dict).
  - UI emphasis (badge / dimming choices).

PURE module — no DB, no LLM, no settings lookup at runtime.

Status definitions
------------------

ON_TIME           Not yet past scheduled, OR no schedule at all.
                  Default "all good" state.

LATE_OPEN         SOFT_EXPIRED past scheduled, still meaningfully doable
                  today. Examples: workout / shower / protein shake /
                  Bible reading / journaling / flexible habits.
                  Late but still *intended*. Never escalates recovery.

AT_RISK           WINDOWED past scheduled but inside grace cutoff.
                  Approaching the point where the dose / nutrition
                  anchor is no longer meaningful. Foundational AT_RISK
                  items drive RECOVERY escalation; non-foundational
                  ones are surfaced as risk but do not flip the mode.

EXPIRED_WINDOWED  WINDOWED past grace cutoff. Cannot be meaningfully
                  recovered as the original dose. Foundational ones
                  drive STABILIZE/RECOVERY narrative.

EXPIRED_HARD      HARD_EXPIRED past scheduled (service, meeting,
                  appointment). The moment is gone — not surfaced as
                  "do now". Logged as missed.

SKIPPED           User explicitly marked the item skipped. Not
                  surfaced anywhere as actionable.

Rationale: prior to this module the system collapsed everything past
its scheduled time into a single "overdue" bucket that flipped the day
into RECOVERY mode after noon. That behaviour treated a late workout
the same as a missed insulin dose. Splitting the state space lets the
recovery machine respect *intent* — late SOFT_EXPIRED items are still
planned for today, not a schedule failure.
"""

import datetime as _dt

from .recoverability import is_recoverable
from .task_classifier import (
    FLEXIBLE,
    HARD_EXPIRED,
    SOFT_EXPIRED,
    WINDOWED,
)

# ── String enum values (JSON-serializable; usable in templates) ─────
ON_TIME = "ON_TIME"
LATE_OPEN = "LATE_OPEN"
AT_RISK = "AT_RISK"
EXPIRED_WINDOWED = "EXPIRED_WINDOWED"
EXPIRED_HARD = "EXPIRED_HARD"
SKIPPED = "SKIPPED"

ALL_STATUSES = (
    ON_TIME,
    LATE_OPEN,
    AT_RISK,
    EXPIRED_WINDOWED,
    EXPIRED_HARD,
    SKIPPED,
)

# Status severity rank — used when aggregating multiple items into a
# group-level status (e.g. medicine windows). Higher = more degraded.
STATUS_SEVERITY_RANK = {
    EXPIRED_HARD: 5,
    EXPIRED_WINDOWED: 4,
    AT_RISK: 3,
    LATE_OPEN: 2,
    ON_TIME: 1,
    SKIPPED: 0,
    None: 0,
}


def _parse_time(value):
    """Parse a time string ('HH:MM' or 'h:MM AM/PM') or time object."""
    if value is None:
        return None
    if isinstance(value, _dt.time):
        return value
    s = str(value).strip()
    for fmt in ("%H:%M", "%I:%M %p"):
        try:
            return _dt.datetime.strptime(s, fmt).time()
        except (ValueError, TypeError):
            continue
    return None


def _to_minutes(t):
    return t.hour * 60 + t.minute


def _now_time(now):
    if isinstance(now, _dt.datetime):
        return now.time()
    return now or _dt.time(12, 0)


def compute_execution_status(item, now):
    """Derive the deterministic execution status for an item.

    Args:
        item: ExecutionItem dict. Must already be annotated by
            task_classifier (carries task_class, recovery_grace_minutes,
            is_reset_action). May carry completion_status / skipped /
            completed_today flags.
        now: datetime.time or datetime.datetime. Used to determine
            whether the item is past scheduled and (for WINDOWED) past
            the grace cutoff.

    Returns:
        str — one of ALL_STATUSES.

    Contract:
        - Pure function. No DB, no LLM, no clock reads beyond `now`.
        - Never returns None. Falls through to ON_TIME on unknowns.
        - Completion is NOT a status here — completed items remain in
          their last derived status (callers know to skip them via
          completed_today / is_actionable). This keeps "what state was
          this item in at the moment it was finished" recoverable.
    """
    now_time = _now_time(now)

    # 1. SKIPPED short-circuits everything else.
    if (
        item.get("completion_status") == "skipped"
        or item.get("skipped")
        or item.get("status") == "skipped"
    ):
        return SKIPPED

    cls = item.get("task_class") or FLEXIBLE
    scheduled = _parse_time(item.get("scheduled_time"))

    # 2. No schedule → status is ON_TIME by default.
    #    FLEXIBLE items inherently have no late state; unscheduled
    #    SOFT_EXPIRED items (rare) are likewise treated as on-time.
    if scheduled is None:
        return ON_TIME

    sched_m = _to_minutes(scheduled)
    now_m = _to_minutes(now_time)

    # 3. Not yet past scheduled → ON_TIME.
    if now_m < sched_m:
        return ON_TIME

    # 4. Past scheduled — class-dependent.
    if cls == HARD_EXPIRED:
        # grace=0 — the moment is gone.
        return EXPIRED_HARD

    if cls == WINDOWED:
        # AT_RISK while inside grace cutoff, EXPIRED_WINDOWED once past.
        if is_recoverable(item, now_time):
            return AT_RISK
        return EXPIRED_WINDOWED

    if cls == SOFT_EXPIRED:
        # Late but still meaningfully completable today.
        return LATE_OPEN

    # 5. FLEXIBLE / unknown — no real "late" semantics.
    return ON_TIME


def annotate_execution_status(item, now):
    """In-place mutator: write execution_status onto the item dict.

    Idempotent — re-annotating an already-annotated item produces the
    same value (given the same `now`).
    """
    item["execution_status"] = compute_execution_status(item, now)
    return item


def worst_status(*statuses):
    """Return the most-degraded status among the inputs.

    Used to aggregate multiple items into a group-level status (e.g.
    medicine window with several doses — the worst dose drives the
    group's status).

    None / unknown values are treated as severity 0 (least degraded).
    """
    best = None
    best_rank = -1
    for s in statuses:
        rank = STATUS_SEVERITY_RANK.get(s, 0)
        if rank > best_rank:
            best = s
            best_rank = rank
    return best
