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

    Uses the contract-driven completer so that whatever the dashboard SHOWS
    as the Wake Up item is exactly what gets completed (no Task-vs-Schedule
    keyword guessing).
    """
    return complete_wake_up(user)


# ── Contract-driven Wake Up completion (the robust path) ──────────────
# Tokens that identify a Wake Up execution item by title. Case-insensitive.
_WAKE_UP_TOKENS = ("wake up", "wake-up", "wakeup")


def complete_wake_up(user, *, target_date=None, execution_contract=None) -> dict[str, Any]:
    """Deterministically complete today's Wake Up item.

    Strategy: locate the Wake Up item in the canonical execution contract
    (`build_today_execution`) and complete THAT exact item via its canonical
    mutation, keyed by source_type + source_id. This removes the
    Task-vs-RoutineSchedule ambiguity entirely — we complete whatever the
    dashboard actually displays.

    Falls back to the keyword facade only when no Wake Up item is surfaced
    in today's contract (covers schedules/tasks not yet in the contract).

    Idempotent: already-completed items are skipped. Never raises on the
    request path. Heavily instrumented for production tracing.
    """
    uid = getattr(user, "id", "?")
    matched: list[dict] = []

    try:
        if execution_contract is not None:
            contract = execution_contract
        else:
            from apps.core.execution.today_execution import build_today_execution
            contract = build_today_execution(user)
        items = contract.get("items", []) or []
    except Exception:
        logger.warning(
            "WAKE_UP build_today_execution failed user=%s", uid, exc_info=True,
        )
        items = []

    for item in items:
        title = (item.get("title") or "").strip().lower()
        if any(tok in title for tok in _WAKE_UP_TOKENS):
            matched.append(item)

    # Trace exactly what we found — so production logs answer "did the
    # lookup match, and what source type was it?"
    logger.info(
        "WAKE_UP_TRACE user=%s contract_items=%d matched=%s",
        uid, len(items),
        [(m.get("source_type"), m.get("source_id"), m.get("title"),
          m.get("completed_today")) for m in matched],
    )

    if not matched:
        # Nothing surfaced today — fall back to the keyword facade in case
        # a schedule/task exists outside today's contract window.
        logger.info("WAKE_UP_FALLBACK_TO_FACADE user=%s", uid)
        return apply_verified_completion(user, "wake_up", target_date=target_date)

    completed_any = False
    already = False
    for item in matched:
        if item.get("completed_today"):
            already = True
            continue
        if _complete_execution_item(user, item, target_date=target_date):
            completed_any = True

    reason = (
        "authenticated_presence" if completed_any
        else ("already_complete" if already else "no_match")
    )
    logger.info(
        "WAKE_UP_RESULT user=%s completed=%s reason=%s",
        uid, completed_any, reason,
    )
    return {
        "activity": "wake_up",
        "completed": completed_any,
        "reason": reason,
        "source": "auto",
        "matched": [m.get("title") for m in matched],
        "source_types": [m.get("source_type") for m in matched],
    }


def _complete_execution_item(user, item, *, target_date=None) -> bool:
    """Complete a single execution item via its canonical mutation.

    Dispatches by source_type to the EXISTING canonical write path — this is
    a router to canonical mutations, not a new write path:
      - task          → Task.mark_complete()
      - routine_item  → auto_complete_routine_schedules() against the exact
                        schedule's own name (guaranteed match, auto provenance)
    """
    stype = item.get("source_type")
    sid = item.get("source_id")
    try:
        if stype == "task":
            from apps.life.models import Task
            t = Task.objects.filter(pk=sid, user=user).first()
            if t and t.completion_status == "pending":
                t.mark_complete()
                logger.info("WAKE_UP_COMPLETED_TASK user=%s task=%s",
                            getattr(user, "id", "?"), sid)
                return True
        elif stype == "routine_item":
            from apps.life.models import RoutineSchedule
            from apps.life.services.routine_helpers import (
                auto_complete_routine_schedules,
            )
            sched = RoutineSchedule.objects.filter(
                pk=sid, routine__user=user,
            ).first()
            if sched:
                # Use the schedule's OWN name as keyword → guaranteed
                # icontains match, with canonical 'auto' provenance.
                res = auto_complete_routine_schedules(
                    user=user, keyword=sched.name, source="auto",
                    target_date=target_date,
                )
                if res:
                    logger.info(
                        "WAKE_UP_COMPLETED_ROUTINE user=%s schedule=%s name=%r",
                        getattr(user, "id", "?"), sid, sched.name,
                    )
                    return True
    except Exception:
        logger.warning(
            "WAKE_UP complete item failed stype=%s sid=%s user=%s",
            stype, sid, getattr(user, "id", "?"), exc_info=True,
        )
    return False
