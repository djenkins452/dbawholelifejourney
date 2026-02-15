"""
GLOE — Learning Calculator.

Computes the responsiveness_score from aggregate profile metrics.

Score range: 0.0 to 1.0

Factors (weighted):
- acted_upon rate: 40% weight (highest — user takes action)
- acknowledged rate: 25% weight (user reads and acknowledges)
- dismiss rate: 20% negative weight (user finds guidance unhelpful)
- response speed: 15% weight (faster response = more engaged)
"""

import logging

logger = logging.getLogger(__name__)

# Weights for score components
WEIGHT_ACTED = 0.40
WEIGHT_ACKNOWLEDGED = 0.25
WEIGHT_DISMISSED = 0.20  # Negative impact
WEIGHT_RESPONSE_SPEED = 0.15

# Response time thresholds (in seconds)
FAST_RESPONSE = 3600  # 1 hour
SLOW_RESPONSE = 86400 * 3  # 3 days


def calculate_responsiveness_score(profile):
    """
    Calculate the responsiveness score for a user's learning profile.

    Args:
        profile: GuidanceLearningProfile instance with updated counts.

    Returns:
        float — score between 0.0 and 1.0
    """
    total = profile.total_guidance_seen
    if total == 0:
        return 0.5  # Neutral default for new users

    # Rate calculations
    acted_rate = profile.total_guidance_acted / total
    acknowledged_rate = profile.total_guidance_acknowledged / total
    dismissed_rate = profile.total_guidance_dismissed / total

    # Response speed component (0.0 to 1.0)
    speed_score = _response_speed_score(profile.avg_response_time_seconds)

    # Weighted composite
    score = (
        (acted_rate * WEIGHT_ACTED)
        + (acknowledged_rate * WEIGHT_ACKNOWLEDGED)
        - (dismissed_rate * WEIGHT_DISMISSED)
        + (speed_score * WEIGHT_RESPONSE_SPEED)
    )

    # Clamp to [0.0, 1.0]
    score = max(0.0, min(1.0, score))

    return round(score, 4)


def _response_speed_score(avg_response_seconds):
    """
    Convert average response time to a 0-1 score.

    Fast (< 1 hour) → 1.0
    Slow (> 3 days) → 0.0
    Linear interpolation in between.
    """
    if avg_response_seconds <= 0:
        return 0.5  # No data

    if avg_response_seconds <= FAST_RESPONSE:
        return 1.0

    if avg_response_seconds >= SLOW_RESPONSE:
        return 0.0

    # Linear interpolation
    return 1.0 - (avg_response_seconds - FAST_RESPONSE) / (SLOW_RESPONSE - FAST_RESPONSE)
