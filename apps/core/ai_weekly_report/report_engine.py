"""
WIRE — Report Engine.

Main entry point for weekly intelligence report generation.
Aggregates SAE, PIE, PRIE, PGE, and GLOE data from the past 7 days.
"""

import logging
from datetime import timedelta

from django.utils import timezone

from apps.core.ai_weekly_report.models import WeeklyIntelligenceReport
from apps.core.ai_weekly_report.report_logger import store_weekly_report
from apps.core.ai_weekly_report.report_ranker import rank_report_items
from apps.core.ai_weekly_report.report_selector import select_report_items

logger = logging.getLogger(__name__)


def generate_weekly_report(user):
    """
    Generate a weekly intelligence report for a user.

    Pipeline: gather → compute deltas → select → rank → summarize → store

    Args:
        user: Django User instance.

    Returns:
        WeeklyIntelligenceReport instance, or None on failure.
    """
    try:
        week_start, week_end = _get_report_week()

        # Check for existing report
        existing = WeeklyIntelligenceReport.objects.filter(
            user=user, week_start_date=week_start,
        ).first()
        if existing:
            logger.debug(f"WIRE: Report already exists for user {user.id}, week {week_start}")
            return existing

        # Step 1: Gather intelligence
        current_state = _get_current_state(user)
        insights = _get_week_insights(user, week_start, week_end)
        predictions = _get_week_predictions(user, week_start, week_end)
        guidance = _get_week_guidance(user, week_start, week_end)
        learning = _get_learning_snapshot(user)
        state_deltas = _compute_state_deltas(current_state)

        # Step 2: Select top items
        selected = select_report_items(
            insights=insights,
            predictions=predictions,
            guidance_items=guidance,
            state_deltas=state_deltas,
        )

        # Step 3: Rank items
        ranked = rank_report_items(selected)

        # Step 4: Generate summary
        summary = _generate_summary(ranked, current_state, learning)

        # Step 5: Store
        report = store_weekly_report(
            user=user,
            week_start=week_start,
            week_end=week_end,
            summary=summary,
            state_delta_snapshot={"deltas": state_deltas},
            insight_snapshot={"insights": insights},
            prediction_snapshot={"predictions": predictions},
            guidance_snapshot={"guidance": guidance},
            learning_snapshot=learning,
        )

        # E3: Create explain record (non-blocking)
        if report:
            try:
                from apps.core.ai_explain.explain_engine import ensure_explain_record
                ensure_explain_record(user, "WIRE", report)
            except Exception:
                pass  # E3 failure must never block WIRE

        logger.info(f"WIRE: Generated weekly report for user {user.id}, week {week_start}")
        return report

    except Exception as e:
        logger.error(
            f"WIRE: Report generation failed for user {user.id}: {e}",
            exc_info=True,
        )
        return None


def get_latest_weekly_report(user):
    """
    Get the most recent weekly report for a user (read-only).

    Returns:
        WeeklyIntelligenceReport or None.
    """
    return WeeklyIntelligenceReport.objects.filter(
        user=user,
    ).first()  # ordered by -week_start_date


def get_report_history(user, limit=12):
    """
    Get historical weekly reports for a user.

    Args:
        user: Django User instance.
        limit: Maximum reports to return.

    Returns:
        QuerySet of WeeklyIntelligenceReport.
    """
    return WeeklyIntelligenceReport.objects.filter(
        user=user,
    )[:limit]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_report_week():
    """
    Get the week boundaries for the report.

    Returns the most recently completed week (Mon-Sun).

    Returns:
        (week_start: date, week_end: date)
    """
    today = timezone.now().date()
    # weekday(): Mon=0 ... Sun=6
    # Days back to the most recent completed Sunday:
    # Mon(0)→1, Tue(1)→2, ..., Sat(5)→6, Sun(6)→7
    days_since_monday = today.weekday()
    if days_since_monday == 6:
        # It's Sunday — report covers the PREVIOUS Mon-Sun
        days_back = 7
    else:
        # Mon-Sat — report covers the week ending last Sunday
        days_back = days_since_monday + 1

    week_end = today - timedelta(days=days_back)  # Sunday
    week_start = week_end - timedelta(days=6)  # Monday

    return week_start, week_end


def _get_current_state(user):
    """Read SAE user state. Failures return empty dict."""
    try:
        from apps.core.ai_state.state_engine import get_user_state
        return get_user_state(user) or {}
    except Exception:
        return {}


def _get_week_insights(user, week_start, week_end):
    """Get PIE insights from the report week."""
    try:
        from apps.core.ai_insights.models import Insight
        from django.utils import timezone as tz

        start_dt = tz.make_aware(
            tz.datetime.combine(week_start, tz.datetime.min.time())
        )
        end_dt = tz.make_aware(
            tz.datetime.combine(week_end + timedelta(days=1), tz.datetime.min.time())
        )

        insights = Insight.objects.filter(
            user=user,
            created_at__gte=start_dt,
            created_at__lt=end_dt,
        ).order_by("-created_at")[:30]

        return [
            {
                "title": i.title,
                "severity": i.severity,
                "description": getattr(i, "description", ""),
                "confidence_score": i.confidence_score,
                "created_at": i.created_at.isoformat(),
            }
            for i in insights
        ]
    except Exception as e:
        logger.error(f"WIRE: Failed to get insights: {e}")
        return []


def _get_week_predictions(user, week_start, week_end):
    """Get PRIE predictions active during the report week."""
    try:
        from apps.core.ai_predictions.models import Prediction
        from django.utils import timezone as tz

        start_dt = tz.make_aware(
            tz.datetime.combine(week_start, tz.datetime.min.time())
        )
        end_dt = tz.make_aware(
            tz.datetime.combine(week_end + timedelta(days=1), tz.datetime.min.time())
        )

        predictions = Prediction.objects.filter(
            user=user,
            created_at__gte=start_dt,
            created_at__lt=end_dt,
        ).order_by("-confidence_score")[:20]

        return [
            {
                "title": f"{p.prediction_type}: {p.predicted_value}",
                "description": p.explanation,
                "confidence_score": p.confidence_score,
                "module": p.module,
                "status": p.status,
                "created_at": p.created_at.isoformat(),
            }
            for p in predictions
        ]
    except Exception as e:
        logger.error(f"WIRE: Failed to get predictions: {e}")
        return []


def _get_week_guidance(user, week_start, week_end):
    """Get PGE guidance items with lifecycle status from the report week."""
    try:
        from apps.core.ai_guidance.models import GuidanceItem
        from django.utils import timezone as tz

        start_dt = tz.make_aware(
            tz.datetime.combine(week_start, tz.datetime.min.time())
        )
        end_dt = tz.make_aware(
            tz.datetime.combine(week_end + timedelta(days=1), tz.datetime.min.time())
        )

        items = GuidanceItem.objects.filter(
            user=user,
            created_at__gte=start_dt,
            created_at__lt=end_dt,
        ).order_by("priority")[:20]

        return [
            {
                "title": g.title,
                "message": g.message,
                "priority": g.priority,
                "acknowledged": g.is_acknowledged,
                "dismissed": g.is_dismissed,
                "acted": g.is_acted_upon,
                "created_at": g.created_at.isoformat(),
            }
            for g in items
        ]
    except Exception as e:
        logger.error(f"WIRE: Failed to get guidance: {e}")
        return []


def _get_learning_snapshot(user):
    """Get GLOE learning profile snapshot."""
    try:
        from apps.core.ai_guidance_learning.learning_models import GuidanceLearningProfile

        profile = GuidanceLearningProfile.objects.filter(user=user).first()
        if not profile:
            return {"responsiveness_score": 0.5, "total_guidance_seen": 0}

        return {
            "responsiveness_score": profile.responsiveness_score,
            "total_guidance_seen": profile.total_guidance_seen,
            "total_acknowledged": profile.total_guidance_acknowledged,
            "total_dismissed": profile.total_guidance_dismissed,
            "total_acted": profile.total_guidance_acted,
            "avg_response_time_seconds": profile.avg_response_time_seconds,
        }
    except Exception:
        return {"responsiveness_score": 0.5, "total_guidance_seen": 0}


def _compute_state_deltas(current_state):
    """
    Compute meaningful state changes.

    Since we don't store historical state snapshots yet, we report
    current notable values as the baseline.
    """
    deltas = []

    # Health changes
    health = current_state.get("health", {})
    weight_trend = health.get("weight_trend")
    if weight_trend and weight_trend != "stable":
        deltas.append({
            "module": "health",
            "label": f"Weight trend: {weight_trend}",
            "description": f"Current: {health.get('weight_current', 'N/A')} {health.get('weight_unit', 'lbs')}",
            "significant": True,
        })

    steps_avg = health.get("steps_avg_7d")
    if steps_avg and steps_avg > 0:
        deltas.append({
            "module": "health",
            "label": f"Avg steps: {steps_avg:,.0f}/day",
            "description": "7-day average",
            "significant": steps_avg >= 10000 or steps_avg < 3000,
        })

    # Goals
    goals = current_state.get("goals", {})
    overdue = goals.get("overdue_goal_count", 0)
    if overdue > 0:
        deltas.append({
            "module": "goals",
            "label": f"{overdue} overdue goal{'s' if overdue > 1 else ''}",
            "description": "Goals past their deadline",
            "significant": True,
        })

    # Habits
    habits = current_state.get("habits", {})
    streak = habits.get("longest_streak", 0)
    if streak >= 7:
        deltas.append({
            "module": "habits",
            "label": f"Longest streak: {streak} days",
            "description": "Keep it up!",
            "significant": streak >= 14,
        })

    completion_rate = habits.get("avg_completion_rate", 0)
    if completion_rate > 0:
        deltas.append({
            "module": "habits",
            "label": f"Habit completion: {completion_rate:.0%}",
            "description": "Average completion rate",
            "significant": completion_rate < 0.5 or completion_rate >= 0.9,
        })

    # Journal
    journal = current_state.get("journal", {})
    entries_30d = journal.get("entries_30d", 0)
    if entries_30d is not None:
        deltas.append({
            "module": "journal",
            "label": f"{entries_30d} journal entries (30d)",
            "description": "Monthly journaling activity",
            "significant": entries_30d == 0,
        })

    # Faith
    faith = current_state.get("faith", {})
    reading_streak = faith.get("reading_streak", 0)
    if reading_streak >= 7:
        deltas.append({
            "module": "faith",
            "label": f"Reading streak: {reading_streak} days",
            "description": "Bible reading consistency",
            "significant": reading_streak >= 14,
        })

    return deltas


def _generate_summary(ranked_items, state, learning):
    """
    Generate a natural language summary from ranked items and state.

    Template-based — no AI call needed.
    """
    if not ranked_items:
        return "No significant intelligence activity this week. Keep logging to build your profile!"

    lines = ["Here's your weekly intelligence summary:\n"]

    # Group by type
    predictions = [i for i in ranked_items if i["type"] == "prediction"]
    insights = [i for i in ranked_items if i["type"] == "insight"]
    state_changes = [i for i in ranked_items if i["type"] == "state_change"]
    guidance_acted = [i for i in ranked_items if i["type"] == "guidance_acted"]

    if predictions:
        lines.append(f"Predictions ({len(predictions)}):")
        for p in predictions[:3]:
            conf = p.get("confidence", 0)
            lines.append(f"  - {p['title']} (confidence: {conf:.0%})")

    if insights:
        lines.append(f"\nInsights ({len(insights)}):")
        for i in insights[:3]:
            lines.append(f"  - [{i.get('severity', 'info')}] {i['title']}")

    if state_changes:
        lines.append(f"\nState Changes ({len(state_changes)}):")
        for s in state_changes[:3]:
            lines.append(f"  - {s['title']}")

    if guidance_acted:
        lines.append(f"\nGuidance Acted ({len(guidance_acted)}):")
        for g in guidance_acted[:3]:
            lines.append(f"  - {g['title']}")

    # Learning summary
    resp = learning.get("responsiveness_score", 0.5)
    total = learning.get("total_guidance_seen", 0)
    if total > 0:
        if resp >= 0.7:
            lines.append("\nYou've been highly engaged with your guidance this week.")
        elif resp <= 0.3:
            lines.append("\nConsider reviewing your pending guidance items.")

    return "\n".join(lines)
