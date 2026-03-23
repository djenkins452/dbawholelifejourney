"""
Phase 4 — Signal Feedback Service

Public API for recording user feedback on behavioral signals.
The system ONLY learns when the user explicitly responds yes or no.

STRICT RULES:
- No updates to execution truth directly
- No decision logic beyond recording + optional completion trigger
- No side effects beyond storing feedback + calling existing services
- Only possible_completion + yes triggers completion
- All other signal types: record only, no action
"""

import hashlib
import logging
from typing import Optional

from django.utils import timezone

logger = logging.getLogger(__name__)


def record_signal_feedback(user, signal: dict, response: str) -> Optional[dict]:
    """Record user feedback on a behavioral signal.

    Args:
        user: User instance
        signal: Signal dict from Phase 3 presenter (must have type, domain,
                item, source fields; fingerprint is generated if missing)
        response: "yes" or "no" (case-insensitive)

    Returns:
        dict with result info, or None if response was invalid.

    Side effects:
        - Stores a SignalFeedback record
        - If response is "yes" AND signal type is "possible_completion",
          triggers completion via existing services
    """
    # Validate response — only yes/no accepted
    response = (response or "").strip().lower()
    if response not in ("yes", "no"):
        logger.debug(
            "[SIGNAL FEEDBACK] Ignored invalid response=%r user=%s",
            response, user.id,
        )
        return None

    # Extract signal fields
    signal_type = signal.get("type", "")
    domain = signal.get("domain", "")
    item = signal.get("item", "")
    source = signal.get("source", "")
    fingerprint = signal.get("fingerprint") or _generate_fingerprint(signal)

    # Store feedback record
    from apps.core.signals.models import SignalFeedback

    feedback = SignalFeedback.objects.create(
        user=user,
        signal_type=signal_type,
        domain=domain,
        item=item or None,
        fingerprint=fingerprint,
        response=response,
        source=source,
    )

    logger.info(
        "[SIGNAL FEEDBACK] Recorded: user=%s type=%s domain=%s item=%s "
        "response=%s fingerprint=%s",
        user.id, signal_type, domain, item, response, fingerprint,
    )

    result = {
        "recorded": True,
        "feedback_id": feedback.id,
        "completion_triggered": False,
    }

    # Execution bridge: only possible_completion + yes triggers completion
    if response == "yes" and signal_type == "possible_completion":
        completion_result = _trigger_completion(user, domain, item)
        result["completion_triggered"] = completion_result.get("success", False)
        result["completion_detail"] = completion_result

    return result


def _generate_fingerprint(signal: dict) -> str:
    """Generate a deterministic fingerprint for a signal.

    Format: {type}:{domain}:{item}:{date}
    Uses today's date if no timestamp in signal.
    """
    signal_type = signal.get("type", "unknown")
    domain = signal.get("domain", "unknown")
    item = signal.get("item", "unknown")

    ts = signal.get("timestamp")
    if ts and hasattr(ts, "date"):
        date_str = ts.date().isoformat()
    elif ts and hasattr(ts, "isoformat"):
        date_str = ts.isoformat()[:10]
    else:
        date_str = timezone.localdate().isoformat()

    raw = f"{signal_type}:{domain}:{item}:{date_str}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Execution Bridge — Controlled completion via existing services
# ---------------------------------------------------------------------------

# Signal item → routine name mapping (mirrors execution_truth_engine bridges)
_ITEM_TO_ROUTINE_NAMES = {
    "prayer": {"prayer time", "prayer", "morning prayer", "evening prayer"},
    "bible_reading": {
        "bible reading", "bible study", "scripture reading", "devotional",
    },
    "workout": {
        "workout", "exercise", "gym", "training", "morning workout",
        "evening workout",
    },
    "running": {"run", "running"},
    "walking": {"walk", "walking"},
    "yoga": {"yoga"},
    "journal_entry": {
        "journal", "journaling", "journal entry", "daily journal",
        "morning journal", "evening journal",
    },
}


def _trigger_completion(user, domain: str, item: str) -> dict:
    """Trigger completion for a confirmed possible_completion signal.

    MUST use existing completion services — never write to models directly.
    Only called for possible_completion + yes response.

    Returns dict with success bool and detail.
    """
    try:
        return _complete_via_routine(user, domain, item)
    except Exception:
        logger.error(
            "[SIGNAL FEEDBACK] Completion failed: user=%s domain=%s item=%s",
            user.id, domain, item,
            exc_info=True,
        )
        return {"success": False, "reason": "completion_error"}


def _complete_via_routine(user, domain: str, item: str) -> dict:
    """Find and complete the matching routine item for today.

    Uses toggle_routine_completion() — the public routine completion API.
    """
    from apps.core.utils import get_user_today
    from apps.life.models import RoutineSchedule

    today = get_user_today(user)
    day_of_week = today.weekday()

    # Get candidate routine names for this signal item
    candidate_names = _ITEM_TO_ROUTINE_NAMES.get(item, set())
    if not candidate_names:
        logger.info(
            "[SIGNAL FEEDBACK] No routine mapping for item=%s, skipping",
            item,
        )
        return {"success": False, "reason": "no_routine_mapping"}

    # Find matching active schedule for today
    schedules = RoutineSchedule.objects.filter(
        routine__user=user,
        routine__is_active=True,
        is_active=True,
    ).select_related("routine")

    matching_schedule = None
    for schedule in schedules:
        name_lower = schedule.name.lower().strip()
        if name_lower not in candidate_names:
            continue
        # Check if scheduled for today
        if schedule.specific_date:
            if schedule.specific_date == today:
                matching_schedule = schedule
                break
        elif schedule.applies_to_day(day_of_week):
            matching_schedule = schedule
            break

    if not matching_schedule:
        logger.info(
            "[SIGNAL FEEDBACK] No matching schedule for domain=%s item=%s "
            "user=%s",
            domain, item, user.id,
        )
        return {"success": False, "reason": "no_matching_schedule"}

    # Check if already completed via existing truth
    from apps.life.models import RoutineLog

    existing_log = RoutineLog.objects.filter(
        user=user,
        schedule=matching_schedule,
        scheduled_date=today,
        log_status__in=("completed", "completed_late"),
    ).exists()

    if existing_log:
        logger.info(
            "[SIGNAL FEEDBACK] Already completed: schedule=%s user=%s",
            matching_schedule.name, user.id,
        )
        return {"success": True, "reason": "already_completed"}

    # Use the public completion service
    from apps.life.services.routine_helpers import toggle_routine_completion

    result = toggle_routine_completion(
        user=user,
        schedule=matching_schedule,
        target_date=today,
    )

    logger.info(
        "[SIGNAL FEEDBACK] Completion triggered: schedule=%s result=%s user=%s",
        matching_schedule.name, result, user.id,
    )

    return {
        "success": result.get("is_completed", False),
        "reason": "completed",
        "schedule_name": matching_schedule.name,
    }
