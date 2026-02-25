"""
EAE — Escalation Engine (Phase 8.4).

Manages the escalation ladder (0–4) based on drift risk severity.
Escalation is immediate upward, gated downward.

Levels:
    0 = NOMINAL (drift < 40)
    1 = ELEVATED (drift 40-59 or 2+ missed NNs)
    2 = ACTIVE (drift 60-69 or 3+ decline days)
    3 = CRITICAL (drift 70-84)
    4 = OVERRIDE (drift 85+ or 5+ days at level 3)
"""
import logging
from datetime import timedelta

from django.utils import timezone

from apps.core.ai_eae.constants import (
    DEESCALATION_DRIFT_DROP,
    DEESCALATION_MIN_COMPLIANCE,
    DEESCALATION_MIN_HOURS,
    DEESCALATION_NN_MISS_WINDOW,
    ESCALATION_ACTIVE,
    ESCALATION_CRITICAL,
    ESCALATION_DRIFT_THRESHOLDS,
    ESCALATION_ELEVATED,
    ESCALATION_NOMINAL,
    ESCALATION_OVERRIDE,
    ESCALATION_SUSTAINED_DAYS,
    apply_intensity,
)
from apps.core.ai_eae.models import EAEEscalationEvent, EAEState

logger = logging.getLogger(__name__)


def _compute_drift_level(drift_severity: float, intensity: float = 1.0) -> int:
    """
    Compute escalation level from drift severity score.
    Higher intensity lowers thresholds (escalates sooner).
    """
    # Apply intensity to thresholds (inverse: higher intensity = lower thresholds)
    t_nominal = apply_intensity(ESCALATION_DRIFT_THRESHOLDS[ESCALATION_NOMINAL], intensity, inverse=True)
    t_elevated = apply_intensity(ESCALATION_DRIFT_THRESHOLDS[ESCALATION_ELEVATED], intensity, inverse=True)
    t_active = apply_intensity(ESCALATION_DRIFT_THRESHOLDS[ESCALATION_ACTIVE], intensity, inverse=True)
    t_critical = apply_intensity(ESCALATION_DRIFT_THRESHOLDS[ESCALATION_CRITICAL], intensity, inverse=True)

    if drift_severity >= t_critical:
        return ESCALATION_OVERRIDE
    elif drift_severity >= t_active:
        return ESCALATION_CRITICAL
    elif drift_severity >= t_elevated:
        return ESCALATION_ACTIVE
    elif drift_severity >= t_nominal:
        return ESCALATION_ELEVATED
    return ESCALATION_NOMINAL


def _check_deescalation_gates(state: EAEState, drift_severity: float) -> bool:
    """
    Check if all de-escalation criteria are met.
    Returns True if de-escalation is allowed.
    """
    now = timezone.now()

    # Gate 1: Drift must decrease by >= DEESCALATION_DRIFT_DROP from peak
    if state.escalation_peak_drift - drift_severity < DEESCALATION_DRIFT_DROP:
        return False

    # Gate 2: Minimum time at current level
    if state.escalation_since:
        hours_at_level = (now - state.escalation_since).total_seconds() / 3600
        if hours_at_level < DEESCALATION_MIN_HOURS:
            return False

    # Gate 3 & 4: No new NN misses + positive compliance
    # These would require querying governance/commitment data.
    # For Phase 8.4, we check basic drift recovery.
    # Full integration with NN miss tracking comes in Phase 8.6.

    return True


def evaluate_escalation(
    state: EAEState,
    drift_severity: float,
    intensity: float = 1.0,
) -> int:
    """
    Evaluate and update escalation level based on current drift.

    Rules:
        - Upward: Immediate when drift crosses threshold
        - Downward: Only if all de-escalation gates pass, one level at a time
        - Sustained level 3 for 5+ days → auto-escalate to 4

    Args:
        state: Current EAEState (will be modified but NOT saved).
        drift_severity: Current drift risk severity (0-100).
        intensity: Intensity multiplier.

    Returns:
        New escalation level.
    """
    current_level = state.escalation_level
    drift_level = _compute_drift_level(drift_severity, intensity)

    new_level = current_level

    # Track peak drift for de-escalation gate
    if drift_severity > state.escalation_peak_drift:
        state.escalation_peak_drift = drift_severity

    # UPWARD ESCALATION — immediate
    if drift_level > current_level:
        new_level = drift_level
        logger.info(
            "EAE escalation UP: L%d → L%d (drift=%.1f, user=%s)",
            current_level, new_level, drift_severity, state.user_id,
        )

    # SUSTAINED LEVEL 3 → AUTO-ESCALATE TO 4
    # (Only when drift still supports level 3+, not when drift has dropped)
    elif (current_level == ESCALATION_CRITICAL
          and drift_level >= ESCALATION_CRITICAL
          and state.escalation_since):
        days_at_level = (timezone.now() - state.escalation_since).days
        sustained_days = int(apply_intensity(ESCALATION_SUSTAINED_DAYS, intensity, inverse=True))
        if days_at_level >= sustained_days:
            new_level = ESCALATION_OVERRIDE
            logger.info(
                "EAE escalation AUTO: L3 → L4 (sustained %d days, user=%s)",
                days_at_level, state.user_id,
            )

    # DOWNWARD DE-ESCALATION — gated
    elif drift_level < current_level and current_level > ESCALATION_NOMINAL:
        if _check_deescalation_gates(state, drift_severity):
            new_level = current_level - 1  # One level at a time
            logger.info(
                "EAE de-escalation: L%d → L%d (drift=%.1f, user=%s)",
                current_level, new_level, drift_severity, state.user_id,
            )

    # Apply level change to state
    if new_level != current_level:
        # Log the event
        direction = 'up' if new_level > current_level else 'down'
        reason = (
            f"Drift severity {drift_severity:.0f} "
            f"{'exceeded' if direction == 'up' else 'recovered below'} "
            f"L{new_level} threshold"
        )
        EAEEscalationEvent.objects.create(
            user_id=state.user_id,
            direction=direction,
            from_level=current_level,
            to_level=new_level,
            trigger_reason=reason,
            drift_risk_at_event=drift_severity,
        )

        state.escalation_level = new_level
        state.escalation_since = timezone.now()

        # Reset peak drift on de-escalation
        if new_level < current_level:
            state.escalation_peak_drift = drift_severity

    # Always update drift
    state.drift_risk_severity = drift_severity

    return new_level
