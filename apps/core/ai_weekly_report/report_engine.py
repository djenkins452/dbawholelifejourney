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
from apps.core.ai_observability.instrumentation import log_engine_run as _instrument_engine_run

logger = logging.getLogger(__name__)


@_instrument_engine_run("WIRE", 3)
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

        # Step 3.5: ICQG quality gate (non-blocking)
        try:
            from apps.core.ai_quality.quality_gate import filter_briefing_items
            ranked = filter_briefing_items(user, ranked)
        except Exception as e:
            logger.warning(f"WIRE: ICQG filter failed (continuing): {e}")

        # Step 4: Generate summary
        summary = _generate_summary(ranked, current_state, learning)

        # Step 4.5: Apply persona rendering (non-blocking)
        summary = _apply_persona(user, summary)

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
    Generate a Weekly Strategic Review.

    Phase 4 upgrade: Instead of a list summary, generates a
    7-section strategic review.

    Structure:
    1. Momentum trajectory
    2. Drift zones
    3. Leadership decisions made
    4. Avoidance patterns
    5. Relationship temperature
    6. Governance compliance
    7. Next week strategic emphasis
    """
    sections = []

    # Group items by type
    predictions = [i for i in ranked_items if i.get("type") == "prediction"]
    insights = [i for i in ranked_items if i.get("type") == "insight"]
    state_changes = [i for i in ranked_items if i.get("type") == "state_change"]
    guidance_acted = [i for i in ranked_items if i.get("type") == "guidance_acted"]

    # 1. Momentum trajectory
    momentum = _build_momentum_trajectory(state_changes, state, learning)
    sections.append(f"MOMENTUM TRAJECTORY: {momentum}")

    # 2. Drift zones
    drift_zones = _build_drift_zones(insights, predictions)
    if drift_zones:
        sections.append(f"DRIFT ZONES: {drift_zones}")

    # 3. Leadership decisions made
    decisions = _build_decisions(guidance_acted)
    if decisions:
        sections.append(f"DECISIONS MADE: {decisions}")

    # 4. Avoidance patterns
    avoidance = _build_avoidance_patterns(insights, state)
    if avoidance:
        sections.append(f"AVOIDANCE PATTERNS: {avoidance}")

    # 5. Relationship temperature
    relational = _build_relationship_temperature(state)
    if relational:
        sections.append(f"RELATIONSHIP TEMPERATURE: {relational}")

    # 6. Governance compliance
    governance = _build_governance_compliance(learning)
    sections.append(f"GOVERNANCE COMPLIANCE: {governance}")

    # 7. Next week emphasis
    emphasis = _build_next_week_emphasis(
        insights, predictions, state_changes, state
    )
    sections.append(f"NEXT WEEK EMPHASIS: {emphasis}")

    if not sections:
        return "No significant intelligence activity this week. Keep logging to build your profile."

    return "\n\n".join(sections)


def _build_momentum_trajectory(state_changes, state, learning):
    """Section 1: Are things getting better, worse, or flat?"""
    parts = []
    significant = [s for s in state_changes if s.get("significant")]
    if significant:
        for s in significant[:3]:
            parts.append(s.get("title", s.get("label", "")))

    habits = state.get("habits", {})
    completion = habits.get("avg_completion_rate", 0)
    if completion >= 0.8:
        parts.append(f"Habit execution strong ({completion:.0%}).")
    elif completion >= 0.5:
        parts.append(f"Habit execution moderate ({completion:.0%}).")
    elif completion > 0:
        parts.append(f"Habit execution declining ({completion:.0%}).")

    resp = learning.get("responsiveness_score", 0.5)
    if resp >= 0.7:
        parts.append("High engagement with guidance.")
    elif resp <= 0.3:
        parts.append("Low engagement with guidance — review pending items.")

    return " ".join(parts) if parts else "Steady state. No significant shifts."


def _build_drift_zones(insights, predictions):
    """Section 2: Where drift is occurring or forming."""
    drift_items = []
    for i in insights:
        if i.get("severity") in ("warning", "critical"):
            drift_items.append(i.get("title", ""))
    for p in predictions:
        if "drift" in p.get("title", "").lower():
            drift_items.append(p.get("title", ""))

    if not drift_items:
        return None
    return " ".join(drift_items[:4])


def _build_decisions(guidance_acted):
    """Section 3: What the user acted on this week."""
    if not guidance_acted:
        return None
    items = [g.get("title", "") for g in guidance_acted[:4]]
    return " ".join(items)


def _build_avoidance_patterns(insights, state):
    """Section 4: What's being avoided."""
    patterns = []
    goals = state.get("goals", {})
    overdue = goals.get("overdue_goal_count", 0)
    if overdue > 0:
        patterns.append(f"{overdue} goals remain overdue.")

    journal = state.get("journal", {})
    days = journal.get("days_since_entry", 0)
    if days and days > 5:
        patterns.append(f"No journal entry in {days} days.")

    # Look for dismissed insights
    dismissed = [i for i in insights if i.get("status") == "dismissed"]
    if len(dismissed) >= 3:
        patterns.append(f"{len(dismissed)} insights dismissed — potential avoidance.")

    return " ".join(patterns) if patterns else None


def _build_relationship_temperature(state):
    """Section 5: Relationship health."""
    rel = state.get("relationships", {})
    drifting = rel.get("drifting_count", 0)
    healthy = rel.get("healthy_count", 0)

    if drifting == 0 and healthy == 0:
        return None

    parts = []
    if healthy > 0:
        parts.append(f"{healthy} relationship{'s' if healthy > 1 else ''} in good standing.")
    if drifting > 0:
        parts.append(f"{drifting} showing drift — reconnection needed.")
    return " ".join(parts)


def _build_governance_compliance(learning):
    """Section 6: How well the user is working with the CoS."""
    resp = learning.get("responsiveness_score", 0.5)
    total = learning.get("total_guidance_seen", 0)
    acted = learning.get("total_acted", 0)

    if total == 0:
        return "No guidance interactions this week."

    rate = acted / total if total > 0 else 0
    if rate >= 0.6:
        return f"Strong compliance — {rate:.0%} guidance acted on. Responsiveness: {resp:.2f}."
    if rate >= 0.3:
        return f"Moderate compliance — {rate:.0%} guidance acted on. Room to improve."
    return f"Low compliance — only {rate:.0%} guidance acted on. Review your pending items."


def _build_next_week_emphasis(insights, predictions, state_changes, state):
    """Section 7: Strategic emphasis for next week."""
    # Look at predictions for trajectory
    high_conf = [p for p in predictions if p.get("confidence_score", p.get("confidence", 0)) >= 0.7]

    if high_conf:
        return f"Watch: {high_conf[0].get('title', 'emerging pattern')}. Adjust proactively."

    overdue = state.get("goals", {}).get("overdue_goal_count", 0)
    if overdue > 2:
        return "Priority: close overdue goals before adding new commitments."

    warnings = [i for i in insights if i.get("severity") == "warning"]
    if warnings:
        return f"Address: {warnings[0].get('title', 'flagged item')}."

    return "Maintain current trajectory. Protect Tier-1 behaviors."


def _apply_persona(user, summary):
    """Apply PIL persona rendering to weekly summary (non-blocking)."""
    if not summary:
        return summary
    try:
        from apps.core.ai_persona.persona_engine import render_with_persona

        return render_with_persona(
            user=user,
            base_message=summary,
            message_type="weekly_report",
        )
    except Exception:
        return summary  # fail-safe
