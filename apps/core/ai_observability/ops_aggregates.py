"""
Ops Aggregates — Rolling metrics computed from EngineRun/DecisionRecord.

All functions return plain dicts suitable for JSON serialization.
All queries use indexed fields for speed.

Project: Whole Life Journey
Path: apps/core/ai_observability/ops_aggregates.py
"""

import logging
from datetime import timedelta

from django.db.models import Avg, Count, Q
from django.utils import timezone

logger = logging.getLogger(__name__)

# Expected cadences for anomaly detection (seconds).
# Values must match the actual ISE scheduler_registry intervals so that
# COAS heartbeat monitoring correctly flags late/missed engines.
#
# UAL/SAE/PIE also fire per-request during chat, but synthetic batch
# execution guarantees a minimum cadence even during idle periods.
ENGINE_CADENCES = {
    "UAL": 1800,  # Per-request + synthetic every 5m; 30m allows inactivity
    "SAE": 1800,
    "PIE": 1800,
    "PRIE": 3600,  # Hourly via scheduler
    "PGE": 21600,  # Every 6 hours (was 3600 — mismatched scheduler)
    "ICQG": 604800,  # Weekly (was 3600 — mismatched scheduler)
    "DBE": 86400,  # Daily
    "WIRE": 604800,  # Weekly
    "DNE": 600,  # Every 10 minutes (was 3600 — mismatched scheduler)
    "GLOE": 21600,  # Every 6 hours (was 86400 — mismatched scheduler)
}

# All instrumented engines — sourced from central registry when available,
# with fallback to ENGINE_CADENCES keys for backward compatibility.
def _get_all_engines():
    """Build ALL_ENGINES list from central registry, falling back to cadence keys."""
    try:
        from apps.core.engine_registry import get_scheduled_engines
        scheduled = get_scheduled_engines()
        if scheduled:
            # Use registry codes, ensuring cadence-monitored engines are included
            registry_codes = {e.code for e in scheduled}
            return sorted(registry_codes | set(ENGINE_CADENCES.keys()))
    except Exception:
        pass
    return sorted(ENGINE_CADENCES.keys())


ALL_ENGINES = _get_all_engines()


def get_engine_pulse(engine_name):
    """
    Get pulse for a single engine.

    Returns:
        dict with: name, status (green/yellow/red), last_run_at,
        seconds_since, avg_duration_15m, error_rate_15m, runs_15m
    """
    from apps.core.ai_observability.models import EngineRun

    now = timezone.now()
    fifteen_min_ago = now - timedelta(minutes=15)

    last_run = (
        EngineRun.objects.filter(engine_name=engine_name)
        .order_by("-started_at")
        .values("started_at", "status", "duration_ms")
        .first()
    )

    runs_15m = EngineRun.objects.filter(
        engine_name=engine_name, started_at__gte=fifteen_min_ago
    )
    total_15m = runs_15m.count()
    errors_15m = runs_15m.filter(status="error").count()
    avg_duration = runs_15m.aggregate(avg=Avg("duration_ms"))["avg"] or 0

    seconds_since = None
    if last_run and last_run["started_at"]:
        seconds_since = int((now - last_run["started_at"]).total_seconds())

    error_rate = (errors_15m / total_15m * 100) if total_15m > 0 else 0
    cadence = ENGINE_CADENCES.get(engine_name, 3600)

    # Status logic
    if seconds_since is None:
        status = "gray"  # Never run
    elif error_rate > 20:
        status = "red"
    elif error_rate > 5 or (seconds_since > cadence * 2):
        status = "yellow"
    else:
        status = "green"

    return {
        "name": engine_name,
        "status": status,
        "last_run_at": (
            last_run["started_at"].isoformat() if last_run and last_run["started_at"] else None
        ),
        "seconds_since": seconds_since,
        "avg_duration_15m": round(avg_duration),
        "error_rate_15m": round(error_rate, 1),
        "runs_15m": total_15m,
        "errors_15m": errors_15m,
    }


def get_all_engine_pulses():
    """Get pulse for all instrumented engines."""
    return [get_engine_pulse(name) for name in ALL_ENGINES]


def get_suppression_stats():
    """
    Suppression rates from ICQG DecisionRecords.

    Returns:
        dict with 15m and 24h suppression counts and rates.
    """
    from apps.core.ai_observability.models import DecisionRecord

    now = timezone.now()

    def _stats(since):
        qs = DecisionRecord.objects.filter(
            engine_name="ICQG",
            decision_type="suppression",
            created_at__gte=since,
        )
        total = qs.count()
        return {"count": total, "since": since.isoformat()}

    return {
        "15m": _stats(now - timedelta(minutes=15)),
        "24h": _stats(now - timedelta(hours=24)),
    }


def get_ual_scenario_distribution():
    """
    UAL scenario distribution from DecisionRecords.

    Returns:
        dict with 1h, 24h, 14d scenario counts.
    """
    from apps.core.ai_observability.models import DecisionRecord

    now = timezone.now()

    def _distribution(since):
        qs = DecisionRecord.objects.filter(
            engine_name="UAL",
            decision_type="arbitration",
            created_at__gte=since,
        )
        counts = {}
        for rec in qs.values_list("decision", flat=True):
            # decision format: "SCENARIO=HEALTH_CRITICAL"
            scenario = rec.replace("SCENARIO=", "") if rec.startswith("SCENARIO=") else rec
            counts[scenario] = counts.get(scenario, 0) + 1
        return counts

    return {
        "1h": _distribution(now - timedelta(hours=1)),
        "24h": _distribution(now - timedelta(hours=24)),
        "14d": _distribution(now - timedelta(days=14)),
    }


def get_confidence_trend():
    """
    Average confidence per hour for the last 24h from DecisionRecords.

    Returns:
        list of {"hour": "2026-02-21T07:00:00", "avg_confidence": 0.65}
    """
    from apps.core.ai_observability.models import DecisionRecord

    now = timezone.now()
    start = now - timedelta(hours=24)

    trend = []
    for h in range(24):
        hour_start = start + timedelta(hours=h)
        hour_end = hour_start + timedelta(hours=1)
        avg = DecisionRecord.objects.filter(
            created_at__gte=hour_start,
            created_at__lt=hour_end,
            confidence__isnull=False,
        ).aggregate(avg=Avg("confidence"))["avg"]
        trend.append(
            {
                "hour": hour_start.isoformat(),
                "avg_confidence": round(avg, 3) if avg else None,
            }
        )
    return trend


def get_system_latency():
    """
    P50/P95 duration per engine over last 1h (approx).

    Returns:
        dict of engine_name -> {"p50": ms, "p95": ms, "count": n}
    """
    from apps.core.ai_observability.models import EngineRun

    now = timezone.now()
    one_hour_ago = now - timedelta(hours=1)

    result = {}
    for engine in ALL_ENGINES:
        durations = list(
            EngineRun.objects.filter(
                engine_name=engine, started_at__gte=one_hour_ago
            )
            .order_by("duration_ms")
            .values_list("duration_ms", flat=True)
        )
        if not durations:
            result[engine] = {"p50": 0, "p95": 0, "count": 0}
            continue

        n = len(durations)
        p50_idx = max(0, int(n * 0.5) - 1)
        p95_idx = max(0, int(n * 0.95) - 1)
        result[engine] = {
            "p50": durations[p50_idx],
            "p95": durations[p95_idx],
            "count": n,
        }
    return result


def get_system_status(pulses=None):
    """
    Overall system status: green, yellow, or red.

    Args:
        pulses: Optional pre-computed engine pulses. Computed if None.

    Returns:
        str: "green", "yellow", or "red"
    """
    if pulses is None:
        pulses = get_all_engine_pulses()

    statuses = [p["status"] for p in pulses]
    if "red" in statuses:
        return "red"
    if "yellow" in statuses:
        return "yellow"
    return "green"
