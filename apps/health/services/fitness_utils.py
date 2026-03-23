# ==============================================================================
# File: fitness_utils.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Query utilities for fitness intelligence — volume tracking,
#              exercise history, and personal bests.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-10
# ==============================================================================
"""
Fitness Utilities — Query helpers for training volume and exercise analytics.

Provides reusable functions for:
  - Weekly training volume calculation
  - Exercise-level volume history over time
  - Personal bests (weight, reps, e1RM, time)
  - Longest hold for time-based exercises

These utilities are designed for the fitness intelligence layer and can be
consumed by PIE rules, CoS context builders, and API endpoints.
"""

import logging
from datetime import timedelta
from decimal import Decimal

from django.db.models import Max, Sum

logger = logging.getLogger(__name__)


def get_weekly_volume(user, week_start_date):
    """
    Calculate total training volume for a given week.

    Volume = sum of (weight × reps) for all non-warmup sets,
    including bodyweight volume (bodyweight_used × reps).

    Args:
        user: Django User instance.
        week_start_date: date object for the Monday of the target week.

    Returns:
        Dict with total_volume (float), set_count (int), workout_count (int).
    """
    from apps.health.models import ExerciseSet, WorkoutSession

    week_end = week_start_date + timedelta(days=6)

    workouts = WorkoutSession.objects.filter(
        user=user,
        date__gte=week_start_date,
        date__lte=week_end,
        completed_at__isnull=False,
    )

    sets = ExerciseSet.objects.filter(
        workout_exercise__session__in=workouts,
        is_warmup=False,
    )

    total_volume = 0.0
    set_count = 0
    for s in sets.select_related("workout_exercise__exercise"):
        set_count += 1
        v = s.volume
        if v is not None:
            total_volume += v

    return {
        "total_volume": round(total_volume, 1),
        "set_count": set_count,
        "workout_count": workouts.count(),
    }


def get_exercise_volume_history(user, exercise, weeks=8):
    """
    Get weekly volume history for a specific exercise.

    Args:
        user: Django User instance.
        exercise: Exercise model instance.
        weeks: Number of weeks of history to retrieve.

    Returns:
        List of dicts: [{"week_start": date, "volume": float, "sets": int}]
        Ordered from oldest to newest.
    """
    from apps.health.models import ExerciseSet

    from apps.core.time.system_clock import get_current_time

    today = get_current_time().date()
    # Start from the most recent Monday
    days_since_monday = today.weekday()
    current_monday = today - timedelta(days=days_since_monday)

    history = []
    for i in range(weeks - 1, -1, -1):
        week_start = current_monday - timedelta(weeks=i)
        week_end = week_start + timedelta(days=6)

        sets = ExerciseSet.objects.filter(
            workout_exercise__session__user=user,
            workout_exercise__exercise=exercise,
            workout_exercise__session__date__gte=week_start,
            workout_exercise__session__date__lte=week_end,
            workout_exercise__session__completed_at__isnull=False,
            is_warmup=False,
        )

        volume = 0.0
        set_count = 0
        for s in sets:
            set_count += 1
            v = s.volume
            if v is not None:
                volume += v

        history.append({
            "week_start": week_start,
            "volume": round(volume, 1),
            "sets": set_count,
        })

    return history


def get_personal_bests(user, exercise):
    """
    Get all personal records for a user/exercise combination.

    Args:
        user: Django User instance.
        exercise: Exercise model instance.

    Returns:
        Dict with keys for each PR type:
        {
            "weight": {"value": float, "reps": int, "date": date} or None,
            "reps": {"value": int, "weight": float, "date": date} or None,
            "e1rm": {"value": float, "date": date} or None,
            "time": {"value": int, "date": date} or None,
        }
    """
    from apps.health.models import PersonalRecord

    records = PersonalRecord.objects.filter(
        user=user,
        exercise=exercise,
    ).order_by("-achieved_date")

    result = {"weight": None, "reps": None, "e1rm": None, "time": None}

    for pr in records:
        if pr.pr_type == "weight" and result["weight"] is None:
            result["weight"] = {
                "value": float(pr.weight) if pr.weight else None,
                "reps": pr.reps,
                "date": pr.achieved_date,
            }
        elif pr.pr_type == "reps" and result["reps"] is None:
            result["reps"] = {
                "value": pr.reps,
                "weight": float(pr.weight) if pr.weight else None,
                "date": pr.achieved_date,
            }
        elif pr.pr_type == "e1rm" and result["e1rm"] is None:
            result["e1rm"] = {
                "value": pr.estimated_1rm if pr.weight and pr.reps else None,
                "date": pr.achieved_date,
            }
        elif pr.pr_type == "time" and result["time"] is None:
            result["time"] = {
                "value": pr.duration_seconds,
                "date": pr.achieved_date,
            }

    return result


def get_longest_hold(user, exercise):
    """
    Get the longest hold (max duration_seconds) for a time-based exercise.

    Args:
        user: Django User instance.
        exercise: Exercise model instance.

    Returns:
        Int (seconds) or None if no time-based sets recorded.
    """
    from apps.health.models import ExerciseSet

    result = ExerciseSet.objects.filter(
        workout_exercise__session__user=user,
        workout_exercise__exercise=exercise,
        is_warmup=False,
        duration_seconds__isnull=False,
    ).aggregate(max_d=Max("duration_seconds"))

    return result["max_d"]
