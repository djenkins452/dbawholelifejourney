"""
EAE — Signal Collector (Phase 8.2).

Gathers all active intelligence signals from every engine into a unified
RawSignalSet for scoring and arbitration. Read-only access to all engine
models — never writes to them.

Signals collected:
    PIE Insights, PRIE Predictions, PGE Guidance, CDCE Correlations,
    ECC Commitments, UAL Arbitration, Drift/Pressure state, Protective alerts
"""
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Dict, List, Optional

from django.utils import timezone

logger = logging.getLogger(__name__)


# =============================================================================
# RAW SIGNAL — Unified wrapper for any engine output
# =============================================================================


@dataclass
class RawSignal:
    """A single intelligence signal from any engine."""

    engine: str             # PIE, PRIE, PGE, CDCE, ECC, DRIFT, PROTECTIVE, UAL
    signal_type: str        # Engine-specific type (e.g., 'weight_trend_up')
    module: str             # Life domain (health, faith, journal, goals, etc.)
    title: str              # Human-readable title
    message: str            # Explanation or detail

    # Scoring inputs
    local_score: float      # Engine's own score (will be normalized by scorer)
    confidence: float       # 0.0–1.0
    severity: str           # info, positive, warning, critical

    # Source reference
    object_type: str        # Model class name (e.g., 'Insight', 'Prediction')
    object_id: int          # Database PK
    created_at: Any         # datetime

    # Optional fields
    actionable: bool = False
    action_url: str = ''
    evidence: Dict = field(default_factory=dict)
    metadata: Dict = field(default_factory=dict)

    # For bundling detection
    bundle_key: str = ''    # Signals with same bundle_key can be bundled


@dataclass
class RawSignalSet:
    """All signals collected for a user, ready for scoring."""

    signals: List[RawSignal] = field(default_factory=list)
    drift_risk_severity: float = 0.0
    capacity_score: float = 0.5
    capacity_state: str = 'NORMAL'
    collection_errors: List[str] = field(default_factory=list)

    @property
    def engine_names(self):
        """Unique engine names that contributed signals."""
        return list({s.engine for s in self.signals})


# =============================================================================
# SIGNAL COLLECTION FUNCTIONS (one per engine)
# =============================================================================


def _collect_pie_insights(user) -> List[RawSignal]:
    """Collect active PIE insights (not dismissed)."""
    try:
        from apps.core.ai_insights.models import Insight
        from apps.core.ai_eae.constants import SEVERITY_WEIGHTS

        insights = Insight.objects.filter(
            user=user,
            status__in=['new', 'read'],
        ).order_by('-created_at')[:20]  # Cap to prevent runaway queries

        signals = []
        for ins in insights:
            severity_score = SEVERITY_WEIGHTS.get(ins.severity, 10)
            local_score = severity_score * (ins.confidence_score or 0.5)
            signals.append(RawSignal(
                engine='PIE',
                signal_type=ins.insight_type,
                module=ins.module or '',
                title=ins.title or '',
                message=ins.message or '',
                local_score=local_score,
                confidence=ins.confidence_score or 0.5,
                severity=ins.severity or 'info',
                object_type='Insight',
                object_id=ins.pk,
                created_at=ins.created_at,
                evidence=ins.evidence or {},
                bundle_key=f"PIE:{ins.module}:{ins.severity}",
            ))
        return signals
    except Exception as e:
        logger.warning("EAE: Failed to collect PIE insights: %s", e)
        return []


def _collect_prie_predictions(user) -> List[RawSignal]:
    """Collect active PRIE predictions (not expired/superseded)."""
    try:
        from apps.core.ai_predictions.models import Prediction
        from apps.core.ai_eae.constants import HORIZON_URGENCY

        now = timezone.now()
        predictions = Prediction.objects.filter(
            user=user,
            status='active',
        ).order_by('-confidence_score')[:15]

        signals = []
        for pred in predictions:
            # Calculate horizon urgency
            if pred.predicted_date:
                days_out = max(0, (pred.predicted_date - now).days)
                urgency = 1.0
                for threshold, mult in sorted(HORIZON_URGENCY.items()):
                    if days_out <= threshold:
                        urgency = mult
                        break
                else:
                    urgency = 0.3  # Beyond 90 days
            else:
                urgency = 0.5
                days_out = 30

            local_score = (pred.confidence_score or 0.5) * 100 * urgency
            signals.append(RawSignal(
                engine='PRIE',
                signal_type=pred.prediction_type,
                module=pred.module or '',
                title=f"Prediction: {pred.prediction_type}",
                message=pred.explanation or '',
                local_score=local_score,
                confidence=pred.confidence_score or 0.5,
                severity='warning' if urgency >= 0.7 else 'info',
                object_type='Prediction',
                object_id=pred.pk,
                created_at=pred.created_at,
                evidence=pred.evidence or {},
                metadata={'predicted_date': str(pred.predicted_date), 'days_out': days_out},
                bundle_key=f"PRIE:{pred.module}:{pred.prediction_type}",
            ))
        return signals
    except Exception as e:
        logger.warning("EAE: Failed to collect PRIE predictions: %s", e)
        return []


def _collect_pge_guidance(user) -> List[RawSignal]:
    """Collect active PGE guidance items (not dismissed/snoozed)."""
    try:
        from apps.core.ai_guidance.models import GuidanceItem
        from apps.core.ai_eae.constants import PRIORITY_WEIGHTS

        now = timezone.now()
        items = GuidanceItem.objects.filter(
            user=user,
            is_active=True,
            dismissed_at__isnull=True,
        ).exclude(
            snoozed_until__gt=now,  # Exclude currently snoozed
        ).order_by('priority')[:15]

        signals = []
        for gi in items:
            priority_score = PRIORITY_WEIGHTS.get(gi.priority, 25)
            confidence = gi.confidence_score if gi.confidence_score is not None else 0.6
            local_score = priority_score * confidence

            # Map priority to severity
            severity_map = {1: 'critical', 2: 'warning', 3: 'warning', 4: 'info', 5: 'info'}
            severity = severity_map.get(gi.priority, 'info')

            signals.append(RawSignal(
                engine='PGE',
                signal_type=gi.guidance_type or '',
                module=gi.module or '',
                title=gi.title or '',
                message=gi.message or '',
                local_score=local_score,
                confidence=confidence,
                severity=severity,
                object_type='GuidanceItem',
                object_id=gi.pk,
                created_at=gi.created_at,
                actionable=True,
                evidence=gi.evidence or {},
                bundle_key=f"PGE:{gi.module}:{gi.guidance_type}",
            ))
        return signals
    except Exception as e:
        logger.warning("EAE: Failed to collect PGE guidance: %s", e)
        return []


def _collect_cdce_correlations(user) -> List[RawSignal]:
    """Collect active cross-domain correlations (strong/moderate only)."""
    try:
        from apps.core.ai_cross_domain.models import DomainCorrelation

        correlations = DomainCorrelation.objects.filter(
            user=user,
            status='active',
            strength__in=['strong', 'moderate'],
        ).order_by('-strength_score')[:10]

        signals = []
        for corr in correlations:
            local_score = (corr.strength_score or 0.5) * 100
            signals.append(RawSignal(
                engine='CDCE',
                signal_type=corr.correlation_type or '',
                module=corr.domain_a or '',
                title=f"{corr.domain_a} ↔ {corr.domain_b}: {corr.correlation_type}",
                message=corr.narrative or '',
                local_score=local_score,
                confidence=corr.strength_score or 0.5,
                severity='warning' if corr.strength == 'strong' else 'info',
                object_type='DomainCorrelation',
                object_id=corr.pk,
                created_at=corr.created_at,
                evidence=corr.evidence or {},
                bundle_key=f"CDCE:{corr.domain_a}:{corr.domain_b}",
            ))
        return signals
    except Exception as e:
        logger.warning("EAE: Failed to collect CDCE correlations: %s", e)
        return []


def _collect_drift_state(user) -> tuple:
    """
    Collect drift risk severity and instability score.
    Returns (drift_risk_severity, signals_list).
    """
    drift_severity = 0.0
    signals = []
    try:
        from apps.core.ai_state.models import UserState
        state = UserState.objects.filter(user=user).first()
        if state:
            instability = getattr(state, 'schedule_instability_score', 0) or 0
            # Normalize instability to 0-100 scale (8 = threshold from drift engine)
            drift_severity = min(100.0, (instability / 8.0) * 50)

            # Also pull per-module drift from state_data if available
            state_data = state.state_data or {}
            for module_key, module_data in state_data.items():
                if isinstance(module_data, dict):
                    module_drift = module_data.get('drift_score', 0)
                    if module_drift and module_drift > 20:
                        signals.append(RawSignal(
                            engine='DRIFT',
                            signal_type='module_drift',
                            module=module_key,
                            title=f"Drift in {module_key}",
                            message=f"Drift score: {module_drift:.0f}",
                            local_score=float(module_drift),
                            confidence=0.8,
                            severity='warning' if module_drift >= 40 else 'info',
                            object_type='UserState',
                            object_id=state.pk,
                            created_at=state.last_updated,
                            bundle_key=f"DRIFT:{module_key}",
                        ))
    except Exception as e:
        logger.warning("EAE: Failed to collect drift state: %s", e)

    return drift_severity, signals


def _collect_pressure_state(user) -> tuple:
    """
    Collect capacity/pressure state.
    Returns (capacity_score, capacity_state, signals_list).
    """
    capacity_score = 0.5
    capacity_state = 'NORMAL'
    signals = []
    try:
        from apps.core.blueprint.pressure_models import PressureSnapshot

        snapshot = PressureSnapshot.objects.filter(
            user=user,
        ).order_by('-computed_at').first()

        if snapshot:
            cpi = snapshot.pressure_index or 0
            capacity_score = max(0.0, 1.0 - (cpi / 100.0))

            if capacity_score < 0.2:
                capacity_state = 'CRITICAL'
            elif capacity_score < 0.4:
                capacity_state = 'LOW'
            elif capacity_score > 0.7:
                capacity_state = 'HIGH_CAPACITY'

            if cpi >= 60:
                signals.append(RawSignal(
                    engine='PROTECTIVE',
                    signal_type='pressure_alert',
                    module='schedule',
                    title=f"Pressure Index: {cpi:.0f}/100",
                    message=f"Capacity state: {capacity_state}",
                    local_score=float(cpi),
                    confidence=0.9,
                    severity='critical' if cpi >= 90 else 'warning',
                    object_type='PressureSnapshot',
                    object_id=snapshot.pk,
                    created_at=snapshot.computed_at,
                    bundle_key='PROTECTIVE:pressure',
                ))
    except Exception as e:
        logger.warning("EAE: Failed to collect pressure state: %s", e)

    return capacity_score, capacity_state, signals


def _collect_recent_deliveries(user, hours=4) -> List[Dict]:
    """
    Collect recently delivered notifications for cross-channel dedup.
    Returns list of dicts with {engine, object_type, object_id, channel}.
    """
    try:
        from apps.core.ai_delivery.models import DeliveredNotification

        cutoff = timezone.now() - timedelta(hours=hours)
        deliveries = DeliveredNotification.objects.filter(
            user=user,
            status='sent',
            delivered_at__gte=cutoff,
        ).values('source_engine', 'source_object_type', 'source_object_id', 'channel')

        return list(deliveries)
    except Exception as e:
        logger.warning("EAE: Failed to collect recent deliveries: %s", e)
        return []


# =============================================================================
# MAIN COLLECTION FUNCTION
# =============================================================================


def collect_signals(user) -> RawSignalSet:
    """
    Collect all active intelligence signals for a user.

    This is the sole entry point for signal collection. It reads from all
    engines (PIE, PRIE, PGE, CDCE, Drift, Pressure) and returns a unified
    RawSignalSet ready for scoring.

    Args:
        user: Django User instance.

    Returns:
        RawSignalSet with all collected signals and state metadata.
    """
    result = RawSignalSet()

    # Collect from each engine (order doesn't matter — scoring normalizes)
    pie_signals = _collect_pie_insights(user)
    prie_signals = _collect_prie_predictions(user)
    pge_signals = _collect_pge_guidance(user)
    cdce_signals = _collect_cdce_correlations(user)

    # Collect state (drift + pressure)
    drift_severity, drift_signals = _collect_drift_state(user)
    capacity_score, capacity_state, pressure_signals = _collect_pressure_state(user)

    # Assemble
    result.signals = (
        pie_signals + prie_signals + pge_signals + cdce_signals
        + drift_signals + pressure_signals
    )
    result.drift_risk_severity = drift_severity
    result.capacity_score = capacity_score
    result.capacity_state = capacity_state

    logger.debug(
        "EAE: Collected %d signals for user %s "
        "(PIE=%d, PRIE=%d, PGE=%d, CDCE=%d, DRIFT=%d, PRESS=%d)",
        len(result.signals), user.pk,
        len(pie_signals), len(prie_signals), len(pge_signals),
        len(cdce_signals), len(drift_signals), len(pressure_signals),
    )

    return result
