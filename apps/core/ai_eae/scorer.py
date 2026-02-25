"""
EAE — Signal Scorer & Normalizer (Phase 8.2).

Normalizes raw signals from all engines to a unified 0–100 scale using:
    normalized = (local × 0.35) + (drift_anchor × 0.30)
                + (governance × 0.20) + (recency × 0.15)

Applies confidence thresholds and intensity multiplier.
"""
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, List, Optional

from django.utils import timezone

from apps.core.ai_eae.constants import (
    CONFIDENCE_HIGH_BOOST,
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_LOW_PENALTY,
    CONFIDENCE_LOW_THRESHOLD,
    GOVERNANCE_FLEXIBLE,
    GOVERNANCE_IMPORTANT,
    GOVERNANCE_NON_NEGOTIABLE,
    GOVERNANCE_UNCATEGORIZED,
    RECENCY_DECAY_HOURS,
    WEIGHT_DRIFT_ANCHOR,
    WEIGHT_GOVERNANCE,
    WEIGHT_LOCAL_SCORE,
    WEIGHT_RECENCY,
    apply_intensity,
)
from apps.core.ai_eae.signal_collector import RawSignal, RawSignalSet

logger = logging.getLogger(__name__)


# =============================================================================
# SCORED SIGNAL — Signal with normalized score
# =============================================================================


@dataclass
class ScoredSignal:
    """A signal with its normalized score and scoring breakdown."""

    raw: RawSignal
    normalized_score: float     # 0–100 final score
    drift_anchor_weight: float  # How much drift contributed
    governance_weight: float    # Governance importance weight
    recency_weight: float       # Recency factor

    # Scoring breakdown for audit
    component_local: float = 0.0
    component_drift: float = 0.0
    component_governance: float = 0.0
    component_recency: float = 0.0
    confidence_modifier: float = 0.0

    # Passthrough from RawSignal
    @property
    def engine(self):
        return self.raw.engine

    @property
    def signal_type(self):
        return self.raw.signal_type

    @property
    def module(self):
        return self.raw.module

    @property
    def title(self):
        return self.raw.title

    @property
    def message(self):
        return self.raw.message

    @property
    def confidence(self):
        return self.raw.confidence

    @property
    def severity(self):
        return self.raw.severity

    @property
    def object_type(self):
        return self.raw.object_type

    @property
    def object_id(self):
        return self.raw.object_id

    @property
    def created_at(self):
        return self.raw.created_at

    @property
    def actionable(self):
        return self.raw.actionable

    @property
    def action_url(self):
        return self.raw.action_url

    @property
    def bundle_key(self):
        return self.raw.bundle_key

    @property
    def evidence(self):
        return self.raw.evidence

    @property
    def metadata(self):
        return self.raw.metadata


# =============================================================================
# GOVERNANCE WEIGHT LOOKUP
# =============================================================================


def _get_governance_weights(user) -> Dict[str, float]:
    """
    Load governance importance weights per module from GovernanceProfile.
    Returns dict mapping module_key -> importance_weight.
    """
    try:
        from apps.core.ai_governance.models import GovernanceProfile

        profiles = GovernanceProfile.objects.filter(
            user=user,
            is_active=True,
        ).values('module_key', 'commitment_level', 'importance_weight')

        weights = {}
        for p in profiles:
            weights[p['module_key']] = p['importance_weight'] or GOVERNANCE_UNCATEGORIZED
        return weights
    except Exception as e:
        logger.warning("EAE: Failed to load governance weights: %s", e)
        return {}


def _get_module_drift_scores(user) -> Dict[str, float]:
    """
    Load per-module drift scores from SAE state_data.
    Returns dict mapping module_key -> drift_score (0-100).
    """
    try:
        from apps.core.ai_state.models import UserState
        state = UserState.objects.filter(user=user).first()
        if not state or not state.state_data:
            return {}

        scores = {}
        for module_key, data in state.state_data.items():
            if isinstance(data, dict):
                drift = data.get('drift_score', 0)
                if drift:
                    scores[module_key] = float(drift)
        return scores
    except Exception as e:
        logger.warning("EAE: Failed to load module drift scores: %s", e)
        return {}


# =============================================================================
# SCORING FUNCTIONS
# =============================================================================


def _compute_recency(created_at, now=None) -> float:
    """
    Compute recency weight (0.0–1.0). Linear decay over RECENCY_DECAY_HOURS.
    Most recent = 1.0, older than decay window = 0.0.
    """
    if not created_at:
        return 0.5  # Unknown age → middle weight
    if now is None:
        now = timezone.now()

    # Ensure both are timezone-aware for comparison
    if hasattr(created_at, 'tzinfo') and created_at.tzinfo is None:
        from django.utils.timezone import make_aware
        created_at = make_aware(created_at)

    age_hours = max(0, (now - created_at).total_seconds() / 3600)
    return max(0.0, 1.0 - (age_hours / RECENCY_DECAY_HOURS))


def _compute_drift_anchor(
    signal: RawSignal,
    drift_risk_severity: float,
    module_drift_scores: Dict[str, float],
    governance_weights: Dict[str, float],
) -> float:
    """
    Compute drift anchor weight for a signal.

    If the signal's module is drifting, this boosts its score proportionally
    to drift severity × governance importance.

    Returns a value 0–100.
    """
    module = signal.module
    if not module:
        return 0.0

    # Per-module drift (more specific) takes priority over global drift
    module_drift = module_drift_scores.get(module, 0.0)
    if module_drift > 0:
        drift_factor = module_drift / 100.0
    elif drift_risk_severity > 0:
        drift_factor = drift_risk_severity / 100.0
    else:
        return 0.0

    # Scale by governance importance
    gov_weight = governance_weights.get(module, GOVERNANCE_UNCATEGORIZED)
    # Normalize governance weight: non_negotiable(2.0)→1.0, important(1.0)→0.5, flexible(0.3)→0.15
    gov_factor = gov_weight / GOVERNANCE_NON_NEGOTIABLE

    return drift_factor * gov_factor * 100.0


def score_signal(
    signal: RawSignal,
    drift_risk_severity: float,
    module_drift_scores: Dict[str, float],
    governance_weights: Dict[str, float],
    intensity: float = 1.0,
    now=None,
) -> ScoredSignal:
    """
    Score a single signal using the normalization formula.

    normalized = (local × 0.35) + (drift_anchor × 0.30)
                + (governance × 0.20) + (recency × 0.15)
                + confidence_modifier
    """
    # Component: local score (clamped 0-100)
    local = max(0.0, min(100.0, signal.local_score))

    # Component: drift anchor
    drift_anchor = _compute_drift_anchor(
        signal, drift_risk_severity, module_drift_scores, governance_weights,
    )
    # Apply intensity to drift anchor weight (higher intensity = drift matters more)
    drift_anchor = apply_intensity(drift_anchor, intensity)

    # Component: governance weight (raw importance → 0-100 scale)
    gov_raw = governance_weights.get(signal.module, GOVERNANCE_UNCATEGORIZED)
    gov_normalized = (gov_raw / GOVERNANCE_NON_NEGOTIABLE) * 100.0

    # Component: recency
    recency = _compute_recency(signal.created_at, now) * 100.0

    # Weighted sum
    normalized = (
        local * WEIGHT_LOCAL_SCORE
        + drift_anchor * WEIGHT_DRIFT_ANCHOR
        + gov_normalized * WEIGHT_GOVERNANCE
        + recency * WEIGHT_RECENCY
    )

    # Confidence modifier
    confidence_mod = 0.0
    if signal.confidence >= CONFIDENCE_HIGH_THRESHOLD:
        confidence_mod = apply_intensity(CONFIDENCE_HIGH_BOOST, intensity)
    elif signal.confidence <= CONFIDENCE_LOW_THRESHOLD:
        confidence_mod = apply_intensity(CONFIDENCE_LOW_PENALTY, intensity)

    normalized += confidence_mod
    normalized = max(0.0, min(100.0, normalized))

    return ScoredSignal(
        raw=signal,
        normalized_score=normalized,
        drift_anchor_weight=drift_anchor,
        governance_weight=gov_raw,
        recency_weight=recency / 100.0,
        component_local=local * WEIGHT_LOCAL_SCORE,
        component_drift=drift_anchor * WEIGHT_DRIFT_ANCHOR,
        component_governance=gov_normalized * WEIGHT_GOVERNANCE,
        component_recency=recency * WEIGHT_RECENCY,
        confidence_modifier=confidence_mod,
    )


# =============================================================================
# MAIN SCORING FUNCTION
# =============================================================================


def score_signals(
    signal_set: RawSignalSet,
    user,
    intensity: float = 1.0,
) -> List[ScoredSignal]:
    """
    Score all signals in a RawSignalSet.

    Args:
        signal_set: Collected signals from signal_collector.
        user: Django User instance.
        intensity: Intensity multiplier (default 1.0).

    Returns:
        List of ScoredSignal, sorted by normalized_score descending.
    """
    if not signal_set.signals:
        return []

    # Load external data once (not per-signal)
    governance_weights = _get_governance_weights(user)
    module_drift_scores = _get_module_drift_scores(user)
    now = timezone.now()

    scored = []
    for signal in signal_set.signals:
        scored_signal = score_signal(
            signal=signal,
            drift_risk_severity=signal_set.drift_risk_severity,
            module_drift_scores=module_drift_scores,
            governance_weights=governance_weights,
            intensity=intensity,
            now=now,
        )
        scored.append(scored_signal)

    # Sort by normalized_score descending (highest priority first)
    scored.sort(key=lambda s: s.normalized_score, reverse=True)

    logger.debug(
        "EAE: Scored %d signals for user %s (top score: %.1f)",
        len(scored), user.pk,
        scored[0].normalized_score if scored else 0,
    )

    return scored
