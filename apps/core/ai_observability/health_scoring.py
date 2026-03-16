"""
COAS — Health Scoring Engine.

Computes 0-100 health scores for three operational subsystems:
  1. Scheduler Health — APScheduler process + ISE/SAME heartbeats + task failures
  2. Engine Health — Engine heartbeat statuses + 30m error rate + active anomalies
  3. Intelligence Freshness — Staleness of key scheduled intelligence tasks

Also computes a weighted overall system health score and persists
snapshots for the Ops Wall to read without live recomputation.

All scoring functions are read-only and must complete in <500ms.
Each scorer is independently try/excepted so one failure doesn't
abort the full monitoring cycle.

No OpenAI calls. No external API calls.

Project: Whole Life Journey
Path: apps/core/ai_observability/health_scoring.py
"""

import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)


# =============================================================================
# SCHEDULER HEALTH SCORING
# =============================================================================

def compute_scheduler_health():
    """
    Compute scheduler subsystem health score (0-100).

    Reads:
        - SchedulerHeartbeat for ISE and SAME status
        - get_scheduler_status() for APScheduler process health
        - ScheduledIntelligenceTask for recently failed tasks

    Returns:
        dict with keys: score (int), details (dict with breakdowns)
        On failure: {score: None, details: {error: str}}
    """
    try:
        return _compute_scheduler_health_inner()
    except Exception as e:
        logger.error("COAS: Scheduler health scorer failed: %s", e, exc_info=True)
        return {"score": None, "details": {"error": str(e)}}


def _compute_scheduler_health_inner():
    from apps.core.ai_observability.models import SchedulerHeartbeat
    from apps.core.ai_scheduler.scheduler_models import ScheduledIntelligenceTask

    score = 100
    details = {}

    # --- ISE Heartbeat ---
    ise_hb = SchedulerHeartbeat.get_for_scheduler("ISE")
    ise_status = ise_hb.status if ise_hb else "OFFLINE"
    ise_penalty = 0
    if ise_status == "DELAYED":
        ise_penalty = 15
    elif ise_status == "OFFLINE":
        ise_penalty = 40
    score -= ise_penalty
    details["ise"] = {
        "status": ise_status,
        "penalty": ise_penalty,
        "drift_seconds": ise_hb.drift_seconds if ise_hb else None,
    }

    # --- SAME Heartbeat ---
    same_hb = SchedulerHeartbeat.get_for_scheduler("SAME")
    same_status = same_hb.status if same_hb else "OFFLINE"
    same_penalty = 0
    if same_status == "DELAYED":
        same_penalty = 10
    elif same_status == "OFFLINE":
        same_penalty = 30
    score -= same_penalty
    details["same"] = {
        "status": same_status,
        "penalty": same_penalty,
        "drift_seconds": same_hb.drift_seconds if same_hb else None,
    }

    # --- Celery Beat health (derived from ISE + SAME) ---
    # If both ISE and SAME are alive, Beat is dispatching. If both offline,
    # Beat is likely dead. Penalty is already captured in ISE/SAME above,
    # so we just report status for observability.
    beat_running = ise_status in ("ALIVE", "DELAYED") or same_status in ("ALIVE", "DELAYED")
    details["celery_beat"] = {
        "running": beat_running,
        "penalty": 0,  # No separate penalty — covered by ISE/SAME
    }

    # --- Failed ISE tasks ---
    try:
        failed_tasks = list(
            ScheduledIntelligenceTask.objects.filter(
                is_active=True,
                last_status="failed",
            ).values_list("task_name", flat=True)
        )
    except Exception:
        failed_tasks = []
    failed_penalty = min(len(failed_tasks) * 3, 15)
    score -= failed_penalty
    details["failed_tasks"] = {
        "count": len(failed_tasks),
        "names": failed_tasks[:5],
        "penalty": failed_penalty,
    }

    return {
        "score": max(score, 0),
        "details": details,
    }


# =============================================================================
# ENGINE HEALTH SCORING
# =============================================================================

def compute_engine_health():
    """
    Compute engine subsystem health score (0-100).

    Reads:
        - get_latest_heartbeats() for engine status distribution
        - EngineRun for 30m error rate
        - OpsAnomaly for active P1 anomalies

    Returns:
        dict with keys: score (int), details (dict)
        On failure: {score: None, details: {error: str}}
    """
    try:
        return _compute_engine_health_inner()
    except Exception as e:
        logger.error("COAS: Engine health scorer failed: %s", e, exc_info=True)
        return {"score": None, "details": {"error": str(e)}}


def _compute_engine_health_inner():
    from apps.core.ai_observability.heartbeat import get_latest_heartbeats
    from apps.core.ai_observability.models import EngineRun, OpsAnomaly

    now = timezone.now()
    score = 100
    details = {}

    # --- Engine heartbeats ---
    heartbeats = get_latest_heartbeats()
    total = len(heartbeats) if heartbeats else 1
    ok_count = sum(
        1 for hb in heartbeats.values()
        if isinstance(hb, dict) and hb.get("status") == "OK"
    )
    pct_ok = ok_count / total if total > 0 else 1.0
    hb_penalty = int((1.0 - pct_ok) * 50)
    score -= hb_penalty
    details["heartbeats"] = {
        "total": total,
        "ok": ok_count,
        "pct_ok": round(pct_ok, 3),
        "penalty": hb_penalty,
    }

    # --- 30m error rate ---
    thirty_min_ago = now - timedelta(minutes=30)
    total_runs = EngineRun.objects.filter(
        started_at__gte=thirty_min_ago
    ).count()
    error_runs = EngineRun.objects.filter(
        started_at__gte=thirty_min_ago,
        status="error",
    ).count()
    error_rate = error_runs / total_runs if total_runs > 0 else 0.0
    error_penalty = min(int(error_rate * 100), 20)
    score -= error_penalty
    details["error_rate_30m"] = {
        "total_runs": total_runs,
        "error_runs": error_runs,
        "rate": round(error_rate, 3),
        "penalty": error_penalty,
    }

    # --- Active P1 anomalies ---
    p1_count = OpsAnomaly.objects.filter(
        is_active=True,
        severity="P1",
    ).count()
    p1_penalty = min(p1_count * 10, 20)
    score -= p1_penalty
    details["p1_anomalies"] = {
        "count": p1_count,
        "penalty": p1_penalty,
    }

    return {
        "score": max(score, 0),
        "details": details,
    }


# =============================================================================
# INTELLIGENCE FRESHNESS SCORING
# =============================================================================

# Key intelligence tasks and their expected intervals + scoring weights.
# Total weight = 100 (maps directly to score points).
_FRESHNESS_TASKS = {
    "generate_daily_briefings": {"expected_seconds": 86400, "weight": 25},
    "refresh_guidance": {"expected_seconds": 21600, "weight": 20},
    "run_pie_synthetic": {"expected_seconds": 300, "weight": 20},
    "run_prie_synthetic": {"expected_seconds": 3600, "weight": 15},
    "deliver_intelligence_notifications": {"expected_seconds": 600, "weight": 20},
}


def compute_intelligence_freshness():
    """
    Compute intelligence freshness score (0-100).

    For each key scheduled task, compares (now - last_run_at) to its
    expected interval. Staleness ratio determines penalty.

    Resilient: missing, renamed, or disabled tasks do NOT crash the scorer.
    Disabled tasks (is_active=False) get zero penalty (intentionally off).
    Missing tasks get full-weight penalty (something is wrong).

    Returns:
        dict with keys: score (int), details (dict)
        On failure: {score: None, details: {error: str}}
    """
    try:
        return _compute_intelligence_freshness_inner()
    except Exception as e:
        logger.error("COAS: Freshness scorer failed: %s", e, exc_info=True)
        return {"score": None, "details": {"error": str(e)}}


def _compute_intelligence_freshness_inner():
    from apps.core.ai_scheduler.scheduler_models import ScheduledIntelligenceTask

    now = timezone.now()
    score = 100
    task_details = {}

    for task_name, config in _FRESHNESS_TASKS.items():
        expected = config["expected_seconds"]
        weight = config["weight"]

        try:
            task = ScheduledIntelligenceTask.objects.get(task_name=task_name)
        except ScheduledIntelligenceTask.DoesNotExist:
            # Task not registered — full penalty (something is wrong)
            task_details[task_name] = {
                "status": "NOT_FOUND",
                "penalty": weight,
                "ratio": None,
            }
            score -= weight
            continue
        except Exception as e:
            # DB error — don't crash, log and skip with full penalty
            logger.warning("COAS: Failed to query task %s: %s", task_name, e)
            task_details[task_name] = {
                "status": "ERROR",
                "penalty": weight,
                "ratio": None,
                "error": str(e),
            }
            score -= weight
            continue

        # Disabled tasks — zero penalty (intentionally turned off)
        if not task.is_active:
            task_details[task_name] = {
                "status": "DISABLED",
                "penalty": 0,
                "ratio": None,
            }
            continue

        if task.last_run_at is None:
            # Never run — full penalty
            task_details[task_name] = {
                "status": "NEVER_RUN",
                "penalty": weight,
                "ratio": None,
                "last_status": task.last_status,
            }
            score -= weight
            continue

        elapsed = (now - task.last_run_at).total_seconds()
        ratio = elapsed / expected if expected > 0 else 999.0

        if ratio <= 1.5:
            penalty = 0
            status = "FRESH"
        elif ratio <= 3.0:
            # Linear interpolation: 0 at 1.5x, full weight at 3.0x
            fraction = (ratio - 1.5) / 1.5
            penalty = int(weight * fraction)
            status = "STALE"
        else:
            penalty = weight
            status = "CRITICAL"

        score -= penalty
        task_details[task_name] = {
            "status": status,
            "ratio": round(ratio, 2),
            "elapsed_seconds": int(elapsed),
            "expected_seconds": expected,
            "penalty": penalty,
            "last_run_at": task.last_run_at.isoformat(),
            "last_status": task.last_status,
        }

    return {
        "score": max(score, 0),
        "details": task_details,
    }


# =============================================================================
# OVERALL SYSTEM HEALTH
# =============================================================================

# Weights for the overall system health composite score
_SUBSYSTEM_WEIGHTS = {
    "scheduler": 0.30,
    "engine": 0.40,
    "freshness": 0.30,
}


def compute_system_health(scheduler_score, engine_score, freshness_score):
    """
    Compute weighted overall system health score (0-100).

    If a subsystem score is None (scorer failed), it is excluded and
    the remaining weights are renormalized.

    Returns:
        dict with keys: score (int), components (dict)
    """
    scores = {
        "scheduler": scheduler_score,
        "engine": engine_score,
        "freshness": freshness_score,
    }

    # Filter out failed scorers (score=None)
    valid = {k: v for k, v in scores.items() if v is not None}

    if not valid:
        return {
            "score": None,
            "components": {
                k: {"score": v, "weight": _SUBSYSTEM_WEIGHTS[k]}
                for k, v in scores.items()
            },
        }

    # Renormalize weights for available scorers
    total_weight = sum(_SUBSYSTEM_WEIGHTS[k] for k in valid)
    weighted_sum = sum(
        v * (_SUBSYSTEM_WEIGHTS[k] / total_weight)
        for k, v in valid.items()
    )
    overall = int(weighted_sum)

    return {
        "score": max(overall, 0),
        "components": {
            k: {"score": scores[k], "weight": _SUBSYSTEM_WEIGHTS[k]}
            for k in scores
        },
    }


def compute_all_scores():
    """
    Compute all COAS health scores in one call.

    Each scorer is independently try/excepted — partial results
    are returned if one fails.

    Returns:
        dict with keys: scheduler, engine, freshness, overall
        Each containing: {score (int or None), details (dict)}
    """
    scheduler = compute_scheduler_health()
    engine = compute_engine_health()
    freshness = compute_intelligence_freshness()
    overall = compute_system_health(
        scheduler["score"],
        engine["score"],
        freshness["score"],
    )

    return {
        "scheduler": scheduler,
        "engine": engine,
        "freshness": freshness,
        "overall": overall,
    }


def save_health_snapshot(scores):
    """
    Persist latest COAS scores as a single-row snapshot.

    Uses update_or_create with pk=1 to maintain a single row.
    The Ops Wall reads this snapshot instead of recomputing live.

    Args:
        scores: dict from compute_all_scores()

    Returns:
        COASHealthSnapshot instance
    """
    from apps.core.ai_observability.models import COASHealthSnapshot

    now = timezone.now()

    snapshot, _ = COASHealthSnapshot.objects.update_or_create(
        pk=1,
        defaults={
            "scheduler_score": scores["scheduler"]["score"] or 0,
            "engine_score": scores["engine"]["score"] or 0,
            "freshness_score": scores["freshness"]["score"] or 0,
            "overall_score": scores["overall"]["score"] or 0,
            "details": {
                "scheduler": scores["scheduler"].get("details", {}),
                "engine": scores["engine"].get("details", {}),
                "freshness": scores["freshness"].get("details", {}),
                "overall": scores["overall"].get("components", {}),
            },
            "computed_at": now,
        },
    )

    return snapshot
