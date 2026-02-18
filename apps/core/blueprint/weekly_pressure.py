"""
Whole Life Journey - Weekly Pressure Engine

Project: Whole Life Journey
Path: apps/core/blueprint/weekly_pressure.py
Purpose: Compute 7-day pressure forecast with opportunity window detection

Description:
    Aggregates ArchitecturePlans for the next 7 days to compute:
    - Per-day capacity load (% of waking hours scheduled)
    - Average weekly load
    - Peak day identification
    - Heavy/light day classification
    - Opportunity windows (2+ hour open blocks)

    This module integrates with:
    - architecture_engine (plan generation for future dates)
    - human_language (translate_weekly_pressure for UI)
    - ISE (scheduled execution via scheduler_registry)

    Output dict matches the contract expected by
    human_language.translate_weekly_pressure().

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import datetime as dt
import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

# Waking hours assumption (matches architecture_engine)
WAKING_HOURS = 16
WAKING_MINUTES = WAKING_HOURS * 60

# Thresholds
HEAVY_DAY_PCT = 70   # >= this is a heavy day
LIGHT_DAY_PCT = 30   # <= this is a light day
OPPORTUNITY_MIN_HOURS = 2  # Minimum hours for an opportunity window


def compute_weekly_pressure(user, start_date=None, days=7):
    """
    Compute the weekly pressure forecast.

    Args:
        user: User instance
        start_date: First day of the window (default: today)
        days: Number of days to look ahead (default: 7)

    Returns:
        dict with keys:
            - day_loads: list of (day_name, capacity_pct) tuples
            - avg_load: float (0-100)
            - peak_day: str (day name)
            - peak_load: float (0-100)
            - peak_detail: str (optional detail about peak)
            - light_days: list of str (day names)
            - heavy_days: list of str (day names)
            - opportunity_windows: list of dicts
    """
    from .models import ArchitecturePlan

    if start_date is None:
        start_date = timezone.localdate()

    day_loads = []
    heavy_days = []
    light_days = []
    opportunity_windows = []
    peak_day = ''
    peak_load = 0
    peak_detail = ''

    for offset in range(days):
        target_date = start_date + dt.timedelta(days=offset)
        day_name = target_date.strftime('%A')

        # Get existing plan for this date
        plan = ArchitecturePlan.get_active_for_date(user, target_date)

        if plan:
            blocks = list(plan.blocks.all().order_by('start_time'))
            capacity_pct, windows = _compute_day_load(
                target_date, blocks,
            )
        else:
            # No plan exists — estimate from non-negotiables
            capacity_pct = _estimate_from_non_negotiables(user, target_date)
            windows = []

        day_loads.append((day_name, round(capacity_pct)))

        if capacity_pct >= HEAVY_DAY_PCT:
            heavy_days.append(day_name)

        if capacity_pct <= LIGHT_DAY_PCT:
            light_days.append(day_name)

        if capacity_pct > peak_load:
            peak_load = capacity_pct
            peak_day = day_name
            if plan and hasattr(plan, 'risk_warnings') and plan.risk_warnings:
                peak_detail = '— ' + str(plan.risk_warnings[0])[:50]

        # Opportunity windows for this day
        for w in windows:
            w['day_name'] = day_name
            opportunity_windows.append(w)

    # Average load
    total_load = sum(pct for _, pct in day_loads)
    avg_load = total_load / max(len(day_loads), 1)

    return {
        'day_loads': day_loads,
        'avg_load': round(avg_load, 1),
        'peak_day': peak_day,
        'peak_load': round(peak_load, 1),
        'peak_detail': peak_detail,
        'light_days': light_days,
        'heavy_days': heavy_days,
        'opportunity_windows': opportunity_windows[:5],  # Top 5
    }


def _compute_day_load(target_date, blocks):
    """
    Compute capacity percentage and opportunity windows for a day's blocks.

    Returns:
        (capacity_pct: float, opportunity_windows: list of dicts)
    """
    if not blocks:
        return 0.0, []

    total_minutes = 0
    sorted_blocks = sorted(
        blocks,
        key=lambda b: b.start_time if b.start_time else dt.time(0),
    )

    for block in sorted_blocks:
        if block.start_time and block.end_time:
            start_dt = dt.datetime.combine(target_date, block.start_time)
            end_dt = dt.datetime.combine(target_date, block.end_time)
            delta = (end_dt - start_dt).total_seconds() / 60
            if delta > 0:
                total_minutes += delta

    capacity_pct = min(100, (total_minutes / WAKING_MINUTES) * 100)

    # Detect opportunity windows (gaps >= 2 hours between blocks)
    windows = _detect_opportunity_windows(target_date, sorted_blocks)

    return capacity_pct, windows


def _detect_opportunity_windows(target_date, sorted_blocks):
    """
    Detect opportunity windows (open gaps >= 2 hours) in a day's schedule.

    Args:
        target_date: date
        sorted_blocks: list of ScheduledBlock, sorted by start_time

    Returns:
        list of dicts with: start_time, end_time, duration_hours
    """
    windows = []

    if not sorted_blocks:
        # Entire day is open
        windows.append({
            'start_time': '08:00',
            'end_time': '20:00',
            'duration_hours': 12,
        })
        return windows

    # Define day boundaries
    day_start = dt.time(7, 0)   # 7 AM
    day_end = dt.time(22, 0)    # 10 PM

    # Build occupied ranges
    occupied = []
    for block in sorted_blocks:
        if block.start_time and block.end_time:
            occupied.append((block.start_time, block.end_time))

    if not occupied:
        return windows

    # Check gap before first block
    first_start = occupied[0][0]
    if first_start > day_start:
        gap_minutes = _time_diff_minutes(day_start, first_start)
        if gap_minutes >= OPPORTUNITY_MIN_HOURS * 60:
            windows.append({
                'start_time': day_start.strftime('%H:%M'),
                'end_time': first_start.strftime('%H:%M'),
                'duration_hours': round(gap_minutes / 60, 1),
            })

    # Check gaps between blocks
    for i in range(len(occupied) - 1):
        end_current = occupied[i][1]
        start_next = occupied[i + 1][0]

        if start_next > end_current:
            gap_minutes = _time_diff_minutes(end_current, start_next)
            if gap_minutes >= OPPORTUNITY_MIN_HOURS * 60:
                windows.append({
                    'start_time': end_current.strftime('%H:%M'),
                    'end_time': start_next.strftime('%H:%M'),
                    'duration_hours': round(gap_minutes / 60, 1),
                })

    # Check gap after last block
    last_end = occupied[-1][1]
    if last_end < day_end:
        gap_minutes = _time_diff_minutes(last_end, day_end)
        if gap_minutes >= OPPORTUNITY_MIN_HOURS * 60:
            windows.append({
                'start_time': last_end.strftime('%H:%M'),
                'end_time': day_end.strftime('%H:%M'),
                'duration_hours': round(gap_minutes / 60, 1),
            })

    return windows


def _time_diff_minutes(t1, t2):
    """Compute minutes between two time objects (t2 - t1)."""
    d1 = dt.datetime.combine(dt.date.today(), t1)
    d2 = dt.datetime.combine(dt.date.today(), t2)
    return (d2 - d1).total_seconds() / 60


def _estimate_from_non_negotiables(user, target_date):
    """
    Estimate day load from non-negotiables when no plan exists.

    Returns: float (capacity_pct estimate)
    """
    try:
        from . import engine as blueprint_engine
        non_negs = blueprint_engine.get_non_negotiables_for_date(
            user, target_date,
        )
        if not non_negs:
            return 0.0

        # Each non-negotiable is ~1h unless duration specified
        total_minutes = 0
        for nn in non_negs:
            duration = getattr(nn, 'duration_minutes', 60) or 60
            total_minutes += duration

        return min(100, (total_minutes / WAKING_MINUTES) * 100)
    except Exception:
        return 0.0
