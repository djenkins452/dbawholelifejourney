"""Single source of truth for selecting a user's active *mission*.

A "mission" is not a new domain or model — it is the headline foundational
LifeGoal, derived deterministically from existing rails (no ``is_mission``
field). Both the dashboard_v3 composer and the CoS goal-state builder consume
``select_active_mission_goal`` so the dashboard mission and Beth's mission are
ALWAYS the same goal. There is exactly one selection function; divergence is
structurally impossible.

Read-only. Reuses LifeGoal + GoalMilestone + GoalMomentumSnapshot. NEVER
triggers live momentum computation on the request path — momentum snapshots
are read from the nightly-populated GoalMomentumSnapshot table only.
"""
from __future__ import annotations


def _latest_momentum(goal):
    """Latest persisted momentum snapshot for a goal (read-only).

    Reads the nightly-computed GoalMomentumSnapshot. NEVER triggers live
    momentum_service computation on the request path.
    """
    return goal.momentum_snapshots.first()  # ordered -snapshot_date


def _rank_mission_goal(goal, today):
    """Deterministic sort key for picking 'the active mission'.

    Preference order (approved spec): has milestones → future target date →
    long-horizon (>=90 days), nearest first → highest momentum score → stable
    id fallback. Tuple sorts ascending; invert so "better" comes first.
    """
    target = goal.target_date
    if target and target > today:
        is_future = True
        days = (target - today).days
        beyond_90 = days >= 90
        days_rank = days
    else:
        is_future = False
        beyond_90 = False
        days_rank = float("inf")

    snap = _latest_momentum(goal)
    momentum_score = snap.momentum_score if snap else -1

    return (
        not goal.has_milestones,   # has milestones first
        not is_future,             # future-dated first
        not beyond_90,             # long-horizon first
        days_rank,                 # nearest qualifying date first
        -momentum_score,           # highest momentum first
        goal.id,                   # stable deterministic fallback
    )


def select_active_mission_goal(user):
    """Return the user's active mission goal, or None.

    Candidates = active + foundational LifeGoals. Deterministic ranking via
    ``_rank_mission_goal``. Returns the LifeGoal instance (not a display dict)
    so each consumer can format for its own surface from a single shared pick.
    """
    from apps.purpose.models import LifeGoal
    from apps.core.utils import get_user_now

    today = get_user_now(user).date()
    candidates = list(
        LifeGoal.objects.filter(
            user=user, status="active", is_foundational=True,
        )
    )
    if not candidates:
        return None
    return sorted(candidates, key=lambda g: _rank_mission_goal(g, today))[0]
