"""
Automatic Personal Record (PR) detection for workout sets.

Detects four types of PRs when a new ExerciseSet is created:
1. Weight PR — new weight exceeds all-time max for the exercise
2. Rep PR — new reps exceed best reps at the same weight
3. e1RM PR — new estimated 1RM exceeds all-time best estimated 1RM
4. Time PR — new duration exceeds all-time longest hold (time-based exercises)

Uses the Brzycki formula for estimated 1RM: weight * (36 / (37 - reps))
"""

import logging
from decimal import Decimal

from django.db.models import Max

logger = logging.getLogger(__name__)


def brzycki_1rm(weight, reps):
    """Calculate estimated 1RM using Brzycki formula. Caps reps at 36."""
    reps = min(int(reps), 36)
    weight = float(weight)
    if reps <= 1:
        return weight
    return weight * (36 / (37 - reps))


def check_and_record_pr(exercise_set):
    """
    Check if an ExerciseSet is a personal record and create PersonalRecord(s).

    Creates a separate PersonalRecord for each PR type detected (weight, reps, e1rm, time).
    Each record includes the previous best value that was surpassed.

    Args:
        exercise_set: ExerciseSet instance (must be saved already)

    Returns:
        List of dicts with PR info, e.g.:
        [{'type': 'weight', 'previous': 185.0, 'new': 195.0}]
        Empty list if no PR detected.
    """
    from apps.health.models import ExerciseSet, PersonalRecord

    # Skip warmups
    if exercise_set.is_warmup:
        return []

    try:
        workout_exercise = exercise_set.workout_exercise
        session = workout_exercise.session
        user = session.user
        exercise = workout_exercise.exercise
    except AttributeError:
        logger.warning("PR check skipped: exercise_set missing required relations")
        return []

    # Route to time-based PR check if this is a time exercise
    if exercise.movement_type == "time" and exercise_set.duration_seconds:
        return _check_time_pr(exercise_set, user, exercise, session)

    # Skip sets missing weight/reps for weighted/bodyweight exercises
    if not exercise_set.weight and not exercise_set.reps:
        return []
    if not exercise_set.weight or not exercise_set.reps:
        # Bodyweight exercises with reps only can still get rep PRs
        if exercise.movement_type == "bodyweight" and exercise_set.reps:
            return _check_bodyweight_pr(exercise_set, user, exercise, session)
        return []

    new_weight = float(exercise_set.weight)
    new_reps = int(exercise_set.reps)

    # All prior non-warmup sets for this exercise by this user
    historical = ExerciseSet.objects.filter(
        workout_exercise__session__user=user,
        workout_exercise__exercise=exercise,
        is_warmup=False,
        weight__isnull=False,
        reps__isnull=False,
    ).exclude(pk=exercise_set.pk)

    prs_detected = []

    # --- 1. Weight PR ---
    max_historical_weight = historical.aggregate(
        max_w=Max("weight")
    )["max_w"]

    if max_historical_weight is None:
        # First recorded set for this exercise — it's a weight PR
        prs_detected.append({
            "type": "weight",
            "previous": None,
            "new": new_weight,
        })
    elif new_weight > float(max_historical_weight):
        prs_detected.append({
            "type": "weight",
            "previous": float(max_historical_weight),
            "new": new_weight,
        })

    # --- 2. Rep PR at same weight ---
    max_reps_at_weight = historical.filter(
        weight=exercise_set.weight
    ).aggregate(max_r=Max("reps"))["max_r"]

    if max_reps_at_weight is not None and new_reps > max_reps_at_weight:
        prs_detected.append({
            "type": "reps",
            "previous": max_reps_at_weight,
            "new": new_reps,
        })

    # --- 3. Estimated 1RM PR ---
    new_e1rm = brzycki_1rm(new_weight, new_reps)

    best_historical_e1rm = 0.0
    historical_sets = historical.values_list("weight", "reps")
    for h_weight, h_reps in historical_sets:
        e1rm = brzycki_1rm(h_weight, h_reps)
        if e1rm > best_historical_e1rm:
            best_historical_e1rm = e1rm

    # Only count e1RM PR if there IS history and the new e1RM beats it
    # AND it wasn't already captured by a weight PR (which implies e1RM PR)
    weight_pr_detected = any(p["type"] == "weight" for p in prs_detected)
    if best_historical_e1rm > 0 and new_e1rm > best_historical_e1rm:
        if not weight_pr_detected:
            prs_detected.append({
                "type": "e1rm",
                "previous": round(best_historical_e1rm, 2),
                "new": round(new_e1rm, 2),
            })

    # --- Record PRs ---
    if prs_detected:
        _record_prs(exercise_set, prs_detected, user, exercise, session)

    return prs_detected


def _check_bodyweight_pr(exercise_set, user, exercise, session):
    """Check for rep PR on bodyweight exercises (no external weight)."""
    from apps.health.models import ExerciseSet

    new_reps = int(exercise_set.reps)

    historical = ExerciseSet.objects.filter(
        workout_exercise__session__user=user,
        workout_exercise__exercise=exercise,
        is_warmup=False,
        reps__isnull=False,
        weight__isnull=True,
    ).exclude(pk=exercise_set.pk)

    max_reps = historical.aggregate(max_r=Max("reps"))["max_r"]

    prs_detected = []
    if max_reps is None:
        # First set — it's a PR
        prs_detected.append({
            "type": "reps",
            "previous": None,
            "new": new_reps,
        })
    elif new_reps > max_reps:
        prs_detected.append({
            "type": "reps",
            "previous": max_reps,
            "new": new_reps,
        })

    if prs_detected:
        _record_prs(exercise_set, prs_detected, user, exercise, session)

    return prs_detected


def _check_time_pr(exercise_set, user, exercise, session):
    """Check for time PR (longest hold) on time-based exercises."""
    from apps.health.models import ExerciseSet

    new_duration = exercise_set.duration_seconds

    historical = ExerciseSet.objects.filter(
        workout_exercise__session__user=user,
        workout_exercise__exercise=exercise,
        is_warmup=False,
        duration_seconds__isnull=False,
    ).exclude(pk=exercise_set.pk)

    max_duration = historical.aggregate(
        max_d=Max("duration_seconds")
    )["max_d"]

    prs_detected = []
    if max_duration is None:
        # First time-based set — it's a PR
        prs_detected.append({
            "type": "time",
            "previous": None,
            "new": new_duration,
        })
    elif new_duration > max_duration:
        prs_detected.append({
            "type": "time",
            "previous": max_duration,
            "new": new_duration,
        })

    if prs_detected:
        _record_prs(exercise_set, prs_detected, user, exercise, session)

    return prs_detected


def _record_prs(exercise_set, prs_detected, user, exercise, session):
    """Record detected PRs to database."""
    from apps.health.models import ExerciseSet, PersonalRecord

    ExerciseSet.objects.filter(pk=exercise_set.pk).update(is_pr=True)

    for pr in prs_detected:
        previous_val = (
            Decimal(str(pr["previous"])) if pr["previous"] is not None else None
        )
        pr_kwargs = {
            "user": user,
            "exercise": exercise,
            "achieved_date": session.date,
            "workout_session": session,
            "pr_type": pr["type"],
            "previous_value": previous_val,
        }

        if pr["type"] == "time":
            pr_kwargs["duration_seconds"] = exercise_set.duration_seconds
        else:
            pr_kwargs["weight"] = exercise_set.weight
            pr_kwargs["reps"] = exercise_set.reps

        PersonalRecord.objects.create(**pr_kwargs)

    logger.info(
        "PR detected for %s on %s: %s",
        exercise.name,
        user.email,
        ", ".join(p["type"] for p in prs_detected),
    )
