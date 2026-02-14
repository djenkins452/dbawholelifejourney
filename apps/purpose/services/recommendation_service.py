"""
Recommendation Service — Generate smart insights and suggestions for goals.

Rules:
- High completion (>90% for 2+ weeks) → suggest increasing target
- Low completion (<40% for 2+ weeks) → suggest decreasing session length
- Day-of-week patterns → note best/worst days
- Milestone celebrations → 7, 30, 60, 90, 180, 365 day milestones
- Duration goals: pace analysis
- Count goals: gradual progression suggestions
- Target goals: pace adjustments

Location: apps/purpose/services/recommendation_service.py
"""

from datetime import timedelta

from django.db.models import Avg

from apps.purpose.models import GoalInsight
from . import analytics_service, streak_service


# Milestone thresholds for celebrations
MILESTONE_DAYS = [7, 14, 30, 60, 90, 180, 365]


def generate_insights(goal) -> list:
    """
    Generate and store new insights for a goal.

    Checks various conditions and creates GoalInsight records
    for any that trigger. Avoids creating duplicate insights
    for the same condition.

    Args:
        goal: HabitGoal instance

    Returns:
        List of newly created GoalInsight instances.
    """
    new_insights = []

    # Get analytics data
    analytics = analytics_service.get_analytics(goal, days=14)
    streak_data = streak_service.get_streak_data(goal)

    # Only generate insights for goals with enough data
    if analytics.total_sessions < 3:
        return new_insights

    # ── Streak Milestones ──
    insight = _check_streak_milestones(goal, streak_data.current)
    if insight:
        new_insights.append(insight)

    # ── High Completion → Suggest Increase ──
    insight = _check_high_completion(goal, analytics)
    if insight:
        new_insights.append(insight)

    # ── Low Completion → Suggest Decrease ──
    insight = _check_low_completion(goal, analytics)
    if insight:
        new_insights.append(insight)

    # ── Day-of-Week Pattern ──
    insight = _check_day_pattern(goal, analytics)
    if insight:
        new_insights.append(insight)

    # ── Trend Warning ──
    insight = _check_trend_warning(goal, analytics)
    if insight:
        new_insights.append(insight)

    # ── Consistency Celebration ──
    insight = _check_consistency_celebration(goal, analytics)
    if insight:
        new_insights.append(insight)

    return new_insights


def get_active_insights(goal):
    """
    Get undismissed insights for a goal, newest first.

    Args:
        goal: HabitGoal instance

    Returns:
        QuerySet of active GoalInsight instances.
    """
    return goal.insights.filter(is_dismissed=False).order_by('-created_at')


def dismiss_insight(insight_id: int) -> bool:
    """
    Mark an insight as dismissed.

    Args:
        insight_id: GoalInsight pk

    Returns:
        True if dismissed, False if not found.
    """
    try:
        insight = GoalInsight.objects.get(pk=insight_id)
        insight.is_dismissed = True
        insight.save(update_fields=['is_dismissed'])
        return True
    except GoalInsight.DoesNotExist:
        return False


def apply_insight(insight_id: int) -> bool:
    """
    Apply an insight's suggestion to the goal.

    Reads suggestion_data and updates goal fields accordingly.

    Args:
        insight_id: GoalInsight pk

    Returns:
        True if applied, False if not applicable.
    """
    try:
        insight = GoalInsight.objects.select_related('goal').get(pk=insight_id)
    except GoalInsight.DoesNotExist:
        return False

    suggestion = insight.suggestion_data
    goal = insight.goal
    changed = False

    if 'new_target' in suggestion:
        from decimal import Decimal
        goal.target_value = Decimal(str(suggestion['new_target']))
        changed = True

    if 'new_sessions_per_week' in suggestion:
        goal.sessions_per_week = suggestion['new_sessions_per_week']
        changed = True

    if changed:
        goal.save()
        insight.is_applied = True
        insight.is_dismissed = True
        insight.save(update_fields=['is_applied', 'is_dismissed'])
        return True

    # Mark as dismissed even if no changes were applicable
    insight.is_dismissed = True
    insight.save(update_fields=['is_dismissed'])
    return False


# =============================================================================
# Insight Check Functions
# =============================================================================

def _has_recent_insight(goal, insight_type: str, days: int = 7) -> bool:
    """Check if a similar insight was created recently."""
    from django.utils import timezone
    cutoff = timezone.now() - timedelta(days=days)
    return goal.insights.filter(
        insight_type=insight_type,
        created_at__gte=cutoff,
    ).exists()


def _check_streak_milestones(goal, current_streak: int):
    """Create celebration insight for streak milestones."""
    for milestone in MILESTONE_DAYS:
        if current_streak == milestone:
            if _has_recent_insight(goal, 'milestone', days=2):
                return None

            return GoalInsight.objects.create(
                goal=goal,
                insight_type='milestone',
                title=f'{milestone}-Day Streak!',
                message=(
                    f"You've completed {goal.name} for {milestone} consecutive "
                    f"{'days' if goal.frequency_type == 'daily' else 'periods'}. "
                    f"That's incredible dedication — keep it going!"
                ),
                suggestion_data={'milestone': milestone},
            )
    return None


def _check_high_completion(goal, analytics):
    """Suggest increasing target if completion rate is consistently high."""
    if analytics.completion_rate < 90:
        return None

    if not goal.target_value:
        return None

    if _has_recent_insight(goal, 'optimization', days=14):
        return None

    new_target = float(goal.target_value) * 1.15  # 15% increase

    unit = goal.target_unit_display
    return GoalInsight.objects.create(
        goal=goal,
        insight_type='optimization',
        title='Ready for a Challenge?',
        message=(
            f"You've maintained a {analytics.completion_rate:.0f}% completion rate. "
            f"Consider increasing your target from {goal.target_value} to "
            f"{new_target:.0f} {unit} per session."
        ),
        suggestion_data={'new_target': round(new_target, 1)},
    )


def _check_low_completion(goal, analytics):
    """Suggest reducing target if completion rate is consistently low."""
    if analytics.completion_rate > 40:
        return None

    if not goal.target_value:
        return None

    if _has_recent_insight(goal, 'warning', days=14):
        return None

    new_target = float(goal.target_value) * 0.8  # 20% decrease

    unit = goal.target_unit_display
    return GoalInsight.objects.create(
        goal=goal,
        insight_type='warning',
        title='Adjust Your Target?',
        message=(
            f"Your completion rate is {analytics.completion_rate:.0f}%. "
            f"Starting smaller can build momentum. Consider reducing "
            f"your target to {new_target:.0f} {unit} per session."
        ),
        suggestion_data={'new_target': round(new_target, 1)},
    )


def _check_day_pattern(goal, analytics):
    """Note day-of-week patterns if significant."""
    breakdown = analytics.day_of_week_breakdown
    if not breakdown:
        return None

    values = [v for v in breakdown.values() if v > 0]
    if len(values) < 3:
        return None

    best = analytics.best_day_of_week
    worst = analytics.worst_day_of_week

    if not best or not worst or best == worst:
        return None

    best_count = breakdown.get(best, 0)
    worst_count = breakdown.get(worst, 0)

    # Only flag if there's a significant difference
    if best_count <= worst_count * 2:
        return None

    if _has_recent_insight(goal, 'pattern', days=14):
        return None

    return GoalInsight.objects.create(
        goal=goal,
        insight_type='pattern',
        title='Pattern Spotted',
        message=(
            f"You tend to be most consistent on {best}s ({best_count} sessions) "
            f"and less active on {worst}s ({worst_count} sessions). "
            f"Consider scheduling your {goal.name} sessions on days "
            f"that work best for you."
        ),
        suggestion_data={'best_day': best, 'worst_day': worst},
    )


def _check_trend_warning(goal, analytics):
    """Warn if trend is declining."""
    if analytics.trend_direction != 'declining':
        return None

    if _has_recent_insight(goal, 'warning', days=14):
        return None

    return GoalInsight.objects.create(
        goal=goal,
        insight_type='warning',
        title='Getting Off Track?',
        message=(
            f"Your activity on {goal.name} has been declining recently. "
            f"That's okay — consistency matters more than perfection. "
            f"Even a small session today keeps the momentum alive."
        ),
        suggestion_data={},
    )


def _check_consistency_celebration(goal, analytics):
    """Celebrate high weekly consistency."""
    if analytics.weekly_consistency < 90:
        return None

    if _has_recent_insight(goal, 'encouragement', days=14):
        return None

    return GoalInsight.objects.create(
        goal=goal,
        insight_type='encouragement',
        title='Consistency Champion!',
        message=(
            f"Your weekly consistency on {goal.name} is {analytics.weekly_consistency:.0f}%. "
            f"You're building a strong habit — this kind of dedication "
            f"compounds over time."
        ),
        suggestion_data={},
    )
