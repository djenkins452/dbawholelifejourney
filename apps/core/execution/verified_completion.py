"""
VERIFIED AUTO-COMPLETION — deterministic completion from verified in-app activity.

This is the FORMAL category for "WLJ is the place the activity happened, so the
matching task auto-completes." It is NOT inferred completion. It is NOT LLM
reasoning. It only fires when there is deterministic proof of activity.

    raw data → signals → completion → Beth/UI

Architecture guarantees:
  - **Single write path.** Every completion flows through the EXISTING
    canonical primitives — `auto_complete_routine_schedules()` (RoutineSchedule
    → RoutineLog, provenance-tracked) and
    `RoutineTaskService.auto_complete_routine_task()` (Task). This module is a
    typed, named facade over those — NOT a second engine.
  - **Provenance.** Each completion records `RoutineLog.completion_source`
    using the existing enum (SOURCE_AUTO / SOURCE_WORKOUT / SOURCE_BIBLE) plus
    a human `reason` for observability (authenticated_presence /
    workout_completed / bible_activity_completed).
  - **Idempotent.** The underlying primitives are first-write-wins per day, so
    repeated calls are safe no-ops.
  - **Never infers.** Only the registered, deterministic activities below are
    eligible. No pattern/streak/schedule guessing.

Public API:
    apply_verified_completion(user, activity, *, source_object_id=None,
                              completion_time=None, target_date=None) -> dict
    on_authenticated_presence(user) -> dict   # convenience: wake_up
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ── The formal category registry ──────────────────────────────────────
# Maps a verified activity to: the schedule-match keywords, the canonical
# RoutineLog.completion_source enum value, the human provenance reason, and
# the Task title keywords. To add a new verified activity, add one entry —
# do not add a new write path.
VERIFIED_ACTIVITIES: dict[str, dict[str, Any]] = {
    "wake_up": {
        # RULE 1 — authenticated activity proves wakefulness.
        "schedule_keywords": ["wake up"],
        "task_keywords": ["Wake Up"],
        "source": "auto",                      # RoutineLog.SOURCE_AUTO
        "reason": "authenticated_presence",
    },
    "workout": {
        # RULE 2 — a workout completed INSIDE WLJ.
        "schedule_keywords": ["workout"],
        "task_keywords": ["Workout"],
        "source": "workout",                   # RoutineLog.SOURCE_WORKOUT
        "reason": "workout_completed",
    },
    "bible": {
        # RULE 3 — Bible reading / study completed INSIDE WLJ.
        "schedule_keywords": ["bible", "reading"],
        "task_keywords": ["Bible", "Quiet Time"],
        "source": "bible",                     # RoutineLog.SOURCE_BIBLE
        "reason": "bible_activity_completed",
    },
}


def apply_verified_completion(
    user,
    activity: str,
    *,
    source_object_id=None,
    completion_time=None,
    target_date=None,
) -> dict[str, Any]:
    """Apply verified auto-completion for one deterministic activity.

    Args:
        user: Django User.
        activity: one of VERIFIED_ACTIVITIES keys ('wake_up', 'workout', 'bible').
        source_object_id: PK of the proving object (e.g. WorkoutSession.pk)
            for RoutineLog traceability. Optional.
        completion_time: aware datetime of the activity (for on-time/late
            classification). Defaults to now in the primitive.
        target_date: date to complete for. Defaults to user-local today.

    Returns:
        dict: {activity, completed, reason, source, schedules, tasks}
        Never raises on the request path — failures degrade to completed=False.
    """
    spec = VERIFIED_ACTIVITIES.get(activity)
    if not spec:
        logger.warning("verified_completion: unknown activity %r", activity)
        return {
            "activity": activity, "completed": False,
            "reason": "unknown_activity", "source": None,
            "schedules": [], "tasks": [],
        }

    schedules_completed: list[dict] = []
    tasks_completed: list[int] = []

    # ── Path 1: RoutineSchedule → RoutineLog (provenance-tracked) ──
    try:
        from apps.life.services.routine_helpers import (
            auto_complete_routine_schedules,
        )
        for kw in spec["schedule_keywords"]:
            res = auto_complete_routine_schedules(
                user=user,
                keyword=kw,
                source=spec["source"],
                completion_time=completion_time,
                source_object_id=source_object_id,
                target_date=target_date,
            )
            if res:
                schedules_completed.extend(res)
    except Exception:
        logger.warning(
            "verified_completion: schedule path failed activity=%s user=%s",
            activity, getattr(user, "id", "?"), exc_info=True,
        )

    # ── Path 2: Task (is_routine title match) ──
    try:
        from apps.life.services.routine_service import RoutineTaskService
        for tkw in spec["task_keywords"]:
            task = RoutineTaskService.auto_complete_routine_task(user, tkw)
            if task:
                tasks_completed.append(task.id)
    except Exception:
        logger.warning(
            "verified_completion: task path failed activity=%s user=%s",
            activity, getattr(user, "id", "?"), exc_info=True,
        )

    completed = bool(schedules_completed or tasks_completed)
    if completed:
        logger.info(
            "VERIFIED_COMPLETION user=%s activity=%s reason=%s source=%s "
            "schedules=%s tasks=%s",
            getattr(user, "id", "?"), activity, spec["reason"], spec["source"],
            [r.get("schedule_id") for r in schedules_completed],
            tasks_completed,
        )

    return {
        "activity": activity,
        "completed": completed,
        "reason": spec["reason"],
        "source": spec["source"],
        "schedules": schedules_completed,
        "tasks": tasks_completed,
    }


def on_authenticated_presence(user) -> dict[str, Any]:
    """RULE 1 convenience: any authenticated activity proves the user is awake.

    Idempotent — safe to call from every authenticated entry point (login
    signal, dashboard load, CoS first interaction). Returns the verified
    completion result for 'wake_up'.
    """
    return apply_verified_completion(user, "wake_up")
