"""
Operations Wall — Telemetry & Aggregation Helpers.

Project: Whole Life Journey
Path: apps/core/ai_observability/ops_telemetry.py
Purpose: Extracted helper functions for the Operations Wall dashboard.
         These functions aggregate telemetry data from various engines
         and subsystems for display on the admin dashboard.

Extracted from ops_views.py for maintainability.

PERFORMANCE NOTE (2026-03-16):
    The OpsStreamView is a pure cache reader (zero DB queries on HTTP path).
    The full payload is built by the SAME engine cycle (background, every 60s).

    _build_engine_cards() was optimized from ~180 queries (N+1 per-engine loop)
    to ~7 batched queries using Django ORM aggregation. Total payload build
    is ~100 queries (down from ~290). Build time is tracked via the
    ops_stream_build_time_ms field in the payload.

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import json
import logging
import time
from datetime import timedelta

from django.core.cache import cache as django_cache
from django.utils import timezone

logger = logging.getLogger(__name__)


# =========================================================================
# HELPER FUNCTIONS
# =========================================================================


def _build_engine_cards(engine_names, cadence_config, heartbeats, now):
    """Build engine card data for each core engine.

    Performance-optimized: uses batched aggregate queries instead of
    per-engine loops. Total query count: ~7 (was ~180 with N+1 pattern).

    Queries:
      1. Last run per engine (Window/Subquery)
      2. Errors in last 30m per engine (aggregate)
      3. Missed heartbeats in last 30m per engine (aggregate)
      4. Errors in last 24h per engine (aggregate)
      5. Sparkline: last 6 runs per engine (Window/row_number)
      6. Duration P95: all runs in last 1h (single query, computed in Python)
      7. Engine registry metadata (in-memory, 0 DB queries)
    """
    cached = django_cache.get("wlj:ops:engine_cards")
    if cached is not None:
        return cached

    from django.db.models import Count, Max, Q, Subquery, OuterRef
    from apps.core.ai_observability.models import EngineHeartbeat, EngineRun

    thirty_min_ago = now - timedelta(minutes=30)
    twenty_four_h_ago = now - timedelta(hours=24)
    one_hour_ago = now - timedelta(hours=1)

    # --- Batch Query 1: Last run per engine ---
    # Use a single query with annotation to get the latest run per engine
    last_runs_qs = (
        EngineRun.objects.filter(engine_name__in=engine_names)
        .values("engine_name")
        .annotate(last_started=Max("started_at"))
    )
    # Map engine_name -> last_started_at
    last_run_map = {r["engine_name"]: r["last_started"] for r in last_runs_qs}

    # Get the actual run details for those latest runs (status, duration)
    # We need the full row for each engine's latest run
    last_run_details = {}
    if last_run_map:
        # Subquery approach: get runs matching engine+max_started_at
        for run in EngineRun.objects.filter(
            engine_name__in=engine_names,
        ).order_by("engine_name", "-started_at").values(
            "engine_name", "started_at", "status", "duration_ms"
        ):
            # Only keep the first (latest) per engine
            if run["engine_name"] not in last_run_details:
                last_run_details[run["engine_name"]] = run
            if len(last_run_details) == len(engine_names):
                break

    # --- Batch Query 2: Error count per engine (last 30m) ---
    errors_30m_qs = (
        EngineRun.objects.filter(
            engine_name__in=engine_names,
            started_at__gte=thirty_min_ago,
            status="error",
        )
        .values("engine_name")
        .annotate(count=Count("id"))
    )
    errors_30m_map = {r["engine_name"]: r["count"] for r in errors_30m_qs}

    # --- Batch Query 3: Missed heartbeats per engine (last 30m) ---
    miss_qs = (
        EngineHeartbeat.objects.filter(
            engine_name__in=engine_names,
            status="MISSED",
            observed_at__gte=thirty_min_ago,
        )
        .values("engine_name")
        .annotate(count=Count("id"))
    )
    miss_map = {r["engine_name"]: r["count"] for r in miss_qs}

    # --- Batch Query 4: Error count per engine (last 24h) ---
    errors_24h_qs = (
        EngineRun.objects.filter(
            engine_name__in=engine_names,
            started_at__gte=twenty_four_h_ago,
            status="error",
        )
        .values("engine_name")
        .annotate(count=Count("id"))
    )
    errors_24h_map = {r["engine_name"]: r["count"] for r in errors_24h_qs}

    # --- Batch Query 5: Sparkline data (last 6 runs per engine) ---
    # Fetch recent runs ordered by engine then time, slice in Python
    sparkline_runs = list(
        EngineRun.objects.filter(engine_name__in=engine_names)
        .order_by("engine_name", "-started_at")
        .values_list("engine_name", "duration_ms")[:len(engine_names) * 6]
    )
    sparkline_map = {}
    for eng, dur in sparkline_runs:
        if eng not in sparkline_map:
            sparkline_map[eng] = []
        if len(sparkline_map[eng]) < 6:
            sparkline_map[eng].append(dur)

    # --- Batch Query 6: Duration P95 (all runs in last 1h) ---
    # Fetch all durations in one query, group in Python
    p95_runs = list(
        EngineRun.objects.filter(
            engine_name__in=engine_names,
            started_at__gte=one_hour_ago,
        )
        .order_by("engine_name", "duration_ms")
        .values_list("engine_name", "duration_ms")
    )
    p95_map = {}
    for eng, dur in p95_runs:
        if eng not in p95_map:
            p95_map[eng] = []
        p95_map[eng].append(dur)

    # --- Engine registry metadata (in-memory, no DB) ---
    from apps.core.ai_observability.engine_registry import get_engine_meta

    # Pre-fetch all engine meta in one call to the in-memory registry
    engine_meta_map = {}
    for name in engine_names:
        engine_meta_map[name] = get_engine_meta(name)

    # --- Assemble cards ---
    cards = []
    for name in engine_names:
        cfg = cadence_config.get(name, {})
        hb = heartbeats.get(name, {})
        interval = cfg.get("interval", 3600)

        # Last run from batch
        last_run = last_run_details.get(name)

        # Status mapping from heartbeat
        hb_status = hb.get("status", "OK")
        if hb_status == "MISSED":
            card_status = "MISSED"
        elif hb_status == "LATE":
            card_status = "DEGRADED"
        elif hb_status == "ERROR":
            card_status = "ERROR"
        else:
            card_status = "OK"

        # Override with error rate check
        errors_30m = errors_30m_map.get(name, 0)
        if errors_30m > 3:
            card_status = "ERROR"

        # Miss counter from batch
        miss_count = miss_map.get(name, 0)

        # Error counter from batch
        errors_24h = errors_24h_map.get(name, 0)

        # Sparkline from batch (reverse to chronological order)
        sparkline = list(reversed(sparkline_map.get(name, [])))

        # Duration P95 from batch
        durations_1h = p95_map.get(name, [])
        if durations_1h:
            p95_idx = max(0, int(len(durations_1h) * 0.95) - 1)
            duration_p95 = durations_1h[p95_idx]
        else:
            duration_p95 = 0

        # Human-readable cadence
        if interval >= 604800:
            cadence_label = f"{interval // 604800}w"
        elif interval >= 86400:
            cadence_label = f"{interval // 86400}d"
        elif interval >= 3600:
            cadence_label = f"{interval // 3600}h"
        else:
            cadence_label = f"{interval // 60}m"

        # Engine metadata from pre-fetched map
        eng_meta = engine_meta_map.get(name)
        can_manual = eng_meta["can_manual_run"] if eng_meta else False
        execution_mode = eng_meta.get("execution_mode", "batch") if eng_meta else "batch"

        cards.append({
            "name": name,
            "status": card_status,
            "cadence": cadence_label,
            "last_run_at": (
                last_run["started_at"].isoformat() if last_run and last_run["started_at"] else None
            ),
            "next_expected_at": hb.get("next_expected_at"),
            "miss_count_30m": miss_count,
            "error_count_24h": errors_24h,
            "duration_p95_1h": duration_p95,
            "sparkline": sparkline,
            "lateness_seconds": hb.get("lateness_seconds", 0),
            "can_manual_run": can_manual,
            "execution_mode": execution_mode,
            "is_frozen": not cfg.get("enabled", True),
        })

    django_cache.set("wlj:ops:engine_cards", cards, timeout=10)
    return cards


def _get_latest_narrative():
    """Get the most recent OpsNarrativeSnapshot as dict. Cached 10s."""
    cached = django_cache.get("wlj:ops:latest_narrative")
    if cached is not None:
        return cached

    from apps.core.ai_observability.models import OpsNarrativeSnapshot

    snapshot = OpsNarrativeSnapshot.objects.first()
    if not snapshot:
        result = {
            "posture": "OK",
            "headline": "SAME not yet initialized — awaiting first run.",
            "bullets_now": ["No data available yet."],
            "recommendations": ["System will begin monitoring once engines start running."],
            "watching_next": [],
        }
        django_cache.set("wlj:ops:latest_narrative", result, timeout=10)
        return result

    result = {
        "posture": snapshot.posture,
        "headline": snapshot.headline,
        "bullets_now": snapshot.bullets_now or [],
        "recommendations": snapshot.recommendations or [],
        "watching_next": snapshot.watching_next or [],
        "created_at": snapshot.created_at.isoformat(),
    }
    django_cache.set("wlj:ops:latest_narrative", result, timeout=10)
    return result


def _get_latest_integrity():
    """Get the latest SystemIntegritySnapshot as dict. Cached 10s."""
    cached = django_cache.get("wlj:ops:latest_integrity")
    if cached is not None:
        return cached

    from apps.core.ai_observability.models import SystemIntegritySnapshot

    snapshot = SystemIntegritySnapshot.objects.first()
    if not snapshot:
        return None

    result = {
        "score": snapshot.score,
        "posture": snapshot.posture,
        "components": snapshot.components,
        "created_at": snapshot.created_at.isoformat(),
    }
    django_cache.set("wlj:ops:latest_integrity", result, timeout=10)
    return result


def _get_active_anomalies():
    """Get all active OpsAnomaly records as list of dicts. Cached 10s."""
    cached = django_cache.get("wlj:ops:active_anomalies")
    if cached is not None:
        return cached

    from apps.core.ai_observability.models import OpsAnomaly

    anomalies = OpsAnomaly.objects.filter(is_active=True).order_by(
        "severity", "-created_at"
    )

    result = []
    for a in anomalies:
        entry = {
            "id": a.id,
            "severity": a.severity,
            "engine_name": a.engine_name,
            "anomaly_type": a.anomaly_type,
            "summary": a.summary,
            "suggested_actions": a.suggested_actions or [],
            "created_at": a.created_at.isoformat(),
            "first_detected": _human_ago(a.created_at),
            "escalation_count": a.escalation_count,
            "original_severity": a.original_severity or a.severity,
            "last_escalated_at": (
                a.last_escalated_at.isoformat() if a.last_escalated_at else None
            ),
        }
        result.append(entry)

    django_cache.set("wlj:ops:active_anomalies", result, timeout=10)
    return result


def _execute_action(action, engine, trace_id):
    """Execute an admin action safely."""
    try:
        if action == "rerun_engine":
            return _action_rerun_engine(engine, trace_id)
        elif action == "requeue_job":
            return _action_rerun_engine(engine, trace_id)  # Same as rerun for now
        elif action == "clear_suppression_cache":
            return _action_clear_suppression_cache(engine)
        elif action == "restart_scheduler":
            return _action_restart_scheduler()
        elif action == "acknowledge_anomaly":
            return _action_acknowledge_anomaly(engine)
        elif action == "rebuild_health_summaries":
            return _action_rebuild_health_summaries()
        elif action == "investigate_pipeline":
            return _action_investigate_pipeline(engine)
        else:
            return {"status": "failure", "detail": f"Unknown action: {action}"}
    except Exception as e:
        logger.exception("Admin action %s failed: %s", action, e)
        return {"status": "failure", "detail": str(e)[:500]}


def _action_rerun_engine(engine, trace_id):
    """
    Re-run an engine using ENGINE_REGISTRY batch runners.

    Uses centralized registry to resolve the correct batch runner function.
    For engines with can_manual_run=True, calls the batch runner that
    iterates all active users internally. For user-context engines,
    returns a message that they'll run on next interaction.
    """
    from apps.core.ai_observability.engine_registry import (
        get_engine_meta,
        resolve_batch_runner,
    )
    from apps.core.ai_observability.trace import trace_context

    meta = get_engine_meta(engine)
    if not meta:
        return {"status": "failure", "detail": f"No registry entry for {engine}"}

    if not meta["can_manual_run"]:
        return {
            "status": "success",
            "detail": (
                f"{engine} requires user context — "
                f"it will run on next user interaction. Trace: {trace_id}"
            ),
        }

    try:
        runner = resolve_batch_runner(engine)
        if not runner:
            return {"status": "failure", "detail": f"No batch runner for {engine}"}

        with trace_context(trace_id=trace_id, source="admin_action"):
            result = runner()

        return {
            "status": "success",
            "detail": f"{engine} re-run successfully. Result: {result}. Trace: {trace_id}",
        }
    except Exception as e:
        return {
            "status": "failure",
            "detail": f"{engine} re-run failed: {str(e)[:300]}",
        }


def _action_clear_suppression_cache(engine):
    """Clear ICQG suppression cache."""
    if engine != "ICQG":
        return {"status": "failure", "detail": "Only ICQG suppression cache can be cleared"}

    try:
        from apps.core.ai_quality.models import QualitySuppressionRecord

        # Clear recent suppression records (last 24h) to allow reprocessing
        cleared = QualitySuppressionRecord.objects.filter(
            suppressed_at__gte=timezone.now() - timedelta(hours=24)
        ).delete()[0]

        return {
            "status": "success",
            "detail": f"Cleared {cleared} suppression records from last 24h",
        }
    except Exception as e:
        return {"status": "failure", "detail": f"Cache clear failed: {str(e)[:300]}"}


def _action_restart_scheduler():
    """Scheduler restart info (APScheduler removed 2026-03-16)."""
    return {
        "status": "info",
        "detail": (
            "APScheduler was removed. All scheduling is via Celery Beat. "
            "Restart the Beat process on Railway to fix scheduling issues."
        ),
    }


def _action_acknowledge_anomaly(engine):
    """Acknowledge and resolve anomalies for a specific engine."""
    from apps.core.ai_observability.models import OpsAnomaly

    resolved = 0
    for anomaly in OpsAnomaly.objects.filter(engine_name=engine, is_active=True):
        anomaly.is_active = False
        anomaly.resolved_at = timezone.now()
        anomaly.save(update_fields=["is_active", "resolved_at", "updated_at"])
        resolved += 1

    return {
        "status": "success",
        "detail": f"Acknowledged {resolved} anomaly/anomalies for {engine}",
    }


def _action_investigate_pipeline(domain):
    """
    Investigate and refresh a domain's signal pipeline.

    Uses cached signal health to avoid expensive live computation.
    The 'engine' parameter carries the domain name (e.g., 'purpose').
    """
    try:
        sh = _get_signal_health() or {}
        domains = sh.get("domains", {})
        domain_lower = (domain or "").lower()

        if domain_lower and domain_lower in domains:
            data = domains[domain_lower]
            freshness = data.get("freshness_hours", 0)
            status = data.get("status", "unknown")
            vol_24h = data.get("volume_24h", 0)

            return {
                "status": "success",
                "detail": (
                    f"Pipeline check for '{domain_lower}': status={status}, "
                    f"freshness={freshness:.0f}h, volume_24h={vol_24h}. "
                    f"Signal pipeline is {'active' if status == 'healthy' else 'degraded — check engine runs and data sources'}."
                ),
            }

        # No specific domain — run overall check
        silent = sh.get("domains_silent", 0)
        active = sh.get("domains_active", 0)
        stalest = sh.get("stalest_domain", "?")
        return {
            "status": "success" if silent == 0 else "failure",
            "detail": (
                f"Signal pipeline: {active} active, {silent} silent domains. "
                f"Stalest: {stalest} ({sh.get('stalest_hours', 0):.0f}h). "
                f"{'All pipelines healthy.' if silent == 0 else 'Run diagnostic scan for details.'}"
            ),
        }
    except Exception as e:
        return {
            "status": "failure",
            "detail": f"Pipeline investigation failed: {str(e)[:300]}",
        }


def _action_rebuild_health_summaries():
    """Queue a full nightly health summary rebuild via Celery."""
    try:
        from apps.health.tasks import build_nightly_health_summaries
        build_nightly_health_summaries.delay()
        return {
            "status": "success",
            "detail": "Health summary nightly rebuild queued via Celery.",
        }
    except ImportError:
        return {
            "status": "failure",
            "detail": "Celery health tasks not available.",
        }
    except Exception as e:
        return {
            "status": "failure",
            "detail": f"Failed to queue rebuild: {e}",
        }


def _get_scheduler_heartbeats():
    """Get heartbeat status for all tracked schedulers. Cached 10s."""
    cached = django_cache.get("wlj:ops:scheduler_heartbeats")
    if cached is not None:
        return cached

    from apps.core.ai_observability.models import SchedulerHeartbeat

    schedulers = []
    try:
        for hb in SchedulerHeartbeat.objects.all():
            schedulers.append({
                "scheduler_name": hb.scheduler_name,
                "status": hb.status,
                "last_tick_at": hb.last_tick_at.isoformat(),
                "expected_interval_seconds": hb.expected_interval_seconds,
                "drift_seconds": hb.drift_seconds,
                "cycle_result": hb.cycle_result,
                "alive_threshold_multiplier": hb.alive_threshold_multiplier,
                "offline_threshold_multiplier": hb.offline_threshold_multiplier,
                "updated_at": hb.updated_at.isoformat(),
            })
    except Exception:
        pass  # Table may not exist yet

    # If no heartbeat rows exist, return OFFLINE indicators
    known_schedulers = {"ISE", "SAME"}
    found = {s["scheduler_name"] for s in schedulers}
    for name in known_schedulers - found:
        expected = 300 if name == "ISE" else 60
        schedulers.append({
            "scheduler_name": name,
            "status": "OFFLINE",
            "last_tick_at": None,
            "expected_interval_seconds": expected,
            "drift_seconds": None,
            "cycle_result": {},
            "alive_threshold_multiplier": 1.5,
            "offline_threshold_multiplier": 3.0,
            "updated_at": None,
        })

    django_cache.set("wlj:ops:scheduler_heartbeats", schedulers, timeout=10)
    return schedulers


def _get_scheduler_health():
    """Get Celery Beat scheduling health for the Ops Wall stream."""
    try:
        from apps.core.scheduler_health import get_scheduler_status
        return get_scheduler_status()
    except Exception as e:
        logger.debug("OpsWall: Scheduler health unavailable: %s", e)
        return None


def _get_celery_health():
    """Get Celery execution layer health for the Ops Wall stream."""
    try:
        from apps.core.ai_observability.celery_health import get_celery_health
        return get_celery_health()
    except Exception as e:
        logger.debug("OpsWall: Celery health unavailable: %s", e)
        return None


def _get_coas_health():
    """Read latest COAS health snapshot (stored by scheduled job, not live recompute). Cached 30s."""
    cached = django_cache.get("wlj:ops:coas_health_view")
    if cached is not None:
        return cached

    try:
        from apps.core.ai_observability.models import COASHealthSnapshot

        snap = COASHealthSnapshot.objects.first()
        if not snap:
            return None
        result = {
            "scheduler": {"score": snap.scheduler_score},
            "engine": {"score": snap.engine_score},
            "freshness": {"score": snap.freshness_score},
            "overall": {"score": snap.overall_score},
            "computed_at": snap.computed_at.isoformat(),
            "details": snap.details,
        }
        django_cache.set("wlj:ops:coas_health_view", result, timeout=30)
        return result
    except Exception as e:
        logger.debug("OpsWall: COAS health unavailable: %s", e)
        return None


def _get_aafr_metrics():
    """
    Compute AI Action Failure Rate metrics for 5m, 1h, and 24h windows.
    Cached 30s — ~7 queries across 3 time windows + top errors.

    Returns success rate as the hero metric, with blocked and failed counts
    surfaced separately so safety blocks don't inflate the failure signal.
    Status is based on the 1h failure rate (excludes blocked).
    """
    cached = django_cache.get("wlj:ops:aafr_metrics")
    if cached is not None:
        return cached

    try:
        from django.db.models import Count, Q
        from apps.core.ai_observability.models import AIActionMetric

        now = timezone.now()
        windows = {
            "5m": now - timedelta(minutes=5),
            "1h": now - timedelta(hours=1),
            "24h": now - timedelta(hours=24),
        }

        result = {}
        for label, cutoff in windows.items():
            qs = AIActionMetric.objects.filter(created_at__gte=cutoff)
            total = qs.count()
            success_count = qs.filter(outcome="success").count()
            blocked_count = qs.filter(outcome="blocked").count()
            failed_count = qs.filter(outcome="failure").count()
            success_rate = (success_count / total * 100) if total > 0 else 100.0
            failure_rate = (failed_count / total * 100) if total > 0 else 0.0
            result[label] = {
                "total": total,
                "success": success_count,
                "blocked": blocked_count,
                "failed": failed_count,
                "success_rate": round(success_rate, 1),
                "failure_rate": round(failure_rate, 2),
            }

        # Top failure categories (24h, failures only)
        categories = list(
            AIActionMetric.objects.filter(
                created_at__gte=windows["24h"],
                outcome="failure",
            )
            .values("error_category")
            .annotate(count=Count("id"))
            .order_by("-count")[:5]
        )
        result["top_errors"] = [
            {"category": c["error_category"] or "unknown", "count": c["count"]}
            for c in categories
        ]

        # Status based on 1h failure rate (excludes blocked)
        failure_rate_1h = result["1h"]["failure_rate"]
        if failure_rate_1h >= 3.0:
            result["status"] = "CRITICAL"
        elif failure_rate_1h >= 1.0:
            result["status"] = "WARNING"
        else:
            result["status"] = "HEALTHY"

        django_cache.set("wlj:ops:aafr_metrics", result, timeout=30)
        return result

    except Exception as e:
        logger.debug("OpsWall: AAFR metrics unavailable: %s", e)
        return None


def _get_eae_ops_telemetry(now):
    """
    Get EAE telemetry for the Operations Wall (Phase 8.8).
    Cached 30s — ~10 queries per call.

    Returns aggregate metrics across all users for monitoring EAE health.
    """
    cached = django_cache.get("wlj:ops:eae_telemetry")
    if cached is not None:
        return cached

    try:
        from apps.core.ai_eae.models import (
            EAEDecisionLog,
            EAEEscalationEvent,
            EAEOverride,
            EAEState,
        )
        from apps.core.ai_eae.constants import ESCALATION_CHOICES
        from django.db.models import Avg, Count, Max, Min

        last_1h = now - timedelta(hours=1)
        last_24h = now - timedelta(hours=24)

        # Decision metrics (last hour and last 24h)
        decisions_1h = EAEDecisionLog.objects.filter(
            created_at__gte=last_1h,
        ).aggregate(
            count=Count('id'),
            avg_duration_ms=Avg('arbitration_duration_ms'),
            max_duration_ms=Max('arbitration_duration_ms'),
            avg_surfaced=Avg('surfaced_count'),
            avg_suppressed=Avg('suppressed_count'),
        )

        decisions_24h = EAEDecisionLog.objects.filter(
            created_at__gte=last_24h,
        ).aggregate(
            count=Count('id'),
            avg_duration_ms=Avg('arbitration_duration_ms'),
        )

        # Escalation distribution (current state across all users)
        level_map = dict(ESCALATION_CHOICES)
        escalation_dist = {}
        for level, label in ESCALATION_CHOICES:
            count = EAEState.objects.filter(escalation_level=level).count()
            if count:
                escalation_dist[label] = count

        # Recent escalation events (last 24h)
        escalation_events_24h = EAEEscalationEvent.objects.filter(
            created_at__gte=last_24h,
        ).count()

        # Active overrides
        override_count = EAEOverride.objects.count()

        # Last arbitration across all users
        last_arb = EAEState.objects.aggregate(
            last=Max('last_arbitration_at'),
        )

        result = {
            'decisions_1h': {
                'count': decisions_1h['count'] or 0,
                'avg_duration_ms': round(decisions_1h['avg_duration_ms'] or 0, 1),
                'max_duration_ms': decisions_1h['max_duration_ms'] or 0,
                'avg_surfaced': round(decisions_1h['avg_surfaced'] or 0, 1),
                'avg_suppressed': round(decisions_1h['avg_suppressed'] or 0, 1),
            },
            'decisions_24h_count': decisions_24h['count'] or 0,
            'decisions_24h_avg_ms': round(decisions_24h['avg_duration_ms'] or 0, 1),
            'escalation_distribution': escalation_dist,
            'escalation_events_24h': escalation_events_24h,
            'active_overrides': override_count,
            'last_arbitration_at': (
                last_arb['last'].isoformat() if last_arb.get('last') else None
            ),
        }
        django_cache.set("wlj:ops:eae_telemetry", result, timeout=30)
        return result
    except Exception as e:
        logger.debug("OpsWall: EAE telemetry unavailable: %s", e)
        return None


def _human_ago(dt):
    """Convert datetime to human-readable 'X ago' string."""
    if not dt:
        return "unknown"
    seconds = int((timezone.now() - dt).total_seconds())
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def _get_learning_health(now):
    """
    Build learning health metrics for the Operations Wall.
    Cached 60s — ~20 queries across 5 subsystems. Data changes slowly.

    Monitors all 5 persistent learning subsystems and returns an overall
    status (LEARNING / DEGRADED / STALE) plus per-subsystem metrics.

    Status thresholds:
      LEARNING (green): ≥3 subsystems active in last 7 days
      DEGRADED (yellow): 1-2 subsystems active in last 7 days
      STALE (red): 0 subsystems active in last 7 days
    """
    cached = django_cache.get("wlj:ops:learning_health")
    if cached is not None:
        return cached

    try:
        from django.db.models import Avg, Count, Max, Sum

        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)
        last_30d = now - timedelta(days=30)

        subsystems = {}
        active_count = 0

        # --- Subsystem 1: Memory Storage ---
        try:
            from apps.ai.models import ConversationMemory

            mem_total = ConversationMemory.objects.count()
            mem_24h = ConversationMemory.objects.filter(
                created_at__gte=last_24h,
            ).count()
            mem_7d = ConversationMemory.objects.filter(
                created_at__gte=last_7d,
            ).count()
            mem_last = ConversationMemory.objects.order_by(
                '-created_at',
            ).values_list('created_at', flat=True).first()

            # Memories with non-zero helpfulness (feedback closed the loop)
            mem_with_feedback = ConversationMemory.objects.exclude(
                helpfulness_score=0.0,
            ).count()

            has_activity = mem_7d > 0
            if has_activity:
                active_count += 1

            subsystems['memory'] = {
                'status': 'ACTIVE' if has_activity else 'STALE',
                'total': mem_total,
                'last_24h': mem_24h,
                'last_7d': mem_7d,
                'with_feedback': mem_with_feedback,
                'last_stored_at': mem_last.isoformat() if mem_last else None,
            }
        except Exception as e:
            logger.debug("Learning health: memory check failed: %s", e)
            subsystems['memory'] = {'status': 'ERROR', 'error': str(e)[:100]}

        # --- Subsystem 2: Corrections ---
        try:
            from apps.ai.models import CorrectionRecord

            corr_total = CorrectionRecord.objects.count()
            corr_7d = CorrectionRecord.objects.filter(
                created_at__gte=last_7d,
            ).count()
            corr_last = CorrectionRecord.objects.order_by(
                '-created_at',
            ).values_list('created_at', flat=True).first()

            # Corrections are rare — active if any exist in 30 days
            has_activity = CorrectionRecord.objects.filter(
                created_at__gte=last_30d,
            ).exists()
            if has_activity:
                active_count += 1

            subsystems['corrections'] = {
                'status': 'ACTIVE' if has_activity else ('IDLE' if corr_total == 0 else 'STALE'),
                'total': corr_total,
                'last_7d': corr_7d,
                'last_stored_at': corr_last.isoformat() if corr_last else None,
            }
        except Exception as e:
            logger.debug("Learning health: corrections check failed: %s", e)
            subsystems['corrections'] = {'status': 'ERROR', 'error': str(e)[:100]}

        # --- Subsystem 3: Behavioral Patterns ---
        try:
            from apps.ai.models import BehavioralPattern

            pat_total = BehavioralPattern.objects.count()
            pat_active = BehavioralPattern.objects.filter(is_active=True).count()
            pat_confirmed = BehavioralPattern.objects.filter(
                user_confirmed=True,
            ).count()
            pat_denied = BehavioralPattern.objects.filter(
                user_confirmed=False,
            ).count()
            pat_pending = BehavioralPattern.objects.filter(
                user_confirmed__isnull=True,
                is_active=True,
            ).count()
            pat_avg_confidence = BehavioralPattern.objects.filter(
                is_active=True,
            ).aggregate(avg=Avg('confidence'))['avg']

            has_activity = pat_active > 0
            if has_activity:
                active_count += 1

            subsystems['patterns'] = {
                'status': 'ACTIVE' if has_activity else 'IDLE',
                'total': pat_total,
                'active': pat_active,
                'confirmed': pat_confirmed,
                'denied': pat_denied,
                'pending': pat_pending,
                'avg_confidence': round(pat_avg_confidence * 100) if pat_avg_confidence else 0,
            }
        except Exception as e:
            logger.debug("Learning health: patterns check failed: %s", e)
            subsystems['patterns'] = {'status': 'ERROR', 'error': str(e)[:100]}

        # --- Subsystem 4: Response Preferences ---
        try:
            from apps.ai.models import ResponsePreference

            pref_count = ResponsePreference.objects.count()
            pref_agg = ResponsePreference.objects.aggregate(
                total_helpful=Sum('helpful_count'),
                total_unhelpful=Sum('unhelpful_count'),
            )
            total_feedback = (
                (pref_agg['total_helpful'] or 0)
                + (pref_agg['total_unhelpful'] or 0)
            )

            has_activity = total_feedback > 0
            if has_activity:
                active_count += 1

            subsystems['response_prefs'] = {
                'status': 'ACTIVE' if has_activity else 'IDLE',
                'users_with_prefs': pref_count,
                'total_feedback': total_feedback,
                'helpful': pref_agg['total_helpful'] or 0,
                'unhelpful': pref_agg['total_unhelpful'] or 0,
            }
        except Exception as e:
            logger.debug("Learning health: response prefs check failed: %s", e)
            subsystems['response_prefs'] = {'status': 'ERROR', 'error': str(e)[:100]}

        # --- Subsystem 5: Profile Evolution ---
        try:
            from apps.core.ai_learning.models import UserLearnedProfile

            profile_count = UserLearnedProfile.objects.count()
            # Count total items across all profiles
            total_items = 0
            evolved_items = 0  # Items in dict format (evolved)
            profiles = UserLearnedProfile.objects.all()
            for p in profiles:
                for field_name in [
                    'stated_values', 'repeated_frustrations', 'recurring_goals',
                    'preferred_communication', 'known_routines', 'spiritual_notes',
                    'health_context', 'relationship_notes', 'work_context',
                    'emotional_patterns', 'motivators', 'self_identified_weaknesses',
                    'life_season',
                ]:
                    items = getattr(p, field_name, []) or []
                    if isinstance(items, list):
                        total_items += len(items)
                        evolved_items += sum(
                            1 for i in items if isinstance(i, dict)
                        )

            has_activity = profile_count > 0 and total_items > 0
            if has_activity:
                active_count += 1

            subsystems['profile'] = {
                'status': 'ACTIVE' if has_activity else 'IDLE',
                'profiles': profile_count,
                'total_items': total_items,
                'evolved_items': evolved_items,
                'evolution_pct': (
                    round(evolved_items / total_items * 100)
                    if total_items > 0 else 0
                ),
            }
        except Exception as e:
            logger.debug("Learning health: profile check failed: %s", e)
            subsystems['profile'] = {'status': 'ERROR', 'error': str(e)[:100]}

        # --- Overall Status ---
        error_count = sum(
            1 for s in subsystems.values() if s.get('status') == 'ERROR'
        )
        if error_count >= 3:
            overall = 'STALE'
        elif active_count >= 3:
            overall = 'LEARNING'
        elif active_count >= 1:
            overall = 'DEGRADED'
        else:
            overall = 'STALE'

        result = {
            'status': overall,
            'active_subsystems': active_count,
            'total_subsystems': 5,
            'subsystems': subsystems,
        }
        django_cache.set("wlj:ops:learning_health", result, timeout=60)
        return result

    except Exception as e:
        logger.debug("Learning health check failed: %s", e)
        return {
            'status': 'STALE',
            'active_subsystems': 0,
            'total_subsystems': 5,
            'subsystems': {},
            'error': str(e)[:200],
        }


def _get_health_intelligence_telemetry(now):
    """
    Build Health Intelligence Engine telemetry for the Operations Wall.
    Cached 60s — ~20 queries across multiple models. Data changes slowly.

    Monitors DailyHealthSummary freshness, data completeness, body comp
    coverage, health scores, and HealthKit ingestion pipeline health.

    Status thresholds:
      OK (green): latest summary ≤ 36h old
      STALE (yellow): latest summary > 36h old
      ERROR (red): no summaries exist or exception
    """
    cached = django_cache.get("wlj:ops:health_intel_telemetry")
    if cached is not None:
        return cached

    try:
        from django.contrib.auth import get_user_model
        from django.db.models import Avg, Count, Max

        from apps.health.models import DailyHealthSummary

        User = get_user_model()
        last_7d = now - timedelta(days=7)
        last_24h = now - timedelta(hours=24)
        last_36h = now - timedelta(hours=36)

        # --- Summary freshness ---
        latest = DailyHealthSummary.objects.aggregate(
            latest_date=Max('summary_date'),
            latest_updated=Max('updated_at'),
        )
        latest_date = latest.get('latest_date')
        latest_updated = latest.get('latest_updated')

        if latest_updated:
            age_str = _human_ago(latest_updated)
            is_stale = latest_updated < last_36h
        else:
            age_str = "never"
            is_stale = True

        # --- Active user coverage (7d) ---
        active_users = User.objects.filter(is_active=True).count()
        users_with_summaries_7d = (
            DailyHealthSummary.objects
            .filter(summary_date__gte=last_7d.date())
            .values('user')
            .distinct()
            .count()
        )

        # --- Data completeness (7d average) ---
        completeness_agg = (
            DailyHealthSummary.objects
            .filter(summary_date__gte=last_7d.date())
            .aggregate(avg_completeness=Avg('data_completeness_pct'))
        )
        avg_completeness = completeness_agg.get('avg_completeness')
        if avg_completeness is not None:
            avg_completeness = round(float(avg_completeness), 1)

        # --- Health & Recovery scores (7d average) ---
        score_agg = (
            DailyHealthSummary.objects
            .filter(
                summary_date__gte=last_7d.date(),
                health_score__isnull=False,
            )
            .aggregate(
                avg_health=Avg('health_score'),
                avg_recovery=Avg('recovery_score'),
            )
        )
        avg_health = round(score_agg['avg_health']) if score_agg.get('avg_health') else None
        avg_recovery = round(score_agg['avg_recovery']) if score_agg.get('avg_recovery') else None

        # --- Body composition coverage (7d) ---
        # Users with fat_loss_quality_label computed (needs multi-day data)
        body_comp_users = (
            DailyHealthSummary.objects
            .filter(
                summary_date__gte=last_7d.date(),
                fat_loss_quality_label__isnull=False,
            )
            .exclude(fat_loss_quality_label="")
            .values('user')
            .distinct()
            .count()
        )
        # Users with raw body comp data (weight + body_fat from HealthKit)
        from apps.health.models import WeightEntry
        body_comp_raw_users = (
            WeightEntry.objects
            .filter(
                recorded_at__date__gte=last_7d.date(),
                body_fat_percentage__isnull=False,
            )
            .values('user')
            .distinct()
            .count()
        )

        # --- Signals breakdown (latest summaries per user) ---
        total_summaries_7d = (
            DailyHealthSummary.objects
            .filter(summary_date__gte=last_7d.date())
            .count()
        )

        # --- HealthKit ingestion stats (24h) ---
        ingestion_stats = _get_ingestion_stats(last_24h)

        # --- Overall status ---
        if latest_date is None:
            status = "ERROR"
        elif is_stale:
            status = "STALE"
        else:
            status = "OK"

        # --- Nightly task metrics (24h) ---
        summaries_built_24h = (
            DailyHealthSummary.objects
            .filter(updated_at__gte=last_24h)
            .count()
        )
        users_processed_24h = (
            DailyHealthSummary.objects
            .filter(updated_at__gte=last_24h)
            .values('user')
            .distinct()
            .count()
        )
        # Oldest active user without a recent (7d) summary
        from django.db.models import Subquery
        users_with_recent = (
            DailyHealthSummary.objects
            .filter(summary_date__gte=last_7d.date())
            .values_list('user_id', flat=True)
            .distinct()
        )
        oldest_missing = (
            User.objects
            .filter(is_active=True)
            .exclude(id__in=Subquery(users_with_recent))
            .order_by('date_joined')
            .values_list('email', flat=True)
            .first()
        )

        result = {
            'status': status,
            'latest_summary_date': str(latest_date) if latest_date else None,
            'latest_updated_age': age_str,
            'active_users': active_users,
            'users_with_summaries_7d': users_with_summaries_7d,
            'avg_completeness_7d': avg_completeness,
            'total_summaries_7d': total_summaries_7d,
            'body_comp_users_7d': body_comp_users,
            'body_comp_raw_users_7d': body_comp_raw_users,
            'scores': {
                'avg_health_7d': avg_health,
                'avg_recovery_7d': avg_recovery,
            },
            'ingestion_24h': ingestion_stats,
            'nightly_task': {
                'summaries_built_24h': summaries_built_24h,
                'users_processed_24h': users_processed_24h,
                'oldest_missing_user': oldest_missing,
            },
        }
        django_cache.set("wlj:ops:health_intel_telemetry", result, timeout=60)
        return result

    except Exception as e:
        logger.debug("Health intelligence telemetry failed: %s", e)
        return {
            'status': 'ERROR',
            'error': str(e)[:200],
        }


def _get_ingestion_stats(since):
    """Get HealthKit ingestion pipeline stats since a given datetime."""
    try:
        from collections import Counter

        from django.db.models import Sum

        from apps.mobile.models import HealthIngestionRun

        runs = HealthIngestionRun.objects.filter(request_timestamp__gte=since)
        total_runs = runs.count()
        if total_runs == 0:
            return {'runs': 0, 'metrics_ingested': 0, 'error_rate': 0.0}

        agg = runs.aggregate(
            total_created=Sum('metrics_created'),
            total_updated=Sum('metrics_updated'),
            total_skipped=Sum('metrics_skipped'),
            total_received=Sum('metrics_received'),
        )
        total_created = agg.get('total_created') or 0
        total_updated = agg.get('total_updated') or 0
        total_skipped = agg.get('total_skipped') or 0
        total_received = agg.get('total_received') or 0

        # Count runs with partial/failed status
        error_runs = runs.filter(status__in=['partial', 'failed']).count()

        # Aggregate validation errors for diagnostics.
        # metrics_skipped conflates legitimate dedup skips and real errors.
        # Count actual errors from validation_errors JSON to separate them.
        total_actual_errors = 0
        error_by_type = Counter()
        error_samples = {}  # type -> first error message
        for run in runs.filter(validation_errors__isnull=False).exclude(validation_errors=[]):
            run_errors = run.validation_errors or []
            total_actual_errors += len(run_errors)
            for err in run_errors:
                mtype = err.get('type', 'unknown')
                error_by_type[mtype] += 1
                if mtype not in error_samples:
                    error_samples[mtype] = err.get('error', '')[:120]

        # True skip count = total_skipped (which includes errors) - actual errors
        true_skips = max(0, total_skipped - total_actual_errors)

        # Error rate = actual errors / received (not skips / received)
        error_rate = (
            round(total_actual_errors / total_received * 100, 1)
            if total_received > 0 else 0.0
        )
        # Skip rate = dedup skips / received (informational)
        skip_rate = (
            round(true_skips / total_received * 100, 1)
            if total_received > 0 else 0.0
        )

        # Build top errors list (sorted by count desc)
        top_errors = [
            {'type': t, 'count': c, 'sample': error_samples.get(t, '')}
            for t, c in error_by_type.most_common(10)
        ]

        return {
            'runs': total_runs,
            'metrics_ingested': total_created + total_updated,
            'metrics_skipped': true_skips,
            'total_received': total_received,
            'error_rate': error_rate,
            'skip_rate': skip_rate,
            'actual_errors': total_actual_errors,
            'error_runs': error_runs,
            'top_errors': top_errors,
        }
    except Exception:
        return {'runs': 0, 'metrics_ingested': None, 'error_rate': None}


def _get_complexity_score():
    """
    Return the System Complexity Score for the Operations Wall.

    Cached for 10 minutes — this scans the filesystem and should not
    run on every 2s poll cycle.

    Returns dict with score (0-10), grade (A-F), dimension breakdown,
    and aggregated warnings.  Returns None if computation fails.
    """
    try:
        from django.core.cache import cache

        cache_key = "wlj:ops:complexity_score"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        from apps.core.observability.complexity_metrics import compute_complexity_score

        result = compute_complexity_score()
        cache.set(cache_key, result, timeout=600)  # 10 min cache
        return result
    except Exception as e:
        logger.debug("OpsWall: complexity score unavailable: %s", e)
        return None


def _get_domain_event_telemetry():
    """Domain event bus statistics for the Operations Wall."""
    try:
        from apps.core.events.domain_events import get_event_bus_stats

        stats = get_event_bus_stats()

        from django.core.cache import cache

        daily_count = cache.get("wlj:domain_events:daily_count", 0)

        return {
            "total_emitted": stats.get("total_events_emitted", 0),
            "suppressed": stats.get("suppressed_count", 0),
            "registered_patterns": stats.get("registered_patterns", 0),
            "total_handlers": stats.get("total_handlers", 0),
            "avg_handler_ms": stats.get("avg_handler_ms", 0),
            "p95_handler_ms": stats.get("p95_handler_ms", 0),
            "type_counts": stats.get("type_counts", {}),
            "daily_count": daily_count,
        }
    except Exception as e:
        logger.debug("OpsWall: domain event telemetry unavailable: %s", e)
        return None


def _get_chat_latency_telemetry(now):
    """
    Chat response latency metrics for the Operations Wall.
    Cached 30s — aggregates over 20 recent snapshots.

    Aggregates recent ChatLatencySnapshot records to show:
    - Average total response time
    - Average per-stage breakdown
    - Recent sample count
    - Slowest stages (for bottleneck identification)
    """
    cached = django_cache.get("wlj:ops:chat_latency")
    if cached is not None:
        return cached

    try:
        from apps.core.ai_observability.models import ChatLatencySnapshot
        from django.db.models import Avg, Count, Max

        window = now - timedelta(hours=24)
        qs = ChatLatencySnapshot.objects.filter(created_at__gte=window)
        stats = qs.aggregate(
            count=Count('id'),
            avg_total=Avg('total_ms'),
            max_total=Max('total_ms'),
        )

        if not stats['count']:
            return {
                'count': 0,
                'avg_total_ms': None,
                'max_total_ms': None,
                'avg_stages': {},
            }

        # Compute average per-stage latency from the JSON stages field
        # Sample the last 20 snapshots for stage breakdown (avoid heavy scan)
        recent = list(qs.order_by('-created_at').values('stages', 'meta')[:20])
        stage_totals = {}
        stage_counts = {}
        token_totals = {'prompt_tokens': 0, 'completion_tokens': 0}
        token_count = 0
        for snap in recent:
            stages = snap.get('stages') or {}
            for label, dur in stages.items():
                if dur is not None:
                    stage_totals[label] = stage_totals.get(label, 0) + dur
                    stage_counts[label] = stage_counts.get(label, 0) + 1
            meta = snap.get('meta') or {}
            if meta.get('prompt_tokens'):
                token_totals['prompt_tokens'] += meta['prompt_tokens']
                token_totals['completion_tokens'] += meta.get('completion_tokens', 0)
                token_count += 1

        avg_stages = {}
        for label in stage_totals:
            avg_stages[label] = round(stage_totals[label] / stage_counts[label], 1)

        # Sort by duration descending (slowest first)
        avg_stages = dict(sorted(avg_stages.items(), key=lambda x: x[1], reverse=True))

        avg_tokens = {}
        if token_count:
            avg_tokens = {
                'avg_prompt_tokens': round(token_totals['prompt_tokens'] / token_count),
                'avg_completion_tokens': round(token_totals['completion_tokens'] / token_count),
            }

        # Token governance stats from _governance and _token_report in meta
        intent_bypass_count = 0
        intent_total = 0
        framework_skip_count = 0
        framework_total = 0
        token_report_totals = {}
        token_report_count = 0
        for snap in recent:
            meta = snap.get('meta') or {}
            governance = meta.get('_governance') or []
            intent_total += 1
            if 'intent_bypassed' in governance:
                intent_bypass_count += 1
            framework_total += 1
            if any(g.startswith('framework_skipped') for g in governance):
                framework_skip_count += 1
            tr = meta.get('_token_report')
            if tr:
                token_report_count += 1
                for comp, count in tr.items():
                    token_report_totals[comp] = token_report_totals.get(comp, 0) + count

        governance_stats = {}
        if intent_total:
            governance_stats['intent_bypass_rate'] = round(
                intent_bypass_count / intent_total * 100, 1
            )
        if framework_total:
            governance_stats['framework_skip_rate'] = round(
                framework_skip_count / framework_total * 100, 1
            )
        if token_report_count:
            governance_stats['avg_token_breakdown'] = {
                comp: round(total / token_report_count)
                for comp, total in sorted(
                    token_report_totals.items(), key=lambda x: -x[1]
                )
            }

        result = {
            'count': stats['count'],
            'avg_total_ms': round(stats['avg_total'] or 0, 0),
            'max_total_ms': round(stats['max_total'] or 0, 0),
            'avg_stages': avg_stages,
            'avg_tokens': avg_tokens,
            'governance': governance_stats,
        }
        django_cache.set("wlj:ops:chat_latency", result, timeout=30)
        return result
    except Exception as e:
        logger.debug("OpsWall: chat latency telemetry unavailable: %s", e)
        return None


def _get_signal_health():
    """
    Read cached signal health snapshot for the polling endpoint.

    Signal health is computed and cached by the SAME engine on its 60s cadence.
    Returns None if cache is empty — callers must handle gracefully.

    WARNING: Do NOT fall back to compute_signal_health() here. That function
    runs multiple DB queries and will block Gunicorn workers if called on
    every polling cycle (especially when Redis is unreachable and cache.get
    always returns None). The SAME engine will populate the cache within 60s.
    """
    try:
        from django.core.cache import cache

        cached = cache.get("wlj:ops:signal_health")
        if cached is not None:
            return cached

        return None
    except Exception as e:
        logger.debug("Signal health unavailable: %s", e)
        return None


def compute_signal_health():
    """
    Compute signal health diagnostics across intelligence domains.

    Queries Insight, Prediction, GuidanceItem, and JournalSignal models
    grouped by domain/module to compute per-domain metrics:
      - freshness: MAX created_at (most recent signal)
      - freshness_hours: hours since most recent signal
      - volume_24h: COUNT signals in last 24 hours
      - volume_7d: COUNT signals in last 7 days
      - distinct_types_7d: COUNT DISTINCT signal types in last 7 days
      - status: healthy / stale / silent (based on freshness + diversity)

    Status thresholds:
      healthy: freshness < 24h AND distinct_types_7d >= 2
      stale: freshness 24h–72h OR distinct_types_7d == 1
      silent: freshness > 72h OR volume_7d == 0

    Returns:
        dict with keys: domains_active, domains_silent, stalest_domain,
        stalest_hours, domains (per-domain breakdown)
    """
    from django.db.models import Count, Max

    now = timezone.now()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    # Seed from domain registry — only signal-eligible domains.
    # A domain is signal-eligible if:
    #   1. domain_class is BEHAVIORAL (excludes INFLUENCE/KNOWLEDGE/CONTEXT/SYSTEM)
    #   2. expected_signal_types is non-empty (excludes feeder domains like meals/medical)
    #   3. At least one signal type is not stubbed (excludes coming_soon like finance)
    domain_data = {}  # domain -> {last_signal_at, volume_24h, volume_7d, types_7d}

    try:
        from apps.core.domain_registry.registry import registry as domain_registry
        from apps.core.domain_registry.descriptors import DomainClass
        from apps.core.ai_eae.signal_aggregation import STUBBED_SIGNAL_TYPES

        for domain_name in domain_registry.get_names():
            cap = domain_registry.get(domain_name)
            if not cap:
                continue
            if cap.domain_class != DomainClass.BEHAVIORAL:
                continue
            if not cap.expected_signal_types:
                continue
            active_types = [t for t in cap.expected_signal_types
                           if t not in STUBBED_SIGNAL_TYPES]
            if not active_types:
                continue
            domain_data[domain_name.lower()] = {
                "last_signal_at": None,
                "volume_24h": 0,
                "volume_7d": 0,
                "types_7d": set(),
            }
    except Exception as e:
        logger.debug("Signal health: domain registry seed failed: %s", e)

    def _merge_domain(domain, last_at, count_24h, count_7d, types_7d):
        """Merge a model's aggregation into the domain_data dict."""
        if not domain:
            return
        domain = domain.lower()
        # Skip legacy domains — standardized names
        if domain in ("goals", "mind"):
            return
        if domain not in domain_data:
            domain_data[domain] = {
                "last_signal_at": None,
                "volume_24h": 0,
                "volume_7d": 0,
                "types_7d": set(),
            }
        d = domain_data[domain]
        if last_at and (d["last_signal_at"] is None or last_at > d["last_signal_at"]):
            d["last_signal_at"] = last_at
        d["volume_24h"] += count_24h or 0
        d["volume_7d"] += count_7d or 0
        if types_7d:
            d["types_7d"].update(types_7d)

    # Helper to run a single aggregated query per model (eliminates N+1)
    from django.db.models import Q as models_Q

    def _query_model(model_class, group_field, type_field, label):
        """Single query per model: GROUP BY domain, aggregate all metrics."""
        try:
            aggs = (
                model_class.objects.filter(**{f"{group_field}__isnull": False})
                .exclude(**{group_field: ""})
                .values(group_field)
                .annotate(
                    last_at=Max("created_at"),
                    vol_24h=Count("id", filter=models_Q(created_at__gte=last_24h)),
                    vol_7d=Count("id", filter=models_Q(created_at__gte=last_7d)),
                )
            )
            for row in aggs:
                domain_val = row[group_field]
                # Get distinct types in 7d (one extra query per domain but bounded)
                types_7d = set()
                if type_field:
                    types_7d = set(
                        model_class.objects.filter(
                            **{group_field: domain_val},
                            created_at__gte=last_7d,
                        )
                        .values_list(type_field, flat=True)
                        .distinct()
                    )
                _merge_domain(
                    domain_val, row["last_at"],
                    row["vol_24h"], row["vol_7d"], types_7d
                )
        except Exception as e:
            logger.debug("Signal health: %s query failed: %s", label, e)

    # --- Insight model (module field) ---
    try:
        from apps.core.ai_insights.models import Insight
        _query_model(Insight, "module", "insight_type", "Insight")
    except ImportError:
        pass

    # --- Prediction model (module field) ---
    try:
        from apps.core.ai_predictions.models import Prediction
        _query_model(Prediction, "module", "prediction_type", "Prediction")
    except ImportError:
        pass

    # --- GuidanceItem model (module field) ---
    try:
        from apps.core.ai_guidance.models import GuidanceItem
        _query_model(GuidanceItem, "module", "guidance_type", "GuidanceItem")
    except ImportError:
        pass

    # --- JournalSignal model (domain field, signal_type) ---
    try:
        from apps.journal.models import JournalSignal
        _query_model(JournalSignal, "domain", "signal_type", "JournalSignal")
    except ImportError:
        pass

    # --- Build per-domain results ---
    domains_active = 0
    domains_silent = 0
    stalest_domain = None
    stalest_hours = 0.0
    domains_result = {}

    for domain, data in sorted(domain_data.items()):
        last_at = data["last_signal_at"]
        if last_at:
            freshness_hours = round(
                (now - last_at).total_seconds() / 3600, 1
            )
        else:
            freshness_hours = None

        volume_24h = data["volume_24h"]
        volume_7d = data["volume_7d"]
        distinct_types = len(data["types_7d"])

        # Determine status
        # Distinguish "never_active" (domain has NEVER produced signals) from
        # "silent" (domain WAS active and stopped).  never_active domains
        # don't count against overall health — they just haven't been used yet.
        if freshness_hours is None and volume_7d == 0:
            status = "never_active"
        elif volume_7d == 0:
            status = "silent"
        elif freshness_hours is not None and freshness_hours > 72:
            status = "silent"
        elif freshness_hours is not None and freshness_hours > 24 or distinct_types < 2:
            status = "stale"
        else:
            status = "healthy"

        if status == "silent":
            domains_silent += 1
        elif status != "never_active":
            domains_active += 1
        # never_active domains excluded from both counts

        # Track stalest domain
        if freshness_hours is not None and freshness_hours > stalest_hours:
            stalest_hours = freshness_hours
            stalest_domain = domain

        domains_result[domain] = {
            "last_signal_at": last_at.isoformat() if last_at else None,
            "freshness_hours": freshness_hours,
            "volume_24h": volume_24h,
            "volume_7d": volume_7d,
            "distinct_types_7d": distinct_types,
            "status": status,
        }

    # Compute total volume (7d) across all domains
    total_volume_7d = sum(d["volume_7d"] for d in domains_result.values())

    # Determine top-level status for the frontend card
    total_domains = len(domains_result)
    if total_domains == 0:
        overall_status = "no_data"
    elif domains_silent == 0:
        overall_status = "healthy"
    elif domains_active > 0:
        overall_status = "degraded"
    else:
        overall_status = "critical"

    return {
        "status": overall_status,
        "domains_active": domains_active,
        "domains_silent": domains_silent,
        "stalest_domain": stalest_domain,
        "stalest_hours": round(stalest_hours, 1),
        "total_volume_7d": total_volume_7d,
        "domains": domains_result,
    }


def _get_validator_health():
    """
    Read cached validator health snapshot for the polling endpoint.

    Validator health is computed and cached by the SAME engine on its 60s cadence.
    Returns None if cache is empty (avoids expensive live computation on request path).
    """
    try:
        from django.core.cache import cache

        cached = cache.get("wlj:ops:validator_health")
        if cached is not None:
            return cached

        # No fallback — return None until SAME populates cache (avoids query storms)
        return None
    except Exception as e:
        logger.debug("Validator health unavailable: %s", e)
        return None


def compute_validator_health():
    """
    Compute validator gate health metrics from ValidatorMetric records.

    Aggregates pass/block/observe/crash rates over three windows:
      - 1h: real-time operational view
      - 24h: daily trend
      - 7d: weekly trend

    Returns:
        dict with keys: total_1h, total_24h, total_7d, block_rate_1h,
        block_rate_24h, block_rate_7d, crash_count_24h, avg_duration_ms,
        by_policy_24h, status
    """
    from django.db.models import Avg, Count

    now = timezone.now()
    last_1h = now - timedelta(hours=1)
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    try:
        from apps.core.ai_observability.models import ValidatorMetric

        # --- 1h window ---
        qs_1h = ValidatorMetric.objects.filter(created_at__gte=last_1h)
        total_1h = qs_1h.count()
        blocks_1h = qs_1h.filter(outcome="block").count()
        block_rate_1h = round(blocks_1h / total_1h, 3) if total_1h > 0 else 0.0

        # --- 24h window ---
        qs_24h = ValidatorMetric.objects.filter(created_at__gte=last_24h)
        total_24h = qs_24h.count()
        blocks_24h = qs_24h.filter(outcome="block").count()
        crashes_24h = qs_24h.filter(outcome="crash").count()
        block_rate_24h = round(blocks_24h / total_24h, 3) if total_24h > 0 else 0.0

        # --- 7d window ---
        qs_7d = ValidatorMetric.objects.filter(created_at__gte=last_7d)
        total_7d = qs_7d.count()
        blocks_7d = qs_7d.filter(outcome="block").count()
        block_rate_7d = round(blocks_7d / total_7d, 3) if total_7d > 0 else 0.0

        # Average duration
        avg_dur = qs_24h.aggregate(avg=Avg("duration_ms"))["avg"] or 0

        # By policy (24h)
        by_policy = {}
        policy_counts = (
            qs_24h.exclude(policy="none")
            .values("policy")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        for row in policy_counts:
            by_policy[row["policy"]] = row["count"]

        # Status determination
        # healthy: block_rate_1h < 5% and no crashes
        # degraded: block_rate_1h 5-20% or crashes present
        # critical: block_rate_1h > 20% or multiple crashes
        if total_1h == 0:
            status = "no_data"
        elif crashes_24h >= 2 or block_rate_1h > 0.20:
            status = "critical"
        elif crashes_24h >= 1 or block_rate_1h > 0.05:
            status = "degraded"
        else:
            status = "healthy"

        return {
            "total_1h": total_1h,
            "total_24h": total_24h,
            "total_7d": total_7d,
            "blocks_1h": blocks_1h,
            "blocks_24h": blocks_24h,
            "block_rate_1h": block_rate_1h,
            "block_rate_24h": block_rate_24h,
            "block_rate_7d": block_rate_7d,
            "crash_count_24h": crashes_24h,
            "avg_duration_ms": round(avg_dur, 1),
            "by_policy_24h": by_policy,
            "status": status,
        }
    except Exception as e:
        logger.debug("Validator health computation failed: %s", e)
        return None


def _get_cos_performance():
    """
    Read cached CoS performance snapshot for the polling endpoint.

    CoS performance is computed and cached by the SAME engine on its 60s cadence.
    Returns None if cache is empty (avoids expensive live computation on request path).
    """
    try:
        from django.core.cache import cache

        cached = cache.get("wlj:ops:cos_performance")
        if cached is not None:
            return cached

        # No fallback — return None until SAME populates cache (avoids query storms)
        return None
    except Exception as e:
        logger.debug("CoS performance unavailable: %s", e)
        return None


def compute_cos_performance():
    """
    Compute CoS (Context of Situation) performance metrics from ChatLatencySnapshot.

    Aggregates context build latency, TTFT, token usage, cache hit rate,
    and per-builder timing breakdown from the last 24h of snapshots.

    Metrics produced:
      - p50_context_build_ms: median COS_CONTEXT_BUILD_TOTAL
      - p95_context_build_ms: 95th percentile COS_CONTEXT_BUILD_TOTAL
      - p95_ttft_ms: 95th percentile LLM_REQUEST time (time to first token proxy)
      - cache_hit_rate: fraction of requests where context build < 100ms (cache hit)
      - avg_prompt_tokens: average prompt token count
      - avg_total_ms: average end-to-end response time
      - sample_count_24h: number of snapshots in window
      - slowest_builders: top 5 context builders by avg duration

    Returns:
        dict or None
    """
    now = timezone.now()
    last_24h = now - timedelta(hours=24)

    try:
        from apps.core.ai_observability.models import ChatLatencySnapshot

        qs = ChatLatencySnapshot.objects.filter(created_at__gte=last_24h)
        count = qs.count()

        if count == 0:
            return {
                "sample_count_24h": 0,
                "p50_context_build_ms": None,
                "p95_context_build_ms": None,
                "p95_ttft_ms": None,
                "cache_hit_rate": None,
                "avg_prompt_tokens": None,
                "avg_total_ms": None,
                "slowest_builders": [],
                "status": "no_data",
            }

        # Fetch recent snapshots (cap at 200 for performance)
        snapshots = list(
            qs.order_by("-created_at")
            .values("stages", "meta", "total_ms")[:200]
        )

        # Extract COS_CONTEXT_BUILD_TOTAL and LLM_REQUEST durations
        context_build_times = []
        llm_request_times = []
        prompt_tokens_list = []
        total_ms_list = []
        cache_hits = 0
        builder_totals = {}  # builder_name -> [durations]

        for snap in snapshots:
            stages = snap.get("stages") or {}
            meta = snap.get("meta") or {}

            # Context build time
            cos_total = stages.get("COS_CONTEXT_BUILD_TOTAL")
            if cos_total is not None:
                context_build_times.append(cos_total)
                # Cache hit heuristic: context build < 100ms means cache was used
                if cos_total < 100:
                    cache_hits += 1

            # LLM request time (TTFT proxy)
            llm_time = stages.get("LLM_REQUEST")
            if llm_time is not None:
                llm_request_times.append(llm_time)

            # Total ms
            total = snap.get("total_ms")
            if total is not None:
                total_ms_list.append(total)

            # Prompt tokens
            pt = meta.get("prompt_tokens")
            if pt:
                prompt_tokens_list.append(pt)

            # Per-builder timing
            for key, dur in stages.items():
                if key.startswith("COS_BUILDER_") and dur is not None:
                    name = key[len("COS_BUILDER_"):]
                    if name not in builder_totals:
                        builder_totals[name] = []
                    builder_totals[name].append(dur)

        def _percentile(values, pct):
            """Compute percentile from sorted values."""
            if not values:
                return None
            sorted_v = sorted(values)
            idx = max(0, int(len(sorted_v) * pct / 100) - 1)
            return round(sorted_v[idx], 1)

        p50_build = _percentile(context_build_times, 50)
        p95_build = _percentile(context_build_times, 95)
        p95_ttft = _percentile(llm_request_times, 95)

        # Cache hit rate
        total_with_build = len(context_build_times)
        cache_hit_rate = (
            round(cache_hits / total_with_build, 3)
            if total_with_build > 0
            else None
        )

        # Average prompt tokens
        avg_prompt = (
            round(sum(prompt_tokens_list) / len(prompt_tokens_list))
            if prompt_tokens_list
            else None
        )

        # Average total ms
        avg_total = (
            round(sum(total_ms_list) / len(total_ms_list), 0)
            if total_ms_list
            else None
        )

        # Slowest builders (by average duration, top 5)
        slowest_builders = []
        for name, durations in builder_totals.items():
            avg = sum(durations) / len(durations)
            slowest_builders.append({
                "name": name,
                "avg_ms": round(avg, 1),
                "sample_count": len(durations),
            })
        slowest_builders.sort(key=lambda x: x["avg_ms"], reverse=True)
        slowest_builders = slowest_builders[:5]

        # Status determination
        if p95_build is not None and p95_build > 5000:
            status = "critical"
        elif p95_build is not None and p95_build > 2000:
            status = "degraded"
        elif count > 0:
            status = "healthy"
        else:
            status = "no_data"

        return {
            "sample_count_24h": count,
            "p50_context_build_ms": p50_build,
            "p95_context_build_ms": p95_build,
            "p95_ttft_ms": p95_ttft,
            "cache_hit_rate": cache_hit_rate,
            "avg_prompt_tokens": avg_prompt,
            "avg_total_ms": avg_total,
            "slowest_builders": slowest_builders,
            "status": status,
        }
    except Exception as e:
        logger.debug("CoS performance computation failed: %s", e)
        return None


def _get_intelligence_pipeline_health(now):
    """
    Intelligence Pipeline Health — monitors the 5-layer data pipeline
    that feeds Beth's reasoning context.
    Cached 60s — ~30 queries across 5 subsystems. Data changes slowly.

    Subsystems monitored:
      1. Signal Snapshots — compute_nightly_signals Celery task output
      2. Goal Momentum — GoalMomentumSnapshot freshness
      3. Journal NLP — JournalSignal extraction pipeline
      4. Compensatory Reasoning — commitment gap analysis availability
      5. CoS Context Completeness — which context builders produced data

    Status thresholds:
      HEALTHY (green): ≥4 subsystems healthy
      DEGRADED (yellow): 2-3 subsystems healthy
      CRITICAL (red): 0-1 subsystems healthy
    """
    cached = django_cache.get("wlj:ops:pipeline_health")
    if cached is not None:
        return cached

    from datetime import timedelta as td

    healthy_count = 0
    subsystems = {}

    # --- 1. Signal Snapshots ---
    try:
        from apps.core.ai_eae.models import SignalSnapshot
        from django.db.models import Count, Max

        last_24h = now - td(hours=24)
        last_7d = now - td(days=7)

        total_snapshots = SignalSnapshot.objects.count()
        snapshots_24h = SignalSnapshot.objects.filter(
            updated_at__gte=last_24h,
        ).count()
        snapshots_7d = SignalSnapshot.objects.filter(
            updated_at__gte=last_7d,
        ).count()

        latest_snapshot = SignalSnapshot.objects.aggregate(
            latest=Max('updated_at'),
        )
        latest_ts = latest_snapshot.get('latest')
        latest_age = _human_ago(latest_ts) if latest_ts else 'never'

        # Users with snapshots today
        users_with_snapshots = (
            SignalSnapshot.objects.filter(updated_at__gte=last_24h)
            .values('user').distinct().count()
        )

        # Signal type distribution (latest 24h)
        type_dist = dict(
            SignalSnapshot.objects.filter(updated_at__gte=last_24h)
            .values_list('signal_type')
            .annotate(cnt=Count('id'))
            .order_by('-cnt')
        )

        is_healthy = total_snapshots > 0 and snapshots_24h > 0
        if is_healthy:
            healthy_count += 1

        subsystems['signal_snapshots'] = {
            'status': 'HEALTHY' if is_healthy else ('STALE' if total_snapshots > 0 else 'EMPTY'),
            'total': total_snapshots,
            'last_24h': snapshots_24h,
            'last_7d': snapshots_7d,
            'latest_age': latest_age,
            'users_24h': users_with_snapshots,
            'type_distribution': type_dist,
        }
    except Exception as e:
        logger.debug("Pipeline health: signal snapshots check failed: %s", e)
        subsystems['signal_snapshots'] = {'status': 'ERROR', 'error': str(e)[:100]}

    # --- 2. Goal Momentum ---
    try:
        from apps.dashboard_v2.models import GoalMomentumSnapshot

        last_24h = now - td(hours=24)
        last_7d = now - td(days=7)

        total_momentum = GoalMomentumSnapshot.objects.count()
        momentum_24h = GoalMomentumSnapshot.objects.filter(
            created_at__gte=last_24h,
        ).count()

        latest_momentum = GoalMomentumSnapshot.objects.aggregate(
            latest=Max('created_at'),
        )
        latest_m_ts = latest_momentum.get('latest')
        latest_m_age = _human_ago(latest_m_ts) if latest_m_ts else 'never'

        # Average momentum score (last 7d)
        from django.db.models import Avg
        avg_score = GoalMomentumSnapshot.objects.filter(
            created_at__gte=last_7d,
        ).aggregate(avg=Avg('momentum_score'))
        avg_momentum = round(avg_score['avg'], 2) if avg_score.get('avg') else None

        # Users covered
        users_covered = (
            GoalMomentumSnapshot.objects.filter(created_at__gte=last_24h)
            .values('user').distinct().count()
        )

        is_healthy = total_momentum > 0 and momentum_24h > 0
        if is_healthy:
            healthy_count += 1

        subsystems['goal_momentum'] = {
            'status': 'HEALTHY' if is_healthy else ('STALE' if total_momentum > 0 else 'EMPTY'),
            'total': total_momentum,
            'last_24h': momentum_24h,
            'latest_age': latest_m_age,
            'avg_score_7d': avg_momentum,
            'users_24h': users_covered,
        }
    except Exception as e:
        logger.debug("Pipeline health: goal momentum check failed: %s", e)
        subsystems['goal_momentum'] = {'status': 'ERROR', 'error': str(e)[:100]}

    # --- 3. Journal NLP (Signal Extraction) ---
    try:
        from apps.journal.models import JournalSignal

        last_24h = now - td(hours=24)
        last_7d = now - td(days=7)

        total_journal_signals = JournalSignal.objects.count()
        signals_24h = JournalSignal.objects.filter(
            created_at__gte=last_24h,
        ).count()
        signals_7d = JournalSignal.objects.filter(
            created_at__gte=last_7d,
        ).count()

        latest_signal = JournalSignal.objects.aggregate(
            latest=Max('created_at'),
        )
        latest_s_ts = latest_signal.get('latest')
        latest_s_age = _human_ago(latest_s_ts) if latest_s_ts else 'never'

        # Entries with signals vs total entries (7d)
        from apps.journal.models import JournalEntry
        entries_7d = JournalEntry.objects.filter(
            created_at__gte=last_7d,
        ).count()
        entries_with_signals = (
            JournalSignal.objects.filter(created_at__gte=last_7d)
            .values('entry').distinct().count()
        )

        # Count entries without signals (backfill candidates)
        entries_without_signals = JournalEntry.objects.exclude(
            pk__in=JournalSignal.objects.values_list("entry_id", flat=True)
        ).count()

        # Journal NLP is healthy if it has ever produced signals
        # (extraction is event-driven, so 0 in 24h is okay if no entries were created)
        is_healthy = total_journal_signals > 0
        if is_healthy:
            healthy_count += 1

        subsystems['journal_nlp'] = {
            'status': 'HEALTHY' if is_healthy else 'EMPTY',
            'total_signals': total_journal_signals,
            'last_24h': signals_24h,
            'last_7d': signals_7d,
            'latest_age': latest_s_age,
            'entries_7d': entries_7d,
            'entries_with_signals_7d': entries_with_signals,
            'entries_without_signals': entries_without_signals,
        }
    except Exception as e:
        logger.debug("Pipeline health: journal NLP check failed: %s", e)
        subsystems['journal_nlp'] = {'status': 'ERROR', 'error': str(e)[:100]}

    # --- 4. Compensatory Reasoning ---
    try:
        from apps.core.ai_insights.models import Insight

        last_24h = now - td(hours=24)
        last_7d = now - td(days=7)

        # Compensatory insights are stored as Insight records with type 'compensatory_progress'
        comp_total = Insight.objects.filter(
            insight_type='compensatory_progress',
        ).count()
        comp_7d = Insight.objects.filter(
            insight_type='compensatory_progress',
            created_at__gte=last_7d,
        ).count()

        # All PIE insights (7d) for context
        total_insights_7d = Insight.objects.filter(
            created_at__gte=last_7d,
        ).count()

        # Compensatory is healthy if PIE is running (insights exist)
        is_healthy = total_insights_7d > 0
        if is_healthy:
            healthy_count += 1

        subsystems['compensatory'] = {
            'status': 'HEALTHY' if is_healthy else ('STALE' if comp_total > 0 else 'EMPTY'),
            'compensatory_total': comp_total,
            'compensatory_7d': comp_7d,
            'total_insights_7d': total_insights_7d,
        }
    except Exception as e:
        logger.debug("Pipeline health: compensatory check failed: %s", e)
        subsystems['compensatory'] = {'status': 'ERROR', 'error': str(e)[:100]}

    # --- 5. CoS Context Completeness ---
    try:
        from django.core.cache import cache

        # Check the CoS context cache for completeness indicators
        # The context builders store their output in the CoS context dict;
        # we check the last chat's latency snapshot for builder coverage
        from apps.core.ai_observability.models import ChatLatencySnapshot

        last_24h = now - td(hours=24)
        recent_chats = ChatLatencySnapshot.objects.filter(
            created_at__gte=last_24h,
        ).count()

        # Check which builders produced data in the last snapshot
        latest_chat = (
            ChatLatencySnapshot.objects.filter(created_at__gte=last_24h)
            .order_by('-created_at')
            .values('stages', 'meta')
            .first()
        )

        builders_present = []
        builders_empty = []
        if latest_chat:
            stages = latest_chat.get('stages') or {}
            # COS_BUILDER_* stage entries are set by personal_assistant.py
            # from the _builder_timings dict returned by build_cos_context().
            # A builder with duration > 0 produced data; duration == 0 means
            # it ran but returned nothing (or was skipped).
            prefix = 'COS_BUILDER_'
            for key, duration in stages.items():
                if not key.startswith(prefix):
                    continue
                name = key[len(prefix):]
                if duration and duration > 0:
                    builders_present.append(name)
                else:
                    builders_empty.append(name)

        is_healthy = recent_chats > 0 and len(builders_present) > 0
        if is_healthy:
            healthy_count += 1

        subsystems['cos_context'] = {
            'status': 'HEALTHY' if is_healthy else ('STALE' if recent_chats > 0 else 'NO_CHATS'),
            'chats_24h': recent_chats,
            'builders_active': len(builders_present),
            'builders_empty': len(builders_empty),
            'active_list': builders_present[:10],
            'empty_list': builders_empty[:10],
        }
    except Exception as e:
        logger.debug("Pipeline health: CoS context check failed: %s", e)
        subsystems['cos_context'] = {'status': 'ERROR', 'error': str(e)[:100]}

    # --- Overall Status ---
    if healthy_count >= 4:
        overall = 'HEALTHY'
    elif healthy_count >= 2:
        overall = 'DEGRADED'
    else:
        overall = 'CRITICAL'

    result = {
        'status': overall,
        'healthy_count': healthy_count,
        'total_subsystems': 5,
        'subsystems': subsystems,
    }
    django_cache.set("wlj:ops:pipeline_health", result, timeout=60)
    return result


# ================================================================== #
#  API Health Telemetry (Phase 8)
# ================================================================== #

def _get_api_health_telemetry(now):
    """
    API health metrics aggregated from APIRequestLog.
    Cached 30s — ~4 queries over the full 24h request log.

    Returns 24h request volume, response times, error rates,
    top endpoints, and channel breakdown (mobile/chat/other).
    """
    cached = django_cache.get("wlj:ops:api_health")
    if cached is not None:
        return cached

    try:
        from apps.core.models import APIRequestLog
        from django.db.models import Avg, Count, Q, F
        from django.db.models.functions import Substr

        window = now - timedelta(hours=24)
        qs = APIRequestLog.objects.filter(created_at__gte=window)

        # --- Overall aggregates ---
        stats = qs.aggregate(
            total=Count('id'),
            avg_ms=Avg('response_time_ms'),
            error_count=Count('id', filter=Q(status_code__gte=400)),
            anomaly_count=Count('id', filter=Q(is_anomaly=True)),
            mobile_count=Count('id', filter=Q(path__startswith='/api/mobile/')),
            chat_count=Count('id', filter=Q(path__contains='/api/chat')),
        )

        total = stats['total'] or 0
        avg_ms = round(stats['avg_ms'] or 0, 1)
        error_count = stats['error_count'] or 0
        anomaly_count = stats['anomaly_count'] or 0
        mobile_count = stats['mobile_count'] or 0
        chat_count = stats['chat_count'] or 0
        error_rate = round((error_count / max(total, 1)) * 100, 1)

        # --- P95 approximation (order by response_time desc, skip top 5%) ---
        p95_ms = None
        if total > 10:
            skip = max(int(total * 0.05), 1)
            p95_row = (
                qs.order_by('-response_time_ms')
                .values_list('response_time_ms', flat=True)[skip:skip + 1]
            )
            p95_list = list(p95_row)
            if p95_list:
                p95_ms = p95_list[0]

        # --- Top endpoints by volume (normalize paths by stripping IDs) ---
        # Group by the first 3 path segments to avoid per-ID fragmentation
        # e.g. /api/mobile/health/ingest/ stays, /api/chat/stream/ stays
        endpoint_qs = (
            qs.values('path')
            .annotate(
                count=Count('id'),
                avg_ms=Avg('response_time_ms'),
                errors=Count('id', filter=Q(status_code__gte=400)),
            )
            .order_by('-count')[:8]
        )
        endpoints = [
            {
                'path': row['path'],
                'count': row['count'],
                'avg_ms': round(row['avg_ms'] or 0, 1),
                'errors': row['errors'],
            }
            for row in endpoint_qs
        ]

        # --- Status determination ---
        if error_rate > 10 or avg_ms > 5000:
            status = 'CRITICAL'
        elif error_rate > 5 or avg_ms > 2000:
            status = 'WARNING'
        elif total == 0:
            status = 'IDLE'
        else:
            status = 'HEALTHY'

        result = {
            'total_requests': total,
            'avg_response_ms': avg_ms,
            'p95_response_ms': p95_ms,
            'error_count': error_count,
            'error_rate_pct': error_rate,
            'anomaly_count': anomaly_count,
            'mobile_requests': mobile_count,
            'chat_requests': chat_count,
            'other_requests': total - mobile_count - chat_count,
            'endpoints': endpoints,
            'status': status,
        }
        django_cache.set("wlj:ops:api_health", result, timeout=30)
        return result

    except Exception:
        logger.exception("Failed to compute API health telemetry")
        return {
            'total_requests': 0,
            'avg_response_ms': 0,
            'p95_response_ms': None,
            'error_count': 0,
            'error_rate_pct': 0,
            'anomaly_count': 0,
            'mobile_requests': 0,
            'chat_requests': 0,
            'other_requests': 0,
            'endpoints': [],
            'status': 'IDLE',
        }


def _get_email_intelligence_telemetry():
    """
    Email Intelligence Pipeline telemetry (Phase 6B.5).

    Pure cache reader — reads from wlj:ops:email_fact_extraction
    (written by EmailFactExtractionService._update_email_telemetry).
    Zero DB queries.
    """
    cached = django_cache.get("wlj:ops:email_fact_extraction")
    if cached is not None:
        return cached

    # No data yet — return empty structure
    return {
        'scans': 0,
        'emails_classified': 0,
        'emails_kept': 0,
        'emails_skipped': 0,
        'facts_created': 0,
        'signals_affected': 0,
        'transactions_created': 0,
        'documents_created': 0,
        'last_run': None,
    }


# =========================================================================
# OPS STREAM PAYLOAD BUILDER
# =========================================================================
# Called by the SAME engine cycle (background worker, every 60s).
# Assembles the full telemetry payload and caches it for OpsStreamView.
# The HTTP request path NEVER calls telemetry builders directly.
# =========================================================================

# Cache key and TTL for the pre-built ops stream payload
OPS_STREAM_CACHE_KEY = "wlj:ops:stream_payload"
OPS_STREAM_CACHE_TTL = 90  # seconds — SAME runs every 60s, 1.5x margin


def build_ops_stream_payload():
    """Build the complete Ops Stream telemetry payload.

    Called by the SAME cycle (background worker). Gathers all telemetry
    from individual helpers and caches the assembled payload.

    Returns:
        dict: The full payload dict (also cached for OpsStreamView).
    """
    from apps.core.ai_observability.heartbeat import (
        get_cadence_config,
        get_latest_heartbeats,
    )
    from apps.core.ai_observability.ops_aggregates import ALL_ENGINES
    from apps.core.ai_observability.ops_feed import get_recent_feed

    build_start = time.monotonic()
    now = timezone.now()
    cadence_config = get_cadence_config()
    heartbeats = get_latest_heartbeats()

    # Engine cards
    engine_cards = _build_engine_cards(ALL_ENGINES, cadence_config, heartbeats, now)

    # SAME narrative (latest)
    narrative = _get_latest_narrative()

    # Active anomalies (watchlist)
    anomalies = _get_active_anomalies()

    # Feed events — fixed 5-minute window (not request-specific)
    feed = get_recent_feed(since=None, limit=50, engine_filter=None)

    # System posture from narrative
    posture = narrative.get("posture", "OK") if narrative else "OK"

    # System Integrity Index (latest snapshot)
    integrity = _get_latest_integrity()

    # Scheduler heartbeats (ISE + SAME)
    scheduler_heartbeats = _get_scheduler_heartbeats()

    # EAE telemetry
    eae_telemetry = _get_eae_ops_telemetry(now)

    # APScheduler health
    scheduler_health = _get_scheduler_health()

    # Celery execution layer health
    celery_health = _get_celery_health()

    # Persistent learning health
    learning_health = _get_learning_health(now)

    # Health Intelligence Engine telemetry
    health_intelligence = _get_health_intelligence_telemetry(now)

    # COAS health scores
    coas_health = _get_coas_health()

    # AI Action Failure Rate metrics
    aafr = _get_aafr_metrics()

    # System Complexity Score
    complexity = _get_complexity_score()

    # Domain event bus telemetry
    domain_events = _get_domain_event_telemetry()

    # Chat latency telemetry
    chat_latency = _get_chat_latency_telemetry(now)

    # Intelligence Pipeline Health
    pipeline_health = _get_intelligence_pipeline_health(now)

    # Signal Health (cached by SAME cycle)
    signal_health = _get_signal_health()

    # Validator Gate Health (cached by SAME cycle)
    validator_health = _get_validator_health()

    # CoS Performance (cached by SAME cycle)
    cos_performance = _get_cos_performance()

    # API Health
    api_health = _get_api_health_telemetry(now)

    # Email Intelligence Pipeline telemetry (Phase 6B.5)
    email_intelligence = _get_email_intelligence_telemetry()

    build_time_ms = round((time.monotonic() - build_start) * 1000)

    payload = {
        "server_time": now.isoformat(),
        "posture": posture,
        "engine_cards": engine_cards,
        "narrative": narrative,
        "anomalies": anomalies,
        "feed": feed,
        "integrity": integrity,
        "scheduler_heartbeats": scheduler_heartbeats,
        "scheduler_health": scheduler_health,
        "celery_health": celery_health,
        "eae_telemetry": eae_telemetry,
        "learning_health": learning_health,
        "health_intelligence": health_intelligence,
        "coas_health": coas_health,
        "aafr": aafr,
        "complexity": complexity,
        "domain_events": domain_events,
        "chat_latency": chat_latency,
        "pipeline_health": pipeline_health,
        "signal_health": signal_health,
        "validator_health": validator_health,
        "cos_performance": cos_performance,
        "api_health": api_health,
        "email_intelligence": email_intelligence,
        "ops_stream_build_time_ms": build_time_ms,
        "next_since": now.isoformat(),
    }

    # Cache payload for OpsStreamView to read
    django_cache.set(OPS_STREAM_CACHE_KEY, payload, timeout=OPS_STREAM_CACHE_TTL)
    logger.info(
        "Ops stream payload built and cached (%d keys, %dms)",
        len(payload),
        build_time_ms,
    )

    return payload
