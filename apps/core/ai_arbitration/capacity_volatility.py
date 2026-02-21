"""
UAL v2.1 — Capacity Volatility Index.

Analyses variance in recent DailyCapacityLog scores to detect
capacity instability. When volatility is high, surfacing
aggressiveness is reduced and confidence framing is downgraded.

Does NOT alter baseline capacity score.
"""
import logging
import math
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# Number of recent days to analyse
VOLATILITY_WINDOW_DAYS = 5

# Std dev threshold for volatility flag
VOLATILITY_THRESHOLD = 0.25

# Confidence downgrade mapping
CONFIDENCE_DOWNGRADE = {
    "HIGH": "MODERATE",
    "MODERATE": "LOW",
    "LOW": "LOW",  # No further downgrade
}


def compute_capacity_volatility(user) -> dict:
    """
    Compute capacity volatility from recent DailyCapacityLog entries.

    Args:
        user: User instance

    Returns:
        {
            "volatility_flag": bool,
            "std_dev": float,
            "sample_count": int,
        }
    """
    try:
        from apps.core.ai_arbitration.models import DailyCapacityLog

        window_start = date.today() - timedelta(days=VOLATILITY_WINDOW_DAYS)
        scores = list(
            DailyCapacityLog.objects.filter(
                user=user,
                date__gte=window_start,
            ).values_list("capacity_score", flat=True)
        )
    except Exception as e:
        logger.debug("UAL volatility computation skipped: %s", e)
        return _empty_result()

    if len(scores) < 2:
        # Not enough data to compute volatility
        return _empty_result()

    std_dev = _compute_std_dev(scores)
    volatility_flag = std_dev > VOLATILITY_THRESHOLD

    return {
        "volatility_flag": volatility_flag,
        "std_dev": round(std_dev, 4),
        "sample_count": len(scores),
    }


def apply_volatility_adjustments(
    volatility: dict,
    confidence_level: str,
) -> dict:
    """
    Apply volatility-based adjustments to arbitration context.

    If volatility_flag is True:
    - Downgrade confidence framing by one level
    - Return flag for surfacing aggressiveness reduction

    Args:
        volatility: output of compute_capacity_volatility()
        confidence_level: current confidence level string

    Returns:
        {
            "adjusted_confidence_level": str,
            "reduce_surfacing": bool,
            "volatility_applied": bool,
        }
    """
    if not volatility.get("volatility_flag", False):
        return {
            "adjusted_confidence_level": confidence_level,
            "reduce_surfacing": False,
            "volatility_applied": False,
        }

    downgraded = CONFIDENCE_DOWNGRADE.get(confidence_level, confidence_level)

    return {
        "adjusted_confidence_level": downgraded,
        "reduce_surfacing": True,
        "volatility_applied": True,
    }


def _compute_std_dev(values: list) -> float:
    """Compute population standard deviation of a list of floats."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / n
    return math.sqrt(variance)


def _empty_result() -> dict:
    return {
        "volatility_flag": False,
        "std_dev": 0.0,
        "sample_count": 0,
    }
