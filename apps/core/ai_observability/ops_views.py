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
    """Main operations wall page — the flagship Vegas Ops Wall.

    Server-side context includes system maturity scores, domain coverage,
    and proactive intelligence metrics (updated on page load, not polled).
    """

    template_name = "admin_console/operations_wall.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Operations Wall"
        context["app_name"] = "admin_console"

        # --- System Maturity (system-wide, not user-scoped) ---
        context.update(self._get_maturity_data())

        # --- Maturity Trend Deltas (compare to previous snapshot) ---
        context["maturity_deltas"] = self._get_maturity_deltas()

        # --- Life Impact Breakdown ---
        context["life_impact_breakdown"] = self._get_life_impact_breakdown(
            context.get("maturity_scores", {}),
        )

        # --- Domain Coverage ---
        context["domain_coverage"] = self._get_domain_coverage()

        # --- Proactive Intelligence (7-day, system-wide) ---
        context["proactive_stats"] = self._get_proactive_stats()

        # --- Canonical Query Compliance (cached from management command) ---
        context["canonical_compliance"] = self._get_canonical_compliance()

        # --- Phase 3: Domain Registry Health ---
        context["registry_health"] = self._get_registry_health()

        return context

    # ------------------------------------------------------------------ #
    #  War Room data helpers (server-side, rendered once on page load)
    # ------------------------------------------------------------------ #

    def _get_canonical_compliance(self):
        """Read cached canonical query compliance from management command."""
        try:
            from django.core.cache import cache

            data = cache.get("wlj:ops:canonical_compliance")
            if data:
                return data
        except Exception:
            pass
        return {"score": None, "violations": 0, "scanned": 0, "last_run": None}

    def _get_maturity_data(self):
        """Read cached maturity scores for the War Room header.

        PERFORMANCE: NEVER computes maturity scores on the request path.
        Reads from cache (populated by SAME cycle every 60s).
        If cache is empty (first 60s after deploy), shows "pending" state.

        compute_all_maturity_scores() runs 600+ queries via
        compute_system_life_impact() and MUST NOT be called here.
        """
        result = {
            "maturity_scores": {},
            "maturity_recommendations": [],
            "maturity_regressions": [],
            "life_impact_sample_size": 0,
        }
        try:
            from django.core.cache import cache

            from apps.core.ai_observability.maturity_engine import (
                detect_regressions,
                generate_recommendations,
            )

            # Read cache ONLY — populated by SAME cycle (every 60s)
            cache_key = "wlj:ops:maturity_scores"
            scores = cache.get(cache_key)
            if scores is None:
                # No cache yet — SAME will populate within 60s
                return result

            # Extract sample_size from life_impact details if present
            li_data = scores.get('life_impact', {})
            result['life_impact_sample_size'] = li_data.get('sample_size', 0)
            result["maturity_scores"] = scores
            result["maturity_recommendations"] = generate_recommendations(scores)
            result["maturity_regressions"] = detect_regressions()
        except ImportError:
            logger.debug("OPS: Maturity engine not available")
        except Exception as e:
            logger.warning("OPS: Maturity data failed: %s", e, exc_info=True)
        return result

    def _get_maturity_deltas(self):
        """Compare latest vs previous maturity snapshot for trend indicators.

        Returns dict mapping dimension names to delta integers.
        Positive = improvement, negative = decline, 0 = unchanged, None = no data.
        """
        deltas = {
            "infrastructure": None,
            "intelligence": None,
            "safety": None,
            "domain_coverage": None,
            "life_impact": None,
            "overall": None,
        }
        try:
            from apps.core.ai_observability.models import SystemMaturitySnapshot

            snapshots = list(
                SystemMaturitySnapshot.objects.order_by("-snapshot_date")[:2]
            )
            if len(snapshots) < 2:
                return deltas

            latest, previous = snapshots[0], snapshots[1]
            deltas["infrastructure"] = latest.infrastructure_score - previous.infrastructure_score
            deltas["intelligence"] = latest.intelligence_score - previous.intelligence_score
            deltas["safety"] = latest.safety_score - previous.safety_score
            deltas["domain_coverage"] = latest.domain_coverage_score - previous.domain_coverage_score
            deltas["life_impact"] = latest.life_impact_score - previous.life_impact_score
            deltas["overall"] = latest.overall_score - previous.overall_score
        except Exception as e:
            logger.debug("OPS: Maturity deltas unavailable: %s", e)
        return deltas

    def _get_life_impact_breakdown(self, maturity_scores):
        """Extract life impact factor breakdown from maturity scores.

        Returns list of dicts: [{name, label, value}, ...] for template rendering.
        """
        factors = []
        try:
            life_data = maturity_scores.get("life_impact", {})
            details = life_data.get("details", {})
            if not details or "error" in details:
                return factors

            factor_labels = {
                "goal_progress": "Goal progress",
                "routine_adherence": "Routine adherence",
                "engagement_depth": "Domain engagement",
            }
            factor_weights = {
                "goal_progress": 0.3,
                "routine_adherence": 0.4,
                "engagement_depth": 0.3,
            }
            for key, label in factor_labels.items():
                val = details.get(key)
                if val is not None:
                    weight = factor_weights.get(key, 0)
                    factors.append({
                        "name": key,
                        "label": label,
                        "value": val,
                        "weight_pct": int(weight * 100),
                    })
        except Exception as e:
            logger.debug("OPS: Life impact breakdown unavailable: %s", e)
        return factors

    def _get_registry_health(self):
        """Phase 3: Domain registry governance health summary."""
        try:
            from apps.core.domain_registry import get_registry_health_summary
            return get_registry_health_summary()
        except Exception:
            return {'status': 'unavailable', 'issues': [], 'domain_count': 0, 'by_class': {}}

    def _get_domain_coverage(self):
        """Fetch domain coverage summary from the registry."""
        try:
            from apps.core.domain_registry import registry

            return registry.get_coverage_summary()
        except ImportError:
            return []

    def _get_proactive_stats(self):
        """7-day proactive check-in statistics (system-wide)."""
        stats = {"total_7d": 0, "by_type": []}
        try:
            from django.db.models import Count

            from apps.ai.models import AssistantMessage

            cutoff = timezone.now() - timedelta(days=7)
            qs = AssistantMessage.objects.filter(
                is_proactive=True,
                created_at__gte=cutoff,
            )
            stats["total_7d"] = qs.count()
            by_type = (
                qs.values("metadata__check_in_type")
                .annotate(cnt=Count("id"))
                .order_by("-cnt")
            )
            stats["by_type"] = [
                (row["metadata__check_in_type"] or "unknown", row["cnt"])
                for row in by_type
            ]
        except Exception as e:
            logger.debug("OPS: Proactive stats unavailable: %s", e)
        return stats


class OpsStreamView(View):
    """
    Polling endpoint for the Operations Wall v2.

    GET /admin-console/ops/stream/

    Returns pre-computed telemetry payload built by the SAME engine cycle
    (background worker, every 60s). The HTTP request path performs ZERO
    telemetry computation — it reads a cached snapshot and returns it.

    If the payload hasn't been built yet (cold start), returns a
    {"status": "pending"} response so the frontend can retry gracefully.
    """

    def get(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({"error": "forbidden"}, status=403)

        from django.core.cache import cache as _cache

        from apps.core.ai_observability.ops_telemetry import OPS_STREAM_CACHE_KEY

        payload = _cache.get(OPS_STREAM_CACHE_KEY)
        if payload is None:
            return JsonResponse({
                "status": "pending",
                "message": "Telemetry payload is being computed. Will be available shortly.",
            })

        return JsonResponse(payload)


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


class SchedulerHeartbeatView(View):
    """
    Scheduler heartbeat endpoint.

    GET /admin-console/ops/scheduler-heartbeat/

    Returns status, drift, and thresholds for ISE and SAME schedulers.
    """

    def get(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({"error": "forbidden"}, status=403)

        return JsonResponse({
            "server_time": timezone.now().isoformat(),
            "schedulers": _get_scheduler_heartbeats(),
        })


class SchedulerHealthView(View):
    """
    Celery Beat scheduling health endpoint.

    GET /admin-console/ops/scheduler-health/

    Returns Celery Beat health derived from ISE/SAME heartbeats.
    """

    def get(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({"error": "forbidden"}, status=403)

        from apps.core.scheduler_health import get_scheduler_status
        status = get_scheduler_status()
        return JsonResponse({
            "server_time": timezone.now().isoformat(),
            "scheduler": status,
        })


class SchedulerRestartView(View):
    """
    Scheduler restart endpoint (deprecated).

    POST /admin-console/ops/scheduler-restart/

    APScheduler was removed in 2026-03-16. All scheduling is via Celery Beat.
    To restart scheduling, restart the Beat process on Railway.
    This endpoint remains for backward compatibility but returns an info message.
    """

    def post(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({"error": "forbidden"}, status=403)

        return JsonResponse({
            "success": False,
            "message": (
                "APScheduler was removed. All scheduling is via Celery Beat. "
                "Restart the Beat process on Railway to fix scheduling issues."
            ),
            "status": {},
        })


class TriggerGoalMomentumView(View):
    """
    Manual trigger for compute_nightly_momentum Celery task.

    POST /admin-console/ops/trigger-goal-momentum/

    Dispatches the nightly goal momentum computation task immediately.
    Creates AdminIntervention audit record.
    """

    def post(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({"error": "forbidden"}, status=403)

        from apps.core.ai_observability.models import AdminIntervention

        trace_id = str(uuid.uuid4())

        try:
            from apps.dashboard_v2.tasks import compute_nightly_momentum

            result = compute_nightly_momentum.delay()

            AdminIntervention.objects.create(
                admin_user=request.user,
                action_type="trigger_goal_momentum",
                engine_name="GOAL_MOMENTUM",
                trace_id=trace_id,
                notes=(
                    f"Manual goal momentum computation triggered "
                    f"(celery_task_id={result.id})"
                ),
                result_status="pending",
            )

            logger.info(
                "Goal momentum manual trigger by %s (celery_task_id=%s)",
                request.user.email, result.id,
            )

            return JsonResponse({
                "success": True,
                "message": "Goal momentum computation queued.",
                "celery_task_id": result.id,
                "trace_id": trace_id,
            })
        except Exception as e:
            logger.exception("Failed to dispatch goal momentum: %s", e)
            return JsonResponse({
                "success": False,
                "error": "dispatch_failed",
                "message": f"Failed to dispatch: {str(e)[:200]}",
            }, status=500)


class TriggerSignalAggregationView(View):
    """
    Manual trigger for compute_nightly_signals Celery task.

    POST /admin-console/ops/trigger-signals/

    Dispatches the nightly signal aggregation task immediately.
    Creates AdminIntervention audit record.
    """

    def post(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({"error": "forbidden"}, status=403)

        from apps.core.ai_observability.models import AdminIntervention

        trace_id = str(uuid.uuid4())

        # Dispatch Celery task
        try:
            from apps.core.ai_eae.tasks import compute_nightly_signals

            result = compute_nightly_signals.delay()

            # Audit trail
            AdminIntervention.objects.create(
                admin_user=request.user,
                action_type="trigger_signal_aggregation",
                engine_name="EAE_SIGNALS",
                trace_id=trace_id,
                notes=(
                    f"Manual signal aggregation triggered "
                    f"(celery_task_id={result.id})"
                ),
                result_status="pending",
            )

            logger.info(
                "Signal aggregation manual trigger by %s (celery_task_id=%s)",
                request.user.email, result.id,
            )

            return JsonResponse({
                "success": True,
                "message": "Signal aggregation task queued.",
                "celery_task_id": result.id,
                "trace_id": trace_id,
            })
        except Exception as e:
            logger.exception("Failed to dispatch signal aggregation: %s", e)
            return JsonResponse({
                "success": False,
                "error": "dispatch_failed",
                "message": f"Failed to dispatch: {str(e)[:200]}",
            }, status=500)


class MetricEvidenceView(View):
    """
    Metric evidence endpoint for investigation panels.

    GET /admin-console/ops/metric-evidence/?target=INFRASTRUCTURE

    Returns the current computed evidence for a maturity metric,
    formatted for display in the investigation panel.
    """

    def get(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({"error": "forbidden"}, status=403)

        target = request.GET.get("target", "")
        if not target:
            return JsonResponse({"error": "target parameter required"}, status=400)

        try:
            from apps.core.ai_observability.diagnostic_engine import get_metric_evidence

            evidence = get_metric_evidence(target)
            return JsonResponse(evidence)
        except Exception as e:
            logger.warning("Metric evidence failed for %s: %s", target, e, exc_info=True)
            return JsonResponse({
                "target": target,
                "score": None,
                "status": "ERROR",
                "components": [],
                "error": f"Evidence loading failed: {str(e)[:300]}",
            }, status=500)


class DiagnosticScanView(View):
    """
    Diagnostic scan endpoint for the Ops Command Center.

    GET /admin-console/ops/diagnose/?target=INFRASTRUCTURE

    Runs a targeted diagnostic scan and returns structured evidence
    with checks, root cause hypothesis, and recommended next steps.
    """

    def get(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({"error": "forbidden"}, status=403)

        target = request.GET.get("target", "")
        if not target:
            return JsonResponse({"error": "target parameter required"}, status=400)

        try:
            from apps.core.ai_observability.diagnostic_engine import (
                DIAGNOSTIC_SCANS,
                run_diagnostic_scan,
            )

            result = run_diagnostic_scan(target)
            result["available_scans"] = list(DIAGNOSTIC_SCANS.keys())
            return JsonResponse(result)
        except Exception as e:
            logger.warning("Diagnostic scan failed for %s: %s", target, e, exc_info=True)
            return JsonResponse({
                "target": target,
                "status": "ERROR",
                "checks": [],
                "error": f"Diagnostic scan failed: {str(e)[:300]}",
            }, status=500)


class DebugPromptView(View):
    """
    Debug prompt generation endpoint.

    GET /admin-console/ops/debug-prompt/?target=INFRASTRUCTURE

    Generates a structured debug prompt combining metric evidence
    and diagnostic scan results for investigation handoff.
    """

    def get(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({"error": "forbidden"}, status=403)

        target = request.GET.get("target", "")
        if not target:
            return JsonResponse({"error": "target parameter required"}, status=400)

        from apps.core.ai_observability.diagnostic_engine import (
            generate_debug_prompt,
            get_metric_evidence,
            run_diagnostic_scan,
        )

        try:
            evidence = get_metric_evidence(target)
            scan_result = run_diagnostic_scan(target)
            prompt = generate_debug_prompt(target, scan_result=scan_result, evidence=evidence)

            return JsonResponse({
                "target": target,
                "prompt": prompt,
                "scan_status": scan_result.get("status"),
                "score": evidence.get("score"),
            })
        except Exception as e:
            logger.warning("Debug prompt generation failed for %s: %s", target, e, exc_info=True)
            return JsonResponse({
                "target": target,
                "error": f"Debug prompt generation failed: {str(e)[:300]}",
            }, status=500)


class DependencyGraphView(AdminRequiredMixin, View):
    """Return engine dependency graph as JSON (Phase 6)."""

    def get(self, request):
        from apps.core.engine_registry import get_critical_engines, get_dependency_graph

        graph = get_dependency_graph()
        critical = get_critical_engines(min_impact=3)
        return JsonResponse({"graph": graph, "critical_engines": critical})


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
        for engine_name in sorted(ALL_ENGINES + ["GLOE", "ISE"]):
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




class TriggerJournalBackfillView(View):
    """
    Manual trigger for journal signal backfill — runs SYNCHRONOUSLY.

    POST /admin-console/ops/trigger-journal-backfill/

    Extracts signals from journal entries that have no JournalSignal records.
    Runs inline (no Celery dependency) so results are returned immediately.
    Returns per-entry diagnostics showing exactly what happened.
    """

    def post(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({"error": "forbidden"}, status=403)

        from apps.core.ai_observability.models import AdminIntervention

        trace_id = str(uuid.uuid4())

        try:
            from apps.journal.models import JournalEntry, JournalSignal
            from apps.journal.services.signal_extractor import (
                JournalSignalExtractor,
                MIN_WORDS_FOR_EXTRACTION,
            )

            # Find entries without signals — newest first so that
            # recent entries (used by Beth's 14-day context window)
            # get signals before older historical entries
            entries_without_signals = (
                JournalEntry.objects.exclude(
                    pk__in=JournalSignal.objects.values_list("entry_id", flat=True)
                )
                .order_by("-created_at")
            )

            total_entries = entries_without_signals.count()
            if total_entries == 0:
                return JsonResponse({
                    "success": True,
                    "message": "All entries already have signals.",
                    "total_entries": 0,
                    "trace_id": trace_id,
                })

            # Check OpenAI client availability first
            from apps.ai.services import get_openai_client
            client = get_openai_client()
            if not client:
                return JsonResponse({
                    "success": False,
                    "error": "openai_unavailable",
                    "message": (
                        "OpenAI client not available. Check OPENAI_API_KEY env var. "
                        f"Found {total_entries} entries without signals."
                    ),
                    "total_entries": total_entries,
                    "trace_id": trace_id,
                }, status=503)

            # Process each entry synchronously with diagnostics
            results = []
            extracted_count = 0
            skipped_short = 0
            skipped_idempotent = 0
            errors = 0

            for entry in entries_without_signals[:50]:  # Cap at 50 to avoid timeout
                entry_result = {"entry_id": entry.pk, "title": (entry.title or "")[:50]}

                # Check word count
                text_parts = []
                if entry.title:
                    text_parts.append(entry.title)
                if entry.body:
                    text_parts.append(entry.body)
                text = ' '.join(text_parts).strip()
                word_count = len(text.split()) if text else 0

                if word_count < MIN_WORDS_FOR_EXTRACTION:
                    entry_result["status"] = "skipped_short"
                    entry_result["word_count"] = word_count
                    entry_result["min_words"] = MIN_WORDS_FOR_EXTRACTION
                    skipped_short += 1
                    results.append(entry_result)
                    continue

                # Check idempotency
                if JournalSignal.objects.filter(entry=entry).exists():
                    entry_result["status"] = "skipped_has_signals"
                    skipped_idempotent += 1
                    results.append(entry_result)
                    continue

                # Run extraction
                try:
                    signals = JournalSignalExtractor.extract_signals(entry)
                    entry_result["status"] = "extracted"
                    entry_result["signals_created"] = len(signals)
                    entry_result["signal_types"] = [s.signal_type for s in signals]
                    extracted_count += len(signals)
                except Exception as e:
                    entry_result["status"] = "error"
                    entry_result["error"] = str(e)[:200]
                    errors += 1

                results.append(entry_result)

            summary = (
                f"Processed {len(results)}/{total_entries} entries: "
                f"{extracted_count} signals extracted, "
                f"{skipped_short} skipped (too short), "
                f"{skipped_idempotent} skipped (already has signals), "
                f"{errors} errors"
            )

            AdminIntervention.objects.create(
                admin_user=request.user,
                action_type="trigger_journal_backfill",
                engine_name="JOURNAL_NLP",
                trace_id=trace_id,
                notes=summary,
            )

            # Invalidate telemetry caches so tile updates immediately
            from django.core.cache import cache as django_cache
            django_cache.delete("wlj:ops:pipeline_health")
            django_cache.delete("wlj:ops:stream_payload")
            django_cache.delete("wlj:ops:signal_health")

            return JsonResponse({
                "success": True,
                "message": summary,
                "total_entries": total_entries,
                "extracted_count": extracted_count,
                "skipped_short": skipped_short,
                "skipped_idempotent": skipped_idempotent,
                "errors": errors,
                "details": results,
                "trace_id": trace_id,
            })

        except Exception as e:
            logger.error(
                "Journal backfill failed: %s", e, exc_info=True,
            )
            return JsonResponse({
                "success": False,
                "error": "backfill_failed",
                "message": str(e)[:500],
            }, status=500)


class RecomputeSignalHealthView(View):
    """
    Force recompute of signal health and clear cached values.

    POST /admin-console/ops/recompute-signal-health/

    Clears signal_health and ops_stream_payload caches, then recomputes
    signal health from current DB state.
    """

    def post(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({"error": "forbidden"}, status=403)

        from django.core.cache import cache

        from apps.core.ai_observability.models import AdminIntervention

        trace_id = str(uuid.uuid4())

        # Clear all ops telemetry caches so next poll rebuilds from DB
        cache.delete("wlj:ops:signal_health")
        cache.delete("wlj:ops:stream_payload")
        cache.delete("wlj:ops:pipeline_health")

        # Recompute signal health
        try:
            from apps.core.ai_observability.ops_telemetry import compute_signal_health

            signal_health = compute_signal_health()

            # Store back in cache
            cache.set("wlj:ops:signal_health", signal_health, 120)

            domain_count = len(signal_health.get("domains", {}))
            domain_names = sorted(signal_health.get("domains", {}).keys())

            AdminIntervention.objects.create(
                admin_user=request.user,
                action_type="recompute_signal_health",
                engine_name="SAME",
                trace_id=trace_id,
                notes=(
                    f"Manual signal health recompute: {domain_count} domains "
                    f"({', '.join(domain_names)})"
                ),
            )

            return JsonResponse({
                "success": True,
                "message": f"Signal health recomputed: {domain_count} domains.",
                "domains": domain_names,
                "trace_id": trace_id,
            })
        except Exception as e:
            logger.error("Signal health recompute failed: %s", e, exc_info=True)
            return JsonResponse({
                "success": False,
                "error": "recompute_failed",
                "message": str(e),
            }, status=500)


# =========================================================================
# HELPER FUNCTIONS — Extracted to ops_telemetry.py
# =========================================================================
# Import all helper functions from the telemetry module for backward compatibility.
from apps.core.ai_observability.ops_telemetry import (  # noqa: E402, F401
    _build_engine_cards,
    _get_latest_narrative,
    _get_latest_integrity,
    _get_active_anomalies,
    _execute_action,
    _action_rerun_engine,
    _action_clear_suppression_cache,
    _action_restart_scheduler,
    _action_acknowledge_anomaly,
    _action_rebuild_health_summaries,
    _get_scheduler_heartbeats,
    _get_scheduler_health,
    _get_celery_health,
    _get_coas_health,
    _get_aafr_metrics,
    _get_eae_ops_telemetry,
    _human_ago,
    _get_learning_health,
    _get_health_intelligence_telemetry,
    _get_ingestion_stats,
    _get_complexity_score,
    _get_domain_event_telemetry,
    _get_chat_latency_telemetry,
    _get_intelligence_pipeline_health,
    _get_signal_health,
    _get_validator_health,
    _get_cos_performance,
    _get_api_health_telemetry,
)
