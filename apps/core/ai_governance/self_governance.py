"""
Phase 8 — Self-Governance: SRI Computation, Escalation, Email Triggers.

Provides:
    - compute_sri(as_of) — rolling 30-day Self-Reliability Index (on-demand)
    - record_self_error(...) — central SelfError creation with auto-escalation
    - check_level2_auto_escalation(...) — repeated Level 2 → Level 3
    - send_governance_alert(level, self_error) — admin email on Level 3

SRI is admin-only visibility. Never user-facing.
No snapshot model — computed fresh each call.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)


# =========================================================================
# SRI Computation (on-demand, no snapshot model)
# =========================================================================

# Penalty weights per error level
SRI_PENALTY_LEVEL_1 = 0.5
SRI_PENALTY_LEVEL_2 = 2.0
SRI_PENALTY_LEVEL_3 = 10.0
SRI_BASE_SCORE = 100.0
SRI_WINDOW_DAYS = 30


def compute_sri(as_of=None):
    """
    Compute Self-Reliability Index — rolling 30-day window.

    Queries SelfError + relevant OpsAnomaly records and computes a
    deterministic score. No LLM involved.

    Args:
        as_of: datetime — freeze time for computation. Defaults to now().

    Returns:
        dict:
            'score': float (0.0–100.0)
            'window_start': datetime
            'window_end': datetime
            'total_errors': int
            'structural_errors': int
            'numeric_errors': int
            'governance_errors': int
            'level3_count': int
            'blocked_count': int
            'computed_at': datetime
    """
    from apps.core.ai_governance.models import SelfError

    if as_of is None:
        as_of = timezone.now()

    window_start = as_of - timedelta(days=SRI_WINDOW_DAYS)

    errors = SelfError.objects.filter(
        created_at__gte=window_start,
        created_at__lte=as_of,
    )

    # Count by level
    level_counts = {1: 0, 2: 0, 3: 0}
    category_counts = {'STRUCTURAL': 0, 'NUMERIC': 0, 'GOVERNANCE': 0}
    blocked_count = 0

    for err in errors.values('level', 'category', 'was_blocked'):
        level_counts[err['level']] = level_counts.get(err['level'], 0) + 1
        category_counts[err['category']] = (
            category_counts.get(err['category'], 0) + 1
        )
        if err['was_blocked']:
            blocked_count += 1

    total = sum(level_counts.values())

    # Deterministic formula
    penalty = (
        level_counts[1] * SRI_PENALTY_LEVEL_1
        + level_counts[2] * SRI_PENALTY_LEVEL_2
        + level_counts[3] * SRI_PENALTY_LEVEL_3
    )
    score = max(0.0, SRI_BASE_SCORE - penalty)

    return {
        'score': round(score, 1),
        'window_start': window_start,
        'window_end': as_of,
        'total_errors': total,
        'structural_errors': category_counts.get('STRUCTURAL', 0),
        'numeric_errors': category_counts.get('NUMERIC', 0),
        'governance_errors': category_counts.get('GOVERNANCE', 0),
        'level3_count': level_counts[3],
        'blocked_count': blocked_count,
        'computed_at': as_of,
    }


# =========================================================================
# Level 2 Auto-Escalation
# =========================================================================

LEVEL2_REPEAT_THRESHOLD = 5
LEVEL2_REPEAT_WINDOW_DAYS = 7


def check_level2_auto_escalation(trigger_code, user=None, window_days=None,
                                  threshold=None):
    """
    Check if an identical Level 2 trigger has repeated enough times
    in the window to warrant auto-escalation to Level 3.

    Args:
        trigger_code: str — the trigger_code to check.
        user: User instance (nullable — if None, checks system-wide).
        window_days: int — lookback window (default 7).
        threshold: int — repeat count threshold (default 5).

    Returns:
        bool — True if should escalate to Level 3.
    """
    from apps.core.ai_governance.models import SelfError

    if window_days is None:
        window_days = LEVEL2_REPEAT_WINDOW_DAYS
    if threshold is None:
        threshold = LEVEL2_REPEAT_THRESHOLD

    window_start = timezone.now() - timedelta(days=window_days)

    qs = SelfError.objects.filter(
        level=SelfError.LEVEL_MODERATE,
        trigger_code=trigger_code,
        created_at__gte=window_start,
    )
    if user is not None:
        qs = qs.filter(user=user)

    count = qs.count()
    return count >= threshold


# =========================================================================
# Central SelfError Recording
# =========================================================================

def record_self_error(user, level, category, trigger_code, trigger_detail='',
                      original_response_hash='', was_blocked=False,
                      trace_id=None, metadata=None):
    """
    Central creation helper for SelfError records.

    Handles:
    1. Auto-escalation: If this is Level 2 and the same trigger_code has
       repeated >= 5 times in 7 days, escalate to Level 3.
    2. Governance email: If final level is 3, send admin alert.
    3. OpsAnomaly: If escalated or Level 3, emit anomaly.

    Args:
        user: User instance (nullable).
        level: int (1, 2, or 3).
        category: str (STRUCTURAL, NUMERIC, GOVERNANCE).
        trigger_code: str — machine-readable trigger.
        trigger_detail: str — what was detected.
        original_response_hash: str — SHA-256 of original response.
        was_blocked: bool — whether response was replaced.
        trace_id: str — UUID linking to EngineRun.
        metadata: dict — additional context.

    Returns:
        SelfError instance (or None on failure).
    """
    import uuid as _uuid

    from apps.core.blueprint.concurrency import safe_db_write

    final_level = level
    auto_escalated = False

    # Check auto-escalation for Level 2
    if level == 2:
        try:
            if check_level2_auto_escalation(trigger_code, user=user):
                final_level = 3
                auto_escalated = True
                logger.warning(
                    "Phase 8: Level 2 trigger '%s' auto-escalated to Level 3 "
                    "(>=%d repeats in %d days)",
                    trigger_code,
                    LEVEL2_REPEAT_THRESHOLD,
                    LEVEL2_REPEAT_WINDOW_DAYS,
                )
        except Exception as e:
            logger.warning("Phase 8: Auto-escalation check failed: %s", e)

    # Build metadata
    error_metadata = metadata or {}
    if auto_escalated:
        error_metadata['auto_escalated_from'] = level
        error_metadata['escalation_reason'] = (
            f"Repeated {LEVEL2_REPEAT_THRESHOLD}+ times in "
            f"{LEVEL2_REPEAT_WINDOW_DAYS} days"
        )

    trace_uuid = None
    if trace_id:
        try:
            trace_uuid = _uuid.UUID(trace_id)
        except (ValueError, AttributeError):
            pass

    def _create():
        from apps.core.ai_governance.models import SelfError
        return SelfError.objects.create(
            user=user,
            level=final_level,
            category=category,
            trigger_code=trigger_code,
            trigger_detail=trigger_detail[:2000],
            original_response_hash=original_response_hash,
            was_blocked=was_blocked,
            engine_run_trace_id=trace_uuid,
            metadata=error_metadata,
        )

    result = safe_db_write(_create)
    self_error = result.get('result') if result.get('success') else None

    # Governance email for Level 3
    if final_level >= 3 and self_error:
        try:
            send_governance_alert(final_level, self_error, auto_escalated)
        except Exception as e:
            logger.warning("Phase 8: Governance email failed: %s", e)

    # OpsAnomaly for auto-escalation
    if auto_escalated:
        try:
            from apps.core.ai_observability.models import OpsAnomaly
            OpsAnomaly.objects.create(
                severity='P1',
                engine_name='VGE',
                anomaly_type=_anomaly_type_for_category(category),
                summary=(
                    f"Level 2 auto-escalated to Level 3: {trigger_code} "
                    f"repeated {LEVEL2_REPEAT_THRESHOLD}+ times in "
                    f"{LEVEL2_REPEAT_WINDOW_DAYS} days"
                ),
                evidence={
                    'trigger_code': trigger_code,
                    'auto_escalated': True,
                    'original_level': level,
                    'final_level': final_level,
                },
                suggested_actions=[
                    f"Investigate recurring trigger: {trigger_code}",
                    "Review LLM system prompt for persistent leakage.",
                ],
            )
        except Exception as e:
            logger.warning("Phase 8: Failed to log escalation anomaly: %s", e)

    return self_error


def _anomaly_type_for_category(category):
    """Map SelfError category to OpsAnomaly type."""
    return {
        'STRUCTURAL': 'STRUCTURAL_VIOLATION',
        'NUMERIC': 'NUMERIC_DEVIATION',
        'GOVERNANCE': 'VALIDATOR_CRASH',
    }.get(category, 'VALIDATOR_CRASH')


# =========================================================================
# Governance Email Triggers
# =========================================================================

def send_governance_alert(level, self_error, auto_escalated=False):
    """
    Send governance alert email to settings.ADMINS for Level 3 events.

    Email contains:
    - Error level and category
    - Trigger code and detail
    - Whether auto-escalated
    - Timestamp

    No technical jargon (no model names, no internal identifiers).
    """
    if level < 3:
        return

    admin_emails = [email for _, email in getattr(settings, 'ADMINS', [])]
    if not admin_emails:
        logger.warning("Phase 8: No ADMINS configured for governance email.")
        return

    escalation_note = ""
    if auto_escalated:
        escalation_note = (
            "\n\nThis was automatically escalated because the same issue "
            "occurred 5 or more times in the last 7 days."
        )

    subject = "[WLJ Governance] Critical Self-Error Detected"

    body = (
        f"A critical self-error was detected in the intelligence system.\n\n"
        f"Category: {self_error.category}\n"
        f"Trigger: {self_error.trigger_code}\n"
        f"Detail: {self_error.trigger_detail[:500]}\n"
        f"Time: {self_error.created_at}\n"
        f"Blocked: {'Yes' if self_error.was_blocked else 'No'}"
        f"{escalation_note}\n\n"
        f"Review the Ops Command Center for full details."
    )

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=getattr(
                settings, 'DEFAULT_FROM_EMAIL', 'noreply@wholelifejourney.com'
            ),
            recipient_list=admin_emails,
            fail_silently=True,
        )
        logger.info(
            "Phase 8: Governance alert sent to %d admin(s) for %s",
            len(admin_emails),
            self_error.trigger_code,
        )
    except Exception as e:
        logger.error("Phase 8: Failed to send governance email: %s", e)
