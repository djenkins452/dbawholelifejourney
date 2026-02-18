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
        return ('Critical', 'Overload risk. Tier-1 items need protection.')


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
            f'{tier1_count} protected commitment{"s" if tier1_count > 1 else ""}.'
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

def translate_risk_warning(warning):
    """
    Translate a raw risk warning string into softer human language.

    Returns: str
    """
    if not warning:
        return ''
    # Common patterns from architecture engine
    w = warning.lower()
    if 'density' in w and 'elevated' in w:
        return 'Schedule is dense — protect margin where possible.'
    elif 'tier 1' in w or 'tier-1' in w:
        return 'A protected commitment may be at risk.'
    elif 'sleep' in w:
        return 'Sleep block isn\'t scheduled — consider adding rest.'
    elif 'overload' in w:
        return 'Tomorrow carries more load than typical.'
    # Pass through if no match
    return warning


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
