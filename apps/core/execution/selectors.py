"""
Deterministic CoS Decision Selectors.

Three pure selectors corresponding to the three CoS decision modes:

    get_next_action(state)    — EXECUTION MODE  ("what should I do right now?")
    get_biggest_risk(state)   — RISK MODE       ("what is my biggest risk?")
    get_fix_priority(state)   — FIX MODE        ("what should I fix first?")

CONTRACT:
- All three take a single argument: the dict from
  apps.core.execution.execution_state.build_execution_state(user, now).
- They MUST NOT read the database, call an LLM, or access raw models.
- They MUST NOT compute urgency, time, or completion truth themselves —
  those come from the prioritizer/active_block already baked into `state`.
- Each returns the same payload shape:

    {
        "mode": "execution" | "risk" | "fix",
        "primary_action": dict | None,    # the chosen action (None = nothing)
        "reason": str,                    # short, deterministic, no LLM
        "follow_on": dict | None,         # optional next-after-primary
        "message": str,                   # one-line locked statement for chat
    }

  primary_action / follow_on are pass-through references into
  state["actions"] when present (so callers can extract title, time,
  source_url, etc. without re-deriving). They are NOT mutated.
"""

import logging
from datetime import time as _time

logger = logging.getLogger(__name__)


# ── Risk-mode domain weights ────────────────────────────────────────────
# Higher weight = greater risk impact. Used as the final tiebreaker in
# get_biggest_risk after foundationality and lateness.
_DOMAIN_RISK_WEIGHT = {
    'health': 5,
    'medical': 5,
    'intake': 5,
    'medicine': 5,
    'medication': 5,
    'supplement': 4,
    'routine': 3,
    'life': 2,
    'task': 2,
    'journal': 1,
    'faith': 1,
}


def _action_time_to_minutes(action) -> int:
    """Parse an action's time_display ('HH:MM' or 'h:MM AM/PM') to minutes.

    Returns a large sentinel (24*60) when no time is present so timeless
    items always sort *after* timed items.
    """
    td = (action or {}).get('time_display') or ''
    if not td:
        return 24 * 60
    s = str(td).strip()
    from datetime import datetime as _dt
    for fmt in ('%H:%M', '%I:%M %p'):
        try:
            t = _dt.strptime(s, fmt).time()
            return t.hour * 60 + t.minute
        except (ValueError, TypeError):
            continue
    return 24 * 60


def _format_time_suffix(action) -> str:
    td = (action or {}).get('time_display') or ''
    return f" ({td})" if td else ""


def _empty_payload(mode: str, message: str) -> dict:
    return {
        "mode": mode,
        "primary_action": None,
        "reason": message,
        "follow_on": None,
        "message": message,
    }


# ══════════════════════════════════════════════════════════════════════
# EXECUTION MODE — "What should I do right now?"
# ══════════════════════════════════════════════════════════════════════

def get_next_action(state: dict) -> dict:
    """
    EXECUTION MODE selector.

    Rules (locked by CoS Time/Sequence Integrity contract):
      - Eligibility = {overdue, now} only. 'next' is follow-on context,
        never primary.
      - Active-block gate: items outside the active block (with 15-min
        lead-in for the front of the next block) are not primary.
        Overdue items always pass the gate.
      - Within the eligible set, the prioritizer's order (urgency tier
        → scheduled_time → foundational → title) is honored verbatim.
    """
    from apps.core.execution.active_block import is_item_in_active_block

    actions = state.get("actions") or []
    if not actions:
        return _empty_payload("execution",
                              "All items are complete — nothing pending.")

    active_block = state.get("active_block") or {}
    now_time = state.get("now") or _time(12, 0)

    def _block_eligible(action):
        return is_item_in_active_block(
            {
                'scheduled_time': action.get('time_display'),
                'time_status': (
                    'overdue' if action.get('urgency') == 'overdue' else None
                ),
            },
            active_block,
            now_time,
        )

    primary_pool = [
        a for a in actions
        if a.get('urgency') in ('overdue', 'now')
    ]
    actionable = [a for a in primary_pool if _block_eligible(a)]

    if not actionable:
        forward_pool = [
            a for a in actions
            if a.get('urgency') in ('next', 'upcoming')
        ]
        forward_in_block = [a for a in forward_pool if _block_eligible(a)]
        forward = forward_in_block or forward_pool
        if forward:
            f = forward[0]
            f_title = f.get('title', '')
            f_time = f.get('time_display', '')
            time_note = f" at {f_time}" if f_time else ""
            msg = f"You're clear right now. Next up is {f_title}{time_note}."
            return {
                "mode": "execution",
                "primary_action": None,
                "reason": msg,
                "follow_on": f,
                "message": msg,
            }
        msg = "You're clear right now — nothing pending in the near term."
        return _empty_payload("execution", msg)

    top = actionable[0]
    top_title = top.get('title', '')
    suffix = _format_time_suffix(top)
    primary_msg = f"Start with {top_title}{suffix}."

    follow = next(
        (
            a for a in actions
            if a is not top
            and a.get('urgency') in ('overdue', 'now', 'next')
            and _block_eligible(a)
        ),
        None,
    )
    if follow:
        f_title = follow.get('title', '')
        f_suffix = _format_time_suffix(follow)
        message = f"{primary_msg} After that: {f_title}{f_suffix}."
    else:
        message = primary_msg

    return {
        "mode": "execution",
        "primary_action": top,
        "reason": (
            f"{top_title} is the next eligible action in your "
            f"{active_block.get('name') or 'current'} block."
        ),
        "follow_on": follow,
        "message": message,
    }


# ══════════════════════════════════════════════════════════════════════
# RISK MODE — "What is my biggest risk right now?"
# ══════════════════════════════════════════════════════════════════════

def get_biggest_risk(state: dict) -> dict:
    """
    RISK MODE selector.

    Selection priority (strict, deterministic):
      1. Foundational + overdue (longest overdue first).
      2. Any overdue (longest overdue first; foundational tiebreak).
      3. Foundational + now-tier missed items (currently in the now
         window but not done — about to slip).

    Within each tier, we further break ties by:
        - earlier scheduled_time (longer lateness)
        - higher domain weight (health/medication > routines > tasks)
        - title (deterministic stable tiebreak)

    No raw-data reasoning. No LLM. No "If ignored:" consequence text in v1.
    """
    actions = state.get("actions") or []
    if not actions:
        return _empty_payload("risk",
                              "No pending items — no risk detected.")

    overdue = state.get("overdue_actions") or []
    now_actions = state.get("now_actions") or []

    def _domain_weight(a):
        src = (a.get('source') or '').lower()
        return _DOMAIN_RISK_WEIGHT.get(src, 0)

    def _risk_key(a):
        # Lower is higher risk (so we sort ascending and take the first).
        # foundational_rank: 0 if foundational, 1 otherwise.
        foundational_rank = 0 if a.get('is_foundational') else 1
        # earlier time = larger lateness ⇒ smaller minutes.
        time_min = _action_time_to_minutes(a)
        # higher weight ⇒ smaller key, so negate.
        weight = -_domain_weight(a)
        return (foundational_rank, time_min, weight, a.get('title', ''))

    pool = []
    if overdue:
        pool = overdue[:]
    elif now_actions:
        pool = now_actions[:]
    else:
        return _empty_payload(
            "risk",
            "No overdue or active-window items — nothing at risk right now.",
        )

    pool.sort(key=_risk_key)
    top = pool[0]

    title = top.get('title', '')
    suffix = _format_time_suffix(top)
    src = (top.get('source') or 'item').replace('_', ' ')
    is_overdue = top.get('urgency') == 'overdue'
    is_foundational = bool(top.get('is_foundational'))

    if is_overdue and is_foundational:
        reason = (
            f"Foundational {src} overdue from {top.get('time_display') or 'today'}."
        )
    elif is_overdue:
        reason = (
            f"{src.capitalize()} overdue from {top.get('time_display') or 'today'}."
        )
    elif is_foundational:
        reason = f"Foundational {src} in active window — about to slip."
    else:
        reason = f"{src.capitalize()} in active window — about to slip."

    message = f"Your biggest risk right now is: {title}{suffix} — {reason} Fix this next."

    return {
        "mode": "risk",
        "primary_action": top,
        "reason": reason,
        "follow_on": None,
        "message": message,
    }


# ══════════════════════════════════════════════════════════════════════
# FIX MODE — "What should I fix first?"
# ══════════════════════════════════════════════════════════════════════

def get_fix_priority(state: dict) -> dict:
    """
    FIX MODE selector.

    Goal: reduce the most accumulated disorder. Picks the single overdue
    item whose completion would unblock the largest number of dependent
    pending tasks. Ties broken by (a) lowest commitment_level (simplest
    quick win), (b) earlier scheduled_time, (c) title.

    Source of unblock impact:
        state["blocked_dependents"]: depends_on_key -> [Task pks]

    We construct candidate `depends_on_key`s from each overdue action's
    type + identifier without parsing keys ourselves — the
    dependency_gating module owns key parsing. Here we only build
    candidate keys that match the canonical formats:
        task:{pk}      — for overdue tasks
        routine:{pk}   — for overdue routine items
        domain:{name}  — for overdue binary-domain actions

    No DB access in this selector — `state["blocked_dependents"]` was
    pre-computed by build_execution_state.
    """
    actions = state.get("actions") or []
    if not actions:
        return _empty_payload("fix",
                              "Nothing to fix — no pending items.")

    overdue = state.get("overdue_actions") or []
    if not overdue:
        return _empty_payload(
            "fix",
            "Nothing to fix — no overdue items.",
        )

    blocked_map = state.get("blocked_dependents") or {}

    _COMMITMENT_RANK = {
        'flexible': 0,
        'important': 1,
        'foundational': 2,
    }

    def _candidate_keys(action) -> list:
        keys = []
        atype = (action.get('type') or '').lower()
        src = (action.get('source') or '').lower()
        pk = action.get('pk')
        if pk and atype == 'task':
            keys.append(f'task:{pk}')
        if pk and src == 'routine':
            keys.append(f'routine:{pk}')
        if src in ('journal', 'faith', 'workout', 'faith_engaged'):
            domain = 'faith' if src in ('faith', 'faith_engaged') else src
            keys.append(f'domain:{domain}')
        return keys

    def _unblock_count(action) -> int:
        total = 0
        for k in _candidate_keys(action):
            total += len(blocked_map.get(k, []))
        return total

    annotated = [(a, _unblock_count(a)) for a in overdue]
    max_unblock = max((cnt for _, cnt in annotated), default=0)

    def _fix_key(item):
        a, cnt = item
        # Higher unblock count first ⇒ negate.
        commitment = (a.get('commitment_level') or '').lower()
        commit_rank = _COMMITMENT_RANK.get(commitment, 1)
        time_min = _action_time_to_minutes(a)
        return (-cnt, commit_rank, time_min, a.get('title', ''))

    annotated.sort(key=_fix_key)
    top, top_unblock = annotated[0]
    title = top.get('title', '')
    suffix = _format_time_suffix(top)

    if top_unblock > 0:
        impact = (
            f"This will unlock {top_unblock} blocked "
            f"{'item' if top_unblock == 1 else 'items'}."
        )
        reason = f"Clears {top_unblock} dependent items downstream."
    else:
        impact = "This is your simplest overdue item — clears the backlog."
        reason = "Simplest overdue item — quick win to reduce backlog."

    message = f"Start by fixing: {title}{suffix}. {impact}"

    return {
        "mode": "fix",
        "primary_action": top,
        "reason": reason,
        "follow_on": None,
        "message": message,
    }


# ── Mode dispatch table ─────────────────────────────────────────────
SELECTORS = {
    "execution": get_next_action,
    "risk":      get_biggest_risk,
    "fix":       get_fix_priority,
}


def select(mode: str, state: dict) -> dict:
    """Dispatch to the selector for `mode`. Defaults to execution on
    unknown mode (CoS must always answer with *something*)."""
    fn = SELECTORS.get(mode, get_next_action)
    return fn(state)
