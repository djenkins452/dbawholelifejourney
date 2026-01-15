"""
Cycle Phase Calculator Service

Calculates the current menstrual cycle phase based on cycle day and user settings.
Adjusts phase lengths proportionally for users with non-standard cycle lengths.

Phases:
- Menstrual: Days 1-5 (bleeding)
- Follicular: Days 6-13 (pre-ovulation)
- Ovulation: Days 14-16 (fertile window peak)
- Luteal: Days 17-28 (post-ovulation)

Usage:
    from apps.health.services.cycle_phase import get_current_phase

    # Get current phase for user
    phase_info = get_current_phase(user)
    if phase_info:
        print(f"Phase: {phase_info['name']}, Day {phase_info['day_in_phase']}")
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional

from django.utils import timezone

from ..models import Cycle, CycleSettings


# Standard 28-day cycle phase definitions
STANDARD_CYCLE_LENGTH = 28
STANDARD_PHASES = [
    {"name": "menstrual", "start_day": 1, "end_day": 5, "duration": 5},
    {"name": "follicular", "start_day": 6, "end_day": 13, "duration": 8},
    {"name": "ovulation", "start_day": 14, "end_day": 16, "duration": 3},
    {"name": "luteal", "start_day": 17, "end_day": 28, "duration": 12},
]

# Phase display information
PHASE_INFO = {
    "menstrual": {
        "display_name": "Menstrual",
        "description": "Period bleeding phase",
        "color": "#E53935",  # Red
        "color_name": "red",
    },
    "follicular": {
        "display_name": "Follicular",
        "description": "Pre-ovulation phase",
        "color": "#FFB300",  # Amber/Orange
        "color_name": "orange",
    },
    "ovulation": {
        "display_name": "Ovulation",
        "description": "Peak fertility window",
        "color": "#43A047",  # Green
        "color_name": "green",
    },
    "luteal": {
        "display_name": "Luteal",
        "description": "Post-ovulation phase",
        "color": "#1E88E5",  # Blue
        "color_name": "blue",
    },
}


@dataclass
class PhaseResult:
    """Result of phase calculation."""

    name: str
    display_name: str
    description: str
    day_in_phase: int
    total_phase_days: int
    cycle_day: int
    color: str
    color_name: str


def get_current_phase(
    user, reference_date: Optional[date] = None
) -> Optional[dict]:
    """
    Calculate the current cycle phase for a user.

    Args:
        user: The User instance to calculate phase for
        reference_date: Date to calculate phase for (defaults to today)

    Returns:
        Dictionary with phase information or None if not in active cycle.
        Keys:
        - name: Phase key (menstrual, follicular, ovulation, luteal)
        - display_name: Human-readable phase name
        - description: Brief phase description
        - day_in_phase: Current day within the phase (1-based)
        - total_phase_days: Total days in this phase
        - cycle_day: Current day in overall cycle (1-based)
        - color: Hex color code for the phase
        - color_name: Color name for CSS classes
    """
    if reference_date is None:
        reference_date = timezone.now().date()

    # Get user's cycle settings for custom cycle length
    try:
        settings = CycleSettings.objects.get(user=user)
        if not settings.is_enabled:
            return None
        user_cycle_length = settings.average_cycle_length
    except CycleSettings.DoesNotExist:
        return None

    # Get the current active cycle
    current_cycle = Cycle.objects.filter(
        user=user,
        end_date__isnull=True,
        start_date__lte=reference_date,
    ).first()

    if not current_cycle:
        return None

    # Calculate current day in cycle (1-based)
    cycle_day = (reference_date - current_cycle.start_date).days + 1

    # Don't return phase if cycle day exceeds user's average cycle length + buffer
    # (cycle should have ended by now)
    if cycle_day > user_cycle_length + 7:
        return None

    # Calculate adjusted phase boundaries based on user's cycle length
    adjusted_phases = _calculate_adjusted_phases(user_cycle_length)

    # Find which phase the current day falls into
    for phase in adjusted_phases:
        if phase["start_day"] <= cycle_day <= phase["end_day"]:
            phase_info = PHASE_INFO[phase["name"]]
            day_in_phase = cycle_day - phase["start_day"] + 1

            return {
                "name": phase["name"],
                "display_name": phase_info["display_name"],
                "description": phase_info["description"],
                "day_in_phase": day_in_phase,
                "total_phase_days": phase["duration"],
                "cycle_day": cycle_day,
                "color": phase_info["color"],
                "color_name": phase_info["color_name"],
            }

    # If cycle day exceeds all phases, user is in extended luteal
    # (can happen near end of cycle)
    luteal_info = PHASE_INFO["luteal"]
    last_phase = adjusted_phases[-1]
    day_in_phase = cycle_day - last_phase["start_day"] + 1

    return {
        "name": "luteal",
        "display_name": luteal_info["display_name"],
        "description": luteal_info["description"],
        "day_in_phase": day_in_phase,
        "total_phase_days": last_phase["duration"],
        "cycle_day": cycle_day,
        "color": luteal_info["color"],
        "color_name": luteal_info["color_name"],
    }


def _calculate_adjusted_phases(cycle_length: int) -> list[dict]:
    """
    Calculate phase boundaries adjusted for user's cycle length.

    Proportionally adjusts standard 28-day phases for different cycle lengths.

    Args:
        cycle_length: User's average cycle length in days

    Returns:
        List of adjusted phase dictionaries with start_day, end_day, duration
    """
    if cycle_length == STANDARD_CYCLE_LENGTH:
        return STANDARD_PHASES

    # Calculate scaling factor
    scale = cycle_length / STANDARD_CYCLE_LENGTH

    adjusted = []
    current_day = 1

    for i, phase in enumerate(STANDARD_PHASES):
        # Calculate proportionally adjusted duration
        if i == len(STANDARD_PHASES) - 1:
            # Last phase (luteal) takes remaining days
            duration = cycle_length - current_day + 1
        else:
            # Scale other phases proportionally, minimum 1 day
            duration = max(1, round(phase["duration"] * scale))

        adjusted.append({
            "name": phase["name"],
            "start_day": current_day,
            "end_day": current_day + duration - 1,
            "duration": duration,
        })

        current_day += duration

    return adjusted


def get_phase_by_day(cycle_day: int, cycle_length: int = STANDARD_CYCLE_LENGTH) -> dict:
    """
    Get phase information for a specific cycle day.

    Useful for calendar views and phase predictions.

    Args:
        cycle_day: Day number in cycle (1-based)
        cycle_length: Total cycle length (defaults to 28)

    Returns:
        Phase information dictionary
    """
    adjusted_phases = _calculate_adjusted_phases(cycle_length)

    for phase in adjusted_phases:
        if phase["start_day"] <= cycle_day <= phase["end_day"]:
            phase_info = PHASE_INFO[phase["name"]]
            return {
                "name": phase["name"],
                "display_name": phase_info["display_name"],
                "description": phase_info["description"],
                "day_in_phase": cycle_day - phase["start_day"] + 1,
                "total_phase_days": phase["duration"],
                "color": phase_info["color"],
                "color_name": phase_info["color_name"],
            }

    # Beyond end of cycle
    return None


def get_all_phases(cycle_length: int = STANDARD_CYCLE_LENGTH) -> list[dict]:
    """
    Get all phases with their boundaries for a given cycle length.

    Useful for displaying phase overview or calendar legends.

    Args:
        cycle_length: Total cycle length (defaults to 28)

    Returns:
        List of all phases with boundaries and info
    """
    adjusted_phases = _calculate_adjusted_phases(cycle_length)

    result = []
    for phase in adjusted_phases:
        phase_info = PHASE_INFO[phase["name"]]
        result.append({
            "name": phase["name"],
            "display_name": phase_info["display_name"],
            "description": phase_info["description"],
            "start_day": phase["start_day"],
            "end_day": phase["end_day"],
            "duration": phase["duration"],
            "color": phase_info["color"],
            "color_name": phase_info["color_name"],
        })

    return result
