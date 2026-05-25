"""
CoS journey context block — passive context for Beth.

Pure function: takes a user, returns the journey context block that the faith
CoS context builder will merge under `faith_summary.journey` (or a top-level
`journey` key, depending on integration).

CRITICAL BOUNDARY (Phase 1):
    - Beth is SILENT on the journey reading surface.
    - This context block is **passive awareness only** — Beth may reference
      it factually when invoked elsewhere ("you're on Day 6 of arc 1"), but
      MUST NOT proactively initiate journey conversation.
    - `momentum_score` is internal-only — Beth must not recite it.

The block is intentionally smaller than the SAE state block: it includes only
fields appropriate for Beth's narrative reference. `momentum_score` and
`application_committed_this_week` are deliberately omitted from Beth-facing
context (they're for internal observability dashboards, not Beth).
"""

from __future__ import annotations

from typing import Any

from apps.faith.journey.state import build_journey_state


def build_journey_context_block(user) -> dict[str, Any]:
    """Return the journey context block for CoS.

    Returns `{"active": False}` when the user has no active journey.
    Beth's prompt should branch on `active` before referencing other fields.
    """
    state = build_journey_state(user)
    if not state["active"]:
        return {"active": False}

    return {
        "active": True,
        "journey_name": state["journey_path_name"],
        "arc_name": state["current_arc_name"],
        "arc_day": state["current_arc_day"],
        "arc_total_days": state["current_arc_total_days"],
        "preferred_difficulty": state["preferred_difficulty"],
        "days_since_last_read": state["days_since_last_read"],
        # NOTE: momentum_score and application_committed_this_week
        # deliberately omitted. Internal-only. Beth never sees them.
    }
