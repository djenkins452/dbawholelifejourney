# ==============================================================================
# File: apps/core/ai_eae/pattern_engine.py
# Description: Phase 5 — Cross-Domain Pattern Engine
#
# Reads base SignalSnapshot rows (verified_action, verified_measurement,
# inferred_behavior) and computes higher-order derived_pattern SignalSnapshots.
#
# Design rules:
# - NEVER queries raw domain models — only reads SignalSnapshots
# - NEVER modifies existing snapshots or signal computers
# - Uses SignalAggregationService._upsert_snapshot() for persistence
# - Deterministic rules only — no LLM, no ML
# - Returns None for insufficient data (missing data = no row)
# - Pattern confidence is discounted from source signal confidence
# ==============================================================================
"""
Phase 5 — Cross-Domain Pattern Engine.

Derives higher-order pattern signals from combinations of base signals
across domains or time. Patterns are stored as SignalSnapshots with
signal_class='derived_pattern' and flow into CoS context automatically.
"""

import datetime as dt
import logging
from typing import Dict, List, Optional

from apps.core.ai_eae.models import SignalSnapshot
from apps.core.ai_eae.pattern_taxonomy import (
    PATTERN_CONFIDENCE_DISCOUNT,
    PATTERN_TYPES,
)

logger = logging.getLogger(__name__)


class PatternEngine:
    """
    Computes cross-domain pattern signals from base SignalSnapshots.

    Each pattern rule follows the contract:
    - Input: signal_map (today's base signals), history (7-day data)
    - Output: dict with {score, confidence, source_signals} or None
    - None means insufficient data — no snapshot will be created
    """

    @staticmethod
    def compute_patterns(user, date) -> List[SignalSnapshot]:
        """
        Compute all pattern types for a user on a given date.

        Fetches today's base signals and 7-day history, then runs each
        pattern rule. Returns list of upserted derived_pattern snapshots.
        """
        from apps.core.ai_eae.signal_aggregation import SignalAggregationService

        # Fetch today's base signals (exclude existing derived patterns)
        todays_signals = _get_todays_base_signals(user, date)
        if not todays_signals:
            return []

        # Fetch 7-day history for trend computation
        history = _get_signal_history(user, date, days=7)

        # Map of signal_type -> today's snapshot dict
        signal_map = {s['signal_type']: s for s in todays_signals}

        results = []
        pattern_rules = [
            ('recovery_risk', PatternEngine._evaluate_recovery_risk),
            ('holistic_momentum', PatternEngine._evaluate_holistic_momentum),
            ('domain_neglect', PatternEngine._evaluate_domain_neglect),
            ('compliance_drift', PatternEngine._evaluate_compliance_drift),
            ('wellbeing_convergence', PatternEngine._evaluate_wellbeing_convergence),
        ]

        for pattern_type, rule_fn in pattern_rules:
            try:
                result = rule_fn(signal_map, history)
                if result is not None:
                    snapshot = SignalAggregationService._upsert_snapshot(
                        user=user,
                        date=date,
                        signal_type=pattern_type,
                        score=result['score'],
                        confidence=result['confidence'],
                        signal_class='derived_pattern',
                        source_signals=result['source_signals'],
                    )
                    results.append(snapshot)
            except Exception as e:
                logger.warning(
                    "Pattern rule %s failed for user %s on %s: %s",
                    pattern_type, user.pk, date, e,
                    exc_info=True,
                )

        return results

    # ──────────────────────────────────────────────────────────
    # Pattern Rules
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _evaluate_recovery_risk(
        signal_map: Dict, history: Dict,
    ) -> Optional[Dict]:
        """
        recovery_risk: health_activity HIGH + health_biometrics LOW.

        Detects overtraining without adequate recovery. Fires when
        activity is strong (>=0.7) but biometrics are poor (<0.4).

        Score = activity_score * (1 - biometrics_score), clamped to [0, 1].
        Higher score = higher risk.
        """
        activity = signal_map.get('health_activity')
        biometrics = signal_map.get('health_biometrics')

        if not activity or not biometrics:
            return None

        activity_score = activity['score']
        bio_score = biometrics['score']

        # Rule: activity must be high AND biometrics must be low
        if activity_score < 0.7 or bio_score >= 0.4:
            return None

        score = min(1.0, activity_score * (1.0 - bio_score))
        confidence = min(activity['confidence'], biometrics['confidence'])
        confidence *= PATTERN_CONFIDENCE_DISCOUNT

        return {
            'score': round(score, 3),
            'confidence': round(confidence, 3),
            'source_signals': {
                'health_activity': activity_score,
                'health_biometrics': bio_score,
                'pattern_rule': 'activity >= 0.7 AND biometrics < 0.4',
            },
        }

    @staticmethod
    def _evaluate_holistic_momentum(
        signal_map: Dict, history: Dict,
    ) -> Optional[Dict]:
        """
        holistic_momentum: 3+ signal types >= 0.7 across 2+ domains.

        Detects positive life momentum when the user is performing well
        across multiple life areas simultaneously.

        Score = average of qualifying signal scores.
        """
        THRESHOLD = 0.7
        qualifying = []
        domains_seen = set()

        for sig_type, sig in signal_map.items():
            if sig['score'] >= THRESHOLD:
                qualifying.append(sig)
                domains_seen.add(sig['domain'])

        if len(qualifying) < 3 or len(domains_seen) < 2:
            return None

        avg_score = sum(s['score'] for s in qualifying) / len(qualifying)
        min_conf = min(s['confidence'] for s in qualifying)
        confidence = min_conf * PATTERN_CONFIDENCE_DISCOUNT

        return {
            'score': round(avg_score, 3),
            'confidence': round(confidence, 3),
            'source_signals': {
                'qualifying_signals': {
                    s['signal_type']: s['score'] for s in qualifying
                },
                'domain_count': len(domains_seen),
                'signal_count': len(qualifying),
                'pattern_rule': '3+ signals >= 0.7 across 2+ domains',
            },
        }

    @staticmethod
    def _evaluate_domain_neglect(
        signal_map: Dict, history: Dict,
    ) -> Optional[Dict]:
        """
        domain_neglect: a domain with 2+ signal types ALL declining (7-day trend).

        Detects systematic neglect of an entire life area. Uses the 7-day
        trend data from signal history.

        Score = 1.0 - average of declining signal scores (lower scores = higher neglect).
        Reports the worst (most neglected) domain.
        """
        # Group today's signals by domain
        domain_signals = {}
        for sig_type, sig in signal_map.items():
            domain = sig['domain']
            domain_signals.setdefault(domain, []).append(sig)

        worst_domain = None
        worst_score = 1.0
        worst_evidence = {}

        for domain, signals in domain_signals.items():
            if len(signals) < 2:
                continue

            # Check if ALL signals in this domain are declining
            all_declining = True
            declining_details = {}

            for sig in signals:
                trend = _get_trend_from_history(history, sig['signal_type'])
                if trend != 'declining':
                    all_declining = False
                    break
                declining_details[sig['signal_type']] = sig['score']

            if all_declining:
                avg_score = sum(declining_details.values()) / len(declining_details)
                if avg_score < worst_score:
                    worst_score = avg_score
                    worst_domain = domain
                    worst_evidence = declining_details

        if worst_domain is None:
            return None

        # Score: higher = more neglected (invert the average)
        neglect_score = max(0.0, min(1.0, 1.0 - worst_score))

        # Confidence based on number of data points in history
        history_depth = sum(
            len(history.get(st, []))
            for st in worst_evidence
        )
        confidence = min(0.85, 0.5 + (history_depth * 0.025))
        confidence *= PATTERN_CONFIDENCE_DISCOUNT

        return {
            'score': round(neglect_score, 3),
            'confidence': round(confidence, 3),
            'source_signals': {
                'neglected_domain': worst_domain,
                'declining_signals': worst_evidence,
                'pattern_rule': '2+ signals in same domain ALL declining over 7 days',
            },
        }

    @staticmethod
    def _evaluate_compliance_drift(
        signal_map: Dict, history: Dict,
    ) -> Optional[Dict]:
        """
        compliance_drift: medication_adherence declining + health_biometrics declining.

        Detects medical compliance risk when both medication adherence
        and biometric health are trending downward together.

        Score = (1 - med_adherence) * (1 - biometrics) * 4, clamped to [0, 1].
        """
        med = signal_map.get('medication_adherence')
        bio = signal_map.get('health_biometrics')

        if not med or not bio:
            return None

        # Both must be declining in trend
        med_trend = _get_trend_from_history(history, 'medication_adherence')
        bio_trend = _get_trend_from_history(history, 'health_biometrics')

        if med_trend != 'declining' or bio_trend != 'declining':
            return None

        # Score: higher = worse compliance
        # The *4 multiplier ensures meaningful scores when both are moderately low
        # e.g., both at 0.5 → (0.5 * 0.5 * 4) = 1.0
        score = min(1.0, (1.0 - med['score']) * (1.0 - bio['score']) * 4)

        confidence = min(med['confidence'], bio['confidence'])
        confidence *= PATTERN_CONFIDENCE_DISCOUNT

        return {
            'score': round(score, 3),
            'confidence': round(confidence, 3),
            'source_signals': {
                'medication_adherence': med['score'],
                'medication_trend': med_trend,
                'health_biometrics': bio['score'],
                'biometrics_trend': bio_trend,
                'pattern_rule': 'medication_adherence declining AND health_biometrics declining',
            },
        }

    @staticmethod
    def _evaluate_wellbeing_convergence(
        signal_map: Dict, history: Dict,
    ) -> Optional[Dict]:
        """
        wellbeing_convergence: mental_reflection + relational_engagement + faith_practice ALL >= 0.6.

        Detects emotional/spiritual wellbeing convergence when the user
        is engaged in introspection, relationships, and spiritual practice.

        Score = average of the three signal scores.
        """
        THRESHOLD = 0.6
        required = ['mental_reflection', 'relational_engagement', 'faith_practice']

        signals = []
        for st in required:
            sig = signal_map.get(st)
            if not sig or sig['score'] < THRESHOLD:
                return None
            signals.append(sig)

        avg_score = sum(s['score'] for s in signals) / len(signals)
        min_conf = min(s['confidence'] for s in signals)
        confidence = min_conf * PATTERN_CONFIDENCE_DISCOUNT

        source = {s['signal_type']: s['score'] for s in signals}
        source['pattern_rule'] = 'mental_reflection + relational + faith ALL >= 0.6'

        return {
            'score': round(avg_score, 3),
            'confidence': round(confidence, 3),
            'source_signals': source,
        }


# ──────────────────────────────────────────────────────────
# Private helpers
# ──────────────────────────────────────────────────────────


def _get_todays_base_signals(user, date) -> List[Dict]:
    """Fetch today's non-derived signals as dicts."""
    snapshots = SignalSnapshot.objects.filter(
        user=user,
        date=date,
    ).exclude(
        signal_class='derived_pattern',
    )
    return [
        {
            'signal_type': s.signal_type,
            'domain': s.domain,
            'score': s.score,
            'confidence': s.confidence,
            'signal_class': s.signal_class,
        }
        for s in snapshots
    ]


def _get_signal_history(user, date, days=7) -> Dict[str, List[Dict]]:
    """
    Fetch signal history for trend computation.

    Returns: {signal_type: [{date, score}, ...]} ordered oldest-first.
    Only includes base signals (excludes derived patterns).
    """
    window_start = date - dt.timedelta(days=days)
    snapshots = SignalSnapshot.objects.filter(
        user=user,
        date__gte=window_start,
        date__lte=date,
    ).exclude(
        signal_class='derived_pattern',
    ).order_by('date')

    history = {}
    for s in snapshots:
        history.setdefault(s.signal_type, []).append({
            'date': s.date,
            'score': s.score,
        })
    return history


def _get_trend_from_history(history: Dict, signal_type: str) -> str:
    """
    Compute trend direction from history dict.

    Returns 'improving', 'declining', or 'stable'.
    Mirrors the logic in cos_context._compute_signal_trend.
    """
    data_points = history.get(signal_type, [])
    if len(data_points) < 2:
        return 'stable'

    scores = [d['score'] for d in data_points]
    mid = len(scores) // 2
    first_half = sum(scores[:mid]) / mid
    second_half = sum(scores[mid:]) / len(scores[mid:])

    diff = second_half - first_half
    if diff > 0.1:
        return 'improving'
    elif diff < -0.1:
        return 'declining'
    return 'stable'
