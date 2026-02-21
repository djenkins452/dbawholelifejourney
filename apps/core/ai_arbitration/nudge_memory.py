"""
UAL v2.1 — Recent Nudge Memory (Semantic Clustering).

Prevents cognitively redundant nudges within short windows.
When a new intervention shares a semantic tag with a recently
surfaced nudge (within 12h), a scoring penalty is applied.

Severity escalations bypass the penalty.

No embeddings — tags reuse scenario names, composite types,
or commitment keys.
"""
import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

# Retention / penalty window
NUDGE_MEMORY_WINDOW_HOURS = 12

# Score penalty for semantic collision
COLLISION_PENALTY = -0.1

# Scenarios that bypass penalty when escalating
SEVERITY_ESCALATION_SCENARIOS = frozenset({
    "HEALTH_CRITICAL",
    "MOOD_CRITICAL",
})


def check_nudge_collisions(user, candidates: list, scenario: str) -> list:
    """
    Check surfaced candidates against recent nudge memory.
    Apply scoring penalty if semantic tag collides within window.

    Severity escalations bypass penalty.

    Args:
        user: User instance
        candidates: list of surfaced item dicts (must have 'category' or 'label')
        scenario: current dominant scenario

    Returns:
        list of candidates with adjusted priorities (penalty applied in-place)
    """
    try:
        from apps.core.ai_arbitration.models import RecentNudgeMemory

        cutoff = timezone.now() - timedelta(hours=NUDGE_MEMORY_WINDOW_HOURS)
        recent_tags = set(
            RecentNudgeMemory.objects.filter(
                user=user,
                surfaced_at__gte=cutoff,
            ).values_list("semantic_tag", flat=True)
        )
    except Exception as e:
        logger.debug("UAL nudge memory check skipped: %s", e)
        return candidates

    if not recent_tags:
        return candidates

    # Check for severity escalation bypass
    is_escalation = scenario in SEVERITY_ESCALATION_SCENARIOS

    for candidate in candidates:
        tag = _extract_semantic_tag(candidate)
        if tag in recent_tags and not is_escalation:
            # Apply collision penalty to priority score
            candidate["priority"] = candidate.get("priority", 0) + COLLISION_PENALTY
            candidate["_nudge_collision"] = True

    return candidates


def record_surfaced_nudges(user, surfaced_items: list, scenario: str,
                           trace_id: str = "") -> None:
    """
    Record surfaced nudges in memory for future collision detection.

    Args:
        user: User instance
        surfaced_items: list of surfaced item dicts
        scenario: dominant scenario
        trace_id: optional trace ID for linking
    """
    try:
        from apps.core.ai_arbitration.models import RecentNudgeMemory

        records = []
        for item in surfaced_items:
            tag = _extract_semantic_tag(item)
            records.append(RecentNudgeMemory(
                user=user,
                scenario=scenario,
                semantic_tag=tag,
                trace_id=trace_id,
            ))

        if records:
            RecentNudgeMemory.objects.bulk_create(records)

        # Cleanup: purge expired entries (older than window)
        _purge_expired(user)

    except Exception as e:
        logger.debug("UAL nudge memory recording skipped: %s", e)


def _extract_semantic_tag(item: dict) -> str:
    """
    Extract a semantic tag from a surfaced item.
    Uses category as primary tag, falls back to label.
    """
    return item.get("category", item.get("label", "unknown"))


def _purge_expired(user) -> None:
    """Remove nudge memory entries older than the retention window."""
    try:
        from apps.core.ai_arbitration.models import RecentNudgeMemory

        cutoff = timezone.now() - timedelta(hours=NUDGE_MEMORY_WINDOW_HOURS)
        RecentNudgeMemory.objects.filter(
            user=user,
            surfaced_at__lt=cutoff,
        ).delete()
    except Exception as e:
        logger.debug("UAL nudge memory purge skipped: %s", e)
