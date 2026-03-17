# ==============================================================================
# File: apps/core/ai_eae/targeted_recompute.py
# Description: Phase 5.5 — Targeted signal recompute after extraction
# Created: 2026-03-16
# ==============================================================================
"""
TargetedSignalRecomputeService — Recompute only affected signals.

Called after CaptureSignal/DocumentSignal extraction completes.
Instead of running full compute_daily_signals(), this service:
1. Blends ONLY the affected signal types from extraction sources
2. Triggers targeted pattern recompute for affected domains
3. All writes go through _upsert_snapshot() (no bypass)

This ensures signals update within the SAME cycle (~60s) rather than
waiting for the nightly aggregation at 4:30 AM UTC.
"""

import logging
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

# Confidence discount multipliers (hierarchy: verified > journal > capture > doc_llm > doc_rule)
CAPTURE_CONFIDENCE_DISCOUNT = 0.6
DOCUMENT_LLM_CONFIDENCE_DISCOUNT = 0.5
DOCUMENT_RULE_CONFIDENCE_DISCOUNT = 0.4

# Telemetry cache keys
CAPTURE_TELEMETRY_KEY = 'wlj:ops:capture_extraction'
DOCUMENT_TELEMETRY_KEY = 'wlj:ops:document_extraction'
TELEMETRY_TTL = 25 * 3600  # 25 hours


class TargetedSignalRecomputeService:
    """
    Targeted recompute of signals after extraction.

    Blends extraction signals for specific (user, date, signal_types) only.
    Does NOT run the full compute_daily_signals pipeline.
    """

    @staticmethod
    def recompute_for_capture(user, date, capture_signals):
        """
        Blend capture extraction signals into SignalSnapshots.

        Args:
            user: User instance
            date: date object
            capture_signals: QuerySet or list of CaptureSignal records
        """
        affected_types = set()
        try:
            affected_types = _blend_capture_signals(user, date, capture_signals)
        except Exception as e:
            logger.warning(
                "Capture signal blending failed for user %s on %s: %s",
                user.pk, date, e, exc_info=True,
            )

        # Trigger targeted pattern recompute if any signals were affected
        if affected_types:
            _recompute_affected_patterns(user, date)

        return affected_types

    @staticmethod
    def recompute_for_document(user, date, document_signals):
        """
        Blend document extraction signals into SignalSnapshots.

        Args:
            user: User instance
            date: date object
            document_signals: QuerySet or list of DocumentSignal records
        """
        affected_types = set()
        try:
            affected_types = _blend_document_signals(user, date, document_signals)
        except Exception as e:
            logger.warning(
                "Document signal blending failed for user %s on %s: %s",
                user.pk, date, e, exc_info=True,
            )

        if affected_types:
            _recompute_affected_patterns(user, date)

        return affected_types


def _blend_capture_signals(user, date, capture_signals):
    """
    Blend capture extraction signals into existing SignalSnapshots.

    Rules:
    - Verified/measurement snapshots: annotate only, never override
    - Existing inferred_behavior: highest confidence wins (not execution order)
    - No existing snapshot: create inferred_behavior with discounted confidence
    - Negative direction: score = 1.0 - discounted_confidence (penalty)
    - Positive direction: score = discounted_confidence

    Returns set of affected signal types.
    """
    from apps.core.ai_eae.models import SignalSnapshot
    from apps.core.ai_eae.signal_aggregation import (
        SIGNAL_TYPE_DOMAIN,
        SignalAggregationService,
    )

    if not capture_signals:
        return set()

    # Group by signal_type, take best confidence per type
    by_type = {}
    for cs in capture_signals:
        existing = by_type.get(cs.signal_type)
        if existing is None or cs.confidence > existing.confidence:
            by_type[cs.signal_type] = cs

    affected = set()

    for signal_type, best_signal in by_type.items():
        discounted = best_signal.confidence * CAPTURE_CONFIDENCE_DISCOUNT

        # Build source attribution
        all_signals_for_type = [
            s for s in capture_signals if s.signal_type == signal_type
        ]
        source_data = {
            'source': 'capture_extraction',
            'capture_entry_id': str(best_signal.entry_id),
            'extractions': [
                {
                    'text': s.extracted_text[:100],
                    'confidence': s.confidence,
                    'direction': s.direction,
                    'extractor': s.extractor_type,
                }
                for s in all_signals_for_type
            ],
        }

        # Check existing snapshot
        existing = SignalSnapshot.objects.filter(
            user=user, date=date, signal_type=signal_type,
        ).first()

        if existing and existing.signal_class in ('verified_action', 'verified_measurement'):
            # Annotate verified snapshot — NEVER override score
            source = existing.source_signals or {}
            source['capture_inferred'] = source_data['extractions']
            existing.source_signals = source
            existing.save(update_fields=['source_signals'])
            affected.add(signal_type)

        elif existing and existing.signal_class == 'inferred_behavior':
            # Compare confidence — highest wins
            if discounted > existing.confidence:
                score = _compute_score(discounted, best_signal.direction)
                domain = SIGNAL_TYPE_DOMAIN.get(signal_type, 'life')
                SignalAggregationService._upsert_snapshot(
                    user, date, signal_type,
                    score=score,
                    confidence=discounted,
                    signal_class='inferred_behavior',
                    source_signals=source_data,
                )
                affected.add(signal_type)
            else:
                # Lower confidence — just annotate
                source = existing.source_signals or {}
                source['capture_inferred'] = source_data['extractions']
                existing.source_signals = source
                existing.save(update_fields=['source_signals'])

        else:
            # No existing snapshot — create new inferred_behavior
            score = _compute_score(discounted, best_signal.direction)
            SignalAggregationService._upsert_snapshot(
                user, date, signal_type,
                score=score,
                confidence=discounted,
                signal_class='inferred_behavior',
                source_signals=source_data,
            )
            affected.add(signal_type)

    return affected


def _blend_document_signals(user, date, document_signals):
    """
    Blend document extraction signals into existing SignalSnapshots.

    Same rules as capture blending but with lower confidence discounts:
    - LLM extractions: DOCUMENT_LLM_CONFIDENCE_DISCOUNT (0.5)
    - Rule extractions: DOCUMENT_RULE_CONFIDENCE_DISCOUNT (0.4)

    Returns set of affected signal types.
    """
    from apps.core.ai_eae.models import SignalSnapshot
    from apps.core.ai_eae.signal_aggregation import (
        SIGNAL_TYPE_DOMAIN,
        SignalAggregationService,
    )

    if not document_signals:
        return set()

    # Group by signal_type, take best confidence per type
    by_type = {}
    for ds in document_signals:
        existing = by_type.get(ds.signal_type)
        if existing is None or ds.confidence > existing.confidence:
            by_type[ds.signal_type] = ds

    affected = set()

    for signal_type, best_signal in by_type.items():
        # Apply tier-appropriate discount
        if best_signal.extractor_type == 'llm':
            discount = DOCUMENT_LLM_CONFIDENCE_DISCOUNT
        else:
            discount = DOCUMENT_RULE_CONFIDENCE_DISCOUNT

        discounted = best_signal.confidence * discount

        # Build source attribution
        all_signals_for_type = [
            s for s in document_signals if s.signal_type == signal_type
        ]
        source_data = {
            'source': 'document_extraction',
            'document_id': best_signal.document_id,
            'extractions': [
                {
                    'text': s.extracted_text[:100],
                    'confidence': s.confidence,
                    'direction': s.direction,
                    'extractor': s.extractor_type,
                }
                for s in all_signals_for_type
            ],
        }

        # Check existing snapshot
        existing = SignalSnapshot.objects.filter(
            user=user, date=date, signal_type=signal_type,
        ).first()

        if existing and existing.signal_class in ('verified_action', 'verified_measurement'):
            # Annotate only
            source = existing.source_signals or {}
            source['document_inferred'] = source_data['extractions']
            existing.source_signals = source
            existing.save(update_fields=['source_signals'])
            affected.add(signal_type)

        elif existing and existing.signal_class == 'inferred_behavior':
            # Highest confidence wins
            if discounted > existing.confidence:
                score = _compute_score(discounted, best_signal.direction)
                SignalAggregationService._upsert_snapshot(
                    user, date, signal_type,
                    score=score,
                    confidence=discounted,
                    signal_class='inferred_behavior',
                    source_signals=source_data,
                )
                affected.add(signal_type)
            else:
                source = existing.source_signals or {}
                source['document_inferred'] = source_data['extractions']
                existing.source_signals = source
                existing.save(update_fields=['source_signals'])

        else:
            # No existing snapshot
            score = _compute_score(discounted, best_signal.direction)
            SignalAggregationService._upsert_snapshot(
                user, date, signal_type,
                score=score,
                confidence=discounted,
                signal_class='inferred_behavior',
                source_signals=source_data,
            )
            affected.add(signal_type)

    return affected


def _compute_score(discounted_confidence, direction):
    """
    Compute signal score from discounted confidence and direction.

    Positive: score = discounted_confidence (higher = more activity)
    Negative: score = max(0.0, 1.0 - discounted_confidence) penalty
    """
    if direction == 'negative':
        return max(0.0, min(1.0, 1.0 - discounted_confidence))
    return max(0.0, min(1.0, discounted_confidence))


def _recompute_affected_patterns(user, date):
    """Trigger pattern engine recompute for affected user/date."""
    try:
        from apps.core.ai_eae.pattern_engine import PatternEngine
        PatternEngine.compute_patterns(user, date)
    except Exception as e:
        logger.warning(
            "Targeted pattern recompute failed for user %s on %s: %s",
            user.pk, date, e,
        )


def update_extraction_telemetry(source_type, processed=0, success=0,
                                 failure=0, signals_extracted=0,
                                 avg_confidence=0.0):
    """
    Update extraction telemetry cache for Ops Wall.

    Args:
        source_type: 'capture' or 'document'
    """
    key = CAPTURE_TELEMETRY_KEY if source_type == 'capture' else DOCUMENT_TELEMETRY_KEY
    existing = cache.get(key) or {
        'processed': 0, 'success': 0, 'failure': 0,
        'signals_extracted': 0, 'last_run': None,
    }

    existing['processed'] += processed
    existing['success'] += success
    existing['failure'] += failure
    existing['signals_extracted'] += signals_extracted
    if avg_confidence > 0:
        existing['avg_confidence'] = avg_confidence
    existing['last_run'] = timezone.now().isoformat()

    cache.set(key, existing, timeout=TELEMETRY_TTL)
