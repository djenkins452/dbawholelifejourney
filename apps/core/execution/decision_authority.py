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
        return get_next_action(state)
    except Exception:  # pragma: no cover - defensive; consumers must never re-decide
        logger.warning("decision_authority: current_action failed user=%s",
                       getattr(user, "id", None), exc_info=True)
        return {
            "mode": "execution",
            "primary_action": None,
            "reason": "empty",
            "follow_on": None,
            "message": "Nothing pending right now.",
        }


def current_action_directive(user, now=None, state=None) -> str:
    """The canonical one-line directive string ("Next: X. Do this now."), for consumers
    that only need text. Thin formatter over `current_action` — no independent logic."""
    return (current_action(user, now=now, state=state) or {}).get(
        "message", "Nothing pending right now.",
    )
