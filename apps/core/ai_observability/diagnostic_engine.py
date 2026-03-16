"""
Ops Command Center — Diagnostic Scan Engine.

Provides targeted diagnostic scans for system metrics and anomaly types.
Each scan is a deterministic function that returns structured evidence.

No LLM calls. No external API calls. All checks are read-only.

Project: Whole Life Journey
Path: apps/core/ai_observability/diagnostic_engine.py
Created: 2026-03-15
"""

import logging
from datetime import timedelta

from django.db.models import Count, Q as models_Q
from django.utils import timezone

logger = logging.getLogger(__name__)


# =============================================================================
# CHECK RESULT BUILDER
# =============================================================================


def _check(name, status, evidence="", detail=None):
    """Build a single check result dict."""
    result = {"name": name, "status": status, "evidence": evidence}
    if detail:
        result["detail"] = detail
    return result


# =============================================================================
# METRIC EVIDENCE — Returns existing computed details for maturity metrics
# =============================================================================


def get_metric_evidence(target):
    """
    Return the current computed evidence for a maturity metric.

    This does NOT run new diagnostic scans — it returns the details
    dict already computed by the scoring functions, formatted for
    display in the investigation panel.

    Args:
        target: One of INFRASTRUCTURE, INTELLIGENCE, SAFETY,
                COVERAGE, LIFE_IMPACT, or an anomaly type name.

    Returns:
        dict with: target, score, status, components (list of evidence items),
        recommendations (list), available_scans (list of scan names)
    """
    target = target.upper().replace("-", "_")

    EVIDENCE_BUILDERS = {
        # Maturity metrics
        "INFRASTRUCTURE": _evidence_infrastructure,
        "INTELLIGENCE": _evidence_intelligence,
        "SAFETY": _evidence_safety,
        "COVERAGE": _evidence_coverage,
        "LIFE_IMPACT": _evidence_life_impact,
        # Anomaly types
        "SIGNAL_DROUGHT": _evidence_signal_drought,
        "ENGINE_STARVATION": _evidence_engine_starvation,
        "ERROR_SPIKE": _evidence_error_spike,
    }

    builder = EVIDENCE_BUILDERS.get(target)
    if builder:
        try:
            return builder()
        except Exception as e:
            logger.warning("Metric evidence failed for %s: %s", target, e, exc_info=True)
            return {
                "target": target,
                "score": None,
                "status": "ERROR",
                "components": [],
                "error": str(e)[:300],
            }

    return {"target": target, "score": None, "status": "UNKNOWN", "components": []}


# =============================================================================
# ANOMALY EVIDENCE — Evidence builders for anomaly-type targets
# =============================================================================


def _evidence_signal_drought():
    """Evidence for SIGNAL_DROUGHT — per-domain signal freshness.

    Uses the cached signal health snapshot (refreshed every 60s by SAME)
    to avoid expensive live computation that caused Cloudflare 524 timeouts.
    Falls back to live computation only if cache is empty.
    """
    from apps.core.ai_observability.ops_telemetry import _get_signal_health

    sh = _get_signal_health() or {}
    domains = sh.get("domains", {})
    silent = sh.get("domains_silent", 0)
    active = sh.get("domains_active", 0)
    total = active + silent

    components = []
    for name, data in sorted(domains.items()):
        freshness_h = data.get("freshness_hours") or 0
        status = data.get("status", "unknown")
        components.append({
            "name": f"{name} signals",
            "value": f"{freshness_h:.0f}h since last signal",
            "status": "OK" if status == "healthy" else "WARN" if status == "stale" else "FAIL",
            "detail": f"24h vol: {data.get('volume_24h', 0)}, 7d vol: {data.get('volume_7d', 0)}, types: {data.get('distinct_types_7d', 0)}",
        })

    overall = "OK" if silent == 0 else "DEGRADED" if silent <= 2 else "CRITICAL"
    return {
        "target": "SIGNAL_DROUGHT",
        "score": round((active / total * 100) if total else 0, 1),
        "status": overall,
        "components": components,
        "recommendations": [
            f"Stalest domain: {sh.get('stalest_domain', '?')} ({(sh.get('stalest_hours') or 0):.0f}h)",
        ] if silent > 0 else [],
    }


def _evidence_engine_starvation():
    """Evidence for ENGINE_STARVATION — engine run freshness and failures."""
    now = timezone.now()
    components = []

    try:
        from apps.core.ai_observability.models import EngineRun
        from django.db.models import Max

        # Get the latest run per engine
        engines = EngineRun.objects.values("engine_name").annotate(
            last_run=Max("completed_at"),
        ).order_by("engine_name")

        starved = 0
        for e in engines:
            if not e["last_run"]:
                continue
            hours_ago = (now - e["last_run"]).total_seconds() / 3600
            # Engines expected to run at least every 24h
            status = "OK" if hours_ago < 12 else "WARN" if hours_ago < 24 else "FAIL"
            if status == "FAIL":
                starved += 1
            components.append({
                "name": e["engine_name"],
                "value": f"Last run {hours_ago:.1f}h ago",
                "status": status,
            })

        overall = "OK" if starved == 0 else "DEGRADED" if starved <= 2 else "CRITICAL"
        return {
            "target": "ENGINE_STARVATION",
            "score": None,
            "status": overall,
            "components": components,
            "recommendations": [f"{starved} engines are starved (>24h since last run)"] if starved else [],
        }
    except Exception as e:
        return {
            "target": "ENGINE_STARVATION",
            "score": None,
            "status": "ERROR",
            "components": [],
            "error": str(e)[:300],
        }


def _evidence_error_spike():
    """Evidence for ERROR_SPIKE — per-engine error rates."""
    now = timezone.now()
    components = []

    try:
        from apps.core.ai_observability.models import EngineRun

        # Error rates in last 1h per engine
        window = now - timedelta(hours=1)
        engines = EngineRun.objects.filter(
            completed_at__gte=window,
        ).values("engine_name").annotate(
            total=Count("id"),
            errors=Count("id", filter=models_Q(status="error")),
        ).order_by("engine_name")

        spike_count = 0
        for e in engines:
            total = e["total"]
            errors = e["errors"]
            rate = (errors / total * 100) if total > 0 else 0
            status = "OK" if rate < 10 else "WARN" if rate < 30 else "FAIL"
            if status == "FAIL":
                spike_count += 1
            components.append({
                "name": e["engine_name"],
                "value": f"{errors}/{total} errors ({rate:.0f}%)",
                "status": status,
            })

        overall = "OK" if spike_count == 0 else "DEGRADED" if spike_count <= 1 else "CRITICAL"
        return {
            "target": "ERROR_SPIKE",
            "score": None,
            "status": overall,
            "components": components,
            "recommendations": [f"{spike_count} engines have error rates >30%"] if spike_count else [],
        }
    except Exception as e:
        return {
            "target": "ERROR_SPIKE",
            "score": None,
            "status": "ERROR",
            "components": [],
            "error": str(e)[:300],
        }


# =============================================================================
# MATURITY METRIC EVIDENCE
# =============================================================================
#
# PERFORMANCE RULE: Evidence builders MUST read from the cached maturity
# scores (populated by Ops Wall page load or SAME cycle) instead of
# recomputing live. compute_system_life_impact() alone runs 600+ queries
# and will cause 524 timeouts if called on the request path.
# =============================================================================


def _get_cached_maturity_scores():
    """Read cached maturity scores. Returns None if cache is empty."""
    try:
        from django.core.cache import cache
        return cache.get("wlj:ops:maturity_scores")
    except Exception:
        return None


def _evidence_infrastructure():
    """Infrastructure evidence — reads cached scores, falls back to lightweight health_scoring."""
    # Try cached scores first (set by Ops Wall page load, 5-min TTL)
    cached = _get_cached_maturity_scores()
    if cached and "infrastructure" in cached:
        infra = cached["infrastructure"]
        score = infra.get("score", 0)
        details = infra.get("details", {})
        components = [{
            "name": "Infrastructure Health",
            "score": score,
            "weight": "100%",
            "items": [
                {"label": "Scheduler", "value": f"{details.get('scheduler', 0)}%", "weight": "35%"},
                {"label": "Engine", "value": f"{details.get('engine', 0)}%", "weight": "35%"},
                {"label": "Freshness", "value": f"{details.get('freshness', 0)}%", "weight": "30%"},
            ],
        }]
        return {
            "target": "INFRASTRUCTURE",
            "score": score,
            "status": _score_status(score),
            "components": components,
            "available_scans": ["INFRASTRUCTURE"],
            "cached": True,
        }

    # Fallback: compute live (health_scoring is ~10 queries, acceptable)
    from apps.core.ai_observability.health_scoring import (
        compute_engine_health,
        compute_intelligence_freshness,
        compute_scheduler_health,
    )

    scheduler = compute_scheduler_health()
    engine = compute_engine_health()
    freshness = compute_intelligence_freshness()

    parts = []
    if scheduler.get("score") is not None:
        parts.append(scheduler["score"] * 0.35)
    if engine.get("score") is not None:
        parts.append(engine["score"] * 0.35)
    if freshness.get("score") is not None:
        parts.append(freshness["score"] * 0.30)
    weight_sum = sum(0.35 if i < 2 else 0.30 for i in range(len(parts)))
    score = int(sum(parts) / weight_sum) if weight_sum else 0

    components = []

    sd = scheduler.get("details", {})
    components.append({
        "name": "Scheduler Health",
        "score": scheduler.get("score"),
        "weight": "35%",
        "items": [
            {"label": "ISE Heartbeat", "value": sd.get("ise", {}).get("status", "?"),
             "penalty": sd.get("ise", {}).get("penalty", 0)},
            {"label": "SAME Heartbeat", "value": sd.get("same", {}).get("status", "?"),
             "penalty": sd.get("same", {}).get("penalty", 0)},
            {"label": "Celery Beat", "value": "Running" if sd.get("celery_beat", {}).get("running") else "DOWN",
             "penalty": sd.get("celery_beat", {}).get("penalty", 0)},
            {"label": "Failed Tasks", "value": str(sd.get("failed_tasks", {}).get("count", 0)),
             "penalty": sd.get("failed_tasks", {}).get("penalty", 0),
             "detail": ", ".join(sd.get("failed_tasks", {}).get("names", []))},
        ],
    })

    ed = engine.get("details", {})
    components.append({
        "name": "Engine Health",
        "score": engine.get("score"),
        "weight": "35%",
        "items": [
            {"label": "Heartbeat OK%", "value": f"{ed.get('heartbeats', {}).get('pct_ok', 0) * 100:.0f}%",
             "penalty": ed.get("heartbeats", {}).get("penalty", 0),
             "detail": f"{ed.get('heartbeats', {}).get('ok', 0)}/{ed.get('heartbeats', {}).get('total', 0)} engines OK"},
            {"label": "30m Error Rate", "value": f"{ed.get('error_rate_30m', {}).get('rate', 0) * 100:.1f}%",
             "penalty": ed.get("error_rate_30m", {}).get("penalty", 0),
             "detail": f"{ed.get('error_rate_30m', {}).get('error_runs', 0)} errors / {ed.get('error_rate_30m', {}).get('total_runs', 0)} runs"},
            {"label": "Active P1 Anomalies", "value": str(ed.get("p1_anomalies", {}).get("count", 0)),
             "penalty": ed.get("p1_anomalies", {}).get("penalty", 0)},
        ],
    })

    fd = freshness.get("details", {})
    freshness_items = []
    for task_name, task_data in fd.items():
        if isinstance(task_data, dict):
            freshness_items.append({
                "label": task_name.replace("_", " ").title(),
                "value": task_data.get("status", "?"),
                "penalty": task_data.get("penalty", 0),
                "detail": f"ratio={task_data.get('ratio', '?')}" if task_data.get("ratio") else "",
            })
    components.append({
        "name": "Intelligence Freshness",
        "score": freshness.get("score"),
        "weight": "30%",
        "items": freshness_items,
    })

    return {
        "target": "INFRASTRUCTURE",
        "score": score,
        "status": _score_status(score),
        "components": components,
        "available_scans": ["INFRASTRUCTURE"],
    }


def _evidence_intelligence():
    """Intelligence evidence — reads cached scores, falls back to lightweight compute."""
    cached = _get_cached_maturity_scores()
    if cached and "intelligence" in cached:
        result = cached["intelligence"]
    else:
        # Lightweight fallback: only 2-3 queries
        from apps.core.ai_observability.maturity_engine import compute_intelligence_score
        result = compute_intelligence_score()

    details = result.get("details", {})
    score = result.get("score", 0)

    components = [{
        "name": "CoS Intelligence Quality",
        "score": score,
        "weight": "100%",
        "items": [
            {"label": "Memory Utilization", "value": f"{details.get('memory_util', 0)}%",
             "weight": "30%"},
            {"label": "Proactive Delivery", "value": f"{details.get('proactive_delivery', 0)}%",
             "weight": "30%"},
            {"label": "Domain Coverage", "value": f"{details.get('domain_coverage', 0)}%",
             "weight": "40%"},
        ],
    }]

    return {
        "target": "INTELLIGENCE",
        "score": score,
        "status": _score_status(score),
        "components": components,
        "available_scans": ["INTELLIGENCE"],
    }


def _evidence_safety():
    """Safety evidence — reads cached scores, falls back to lightweight compute."""
    cached = _get_cached_maturity_scores()
    if cached and "safety" in cached:
        result = cached["safety"]
    else:
        # Lightweight fallback: only 2 queries
        from apps.core.ai_observability.maturity_engine import compute_safety_score
        result = compute_safety_score()

    details = result.get("details", {})
    score = result.get("score", 0)

    components = [{
        "name": "Execution Safety",
        "score": score,
        "weight": "100%",
        "items": [
            {"label": "7-Day Success Rate", "value": f"{details.get('success_rate', 0)}%",
             "weight": "70%"},
            {"label": "Learning Mode Integrity", "value": f"{details.get('learning_mode', 0)}%",
             "weight": "30%"},
        ],
    }]

    return {
        "target": "SAFETY",
        "score": score,
        "status": _score_status(score),
        "components": components,
        "available_scans": ["SAFETY"],
    }


def _evidence_coverage():
    """Coverage evidence — reads cached scores, falls back to in-memory registry (no DB)."""
    cached = _get_cached_maturity_scores()
    if cached and "domain_coverage" in cached:
        result = cached["domain_coverage"]
    else:
        # In-memory fallback: 0 queries (registry is in-memory)
        from apps.core.ai_observability.maturity_engine import compute_domain_coverage_score
        result = compute_domain_coverage_score()

    details = result.get("details", {})
    score = result.get("score", 0)

    domain_items = []
    for d in details.get("domains", []):
        if isinstance(d, dict):
            domain_items.append({
                "label": d.get("display_name", d.get("name", "?")),
                "value": f"{d.get('coverage_score', 0)}%",
                "detail": f"intents={d.get('intent_count', 0)} signals={d.get('signal_count', 0)} models={d.get('model_count', 0)}",
            })

    components = [{
        "name": "Domain Coverage",
        "score": score,
        "weight": "100%",
        "items": domain_items,
        "summary": f"{details.get('total_domains', 0)} domains, {details.get('full_coverage', 0)} at 100%, {details.get('no_intents', 0)} with no intents",
    }]

    return {
        "target": "COVERAGE",
        "score": score,
        "status": _score_status(score),
        "components": components,
        "available_scans": ["COVERAGE"],
    }


def _evidence_life_impact():
    """Life Impact evidence — MUST use cache. Live compute runs 600+ queries."""
    cached = _get_cached_maturity_scores()
    if cached and "life_impact" in cached:
        result = cached["life_impact"]
    else:
        # DO NOT call compute_system_life_impact() — it runs 600+ queries
        # and will cause a 524 timeout. Return a "waiting for data" response.
        return {
            "target": "LIFE_IMPACT",
            "score": None,
            "status": "PENDING",
            "components": [{
                "name": "Life Impact (System Average)",
                "score": None,
                "weight": "100%",
                "summary": "Waiting for data — scores compute on Ops Wall load or daily snapshot",
                "items": [],
            }],
            "available_scans": ["LIFE_IMPACT"],
        }

    details = result.get("details", {})
    score = result.get("score", 0)
    sample_size = result.get("sample_size", 0)

    components = [{
        "name": "Life Impact (System Average)",
        "score": score,
        "weight": "100%",
        "summary": f"Averaged across {sample_size} user{'s' if sample_size != 1 else ''}",
        "items": [
            {"label": "Goal Progress", "value": f"{details.get('goal_progress', 0)}%",
             "weight": "30%"},
            {"label": "Routine Adherence", "value": f"{details.get('routine_adherence', 0)}%",
             "weight": "40%"},
            {"label": "Domain Engagement", "value": f"{details.get('engagement_depth', 0)}%",
             "weight": "30%"},
        ],
    }]

    return {
        "target": "LIFE_IMPACT",
        "score": score,
        "status": _score_status(score),
        "components": components,
        "available_scans": ["LIFE_IMPACT"],
    }


def _score_status(score):
    if score is None:
        return "UNKNOWN"
    if score >= 90:
        return "OPTIMAL"
    if score >= 70:
        return "NOMINAL"
    if score >= 40:
        return "DEGRADED"
    return "CRITICAL"


# =============================================================================
# DIAGNOSTIC SCAN REGISTRY
# =============================================================================

# Maps scan targets to their scan functions.
# Each scan function returns a structured dict with checks, hypothesis,
# and recommended next step.
DIAGNOSTIC_SCANS = {}


def _register_scan(target_name):
    """Decorator to register a diagnostic scan function."""
    def decorator(func):
        DIAGNOSTIC_SCANS[target_name] = func
        return func
    return decorator


def run_diagnostic_scan(target):
    """
    Run a targeted diagnostic scan.

    Args:
        target: Scan target name (e.g., "INFRASTRUCTURE", "SIGNAL_DROUGHT")

    Returns:
        dict with: target, status (OK/DEGRADED/FAIL), summary, checks (list),
        root_cause_hypothesis, recommended_next_step, related_entities
    """
    target = target.upper().replace("-", "_")
    scan_fn = DIAGNOSTIC_SCANS.get(target)

    if not scan_fn:
        return {
            "target": target,
            "status": "UNSUPPORTED",
            "summary": f"No diagnostic scan registered for '{target}'.",
            "checks": [],
            "available_scans": list(DIAGNOSTIC_SCANS.keys()),
        }

    try:
        result = scan_fn()
        result["target"] = target
        return result
    except Exception as e:
        logger.error("Diagnostic scan failed for %s: %s", target, e, exc_info=True)
        return {
            "target": target,
            "status": "ERROR",
            "summary": f"Scan failed: {str(e)[:300]}",
            "checks": [],
            "error": str(e)[:500],
        }


# =============================================================================
# SCAN: INFRASTRUCTURE
# =============================================================================


@_register_scan("INFRASTRUCTURE")
def _scan_infrastructure():
    """Full diagnostic scan for infrastructure health."""
    from apps.core.ai_observability.health_scoring import (
        compute_engine_health,
        compute_intelligence_freshness,
        compute_scheduler_health,
    )

    checks = []
    issues = []

    # Check 1: Scheduler heartbeats
    scheduler = compute_scheduler_health()
    sd = scheduler.get("details", {})

    ise_status = sd.get("ise", {}).get("status", "OFFLINE")
    checks.append(_check(
        "ISE Scheduler Heartbeat",
        "OK" if ise_status == "ALIVE" else "FAIL",
        f"Status: {ise_status}, drift: {sd.get('ise', {}).get('drift_seconds', '?')}s",
    ))
    if ise_status != "ALIVE":
        issues.append(f"ISE heartbeat is {ise_status}")

    same_status = sd.get("same", {}).get("status", "OFFLINE")
    checks.append(_check(
        "SAME Scheduler Heartbeat",
        "OK" if same_status == "ALIVE" else "FAIL" if same_status == "OFFLINE" else "WARN",
        f"Status: {same_status}, drift: {sd.get('same', {}).get('drift_seconds', '?')}s",
    ))
    if same_status == "OFFLINE":
        issues.append(f"SAME heartbeat is {same_status}")

    # Check 2: Celery Beat health
    beat_running = sd.get("celery_beat", {}).get("running", False)
    checks.append(_check(
        "Celery Beat",
        "OK" if beat_running else "FAIL",
        "Running" if beat_running else "NOT RUNNING",
    ))
    if not beat_running:
        issues.append("Celery Beat is not dispatching tasks")

    # Check 3: Failed tasks
    failed_count = sd.get("failed_tasks", {}).get("count", 0)
    failed_names = sd.get("failed_tasks", {}).get("names", [])
    checks.append(_check(
        "ISE Task Health",
        "OK" if failed_count == 0 else "WARN" if failed_count <= 2 else "FAIL",
        f"{failed_count} failed tasks" + (f": {', '.join(failed_names)}" if failed_names else ""),
    ))
    if failed_count > 0:
        issues.append(f"{failed_count} ISE tasks in failed state: {', '.join(failed_names)}")

    # Check 4: Engine heartbeats
    engine = compute_engine_health()
    ed = engine.get("details", {})
    pct_ok = ed.get("heartbeats", {}).get("pct_ok", 1.0)
    checks.append(_check(
        "Engine Heartbeat Distribution",
        "OK" if pct_ok >= 0.9 else "WARN" if pct_ok >= 0.7 else "FAIL",
        f"{pct_ok * 100:.0f}% engines reporting OK ({ed.get('heartbeats', {}).get('ok', 0)}/{ed.get('heartbeats', {}).get('total', 0)})",
    ))
    if pct_ok < 0.9:
        issues.append(f"Only {pct_ok * 100:.0f}% of engines have OK heartbeats")

    # Check 5: Error rate
    error_rate = ed.get("error_rate_30m", {}).get("rate", 0)
    checks.append(_check(
        "30-Minute Error Rate",
        "OK" if error_rate < 0.05 else "WARN" if error_rate < 0.15 else "FAIL",
        f"{error_rate * 100:.1f}% ({ed.get('error_rate_30m', {}).get('error_runs', 0)} errors / {ed.get('error_rate_30m', {}).get('total_runs', 0)} runs)",
    ))
    if error_rate >= 0.05:
        issues.append(f"30m error rate at {error_rate * 100:.1f}%")

    # Check 6: Intelligence freshness
    freshness = compute_intelligence_freshness()
    fd = freshness.get("details", {})
    stale_tasks = [k for k, v in fd.items() if isinstance(v, dict) and v.get("status") in ("STALE", "CRITICAL", "NEVER_RUN", "NOT_FOUND")]
    checks.append(_check(
        "Intelligence Task Freshness",
        "OK" if not stale_tasks else "WARN" if len(stale_tasks) <= 1 else "FAIL",
        f"{len(stale_tasks)} stale/missing tasks" + (f": {', '.join(stale_tasks)}" if stale_tasks else ""),
    ))
    if stale_tasks:
        issues.append(f"Stale intelligence tasks: {', '.join(stale_tasks)}")

    # Check 7: P1 anomalies
    p1_count = ed.get("p1_anomalies", {}).get("count", 0)
    checks.append(_check(
        "Active P1 Anomalies",
        "OK" if p1_count == 0 else "FAIL",
        f"{p1_count} active P1 anomalies",
    ))
    if p1_count > 0:
        issues.append(f"{p1_count} active P1 anomalies")

    # Determine overall status
    fail_count = sum(1 for c in checks if c["status"] == "FAIL")
    warn_count = sum(1 for c in checks if c["status"] == "WARN")

    if fail_count >= 2:
        overall = "FAIL"
    elif fail_count == 1 or warn_count >= 3:
        overall = "DEGRADED"
    elif warn_count > 0:
        overall = "WARN"
    else:
        overall = "OK"

    # Build hypothesis
    if issues:
        hypothesis = "Infrastructure degradation detected. " + "; ".join(issues[:3]) + "."
        if len(issues) > 3:
            hypothesis += f" ({len(issues) - 3} additional issues.)"
    else:
        hypothesis = "Infrastructure is healthy. All checks passed."

    return {
        "status": overall,
        "summary": f"{fail_count} failures, {warn_count} warnings across {len(checks)} checks",
        "checks": checks,
        "root_cause_hypothesis": hypothesis,
        "recommended_next_step": _infra_recommendation(issues),
        "related_entities": {
            "scheduler_score": scheduler.get("score"),
            "engine_score": engine.get("score"),
            "freshness_score": freshness.get("score"),
        },
    }


def _infra_recommendation(issues):
    if not issues:
        return "No action needed."
    issue_str = " ".join(issues).lower()
    if "celery beat" in issue_str or "not dispatching" in issue_str:
        return "Check Celery Beat process on Railway. Restart the Beat service if scheduling has stopped."
    if "heartbeat" in issue_str and "offline" in issue_str:
        return "Scheduler heartbeat offline. Check if Celery Beat process is running on Railway."
    if "failed" in issue_str and "task" in issue_str:
        return "Failed ISE tasks. Check Celery worker logs for task error details."
    if "p1" in issue_str:
        return "Active P1 anomalies require immediate attention. Review watchlist for details."
    if "error rate" in issue_str:
        return "Elevated error rate. Check recent EngineRun errors in Diagnostics Console."
    return "Review the failing checks above and address the highest-severity items first."


# =============================================================================
# SCAN: LIFE_IMPACT
# =============================================================================


@_register_scan("LIFE_IMPACT")
def _scan_life_impact():
    """Diagnostic scan for Life Impact score."""
    checks = []
    issues = []

    # Check 1: Goals exist
    try:
        from apps.purpose.models import GoalMilestone, LifeGoal
        active_goals = LifeGoal.objects.filter(status="active").count()
        total_milestones = GoalMilestone.objects.filter(goal__status="active").count()
        completed_milestones = GoalMilestone.objects.filter(goal__status="active", status="completed").count()

        checks.append(_check(
            "Active Goals",
            "OK" if active_goals > 0 else "FAIL",
            f"{active_goals} active goals, {completed_milestones}/{total_milestones} milestones completed",
        ))
        if active_goals == 0:
            issues.append("No active goals exist in the system")
        elif total_milestones == 0:
            issues.append("Goals exist but no milestones are defined")
    except Exception as e:
        checks.append(_check("Active Goals", "ERROR", str(e)[:200]))

    # Check 2: Routine adherence
    try:
        from apps.life.models import Task
        cutoff = timezone.now().date() - timedelta(days=7)
        total_tasks = Task.objects.filter(due_date__gte=cutoff).count()
        completed_tasks = Task.objects.filter(due_date__gte=cutoff, is_complete=True).count()
        adherence = int((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0

        checks.append(_check(
            "Routine Adherence (7d)",
            "OK" if adherence >= 60 else "WARN" if adherence >= 30 else "FAIL",
            f"{adherence}% ({completed_tasks}/{total_tasks} tasks completed)",
        ))
        if total_tasks == 0:
            issues.append("No tasks with due dates in the last 7 days")
        elif adherence < 30:
            issues.append(f"Very low routine adherence: {adherence}%")
    except Exception as e:
        checks.append(_check("Routine Adherence", "ERROR", str(e)[:200]))

    # Check 3: Domain engagement
    try:
        from apps.core.domain_registry import registry
        all_domains = registry.get_all()
        active_count = 0
        inactive_domains = []
        for name in all_domains:
            from apps.core.ai_observability.maturity_engine import _domain_has_recent_data
            if _domain_has_recent_data(name):
                active_count += 1
            else:
                inactive_domains.append(name)
        engagement = int((active_count / len(all_domains)) * 100) if all_domains else 0

        checks.append(_check(
            "Domain Engagement (30d)",
            "OK" if engagement >= 50 else "WARN" if engagement >= 25 else "FAIL",
            f"{active_count}/{len(all_domains)} domains active" +
            (f" (inactive: {', '.join(inactive_domains[:5])})" if inactive_domains else ""),
        ))
        if engagement < 25:
            issues.append(f"Low domain engagement: {engagement}% — {len(inactive_domains)} domains inactive")
    except Exception as e:
        checks.append(_check("Domain Engagement", "ERROR", str(e)[:200]))

    # Check 4: User sample size
    try:
        from apps.users.models import User
        eligible = User.objects.filter(is_active=True, is_staff=False).count()
        checks.append(_check(
            "Eligible User Base",
            "OK" if eligible > 0 else "WARN",
            f"{eligible} active non-staff users",
        ))
        if eligible == 0:
            issues.append("No active non-staff users for life impact scoring")
    except Exception as e:
        checks.append(_check("User Base", "ERROR", str(e)[:200]))

    fail_count = sum(1 for c in checks if c["status"] == "FAIL")
    warn_count = sum(1 for c in checks if c["status"] == "WARN")

    if fail_count >= 2:
        overall = "FAIL"
    elif fail_count == 1 or warn_count >= 2:
        overall = "DEGRADED"
    elif warn_count > 0:
        overall = "WARN"
    else:
        overall = "OK"

    if issues:
        hypothesis = "Life Impact is low because: " + "; ".join(issues[:3]) + "."
    else:
        hypothesis = "Life Impact scoring is healthy. All factors contributing."

    return {
        "status": overall,
        "summary": f"{fail_count} failures, {warn_count} warnings across {len(checks)} checks",
        "checks": checks,
        "root_cause_hypothesis": hypothesis,
        "recommended_next_step": _life_impact_recommendation(issues),
        "related_entities": {},
    }


def _life_impact_recommendation(issues):
    if not issues:
        return "No action needed."
    issue_str = " ".join(issues).lower()
    if "no active goals" in issue_str:
        return "Create life goals in the Purpose module to begin tracking progress."
    if "no milestones" in issue_str:
        return "Add milestones to existing goals to enable progress tracking."
    if "adherence" in issue_str:
        return "Low task completion. Check if reminder notifications are firing."
    if "inactive" in issue_str or "engagement" in issue_str:
        return "Low domain engagement. Log data in underused domains to increase coverage."
    return "Review the failing checks and address user engagement gaps."


# =============================================================================
# SCAN: SIGNAL_DROUGHT
# =============================================================================


@_register_scan("SIGNAL_DROUGHT")
def _scan_signal_drought():
    """Diagnostic scan for Signal Drought anomaly."""
    checks = []
    issues = []
    now = timezone.now()

    # Check 1: Signal ingestion pipeline
    try:
        from apps.core.ai_insights.models import Insight
        recent_insights = Insight.objects.filter(
            created_at__gte=now - timedelta(hours=24),
        ).count()
        checks.append(_check(
            "Signal Ingestion (Insights 24h)",
            "OK" if recent_insights > 0 else "FAIL",
            f"{recent_insights} insights generated in last 24h",
        ))
        if recent_insights == 0:
            issues.append("No insights generated in the last 24 hours")
    except Exception as e:
        checks.append(_check("Signal Ingestion", "ERROR", str(e)[:200]))

    # Check 2: Predictions pipeline
    try:
        from apps.core.ai_predictions.models import Prediction
        recent_predictions = Prediction.objects.filter(
            created_at__gte=now - timedelta(hours=24),
        ).count()
        checks.append(_check(
            "Signal Ingestion (Predictions 24h)",
            "OK" if recent_predictions > 0 else "WARN",
            f"{recent_predictions} predictions generated in last 24h",
        ))
        if recent_predictions == 0:
            issues.append("No predictions generated in the last 24 hours")
    except Exception as e:
        checks.append(_check("Prediction Pipeline", "ERROR", str(e)[:200]))

    # Check 3: Signal snapshot freshness
    try:
        from apps.core.ai_eae.models import SignalSnapshot
        latest = SignalSnapshot.objects.order_by("-updated_at").first()
        if latest:
            age_hours = (now - latest.updated_at).total_seconds() / 3600
            checks.append(_check(
                "Signal Snapshot Freshness",
                "OK" if age_hours < 26 else "WARN" if age_hours < 48 else "FAIL",
                f"Latest snapshot is {age_hours:.1f} hours old",
            ))
            if age_hours >= 26:
                issues.append(f"Signal snapshots are {age_hours:.0f}h stale")
        else:
            checks.append(_check("Signal Snapshot Freshness", "FAIL", "No snapshots found"))
            issues.append("No signal snapshots exist")
    except ImportError:
        checks.append(_check("Signal Snapshot Freshness", "WARN", "SignalSnapshot model not available"))
    except Exception as e:
        checks.append(_check("Signal Snapshot Freshness", "ERROR", str(e)[:200]))

    # Check 4: Signal aggregation task (Celery Beat, not ISE scheduler)
    try:
        from django.conf import settings as django_settings
        beat_schedule = getattr(django_settings, 'CELERY_BEAT_SCHEDULE', {})
        # Find the entry with task "core.compute_nightly_signals"
        beat_entry = None
        beat_key = None
        for key, entry in beat_schedule.items():
            if entry.get("task") == "core.compute_nightly_signals":
                beat_entry = entry
                beat_key = key
                break

        if beat_entry:
            # Verify the task module is importable
            try:
                from apps.core.ai_eae.tasks import compute_nightly_signals  # noqa: F401
                task_importable = True
            except ImportError:
                task_importable = False

            if task_importable:
                checks.append(_check(
                    "Signal Aggregation Task",
                    "OK",
                    f"Celery Beat entry '{beat_key}' registered and task importable",
                ))
            else:
                checks.append(_check(
                    "Signal Aggregation Task",
                    "FAIL",
                    f"Celery Beat entry '{beat_key}' exists but task import failed",
                ))
                issues.append("Signal aggregation task import failed")
        else:
            checks.append(_check("Signal Aggregation Task", "FAIL", "Task not in CELERY_BEAT_SCHEDULE"))
            issues.append("compute_nightly_signals not registered in Celery Beat")
    except Exception as e:
        checks.append(_check("Signal Aggregation Task", "ERROR", str(e)[:200]))

    # Check 5: Per-domain signal health (use cache to avoid timeout)
    try:
        from apps.core.ai_observability.ops_telemetry import _get_signal_health
        sh = _get_signal_health() or {}
        silent_domains = sh.get("domains_silent", 0)
        stalest = sh.get("stalest_domain", "?")
        stalest_hours = sh.get("stalest_hours", 0)
        checks.append(_check(
            "Domain Signal Coverage",
            "OK" if silent_domains == 0 else "WARN" if silent_domains <= 2 else "FAIL",
            f"{silent_domains} silent domains. Stalest: {stalest} ({stalest_hours:.0f}h)",
        ))
        if silent_domains > 0:
            issues.append(f"{silent_domains} domains are signal-silent (stalest: {stalest})")
    except Exception as e:
        checks.append(_check("Domain Signal Coverage", "ERROR", str(e)[:200]))

    fail_count = sum(1 for c in checks if c["status"] == "FAIL")
    warn_count = sum(1 for c in checks if c["status"] == "WARN")

    if fail_count >= 2:
        overall = "FAIL"
    elif fail_count == 1 or warn_count >= 2:
        overall = "DEGRADED"
    elif warn_count > 0:
        overall = "WARN"
    else:
        overall = "OK"

    if issues:
        hypothesis = "Signal drought caused by: " + "; ".join(issues[:3]) + "."
    else:
        hypothesis = "Signal pipeline is healthy. No drought detected."

    return {
        "status": overall,
        "summary": f"{fail_count} failures, {warn_count} warnings across {len(checks)} checks",
        "checks": checks,
        "root_cause_hypothesis": hypothesis,
        "recommended_next_step": _signal_drought_recommendation(issues),
        "related_entities": {},
    }


def _signal_drought_recommendation(issues):
    if not issues:
        return "No action needed."
    issue_str = " ".join(issues).lower()
    if "snapshot" in issue_str and ("stale" in issue_str or "not exist" in issue_str):
        return "Signal snapshot job not running. Trigger manually: POST /admin-console/ops/trigger-signals/"
    if "aggregation task" in issue_str and "disabled" in issue_str:
        return "Signal aggregation task is disabled. Re-enable in scheduler."
    if "no insights" in issue_str:
        return "Insight pipeline not producing output. Check PIE engine runs in Diagnostics Console."
    return "Review signal pipeline health and trigger manual signal aggregation."


# =============================================================================
# SCAN: ENGINE_STARVATION
# =============================================================================


@_register_scan("ENGINE_STARVATION")
def _scan_engine_starvation():
    """Diagnostic scan for Engine Starvation anomaly."""
    from apps.core.ai_observability.heartbeat import get_cadence_config, get_latest_heartbeats
    from apps.core.ai_observability.models import EngineRun, OpsAnomaly
    from apps.core.ai_observability.ops_aggregates import ALL_ENGINES

    checks = []
    issues = []
    now = timezone.now()

    # Check 1: Which engines are starved?
    heartbeats = get_latest_heartbeats()
    cadence = get_cadence_config()
    starved_engines = []

    for engine_name in ALL_ENGINES:
        cfg = cadence.get(engine_name, {})
        if not cfg.get("enabled", True):
            continue
        interval = cfg.get("interval", 3600)
        hb = heartbeats.get(engine_name, {})
        hb_status = hb.get("status", "OK")
        if hb_status in ("MISSED", "ERROR"):
            # Check if there are any recent runs
            recent_runs = EngineRun.objects.filter(
                engine_name=engine_name,
                started_at__gte=now - timedelta(seconds=interval * 3),
            ).count()
            if recent_runs == 0:
                starved_engines.append(engine_name)

    checks.append(_check(
        "Engine Starvation Check",
        "OK" if not starved_engines else "FAIL",
        f"{len(starved_engines)} starved engines" +
        (f": {', '.join(starved_engines[:5])}" if starved_engines else ""),
    ))
    if starved_engines:
        issues.append(f"Engines with no recent runs: {', '.join(starved_engines)}")

    # Check 2: Scheduler heartbeat (engines need scheduler to trigger them)
    from apps.core.ai_observability.models import SchedulerHeartbeat
    ise_hb = SchedulerHeartbeat.get_for_scheduler("ISE")
    ise_status = ise_hb.status if ise_hb else "OFFLINE"
    checks.append(_check(
        "ISE Scheduler (engine trigger)",
        "OK" if ise_status == "ALIVE" else "FAIL",
        f"ISE status: {ise_status}",
    ))
    if ise_status != "ALIVE":
        issues.append(f"ISE scheduler is {ise_status} — engines cannot be triggered")

    # Check 3: Active starvation anomalies
    starvation_anomalies = list(OpsAnomaly.objects.filter(
        is_active=True,
        anomaly_type="ENGINE_STARVATION",
    ).values_list("engine_name", flat=True))
    checks.append(_check(
        "Active Starvation Anomalies",
        "OK" if not starvation_anomalies else "WARN",
        f"{len(starvation_anomalies)} active" +
        (f": {', '.join(starvation_anomalies[:5])}" if starvation_anomalies else ""),
    ))

    # Check 4: Celery Beat scheduling health
    try:
        from apps.core.scheduler_health import get_scheduler_status
        sched = get_scheduler_status()
        running = sched.get("running", False)
        checks.append(_check(
            "Celery Beat",
            "OK" if running else "FAIL",
            "Running" if running else "NOT RUNNING — check Beat process on Railway",
        ))
        if not running:
            issues.append("Celery Beat is not dispatching tasks — engines will not be scheduled")
    except Exception as e:
        checks.append(_check("Celery Beat", "ERROR", str(e)[:200]))

    fail_count = sum(1 for c in checks if c["status"] == "FAIL")
    warn_count = sum(1 for c in checks if c["status"] == "WARN")

    if fail_count >= 2:
        overall = "FAIL"
    elif fail_count == 1:
        overall = "DEGRADED"
    elif warn_count > 0:
        overall = "WARN"
    else:
        overall = "OK"

    if issues:
        hypothesis = "Engine starvation caused by: " + "; ".join(issues[:3]) + "."
    else:
        hypothesis = "No engine starvation detected. All engines running within expected cadence."

    return {
        "status": overall,
        "summary": f"{fail_count} failures, {warn_count} warnings across {len(checks)} checks",
        "checks": checks,
        "root_cause_hypothesis": hypothesis,
        "recommended_next_step": (
            "Check ISE scheduler and Celery worker status."
            if any("scheduler" in i.lower() or "celery beat" in i.lower() for i in issues)
            else "Trigger manual engine runs for starved engines."
            if starved_engines
            else "No action needed."
        ),
        "related_entities": {
            "starved_engines": starved_engines,
            "starvation_anomalies": starvation_anomalies,
        },
    }


# =============================================================================
# SCAN: INTELLIGENCE (CoS quality)
# =============================================================================


@_register_scan("INTELLIGENCE")
def _scan_intelligence():
    """Diagnostic scan for CoS Intelligence quality."""
    checks = []
    issues = []
    now = timezone.now()

    # Check 1: Memory accumulation
    try:
        from apps.ai.models import ConversationMemory
        total = ConversationMemory.objects.count()
        recent = ConversationMemory.objects.filter(
            created_at__gte=now - timedelta(days=7),
        ).count()
        checks.append(_check(
            "Conversation Memory",
            "OK" if total >= 5 else "WARN" if total > 0 else "FAIL",
            f"{total} total memories, {recent} in last 7 days",
        ))
        if total == 0:
            issues.append("No conversation memories stored")
    except Exception as e:
        checks.append(_check("Conversation Memory", "ERROR", str(e)[:200]))

    # Check 2: Proactive check-in delivery
    try:
        from apps.ai.models import AssistantMessage
        proactive_7d = AssistantMessage.objects.filter(
            is_proactive=True,
            created_at__gte=now - timedelta(days=7),
        ).count()
        checks.append(_check(
            "Proactive Check-in Delivery (7d)",
            "OK" if proactive_7d >= 10 else "WARN" if proactive_7d > 0 else "FAIL",
            f"{proactive_7d} proactive messages delivered",
        ))
        if proactive_7d == 0:
            issues.append("No proactive check-ins delivered in the last 7 days")
    except Exception as e:
        checks.append(_check("Proactive Delivery", "ERROR", str(e)[:200]))

    # Check 3: Domain registry coverage
    try:
        from apps.core.domain_registry import registry
        coverage = registry.get_coverage_summary()
        avg_score = sum(d["coverage_score"] for d in coverage) / len(coverage) if coverage else 0
        no_intents = sum(1 for d in coverage if d["intent_count"] == 0)
        checks.append(_check(
            "Domain Registry Coverage",
            "OK" if avg_score >= 60 else "WARN" if avg_score >= 40 else "FAIL",
            f"Average coverage: {avg_score:.0f}%, {no_intents} domains with no intents",
        ))
        if no_intents > 2:
            issues.append(f"{no_intents} domains have zero intent coverage")
    except Exception as e:
        checks.append(_check("Domain Coverage", "ERROR", str(e)[:200]))

    fail_count = sum(1 for c in checks if c["status"] == "FAIL")
    warn_count = sum(1 for c in checks if c["status"] == "WARN")

    if fail_count >= 2:
        overall = "FAIL"
    elif fail_count == 1 or warn_count >= 2:
        overall = "DEGRADED"
    elif warn_count > 0:
        overall = "WARN"
    else:
        overall = "OK"

    if issues:
        hypothesis = "Intelligence quality degraded because: " + "; ".join(issues[:3]) + "."
    else:
        hypothesis = "Intelligence quality is healthy."

    return {
        "status": overall,
        "summary": f"{fail_count} failures, {warn_count} warnings across {len(checks)} checks",
        "checks": checks,
        "root_cause_hypothesis": hypothesis,
        "recommended_next_step": (
            "Check proactive check-in scheduled task in ISE."
            if "proactive" in " ".join(issues).lower()
            else "Register intent capabilities for undercovered domains."
            if "intent" in " ".join(issues).lower()
            else "No action needed."
        ),
        "related_entities": {},
    }


# =============================================================================
# SCAN: SAFETY
# =============================================================================


@_register_scan("SAFETY")
def _scan_safety():
    """Diagnostic scan for Execution Safety."""
    checks = []
    issues = []
    now = timezone.now()

    # Check 1: 7-day error rate
    try:
        from apps.core.ai_observability.models import EngineRun
        cutoff = now - timedelta(days=7)
        total = EngineRun.objects.filter(started_at__gte=cutoff).count()
        errors = EngineRun.objects.filter(started_at__gte=cutoff, status="error").count()
        rate = (errors / total * 100) if total > 0 else 0
        checks.append(_check(
            "7-Day Execution Error Rate",
            "OK" if rate < 5 else "WARN" if rate < 15 else "FAIL",
            f"{rate:.1f}% ({errors}/{total} runs)",
        ))
        if rate >= 5:
            issues.append(f"Error rate is {rate:.1f}% over 7 days")
    except Exception as e:
        checks.append(_check("Error Rate", "ERROR", str(e)[:200]))

    # Check 2: Validator gate health
    try:
        from apps.core.ai_observability.ops_telemetry import compute_validator_health
        vh = compute_validator_health()
        crash_count = vh.get("crashes_24h", 0)
        block_rate = vh.get("block_rate_1h", 0) * 100
        checks.append(_check(
            "Validator Gate Health",
            "OK" if crash_count == 0 and block_rate < 5 else "WARN" if crash_count <= 1 else "FAIL",
            f"{crash_count} crashes (24h), {block_rate:.1f}% block rate (1h)",
        ))
        if crash_count > 0:
            issues.append(f"Validator gate crashed {crash_count} times in 24h")
    except Exception as e:
        checks.append(_check("Validator Gate", "ERROR", str(e)[:200]))

    fail_count = sum(1 for c in checks if c["status"] == "FAIL")
    warn_count = sum(1 for c in checks if c["status"] == "WARN")

    if fail_count >= 1:
        overall = "FAIL"
    elif warn_count > 0:
        overall = "DEGRADED"
    else:
        overall = "OK"

    if issues:
        hypothesis = "Safety degradation: " + "; ".join(issues) + "."
    else:
        hypothesis = "Execution safety is healthy."

    return {
        "status": overall,
        "summary": f"{fail_count} failures, {warn_count} warnings across {len(checks)} checks",
        "checks": checks,
        "root_cause_hypothesis": hypothesis,
        "recommended_next_step": (
            "Review validator gate crash logs in Diagnostics Console."
            if "crash" in " ".join(issues).lower()
            else "Review EngineRun error logs for recurring failures."
            if issues
            else "No action needed."
        ),
        "related_entities": {},
    }


# =============================================================================
# SCAN: COVERAGE
# =============================================================================


@_register_scan("COVERAGE")
def _scan_coverage():
    """Diagnostic scan for Domain Coverage."""
    checks = []
    issues = []

    try:
        from apps.core.domain_registry import registry
        coverage = registry.get_coverage_summary()

        no_intents = [d["name"] for d in coverage if d["intent_count"] == 0]
        no_context = [d["name"] for d in coverage if not d.get("has_context_builder")]
        no_signals = [d["name"] for d in coverage if d["signal_count"] == 0]
        low_coverage = [d["name"] for d in coverage if d["coverage_score"] < 50]

        checks.append(_check(
            "Intent Registration",
            "OK" if not no_intents else "WARN" if len(no_intents) <= 2 else "FAIL",
            f"{len(no_intents)} domains without intents" +
            (f": {', '.join(no_intents[:5])}" if no_intents else ""),
        ))
        if len(no_intents) > 2:
            issues.append(f"{len(no_intents)} domains lack intent types")

        checks.append(_check(
            "Context Builder Coverage",
            "OK" if not no_context else "WARN",
            f"{len(no_context)} domains without context builders" +
            (f": {', '.join(no_context[:5])}" if no_context else ""),
        ))

        checks.append(_check(
            "Proactive Signal Coverage",
            "OK" if not no_signals else "WARN" if len(no_signals) <= 3 else "FAIL",
            f"{len(no_signals)} domains without proactive signals" +
            (f": {', '.join(no_signals[:5])}" if no_signals else ""),
        ))

        checks.append(_check(
            "Overall Coverage Score",
            "OK" if not low_coverage else "WARN" if len(low_coverage) <= 2 else "FAIL",
            f"{len(low_coverage)} domains below 50% coverage" +
            (f": {', '.join(low_coverage[:5])}" if low_coverage else ""),
        ))
        if len(low_coverage) > 2:
            issues.append(f"{len(low_coverage)} domains have coverage below 50%")

    except Exception as e:
        checks.append(_check("Domain Registry", "ERROR", str(e)[:200]))
        issues.append(f"Failed to read domain registry: {str(e)[:100]}")

    fail_count = sum(1 for c in checks if c["status"] == "FAIL")
    warn_count = sum(1 for c in checks if c["status"] == "WARN")

    if fail_count >= 1:
        overall = "FAIL"
    elif warn_count >= 2:
        overall = "DEGRADED"
    elif warn_count > 0:
        overall = "WARN"
    else:
        overall = "OK"

    if issues:
        hypothesis = "Coverage gaps: " + "; ".join(issues) + "."
    else:
        hypothesis = "Domain coverage is comprehensive."

    return {
        "status": overall,
        "summary": f"{fail_count} failures, {warn_count} warnings across {len(checks)} checks",
        "checks": checks,
        "root_cause_hypothesis": hypothesis,
        "recommended_next_step": (
            "Register capabilities.py intents for undercovered domains."
            if issues
            else "No action needed."
        ),
        "related_entities": {},
    }


# =============================================================================
# SCAN: ERROR_SPIKE (anomaly scan)
# =============================================================================


@_register_scan("ERROR_SPIKE")
def _scan_error_spike():
    """Diagnostic scan for Error Spike anomaly."""
    from apps.core.ai_observability.models import EngineRun, OpsAnomaly

    checks = []
    issues = []
    now = timezone.now()

    # Get affected engines from active anomalies
    affected_engines = list(OpsAnomaly.objects.filter(
        is_active=True,
        anomaly_type="ERROR_SPIKE",
    ).values_list("engine_name", flat=True))

    # Check per-engine error rates
    for engine_name in (affected_engines or ["*ALL*"]):
        qs = EngineRun.objects.filter(started_at__gte=now - timedelta(minutes=30))
        if engine_name != "*ALL*":
            qs = qs.filter(engine_name=engine_name)
        total = qs.count()
        errors = qs.filter(status="error").count()
        rate = (errors / total * 100) if total > 0 else 0

        label = f"Error Rate: {engine_name}" if engine_name != "*ALL*" else "Global 30m Error Rate"
        checks.append(_check(
            label,
            "OK" if rate < 10 else "WARN" if rate < 25 else "FAIL",
            f"{rate:.1f}% ({errors}/{total} runs)",
        ))
        if rate >= 10:
            issues.append(f"{engine_name}: {rate:.1f}% error rate in last 30m")

    # Check for common error types
    try:
        recent_errors = EngineRun.objects.filter(
            started_at__gte=now - timedelta(minutes=30),
            status="error",
        ).values_list("error_type", flat=True)[:20]
        error_types = {}
        for et in recent_errors:
            if et:
                error_types[et] = error_types.get(et, 0) + 1
        if error_types:
            top_error = max(error_types.items(), key=lambda x: x[1])
            checks.append(_check(
                "Dominant Error Type",
                "WARN",
                f"Most common: {top_error[0]} ({top_error[1]} occurrences)",
            ))
    except Exception:
        pass

    fail_count = sum(1 for c in checks if c["status"] == "FAIL")
    warn_count = sum(1 for c in checks if c["status"] == "WARN")

    overall = "FAIL" if fail_count else "DEGRADED" if warn_count else "OK"

    if issues:
        hypothesis = "Error spike in: " + "; ".join(issues[:3]) + "."
    else:
        hypothesis = "No error spike currently active."

    return {
        "status": overall,
        "summary": f"{fail_count} failures, {warn_count} warnings across {len(checks)} checks",
        "checks": checks,
        "root_cause_hypothesis": hypothesis,
        "recommended_next_step": (
            "Open Diagnostics Console filtered by error status to review stack traces."
            if issues
            else "No action needed."
        ),
        "related_entities": {
            "affected_engines": affected_engines,
        },
    }


# =============================================================================
# DEBUG PROMPT GENERATION
# =============================================================================


def generate_debug_prompt(target, scan_result=None, evidence=None):
    """
    Generate a structured debug prompt from diagnostic evidence.

    Args:
        target: The investigation target name
        scan_result: Optional result from run_diagnostic_scan()
        evidence: Optional result from get_metric_evidence()

    Returns:
        str: Formatted markdown debug prompt
    """
    lines = []

    # Header
    lines.append(f"## WLJ Debugging Prompt — {target}")
    lines.append("")

    # Evidence summary
    if evidence:
        lines.append(f"**Target:** {evidence.get('target', target)}")
        lines.append(f"**Current Score:** {evidence.get('score', '?')}")
        lines.append(f"**Status:** {evidence.get('status', '?')}")
        lines.append("")

        for comp in evidence.get("components", []):
            lines.append(f"### {comp.get('name', '?')} (score: {comp.get('score', '?')}, weight: {comp.get('weight', '?')})")
            if comp.get("summary"):
                lines.append(f"*{comp['summary']}*")
            for item in comp.get("items", []):
                penalty_str = f" [penalty: -{item['penalty']}]" if item.get("penalty") else ""
                detail_str = f" — {item['detail']}" if item.get("detail") else ""
                lines.append(f"- **{item['label']}:** {item['value']}{penalty_str}{detail_str}")
            lines.append("")

    # Scan results
    if scan_result and scan_result.get("status") != "UNSUPPORTED":
        lines.append("### DIAGNOSTIC SCAN RESULTS")
        lines.append(f"**Overall:** {scan_result.get('status', '?')}")
        lines.append(f"**Summary:** {scan_result.get('summary', '?')}")
        lines.append("")

        for check in scan_result.get("checks", []):
            status_icon = {"OK": "PASS", "WARN": "WARN", "FAIL": "FAIL", "ERROR": "ERR"}.get(check["status"], check["status"])
            lines.append(f"- [{status_icon}] **{check['name']}** — {check['evidence']}")
        lines.append("")

        if scan_result.get("root_cause_hypothesis"):
            lines.append("### ROOT CAUSE HYPOTHESIS")
            lines.append(scan_result["root_cause_hypothesis"])
            lines.append("")

        if scan_result.get("recommended_next_step"):
            lines.append("### RECOMMENDED NEXT STEP")
            lines.append(scan_result["recommended_next_step"])
            lines.append("")

    # Investigation steps
    lines.append("### INVESTIGATION STEPS")
    lines.append(f"1. Trace the {target} subsystem in `apps/core/ai_observability/`")
    lines.append("2. Check recent EngineRun logs for related engines")
    lines.append("3. Review the canonical data sources feeding the score")
    lines.append("4. Determine root cause from structured evidence above")
    lines.append("5. Propose minimal fix")
    lines.append("6. Verify: `python3 manage.py test apps.core.ai_observability -v 1 --failfast`")

    return "\n".join(lines)
