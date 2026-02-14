"""
Analytics Service — Compute goal analytics and performance metrics.

Provides:
- Completion rate (% of target periods completed)
- Average duration / count values
- Weekly consistency score
- Day-of-week breakdown
- Time-of-day patterns
- Trend direction (improving/declining/stable)

Location: apps/purpose/services/analytics_service.py
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from django.db.models import Avg, Count, Sum
from django.utils import timezone

from . import streak_service


@dataclass
class GoalAnalytics:
    """Structured analytics data for a goal."""
    completion_rate: float = 0.0  # 0-100
    avg_duration: Optional[float] = None  # minutes, DURATION goals only
    avg_count: Optional[float] = None  # COUNT goals only
    weekly_consistency: float = 0.0  # 0-100, % of weeks meeting target
    total_sessions: int = 0
    missed_days: int = 0
    best_day_of_week: Optional[str] = None
    worst_day_of_week: Optional[str] = None
    time_of_day_distribution: dict = field(default_factory=dict)
    day_of_week_breakdown: dict = field(default_factory=dict)
    trend_direction: str = 'stable'  # 'improving', 'declining', 'stable'
    current_streak: int = 0
    longest_streak: int = 0
    weekly_data: list = field(default_factory=list)  # Last 4 weeks for chart


DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def get_analytics(goal, days: int = 30) -> GoalAnalytics:
    """
    Calculate comprehensive analytics for a goal over the specified period.

    Args:
        goal: HabitGoal instance
        days: Number of days to analyze (default 30)

    Returns:
        GoalAnalytics dataclass with all computed metrics.
    """
    analytics = GoalAnalytics()

    analytics.completion_rate = get_completion_rate(goal, days)
    analytics.total_sessions = _count_sessions(goal, days)
    analytics.missed_days = _count_missed_days(goal, days)

    # Measurement-specific averages
    if goal.is_duration:
        analytics.avg_duration = _get_avg_duration(goal, days)
    elif goal.is_count:
        analytics.avg_count = _get_avg_count(goal, days)

    analytics.weekly_consistency = get_weekly_consistency(goal, weeks=4)
    analytics.day_of_week_breakdown = get_day_of_week_breakdown(goal, days)

    # Best/worst days
    if analytics.day_of_week_breakdown:
        sorted_days = sorted(
            analytics.day_of_week_breakdown.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        analytics.best_day_of_week = sorted_days[0][0] if sorted_days[0][1] > 0 else None
        analytics.worst_day_of_week = sorted_days[-1][0] if len(sorted_days) > 1 else None

    analytics.time_of_day_distribution = _get_time_of_day_distribution(goal, days)
    analytics.trend_direction = get_trend(goal)

    # Streaks
    streak_data = streak_service.get_streak_data(goal)
    analytics.current_streak = streak_data.current
    analytics.longest_streak = streak_data.longest

    # Weekly chart data (last 4 weeks)
    analytics.weekly_data = _get_weekly_chart_data(goal)

    return analytics


def get_completion_rate(goal, days: int = 30) -> float:
    """
    Calculate completion rate as percentage over the specified period.

    For daily goals: (completed_days / total_trackable_days) * 100
    For weekly/monthly: uses period-appropriate calculations.

    Args:
        goal: HabitGoal instance
        days: Days to look back

    Returns:
        Completion rate as float (0-100).
    """
    from apps.core.utils import get_user_today
    today = get_user_today(goal.user)
    start = max(goal.start_date, today - timedelta(days=days))
    end = min(goal.end_date, today)

    if start > end:
        return 0.0

    total_days = (end - start).days + 1
    completed = goal.habit_entries.filter(
        date__gte=start,
        date__lte=end,
        completed=True,
    ).values('date').distinct().count()

    if total_days <= 0:
        return 0.0

    return min(100.0, (completed / total_days) * 100)


def get_weekly_consistency(goal, weeks: int = 4) -> float:
    """
    Calculate percentage of weeks that met the session target.

    Args:
        goal: HabitGoal instance
        weeks: Number of weeks to check

    Returns:
        Consistency percentage (0-100).
    """
    from apps.core.utils import get_user_today
    today = get_user_today(goal.user)
    target = goal.sessions_per_week or (7 if goal.frequency_type == 'daily' else 1)

    weeks_met = 0
    weeks_checked = 0

    for w in range(weeks):
        week_end = today - timedelta(days=today.weekday()) - timedelta(weeks=w)
        week_start = week_end - timedelta(days=6)

        # Skip weeks before goal start
        if week_end < goal.start_date:
            continue

        week_start = max(week_start, goal.start_date)
        weeks_checked += 1

        count = goal.habit_entries.filter(
            date__gte=week_start,
            date__lte=week_end,
            completed=True,
        ).count()

        if count >= target:
            weeks_met += 1

    if weeks_checked == 0:
        return 0.0

    return (weeks_met / weeks_checked) * 100


def get_day_of_week_breakdown(goal, days: int = 30) -> dict:
    """
    Get completion counts broken down by day of week.

    Args:
        goal: HabitGoal instance
        days: Days to look back

    Returns:
        Dict mapping day names to completion counts.
    """
    from apps.core.utils import get_user_today
    today = get_user_today(goal.user)
    start = max(goal.start_date, today - timedelta(days=days))

    entries = goal.habit_entries.filter(
        date__gte=start,
        date__lte=today,
        completed=True,
    ).values_list('date', flat=True)

    counts = Counter()
    for d in entries:
        counts[DAY_NAMES[d.weekday()]] += 1

    # Ensure all days present
    return {day: counts.get(day, 0) for day in DAY_NAMES}


def get_trend(goal, periods: int = 4) -> str:
    """
    Determine trend direction by comparing recent vs prior period.

    Compares completion rate of the most recent `periods/2` weeks
    against the prior `periods/2` weeks.

    Args:
        goal: HabitGoal instance
        periods: Number of week-periods to compare

    Returns:
        'improving', 'declining', or 'stable'.
    """
    from apps.core.utils import get_user_today
    today = get_user_today(goal.user)
    half = max(1, periods // 2)

    # Recent period
    recent_end = today
    recent_start = today - timedelta(weeks=half)
    recent_rate = _period_completion_rate(goal, recent_start, recent_end)

    # Prior period
    prior_end = recent_start - timedelta(days=1)
    prior_start = prior_end - timedelta(weeks=half)
    prior_rate = _period_completion_rate(goal, prior_start, prior_end)

    if prior_rate == 0 and recent_rate == 0:
        return 'stable'

    diff = recent_rate - prior_rate
    if diff > 10:
        return 'improving'
    elif diff < -10:
        return 'declining'
    return 'stable'


# =============================================================================
# Private Helpers
# =============================================================================

def _count_sessions(goal, days: int) -> int:
    """Count total completed sessions in the period."""
    from apps.core.utils import get_user_today
    today = get_user_today(goal.user)
    start = max(goal.start_date, today - timedelta(days=days))
    return goal.habit_entries.filter(
        date__gte=start, date__lte=today, completed=True
    ).count()


def _count_missed_days(goal, days: int) -> int:
    """Count days with no completed entry in the period."""
    from apps.core.utils import get_user_today
    today = get_user_today(goal.user)
    start = max(goal.start_date, today - timedelta(days=days))
    end = min(goal.end_date, today)
    total_days = (end - start).days + 1

    completed_days = goal.habit_entries.filter(
        date__gte=start, date__lte=end, completed=True
    ).values('date').distinct().count()

    return max(0, total_days - completed_days)


def _get_avg_duration(goal, days: int) -> float:
    """Average duration in minutes for DURATION goals."""
    from apps.core.utils import get_user_today
    today = get_user_today(goal.user)
    start = max(goal.start_date, today - timedelta(days=days))
    result = goal.habit_entries.filter(
        date__gte=start, date__lte=today,
        completed=True, duration_minutes__isnull=False,
    ).aggregate(avg=Avg('duration_minutes'))
    return float(result['avg']) if result['avg'] else 0.0


def _get_avg_count(goal, days: int) -> float:
    """Average count value for COUNT goals."""
    from apps.core.utils import get_user_today
    today = get_user_today(goal.user)
    start = max(goal.start_date, today - timedelta(days=days))
    result = goal.habit_entries.filter(
        date__gte=start, date__lte=today,
        completed=True, count_value__isnull=False,
    ).aggregate(avg=Avg('count_value'))
    return float(result['avg']) if result['avg'] else 0.0


def _get_time_of_day_distribution(goal, days: int) -> dict:
    """
    Analyze when entries are created to find time-of-day patterns.

    Returns: {'morning': N, 'afternoon': N, 'evening': N, 'night': N}
    """
    from apps.core.utils import get_user_today
    today = get_user_today(goal.user)
    start = max(goal.start_date, today - timedelta(days=days))

    entries = goal.habit_entries.filter(
        date__gte=start, date__lte=today, completed=True,
    ).values_list('created_at', flat=True)

    distribution = {'morning': 0, 'afternoon': 0, 'evening': 0, 'night': 0}
    for created_at in entries:
        if created_at is None:
            continue
        hour = created_at.hour
        if 5 <= hour < 12:
            distribution['morning'] += 1
        elif 12 <= hour < 17:
            distribution['afternoon'] += 1
        elif 17 <= hour < 21:
            distribution['evening'] += 1
        else:
            distribution['night'] += 1

    return distribution


def _period_completion_rate(goal, start, end) -> float:
    """Completion rate for a specific date range."""
    start = max(start, goal.start_date)
    end = min(end, goal.end_date)

    if start > end:
        return 0.0

    total_days = (end - start).days + 1
    completed = goal.habit_entries.filter(
        date__gte=start, date__lte=end, completed=True,
    ).values('date').distinct().count()

    return (completed / total_days) * 100 if total_days > 0 else 0.0


def _get_weekly_chart_data(goal, weeks: int = 4) -> list:
    """
    Get completion data for the last N weeks, suitable for chart rendering.

    Returns: [{'week_label': 'Feb 3', 'completed': 5, 'target': 7}, ...]
    """
    from apps.core.utils import get_user_today
    today = get_user_today(goal.user)
    target_per_week = goal.sessions_per_week or (7 if goal.frequency_type == 'daily' else 1)

    data = []
    for w in range(weeks - 1, -1, -1):  # oldest first
        week_end_day = today - timedelta(days=today.weekday()) - timedelta(weeks=w)
        week_start_day = week_end_day - timedelta(days=6)
        week_start_day = max(week_start_day, goal.start_date)

        count = goal.habit_entries.filter(
            date__gte=week_start_day,
            date__lte=week_end_day,
            completed=True,
        ).count()

        data.append({
            'week_label': week_start_day.strftime('%b %d'),
            'completed': count,
            'target': target_per_week,
            'percent': min(100, int((count / target_per_week) * 100)) if target_per_week > 0 else 0,
        })

    return data


def analytics_to_dict(analytics: GoalAnalytics) -> dict:
    """
    Convert GoalAnalytics dataclass to JSON-serializable dict.

    Args:
        analytics: GoalAnalytics instance

    Returns:
        Dict suitable for JSON response.
    """
    return {
        'completion_rate': round(analytics.completion_rate, 1),
        'avg_duration': round(analytics.avg_duration, 1) if analytics.avg_duration is not None else None,
        'avg_count': round(analytics.avg_count, 1) if analytics.avg_count is not None else None,
        'weekly_consistency': round(analytics.weekly_consistency, 1),
        'total_sessions': analytics.total_sessions,
        'missed_days': analytics.missed_days,
        'best_day_of_week': analytics.best_day_of_week,
        'worst_day_of_week': analytics.worst_day_of_week,
        'time_of_day_distribution': analytics.time_of_day_distribution,
        'day_of_week_breakdown': analytics.day_of_week_breakdown,
        'trend_direction': analytics.trend_direction,
        'current_streak': analytics.current_streak,
        'longest_streak': analytics.longest_streak,
        'weekly_data': analytics.weekly_data,
    }
