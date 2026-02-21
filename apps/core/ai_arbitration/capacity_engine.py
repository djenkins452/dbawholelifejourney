"""
UAL v2 — Capacity Composite Engine.

Computes a weighted capacity score from multiple signal dimensions.
Classifies into HIGH_CAPACITY / NORMAL / LOW / CRITICAL.

Capacity state modifies:
- Max surfaced items (3 → 2 if LOW, 3 → 1 if CRITICAL)
- Directive intensity
- Strategic surfacing suppression
- Accountability severity
"""
import logging
from datetime import date

logger = logging.getLogger(__name__)

# Capacity states
HIGH_CAPACITY = "HIGH_CAPACITY"
NORMAL = "NORMAL"
LOW = "LOW"
CRITICAL = "CRITICAL"

# Capacity component weights (sum to 1.0)
# Higher weight = more impact on capacity reduction
CAPACITY_WEIGHTS = {
    "sleep_deficit": 0.30,
    "mood_decline": 0.20,
    "emotional_load": 0.20,
    "schedule_overload": 0.20,
    "open_loop_count": 0.10,
}

# State thresholds (capacity is INVERTED — higher signals = lower capacity)
# Score represents available capacity (1 = full, 0 = empty)
HIGH_CAPACITY_THRESHOLD = 0.75
NORMAL_THRESHOLD = 0.45
LOW_THRESHOLD = 0.25
# Below LOW_THRESHOLD = CRITICAL

# Max surfaced items by capacity state
CAPACITY_SURFACE_LIMITS = {
    HIGH_CAPACITY: 3,
    NORMAL: 3,
    LOW: 2,
    CRITICAL: 1,
}


def compute_capacity(strengths: dict) -> dict:
    """
    Compute capacity score and state from signal strengths.

    Capacity is the INVERSE of signal load — high signals mean
    low capacity. The score is normalised 0-1 where 1 = full capacity.

    Args:
        strengths: dict of signal_name → float (0-1)

    Returns:
        {
            "capacity_score": float,  # 0-1 (1 = full capacity)
            "capacity_state": str,  # HIGH_CAPACITY / NORMAL / LOW / CRITICAL
            "max_surfaced": int,  # adjusted limit
            "components": dict,  # individual signal values used
        }
    """
    # Compute weighted load from signals
    load = 0.0
    components = {}
    for signal, weight in CAPACITY_WEIGHTS.items():
        value = strengths.get(signal, 0.0)
        components[signal] = round(value, 3)
        load += value * weight

    # Invert: high load = low capacity
    capacity_score = round(max(0.0, min(1.0, 1.0 - load)), 3)

    # Classify state
    capacity_state = _classify_state(capacity_score)

    return {
        "capacity_score": capacity_score,
        "capacity_state": capacity_state,
        "max_surfaced": CAPACITY_SURFACE_LIMITS[capacity_state],
        "components": components,
    }


def _classify_state(score: float) -> str:
    """Classify capacity score into state."""
    if score >= HIGH_CAPACITY_THRESHOLD:
        return HIGH_CAPACITY
    elif score >= NORMAL_THRESHOLD:
        return NORMAL
    elif score >= LOW_THRESHOLD:
        return LOW
    return CRITICAL


def log_daily_capacity(user, capacity_result: dict) -> None:
    """
    Log today's capacity state. Updates if already logged today.
    Non-blocking — failures are silently logged.
    """
    try:
        from apps.core.ai_arbitration.models import DailyCapacityLog

        DailyCapacityLog.objects.update_or_create(
            user=user,
            date=date.today(),
            defaults={
                "capacity_score": capacity_result["capacity_score"],
                "capacity_state": capacity_result["capacity_state"],
                "sleep_deficit": capacity_result["components"].get("sleep_deficit", 0),
                "mood_decline": capacity_result["components"].get("mood_decline", 0),
                "emotional_load": capacity_result["components"].get("emotional_load", 0),
                "schedule_overload": capacity_result["components"].get("schedule_overload", 0),
                "open_loop_count": capacity_result["components"].get("open_loop_count", 0),
            },
        )
    except Exception as e:
        logger.debug("UAL capacity logging skipped: %s", e)
