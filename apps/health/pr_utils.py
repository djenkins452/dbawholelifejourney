"""
Automatic Personal Record (PR) detection for workout sets.

Detects three types of PRs when a new ExerciseSet is created:
1. Weight PR — new weight exceeds all-time max for the exercise
2. Rep PR — new reps exceed best reps at the same weight
3. e1RM PR — new estimated 1RM exceeds all-time best estimated 1RM

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

    Creates a separate PersonalRecord for each PR type detected (weight, reps, e1rm).
    Each record includes the previous best value that was surpassed.

    Args:
        exercise_set: ExerciseSet instance (must be saved already)

    Returns:
        List of dicts with PR info, e.g.:
        [{'type': 'weight', 'previous': 185.0, 'new': 195.0}]
        Empty list if no PR detected.
    """
    from apps.health.models import ExerciseSet, PersonalRecord

    # Skip warmups and sets missing weight/reps
    if exercise_set.is_warmup:
        return []
    if not exercise_set.weight or not exercise_set.reps:
        return []

    try:
        workout_exercise = exercise_set.workout_exercise
        session = workout_exercise.session
        user = session.user
        exercise = workout_exercise.exercise
    except AttributeError:
        logger.warning("PR check skipped: exercise_set missing required relations")
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
        # Mark the set as a PR
        ExerciseSet.objects.filter(pk=exercise_set.pk).update(is_pr=True)

        # Create a PersonalRecord for EACH PR type
        for pr in prs_detected:
            previous_val = (
                Decimal(str(pr["previous"])) if pr["previous"] is not None else None
            )
            PersonalRecord.objects.create(
                user=user,
                exercise=exercise,
                weight=exercise_set.weight,
                reps=exercise_set.reps,
                achieved_date=session.date,
                workout_session=session,
                pr_type=pr["type"],
                previous_value=previous_val,
            )

        logger.info(
            "PR detected for %s on %s: %s",
            exercise.name,
            user.email,
            ", ".join(p["type"] for p in prs_detected),
        )

    return prs_detected
