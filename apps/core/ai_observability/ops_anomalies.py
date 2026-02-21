"""
Ops Anomalies — Admin-only monitoring rules for the Operations Wall.

These are NOT intelligence features. They detect operational anomalies
in the engine pipeline itself (silence, error bursts, suppression spikes).

Project: Whole Life Journey
Path: apps/core/ai_observability/ops_anomalies.py
"""

import logging
import math
from datetime import timedelta

from django.db.models import Avg, Count, StdDev
from django.utils import timezone

logger = logging.getLogger(__name__)

# Critical engines that should run frequently
CRITICAL_ENGINES = ["UAL", "SAE", "PIE", "DNE"]


def detect_anomalies():
    """
    Run all anomaly detection rules.

    Returns:
        list of anomaly dicts, sorted by severity (crit > warn > info).
    """
    anomalies = []

    try:
        anomalies.extend(_check_engine_silence())
    except Exception as e:
        logger.debug("Anomaly check (silence) failed: %s", e)

    try:
        anomalies.extend(_check_error_burst())
    except Exception as e:
        logger.debug("Anomaly check (error_burst) failed: %s", e)

    try:
        anomalies.extend(_check_suppression_spike())
    except Exception as e:
        logger.debug("Anomaly check (suppression_spike) failed: %s", e)

    try:
        anomalies.extend(_check_scenario_dominance())
    except Exception as e:
        logger.debug("Anomaly check (scenario_dominance) failed: %s", e)

    try:
        anomalies.extend(_check_confidence_volatility())
    except Exception as e:
        logger.debug("Anomaly check (confidence_volatility) failed: %s", e)

    try:
        anomalies.extend(_check_delivery_storm())
    except Exception as e:
        logger.debug("Anomaly check (delivery_storm) failed: %s", e)

    # Sort: crit > warn > info
    severity_order = {"crit": 0, "warn": 1, "info": 2}
    anomalies.sort(key=lambda a: severity_order.get(a["severity"], 3))
    return anomalies


def _check_engine_silence():
    """Any critical engine hasn't run in its expected cadence window."""
    from apps.core.ai_observability.models import EngineRun
    from apps.core.ai_observability.ops_aggregates import ENGINE_CADENCES

    now = timezone.now()
    anomalies = []

    for engine in CRITICAL_ENGINES:
        cadence = ENGINE_CADENCES.get(engine, 3600)
        last_run = (
            EngineRun.objects.filter(engine_name=engine)
            .order_by("-started_at")
            .values("started_at")
            .first()
        )

        if not last_run or not last_run["started_at"]:
            continue  # Never run = no anomaly (might be new install)

        seconds_since = (now - last_run["started_at"]).total_seconds()

        if seconds_since > cadence * 3:
            severity = "crit" if seconds_since > cadence * 5 else "warn"
            minutes = int(seconds_since / 60)
            anomalies.append(
                {
                    "rule": "engine_silence",
                    "severity": severity,
                    "engine": engine,
                    "message": (
                        f"{engine} silent for {minutes}m "
                        f"(expected every {cadence // 60}m)"
                    ),
                    "diagnostic_link": (
                        f"/admin-console/diagnostics/"
                        f"?engine={engine}&since=-60m"
                    ),
                }
            )
    return anomalies


def _check_error_burst():
    """More than 3 errors in the last 15 minutes for any engine."""
    from apps.core.ai_observability.models import EngineRun
    from apps.core.ai_observability.ops_aggregates import ALL_ENGINES

    now = timezone.now()
    fifteen_min_ago = now - timedelta(minutes=15)
    anomalies = []

    error_counts = (
        EngineRun.objects.filter(
            status="error", started_at__gte=fifteen_min_ago
        )
        .values("engine_name")
        .annotate(count=Count("id"))
    )

    for entry in error_counts:
        if entry["count"] > 3:
            anomalies.append(
                {
                    "rule": "error_burst",
                    "severity": "warn",
                    "engine": entry["engine_name"],
                    "message": (
                        f"{entry['engine_name']}: {entry['count']} errors in 15m"
                    ),
                    "diagnostic_link": (
                        f"/admin-console/diagnostics/"
                        f"?engine={entry['engine_name']}&status=error&since=-15m"
                    ),
                }
            )
    return anomalies


def _check_suppression_spike():
    """Suppression rate in 15m significantly higher than 24h baseline."""
    from apps.core.ai_observability.models import DecisionRecord

    now = timezone.now()

    count_15m = DecisionRecord.objects.filter(
        engine_name="ICQG",
        decision_type="suppression",
        created_at__gte=now - timedelta(minutes=15),
    ).count()

    count_24h = DecisionRecord.objects.filter(
        engine_name="ICQG",
        decision_type="suppression",
        created_at__gte=now - timedelta(hours=24),
    ).count()

    # Normalize 24h to 15m equivalent
    baseline_15m = count_24h / 96 if count_24h > 0 else 0

    if count_15m > 3 and baseline_15m > 0 and count_15m > baseline_15m * 3:
        return [
            {
                "rule": "suppression_spike",
                "severity": "warn",
                "engine": "ICQG",
                "message": (
                    f"Suppression spike: {count_15m} in 15m "
                    f"(baseline ~{baseline_15m:.1f}/15m)"
                ),
                "diagnostic_link": "/admin-console/diagnostics/?engine=ICQG&since=-15m",
            }
        ]
    return []


def _check_scenario_dominance():
    """Same UAL scenario appears in >70% of decisions in last 24h."""
    from apps.core.ai_observability.models import DecisionRecord

    now = timezone.now()
    qs = DecisionRecord.objects.filter(
        engine_name="UAL",
        decision_type="arbitration",
        created_at__gte=now - timedelta(hours=24),
    )
    total = qs.count()
    if total < 10:
        return []  # Not enough data

    counts = {}
    for decision in qs.values_list("decision", flat=True):
        scenario = decision.replace("SCENARIO=", "") if decision.startswith("SCENARIO=") else decision
        counts[scenario] = counts.get(scenario, 0) + 1

    anomalies = []
    for scenario, count in counts.items():
        pct = count / total * 100
        if pct > 70 and scenario != "STABLE_EXECUTION":
            anomalies.append(
                {
                    "rule": "scenario_dominance",
                    "severity": "info",
                    "engine": "UAL",
                    "message": (
                        f"UAL: {scenario} dominant ({pct:.0f}% of {total} decisions in 24h)"
                    ),
                    "diagnostic_link": "/admin-console/diagnostics/?engine=UAL&since=-24h",
                }
            )
    return anomalies


def _check_confidence_volatility():
    """Confidence std-dev > 0.3 across UAL decisions in last 24h."""
    from apps.core.ai_observability.models import DecisionRecord

    now = timezone.now()
    stats = DecisionRecord.objects.filter(
        engine_name="UAL",
        decision_type="arbitration",
        confidence__isnull=False,
        created_at__gte=now - timedelta(hours=24),
    ).aggregate(
        stddev=StdDev("confidence"),
        avg=Avg("confidence"),
        count=Count("id"),
    )

    if stats["count"] and stats["count"] >= 5 and stats["stddev"] and stats["stddev"] > 0.3:
        return [
            {
                "rule": "confidence_volatility",
                "severity": "info",
                "engine": "UAL",
                "message": (
                    f"UAL confidence volatile: "
                    f"stddev={stats['stddev']:.2f}, "
                    f"avg={stats['avg']:.2f} "
                    f"({stats['count']} decisions in 24h)"
                ),
                "diagnostic_link": "/admin-console/diagnostics/?engine=UAL&since=-24h",
            }
        ]
    return []


def _check_delivery_storm():
    """DNE delivered_count in 15m > 3x the 24h hourly average."""
    from apps.core.ai_observability.models import EngineRun

    now = timezone.now()

    count_15m = EngineRun.objects.filter(
        engine_name="DNE",
        started_at__gte=now - timedelta(minutes=15),
    ).count()

    count_24h = EngineRun.objects.filter(
        engine_name="DNE",
        started_at__gte=now - timedelta(hours=24),
    ).count()

    # Normalize to 15m equivalent
    baseline_15m = count_24h / 96 if count_24h > 0 else 0

    if count_15m > 5 and baseline_15m > 0 and count_15m > baseline_15m * 3:
        return [
            {
                "rule": "delivery_storm",
                "severity": "warn",
                "engine": "DNE",
                "message": (
                    f"DNE delivery storm: {count_15m} runs in 15m "
                    f"(baseline ~{baseline_15m:.1f}/15m)"
                ),
                "diagnostic_link": "/admin-console/diagnostics/?engine=DNE&since=-15m",
            }
        ]
    return []
