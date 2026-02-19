"""
Whole Life Journey - Human Translation Layer

Project: Whole Life Journey
Path: apps/core/blueprint/human_language.py
Purpose: Translate raw engine metrics into natural human language

Description:
    Converts alignment%, drift%, capacity%, block counts, and
    weekly pressure into conversational language suitable for
    primary UI. Raw metrics are only shown in collapsible
    "System Detail" panels or E3 explainability mode.

    This module is the SOLE authority for metric→language
    translation. No other module should render raw percentages
    in primary user-facing UI.

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Alignment → Human Language
# ---------------------------------------------------------------------------

def translate_alignment(score):
    """
    Translate alignment score (0-100) to human language.

    Returns: (short_label, description)
    """
    if score is None:
        return ('Calibrating', 'System is establishing your baseline.')
    score = int(score)
    if score >= 90:
        return ('Locked in', 'Your week is running exactly on plan.')
    elif score >= 80:
        return ('Steady', "You're steady this week.")
    elif score >= 65:
        return ('Drifting slightly', 'A few things are pulling off course.')
    elif score >= 50:
        return ('Under pressure', 'Several areas need attention.')
    else:
        return ('Off course', 'Significant drift from your plan.')


# ---------------------------------------------------------------------------
# Drift Risk → Human Language
# ---------------------------------------------------------------------------

def translate_drift_risk(pct):
    """
    Translate drift risk percentage (0-100) to human language.

    Returns: (short_label, description)
    """
    if pct is None:
        return ('Unknown', 'Not enough data yet.')
    pct = int(pct)
    if pct < 15:
        return ('Clear', 'No pressure building.')
    elif pct < 25:
        return ('Low risk', 'Slight background pressure, nothing urgent.')
    elif pct < 40:
        return ('Moderate', 'Some compression building — worth watching.')
    elif pct < 60:
        return ('Elevated', 'Pressure building. Consider protecting margin.')
    elif pct < 80:
        return ('High', 'Schedule is under real pressure.')
    else:
        return ('Critical', 'Overload risk. Your top priorities need protection.')


# ---------------------------------------------------------------------------
# Capacity → Human Language
# ---------------------------------------------------------------------------

def translate_capacity(pct):
    """
    Translate capacity percentage (0-100) to human language.

    Returns: (short_label, description)
    """
    if pct is None:
        return ('No plan', 'No architecture for today yet.')
    pct = int(pct)
    if pct < 20:
        return ('Light day', 'Wide open — space available.')
    elif pct < 40:
        return ('Easy pace', 'Comfortable amount scheduled.')
    elif pct < 60:
        return ('Moderate', 'Balanced schedule.')
    elif pct < 80:
        return ('Full day', 'Solid schedule. Not much margin.')
    elif pct < 90:
        return ('Heavy', 'Schedule is dense. Protect recovery time.')
    else:
        return ('Packed', 'Near capacity. Any addition creates pressure.')


# ---------------------------------------------------------------------------
# Block Progress → Human Language
# ---------------------------------------------------------------------------

def translate_progress(completed, total):
    """
    Translate block progress to human language.

    Returns: (short_label, description)
    """
    if total is None or total == 0:
        return ('No blocks', 'No scheduled blocks today.')
    completed = completed or 0
    remaining = total - completed
    pct = round(completed / total * 100)

    if pct == 100:
        return ('Complete', 'Everything done for today.')
    elif pct >= 75:
        return ('Almost there', f'{remaining} left to finish today.')
    elif pct >= 50:
        return ('Half done', f'{remaining} items remaining.')
    elif pct > 0:
        return ('Getting started', f'{remaining} of {total} still ahead.')
    else:
        return ('Day ahead', f'{total} items on the schedule today.')


# ---------------------------------------------------------------------------
# Weekly Pressure → Human Language
# ---------------------------------------------------------------------------

def translate_weekly_pressure(pressure_data):
    """
    Translate weekly pressure data into a one-line summary.

    Args:
        pressure_data: dict with keys like:
            - day_loads: list of (day_name, capacity_pct) tuples
            - avg_load: float
            - peak_day: str
            - peak_load: float
            - light_days: list of str
            - heavy_days: list of str
            - opportunity_windows: list of dicts

    Returns: str — one-line summary for primary UI
    """
    if not pressure_data:
        return 'Week not yet calculated.'

    avg = pressure_data.get('avg_load', 0)
    heavy_days = pressure_data.get('heavy_days', [])
    light_days = pressure_data.get('light_days', [])
    peak_day = pressure_data.get('peak_day', '')
    peak_load = pressure_data.get('peak_load', 0)

    parts = []

    # Overall assessment
    if avg < 30:
        parts.append('Light week overall.')
    elif avg < 50:
        parts.append('Moderate week.')
    elif avg < 70:
        parts.append('Full week ahead.')
    else:
        parts.append('Heavy week.')

    # Peak pressure
    if peak_day and peak_load >= 60:
        time_hint = ''
        peak_detail = pressure_data.get('peak_detail', '')
        if peak_detail:
            time_hint = f' {peak_detail}'
        parts.append(f'{peak_day} heavy{time_hint}.')

    # Light days / opportunities
    if light_days:
        if len(light_days) == 1:
            parts.append(f'{light_days[0]} is open.')
        elif len(light_days) <= 3:
            parts.append(f'{", ".join(light_days[:-1])} and {light_days[-1]} are open.')

    # Overload warning
    if len(heavy_days) >= 3:
        parts.append('Consider shifting one block.')

    return ' '.join(parts)


def translate_opportunity_window(window):
    """
    Translate an opportunity window dict into human language.

    Args:
        window: dict with keys: day_name, start_time, end_time, duration_hours

    Returns: str
    """
    if not window:
        return ''
    day = window.get('day_name', '')
    start = window.get('start_time', '')
    end = window.get('end_time', '')
    hours = window.get('duration_hours', 0)

    if hours >= 3:
        return f'{day} {start}–{end} is open. Good window for activity.'
    elif hours >= 2:
        return f'{day} has {hours:.0f} free hours ({start}–{end}).'
    else:
        return f'{day} {start}–{end} has some space.'


# ---------------------------------------------------------------------------
# Day Assessment → Human Language
# ---------------------------------------------------------------------------

def translate_day_assessment(capacity_pct, drift_risk_pct, tier1_count,
                             completed, total):
    """
    Build a one-line executive summary for today.

    Returns: str
    """
    parts = []

    # Today's character
    cap_label, _ = translate_capacity(capacity_pct)
    parts.append(f'Today is {cap_label.lower()}.')

    # Tier-1 protections
    if tier1_count and tier1_count > 0:
        parts.append(
            f'{tier1_count} priorit{"ies" if tier1_count > 1 else "y"} locked in.'
        )

    # Drift risk if notable
    if drift_risk_pct and drift_risk_pct >= 25:
        drift_label, _ = translate_drift_risk(drift_risk_pct)
        parts.append(f'{drift_label} risk.')

    # Progress if mid-day
    if total and total > 0 and completed and completed > 0:
        prog_label, _ = translate_progress(completed, total)
        parts.append(prog_label + '.')

    return ' '.join(parts)


# ---------------------------------------------------------------------------
# Risk Warnings → Human Language
# ---------------------------------------------------------------------------

def translate_risk_warning(warning, context=None):
    """
    Translate a raw risk warning string into specific human language.

    Args:
        warning: Raw warning string from the governance engine
        context: Optional dict with keys:
            - commitment_name: Name of the specific commitment
            - time_remaining_minutes: Minutes until window closes
            - recommended_action: What the user should do

    Returns: str
    """
    if not warning:
        return ''

    # If we have specific context, generate a precise alert
    if context:
        name = context.get('commitment_name', '')
        minutes = context.get('time_remaining_minutes')
        action = context.get('recommended_action', '')

        if name and minutes is not None:
            if minutes > 0:
                if minutes <= 15:
                    return f"{name} hasn't happened yet — only {minutes} minutes left."
                else:
                    hours = minutes // 60
                    mins = minutes % 60
                    time_str = f"{hours}h {mins}m" if hours else f"{minutes} minutes"
                    return f"{name} hasn't happened yet, and you have {time_str} before your window closes."
            else:
                return f"{name} window has passed."
        elif name and action:
            return f"{name}: {action}"
        elif name:
            return f"{name} needs attention."

    # Fallback: category-based translation (no internal terms)
    w = warning.lower()
    if 'density' in w and 'elevated' in w:
        return 'Schedule is dense — protect margin where possible.'
    elif 'tier 1' in w or 'tier-1' in w or 'protected' in w:
        # Extract specific item name if present in the warning string
        # Warnings often contain item names after colons or in quotes
        import re
        quoted = re.search(r'["\']([^"\']+)["\']', warning)
        after_colon = re.search(r':\s*(.+)', warning)
        if quoted:
            return f'{quoted.group(1)} needs your attention.'
        elif after_colon:
            detail = after_colon.group(1).strip().rstrip('.')
            detail = detail.replace('Tier-1', '').replace('Tier 1', '').strip()
            if detail:
                return f'{detail}.'
        # If we still can't extract specifics, say what category
        if 'no tier 1' in w or 'no tier-1' in w:
            return 'No top priorities are scheduled today — consider adding one.'
        return 'A top priority hasn\'t been completed yet — check your plan.'
    elif 'sleep' in w:
        return "Sleep isn't scheduled — consider adding rest."
    elif 'overload' in w:
        return 'Tomorrow carries more load than typical.'
    # Pass through if no match (but strip internal terms)
    cleaned = warning.replace('Tier-1', 'priority').replace('tier-1', 'priority')
    cleaned = cleaned.replace('Tier 1', 'priority').replace('tier 1', 'priority')
    return cleaned


# ---------------------------------------------------------------------------
# Missed Commitment → Human Language (Drift Response)
# ---------------------------------------------------------------------------

def translate_missed_commitment(item_name, time_remaining_minutes=None,
                                 miss_count_week=0, accountability_style='standard'):
    """
    Generate a specific message when a commitment is missed or at risk.

    Args:
        item_name: Name of the commitment (e.g., "Morning Prayer", "Gym session")
        time_remaining_minutes: Minutes until the window closes (None if already passed)
        miss_count_week: Number of times missed this week
        accountability_style: 'light', 'standard', or 'firm'

    Returns: str
    """
    if not item_name:
        return ''

    parts = []

    # Time-based message
    if time_remaining_minutes is not None and time_remaining_minutes > 0:
        if time_remaining_minutes <= 15:
            parts.append(f"You have {time_remaining_minutes} minutes left for {item_name}.")
        elif time_remaining_minutes <= 60:
            parts.append(f"You still have {time_remaining_minutes} minutes to get {item_name} done.")
        else:
            hours = time_remaining_minutes // 60
            mins = time_remaining_minutes % 60
            time_str = f"{hours}h {mins}m" if mins else f"{hours} hour{'s' if hours > 1 else ''}"
            parts.append(f"{item_name} has {time_str} remaining.")
    elif time_remaining_minutes is not None and time_remaining_minutes <= 0:
        parts.append(f"{item_name} window has passed.")

    # Pattern detection
    if miss_count_week >= 3:
        if accountability_style == 'light':
            parts.append(f"That's {miss_count_week} times this week — worth thinking about.")
        elif accountability_style == 'firm':
            parts.append(
                f"You marked this non-negotiable. You've missed it "
                f"{miss_count_week} times this week. We're off track."
            )
        else:
            parts.append(f"This is the {_ordinal(miss_count_week)} miss this week.")
    elif miss_count_week == 2:
        if accountability_style != 'light':
            parts.append("Second miss this week.")

    return ' '.join(parts)


def _ordinal(n):
    """Return ordinal string for a number (1st, 2nd, 3rd, etc.)."""
    if 11 <= (n % 100) <= 13:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return f"{n}{suffix}"


# ---------------------------------------------------------------------------
# Status Line → Human Language
# ---------------------------------------------------------------------------

def get_status_line(drift_risk_pct):
    """
    Return the system status line (replaces "System stable. Tier-1 protected.")

    Returns: str
    """
    if drift_risk_pct is None:
        drift_risk_pct = 0
    if drift_risk_pct >= 50:
        return 'Under pressure. Protections locked.'
    elif drift_risk_pct >= 25:
        return 'Moderate pressure. Adjustments available.'
    else:
        return 'Running clean. Protections in place.'
