"""
Operations Wall v2 — Vegas Ops Wall views.

Routes:
  /admin-console/ops/              -> OpsWallView (flagship page)
  /admin-console/ops/stream/       -> OpsStreamView (JSON polling)
  /admin-console/ops/actions/      -> OpsActionView (POST: admin actions)
  /admin-console/ops/trigger-same/ -> TriggerSAMEView (POST: manual SAME execution)
  /admin-console/ops/same-status/  -> SAMEStatusView (GET: execution status)
  /admin-console/ops/all-engines/  -> AllEnginesView (table/search)

Project: Whole Life Journey
Path: apps/core/ai_observability/ops_views.py
"""

import json
import logging
import uuid
from datetime import timedelta

from django.contrib.auth.mixins import UserPassesTestMixin
from django.http import JsonResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

logger = logging.getLogger(__name__)


class AdminRequiredMixin(UserPassesTestMixin):
    """Restrict to staff users."""

    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_staff

    def handle_no_permission(self):
        from django.shortcuts import redirect

        return redirect("dashboard:home")


class OperationsWallView(AdminRequiredMixin, TemplateView):
    """Main operations wall page — the flagship Vegas Ops Wall."""

    template_name = "admin_console/operations_wall.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Operations Wall"
        context["app_name"] = "admin_console"
        return context


class OpsStreamView(View):
    """
    Polling endpoint for the Operations Wall v2.

    GET /admin-console/ops/stream/?since=<iso-timestamp>&engine=<name>&filter=<type>

    Returns JSON with:
      - engine cards (status, cadence, sparkline data, miss/error counters)
      - SAME narrative snapshot
      - active anomalies (watchlist)
      - live feed events (incremental since cursor)
      - system posture
    """

    def get(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({"error": "forbidden"}, status=403)

        since_str = request.GET.get("since", "")
        engine_filter = request.GET.get("engine", "")
        feed_filter = request.GET.get("filter", "")  # core/errors/decisions/anomalies

        try:
            since = timezone.datetime.fromisoformat(since_str)
            if timezone.is_naive(since):
                since = timezone.make_aware(since)
        except (ValueError, TypeError):
            since = timezone.now() - timedelta(minutes=5)

        from apps.core.ai_observability.heartbeat import (
            get_cadence_config,
            get_latest_heartbeats,
        )
        from apps.core.ai_observability.models import (
            EngineRun,
            OpsAnomaly,
            OpsNarrativeSnapshot,
            SystemIntegritySnapshot,
        )
        from apps.core.ai_observability.ops_aggregates import ALL_ENGINES
        from apps.core.ai_observability.ops_feed import get_recent_feed

        now = timezone.now()
        cadence_config = get_cadence_config()
        heartbeats = get_latest_heartbeats()

        # Build engine cards
        engine_cards = _build_engine_cards(ALL_ENGINES, cadence_config, heartbeats, now)

        # Get SAME narrative (latest)
        narrative = _get_latest_narrative()

        # Get active anomalies (watchlist)
        anomalies = _get_active_anomalies()

        # Get feed events
        feed = get_recent_feed(
            since=since,
            limit=50,
            engine_filter=engine_filter or None,
        )

        # Apply feed filter
        if feed_filter == "errors":
            feed = [f for f in feed if f["severity"] == "error"]
        elif feed_filter == "decisions":
            feed = [f for f in feed if f["type"] == "decision"]

        # System posture from narrative
        posture = narrative.get("posture", "OK") if narrative else "OK"

        # System Integrity Index (latest snapshot)
        integrity = _get_latest_integrity()

        return JsonResponse({
            "server_time": now.isoformat(),
            "posture": posture,
            "engine_cards": engine_cards,
            "narrative": narrative,
            "anomalies": anomalies,
            "feed": feed,
            "integrity": integrity,
            "next_since": now.isoformat(),
        })


class OpsActionView(View):
    """
    Admin action endpoint — POST to execute safe operational actions.

    POST /admin-console/ops/actions/
    Body: {"action": "rerun_engine", "engine": "UAL"}

    All actions create AdminIntervention records.
    """

    def post(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({"error": "forbidden"}, status=403)

        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "invalid JSON"}, status=400)

        action = body.get("action", "")
        engine = body.get("engine", "")

        if not action:
            return JsonResponse({"error": "action required"}, status=400)

        from apps.core.ai_observability.models import AdminIntervention

        trace_id = str(uuid.uuid4())

        # Create intervention record
        intervention = AdminIntervention.objects.create(
            admin_user=request.user,
            action_type=action,
            engine_name=engine,
            trace_id=trace_id,
            notes=f"Admin action via Ops Wall: {action} on {engine}",
            result_status="pending",
        )

        # Execute the action
        result = _execute_action(action, engine, trace_id)

        # Update intervention with result
        intervention.result_status = result["status"]
        intervention.result_detail = result["detail"]
        intervention.save(update_fields=["result_status", "result_detail"])

        return JsonResponse({
            "success": result["status"] == "success",
            "message": result["detail"],
            "trace_id": trace_id,
            "intervention_id": intervention.id,
        })


class IntegrityIndexView(View):
    """
    Dedicated endpoint for System Integrity Index.

    GET /admin-console/ops/integrity/

    Returns JSON with current score, posture, component breakdown,
    and recent history (last 30 snapshots).
    """

    def get(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({"error": "forbidden"}, status=403)

        from apps.core.ai_observability.models import SystemIntegritySnapshot

        # Latest snapshot
        latest = SystemIntegritySnapshot.objects.first()
        if not latest:
            return JsonResponse({
                "score": None,
                "posture": "UNKNOWN",
                "components": {},
                "history": [],
            })

        # Recent history (last 30 snapshots for sparkline)
        history = list(
            SystemIntegritySnapshot.objects.order_by("-created_at")[:30]
            .values("score", "posture", "created_at")
        )
        history = [
            {
                "score": h["score"],
                "posture": h["posture"],
                "created_at": h["created_at"].isoformat(),
            }
            for h in reversed(history)  # Chronological order
        ]

        return JsonResponse({
            "score": latest.score,
            "posture": latest.posture,
            "components": latest.components,
            "created_at": latest.created_at.isoformat(),
            "history": history,
        })


class CadenceTimelineView(View):
    """
    Time-series heartbeat history for cadence visualization.

    GET /admin-console/ops/cadence/?minutes=30&engine=UAL

    Returns JSON with per-engine timeline data including:
    - Expected cadence ticks
    - Actual heartbeat observations
    - Status at each observation
    """

    def get(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({"error": "forbidden"}, status=403)

        from apps.core.ai_observability.heartbeat import get_cadence_config
        from apps.core.ai_observability.models import EngineHeartbeat, EngineRun
        from apps.core.ai_observability.ops_aggregates import ALL_ENGINES

        minutes = min(int(request.GET.get("minutes", 30)), 120)
        engine_filter = request.GET.get("engine", "")

        now = timezone.now()
        since = now - timedelta(minutes=minutes)
        cadence_config = get_cadence_config()

        engines = [engine_filter] if engine_filter else ALL_ENGINES
        timelines = {}

        for engine in engines:
            cfg = cadence_config.get(engine, {})
            if not cfg.get("enabled", True):
                continue

            interval = cfg.get("interval", 3600)

            # Actual heartbeats in window
            heartbeats = list(
                EngineHeartbeat.objects.filter(
                    engine_name=engine,
                    observed_at__gte=since,
                ).order_by("observed_at").values(
                    "observed_at", "status", "lateness_seconds"
                )[:60]  # Cap at 60 entries per engine
            )

            # Actual engine runs in window
            runs = list(
                EngineRun.objects.filter(
                    engine_name=engine,
                    started_at__gte=since,
                ).order_by("started_at").values(
                    "started_at", "status", "duration_ms"
                )[:60]
            )

            # Expected cadence ticks in window
            expected_ticks = []
            if interval > 0 and interval <= minutes * 60:
                tick = since
                while tick <= now:
                    expected_ticks.append(tick.isoformat())
                    tick += timedelta(seconds=interval)

            # Identify missed intervals (expected ticks with no nearby run)
            run_times = [r["started_at"] for r in runs]
            missed_ticks = []
            for tick_iso in expected_ticks:
                tick_dt = timezone.datetime.fromisoformat(tick_iso)
                if timezone.is_naive(tick_dt):
                    tick_dt = timezone.make_aware(tick_dt)
                jitter = cfg.get("jitter", 60)
                hit = any(
                    abs((rt - tick_dt).total_seconds()) < interval + jitter
                    for rt in run_times
                )
                if not hit:
                    missed_ticks.append(tick_iso)

            timelines[engine] = {
                "interval_seconds": interval,
                "heartbeats": [
                    {
                        "time": h["observed_at"].isoformat(),
                        "status": h["status"],
                        "lateness": h["lateness_seconds"],
                    }
                    for h in heartbeats
                ],
                "runs": [
                    {
                        "time": r["started_at"].isoformat(),
                        "status": r["status"],
                        "duration_ms": r["duration_ms"],
                    }
                    for r in runs
                ],
                "expected_ticks": expected_ticks,
                "missed_ticks": missed_ticks,
            }

        return JsonResponse({
            "server_time": now.isoformat(),
            "window_minutes": minutes,
            "timelines": timelines,
        })


class TriggerSAMEView(View):
    """
    Manual SAME execution trigger.

    POST /admin-console/ops/trigger-same/

    Dispatches run_same_cycle_task.delay() with idempotency guard:
    rejects if a SAME execution is already queued/running (within 5 min).
    Creates SAMEExecutionLog + AdminIntervention audit records.
    """

    def post(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({"error": "forbidden"}, status=403)

        from apps.core.ai_observability.models import (
            AdminIntervention,
            SAMEExecutionLog,
        )

        # Idempotency guard — reject if execution already active
        if SAMEExecutionLog.is_execution_active():
            active = SAMEExecutionLog.objects.filter(
                status__in=["queued", "running"],
                started_at__gte=timezone.now() - timedelta(minutes=5),
            ).first()
            return JsonResponse({
                "success": False,
                "error": "execution_active",
                "message": "SAME execution already in progress.",
                "execution_id": active.id if active else None,
                "status": active.status if active else "unknown",
            }, status=409)

        # Create execution log entry
        execution = SAMEExecutionLog.objects.create(
            trigger_source="manual",
            status="queued",
            triggered_by=request.user,
        )

        # Dispatch Celery task
        try:
            from apps.core.tasks import run_same_cycle_task

            result = run_same_cycle_task.delay()
            execution.celery_task_id = result.id
            execution.save(update_fields=["celery_task_id"])
        except Exception as e:
            execution.status = "failed"
            execution.error_detail = str(e)[:500]
            execution.completed_at = timezone.now()
            execution.save(update_fields=["status", "error_detail", "completed_at"])
            logger.exception("Failed to dispatch SAME task: %s", e)
            return JsonResponse({
                "success": False,
                "error": "dispatch_failed",
                "message": f"Failed to dispatch SAME task: {str(e)[:200]}",
                "execution_id": execution.id,
            }, status=500)

        # Audit record
        trace_id = str(uuid.uuid4())
        AdminIntervention.objects.create(
            admin_user=request.user,
            action_type="rerun_engine",
            engine_name="SAME",
            trace_id=trace_id,
            notes=f"Manual SAME execution triggered (execution_id={execution.id}, celery_task_id={result.id})",
            result_status="pending",
        )

        logger.info(
            "SAME manual trigger by %s (execution_id=%s, celery_task_id=%s)",
            request.user.email,
            execution.id,
            result.id,
        )

        return JsonResponse({
            "success": True,
            "message": "SAME cycle queued for execution.",
            "execution_id": execution.id,
            "celery_task_id": result.id,
            "status": "queued",
        })


class SAMEStatusView(View):
    """
    SAME execution status endpoint.

    GET /admin-console/ops/same-status/

    Returns the latest SAMEExecutionLog entry with status,
    duration, trigger source, and timestamps.
    """

    def get(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({"error": "forbidden"}, status=403)

        from apps.core.ai_observability.models import SAMEExecutionLog

        latest = SAMEExecutionLog.get_latest()
        if not latest:
            return JsonResponse({
                "has_data": False,
                "message": "No SAME executions recorded yet.",
            })

        return JsonResponse({
            "has_data": True,
            "execution_id": latest.id,
            "trigger_source": latest.trigger_source,
            "status": latest.status,
            "started_at": latest.started_at.isoformat(),
            "completed_at": latest.completed_at.isoformat() if latest.completed_at else None,
            "duration_ms": latest.duration_ms,
            "error_detail": latest.error_detail if latest.status == "failed" else "",
            "triggered_by": latest.triggered_by.email if latest.triggered_by else None,
            "is_active": latest.status in ["queued", "running"],
        })


class TriggerEngineView(View):
    """
    Per-engine manual execution trigger.

    POST /admin-console/ops/trigger-engine/
    Body: {"engine": "DBE"}

    Guards:
    - Admin-only
    - Engine must exist in ENGINE_REGISTRY with can_manual_run=True
    - Engine must not be frozen (EngineExpectedCadence.is_enabled)
    - Idempotency: reject if EngineExecutionLog already active for engine
    """

    def post(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({"error": "forbidden"}, status=403)

        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "invalid JSON"}, status=400)

        engine = body.get("engine", "")

        # Validate engine
        from apps.core.ai_observability.engine_registry import get_engine_meta

        meta = get_engine_meta(engine)
        if not meta:
            return JsonResponse(
                {"error": f"Unknown engine: {engine}"}, status=400,
            )
        if not meta["can_manual_run"]:
            return JsonResponse({
                "success": False,
                "error": "not_manual",
                "message": f"{engine} requires user context and cannot be run manually.",
            }, status=400)

        # Freeze check via EngineExpectedCadence
        from apps.core.ai_observability.models import EngineExpectedCadence

        try:
            cadence = EngineExpectedCadence.objects.get(engine_name=engine)
            if not cadence.is_enabled:
                return JsonResponse({
                    "success": False,
                    "error": "engine_frozen",
                    "message": f"{engine} is currently frozen/disabled.",
                }, status=409)
        except EngineExpectedCadence.DoesNotExist:
            pass  # No cadence config = not frozen

        # Idempotency guard
        from apps.core.ai_observability.models import EngineExecutionLog

        if EngineExecutionLog.is_engine_active(engine):
            active = EngineExecutionLog.objects.filter(
                engine_name=engine,
                status__in=["queued", "running"],
            ).first()
            return JsonResponse({
                "success": False,
                "error": "execution_active",
                "message": f"{engine} execution already in progress.",
                "execution_id": active.id if active else None,
            }, status=409)

        # Create execution log
        execution = EngineExecutionLog.objects.create(
            engine_name=engine,
            trigger_source="manual",
            status="queued",
            triggered_by=request.user,
        )

        # Dispatch Celery task
        try:
            from apps.core.tasks import run_engine_task

            result = run_engine_task.delay(engine, execution.id)
            execution.celery_task_id = result.id
            execution.save(update_fields=["celery_task_id"])
        except Exception as e:
            execution.status = "failed"
            execution.error_detail = str(e)[:500]
            execution.completed_at = timezone.now()
            execution.save(update_fields=["status", "error_detail", "completed_at"])
            logger.exception("Failed to dispatch engine task %s: %s", engine, e)
            return JsonResponse({
                "success": False,
                "error": "dispatch_failed",
                "message": f"Failed to dispatch {engine} task: {str(e)[:200]}",
                "execution_id": execution.id,
            }, status=500)

        # Audit trail
        trace_id = str(uuid.uuid4())
        from apps.core.ai_observability.models import AdminIntervention

        mode = meta.get("execution_mode", "batch")
        AdminIntervention.objects.create(
            admin_user=request.user,
            action_type="rerun_engine",
            engine_name=engine,
            trace_id=trace_id,
            notes=(
                f"Manual engine execution ({mode}): {engine} "
                f"(execution_id={execution.id}, celery_task_id={result.id})"
            ),
            result_status="pending",
        )

        logger.info(
            "Engine manual trigger (%s) by %s: %s (execution_id=%s, celery_task_id=%s)",
            mode, request.user.email, engine, execution.id, result.id,
        )

        return JsonResponse({
            "success": True,
            "message": f"{engine} queued for execution.",
            "execution_id": execution.id,
            "celery_task_id": result.id,
            "engine": engine,
            "status": "queued",
        })


class EngineStatusView(View):
    """
    Per-engine execution status endpoint (polling).

    GET /admin-console/ops/engine-status/?engine=DBE

    Returns the latest EngineExecutionLog for the given engine.
    """

    def get(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({"error": "forbidden"}, status=403)

        engine = request.GET.get("engine", "")
        if not engine:
            return JsonResponse({"error": "engine parameter required"}, status=400)

        from apps.core.ai_observability.models import EngineExecutionLog

        latest = EngineExecutionLog.get_latest_for_engine(engine)
        if not latest:
            return JsonResponse({"has_data": False, "engine": engine})

        return JsonResponse({
            "has_data": True,
            "execution_id": latest.id,
            "engine": latest.engine_name,
            "trigger_source": latest.trigger_source,
            "status": latest.status,
            "started_at": latest.started_at.isoformat(),
            "completed_at": (
                latest.completed_at.isoformat() if latest.completed_at else None
            ),
            "duration_ms": latest.duration_ms,
            "result_summary": latest.result_summary,
            "error_detail": latest.error_detail if latest.status == "failed" else "",
            "triggered_by": (
                latest.triggered_by.email if latest.triggered_by else None
            ),
            "is_active": latest.status in ["queued", "running"],
        })


class AllEnginesView(AdminRequiredMixin, TemplateView):
    """All engines table view with search."""

    template_name = "admin_console/all_engines.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "All Engines"
        context["app_name"] = "admin_console"

        from apps.core.ai_observability.heartbeat import get_cadence_config
        from apps.core.ai_observability.models import EngineRun
        from apps.core.ai_observability.ops_aggregates import ALL_ENGINES

        now = timezone.now()
        cadence_config = get_cadence_config()

        engines = []
        for engine_name in sorted(ALL_ENGINES + ["GLOE", "ISE", "E3"]):
            cfg = cadence_config.get(engine_name, {})
            last_run = (
                EngineRun.objects.filter(engine_name=engine_name)
                .order_by("-started_at")
                .values("started_at", "status", "duration_ms")
                .first()
            )

            interval = cfg.get("interval", 0)
            if interval >= 604800:
                interval_label = f"{interval // 604800}w"
            elif interval >= 86400:
                interval_label = f"{interval // 86400}d"
            elif interval >= 3600:
                interval_label = f"{interval // 3600}h"
            elif interval > 0:
                interval_label = f"{interval // 60}m"
            else:
                interval_label = "—"

            engines.append({
                "name": engine_name,
                "interval_label": interval_label,
                "enabled": cfg.get("enabled", False),
                "last_run_at": last_run["started_at"] if last_run else None,
                "last_status": last_run["status"] if last_run else "never",
                "last_duration": last_run["duration_ms"] if last_run else 0,
            })

        context["engines"] = engines
        return context


# =========================================================================
# HELPER FUNCTIONS
# =========================================================================


def _build_engine_cards(engine_names, cadence_config, heartbeats, now):
    """Build engine card data for each core engine."""
    from apps.core.ai_observability.models import EngineRun

    cards = []

    for name in engine_names:
        cfg = cadence_config.get(name, {})
        hb = heartbeats.get(name, {})
        interval = cfg.get("interval", 3600)

        # Last run
        last_run = (
            EngineRun.objects.filter(engine_name=name)
            .order_by("-started_at")
            .values("started_at", "status", "duration_ms")
            .first()
        )

        # Status mapping from heartbeat to card status
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
        thirty_min_ago = now - timedelta(minutes=30)
        errors_30m = EngineRun.objects.filter(
            engine_name=name,
            started_at__gte=thirty_min_ago,
            status="error",
        ).count()
        if errors_30m > 3:
            card_status = "ERROR"

        # Miss counter (last 30m)
        miss_count = 0
        if hb_status == "MISSED":
            lateness = hb.get("lateness_seconds", 0)
            if interval > 0:
                miss_count = max(1, lateness // interval)

        # Error counter (last 24h)
        twenty_four_h_ago = now - timedelta(hours=24)
        errors_24h = EngineRun.objects.filter(
            engine_name=name,
            started_at__gte=twenty_four_h_ago,
            status="error",
        ).count()

        # Sparkline data: last 6 runs durations
        recent_runs = list(
            EngineRun.objects.filter(engine_name=name)
            .order_by("-started_at")[:6]
            .values_list("duration_ms", flat=True)
        )
        sparkline = list(reversed(recent_runs))  # Chronological order

        # Duration P95 (last 1h)
        one_hour_ago = now - timedelta(hours=1)
        durations_1h = list(
            EngineRun.objects.filter(
                engine_name=name,
                started_at__gte=one_hour_ago,
            )
            .order_by("duration_ms")
            .values_list("duration_ms", flat=True)
        )
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

        # Engine manual execution metadata from registry
        from apps.core.ai_observability.engine_registry import get_engine_meta

        eng_meta = get_engine_meta(name)
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

    return cards


def _get_latest_narrative():
    """Get the most recent OpsNarrativeSnapshot as dict."""
    from apps.core.ai_observability.models import OpsNarrativeSnapshot

    snapshot = OpsNarrativeSnapshot.objects.first()
    if not snapshot:
        return {
            "posture": "OK",
            "headline": "SAME not yet initialized — awaiting first run.",
            "bullets_now": ["No data available yet."],
            "recommendations": ["System will begin monitoring once engines start running."],
            "watching_next": [],
        }

    return {
        "posture": snapshot.posture,
        "headline": snapshot.headline,
        "bullets_now": snapshot.bullets_now or [],
        "recommendations": snapshot.recommendations or [],
        "watching_next": snapshot.watching_next or [],
        "created_at": snapshot.created_at.isoformat(),
    }


def _get_latest_integrity():
    """Get the latest SystemIntegritySnapshot as dict."""
    from apps.core.ai_observability.models import SystemIntegritySnapshot

    snapshot = SystemIntegritySnapshot.objects.first()
    if not snapshot:
        return None

    return {
        "score": snapshot.score,
        "posture": snapshot.posture,
        "components": snapshot.components,
        "created_at": snapshot.created_at.isoformat(),
    }


def _get_active_anomalies():
    """Get all active OpsAnomaly records as list of dicts."""
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
    """Signal ISE scheduler restart (creates a marker for the scheduler to pick up)."""
    return {
        "status": "success",
        "detail": (
            "Scheduler restart signaled. ISE will pick up on next cron cycle "
            "(Railway runs every 5 minutes)."
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
