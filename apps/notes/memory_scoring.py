"""
Memory Intelligence Scoring for CoS Note Retrieval.

Provides a deterministic second-stage ranker that combines PostgreSQL FTS rank
with contextual signals (recency, pinning, entity scope, tag overlap) to
surface the "best" memory, not just "matching" memories.

Scoring Formula (documented):
─────────────────────────────
  combined_score = (
      BASE_WEIGHT   * normalized_fts_rank
    + RECENCY_WEIGHT * recency_factor
    + PINNED_WEIGHT  * pinned_factor
    + ENTITY_WEIGHT  * entity_factor
    + TAG_WEIGHT     * tag_factor
  )

Weights are tuned so that:
  - A highly relevant text match always outranks a pinned-but-irrelevant note
  - Recency provides a tiebreaker among equally relevant notes
  - Entity scoping and tag overlap provide meaningful but not dominant boosts

Constants can be adjusted; the formula remains stable and explainable.
"""

import math
from datetime import timedelta

from django.utils import timezone

# ---------------------------------------------------------------------------
# Scoring weights — must sum to a meaningful total but relative ratios matter
# ---------------------------------------------------------------------------
BASE_WEIGHT = 0.50       # FTS rank is the dominant signal
RECENCY_WEIGHT = 0.20    # Recent notes get a tiebreaker boost
PINNED_WEIGHT = 0.10     # Pinned notes get a small but meaningful boost
ENTITY_WEIGHT = 0.12     # Entity-scoped match is valuable context
TAG_WEIGHT = 0.08        # Tag overlap is a supporting signal

# Recency decay thresholds (days since last update)
RECENCY_STRONG = 7       # ≤ 7 days → factor 1.0
RECENCY_MODERATE = 30    # 8–30 days → factor 0.7
RECENCY_LIGHT = 180      # 31–180 days → factor 0.4
# > 180 days → factor 0.15

# Max reasons per result
MAX_REASONS = 5


def _normalize_fts_rank(rank, max_rank):
    """
    Normalize FTS rank to [0, 1] range.

    Uses the max_rank in the candidate set as the ceiling.
    If max_rank is 0, returns a small base value (all notes equally matched).
    """
    if max_rank is None or max_rank <= 0:
        return 0.5 if rank and rank > 0 else 0.0
    return min(rank / max_rank, 1.0) if rank else 0.0


def _recency_factor(updated_at):
    """
    Compute a recency factor in [0, 1] using smooth decay.

    Uses an exponential-like step decay that is easy to reason about:
      ≤ 7 days:    1.0
      8–30 days:   0.7
      31–180 days: 0.4
      > 180 days:  0.15
    """
    if updated_at is None:
        return 0.15

    now = timezone.now()
    days_ago = max((now - updated_at).total_seconds() / 86400, 0)

    if days_ago <= RECENCY_STRONG:
        return 1.0
    elif days_ago <= RECENCY_MODERATE:
        # Smooth interpolation from 1.0 → 0.7 over days 7–30
        progress = (days_ago - RECENCY_STRONG) / (RECENCY_MODERATE - RECENCY_STRONG)
        return 1.0 - (0.3 * progress)
    elif days_ago <= RECENCY_LIGHT:
        # Smooth interpolation from 0.7 → 0.4 over days 30–180
        progress = (days_ago - RECENCY_MODERATE) / (RECENCY_LIGHT - RECENCY_MODERATE)
        return 0.7 - (0.3 * progress)
    else:
        return 0.15


def _pinned_factor(is_pinned):
    """Return 1.0 if pinned, 0.0 otherwise."""
    return 1.0 if is_pinned else 0.0


def _entity_factor(note_attachment_entity_ids, scoped_content_type_id, scoped_object_id):
    """
    Return 1.0 if this note is attached to the scoped entity, 0.0 otherwise.

    Args:
        note_attachment_entity_ids: set of (content_type_id, object_id) tuples
            from this note's attachments.
        scoped_content_type_id: ContentType PK of the scoped entity (or None).
        scoped_object_id: PK of the scoped entity (or None).
    """
    if scoped_content_type_id is None or scoped_object_id is None:
        return 0.0
    if (scoped_content_type_id, scoped_object_id) in note_attachment_entity_ids:
        return 1.0
    return 0.0


def _tag_factor(note_tag_names, query_tags):
    """
    Return a tag overlap score in [0, 1].

    Computed as |intersection| / |query_tags|.
    """
    if not query_tags:
        return 0.0
    note_tags_lower = {t.lower() for t in note_tag_names}
    query_tags_lower = {t.lower() for t in query_tags}
    overlap = note_tags_lower & query_tags_lower
    return len(overlap) / len(query_tags_lower)


def score_note(
    *,
    fts_rank,
    max_fts_rank,
    updated_at,
    is_pinned,
    note_attachment_entity_ids,
    scoped_content_type_id,
    scoped_object_id,
    note_tag_names,
    query_tags,
):
    """
    Score a note candidate for CoS ranking.

    Args:
        fts_rank: PostgreSQL FTS rank score (float or None).
        max_fts_rank: Maximum FTS rank in the candidate pool (for normalization).
        updated_at: Note's updated_at datetime.
        is_pinned: Whether the note is pinned.
        note_attachment_entity_ids: set of (content_type_id, object_id) tuples.
        scoped_content_type_id: ContentType PK if entity-scoped search, else None.
        scoped_object_id: Entity PK if entity-scoped search, else None.
        note_tag_names: List of tag name strings for this note.
        query_tags: List of tag name strings from the query filter.

    Returns:
        dict with "combined_score" (float) and "reasons" (list of str, max 5).
    """
    reasons = []

    # A) Base FTS score
    norm_fts = _normalize_fts_rank(fts_rank, max_fts_rank)
    if norm_fts >= 0.7:
        reasons.append("Strong text match")
    elif norm_fts >= 0.3:
        reasons.append("Good text match")
    elif norm_fts > 0:
        reasons.append("Partial text match")

    # B) Recency
    recency = _recency_factor(updated_at)
    if recency >= 0.9:
        reasons.append("Recently updated")
    elif recency >= 0.6:
        reasons.append("Updated within last month")

    # C) Pinned
    pinned = _pinned_factor(is_pinned)
    if pinned > 0:
        reasons.append("Pinned note")

    # D) Entity match
    entity = _entity_factor(
        note_attachment_entity_ids, scoped_content_type_id, scoped_object_id
    )
    if entity > 0:
        # Build a descriptive reason
        reasons.append("Attached to this entity")

    # E) Tag overlap
    tag = _tag_factor(note_tag_names, query_tags)
    if tag > 0 and query_tags:
        note_tags_lower = {t.lower() for t in note_tag_names}
        query_tags_lower = {t.lower() for t in query_tags}
        overlapping = note_tags_lower & query_tags_lower
        if overlapping:
            tag_str = ", ".join(sorted(overlapping))
            reasons.append(f"Tag overlap: {tag_str}")

    # Combined score
    combined_score = (
        BASE_WEIGHT * norm_fts
        + RECENCY_WEIGHT * recency
        + PINNED_WEIGHT * pinned
        + ENTITY_WEIGHT * entity
        + TAG_WEIGHT * tag
    )

    return {
        "combined_score": round(combined_score, 4),
        "reasons": reasons[:MAX_REASONS],
    }


def score_fallback_note(*, updated_at, is_pinned):
    """
    Score a note for fallback display (no query, or no FTS matches).

    Used when showing pinned + recent notes without a search query.
    """
    reasons = []

    recency = _recency_factor(updated_at)
    if recency >= 0.9:
        reasons.append("Recently updated")
    elif recency >= 0.6:
        reasons.append("Updated within last month")

    pinned = _pinned_factor(is_pinned)
    if pinned > 0:
        reasons.append("Pinned note")

    # Fallback scoring: recency + pinned only
    combined_score = RECENCY_WEIGHT * recency + PINNED_WEIGHT * pinned

    return {
        "combined_score": round(combined_score, 4),
        "reasons": reasons[:MAX_REASONS],
    }
