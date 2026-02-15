"""
ICQG — Repeat Suppression.

Suppresses repeated guidance that appears within a configurable window
(default 72 hours), unless the severity has increased (priority moved higher).
"""

import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

# Default suppression window in hours
SUPPRESSION_WINDOW_HOURS = 72


def check_repeat_suppression(user, candidate):
    """
    Check if a guidance candidate should be suppressed as a repeat.

    Rules:
    - If same signature appeared within the suppression window:
      - SUPPRESS unless priority moved higher (numerically lower)
    - If suppressed, update the suppression record

    Args:
        user: Django User instance.
        candidate: dict with guidance_type, title, evidence, priority, metadata.

    Returns:
        (should_suppress: bool, reason: str or None)
    """
    try:
        from apps.core.ai_quality.quality_models import QualitySuppressionRecord

        signature = _compute_candidate_signature(candidate)
        now = timezone.now()

        record = QualitySuppressionRecord.objects.filter(
            user=user,
            signature_hash=signature,
        ).first()

        if not record:
            # First time seeing this signature — no suppression
            return False, None

        if record.suppressed_until <= now:
            # Suppression window expired — allow through
            return False, None

        # Active suppression window — check for severity increase
        current_priority = candidate.get("priority", 3)
        if current_priority < record.last_priority:
            # Severity increased (lower number = higher priority) — allow
            logger.debug(
                f"ICQG: Severity increase bypasses suppression for user "
                f"{user.id}: P{record.last_priority} → P{current_priority}"
            )
            return False, None

        # Same or lower severity within window — suppress
        record.count += 1
        record.last_seen_at = now
        record.save(update_fields=["count", "last_seen_at"])

        reason = (
            f"Repeat suppression: seen {record.count} times, "
            f"suppressed until {record.suppressed_until.isoformat()}"
        )
        logger.debug(f"ICQG: {reason} for user {user.id}")
        return True, reason

    except Exception as e:
        logger.error(f"ICQG: Repeat suppression check failed: {e}")
        return False, None  # Fail open — do not block on errors


def record_suppression(user, candidate):
    """
    Record a suppression entry after guidance is stored.

    Called after a guidance candidate passes through the quality gate
    and is stored — sets the suppression window for future repeats.

    Args:
        user: Django User instance.
        candidate: dict with guidance_type, title, evidence, priority.
    """
    try:
        from apps.core.ai_quality.quality_models import QualitySuppressionRecord

        signature = _compute_candidate_signature(candidate)
        now = timezone.now()
        suppress_until = now + timedelta(hours=SUPPRESSION_WINDOW_HOURS)

        record, created = QualitySuppressionRecord.objects.update_or_create(
            user=user,
            signature_hash=signature,
            defaults={
                "suppressed_until": suppress_until,
                "last_seen_at": now,
                "last_priority": candidate.get("priority", 3),
            },
        )
        if not created:
            record.count += 1
            record.save(update_fields=["count"])

    except Exception as e:
        logger.error(f"ICQG: Failed to record suppression: {e}")


def _compute_candidate_signature(candidate):
    """Compute signature hash from a guidance candidate dict."""
    from apps.core.ai_quality.quality_models import QualitySuppressionRecord

    guidance_type = candidate.get("guidance_type", "")
    title = candidate.get("title", "")

    # Extract evidence IDs from evidence dict
    evidence = candidate.get("evidence", {})
    evidence_ids = None
    if isinstance(evidence, dict):
        # Common patterns: evidence.record_ids, evidence.insight_ids
        ids = evidence.get("record_ids", []) or evidence.get("insight_ids", [])
        if ids:
            evidence_ids = ids

    return QualitySuppressionRecord.compute_signature(
        guidance_type, title, evidence_ids
    )
