"""
Physical Intelligence V2 — Outcome Validation.

Path: apps/health/services/outcome_validation.py
Purpose: Determine whether the user's current protocol is producing
         the expected physical results.

Architecture:
    - Pure function: reads BodyCompositionTrend + TransformationProtocol
    - No DB queries (all inputs passed in)
    - Returns outcome_status and goal trajectory
    - Called by compute_physical_decision(), never on request path

Copyright: (c) Whole Life Journey. All rights reserved.
"""

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)


def validate_outcome(user, body_comp_trend, protocol_type):
    """Determine whether the user's protocol is producing expected results.

    Args:
        user: Django User instance (for protocol lookup if needed)
        body_comp_trend: dict from compute_body_composition_trend()
        protocol_type: str — 'cut' | 'bulk' | 'recomposition' | 'maintenance' | None

    Returns:
        dict with:
            outcome_status: 'working' | 'partial' | 'not_working' | 'unknown'
            outcome_evidence: list of evidence strings
            goal_trajectory: 'ahead' | 'on_pace' | 'behind' | 'off_track' | None
            trajectory_detail: str or None
    """
    try:
        return _validate(user, body_comp_trend, protocol_type)
    except Exception:
        logger.error(
            "Outcome validation failed for user %s", user.pk, exc_info=True
        )
        return {
            "outcome_status": "unknown",
            "outcome_evidence": [],
            "goal_trajectory": None,
            "trajectory_detail": None,
        }


def _validate(user, trend, protocol_type):
    """Core validation logic."""
    if not protocol_type:
        return {
            "outcome_status": "unknown",
            "outcome_evidence": [],
            "goal_trajectory": None,
            "trajectory_detail": None,
        }

    # Check if protocol is too new for assessment
    protocol = _get_active_protocol(user)
    if protocol:
        days_in = (date.today() - protocol.start_date).days
        if days_in < 14:
            return {
                "outcome_status": "unknown",
                "outcome_evidence": [],
                "goal_trajectory": None,
                "trajectory_detail": (
                    f"Day {days_in} of protocol. Need 14+ days to assess. "
                    f"Focus on compliance, not results."
                ),
            }

    # Validate by protocol type
    validators = {
        "cut": _validate_cut,
        "bulk": _validate_bulk,
        "recomposition": _validate_recomp,
        "maintenance": _validate_maintenance,
    }
    validate_fn = validators.get(protocol_type, _validate_maintenance)
    outcome_status, outcome_evidence = validate_fn(trend)

    # Compute trajectory
    trajectory, trajectory_detail = _compute_trajectory(user, protocol, trend)

    return {
        "outcome_status": outcome_status,
        "outcome_evidence": outcome_evidence,
        "goal_trajectory": trajectory,
        "trajectory_detail": trajectory_detail,
    }


# =========================================================================
# Protocol-Specific Validators
# =========================================================================


def _validate_cut(trend):
    """Is the cut working?

    Working: fat loss confirmed, muscle not lost
    Partial: fat loss but with muscle loss, or likely but not confirmed
    Not working: spinning wheels or regression
    """
    verdict = trend.get("verdict", "no_data")
    fat = trend.get("fat_loss_status", "not_confirmed")
    muscle = trend.get("muscle_gain_status", "unclear")

    evidence = list(trend.get("fat_loss_evidence", []))
    evidence.extend(trend.get("muscle_evidence", []))

    if verdict in ("effective_cut", "recomposition"):
        return "working", evidence
    elif verdict == "cut_with_muscle_loss":
        return "partial", evidence
    elif fat == "likely":
        return "partial", evidence
    elif verdict in ("spinning_wheels", "regression"):
        return "not_working", evidence
    else:
        return "unknown", evidence


def _validate_bulk(trend):
    """Is the bulk working?

    Working: gaining muscle (weight up + strength/measurements up)
    Partial: weight up but muscle unclear
    Not working: no gains or regression
    """
    verdict = trend.get("verdict", "no_data")
    muscle = trend.get("muscle_gain_status", "unclear")

    evidence = list(trend.get("muscle_evidence", []))
    evidence.extend(trend.get("fat_loss_evidence", []))

    if muscle == "likely":
        return "working", evidence
    elif verdict in ("effective_bulk", "recomposition"):
        return "working", evidence
    elif muscle == "unclear" and trend.get("weight_trend", 0) > 0:
        return "partial", evidence
    elif verdict in ("spinning_wheels", "regression"):
        return "not_working", evidence
    else:
        return "unknown", evidence


def _validate_recomp(trend):
    """Is the recomp working?

    Working: recomposition detected (fat down + muscle up)
    Partial: one dimension working, other unclear
    Not working: spinning wheels
    """
    verdict = trend.get("verdict", "no_data")
    fat = trend.get("fat_loss_status", "not_confirmed")
    muscle = trend.get("muscle_gain_status", "unclear")
    recomp = trend.get("recomposition_status", False)

    evidence = list(trend.get("fat_loss_evidence", []))
    evidence.extend(trend.get("muscle_evidence", []))

    if recomp or verdict == "recomposition":
        return "working", evidence
    elif fat in ("confirmed", "likely") and muscle != "unlikely":
        return "partial", evidence
    elif muscle == "likely" and fat != "reversed":
        return "partial", evidence
    elif verdict == "spinning_wheels":
        return "not_working", evidence
    else:
        return "unknown", evidence


def _validate_maintenance(trend):
    """Is maintenance holding?

    Working: no major changes (spinning_wheels IS success here)
    Not working: regression or reversed fat loss
    """
    verdict = trend.get("verdict", "no_data")
    fat = trend.get("fat_loss_status", "not_confirmed")
    muscle = trend.get("muscle_gain_status", "unclear")

    evidence = list(trend.get("fat_loss_evidence", []))
    evidence.extend(trend.get("muscle_evidence", []))

    # Spinning wheels during maintenance = success
    if verdict == "spinning_wheels":
        return "working", ["stable"]
    elif fat == "reversed" or muscle == "unlikely":
        return "not_working", evidence
    else:
        return "working", ["stable"]


# =========================================================================
# Goal Trajectory
# =========================================================================


def _compute_trajectory(user, protocol, trend):
    """Project whether user is on pace for their goal."""
    if not protocol:
        return None, None

    if not protocol.goal_weight or not protocol.target_end_date:
        return None, None

    # Get current weight from trend data
    weight_rate = trend.get("fat_loss_rate_lbs_per_week")
    if weight_rate is None:
        return None, "Insufficient rate data to project pace."

    current_weight = None
    try:
        from apps.health.models import WeightEntry

        latest = (
            WeightEntry.objects.filter(user=user)
            .order_by("-recorded_at")
            .values_list("value", flat=True)
            .first()
        )
        if latest:
            current_weight = float(latest)
    except Exception:
        pass

    if not current_weight:
        return None, None

    goal_weight = float(protocol.goal_weight)
    remaining = abs(current_weight - goal_weight)
    days_left = (protocol.target_end_date - date.today()).days

    if days_left <= 0:
        return "off_track", (
            f"Target date passed. Current: {current_weight:.1f}, "
            f"Goal: {goal_weight:.0f}."
        )

    weeks_left = days_left / 7
    weekly_rate = abs(weight_rate) if weight_rate else 0

    if weekly_rate < 0.1:
        return "behind", f"Rate too slow to project. {weeks_left:.0f} weeks remain."

    weeks_needed = remaining / weekly_rate

    if weeks_needed <= weeks_left * 0.8:
        return "ahead", (
            f"~{weeks_needed:.0f} weeks to goal ({weeks_left:.0f} available)."
        )
    elif weeks_needed <= weeks_left * 1.1:
        return "on_pace", (
            f"On track — ~{weeks_needed:.0f} weeks at current rate."
        )
    elif weeks_needed <= weeks_left * 1.5:
        return "behind", (
            f"Need ~{weeks_needed:.0f} weeks but only "
            f"{weeks_left:.0f} remain."
        )
    else:
        return "off_track", (
            f"~{weeks_needed:.0f} weeks needed, "
            f"{weeks_left:.0f} available."
        )


# =========================================================================
# Helpers
# =========================================================================


def _get_active_protocol(user):
    """Get the user's active TransformationProtocol."""
    try:
        from apps.health.models import TransformationProtocol

        return (
            TransformationProtocol.objects.filter(user=user, is_active=True)
            .order_by("-start_date")
            .first()
        )
    except Exception:
        return None
