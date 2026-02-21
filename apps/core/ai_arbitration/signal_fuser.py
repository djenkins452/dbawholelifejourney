"""
UAL — Signal Fuser.

Combines cross-domain signals into composite indicators before
intervention selection. This is NOT rule-per-domain — it detects
patterns that emerge only when multiple domains are viewed together.
"""
import logging

from apps.core.ai_observability.instrumentation import log_engine_span as _instrument_span

logger = logging.getLogger(__name__)

# Composite signal definitions
# Each composite has required signals (all must exceed threshold)
# and a resulting label + description.

COMPOSITE_DEFINITIONS = [
    {
        "name": "LOW_CAPACITY_DAY",
        "description": "Poor sleep, low mood, and high schedule density combine to limit effective capacity.",
        "required": {
            "sleep_deficit": 0.4,
            "schedule_overload": 0.3,
        },
        "supporting": {
            "mood_decline": 0.2,
            "emotional_load": 0.2,
        },
        "min_required": 2,  # All required must meet threshold
        "min_supporting": 0,  # Supporting boost confidence
    },
    {
        "name": "PHYSICAL_RISK",
        "description": "Injury signals combined with scheduled physical activity.",
        "required": {
            "injury_risk": 0.5,
        },
        "supporting": {
            "sleep_deficit": 0.3,
            "schedule_overload": 0.2,
        },
        "min_required": 1,
        "min_supporting": 0,
    },
    {
        "name": "RELATIONAL_OPPORTUNITY",
        "description": "Approaching relationship event with available schedule capacity.",
        "required": {
            "relationship_event": 0.5,
        },
        "supporting": {},
        "min_required": 1,
        "min_supporting": 0,
        "anti_signals": {
            "schedule_overload": 0.6,
            "medication_risk": 0.5,
        },
    },
    {
        "name": "EMOTIONAL_OVERLOAD",
        "description": "Mood decline plus emotional journal content plus schedule pressure.",
        "required": {
            "mood_decline": 0.4,
            "emotional_load": 0.4,
        },
        "supporting": {
            "sleep_deficit": 0.3,
            "schedule_overload": 0.3,
        },
        "min_required": 2,
        "min_supporting": 0,
    },
    {
        "name": "RECOVERY_NEEDED",
        "description": "Sleep deficit combined with high activity load — body needs recovery.",
        "required": {
            "sleep_deficit": 0.5,
        },
        "supporting": {
            "schedule_overload": 0.4,
            "mood_decline": 0.2,
        },
        "min_required": 1,
        "min_supporting": 1,
    },
    {
        "name": "ALIGNMENT_CRISIS",
        "description": "Drift severity plus missed non-negotiables signals values misalignment.",
        "required": {
            "drift_severity": 0.5,
            "non_negotiable_miss": 0.4,
        },
        "supporting": {
            "mood_decline": 0.2,
        },
        "min_required": 2,
        "min_supporting": 0,
    },
    {
        "name": "DEADLINE_CONVERGENCE",
        "description": "Multiple deadlines approaching simultaneously.",
        "required": {
            "deadline_pressure": 0.6,
            "open_loop_count": 0.4,
        },
        "supporting": {
            "schedule_overload": 0.3,
        },
        "min_required": 2,
        "min_supporting": 0,
    },
]


@_instrument_span("UAL", "fuse_signals")
def fuse_signals(strengths: dict) -> list:
    """
    Detect cross-domain composite patterns from signal strengths.

    Args:
        strengths: dict of signal_name → float (0-1)

    Returns:
        list of detected composites, sorted by strength:
        [
            {
                "name": "LOW_CAPACITY_DAY",
                "description": "...",
                "strength": 0.72,
                "contributing_signals": {"sleep_deficit": 0.6, ...},
            },
            ...
        ]
    """
    detected = []

    for defn in COMPOSITE_DEFINITIONS:
        # Check all required signals meet threshold
        required_met = 0
        contributing = {}

        for signal, threshold in defn["required"].items():
            val = strengths.get(signal, 0.0)
            if val >= threshold:
                required_met += 1
                contributing[signal] = val

        if required_met < defn["min_required"]:
            continue

        # Check supporting signals
        supporting_met = 0
        for signal, threshold in defn.get("supporting", {}).items():
            val = strengths.get(signal, 0.0)
            if val >= threshold:
                supporting_met += 1
                contributing[signal] = val

        if supporting_met < defn.get("min_supporting", 0):
            continue

        # Check anti-signals (conditions that suppress this composite)
        anti_triggered = False
        for signal, threshold in defn.get("anti_signals", {}).items():
            if strengths.get(signal, 0.0) >= threshold:
                anti_triggered = True
                break

        if anti_triggered:
            continue

        # Compute composite strength (average of contributing signals)
        strength = sum(contributing.values()) / max(len(contributing), 1)

        detected.append({
            "name": defn["name"],
            "description": defn["description"],
            "strength": round(strength, 3),
            "contributing_signals": contributing,
        })

    # Sort by strength descending
    detected.sort(key=lambda x: x["strength"], reverse=True)
    return detected
