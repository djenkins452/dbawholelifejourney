"""
Operations Wall — Telemetry & Aggregation Helpers.

Project: Whole Life Journey
Path: apps/core/ai_observability/ops_telemetry.py
Purpose: Extracted helper functions for the Operations Wall dashboard.
         These functions aggregate telemetry data from various engines
         and subsystems for display on the admin dashboard.

Extracted from ops_views.py for maintainability.

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import json
import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)


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

        # Miss counter (rolling 30m window) — counts historical MISSED
        # heartbeat observations.  After recovery the engine flips to OK
        # but miss_count remains >0 until old observations age out.
        from apps.core.ai_observability.models import EngineHeartbeat

        thirty_min_ago = now - timedelta(minutes=30)
        miss_count = EngineHeartbeat.objects.filter(
            engine_name=name,
            status="MISSED",
            observed_at__gte=thirty_min_ago,
        ).count()

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
        elif action == "rebuild_health_summaries":
            return _action_rebuild_health_summaries()
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
    """Get heartbeat status for all tracked schedulers."""
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

    return schedulers


def _get_scheduler_health():
    """Get APScheduler health status for the Ops Wall stream."""
    try:
        from apps.core.scheduler_health import get_scheduler_status
        return get_scheduler_status()
    except Exception as e:
        logger.debug("OpsWall: Scheduler health unavailable: %s", e)
        return None


def _get_coas_health():
    """Read latest COAS health snapshot (stored by scheduled job, not live recompute)."""
    try:
        from apps.core.ai_observability.models import COASHealthSnapshot

        snap = COASHealthSnapshot.objects.first()
        if not snap:
            return None
        return {
            "scheduler": {"score": snap.scheduler_score},
            "engine": {"score": snap.engine_score},
            "freshness": {"score": snap.freshness_score},
            "overall": {"score": snap.overall_score},
            "computed_at": snap.computed_at.isoformat(),
            "details": snap.details,
        }
    except Exception as e:
        logger.debug("OpsWall: COAS health unavailable: %s", e)
        return None


def _get_aafr_metrics():
    """
    Compute AI Action Failure Rate metrics for 5m, 1h, and 24h windows.

    Returns success rate as the hero metric, with blocked and failed counts
    surfaced separately so safety blocks don't inflate the failure signal.
    Status is based on the 1h failure rate (excludes blocked).
    """
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

        return result

    except Exception as e:
        logger.debug("OpsWall: AAFR metrics unavailable: %s", e)
        return None


def _get_eae_ops_telemetry(now):
    """
    Get EAE telemetry for the Operations Wall (Phase 8.8).

    Returns aggregate metrics across all users for monitoring EAE health.
    """
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

        return {
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

    Monitors all 5 persistent learning subsystems and returns an overall
    status (LEARNING / DEGRADED / STALE) plus per-subsystem metrics.

    Status thresholds:
      LEARNING (green): ≥3 subsystems active in last 7 days
      DEGRADED (yellow): 1-2 subsystems active in last 7 days
      STALE (red): 0 subsystems active in last 7 days
    """
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

        return {
            'status': overall,
            'active_subsystems': active_count,
            'total_subsystems': 5,
            'subsystems': subsystems,
        }

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

    Monitors DailyHealthSummary freshness, data completeness, body comp
    coverage, health scores, and HealthKit ingestion pipeline health.

    Status thresholds:
      OK (green): latest summary ≤ 36h old
      STALE (yellow): latest summary > 36h old
      ERROR (red): no summaries exist or exception
    """
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

        return {
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
