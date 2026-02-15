"""
PGE -- Guidance Logger.

Stores guidance items with deduplication. If a guidance item with
the same dedupe_key already exists and is active, it updates instead
of creating a duplicate.
"""

import logging

from django.utils import timezone
from datetime import timedelta

from apps.core.ai_guidance.models import GuidanceItem

logger = logging.getLogger(__name__)

# How long guidance items remain active before expiring
DEFAULT_EXPIRY_DAYS = 7


def log_guidance(user, ranked_candidates):
    """
    Store ranked guidance candidates with deduplication.

    For each candidate:
    - If an active item with same dedupe_key exists → update it
    - Otherwise → create new GuidanceItem

    Args:
        user: Django user instance.
        ranked_candidates: List of guidance candidate dicts (already ranked).

    Returns:
        List of created/updated GuidanceItem instances.
    """
    stored = []
    now = timezone.now()
    default_expiry = now + timedelta(days=DEFAULT_EXPIRY_DAYS)

    for candidate in ranked_candidates:
        try:
            item = _upsert_guidance(user, candidate, default_expiry)
            if item:
                stored.append(item)
                # E3: Create explain record (non-blocking)
                try:
                    from apps.core.ai_explain.explain_engine import ensure_explain_record
                    ensure_explain_record(user, "PGE", item)
                except Exception:
                    pass  # E3 failure must never block PGE
        except Exception as e:
            logger.error(
                f"PGE: Failed to store guidance '{candidate.get('title', '?')}' "
                f"for user {user.id}: {e}",
                exc_info=True,
            )

    return stored


def _upsert_guidance(user, candidate, default_expiry):
    """
    Create or update a guidance item using dedupe_key.

    If same dedupe_key exists and is active, update instead of create.
    If same dedupe_key exists but is inactive, create a new one.
    """
    dedupe_key = candidate.get("dedupe_key", "")
    if not dedupe_key:
        logger.warning("PGE: Guidance candidate missing dedupe_key, skipping")
        return None

    # Check for existing active item with same key
    existing = GuidanceItem.objects.filter(
        user=user,
        dedupe_key=dedupe_key,
        is_active=True,
    ).first()

    if existing:
        # Update existing — refresh message/priority/evidence
        existing.title = candidate.get("title", existing.title)
        existing.message = candidate.get("message", existing.message)
        existing.priority = candidate.get("priority", existing.priority)
        existing.confidence_score = candidate.get(
            "confidence_score", existing.confidence_score
        )
        existing.evidence = candidate.get("evidence", existing.evidence)
        existing.expires_at = candidate.get("expires_at", default_expiry)
        existing.save(
            update_fields=[
                "title",
                "message",
                "priority",
                "confidence_score",
                "evidence",
                "expires_at",
                "updated_at",
            ]
        )
        logger.debug(f"PGE: Updated guidance {existing.id} ({dedupe_key[:16]}...)")
        return existing

    # Create new guidance item with clean lifecycle state
    item = GuidanceItem.objects.create(
        user=user,
        title=candidate.get("title", ""),
        message=candidate.get("message", ""),
        priority=candidate.get("priority", 3),
        guidance_type=candidate.get("guidance_type", ""),
        source=candidate.get("source", "composite"),
        module=candidate.get("module", ""),
        confidence_score=candidate.get("confidence_score"),
        evidence=candidate.get("evidence", {}),
        dedupe_key=dedupe_key,
        metadata=candidate.get("metadata", {}),
        expires_at=candidate.get("expires_at", default_expiry),
        # Lifecycle fields initialized to None (clean state)
        acknowledged_at=None,
        dismissed_at=None,
        snoozed_until=None,
        acted_upon_at=None,
        action_type=None,
        feedback=None,
    )
    logger.debug(f"PGE: Created guidance {item.id} ({dedupe_key[:16]}...)")
    return item
