"""
UAL v2.1 — Intervention Fatigue Engine.

Computes per-scenario fatigue scores based on rolling 7-day
intervention response patterns. When interventions are repeatedly
ignored, surfacing bias is gently reduced. When compliance is high,
a slight positive bias is applied.

Bias is EPHEMERAL — applied only during classification, never
persisted to WeightAdjustment model.

Safety bounds: bias never exceeds ±0.05.
"""
import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# Rolling window for fatigue analysis
FATIGUE_WINDOW_DAYS = 7

# Bias bounds (NEVER exceed these)
MAX_POSITIVE_BIAS = 0.03
MAX_NEGATIVE_BIAS = -0.05

# Fatigue thresholds
HIGH_FATIGUE_THRESHOLD = 0.6
LOW_FATIGUE_THRESHOLD = 0.3

# Compliance ratio threshold for positive bias
HIGH_COMPLIANCE_THRESHOLD = 0.6


def compute_fatigue_scores(user) -> dict:
    """
    Compute per-scenario fatigue scores from rolling 7-day response data.

    Args:
        user: User instance

    Returns:
        {
            "scenario_fatigue": {scenario: float},  # 0-1 fatigue per scenario
            "scenario_bias": {scenario: float},      # ephemeral bias per scenario
        }
    """
    try:
        from apps.core.ai_arbitration.models import InterventionResponseLog

        window_start = date.today() - timedelta(days=FATIGUE_WINDOW_DAYS)
        logs = list(
            InterventionResponseLog.objects.filter(
                user=user,
                date__gte=window_start,
            ).values("scenario", "surfaced_count", "complied_count",
                     "ignored_count", "overrode_count", "date")
        )
    except Exception as e:
        logger.debug("UAL fatigue computation skipped: %s", e)
        return _empty_result()

    if not logs:
        return _empty_result()

    # Aggregate per scenario
    scenario_data = {}
    for log in logs:
        sc = log["scenario"]
        if sc not in scenario_data:
            scenario_data[sc] = {
                "surfaced": 0, "complied": 0,
                "ignored": 0, "overrode": 0,
                "dates_ignored": set(),
            }
        scenario_data[sc]["surfaced"] += log["surfaced_count"]
        scenario_data[sc]["complied"] += log["complied_count"]
        scenario_data[sc]["ignored"] += log["ignored_count"]
        scenario_data[sc]["overrode"] += log["overrode_count"]
        if log["ignored_count"] > 0:
            scenario_data[sc]["dates_ignored"].add(log["date"])

    scenario_fatigue = {}
    scenario_bias = {}

    for scenario, data in scenario_data.items():
        fatigue = _compute_fatigue_score(data)
        scenario_fatigue[scenario] = fatigue
        scenario_bias[scenario] = _compute_bias(fatigue, data)

    return {
        "scenario_fatigue": scenario_fatigue,
        "scenario_bias": scenario_bias,
    }


def _compute_fatigue_score(data: dict) -> float:
    """
    Compute fatigue score for a single scenario.

    Formula: ignored_ratio × 0.7 + consecutive_ignore_days × 0.1
    Clamped 0-1.
    """
    surfaced = data["surfaced"]
    if surfaced == 0:
        return 0.0

    ignored = data["ignored"]
    ignored_ratio = ignored / surfaced

    # Approximate consecutive ignore days from dates_ignored set
    consecutive = _count_consecutive_recent_days(data["dates_ignored"])

    fatigue = ignored_ratio * 0.7 + consecutive * 0.1
    return max(0.0, min(1.0, round(fatigue, 3)))


def _count_consecutive_recent_days(dates_ignored: set) -> int:
    """
    Count consecutive recent days with ignored interventions
    (working backwards from today).
    """
    if not dates_ignored:
        return 0

    today = date.today()
    consecutive = 0
    for i in range(FATIGUE_WINDOW_DAYS):
        check_date = today - timedelta(days=i)
        if check_date in dates_ignored:
            consecutive += 1
        else:
            break
    return consecutive


def _compute_bias(fatigue: float, data: dict) -> float:
    """
    Compute ephemeral surfacing bias based on fatigue score.

    High fatigue → negative bias (reduce surfacing).
    Low fatigue + high compliance → slight positive bias.
    Bias NEVER exceeds ±0.05.
    """
    if fatigue > HIGH_FATIGUE_THRESHOLD:
        # Penalise — scale between -0.01 and MAX_NEGATIVE_BIAS
        intensity = min(1.0, (fatigue - HIGH_FATIGUE_THRESHOLD) / 0.4)
        bias = MAX_NEGATIVE_BIAS * intensity
        return max(MAX_NEGATIVE_BIAS, round(bias, 3))

    if fatigue < LOW_FATIGUE_THRESHOLD:
        surfaced = data["surfaced"]
        complied = data["complied"]
        if surfaced > 0:
            compliance_ratio = complied / surfaced
            if compliance_ratio >= HIGH_COMPLIANCE_THRESHOLD:
                return MAX_POSITIVE_BIAS

    return 0.0


def log_intervention_response(user, scenario: str, response_type: str) -> None:
    """
    Log an intervention response for fatigue tracking.

    Args:
        user: User instance
        scenario: scenario name (e.g., "HEALTH_CRITICAL")
        response_type: "surfaced" | "complied" | "ignored" | "overrode"
    """
    try:
        from apps.core.ai_arbitration.models import InterventionResponseLog

        today = date.today()
        log, _ = InterventionResponseLog.objects.get_or_create(
            user=user,
            date=today,
            scenario=scenario,
            defaults={
                "surfaced_count": 0,
                "complied_count": 0,
                "ignored_count": 0,
                "overrode_count": 0,
            },
        )

        field_map = {
            "surfaced": "surfaced_count",
            "complied": "complied_count",
            "ignored": "ignored_count",
            "overrode": "overrode_count",
        }
        field = field_map.get(response_type)
        if field:
            setattr(log, field, getattr(log, field) + 1)
            log.save(update_fields=[field])
    except Exception as e:
        logger.debug("UAL intervention response logging skipped: %s", e)


def _empty_result() -> dict:
    return {
        "scenario_fatigue": {},
        "scenario_bias": {},
    }
