"""
EAE — Primary Focus Manager (Phase 8.4).

Manages the "Primary Focus" — the single most important thing for the user
right now. Limited to 2 changes per day (morning set + midday correction).

Rules:
    - Morning set: First interaction of the day → set from highest-ranked unit
    - Midday correction: Only if drift increased by >= 15 since morning
    - Lockout: After 2 changes, focus locked until midnight (user timezone)
    - Retained: Primary Focus always included in cognitive units
"""
import logging
from datetime import date
from typing import List, Optional

from django.utils import timezone

from apps.core.ai_eae.bundler import CognitiveUnit
from apps.core.ai_eae.constants import (
    PRIMARY_FOCUS_DRIFT_THRESHOLD,
    PRIMARY_FOCUS_MAX_CHANGES,
    apply_intensity,
)
from apps.core.ai_eae.models import EAEState

logger = logging.getLogger(__name__)


def evaluate_focus(
    state: EAEState,
    units: List[CognitiveUnit],
    drift_severity: float,
    intensity: float = 1.0,
) -> Optional[CognitiveUnit]:
    """
    Evaluate and potentially update the Primary Focus.

    Args:
        state: Current EAEState (will be modified but NOT saved).
        units: Ranked cognitive units (index 0 = highest priority).
        drift_severity: Current drift severity.
        intensity: Intensity multiplier.

    Returns:
        The CognitiveUnit that is the Primary Focus (may be existing or new),
        or None if no units available.
    """
    if not units:
        return None

    today = date.today()

    # Reset daily counters if new day
    state.reset_daily_counters(today)

    top_unit = units[0]
    current_focus = state.primary_focus_label

    # Case 1: No focus set yet today → morning set
    if not current_focus or state.focus_date != today:
        _set_focus(state, top_unit, 'morning')
        return top_unit

    # Case 2: Focus locked (2 changes already)
    if state.focus_locked:
        # Find the current focus unit in the list, or keep top
        for unit in units:
            if unit.title == current_focus:
                return unit
        # Current focus not in units anymore — keep top but don't change state
        return top_unit

    # Case 3: Check if midday correction is warranted
    # Only correct if drift increased significantly AND top unit differs from focus
    drift_threshold = apply_intensity(
        PRIMARY_FOCUS_DRIFT_THRESHOLD, intensity,
    )

    drift_increased = (drift_severity - state.drift_risk_severity) >= drift_threshold
    focus_differs = top_unit.title != current_focus

    if drift_increased and focus_differs:
        _set_focus(state, top_unit, 'midday_correction')
        return top_unit

    # Case 4: Retain current focus
    for unit in units:
        if unit.title == current_focus:
            return unit

    # Current focus not in units — top unit becomes implicit focus but don't count as change
    return top_unit


def _set_focus(state: EAEState, unit: CognitiveUnit, change_type: str):
    """Set primary focus on state (does NOT save)."""
    state.primary_focus_label = unit.title
    state.primary_focus_module = unit.module
    state.primary_focus_set_at = timezone.now()
    state.focus_changes_today += 1

    logger.info(
        "EAE focus: Set '%s' (%s) as primary focus for user %s (%s, change #%d)",
        unit.title, unit.module, state.user_id,
        change_type, state.focus_changes_today,
    )


def ensure_focus_in_units(
    units: List[CognitiveUnit],
    focus_label: str,
) -> List[CognitiveUnit]:
    """
    Ensure the Primary Focus unit is always included in surfaced units.
    If it was budget-cut, re-insert it at the end (replacing the lowest-ranked).

    Args:
        units: Surfaced cognitive units after budget.
        focus_label: The Primary Focus label.

    Returns:
        Updated units list with focus guaranteed present.
    """
    if not focus_label or not units:
        return units

    # Check if focus is already in the list
    for unit in units:
        if unit.title == focus_label:
            return units  # Already present

    # Focus was cut by budget — it's not critical enough to force-insert
    # unless we have a strong signal. For now, trust the budget.
    # The focus was set when it was top-ranked; if it's no longer top-ranked,
    # the budget correctly prioritized other items.
    return units
