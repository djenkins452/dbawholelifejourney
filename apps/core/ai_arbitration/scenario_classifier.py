"""
UAL — Scenario Classifier.

Classifies the dominant scenario from normalised signal strengths
using weighted scoring. Returns exactly ONE dominant scenario with
optional secondary scenarios.

v2: Confidence dampening levels, adaptive weight support.
"""
import logging

logger = logging.getLogger(__name__)

# Scenario types
TIME_CRITICAL = "TIME_CRITICAL"
HEALTH_CRITICAL = "HEALTH_CRITICAL"
DRIFT_CRITICAL = "DRIFT_CRITICAL"
MOOD_CRITICAL = "MOOD_CRITICAL"
RELATIONSHIP_CRITICAL = "RELATIONSHIP_CRITICAL"
STABLE_EXECUTION = "STABLE_EXECUTION"

ALL_SCENARIOS = [
    TIME_CRITICAL,
    HEALTH_CRITICAL,
    DRIFT_CRITICAL,
    MOOD_CRITICAL,
    RELATIONSHIP_CRITICAL,
]

# Confidence levels (v2)
CONFIDENCE_LOW = "LOW"
CONFIDENCE_MODERATE = "MODERATE"
CONFIDENCE_HIGH = "HIGH"

# Scenario weight matrices: signal_name → weight
# Each scenario emphasises different signals.
SCENARIO_WEIGHTS = {
    TIME_CRITICAL: {
        "calendar_urgency": 0.35,
        "deadline_pressure": 0.30,
        "schedule_overload": 0.20,
        "open_loop_count": 0.15,
    },
    HEALTH_CRITICAL: {
        "medication_risk": 0.35,
        "sleep_deficit": 0.25,
        "injury_risk": 0.20,
        "mood_decline": 0.10,
        "schedule_overload": 0.10,
    },
    DRIFT_CRITICAL: {
        "drift_severity": 0.40,
        "non_negotiable_miss": 0.35,
        "open_loop_count": 0.15,
        "schedule_overload": 0.10,
    },
    MOOD_CRITICAL: {
        "mood_decline": 0.40,
        "emotional_load": 0.30,
        "sleep_deficit": 0.20,
        "schedule_overload": 0.10,
    },
    RELATIONSHIP_CRITICAL: {
        "relationship_event": 0.40,
        "relationship_drift": 0.35,
        "emotional_load": 0.15,
        "schedule_overload": 0.10,
    },
}

# Minimum score for a scenario to be considered "active"
ACTIVE_THRESHOLD = 0.25

# Minimum score for dominant scenario (below this → STABLE_EXECUTION)
DOMINANT_THRESHOLD = 0.30

# Confidence gap thresholds (v2)
LOW_CONFIDENCE_GAP = 0.05
MODERATE_CONFIDENCE_GAP = 0.15

# Max adaptive weight adjustment from baseline
MAX_WEIGHT_DELTA = 0.10


def classify_scenario(strengths: dict, weight_adjustments: dict = None) -> dict:
    """
    Classify the dominant scenario from signal strengths.

    Args:
        strengths: dict of signal_name → float (0-1)
        weight_adjustments: optional dict of (scenario, signal) → delta
            from WeightAdjustment model. Applied on top of baseline.

    Returns:
        {
            "dominant_scenario": str,
            "secondary_scenarios": list[str],
            "scenario_scores": dict[str, float],
            "confidence": float,  # 0-1
            "confidence_level": str,  # LOW / MODERATE / HIGH
            "confidence_gap": float,  # gap between top and second
        }
    """
    scores = {}
    for scenario, base_weights in SCENARIO_WEIGHTS.items():
        # Apply adaptive weight adjustments if provided
        weights = _apply_adjustments(scenario, base_weights, weight_adjustments)
        score = sum(
            strengths.get(signal, 0.0) * weight
            for signal, weight in weights.items()
        )
        scores[scenario] = round(score, 4)

    # Sort by score descending
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    top_scenario = ranked[0][0]
    top_score = ranked[0][1]
    second_score = ranked[1][1] if len(ranked) > 1 else 0

    # Confidence gap (v2)
    confidence_gap = round(top_score - second_score, 4)
    confidence_level = _classify_confidence(confidence_gap)

    # If nothing reaches threshold, it's a stable execution day
    if top_score < DOMINANT_THRESHOLD:
        return {
            "dominant_scenario": STABLE_EXECUTION,
            "secondary_scenarios": [
                s for s, sc in ranked if sc >= ACTIVE_THRESHOLD
            ],
            "scenario_scores": scores,
            "confidence": 1.0 - top_score,  # High confidence in stability
            "confidence_level": CONFIDENCE_HIGH,
            "confidence_gap": confidence_gap,
        }

    # Determine secondary scenarios
    secondaries = [
        s for s, sc in ranked[1:]
        if sc >= ACTIVE_THRESHOLD and s != top_scenario
    ]

    # Confidence = gap between top and second (scaled to 0-1)
    gap = top_score - second_score
    confidence = min(1.0, 0.5 + (gap / 0.10) * 0.5)

    return {
        "dominant_scenario": top_scenario,
        "secondary_scenarios": secondaries,
        "scenario_scores": scores,
        "confidence": round(confidence, 3),
        "confidence_level": confidence_level,
        "confidence_gap": confidence_gap,
    }


def _classify_confidence(gap: float) -> str:
    """
    Classify confidence level based on gap between top two scenarios.

    <0.05 → LOW: ambiguous, soften response
    0.05-0.15 → MODERATE: normal behavior
    >0.15 → HIGH: clear dominance, full suppression OK
    """
    if gap < LOW_CONFIDENCE_GAP:
        return CONFIDENCE_LOW
    elif gap <= MODERATE_CONFIDENCE_GAP:
        return CONFIDENCE_MODERATE
    return CONFIDENCE_HIGH


def _apply_adjustments(
    scenario: str,
    base_weights: dict,
    adjustments: dict = None,
) -> dict:
    """
    Apply adaptive weight adjustments to baseline weights.

    Adjustments are clamped to ±MAX_WEIGHT_DELTA from baseline.
    If no adjustments provided, returns base weights unchanged.
    """
    if not adjustments:
        return base_weights

    adjusted = {}
    for signal, base in base_weights.items():
        key = (scenario, signal)
        delta = adjustments.get(key, 0.0)
        # Clamp delta
        delta = max(-MAX_WEIGHT_DELTA, min(MAX_WEIGHT_DELTA, delta))
        # Ensure weight stays positive
        adjusted[signal] = max(0.0, base + delta)
    return adjusted
