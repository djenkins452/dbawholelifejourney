"""
COS-CX3: Goal Behavior Gap Analyzer
====================================

The genuinely NEW intelligence component. Compares declared goal targets
to actual behavior frequency and surfaces the delta.

This is the "You're doing A, B, D, E but not C" detector.

For each active goal, determines:
  - target frequency (from goal metadata or inferred from domain)
  - actual frequency (from real data over trailing window)
  - gap percentage
  - trend direction
  - risk level

Performance target: < 10ms (bounded queries per goal, max 3 goals).
Token budget: ~150 tokens max.
"""
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)

MAX_GAPS = 3
TRAILING_WEEKS = 4  # 4-week lookback window


def analyze_goal_behavior_gaps(user, now):
    """
    Analyze gaps between declared goals and actual behavior.

    Args:
        user: Django User object
        now: timezone-aware datetime in user's timezone

    Returns:
        list of dicts, each with:
            goal_title, target_desc, actual_desc, gap_pct, trend, risk_level
        or empty list on failure.
    """
    try:
        from apps.purpose.models import LifeGoal

        today = now.date()
        window_start = today - timedelta(weeks=TRAILING_WEEKS)

        active_goals = list(
            LifeGoal.objects.filter(
                user=user,
                status='active',
            ).select_related('domain')[:MAX_GAPS + 2]  # Slight over-fetch to allow filtering
        )

        gaps = []
        for goal in active_goals:
            gap = _analyze_single_goal(user, goal, today, window_start)
            if gap and gap.get('gap_pct', 0) < -15:  # Only report meaningful gaps
                gaps.append(gap)

        # Sort by severity (most negative gap first)
        gaps.sort(key=lambda g: g.get('gap_pct', 0))
        return gaps[:MAX_GAPS]

    except Exception as e:
        logger.debug("Goal gap analysis skipped: %s", e)
        return []


def format_goal_gaps_block(gaps):
    """
    Format gap analysis as injectable context block.

    Args:
        gaps: list from analyze_goal_behavior_gaps()

    Returns:
        str — formatted block, or "" if no gaps.
    """
    if not gaps:
        return ""

    lines = ["=== GOAL GAPS ==="]
    for gap in gaps:
        risk_tag = f"[{gap['risk_level'].upper()}]" if gap.get('risk_level') else ""
        lines.append(f"{gap['goal_title']}: {risk_tag}")
        lines.append(f"  Target: {gap['target_desc']}")
        lines.append(f"  Actual: {gap['actual_desc']}")
        lines.append(f"  Gap: {gap['gap_pct']:+d}%")
        if gap.get('trend'):
            lines.append(f"  Trend: {gap['trend']}")

    return "\n".join(lines)


def _analyze_single_goal(user, goal, today, window_start):
    """Analyze a single goal for behavioral gaps."""
    try:
        domain_key = goal.domain.slug if goal.domain else ''

        # Try domain-specific analysis
        if domain_key in ('health', 'health-discipline') or _title_matches(
            goal.title, ['workout', 'exercise', 'fitness', 'gym', 'run', 'walk',
                         'cardio', 'strength', 'weight loss', 'lose weight']
        ):
            return _analyze_fitness_gap(user, goal, today, window_start)

        elif domain_key in ('faith', 'spiritual') or _title_matches(
            goal.title, ['bible', 'read', 'scripture', 'pray', 'prayer',
                         'quiet time', 'devotional', 'faith']
        ):
            return _analyze_faith_gap(user, goal, today, window_start)

        elif domain_key in ('journal', 'reflection') or _title_matches(
            goal.title, ['journal', 'write', 'reflect', 'diary']
        ):
            return _analyze_journal_gap(user, goal, today, window_start)

        elif _title_matches(
            goal.title, ['weight', 'pounds', 'lbs', 'body fat', 'bmi']
        ):
            return _analyze_weight_gap(user, goal, today, window_start)

        # Generic milestone-based analysis for other goals
        return _analyze_milestone_gap(user, goal, today)

    except Exception as e:
        logger.debug("Single goal gap analysis failed for '%s': %s", goal.title, e)
        return None


def _analyze_fitness_gap(user, goal, today, window_start):
    """Fitness goal: compare workout frequency to inferred target."""
    try:
        from apps.health.services.workout_queries import WorkoutQueries

        # Infer target: look for numbers in goal title/description
        target_per_week = _extract_frequency_target(goal, default=3)

        # Count actual completed workouts in trailing window
        total_weeks = max(TRAILING_WEEKS, 1)
        workout_count = WorkoutQueries.completed_in_range(
            user, window_start, today,
        ).count()
        actual_per_week = round(workout_count / total_weeks, 1)

        gap_pct = _compute_gap_pct(actual_per_week, target_per_week)

        # Trend: compare last 2 weeks vs prior 2 weeks
        midpoint = today - timedelta(weeks=2)
        recent = WorkoutQueries.completed_in_range(
            user, midpoint, today,
        ).count()
        earlier = WorkoutQueries.completed_in_range(
            user, window_start, midpoint - timedelta(days=1),
        ).count()
        trend = _compute_trend(recent, earlier)

        return {
            'goal_title': goal.title,
            'target_desc': f"{target_per_week}x/week",
            'actual_desc': f"{actual_per_week}x/week (last {total_weeks} weeks)",
            'gap_pct': gap_pct,
            'trend': trend,
            'risk_level': _risk_from_gap(gap_pct),
        }
    except Exception as e:
        logger.debug("Fitness gap analysis failed: %s", e)
        return None


def _analyze_faith_gap(user, goal, today, window_start):
    """Faith goal: reading plan completion or prayer frequency."""
    try:
        from apps.faith.models import UserReadingProgress

        target_per_week = _extract_frequency_target(goal, default=7)  # Daily by default
        total_weeks = max(TRAILING_WEEKS, 1)

        # Count days with reading progress
        reading_days = UserReadingProgress.objects.filter(
            user_plan__user=user,
            completed_at__date__gte=window_start,
            completed_at__date__lte=today,
        ).values('completed_at__date').distinct().count()

        actual_per_week = round(reading_days / total_weeks, 1)
        gap_pct = _compute_gap_pct(actual_per_week, target_per_week)

        midpoint = today - timedelta(weeks=2)
        recent = UserReadingProgress.objects.filter(
            user_plan__user=user,
            completed_at__date__gte=midpoint,
            completed_at__date__lte=today,
        ).values('completed_at__date').distinct().count()
        earlier = UserReadingProgress.objects.filter(
            user_plan__user=user,
            completed_at__date__gte=window_start,
            completed_at__date__lt=midpoint,
        ).values('completed_at__date').distinct().count()
        trend = _compute_trend(recent, earlier)

        return {
            'goal_title': goal.title,
            'target_desc': f"{target_per_week}x/week",
            'actual_desc': f"{actual_per_week}x/week (last {total_weeks} weeks)",
            'gap_pct': gap_pct,
            'trend': trend,
            'risk_level': _risk_from_gap(gap_pct),
        }
    except Exception as e:
        logger.debug("Faith gap analysis failed: %s", e)
        return None


def _analyze_journal_gap(user, goal, today, window_start):
    """Journal goal: entry frequency."""
    try:
        from apps.journal.models import JournalEntry

        target_per_week = _extract_frequency_target(goal, default=7)
        total_weeks = max(TRAILING_WEEKS, 1)

        entry_count = JournalEntry.objects.filter(
            user=user,
            created_at__date__gte=window_start,
            created_at__date__lte=today,
        ).count()
        actual_per_week = round(entry_count / total_weeks, 1)
        gap_pct = _compute_gap_pct(actual_per_week, target_per_week)

        midpoint = today - timedelta(weeks=2)
        recent = JournalEntry.objects.filter(
            user=user, created_at__date__gte=midpoint, created_at__date__lte=today
        ).count()
        earlier = JournalEntry.objects.filter(
            user=user, created_at__date__gte=window_start, created_at__date__lt=midpoint
        ).count()
        trend = _compute_trend(recent, earlier)

        return {
            'goal_title': goal.title,
            'target_desc': f"{target_per_week}x/week",
            'actual_desc': f"{actual_per_week}x/week (last {total_weeks} weeks)",
            'gap_pct': gap_pct,
            'trend': trend,
            'risk_level': _risk_from_gap(gap_pct),
        }
    except Exception as e:
        logger.debug("Journal gap analysis failed: %s", e)
        return None


def _analyze_weight_gap(user, goal, today, window_start):
    """Weight goal: compare current weight to target."""
    try:
        from apps.health.models import WeightEntry

        latest = WeightEntry.objects.filter(
            user=user,
        ).order_by('-date').first()

        if not latest:
            return None

        # Try to extract target weight from goal title/description
        target_weight = _extract_number_from_text(
            f"{goal.title} {goal.description or ''}"
        )
        if not target_weight:
            return None

        current = float(latest.weight)
        gap = current - target_weight
        gap_pct = int((gap / target_weight) * 100) if target_weight else 0

        # Trend from recent entries
        month_ago = today - timedelta(days=30)
        older = WeightEntry.objects.filter(
            user=user, date__gte=month_ago, date__lt=today - timedelta(days=14)
        ).order_by('-date').first()

        trend = "stable"
        if older:
            diff = current - float(older.weight)
            if gap > 0:  # Need to lose weight
                trend = "improving" if diff < -1 else ("worsening" if diff > 1 else "stable")
            else:  # Need to gain weight
                trend = "improving" if diff > 1 else ("worsening" if diff < -1 else "stable")

        return {
            'goal_title': goal.title,
            'target_desc': f"{target_weight} lbs",
            'actual_desc': f"{current} lbs (current)",
            'gap_pct': -abs(gap_pct) if gap > 0 else gap_pct,
            'trend': trend,
            'risk_level': _risk_from_gap(-abs(gap_pct)),
        }
    except Exception as e:
        logger.debug("Weight gap analysis failed: %s", e)
        return None


def _analyze_milestone_gap(user, goal, today):
    """Generic: milestone completion pace vs. deadline."""
    try:
        if not goal.target_date:
            return None

        total = goal.milestone_count
        completed = goal.completed_milestone_count
        if total == 0:
            return None

        # How much time has elapsed vs. total timeline
        # (can't compute without start date, use created_at)
        created = goal.created_at.date() if hasattr(goal, 'created_at') else None
        if not created:
            return None

        total_days = max((goal.target_date - created).days, 1)
        elapsed_days = max((today - created).days, 1)
        time_pct = min(int((elapsed_days / total_days) * 100), 100)
        progress_pct = int((completed / total) * 100)

        gap_pct = progress_pct - time_pct  # Negative = behind schedule

        if gap_pct >= -10:  # On track or ahead
            return None

        days_left = max((goal.target_date - today).days, 0)

        return {
            'goal_title': goal.title,
            'target_desc': f"{time_pct}% of time elapsed, {days_left}d remaining",
            'actual_desc': f"{progress_pct}% complete ({completed}/{total} milestones)",
            'gap_pct': gap_pct,
            'trend': None,
            'risk_level': _risk_from_gap(gap_pct),
        }
    except Exception as e:
        logger.debug("Milestone gap analysis failed: %s", e)
        return None


# --- Utility functions ---

def _title_matches(title, keywords):
    """Check if goal title contains any of the keywords."""
    title_lower = title.lower()
    return any(kw in title_lower for kw in keywords)


def _extract_frequency_target(goal, default=3):
    """Extract a numeric frequency target from goal title/description."""
    import re
    text = f"{goal.title} {goal.description or ''} {goal.success_looks_like or ''}"
    # Match patterns like "3x/week", "3 times a week", "3 per week"
    match = re.search(r'(\d+)\s*(?:x|times?)\s*(?:per|a|/)\s*week', text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    # Match "daily" = 7/week
    if re.search(r'\bdaily\b', text, re.IGNORECASE):
        return 7
    # Match "every day"
    if re.search(r'\bevery\s+day\b', text, re.IGNORECASE):
        return 7
    return default


def _extract_number_from_text(text):
    """Extract a weight-like number from text (e.g., '185 lbs')."""
    import re
    match = re.search(r'(\d{2,3})\s*(?:lbs?|pounds?|kg)?', text, re.IGNORECASE)
    if match:
        num = int(match.group(1))
        if 80 <= num <= 500:  # Reasonable weight range
            return num
    return None


def _compute_gap_pct(actual, target):
    """Compute gap as percentage. Negative = behind target."""
    if target <= 0:
        return 0
    return int(((actual - target) / target) * 100)


def _compute_trend(recent_count, earlier_count):
    """Determine trend direction from two-period comparison."""
    if recent_count > earlier_count + 1:
        return "improving"
    elif recent_count < earlier_count - 1:
        return "declining"
    return "stable"


def _risk_from_gap(gap_pct):
    """Classify risk level from gap percentage."""
    if gap_pct <= -60:
        return "high"
    elif gap_pct <= -30:
        return "moderate"
    elif gap_pct <= -15:
        return "low"
    return None
