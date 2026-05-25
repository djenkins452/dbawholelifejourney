"""
Faith dashboard card data for the Journey.

A single, quiet helper that returns the data the modest Faith-page card
needs — or None when there is nothing to show.

Important UX boundaries (Phase 1, locked):
    - This card appears on the Faith dashboard ONLY.
    - It does NOT surface on the homepage, global dashboard, "Do This Now",
      CoS prioritization, or any cross-domain prioritization surface.
    - The card uses NO urgency language, NO streak framing, NO guilt.
    - It is opt-in (only renders when the user has an active journey).
"""

from __future__ import annotations

from typing import Any, Optional

from apps.faith.journey.services import get_active_journey, get_current_day


def get_dashboard_card_data(user) -> Optional[dict[str, Any]]:
    """Return the data the Faith-dashboard journey card needs, or None.

    Returns None when:
      - User is not authenticated
      - User has no active journey
      - User's active journey has no current day (authored content gap)
    """
    if not getattr(user, "is_authenticated", False):
        return None
    uj = get_active_journey(user)
    if uj is None:
        return None
    day = get_current_day(uj)
    if day is None:
        return None
    arc = day.arc
    return {
        "journey_name": uj.journey_path.name,
        "arc_name": arc.name,
        "day_number": day.day_number,
        "total_days": arc.estimated_days,
        "focus": day.key_insight,         # one-sentence takeaway
        "scripture_refs": day.scripture_refs,
    }
