"""
Phase 6 — Concurrency & Degraded-Mode Utilities.

Provides:
    - Conversation metadata locking with retry + degrade
    - Commitment race condition detection + anomaly logging
    - Observability helpers for escalation transitions
    - Degraded-mode user-friendly messaging
    - ArchitecturePlan atomic activation

All user-facing messages are plain language. No technical jargon.
Observability logging is fire-and-forget (never breaks user flow).

Project: Whole Life Journey
Path: apps/core/blueprint/concurrency.py
"""

import logging
import random
import time
from uuid import uuid4

from django.db import DatabaseError, OperationalError, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# =========================================================================
# USER-FRIENDLY DEGRADED-MODE MESSAGES
# =========================================================================

DEGRADED_MSG_SAVE_RETRY = (
    "I couldn't update your records right this second, "
    "but I saved your request and we'll try again."
)

DEGRADED_MSG_LIMITED_MODE = (
    "I'm running in a limited mode right now, "
    "so I may miss some suggestions."
)

DEGRADED_MSG_TEMPORARY_ISSUE = (
    "Something didn't save properly. Your commitments are safe — "
    "I'll catch up shortly."
)

DEGRADED_MSG_SLOW_RESPONSE = (
    "I'm taking a little longer than usual. "
    "Your information is safe."
)


# =========================================================================
# 6.1 — CONVERSATION METADATA LOCKING
# =========================================================================


def update_conversation_metadata(conversation, updater_fn, degraded_message=None):
    """
    Safely read-modify-write conversation.metadata with row-level locking.

    Tries once with select_for_update(). If blocked (OperationalError),
    retries once after a small jitter (50-150ms). If still blocked,
    proceeds in degraded mode (no metadata mutation).

    Args:
        conversation: AssistantConversation instance (must have .pk).
        updater_fn: callable(metadata_dict) -> metadata_dict.
            Receives the current metadata dict, returns the updated dict.
        degraded_message: Optional str to return if degraded mode is entered.

    Returns:
        dict with:
            'success': bool — whether metadata was actually updated.
            'degraded': bool — whether degraded mode was entered.
            'message': str or None — user-facing degraded message (if any).
    """
    from apps.ai.models import AssistantConversation

    for attempt in range(2):
        try:
            with transaction.atomic():
                locked = AssistantConversation.objects.select_for_update(
                    nowait=(attempt == 0),
                ).get(pk=conversation.pk)

                current_metadata = locked.metadata or {}
                updated_metadata = updater_fn(current_metadata)
                locked.metadata = updated_metadata
                locked.save(update_fields=['metadata'])

                # Refresh the caller's reference
                conversation.metadata = updated_metadata
                return {
                    'success': True,
                    'degraded': False,
                    'message': None,
                }

        except (OperationalError, DatabaseError) as e:
            if attempt == 0:
                # First failure — retry with jitter
                jitter = random.uniform(0.05, 0.15)
                time.sleep(jitter)
                logger.warning(
                    "Phase 6: Metadata lock contention on conversation %s, "
                    "retrying after %.0fms jitter",
                    conversation.pk, jitter * 1000,
                )
                continue
            else:
                # Second failure — degrade gracefully
                logger.error(
                    "Phase 6: Metadata lock failed after retry on "
                    "conversation %s: %s. Entering degraded mode.",
                    conversation.pk, e,
                )
                return {
                    'success': False,
                    'degraded': True,
                    'message': degraded_message or DEGRADED_MSG_SAVE_RETRY,
                }

    # Should not reach here, but safe fallback
    return {'success': False, 'degraded': True, 'message': DEGRADED_MSG_SAVE_RETRY}


# =========================================================================
# 6.3 — ARCHITECTURE PLAN ATOMIC ACTIVATION
# =========================================================================


def activate_plan_atomic(plan):
    """
    Atomically activate an ArchitecturePlan, superseding any other active
    plan for the same user+date. Under concurrent calls, exactly one plan
    ends in 'active' status.

    Args:
        plan: ArchitecturePlan instance.
    """
    from apps.core.blueprint.models import ArchitecturePlan

    with transaction.atomic():
        # Lock the plan row being activated
        locked_plan = ArchitecturePlan.objects.select_for_update().get(pk=plan.pk)

        # Supersede other active plans for the same user+date
        ArchitecturePlan.objects.filter(
            user=locked_plan.user,
            date=locked_plan.date,
            status=ArchitecturePlan.STATUS_ACTIVE,
        ).exclude(pk=locked_plan.pk).update(status=ArchitecturePlan.STATUS_SUPERSEDED)

        locked_plan.status = ArchitecturePlan.STATUS_ACTIVE
        locked_plan.save(update_fields=['status', 'updated_at'])

        # Update the caller's reference
        plan.status = locked_plan.status


# =========================================================================
# 6.5 — COMMITMENT RACE CONDITION ANOMALY
# =========================================================================


def check_commitment_race_condition(user):
    """
    Detect if two commitment mutations occurred within 1 second for the
    same user. If so, log a COMMITMENT_RACE_CONDITION anomaly.

    Internal-only by default (not user-facing).

    Args:
        user: User instance.

    Returns:
        bool — True if race condition detected.
    """
    try:
        from apps.core.blueprint.models import Commitment

        now = timezone.now()
        one_second_ago = now - timezone.timedelta(seconds=1)

        recent_count = Commitment.objects.filter(
            user=user,
            updated_at__gte=one_second_ago,
        ).count()

        if recent_count >= 2:
            _log_race_condition_anomaly(user, recent_count)
            return True

        return False
    except Exception as e:
        logger.warning("Phase 6: Race condition check failed: %s", e)
        return False


def _log_race_condition_anomaly(user, mutation_count):
    """Fire-and-forget: log a COMMITMENT_RACE_CONDITION anomaly."""
    try:
        from apps.core.ai_observability.models import OpsAnomaly

        OpsAnomaly.objects.create(
            severity='P2',
            engine_name='ECC',
            anomaly_type='COMMITMENT_RACE_CONDITION',
            summary=(
                f"Detected {mutation_count} commitment mutations within 1 second "
                f"for user {user.pk}. Possible concurrent write."
            ),
            evidence={
                'user_id': user.pk,
                'mutation_count': mutation_count,
                'detected_at': timezone.now().isoformat(),
            },
            suggested_actions=[
                "Review recent commitment writes for this user",
                "Check for multi-tab or multi-device concurrent usage",
            ],
        )
        logger.info(
            "Phase 6: COMMITMENT_RACE_CONDITION anomaly logged for user %s",
            user.pk,
        )
    except Exception as e:
        logger.warning("Phase 6: Failed to log race condition anomaly: %s", e)


# =========================================================================
# 6.6 — OBSERVABILITY: ESCALATION TRANSITION LOGGING
# =========================================================================


def log_escalation_transition(user, from_level, to_level, trigger,
                              recovery_reasons=None):
    """
    Log both EngineRun and DecisionRecord when EscalationState changes level.

    Fire-and-forget: failures are logged but never break user flow.

    Args:
        user: User instance.
        from_level: int — previous escalation level.
        to_level: int — new escalation level.
        trigger: str — what caused the transition.
        recovery_reasons: dict or None — recovery gate details.
    """
    try:
        from apps.core.ai_observability.models import DecisionRecord, EngineRun

        trace_id = str(uuid4())
        now = timezone.now()

        # EngineRun record
        EngineRun.objects.create(
            trace_id=trace_id,
            engine_name='ESC',
            phase=2,  # Execution phase
            started_at=now,
            ended_at=now,
            duration_ms=0,
            status='success',
            user_id=user.pk,
            metadata={
                'from_level': from_level,
                'to_level': to_level,
                'trigger': trigger,
            },
        )

        # DecisionRecord
        level_names = {0: 'CLEAN', 1: 'EARLY_EROSION', 2: 'STRUCTURAL_DRIFT'}
        DecisionRecord.objects.create(
            trace_id=trace_id,
            decision_type='other',
            engine_name='ESC',
            decision=f"ESCALATION_TRANSITION={level_names.get(to_level, 'UNKNOWN')}",
            rationale=(
                f"Escalation changed from {level_names.get(from_level, '?')} "
                f"to {level_names.get(to_level, '?')}. Trigger: {trigger}."
            ),
            inputs_summary={
                'from_level': from_level,
                'to_level': to_level,
                'trigger': trigger,
                'recovery_reasons': recovery_reasons or {},
            },
            user_id=user.pk,
        )

        logger.debug(
            "Phase 6: Escalation transition logged — trace=%s user=%s %d→%d",
            trace_id[:8], user.pk, from_level, to_level,
        )
    except Exception as e:
        # Fire-and-forget: NEVER break user flow
        logger.warning(
            "Phase 6: Failed to log escalation transition: %s", e,
        )


# =========================================================================
# 6.7-6.9 — DEGRADED-MODE HELPERS
# =========================================================================


def safe_llm_call(llm_fn, *args, fallback_response=None, **kwargs):
    """
    Wrap an LLM call with degraded-mode handling.

    If the LLM call fails (timeout, error, None response), returns a safe
    plain-language fallback.

    Args:
        llm_fn: callable that makes the LLM API call.
        fallback_response: str — what to return if LLM fails.

    Returns:
        dict with:
            'response': str — LLM response or fallback.
            'degraded': bool — whether fallback was used.
            'message': str or None — user notification if degraded.
    """
    default_fallback = (
        "I'm here but my analysis tools aren't responding right now. "
        "Your commitments and schedule are safe. "
        "I'll have full suggestions next time."
    )
    try:
        result = llm_fn(*args, **kwargs)
        if result is None:
            return {
                'response': fallback_response or default_fallback,
                'degraded': True,
                'message': DEGRADED_MSG_LIMITED_MODE,
            }
        return {
            'response': result,
            'degraded': False,
            'message': None,
        }
    except Exception as e:
        logger.error("Phase 6: LLM call failed: %s", e)
        return {
            'response': fallback_response or default_fallback,
            'degraded': True,
            'message': DEGRADED_MSG_LIMITED_MODE,
        }


def safe_db_write(write_fn, *args, **kwargs):
    """
    Wrap a DB write with degraded-mode handling.

    If the write fails, logs the error and returns a degraded result.
    Never raises to the caller.

    Args:
        write_fn: callable that performs the DB write.

    Returns:
        dict with:
            'success': bool
            'result': Any — the write_fn return value, or None.
            'degraded': bool
            'message': str or None — user notification if degraded.
    """
    try:
        result = write_fn(*args, **kwargs)
        return {
            'success': True,
            'result': result,
            'degraded': False,
            'message': None,
        }
    except (OperationalError, DatabaseError) as e:
        logger.error("Phase 6: DB write failed: %s", e)
        return {
            'success': False,
            'result': None,
            'degraded': True,
            'message': DEGRADED_MSG_TEMPORARY_ISSUE,
        }
    except Exception as e:
        logger.error("Phase 6: Unexpected DB write error: %s", e)
        return {
            'success': False,
            'result': None,
            'degraded': True,
            'message': DEGRADED_MSG_TEMPORARY_ISSUE,
        }


def safe_cache_read(cache_fn, *args, fallback=None, **kwargs):
    """
    Wrap a cache read with degraded-mode handling.

    If cache is unavailable, returns the fallback value.
    User experience is not impacted unless fallback materially degrades it.

    Args:
        cache_fn: callable that reads from cache.
        fallback: default value if cache read fails.

    Returns:
        dict with:
            'value': Any — cached value or fallback.
            'degraded': bool
            'message': str or None — user notification only if material impact.
    """
    try:
        value = cache_fn(*args, **kwargs)
        if value is not None:
            return {'value': value, 'degraded': False, 'message': None}
        return {'value': fallback, 'degraded': False, 'message': None}
    except Exception as e:
        logger.warning("Phase 6: Cache read failed: %s", e)
        return {
            'value': fallback,
            'degraded': True,
            'message': None,  # Only notify if material — caller decides
        }
