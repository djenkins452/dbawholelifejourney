"""
UAL v2 — Pattern Analyzer.

Analyzes 14-day scenario history to detect multi-day patterns.
Returns escalation hints that gently influence intervention intensity.

Patterns detected:
- MOOD_CRITICAL ≥3 times in 5 days
- DRIFT_CRITICAL ≥4 times in 7 days
- HEALTH_CRITICAL mornings ≥3 times in 5 days
- Any scenario repeated ≥5 times in 7 days (generic repetition)

Does not overreact. Hints modify intensity slightly.
"""
import logging
from collections import Counter
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# Pattern definitions: (scenario, count_threshold, window_days, escalation_label)
PATTERN_RULES = [
    ("MOOD_CRITICAL", 3, 5, "MOOD_PERSISTENT"),
    ("DRIFT_CRITICAL", 4, 7, "DRIFT_PERSISTENT"),
    ("HEALTH_CRITICAL", 3, 5, "HEALTH_PERSISTENT"),
]

# Generic repetition threshold
GENERIC_REPETITION_COUNT = 5
GENERIC_REPETITION_WINDOW = 7

# Rolling window for full analysis
ANALYSIS_WINDOW_DAYS = 14


def analyze_patterns(user) -> dict:
    """
    Analyze scenario history for multi-day patterns.

    Args:
        user: User instance

    Returns:
        {
            "escalation_hints": list[dict],  # detected patterns
            "scenario_frequency": dict,  # scenario → count in window
            "repetition_flags": list[str],  # scenarios flagged for repetition
            "analysis_window_days": int,
        }
    """
    try:
        from apps.core.ai_arbitration.models import ScenarioHistory

        today = date.today()
        window_start = today - timedelta(days=ANALYSIS_WINDOW_DAYS)

        history = list(
            ScenarioHistory.objects.filter(
                user=user,
                date__gte=window_start,
            ).values_list("date", "dominant_scenario").order_by("-date")
        )
    except Exception as e:
        logger.debug("UAL pattern analysis skipped: %s", e)
        return _empty_result()

    if not history:
        return _empty_result()

    today = date.today()
    escalation_hints = []
    repetition_flags = []

    # Check specific pattern rules
    for scenario, threshold, window, label in PATTERN_RULES:
        window_start = today - timedelta(days=window)
        count = sum(
            1 for d, s in history
            if s == scenario and d >= window_start
        )
        if count >= threshold:
            escalation_hints.append({
                "pattern": label,
                "scenario": scenario,
                "count": count,
                "window_days": window,
                "intensity_modifier": _compute_intensity(count, threshold),
            })
            repetition_flags.append(scenario)

    # Check generic repetition
    recent_start = today - timedelta(days=GENERIC_REPETITION_WINDOW)
    recent = [s for d, s in history if d >= recent_start]
    freq = Counter(recent)
    for scenario, count in freq.items():
        if (
            count >= GENERIC_REPETITION_COUNT
            and scenario not in repetition_flags
            and scenario != "STABLE_EXECUTION"
        ):
            escalation_hints.append({
                "pattern": "GENERIC_REPETITION",
                "scenario": scenario,
                "count": count,
                "window_days": GENERIC_REPETITION_WINDOW,
                "intensity_modifier": _compute_intensity(
                    count, GENERIC_REPETITION_COUNT
                ),
            })
            repetition_flags.append(scenario)

    # Full-window frequency
    all_scenarios = [s for _, s in history]
    scenario_frequency = dict(Counter(all_scenarios))

    return {
        "escalation_hints": escalation_hints,
        "scenario_frequency": scenario_frequency,
        "repetition_flags": repetition_flags,
        "analysis_window_days": ANALYSIS_WINDOW_DAYS,
    }


def _compute_intensity(count: int, threshold: int) -> float:
    """
    Compute a gentle intensity modifier based on how far
    above threshold the count is.

    Returns 0.0-0.3 (never aggressive).
    """
    excess = count - threshold
    # +0.1 per count above threshold, max 0.3
    return min(0.3, excess * 0.1 + 0.1)


def log_scenario_history(user, result) -> None:
    """
    Log today's scenario to history. Updates if already logged.
    Non-blocking.
    """
    try:
        from apps.core.ai_arbitration.models import ScenarioHistory

        ScenarioHistory.objects.update_or_create(
            user=user,
            date=date.today(),
            defaults={
                "dominant_scenario": result.dominant_scenario,
                "intervention_style": result.intervention_style,
                "capacity_state": getattr(result, "capacity_state", "NORMAL"),
                "suppressed_count": len(result.suppressed_items),
                "surfaced_count": len(result.surfaced_items),
            },
        )
    except Exception as e:
        logger.debug("UAL scenario history logging skipped: %s", e)


def _empty_result() -> dict:
    return {
        "escalation_hints": [],
        "scenario_frequency": {},
        "repetition_flags": [],
        "analysis_window_days": ANALYSIS_WINDOW_DAYS,
    }
