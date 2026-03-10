# ==============================================================================
# File: user_context.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Gather health-relevant user context for PIE analysis
#              personalization. All data pulled dynamically from WLJ models.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-10
# ==============================================================================
"""
Health User Context — Pulls relevant user data for analysis personalization.

Gathers from:
  - HealthProfile: activity level, weight goal
  - SleepEntry: recent 7-day sleep history and trends
  - Task: recurring morning tasks → inferred wake time
  - PersonalFact: health-related biographical facts
  - LifeGoal: active health/fitness goals
"""

import logging

logger = logging.getLogger(__name__)


def get_health_user_context(user):
    """
    Gather health-relevant user context for PIE analysis personalization.

    Returns dict with available context — missing data returns None/empty.
    Never raises; logs and continues on any model access failure.
    """
    ctx = {
        'activity_level': None,
        'has_weight_goal': False,
        'weight_goal': None,
        'recent_sleep_avg_minutes': None,
        'recent_sleep_trend': None,
        'wake_time': None,
        'health_goals': [],
        'health_facts': [],
    }

    # ── HealthProfile ────────────────────────────────────────────────
    try:
        from apps.health.models import HealthProfile
        profile = HealthProfile.objects.filter(user=user).first()
        if profile:
            ctx['activity_level'] = profile.activity_level or None
            if profile.has_weight_goal:
                ctx['has_weight_goal'] = True
                ctx['weight_goal'] = {
                    'target': float(profile.weight_goal),
                    'unit': profile.weight_goal_unit,
                }
    except Exception:
        logger.debug("Health context: HealthProfile unavailable", exc_info=True)

    # ── Recent Sleep History (7 days) ────────────────────────────────
    try:
        from apps.health.models import SleepEntry
        from apps.core.ai_insights.pattern_utils import (
            compute_simple_trend,
            get_time_window,
        )

        window_start, window_end = get_time_window(days=7)
        recent_sleep = list(
            SleepEntry.objects.filter(
                user=user,
                status='active',
                sleep_date__gte=window_start.date(),
            )
            .order_by('sleep_date')
            .values_list('sleep_date', 'asleep_duration_minutes')
        )

        if recent_sleep:
            durations = [
                d for _, d in recent_sleep if d is not None
            ]
            if durations:
                ctx['recent_sleep_avg_minutes'] = round(
                    sum(durations) / len(durations)
                )

            # Trend from entries with duration data
            trend_data = [
                (dt, float(d)) for dt, d in recent_sleep if d is not None
            ]
            if len(trend_data) >= 2:
                trend = compute_simple_trend(trend_data)
                if trend:
                    ctx['recent_sleep_trend'] = trend['direction']
    except Exception:
        logger.debug("Health context: SleepEntry unavailable", exc_info=True)

    # ── Wake Time (from recurring morning tasks) ─────────────────────
    try:
        from apps.life.models import Task
        from datetime import time as dt_time

        # Find recurring tasks with early morning scheduled times
        morning_task = (
            Task.objects.filter(
                user=user,
                is_recurring=True,
                status='active',
            )
            .exclude(scheduled_time__isnull=True)
            .order_by('scheduled_time')
            .first()
        )
        if morning_task and morning_task.scheduled_time:
            sched = morning_task.scheduled_time
            # Only use if it's a morning time (before 9 AM)
            if hasattr(sched, 'hour'):
                if sched.hour < 9:
                    ctx['wake_time'] = sched.strftime('%H:%M')
            elif isinstance(sched, str) and ':' in sched:
                hour = int(sched.split(':')[0])
                if hour < 9:
                    ctx['wake_time'] = sched[:5]
    except Exception:
        logger.debug("Health context: Task wake time unavailable", exc_info=True)

    # ── Personal Facts (health-related) ──────────────────────────────
    try:
        from apps.core.ai_memory.models import PersonalFact

        facts = PersonalFact.objects.filter(
            user=user,
            is_active=True,
            fact_type='health_condition',
        ).values_list('fact_text', flat=True)[:5]

        ctx['health_facts'] = list(facts)
    except Exception:
        logger.debug("Health context: PersonalFact unavailable", exc_info=True)

    # ── Active Health/Fitness Goals ──────────────────────────────────
    try:
        from apps.purpose.models import LifeGoal

        goals = LifeGoal.objects.filter(
            user=user,
            status='active',
            domain__in=['health', 'fitness'],
        ).values_list('title', flat=True)[:5]

        ctx['health_goals'] = list(goals)
    except Exception:
        logger.debug("Health context: LifeGoal unavailable", exc_info=True)

    return ctx
