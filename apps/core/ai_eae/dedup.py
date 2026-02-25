"""
EAE — Deduplication (Phase 8.2).

Second-layer dedup on top of per-engine dedup. Removes redundant signals
that would waste cognitive budget:
    1. Same-module, same-type, same-day → keep highest scored
    2. Overlapping predictions → keep highest confidence
    3. Insight + Guidance overlap → keep guidance (more actionable)
    4. Cross-channel dedup → suppress if recently delivered
"""
import logging
from datetime import date, timedelta
from typing import Dict, List, Optional

from django.utils import timezone

from apps.core.ai_eae.constants import (
    CROSS_CHANNEL_DEDUP_HOURS,
    DEDUP_PREDICTION_HORIZON_DAYS,
)
from apps.core.ai_eae.scorer import ScoredSignal

logger = logging.getLogger(__name__)


def _same_day_dedup(signals: List[ScoredSignal]) -> List[ScoredSignal]:
    """
    Remove same-module, same-type signals from the same day.
    Keep the highest-scored one.
    """
    seen = {}  # key: (module, signal_type, date) → best ScoredSignal
    for sig in signals:
        sig_date = sig.created_at.date() if sig.created_at else date.today()
        key = (sig.module, sig.signal_type, sig_date)
        if key not in seen or sig.normalized_score > seen[key].normalized_score:
            seen[key] = sig
    return list(seen.values())


def _prediction_overlap_dedup(signals: List[ScoredSignal]) -> List[ScoredSignal]:
    """
    Remove overlapping PRIE predictions targeting same metric at similar horizons.
    Keep highest confidence.
    """
    prie_signals = [s for s in signals if s.engine == 'PRIE']
    other_signals = [s for s in signals if s.engine != 'PRIE']

    if len(prie_signals) <= 1:
        return signals

    # Group by (module, base prediction type) and check horizon overlap
    seen = {}
    for sig in prie_signals:
        # Extract base type (e.g., 'weight' from 'weight_30d')
        base_type = sig.signal_type.rsplit('_', 1)[0] if '_' in sig.signal_type else sig.signal_type
        key = (sig.module, base_type)

        if key not in seen:
            seen[key] = sig
        else:
            # Keep the one with higher confidence
            if sig.confidence > seen[key].confidence:
                seen[key] = sig

    return other_signals + list(seen.values())


def _insight_guidance_dedup(signals: List[ScoredSignal]) -> List[ScoredSignal]:
    """
    If PIE insight and PGE guidance reference same module+type, keep guidance
    (more actionable) and suppress the insight.
    """
    pge_keys = set()
    for sig in signals:
        if sig.engine == 'PGE':
            pge_keys.add((sig.module, sig.signal_type))

    if not pge_keys:
        return signals

    result = []
    for sig in signals:
        if sig.engine == 'PIE' and (sig.module, sig.signal_type) in pge_keys:
            # PIE insight overlaps with PGE guidance → suppress
            logger.debug(
                "EAE dedup: Suppressed PIE %s/%s (PGE guidance exists)",
                sig.module, sig.signal_type,
            )
            continue
        result.append(sig)
    return result


def _cross_channel_dedup(
    signals: List[ScoredSignal],
    recent_deliveries: List[Dict],
    channel: str,
) -> List[ScoredSignal]:
    """
    Suppress signals that were recently delivered via another channel.
    Only applies to chat channel (push items suppress from chat).
    """
    if channel != 'chat' or not recent_deliveries:
        return signals

    # Build set of recently-delivered (object_type, object_id) pairs
    delivered = set()
    for d in recent_deliveries:
        delivered.add((
            d.get('source_object_type', ''),
            d.get('source_object_id', 0),
        ))

    if not delivered:
        return signals

    result = []
    for sig in signals:
        if (sig.object_type, sig.object_id) in delivered:
            logger.debug(
                "EAE dedup: Cross-channel suppressed %s #%d (recently delivered)",
                sig.object_type, sig.object_id,
            )
            continue
        result.append(sig)
    return result


def deduplicate(
    signals: List[ScoredSignal],
    channel: str = 'chat',
    recent_deliveries: Optional[List[Dict]] = None,
) -> List[ScoredSignal]:
    """
    Apply all dedup layers to scored signals.

    Args:
        signals: Scored signals sorted by score descending.
        channel: Current delivery channel.
        recent_deliveries: Recently delivered notifications for cross-channel dedup.

    Returns:
        Deduplicated list, still sorted by score descending.
    """
    if not signals:
        return []

    original_count = len(signals)

    # Layer 1: Same-day dedup
    signals = _same_day_dedup(signals)

    # Layer 2: Prediction overlap
    signals = _prediction_overlap_dedup(signals)

    # Layer 3: Insight/Guidance overlap
    signals = _insight_guidance_dedup(signals)

    # Layer 4: Cross-channel dedup
    if recent_deliveries:
        signals = _cross_channel_dedup(signals, recent_deliveries, channel)

    # Re-sort after dedup (some items removed)
    signals.sort(key=lambda s: s.normalized_score, reverse=True)

    removed = original_count - len(signals)
    if removed > 0:
        logger.debug("EAE dedup: Removed %d duplicates (%d → %d)", removed, original_count, len(signals))

    return signals
