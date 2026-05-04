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

    Pure pick from pre-filtered state["eligible_actions"]. No priority
    computation, no re-ranking, no DB, no LLM. Recovery filtering, block
    collapse suppression, and recovery-mode bucket reordering all
    happened upstream in build_execution_state.

    Output is EXACTLY one line:
        "Next: [Action]. Do this now."     — current overdue/now action
        "Next: [Action]."                  — forward-only context
        "Nothing pending right now."       — empty pool
    """
    # eligible_actions is the block-filtered subset upstream. An empty
    # list means "nothing in the current window" — do NOT fall back to
    # the unfiltered action list for the PRIMARY pool (it would
    # re-introduce stale items as "Do this now").
    if "eligible_actions" in state:
        eligible = state.get("eligible_actions") or []
    else:
        eligible = state.get("actions") or []

    primary_pool = [
        a for a in eligible
        if a.get('urgency') in ('overdue', 'now')
    ]
    if primary_pool:
        top = primary_pool[0]
        title = top.get('title', '')
        return {
            "mode": "execution",
            "primary_action": top,
            "reason": "current",
            "follow_on": None,
            "message": f"Next: {title}. Do this now.",
        }

    # Forward hint may pull from the FULL list — block-eligible upcoming
    # first, then any upcoming. The hint is informational, not a "do now"
    # instruction, so showing a future item from the next block is fine.
    forward_eligible = [
        a for a in eligible
        if a.get('urgency') in ('next', 'upcoming')
    ]
    if forward_eligible:
        f = forward_eligible[0]
        title = f.get('title', '')
        return {
            "mode": "execution",
            "primary_action": None,
            "reason": "upcoming",
            "follow_on": f,
            "message": f"Next: {title}.",
        }

    all_actions = state.get("actions") or []
    forward_any = [
        a for a in all_actions
        if a.get('urgency') in ('next', 'upcoming')
    ]
    if forward_any:
        f = forward_any[0]
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

    Pure pick from pre-filtered state["at_risk_actions"]. The horizon
    rule (60–90 min standard, 4h with dependency, suppress non-dependency
    future risk when overdue exists) is enforced upstream in
    compute_at_risk(). Foundational missed items take precedence,
    including ones that are no longer recoverable but still influence
    the day narrative.

    Output is EXACTLY one line:
        "Biggest risk: [Issue]. Fix this next."
    or:
        "No risks right now."
    """
    at_risk = state.get("at_risk_actions") or []

    # Foundational expired items also count as risk signals even though
    # they cannot be acted on — they describe what's already lost. We
    # surface them when no actionable risk exists.
    expired_items = state.get("expired_items") or []
    foundational_expired = [
        i for i in expired_items if i.get('is_foundational')
    ]

    if not at_risk and not foundational_expired:
        return _empty_payload("risk", "No risks right now.")

    def _domain_weight(a):
        src = (a.get('source') or a.get('domain') or '').lower()
        return _DOMAIN_RISK_WEIGHT.get(src, 0)

    def _risk_key(a):
        foundational_rank = 0 if a.get('is_foundational') else 1
        time_min = _action_time_to_minutes(a)
        weight = -_domain_weight(a)
        return (foundational_rank, time_min, weight, a.get('title', ''))

    if at_risk:
        pool = list(at_risk)
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

    # Fall through to foundational expired — read from items, not actions.
    foundational_expired.sort(key=lambda i: (
        i.get('scheduled_time') or '23:59',
        i.get('title') or '',
    ))
    top_item = foundational_expired[0]
    title = top_item.get('title', '')
    return {
        "mode": "risk",
        "primary_action": None,
        "reason": "foundational_missed",
        "follow_on": None,
        "message": f"Biggest risk: {title} missed. Reset for the rest of today.",
    }


# ══════════════════════════════════════════════════════════════════════
# FIX MODE — "What should I fix first?"
# ══════════════════════════════════════════════════════════════════════

def get_fix_priority(state: dict) -> dict:
    """
    FIX MODE selector — STRICT MODE ISOLATION contract.

    Pure pick from pre-filtered state. Recovery-mode awareness:
      - In RECOVERY/STABILIZE, prefer (a) a reset action if available,
        (b) the highest-leverage collapsed-block summary.
      - Otherwise pick the overdue action whose completion unblocks
        the most dependent pending tasks.

    Output is EXACTLY one line:
        "Fix this first: [Action]."
    or:
        "Nothing to fix."
    """
    # Fix mode reads the FULL action list (not block-filtered) — fix is
    # about clearing accumulated disorder, not just the active block.
    actions = state.get("actions") or []
    overdue = state.get("overdue_actions") or []
    recovery = state.get("recovery_state") or {}
    mode = recovery.get("mode", "NORMAL")
    collapsed_blocks = state.get("collapsed_blocks") or []

    # Recovery / stabilize: prefer the reset lever first. The bucket
    # selection upstream already pushed reset actions to the front.
    if mode in ("RECOVERY", "STABILIZE"):
        for a in actions:
            if a.get('is_reset_action'):
                title = a.get('title', '')
                return {
                    "mode": "fix",
                    "primary_action": a,
                    "reason": "reset",
                    "follow_on": None,
                    "message": f"Fix this first: {title}.",
                }
        # No reset action — surface a recover_partially block summary
        # if one exists (highest-leverage missed group).
        partial = [
            c for c in collapsed_blocks
            if c.get('strategy') == 'recover_partially'
        ]
        if partial:
            top_block = sorted(
                partial, key=lambda c: -c.get('item_count', 0)
            )[0]
            title = top_block.get('parent_title', 'Missed block')
            return {
                "mode": "fix",
                "primary_action": None,
                "reason": "block_recover",
                "follow_on": None,
                "message": f"Fix this first: {title}.",
            }

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
