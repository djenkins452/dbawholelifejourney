"""
UAL — Scenario Classifier.

Classifies the dominant scenario from normalised signal strengths
using weighted scoring. Returns exactly ONE dominant scenario with
optional secondary scenarios.
"""
import logging

from apps.core.ai_observability.instrumentation import log_engine_span as _instrument_span

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

# Minimum gap between dominant and secondary to be confident
CONFIDENCE_GAP = 0.10


@_instrument_span("UAL", "classify_scenario")
def classify_scenario(strengths: dict) -> dict:
    """
    Classify the dominant scenario from signal strengths.

    Args:
        strengths: dict of signal_name → float (0-1)

    Returns:
        {
            "dominant_scenario": str,
            "secondary_scenarios": list[str],
            "scenario_scores": dict[str, float],
            "confidence": float,  # 0-1
        }
    """
    scores = {}
    for scenario, weights in SCENARIO_WEIGHTS.items():
        score = sum(
            strengths.get(signal, 0.0) * weight
            for signal, weight in weights.items()
        )
        scores[scenario] = round(score, 4)

    # Sort by score descending
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    top_scenario = ranked[0][0]
    top_score = ranked[0][1]

    # If nothing reaches threshold, it's a stable execution day
    if top_score < DOMINANT_THRESHOLD:
        return {
            "dominant_scenario": STABLE_EXECUTION,
            "secondary_scenarios": [
                s for s, sc in ranked if sc >= ACTIVE_THRESHOLD
            ],
            "scenario_scores": scores,
            "confidence": 1.0 - top_score,  # High confidence in stability
        }

    # Determine secondary scenarios
    secondaries = [
        s for s, sc in ranked[1:]
        if sc >= ACTIVE_THRESHOLD and s != top_scenario
    ]

    # Confidence = gap between top and second
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    gap = top_score - second_score
    confidence = min(1.0, 0.5 + (gap / CONFIDENCE_GAP) * 0.5)

    return {
        "dominant_scenario": top_scenario,
        "secondary_scenarios": secondaries,
        "scenario_scores": scores,
        "confidence": round(confidence, 3),
    }
