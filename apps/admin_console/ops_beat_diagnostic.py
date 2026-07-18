"""
TEMPORARY incident glass-box — OPS-1 Beat-task runtime diagnostic.

Incident: `capture.send_pending_capture_reminders` reported MISSED_RUN on the Ops
Wall while the worker pool is healthy. The prior runtime trace could not, from
pool-level evidence, distinguish "task never dispatched/executed" from "task
executed but the OPS-1 heartbeat (ScheduledTaskRun.ran_at) never advanced".

This read-only endpoint assembles, for one canonical Celery task name, every
durable/lightweight runtime fact needed to select ONE Phase-2 branch:

  A never dispatched · B dispatched-not-consumed · C received-but-fails ·
  D executed-but-OPS-1-stale (recorder) · E OPS-1/OPS-7 fresh but SAME MISSED

Authentication + rate limiting reuse the EXISTING Claude API framework
(`X-Claude-API-Key` + `APIRateLimitMixin`) — no new auth surface.

Read-only · operator-scoped · request-path-light (a handful of indexed reads +
short-timeout Redis) · no sensitive payloads · REMOVE after verification.

Path: apps/admin_console/ops_beat_diagnostic.py  (temporary — incident scaffolding)
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.views import View

from apps.core.rate_limiting import APIRateLimitMixin, secure_compare_api_key

logger = logging.getLogger(__name__)

DEFAULT_TASK = "capture.send_pending_capture_reminders"


def _iso(dt):
    return dt.isoformat() if dt else None


class OpsBeatTaskDiagnosticAPIView(APIRateLimitMixin, View):
    """GET ?task=<celery task name>  → full runtime state for one Beat task."""

    rate_limit_requests_per_minute = 30
    rate_limit_requests_per_hour = 300
    rate_limit_key_prefix = "admin_api_ops_beat_diag"

    def get(self, request):
        if not settings.CLAUDE_API_KEY:
            return JsonResponse({"error": "CLAUDE_API_KEY not configured"}, status=500)
        if not secure_compare_api_key(
            request.headers.get("X-Claude-API-Key", ""), settings.CLAUDE_API_KEY
        ):
            return JsonResponse(
                {"error": "Invalid or missing API key. Include X-Claude-API-Key."},
                status=401,
            )

        task = request.GET.get("task", DEFAULT_TASK).strip() or DEFAULT_TASK
        now = timezone.now()

        report = {
            "task_name": task,
            "generated_at": _iso(now),
            "process": "web",  # signals fire in the worker; this reads shared state
            "1_beat_config": self._beat_config(task),
            "2_ops1_scheduled_task_run": self._ops1(task, now),
            "3_ops7_task_health": self._ops7(task),
            "4_celery_registration": self._registration(task),
            "5_recovery_evidence": self._recovery(task),
            "6_registry_comparison": self._registry_comparison(task),
            "7_active_incident": self._incident(task),
        }
        report["classification_hint"] = self._hint(report)
        return JsonResponse(report, json_dumps_params={"indent": 2})

    # ── 1. Beat configuration ────────────────────────────────────────────
    def _beat_config(self, task):
        out = {"schedule_entries": [], "in_settings_schedule": False,
               "in_effective_runtime_schedule": False}
        schedule = getattr(settings, "CELERY_BEAT_SCHEDULE", {}) or {}
        for key, entry in schedule.items():
            if entry.get("task") == task:
                out["in_settings_schedule"] = True
                sched = entry.get("schedule")
                out["schedule_entries"].append({
                    "entry_name": key,
                    "task": entry.get("task"),
                    "schedule_repr": repr(sched),
                    "schedule_seconds": sched if isinstance(sched, (int, float)) else None,
                    "options": entry.get("options"),
                    "queue": (entry.get("options") or {}).get("queue"),
                })
        try:
            from celery import current_app
            eff = current_app.conf.beat_schedule or {}
            out["in_effective_runtime_schedule"] = any(
                e.get("task") == task for e in eff.values()
            )
            out["effective_entry_names"] = [
                k for k, e in eff.items() if e.get("task") == task
            ]
        except Exception as e:
            out["effective_schedule_error"] = str(e)[:200]
        return out

    # ── 2. OPS-1 ScheduledTaskRun + computed freshness ───────────────────
    def _ops1(self, task, now):
        from apps.core.ai_observability.models import ScheduledTaskRun
        from apps.core.ai_observability.scheduled_task_monitor import (
            compute_scheduled_task_states,
        )
        out = {}
        row = ScheduledTaskRun.objects.filter(task_name=task).first()
        if row is None:
            out["row_exists"] = False
        else:
            out.update({
                "row_exists": True,
                "ran_at": _iso(row.ran_at),
                "age_seconds": int((now - row.ran_at).total_seconds()),
                "status": row.status,
                "duration_ms": row.duration_ms,
                "error_message": row.error_message or "",
            })
        state = next(
            (s for s in compute_scheduled_task_states(now) if s["task_name"] == task),
            None,
        )
        out["computed_state"] = state or {"note": "task not in monitored registry"}
        return out

    # ── 3. OPS-7 task-health (transient Redis; failure/retry/active only) ─
    def _ops7(self, task):
        try:
            from apps.core.ai_observability import task_health_monitor as th
        except Exception as e:
            return {"available": False, "error": str(e)[:200]}
        client = th._redis()
        if client is None:
            return {"available": False, "reason": "no Redis (dev in-memory broker)"}

        def _matches(list_key):
            hits = []
            try:
                for raw in client.lrange(list_key, 0, -1):
                    e = th._decode(raw)
                    epoch, _, name = e.partition(":")
                    if name == task:
                        hits.append(float(epoch))
            except Exception:
                pass
            return {"count": len(hits), "most_recent_epoch": max(hits) if hits else None}

        active_hit = None
        try:
            for tid, score in client.zrange(th._ACTIVE_ZSET, 0, -1, withscores=True):
                if th._decode(client.hget(th._ACTIVE_NAMES, tid)) == task:
                    active_hit = {"task_id": th._decode(tid), "start_epoch": score}
                    break
        except Exception:
            pass
        return {
            "available": True,
            "note": (
                "OPS-7 records ONLY failures/retries/revoked/active (transient, "
                "self-expiring ~1h). Successful completions leave NO durable trace "
                "(CELERY_TASK_IGNORE_RESULT=True, no result backend). Absence from "
                "failures + absence from active is consistent with silent success."
            ),
            "currently_active": active_hit,
            "failures": _matches(th._FAILURES_LIST),
            "retries": _matches(th._RETRIES_LIST),
            "revoked": _matches(th._REVOKED_LIST),
        }

    # ── 4. Celery registration (importable in this process?) ─────────────
    def _registration(self, task):
        try:
            from celery import current_app
            obj = current_app.tasks.get(task)
            return {
                "registered_in_app": obj is not None,
                "resolved_name": getattr(obj, "name", None),
                "result_backend": str(getattr(settings, "CELERY_RESULT_BACKEND", "") or ""),
                "task_ignore_result": bool(getattr(settings, "CELERY_TASK_IGNORE_RESULT", False)),
                "note": "no per-task success history persists (ignore_result + no result backend)",
            }
        except Exception as e:
            return {"error": str(e)[:200]}

    # ── 5. Recovery evidence (RecoveryAttempt audit) ─────────────────────
    def _recovery(self, task):
        try:
            from apps.core.operations.models import RecoveryAttempt
        except Exception as e:
            return {"available": False, "error": str(e)[:200]}
        rows = list(
            RecoveryAttempt.objects.filter(
                anomaly_type="MISSED_RUN", engine_name=task
            ).order_by("-created_at")[:10]
        )
        return {
            "available": True,
            "attempt_count_shown": len(rows),
            "attempts": [{
                "created_at": _iso(r.created_at),
                "updated_at": _iso(r.updated_at),
                "phase": r.phase,
                "outcome": r.outcome,
                "mode": r.mode,
                "classification": r.classification,
                "attempt_number": r.attempt_number,
                "action_taken": (r.action_taken or "")[:300],
                "evidence_after": r.evidence_after,
                "error": (r.error or "")[:300],
            } for r in rows],
        }

    # ── 6. Registry comparison (the OPS-1 recorder guard) ────────────────
    def _registry_comparison(self, task):
        from django.core.cache import cache
        from apps.core.ai_observability.scheduled_task_monitor import (
            _CADENCE_CACHE_KEY,
            get_monitored_beat_tasks,
        )
        registry = get_monitored_beat_tasks()
        names = sorted(registry.keys())
        cached_raw = cache.get(_CADENCE_CACHE_KEY)
        return {
            "canonical_task_in_registry": task in registry,
            "registry_size": len(names),
            "registry_task_names": names,
            "cache_key": _CADENCE_CACHE_KEY,
            "cache_populated": cached_raw is not None,
            "recorder_guard_would_skip": task not in registry,
            "note": (
                "record_scheduled_task_run() early-returns when the task name is "
                "NOT in this registry. If canonical_task_in_registry is False in "
                "the worker, every completion is silently dropped -> OPS-1 stale."
            ),
        }

    # ── 7. Active incident (OpsAnomaly lifecycle) ────────────────────────
    def _incident(self, task):
        from apps.core.ai_observability.models import OpsAnomaly
        latest = (
            OpsAnomaly.objects.filter(anomaly_type="MISSED_RUN", engine_name=task)
            .order_by("-created_at")
            .first()
        )
        if latest is None:
            return {"exists": False}
        return {
            "exists": True,
            "is_active": latest.is_active,
            "severity": latest.severity,
            "original_severity": latest.original_severity,
            "escalation_count": latest.escalation_count,
            "created_at": _iso(latest.created_at),
            "updated_at": _iso(latest.updated_at),
            "resolved_at": _iso(latest.resolved_at),
            "summary": (latest.summary or "")[:300],
            "evidence": latest.evidence,
        }

    # ── classification hint (advisory, not authoritative) ────────────────
    def _hint(self, r):
        ops1 = r["2_ops1_scheduled_task_run"]
        ops7 = r["3_ops7_task_health"]
        reg = r["6_registry_comparison"]
        state = (ops1.get("computed_state") or {}).get("status")
        failing = isinstance(ops7, dict) and (ops7.get("failures") or {}).get("count")
        if not r["1_beat_config"]["in_effective_runtime_schedule"]:
            return "BRANCH A candidate — task absent from effective runtime schedule"
        if failing:
            return "BRANCH C candidate — OPS-7 shows recent failures for this task"
        if reg.get("recorder_guard_would_skip"):
            return ("BRANCH D candidate — task NOT in monitored registry (web view); "
                    "OPS-1 recorder guard would silently skip completions")
        if state == "MISSED" and ops1.get("row_exists"):
            return ("BRANCH D/E — OPS-1 row stale while task registered & guard OK; "
                    "confirm via recovery re-enqueue not advancing ran_at")
        return "inconclusive — inspect full report"
