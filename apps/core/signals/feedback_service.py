"""
Phase 4 — Signal Feedback Service (v4.1 — Integrity Hardened)

Public API for recording user feedback on behavioral signals.
The system ONLY learns when the user explicitly responds yes or no.

STRICT RULES:
- No updates to execution truth directly
- No decision logic beyond recording + optional completion trigger
- No side effects beyond storing feedback + calling existing services
- Only possible_completion + yes triggers completion
- All other signal types: record only, no action

v4.1 HARDENING:
- Idempotency guard via execution truth pre-check
- Fingerprint normalization (lowercase, strip)
- Handler abstraction for multi-domain completion
- Safe execution bridge (4-gate check)
"""

import hashlib
import logging
from typing import Callable, Dict, Optional

from django.utils import timezone

logger = logging.getLogger(__name__)


def record_signal_feedback(user, signal: dict, response: str) -> Optional[dict]:
    """Record user feedback on a behavioral signal.

    Args:
        user: User instance
        signal: Signal dict from Phase 3 presenter (must have type, domain,
                item, source fields; fingerprint is generated if missing).
                The caller MUST pass the exact signal dict that was presented
                to the user — no guessing based on text alone.
        response: "yes" or "no" (case-insensitive)

    Returns:
        dict with result info, or None if response was invalid.

    Side effects:
        - Stores a SignalFeedback record
        - If response is "yes" AND signal type is "possible_completion"
          AND handler exists AND item not already completed,
          triggers completion via existing services
    """
    # Gate 1: Validate response — only yes/no accepted
    response = (response or "").strip().lower()
    if response not in ("yes", "no"):
        logger.debug(
            "[SIGNAL FEEDBACK] Ignored invalid response=%r user=%s",
            response, user.id,
        )
        return None

    # Extract and normalize signal fields
    signal_type = (signal.get("type") or "").strip().lower()
    domain = (signal.get("domain") or "").strip().lower()
    item = (signal.get("item") or "").strip().lower()
    source = (signal.get("source") or "").strip().lower()
    fingerprint = signal.get("fingerprint") or _generate_fingerprint(signal)

    # Store feedback record (always, regardless of completion outcome)
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

    # Gate 2: Only possible_completion triggers completion
    if signal_type != "possible_completion":
        return result

    # Gate 3: Only "yes" triggers completion
    if response != "yes":
        return result

    # Gate 4: Handler must exist for this domain
    handler = _get_completion_handler(domain, item)
    if handler is None:
        logger.info(
            "[SIGNAL FEEDBACK] No handler for domain=%s item=%s, "
            "feedback recorded only",
            domain, item,
        )
        result["completion_detail"] = {
            "success": False,
            "reason": "no_handler",
        }
        return result

    # Gate 5: Idempotency — check execution truth BEFORE triggering
    if _is_already_completed(user, domain, item):
        logger.info(
            "[SIGNAL FEEDBACK] Already completed (truth check): "
            "domain=%s item=%s user=%s",
            domain, item, user.id,
        )
        result["completion_triggered"] = True
        result["completion_detail"] = {
            "success": True,
            "reason": "already_completed",
        }
        return result

    # All gates passed — trigger completion
    try:
        completion_result = handler(user, domain, item)
        result["completion_triggered"] = completion_result.get("success", False)
        result["completion_detail"] = completion_result
    except Exception:
        logger.error(
            "[SIGNAL FEEDBACK] Completion failed: user=%s domain=%s item=%s",
            user.id, domain, item,
            exc_info=True,
        )
        result["completion_detail"] = {
            "success": False,
            "reason": "completion_error",
        }

    return result


# ---------------------------------------------------------------------------
# Fingerprint generation (normalized)
# ---------------------------------------------------------------------------

def _generate_fingerprint(signal: dict) -> str:
    """Generate a deterministic fingerprint for a signal.

    Format: {type}:{domain}:{item}:{date}
    All fields are normalized (lowercase, stripped) before hashing.
    Uses today's date if no timestamp in signal.
    """
    signal_type = (signal.get("type") or "unknown").strip().lower()
    domain = (signal.get("domain") or "unknown").strip().lower()
    item = (signal.get("item") or "unknown").strip().lower()

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
# Idempotency guard via execution truth
# ---------------------------------------------------------------------------

def _is_already_completed(user, domain: str, item: str) -> bool:
    """Check if domain+item is already completed today via execution truth.

    Uses the Execution Truth Engine — the single source of truth.
    """
    try:
        from apps.core.execution.execution_truth_engine import get_execution_truth
        truth = get_execution_truth(user)
    except ImportError:
        logger.warning(
            "[SIGNAL FEEDBACK] Execution truth engine not available"
        )
        return False
    except Exception:
        logger.error(
            "[SIGNAL FEEDBACK] Execution truth check failed",
            exc_info=True,
        )
        return False

    # Use the presenter's truth-checking logic for consistency
    from apps.core.signals.signal_presenter import _is_completed_in_truth
    return _is_completed_in_truth(domain, item, truth)


# ---------------------------------------------------------------------------
# Completion Handler Abstraction
# ---------------------------------------------------------------------------

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

# Domain+item → handler mapping
# Each handler: (user, domain, item) -> dict with "success" key
# Extensible: add new handlers as domains get completion support.
# Missing handler = feedback recorded only, no execution.
_COMPLETION_HANDLERS: Dict[str, Callable] = {
    # Faith domain — routed through routine completion
    ("faith", "prayer"): _complete_via_routine,
    ("faith", "bible_reading"): _complete_via_routine,
    ("faith", "church"): _complete_via_routine,
    # Health domain — routed through routine completion
    ("health", "workout"): _complete_via_routine,
    ("health", "running"): _complete_via_routine,
    ("health", "walking"): _complete_via_routine,
    ("health", "yoga"): _complete_via_routine,
    # Journal domain — routed through routine completion
    ("journal", "journal_entry"): _complete_via_routine,
}


def _get_completion_handler(domain: str, item: str) -> Optional[Callable]:
    """Look up the completion handler for a domain+item pair.

    Returns None if no handler is registered (feedback-only).
    """
    return _COMPLETION_HANDLERS.get((domain, item))
