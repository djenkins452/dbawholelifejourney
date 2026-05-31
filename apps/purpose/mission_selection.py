"""Single source of truth for selecting a user's active *mission*.

A "mission" is the goal the user has EXPLICITLY chosen as their featured
Mission (``LifeGoal.is_primary_mission``). It is user intent, never derived:
there is no fallback to foundational goals, nearest deadline, momentum, or
first-active. If the user has not selected a Primary Mission, there is no
mission — the dashboard card hides and the Chief of Staff stays silent on it.

Both the dashboard_v3 composer and the CoS goal-state builder consume
``select_active_mission_goal`` so the dashboard mission and Beth's mission are
ALWAYS the same goal. There is exactly one selection function; divergence is
structurally impossible. At most one active Primary Mission exists per user
(enforced by a partial unique constraint on LifeGoal), so ``.first()`` is the
single deterministic pick.

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


def select_active_mission_goal(user):
    """Return the user's active Primary Mission goal, or None.

    Selection is explicit: ``is_primary_mission=True`` AND ``status='active'``.
    No derived fallback. Returns the LifeGoal instance (not a display dict) so
    each consumer formats for its own surface from a single shared pick.
    """
    from apps.purpose.models import LifeGoal

    return LifeGoal.objects.filter(
        user=user, status="active", is_primary_mission=True,
    ).first()
