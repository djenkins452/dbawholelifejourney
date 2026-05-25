"""
SAE Journey state builder.

Pure function: takes a user, returns the structured journey state block that
the faith SAE state builder will merge under `faith.journey`.

Read-only. No DB writes. No heavy analytics. All fields cheap to compute.

Shape (per spec §4):
{
    "active": bool,
    "journey_path_slug": str | None,
    "journey_path_name": str | None,
    "current_arc_slug": str | None,
    "current_arc_name": str | None,
    "current_arc_day": int | None,
    "current_arc_total_days": int | None,
    "preferred_difficulty": str | None,
    "days_since_last_read": int | None,
    "momentum_score": float,                    # internal-only — never displayed
    "application_committed_this_week": int,
}

momentum_score policy:
    - 1.0 when last_engaged_at < 3 days ago
    - Linear decay from 1.0 at day 3 to 0.0 at day 21
    - Internal observability only. Never user-facing. Never Beth-recited.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.utils import timezone

from apps.faith.journey.models import UserJourney, UserJourneyDayProgress


_EMPTY_BLOCK: dict[str, Any] = {
    "active": False,
    "journey_path_slug": None,
    "journey_path_name": None,
    "current_arc_slug": None,
    "current_arc_name": None,
    "current_arc_day": None,
    "current_arc_total_days": None,
    "preferred_difficulty": None,
    "days_since_last_read": None,
    "momentum_score": 1.0,
    "application_committed_this_week": 0,
}


def compute_momentum_score(days_since_last_read: int | None) -> float:
    """Decay from 1.0 (≤2 days) linearly to 0.0 (≥21 days).

    Internal observability only. Never surfaced to users or to Beth.
    """
    if days_since_last_read is None:
        return 1.0
    if days_since_last_read < 3:
        return 1.0
    if days_since_last_read >= 21:
        return 0.0
    # Linear decay between day 3 and day 21
    span = 21 - 3
    progress = (days_since_last_read - 3) / span
    return round(max(0.0, 1.0 - progress), 3)


def build_journey_state(user) -> dict[str, Any]:
    """Return the canonical journey state block for SAE.

    Always returns a dict (never None). When the user has no active journey,
    returns the empty block — keeps Beth's context shape stable.
    """
    uj = (
        UserJourney.objects
        .filter(user=user, journey_status="active")
        .select_related("journey_path", "current_arc")
        .first()
    )
    if uj is None:
        return dict(_EMPTY_BLOCK)

    now = timezone.now()
    days_since_last_read: int | None = None
    if uj.last_engaged_at:
        days_since_last_read = (now.date() - uj.last_engaged_at.date()).days

    application_committed_this_week = (
        UserJourneyDayProgress.objects
        .filter(
            user=user,
            user_journey=uj,
            application_committed=True,
            completed_at__gte=now - timedelta(days=7),
        )
        .count()
    )

    arc = uj.current_arc
    return {
        "active": True,
        "journey_path_slug": uj.journey_path.slug,
        "journey_path_name": uj.journey_path.name,
        "current_arc_slug": arc.slug if arc else None,
        "current_arc_name": arc.name if arc else None,
        "current_arc_day": uj.current_day_number,
        "current_arc_total_days": arc.estimated_days if arc else None,
        "preferred_difficulty": uj.preferred_difficulty,
        "days_since_last_read": days_since_last_read,
        "momentum_score": compute_momentum_score(days_since_last_read),
        "application_committed_this_week": application_committed_this_week,
    }
