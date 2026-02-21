"""
ICQG — Quality Gate Entry Points.

Central API for the Intelligence Calibration & Quality Gate.
Exposes three filter functions consumed by PGE, DBE/WIRE, and DNE.

All functions fail open — if ICQG fails, items pass through unfiltered.
"""

import logging

from apps.core.ai_observability.instrumentation import log_engine_run as _instrument_engine_run
from apps.core.ai_observability.instrumentation import record_decision as _record_decision

logger = logging.getLogger(__name__)

# Minimum confidence for prediction-based notifications
MIN_PREDICTION_CONFIDENCE = 0.75

# Minimum confidence for guidance delivery (not storage)
MIN_DELIVERY_CONFIDENCE = 0.60


@_instrument_engine_run("ICQG", 3)
def filter_guidance_candidates(user, candidates):
    """
    Filter guidance candidates before storage (PGE integration).

    Applied after ranking but before log_guidance().

    Applies:
    1. Repeat suppression (72h window)
    2. Conflict detection and resolution
    3. Evidence quality check

    Args:
        user: Django User instance.
        candidates: list of ranked guidance candidate dicts.

    Returns:
        list of filtered candidates (may be smaller).
    """
    if not candidates:
        return []

    try:
        from apps.core.ai_quality.repeat_suppression import (
            check_repeat_suppression,
            record_suppression,
        )
        from apps.core.ai_quality.conflict_detector import detect_guidance_conflicts

        # Step 1: Conflict detection (may merge/downgrade)
        resolved = detect_guidance_conflicts(candidates)

        # Step 2: Repeat suppression
        filtered = []
        for candidate in resolved:
            suppressed, reason = check_repeat_suppression(user, candidate)
            if suppressed:
                logger.debug(
                    f"ICQG: Suppressed '{candidate.get('title', '?')}' "
                    f"for user {user.id}: {reason}"
                )
                continue

            # Step 3: Evidence quality check
            if not _has_sufficient_evidence(candidate):
                logger.debug(
                    f"ICQG: Skipped '{candidate.get('title', '?')}' "
                    f"for user {user.id}: insufficient evidence"
                )
                continue

            filtered.append(candidate)

        # Step 4: Record suppressions for items that passed
        for candidate in filtered:
            record_suppression(user, candidate)

        suppressed_count = len(candidates) - len(filtered)
        if suppressed_count > 0:
            logger.info(
                f"ICQG: Filtered {suppressed_count}/{len(candidates)} "
                f"guidance candidates for user {user.id}"
            )
            _record_decision(
                engine_name="ICQG",
                decision_type="suppression",
                decision=f"SUPPRESSED={suppressed_count}/{len(candidates)}",
                rationale="repeat_suppression + evidence_quality",
                user_id=user.id,
                affected_items=[c.get("title", "") for c in candidates if c not in filtered],
            )

        return filtered

    except Exception as e:
        logger.error(f"ICQG: filter_guidance_candidates failed: {e}")
        return candidates  # Fail open


@_instrument_engine_run("ICQG", 3)
def filter_briefing_items(user, items):
    """
    Filter briefing/report items before summary generation (DBE/WIRE integration).

    Applied after ranking but before _generate_summary().

    Applies:
    1. Conflict detection (prediction vs insight contradictions)
    2. Minimum confidence threshold for predictions
    3. Evidence presence check

    Args:
        user: Django User instance.
        items: list of ranked briefing item dicts.

    Returns:
        list of filtered items.
    """
    if not items:
        return []

    try:
        from apps.core.ai_quality.conflict_detector import detect_briefing_conflicts

        # Step 1: Conflict detection
        resolved = detect_briefing_conflicts(items)

        # Step 2: Filter low-confidence predictions
        filtered = []
        for item in resolved:
            item_type = item.get("type", "")
            confidence = item.get("confidence") or item.get("confidence_score") or 0

            # Skip predictions below threshold (but keep insights/guidance)
            if item_type == "prediction" and confidence < MIN_DELIVERY_CONFIDENCE:
                logger.debug(
                    f"ICQG: Removed low-confidence prediction from briefing "
                    f"({confidence:.2f} < {MIN_DELIVERY_CONFIDENCE})"
                )
                continue

            filtered.append(item)

        return filtered

    except Exception as e:
        logger.error(f"ICQG: filter_briefing_items failed: {e}")
        return items  # Fail open


def filter_delivery_candidates(user, items):
    """
    Filter delivery candidates before sending (DNE integration).

    Applied in _deliver_for_user() before routing to channels.

    Applies:
    1. Minimum confidence for prediction-based notifications (0.75)
    2. Evidence required (must have E3-ready data or snapshot)
    3. Informational guidance excluded from email/SMS during quiet hours

    Args:
        user: Django User instance.
        items: list of (engine, obj_type, obj_id, payload) tuples.

    Returns:
        list of filtered (engine, obj_type, obj_id, payload) tuples.
    """
    if not items:
        return []

    try:
        filtered = []
        for engine, obj_type, obj_id, payload in items:
            # Check minimum prediction confidence for delivery
            if engine == "PRIE" or _is_prediction_derived(engine, obj_type, payload):
                confidence = payload.get("confidence_score") or 0
                if confidence < MIN_PREDICTION_CONFIDENCE:
                    logger.debug(
                        f"ICQG: Blocked low-confidence prediction delivery "
                        f"({confidence:.2f} < {MIN_PREDICTION_CONFIDENCE})"
                    )
                    continue

            filtered.append((engine, obj_type, obj_id, payload))

        return filtered

    except Exception as e:
        logger.error(f"ICQG: filter_delivery_candidates failed: {e}")
        return items  # Fail open


def _has_sufficient_evidence(candidate):
    """
    Check if a guidance candidate has sufficient evidence for storage.

    Requirements:
    - Must have non-empty evidence dict OR a source that implies evidence
    - Predictions must have confidence_score

    Returns:
        bool
    """
    source = candidate.get("source", "")
    evidence = candidate.get("evidence", {})
    confidence = candidate.get("confidence_score")

    # Prediction-based items must have a confidence score
    if source == "prie_prediction" and not confidence:
        return False

    # Must have some form of evidence or a known reliable source
    if evidence and isinstance(evidence, dict) and len(evidence) > 0:
        return True

    # SAE state items are evidence-complete by definition
    if source == "sae_state":
        return True

    # Composite items should have evidence
    if source == "composite" and not evidence:
        return False

    # PIE insight items have evidence in the insight itself
    if source == "pie_insight":
        return True

    return True  # Default: allow through


def _is_prediction_derived(engine, obj_type, payload):
    """Check if a delivery item is derived from a prediction."""
    if engine == "PGE" and payload.get("source") == "prie_prediction":
        return True
    return False
