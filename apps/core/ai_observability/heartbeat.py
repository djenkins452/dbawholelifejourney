"""
Heartbeat Calculator — Computes expected vs actual engine run cadence.

Reads EngineExpectedCadence config and latest EngineRun records to
produce EngineHeartbeat entries. Called by SAME engine or on-demand.

Project: Whole Life Journey
Path: apps/core/ai_observability/heartbeat.py
"""

import logging
from datetime import timedelta

from django.utils import timezone

from apps.core.ai_observability.ops_aggregates import ENGINE_CADENCES

logger = logging.getLogger(__name__)

# Default jitter per cadence tier (seconds)
DEFAULT_JITTER = {
    300: 120,      # 5m cadence -> 2m jitter
    3600: 300,     # 1h cadence -> 5m jitter
    86400: 3600,   # 24h cadence -> 1h jitter
    604800: 86400,  # 7d cadence -> 24h jitter
}


def get_cadence_config():
    """
    Get cadence configuration, preferring database records over hardcoded defaults.

    Returns:
        dict of engine_name -> {interval, jitter, enabled}
    """
    from apps.core.ai_observability.models import EngineExpectedCadence

    config = {}

    # Start with hardcoded defaults
    for engine, interval in ENGINE_CADENCES.items():
        jitter = DEFAULT_JITTER.get(interval, 60)
        config[engine] = {
            "interval": interval,
            "jitter": jitter,
            "enabled": True,
        }

    # Override with database config
    try:
        for cadence in EngineExpectedCadence.objects.filter(is_enabled=True):
            config[cadence.engine_name] = {
                "interval": cadence.expected_interval_seconds,
                "jitter": cadence.expected_jitter_seconds,
                "enabled": True,
            }
        # Mark disabled engines
        for cadence in EngineExpectedCadence.objects.filter(is_enabled=False):
            if cadence.engine_name in config:
                config[cadence.engine_name]["enabled"] = False
    except Exception:
        pass  # Database not ready yet

    return config


def compute_heartbeats():
    """
    Compute heartbeat status for all enabled engines.

    Returns:
        list of EngineHeartbeat instances (unsaved if save=False).
    """
    from apps.core.ai_observability.models import EngineHeartbeat, EngineRun

    now = timezone.now()
    config = get_cadence_config()
    heartbeats = []

    for engine_name, cfg in config.items():
        if not cfg["enabled"]:
            continue

        interval = cfg["interval"]
        jitter = cfg["jitter"]

        # Get last successful run
        last_run = (
            EngineRun.objects.filter(engine_name=engine_name)
            .order_by("-started_at")
            .values("started_at", "status")
            .first()
        )

        last_run_at = last_run["started_at"] if last_run else None

        # Compute next expected and status
        if last_run_at is None:
            # Never run — don't flag as missed (could be new install)
            status = "OK"
            next_expected_at = None
            lateness = 0
        else:
            next_expected_at = last_run_at + timedelta(seconds=interval)
            deadline = next_expected_at + timedelta(seconds=jitter)

            if now <= next_expected_at:
                status = "OK"
                lateness = 0
            elif now <= deadline:
                status = "LATE"
                lateness = int((now - next_expected_at).total_seconds())
            else:
                status = "MISSED"
                lateness = int((now - next_expected_at).total_seconds())

        # Check for recent errors
        recent_errors = 0
        if last_run and last_run.get("status") == "error":
            status = "ERROR"

        # Count errors in last 30m for metadata
        thirty_min_ago = now - timedelta(minutes=30)
        recent_errors = EngineRun.objects.filter(
            engine_name=engine_name,
            started_at__gte=thirty_min_ago,
            status="error",
        ).count()

        recent_runs = EngineRun.objects.filter(
            engine_name=engine_name,
            started_at__gte=thirty_min_ago,
        ).count()

        heartbeat = EngineHeartbeat(
            engine_name=engine_name,
            observed_at=now,
            status=status,
            last_run_at=last_run_at,
            next_expected_at=next_expected_at,
            lateness_seconds=lateness,
            metadata={
                "interval_seconds": interval,
                "jitter_seconds": jitter,
                "recent_errors_30m": recent_errors,
                "recent_runs_30m": recent_runs,
            },
        )
        heartbeats.append(heartbeat)

    return heartbeats


def compute_and_save_heartbeats():
    """
    Compute heartbeats and save to database.

    Returns:
        list of saved EngineHeartbeat instances.
    """
    from apps.core.ai_observability.models import EngineHeartbeat

    heartbeats = compute_heartbeats()

    saved = []
    for hb in heartbeats:
        try:
            hb.save()
            saved.append(hb)
        except Exception as e:
            logger.warning("Failed to save heartbeat for %s: %s", hb.engine_name, e)

    return saved


def get_latest_heartbeats():
    """
    Get the most recent heartbeat for each engine.

    Returns:
        dict of engine_name -> heartbeat dict.
    """
    from apps.core.ai_observability.models import EngineHeartbeat

    result = {}
    seen = set()

    for hb in EngineHeartbeat.objects.order_by("-observed_at")[:100]:
        if hb.engine_name not in seen:
            seen.add(hb.engine_name)
            result[hb.engine_name] = {
                "engine_name": hb.engine_name,
                "status": hb.status,
                "observed_at": hb.observed_at.isoformat(),
                "last_run_at": hb.last_run_at.isoformat() if hb.last_run_at else None,
                "next_expected_at": (
                    hb.next_expected_at.isoformat() if hb.next_expected_at else None
                ),
                "lateness_seconds": hb.lateness_seconds,
                "metadata": hb.metadata,
            }

    return result


def seed_cadence_config():
    """
    Seed EngineExpectedCadence from ENGINE_CADENCES defaults.

    Safe to call multiple times — uses get_or_create.
    """
    from apps.core.ai_observability.models import EngineExpectedCadence

    for engine_name, interval in ENGINE_CADENCES.items():
        jitter = DEFAULT_JITTER.get(interval, 60)
        EngineExpectedCadence.objects.get_or_create(
            engine_name=engine_name,
            defaults={
                "expected_interval_seconds": interval,
                "expected_jitter_seconds": jitter,
                "is_enabled": True,
            },
        )
