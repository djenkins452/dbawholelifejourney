"""
UAL v2 — Adaptive Weight Tuner.

Adjusts scenario classification weights based on user compliance patterns.
Slow adaptation only:
- Every 50 decisions, adjust by ±0.02 max
- Clamp within ±0.10 of baseline
- Never self-amplify beyond bounds

Compliance signals:
- complied: user followed the surfaced suggestion
- overrode: user explicitly chose different action
- ignored: user did not respond to surfaced suggestion
"""
import logging

logger = logging.getLogger(__name__)

# How often to run weight adjustment (every N decisions)
ADJUSTMENT_INTERVAL = 50

# Max adjustment per cycle
MAX_ADJUSTMENT_PER_CYCLE = 0.02

# Absolute max delta from baseline
MAX_DELTA_FROM_BASELINE = 0.10

# Response value mappings for weight direction
RESPONSE_WEIGHTS = {
    "complied": 1.0,    # Reinforce current weights
    "overrode": -1.0,   # Reduce weight (user disagrees)
    "ignored": -0.5,    # Slightly reduce (user unengaged)
}


def get_weight_adjustments(user) -> dict:
    """
    Load current weight adjustments for a user.

    Returns:
        dict of (scenario, signal) → delta
    """
    try:
        from apps.core.ai_arbitration.models import WeightAdjustment

        adjustments = WeightAdjustment.objects.filter(user=user)
        return {
            (adj.scenario, adj.signal): adj.adjustment_delta
            for adj in adjustments
        }
    except Exception as e:
        logger.debug("UAL weight loading skipped: %s", e)
        return {}


def maybe_tune_weights(user) -> bool:
    """
    Check if weight tuning is due and run if so.

    Tuning runs every ADJUSTMENT_INTERVAL decisions.
    Returns True if tuning was performed.
    """
    try:
        from apps.core.ai_arbitration.models import (
            ArbitrationDecisionLog,
            WeightAdjustment,
        )
        from apps.core.ai_arbitration.scenario_classifier import SCENARIO_WEIGHTS

        # Count decisions since last tune
        total = ArbitrationDecisionLog.objects.filter(user=user).count()
        if total == 0 or total % ADJUSTMENT_INTERVAL != 0:
            return False

        # Get recent decisions with feedback
        recent = list(
            ArbitrationDecisionLog.objects.filter(
                user=user,
                user_response__isnull=False,
            ).order_by("-timestamp")[:ADJUSTMENT_INTERVAL].values(
                "dominant_scenario", "user_response"
            )
        )

        if len(recent) < 10:  # Need minimum sample
            return False

        # Calculate compliance direction per scenario
        scenario_signals = {}
        for decision in recent:
            scenario = decision["dominant_scenario"]
            response = decision["user_response"]
            weight = RESPONSE_WEIGHTS.get(response, 0.0)
            if scenario not in scenario_signals:
                scenario_signals[scenario] = []
            scenario_signals[scenario].append(weight)

        # Apply adjustments
        for scenario, base_weights in SCENARIO_WEIGHTS.items():
            if scenario not in scenario_signals:
                continue

            signals = scenario_signals[scenario]
            avg_signal = sum(signals) / len(signals)

            # Compute delta direction
            delta = avg_signal * MAX_ADJUSTMENT_PER_CYCLE

            for signal, baseline in base_weights.items():
                adj, created = WeightAdjustment.objects.get_or_create(
                    user=user,
                    scenario=scenario,
                    signal=signal,
                    defaults={"baseline_weight": baseline, "adjustment_delta": 0.0},
                )

                # Apply delta with clamping
                new_delta = adj.adjustment_delta + delta
                new_delta = max(
                    -MAX_DELTA_FROM_BASELINE,
                    min(MAX_DELTA_FROM_BASELINE, new_delta),
                )
                adj.adjustment_delta = round(new_delta, 4)
                adj.save(update_fields=["adjustment_delta", "last_updated"])

        return True

    except Exception as e:
        logger.debug("UAL weight tuning skipped: %s", e)
        return False
