"""
Brain Training Statistics Service

Provides improvement calculations and trend analysis for brain training progress.
"""

from datetime import timedelta

from django.db.models import Avg, Count, Sum
from django.utils import timezone

from ..models import DailyStats, GameSession


def get_improvement_stats(user, game, timeframe_days=28):
    """
    Calculate improvement statistics for a user's game performance.

    Compares the most recent 14-day window to the previous 14-day window.

    Args:
        user: User instance
        game: Game instance
        timeframe_days: Total days to analyze (default 28, split into two 14-day windows)

    Returns:
        dict with improvement metrics:
        - score_improvement_pct: Percentage improvement in average score
        - time_improvement_pct: Percentage improvement (reduction) in average time
        - trend: 'improving', 'declining', or 'stable'
        - recent_avg_score: Average score in recent period
        - previous_avg_score: Average score in previous period
        - recent_avg_time: Average time in recent period
        - previous_avg_time: Average time in previous period
    """
    today = timezone.now().date()
    window_size = timeframe_days // 2

    recent_start = today - timedelta(days=window_size)
    previous_start = today - timedelta(days=timeframe_days)
    previous_end = recent_start

    # Get recent period stats
    recent_sessions = GameSession.objects.filter(
        user=user,
        challenge__game=game,
        status=GameSession.STATUS_COMPLETED,
        completed_at__date__gte=recent_start,
        completed_at__date__lt=today + timedelta(days=1),
    )

    recent_stats = recent_sessions.aggregate(
        avg_score=Avg('score'),
        avg_time=Avg('time_spent_seconds'),
        count=Count('id'),
    )

    # Get previous period stats
    previous_sessions = GameSession.objects.filter(
        user=user,
        challenge__game=game,
        status=GameSession.STATUS_COMPLETED,
        completed_at__date__gte=previous_start,
        completed_at__date__lt=previous_end,
    )

    previous_stats = previous_sessions.aggregate(
        avg_score=Avg('score'),
        avg_time=Avg('time_spent_seconds'),
        count=Count('id'),
    )

    # Calculate improvements
    recent_avg_score = recent_stats['avg_score'] or 0
    previous_avg_score = previous_stats['avg_score'] or 0
    recent_avg_time = recent_stats['avg_time'] or 0
    previous_avg_time = previous_stats['avg_time'] or 0

    # Score improvement (higher is better)
    if previous_avg_score > 0:
        score_improvement_pct = round(
            ((recent_avg_score - previous_avg_score) / previous_avg_score) * 100, 1
        )
    else:
        score_improvement_pct = 0

    # Time improvement (lower is better, so we invert)
    if previous_avg_time > 0:
        time_improvement_pct = round(
            ((previous_avg_time - recent_avg_time) / previous_avg_time) * 100, 1
        )
    else:
        time_improvement_pct = 0

    # Determine trend
    if score_improvement_pct > 5:
        trend = 'improving'
    elif score_improvement_pct < -5:
        trend = 'declining'
    else:
        trend = 'stable'

    return {
        'score_improvement_pct': score_improvement_pct,
        'time_improvement_pct': time_improvement_pct,
        'trend': trend,
        'recent_avg_score': round(recent_avg_score, 1),
        'previous_avg_score': round(previous_avg_score, 1),
        'recent_avg_time': round(recent_avg_time, 1),
        'previous_avg_time': round(previous_avg_time, 1),
        'recent_sessions': recent_stats['count'] or 0,
        'previous_sessions': previous_stats['count'] or 0,
    }


def get_daily_trend(user, game, days=14):
    """
    Get daily performance trend for a game.

    Args:
        user: User instance
        game: Game instance
        days: Number of days to include

    Returns:
        List of dicts with daily stats
    """
    start_date = timezone.now().date() - timedelta(days=days)

    daily = DailyStats.objects.filter(
        user=user,
        game=game,
        date__gte=start_date,
    ).order_by('date')

    return [
        {
            'date': d.date.isoformat(),
            'sessions': d.sessions_completed,
            'avg_score': d.average_score,
            'avg_time': d.average_time_seconds,
            'best_score': d.best_score,
        }
        for d in daily
    ]


def get_difficulty_distribution(user, game, days=30):
    """
    Get distribution of completed sessions by difficulty.

    Args:
        user: User instance
        game: Game instance
        days: Number of days to include

    Returns:
        Dict mapping difficulty to count
    """
    start_date = timezone.now().date() - timedelta(days=days)

    sessions = GameSession.objects.filter(
        user=user,
        challenge__game=game,
        status=GameSession.STATUS_COMPLETED,
        completed_at__date__gte=start_date,
    ).values('challenge__difficulty').annotate(count=Count('id'))

    return {
        item['challenge__difficulty']: item['count']
        for item in sessions
    }
