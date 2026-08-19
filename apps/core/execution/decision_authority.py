# ==============================================================================
# File: apps/core/execution/decision_authority.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: THE single deterministic producer of "what should I do right now?"
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-10
# ==============================================================================
"""
Execution Decision Authority — the ONE producer of the current recommended action.

There is exactly ONE place in WLJ that decides "what should Danny do right now?":
this module, over `build_execution_state` + `get_next_action`. Every surface — the
dashboard, proactive check-ins, OpenAI conversations, notifications, voice, widgets,
executive summaries — is a CONSUMER of `current_action(user)`. They may FORMAT the
decision differently (a card, a coaching sentence, a spoken line, a push title); they
MUST NOT re-derive it, re-order actions, or compute their own "next action".

    The dashboard must never disagree with a check-in.
    A notification must never disagree with OpenAI.
    The voice assistant must never disagree with the dashboard.

Because there is one function that decides, they cannot. This is enforced by
`apps/core/tests/test_execution_decision_authority_contract.py`, which fails CI if any
consumer grows its own prioritization/ordering/selection logic.

Prioritization, ordering, active-block gating, recovery filtering, and next-action
SELECTION happen upstream (in `build_execution_state` and `selectors.get_next_action`).
This module only composes them into the single public entrypoint and returns the
canonical decision as structured truth (never prose).
"""

import logging

logger = logging.getLogger(__name__)


def current_action(user, now=None, state=None) -> dict:
    """THE canonical answer to "what should I do right now?" — as structured truth.

    Args:
        user:  the user.
        now:   optional user-local datetime (defaults to the user's current time).
        state: optional pre-built execution state (from `build_execution_state`), so a
               caller that already built it — e.g. a v3 dashboard render — does not
               build it twice. When omitted it is built here.

    Returns the `get_next_action` payload (the ONE decision):
        {
            "mode": "execution",
            "primary_action": dict | None,   # the chosen action (None = nothing now)
            "reason": str,
            "follow_on": dict | None,         # soft next-after — NOT a second decision
            "message": str,                   # one-line canonical directive
        }

    Never raises: on any failure returns a safe empty decision so every consumer can
    render "nothing pending right now" rather than inventing its own answer.
    """
    try:
        from apps.core.execution.selectors import get_next_action
        if state is None:
            from apps.core.execution.execution_state import build_execution_state
            state = build_execution_state(user, now=now)
        return _stamp(get_next_action(state))
    except Exception:  # pragma: no cover - defensive; consumers must never re-decide
        logger.warning("decision_authority: current_action failed user=%s",
                       getattr(user, "id", None), exc_info=True)
        return _stamp({
            "mode": "execution",
            "primary_action": None,
            "reason": "empty",
            "follow_on": None,
            "message": "Nothing pending right now.",
        })


# RETRIEVAL AUTHORITY METADATA CONTRACT (platform adoption, Wave 2). Decision Authority
# is a CANONICAL authority — the single deterministic producer of "what to do now"
# (a second selector is CI-rejected), so it declares `canonical_authority`, not a
# projection. One composed decision per call → declared at the envelope root.
def _stamp(decision):
    from apps.core.truth import authority as A
    return A.stamp(decision, A.AuthorityDeclaration(
        authority="decision_authority.current_action", semantics=A.CURRENT,
        truth_category=A.CATEGORY_SUMMARY, classification=A.CANONICAL_AUTHORITY))


def _facts(action) -> dict:
    """Project an action to envelope-safe FACTS (no heavy objects, no judgment)."""
    return {
        "title": action.get("title"),
        # Accept either shape: prioritized actions carry `time_display`, raw execution
        # items carry `scheduled_time`. Same value, no recomputation.
        "time": action.get("time_display") or action.get("scheduled_time"),
        "time_status": action.get("time_status"),
        "urgency": action.get("urgency"),
        "importance": action.get("importance"),
        "source_type": action.get("source_type") or action.get("source"),
        # CANONICAL IDENTITY for every executable item in the envelope — not just the
        # current action (2026-08-18). Without this the model could only address the
        # ONE prioritized item by identity, so a visible-but-not-current item had to be
        # rediscovered by title. Identity here + the target-binding check in
        # execution_completion means naming any visible item is both possible and safe.
        "source_id": action.get("source_id", action.get("pk")),
        "can_complete": action.get("can_complete", False),
        # EXPLICIT CURRENT STATE (2026-08-18 temporal-truth incident). Read straight from
        # the canonical value `build_today_execution` already computed — no second
        # derivation, no extra query, no cache. Every executable item now states whether
        # it is done RIGHT NOW, so a later turn never has to remember (or misremember)
        # what an earlier turn claimed. Production 2026-08-18: an item was asserted
        # "already complete" five hours after a completion that never actually wrote.
        "completed_today": bool(action.get("completed_today", False)),
    }


def execution_facts(user, now=None, state=None) -> dict:
    """The full day's execution as deterministic FACTS for the envelope — the bucketed
    truth the retired renderer used to show as prose (what's done, overdue, coming up,
    later) plus the timing calculations and the active block. Facts only: titles, times,
    statuses, numbers. NO judgment ('behind'/'at risk') and NO prose — the model authors.

    Reuses `build_execution_state` (the single producer); pass `state` to avoid rebuilding.
    """
    try:
        if state is None:
            from apps.core.execution.execution_state import build_execution_state
            state = build_execution_state(user, now=now)
        # Completed reads the SINGLE reconciled bucket from build_execution_state — never
        # an independent completion query — so it can never disagree with overdue/pending.
        # Completed items now carry the SAME fact shape as every other bucket —
        # including canonical identity and `completed_today: true`. Previously they were
        # bare {title, time}, so a completed item had no identity and no explicit state,
        # and the model could only infer "is it done?" from which list it appeared in.
        completed = [_facts(i) for i in (state.get("completed_today") or [])]
        return _stamp_execution({
            "active_block": (state.get("active_block") or {}).get("name"),
            "timing": state.get("timing"),
            # The deterministic day execution phase — the ONE fact every surface reads
            # for "where is the user in today's execution?" (facts only, never a verdict).
            "execution_phase": state.get("execution_phase"),
            "overdue": [_facts(a) for a in (state.get("overdue_actions") or [])],
            "due_now": [_facts(a) for a in (state.get("now_actions") or [])],
            "coming_up": [_facts(a) for a in (state.get("next_actions") or [])],
            "later": [_facts(a) for a in (state.get("upcoming_actions") or [])],
            "completed": completed,
        })
    except Exception:  # pragma: no cover - defensive; envelope must never hard-fail
        logger.warning("execution_facts failed user=%s",
                       getattr(user, "id", None), exc_info=True)
        return _stamp_execution({"status": "pending"})


def _stamp_execution(facts):
    # Execution State is CANONICAL — the single producer is `build_execution_state`
    # (reused, never re-queried), so it declares `canonical_authority` at the root.
    from apps.core.truth import authority as A
    return A.stamp(facts, A.AuthorityDeclaration(
        authority="build_execution_state", semantics=A.CURRENT,
        truth_category=A.CATEGORY_SUMMARY, classification=A.CANONICAL_AUTHORITY))


def current_action_directive(user, now=None, state=None) -> str:
    """The canonical one-line directive string ("Next: X. Do this now."), for consumers
    that only need text. Thin formatter over `current_action` — no independent logic."""
    return (current_action(user, now=now, state=state) or {}).get(
        "message", "Nothing pending right now.",
    )
