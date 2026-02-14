"""
Streak Service — Calculate streaks for goals of any measurement type and frequency.

Handles:
- Daily goals: consecutive days with completed entries
- Weekly goals: consecutive weeks meeting sessions_per_week target
- Monthly goals: consecutive months with completed entries

Location: apps/purpose/services/streak_service.py
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from django.utils import timezone


@dataclass
class StreakData:
    """Structured streak information for a goal."""
    current: int
    longest: int
    at_risk: bool  # True if user hasn't logged today yet (could break streak)
    streak_start_date: Optional[date]


def get_streak_data(goal) -> StreakData:
    """
    Calculate comprehensive streak data for a goal.

    Args:
        goal: HabitGoal instance

    Returns:
        StreakData with current/longest streaks and risk indicator.
    """
    current = get_current_streak(goal)
    longest = get_longest_streak(goal)
    at_risk = _is_at_risk(goal)

    # Calculate streak start date
    streak_start = None
    if current > 0 and goal.frequency_type == 'daily':
        from apps.core.utils import get_user_today
        today = get_user_today(goal.user)
        streak_start = today - timedelta(days=current - 1)

    return StreakData(
        current=current,
        longest=longest,
        at_risk=at_risk,
        streak_start_date=streak_start,
    )


def get_current_streak(goal) -> int:
    """
    Calculate current consecutive completion streak.

    For daily goals: consecutive days with completed entries working backward from today.
    For weekly goals: consecutive weeks meeting sessions_per_week.
    For monthly goals: consecutive months with at least one completed entry.

    Args:
        goal: HabitGoal instance

    Returns:
        Current streak count (0 if no streak).
    """
    if goal.frequency_type == 'daily':
        return _daily_streak(goal, reverse=False)
    elif goal.frequency_type == 'weekly':
        return _weekly_streak(goal, reverse=False)
    elif goal.frequency_type == 'monthly':
        return _monthly_streak(goal, reverse=False)
    return 0


def get_longest_streak(goal) -> int:
    """
    Calculate the longest streak ever achieved for the goal.

    Scans all history to find the maximum consecutive streak.

    Args:
        goal: HabitGoal instance

    Returns:
        Longest streak count.
    """
    if goal.frequency_type == 'daily':
        return _daily_longest_streak(goal)
    elif goal.frequency_type == 'weekly':
        return _weekly_longest_streak(goal)
    elif goal.frequency_type == 'monthly':
        return _monthly_longest_streak(goal)
    return 0


# =============================================================================
# Daily Streak Calculations
# =============================================================================

def _daily_streak(goal, reverse=False) -> int:
    """Calculate current daily streak working backward from today."""
    from apps.core.utils import get_user_today
    today = get_user_today(goal.user)

    completed_dates = set(
        goal.habit_entries.filter(completed=True)
        .values_list('date', flat=True)
    )

    if not completed_dates:
        return 0

    check_date = min(today, goal.end_date)
    streak = 0

    while check_date >= goal.start_date:
        if check_date in completed_dates:
            streak += 1
            check_date -= timedelta(days=1)
        elif check_date > today:
            # Skip future dates
            check_date -= timedelta(days=1)
        else:
            break

    return streak


def _daily_longest_streak(goal) -> int:
    """Find the longest daily streak by scanning all entries."""
    completed_dates = sorted(
        goal.habit_entries.filter(completed=True)
        .values_list('date', flat=True)
    )

    if not completed_dates:
        return 0

    longest = 1
    current = 1

    for i in range(1, len(completed_dates)):
        if (completed_dates[i] - completed_dates[i - 1]).days == 1:
            current += 1
            longest = max(longest, current)
        else:
            current = 1

    return longest


# =============================================================================
# Weekly Streak Calculations
# =============================================================================

def _get_week_number(d):
    """Get ISO year-week tuple for a date."""
    iso = d.isocalendar()
    return (iso[0], iso[1])


def _weekly_streak(goal, reverse=False) -> int:
    """
    Calculate current weekly streak.

    A week counts as complete if the user has at least sessions_per_week
    completed entries (or at least 1 if sessions_per_week is not set).
    """
    from apps.core.utils import get_user_today
    today = get_user_today(goal.user)
    target = goal.sessions_per_week or 1

    # Group completed entries by ISO week
    entries = goal.habit_entries.filter(completed=True).values_list('date', flat=True)
    weeks = {}
    for d in entries:
        wk = _get_week_number(d)
        weeks[wk] = weeks.get(wk, 0) + 1

    # Walk backward from current week
    current_week = _get_week_number(today)
    streak = 0
    check_date = today

    while check_date >= goal.start_date:
        wk = _get_week_number(check_date)
        if weeks.get(wk, 0) >= target:
            streak += 1
            # Jump to start of this week, then go back one day
            # to enter the previous week
            days_since_monday = check_date.weekday()
            check_date = check_date - timedelta(days=days_since_monday + 1)
        else:
            # Current week in progress — give grace if it's the current week
            if wk == current_week:
                days_since_monday = check_date.weekday()
                check_date = check_date - timedelta(days=days_since_monday + 1)
                continue
            break

    return streak


def _weekly_longest_streak(goal) -> int:
    """Find the longest weekly streak."""
    target = goal.sessions_per_week or 1

    entries = sorted(
        goal.habit_entries.filter(completed=True).values_list('date', flat=True)
    )

    if not entries:
        return 0

    # Group by week
    weeks = {}
    for d in entries:
        wk = _get_week_number(d)
        weeks[wk] = weeks.get(wk, 0) + 1

    # Get sorted list of weeks that met the target
    met_weeks = sorted([wk for wk, count in weeks.items() if count >= target])

    if not met_weeks:
        return 0

    longest = 1
    current = 1

    for i in range(1, len(met_weeks)):
        prev_year, prev_week = met_weeks[i - 1]
        curr_year, curr_week = met_weeks[i]

        # Check if consecutive weeks
        prev_date = date.fromisocalendar(prev_year, prev_week, 1)
        curr_date = date.fromisocalendar(curr_year, curr_week, 1)

        if (curr_date - prev_date).days == 7:
            current += 1
            longest = max(longest, current)
        else:
            current = 1

    return longest


# =============================================================================
# Monthly Streak Calculations
# =============================================================================

def _get_month_key(d):
    """Get (year, month) tuple for a date."""
    return (d.year, d.month)


def _monthly_streak(goal, reverse=False) -> int:
    """Calculate current monthly streak (consecutive months with completion)."""
    from apps.core.utils import get_user_today
    today = get_user_today(goal.user)

    entries = goal.habit_entries.filter(completed=True).values_list('date', flat=True)
    months = set()
    for d in entries:
        months.add(_get_month_key(d))

    if not months:
        return 0

    streak = 0
    year, month = today.year, today.month

    while True:
        if (year, month) in months:
            streak += 1
        elif (year, month) == _get_month_key(today):
            # Current month in progress — give grace
            pass
        else:
            break

        # Go to previous month
        if month == 1:
            year -= 1
            month = 12
        else:
            month -= 1

        # Stop if before goal start
        if date(year, month, 1) < date(goal.start_date.year, goal.start_date.month, 1):
            break

    return streak


def _monthly_longest_streak(goal) -> int:
    """Find the longest monthly streak."""
    entries = goal.habit_entries.filter(completed=True).values_list('date', flat=True)
    months = set()
    for d in entries:
        months.add(_get_month_key(d))

    if not months:
        return 0

    sorted_months = sorted(months)
    longest = 1
    current = 1

    for i in range(1, len(sorted_months)):
        prev_y, prev_m = sorted_months[i - 1]
        curr_y, curr_m = sorted_months[i]

        # Check if consecutive months
        expected_m = prev_m + 1
        expected_y = prev_y
        if expected_m > 12:
            expected_m = 1
            expected_y += 1

        if curr_y == expected_y and curr_m == expected_m:
            current += 1
            longest = max(longest, current)
        else:
            current = 1

    return longest


# =============================================================================
# Risk Assessment
# =============================================================================

def _is_at_risk(goal) -> bool:
    """
    Check if the current streak is at risk of breaking.

    For daily goals: True if today has no completed entry yet.
    For weekly goals: True if remaining days this week won't meet target.
    For monthly goals: True if no entries this month yet.
    """
    from apps.core.utils import get_user_today
    today = get_user_today(goal.user)

    # Goal hasn't started or already ended
    if today < goal.start_date or today > goal.end_date:
        return False

    if goal.frequency_type == 'daily':
        return not goal.habit_entries.filter(date=today, completed=True).exists()

    elif goal.frequency_type == 'weekly':
        target = goal.sessions_per_week or 1
        week_start = today - timedelta(days=today.weekday())
        week_entries = goal.habit_entries.filter(
            date__gte=week_start, date__lte=today, completed=True
        ).count()
        remaining_days = 6 - today.weekday()  # days left this week
        return (week_entries + remaining_days) < target

    elif goal.frequency_type == 'monthly':
        month_start = today.replace(day=1)
        return not goal.habit_entries.filter(
            date__gte=month_start, date__lte=today, completed=True
        ).exists()

    return False
