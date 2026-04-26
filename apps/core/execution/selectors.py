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
    EXECUTION MODE selector — STRICT MODE ISOLATION contract.

    Output is EXACTLY one line, no commentary, no follow-on:
        "Next: [Action]. Do this now."
    or, when no current valid action exists:
        "Next: [Action]." (forward-only — no "Do this now")
    or, when nothing is pending at all:
        "Nothing pending right now."

    Rules:
      - Eligibility = {overdue, now} only. 'next' (~2h away) is NOT
        primary — it is forward context only.
      - Active-block gate: items in the active block, or the next
        block during lead-in, or overdue items in the *immediately
        preceding* canonical block. Overdue items in long-past blocks
        (e.g. a 5:30 AM prayer at noon) are NEVER primary — they
        surface in Risk / Fix instead.
      - Selector returns a SINGLE deterministic line. The chat shortcut
        and JSON API both render this as `message`. No blending.
    """
    from apps.core.execution.active_block import is_item_in_active_block

    actions = state.get("actions") or []
    if not actions:
        return _empty_payload("execution", "Nothing pending right now.")

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

    if actionable:
        top = actionable[0]
        title = top.get('title', '')
        return {
            "mode": "execution",
            "primary_action": top,
            "reason": "current",
            "follow_on": None,
            "message": f"Next: {title}. Do this now.",
        }

    # Nothing currently actionable — surface the next eligible item as
    # forward context, but DO NOT instruct "Do this now".
    forward_pool = [
        a for a in actions
        if a.get('urgency') in ('next', 'upcoming')
        and _block_eligible(a)
    ]
    if not forward_pool:
        forward_pool = [
            a for a in actions
            if a.get('urgency') in ('next', 'upcoming')
        ]
    if forward_pool:
        f = forward_pool[0]
        title = f.get('title', '')
        return {
            "mode": "execution",
            "primary_action": None,
            "reason": "upcoming",
            "follow_on": f,
            "message": f"Next: {title}.",
        }

    return _empty_payload("execution", "Nothing pending right now.")


# ══════════════════════════════════════════════════════════════════════
# RISK MODE — "What is my biggest risk right now?"
# ══════════════════════════════════════════════════════════════════════

def get_biggest_risk(state: dict) -> dict:
    """
    RISK MODE selector — STRICT MODE ISOLATION contract.

    Output is EXACTLY one line:
        "Biggest risk: [Issue]. Fix this next."
    or, when nothing is at risk:
        "No risks right now."

    No time math. No reason text. No multiple suggestions.

    Selection priority (strict, deterministic):
      1. Foundational + overdue (longest overdue first).
      2. Any overdue (longest overdue first; foundational tiebreak).
      3. Foundational + now-tier missed items (currently in the now
         window but not done — about to slip).

    Within each tier, ties broken by: earlier scheduled_time
    (longer lateness) → higher domain weight (health/medication >
    routines > tasks) → title.
    """
    actions = state.get("actions") or []
    if not actions:
        return _empty_payload("risk", "No risks right now.")

    overdue = state.get("overdue_actions") or []
    now_actions = state.get("now_actions") or []

    def _domain_weight(a):
        src = (a.get('source') or '').lower()
        return _DOMAIN_RISK_WEIGHT.get(src, 0)

    def _risk_key(a):
        foundational_rank = 0 if a.get('is_foundational') else 1
        time_min = _action_time_to_minutes(a)
        weight = -_domain_weight(a)
        return (foundational_rank, time_min, weight, a.get('title', ''))

    pool = list(overdue) if overdue else list(now_actions)
    if not pool:
        return _empty_payload("risk", "No risks right now.")

    pool.sort(key=_risk_key)
    top = pool[0]
    title = top.get('title', '')

    return {
        "mode": "risk",
        "primary_action": top,
        "reason": "overdue" if top.get('urgency') == 'overdue' else "at_risk",
        "follow_on": None,
        "message": f"Biggest risk: {title}. Fix this next.",
    }


# ══════════════════════════════════════════════════════════════════════
# FIX MODE — "What should I fix first?"
# ══════════════════════════════════════════════════════════════════════

def get_fix_priority(state: dict) -> dict:
    """
    FIX MODE selector — STRICT MODE ISOLATION contract.

    Output is EXACTLY one line:
        "Fix this first: [Action]."
    or, when nothing is overdue:
        "Nothing to fix."

    No time. No impact text. No multiple suggestions.

    Goal: reduce accumulated disorder. Picks the overdue item whose
    completion unblocks the most dependent pending tasks (via
    state["blocked_dependents"], pre-computed by build_execution_state
    from dependency_gating semantics). Ties broken by:
      1. lowest commitment_level (simplest quick win)
      2. earliest scheduled_time
      3. title
    """
    actions = state.get("actions") or []
    if not actions:
        return _empty_payload("fix", "Nothing to fix.")

    overdue = state.get("overdue_actions") or []
    if not overdue:
        return _empty_payload("fix", "Nothing to fix.")

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
        return sum(
            len(blocked_map.get(k, [])) for k in _candidate_keys(action)
        )

    annotated = [(a, _unblock_count(a)) for a in overdue]

    def _fix_key(item):
        a, cnt = item
        commitment = (a.get('commitment_level') or '').lower()
        commit_rank = _COMMITMENT_RANK.get(commitment, 1)
        time_min = _action_time_to_minutes(a)
        return (-cnt, commit_rank, time_min, a.get('title', ''))

    annotated.sort(key=_fix_key)
    top, _top_unblock = annotated[0]
    title = top.get('title', '')

    return {
        "mode": "fix",
        "primary_action": top,
        "reason": "backlog_cleanup",
        "follow_on": None,
        "message": f"Fix this first: {title}.",
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
