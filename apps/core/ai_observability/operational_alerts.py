"""
COAS — Operational Alerts.

State-change alert detection, CoS chat injection, and diagnostic
prompt generation. Called by the COAS scheduled job after scoring.

STATE-CHANGE ALERTING (not cooldown-based):
  - Only injects CoS chat alerts when severity CHANGES (worsens or recovers)
  - Same severity persisting = no duplicate alert
  - Recovery from alert/critical = resolve + notify

Alert thresholds:
    80-100: Healthy (resolve any open alert, notify recovery)
    60-79:  Warning (create record, log only, no chat injection)
    40-59:  Alert (create record + inject into admin CoS chats)
    <40:    Critical (record + inject chat + generate diagnostic prompt)

Diagnostic prompts are generated for CRITICAL alerts only.

Project: Whole Life Journey
Path: apps/core/ai_observability/operational_alerts.py
"""

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

# Score thresholds
THRESHOLD_HEALTHY = 80   # At or above = healthy
THRESHOLD_ALERT = 60     # Below this = admin alert
THRESHOLD_CRITICAL = 40  # Below this = critical + diagnostic prompt

# Severity ordering for comparison (higher = worse)
_SEVERITY_ORDER = {"warning": 1, "alert": 2, "critical": 3}


def _classify_severity(score):
    """Classify a health score into a severity level."""
    if score >= THRESHOLD_HEALTHY:
        return None  # Healthy, no alert
    elif score >= THRESHOLD_ALERT:
        return "warning"
    elif score >= THRESHOLD_CRITICAL:
        return "alert"
    else:
        return "critical"


def _severity_is_worse(new_severity, old_severity):
    """Return True if new_severity is worse than old_severity."""
    return _SEVERITY_ORDER.get(new_severity, 0) > _SEVERITY_ORDER.get(old_severity, 0)


def check_and_alert(scores):
    """
    Evaluate all subsystem scores and create alerts on state changes.

    Uses state-change logic:
      - New degradation: healthy → degraded = create alert
      - Severity worsens: existing open alert escalated = new alert, close old
      - Same severity persists: no action
      - Recovery: degraded → healthy = resolve open alert, notify

    Args:
        scores: dict from compute_all_scores() with keys:
            scheduler, engine, freshness, overall

    Returns:
        list of created OperationalAlert instances
    """
    from apps.core.ai_observability.models import OperationalAlert

    now = timezone.now()
    created_alerts = []

    subsystems = [
        ("scheduler", scores.get("scheduler", {})),
        ("engine", scores.get("engine", {})),
        ("freshness", scores.get("freshness", {})),
        ("overall", scores.get("overall", {})),
    ]

    for subsystem_name, subsystem_data in subsystems:
        try:
            score = subsystem_data.get("score")

            # Skip subsystems where scorer failed
            if score is None:
                continue

            details = subsystem_data.get(
                "details", subsystem_data.get("components", {})
            )

            # Find existing open/acknowledged alert for this subsystem
            latest_open = (
                OperationalAlert.objects.filter(
                    subsystem=subsystem_name,
                    status__in=["open", "acknowledged"],
                )
                .order_by("-created_at")
                .first()
            )

            new_severity = _classify_severity(score)

            # --- HEALTHY: resolve any open alert ---
            if new_severity is None:
                if latest_open:
                    was_severe = latest_open.severity in ("alert", "critical")
                    latest_open.status = "resolved"
                    latest_open.resolved_at = now
                    latest_open.save(update_fields=["status", "resolved_at"])
                    logger.info(
                        "COAS: Resolved %s alert for %s (score recovered to %d)",
                        latest_open.severity,
                        subsystem_name,
                        score,
                    )
                    # Notify recovery if it was an alert/critical level
                    if was_severe:
                        recovery_msg = _build_recovery_message(
                            subsystem_name, score, latest_open
                        )
                        _inject_admin_alert(recovery_msg, latest_open)
                continue

            # --- DEGRADED: determine if state changed ---
            if latest_open:
                if new_severity == latest_open.severity:
                    # Same severity persists — no action
                    continue

                if _severity_is_worse(new_severity, latest_open.severity):
                    # Severity worsened — close old, create new
                    latest_open.status = "resolved"
                    latest_open.resolved_at = now
                    latest_open.save(update_fields=["status", "resolved_at"])
                    logger.info(
                        "COAS: Escalated %s → %s for %s",
                        latest_open.severity,
                        new_severity,
                        subsystem_name,
                    )
                else:
                    # Severity improved but still degraded — update existing, no re-alert
                    latest_open.severity = new_severity
                    latest_open.health_score = score
                    latest_open.details = details
                    latest_open.save(
                        update_fields=["severity", "health_score", "details"]
                    )
                    continue

            # --- Create new alert ---
            message = _build_alert_message(
                subsystem_name, score, new_severity, details
            )

            # Diagnostic prompt for critical only
            diagnostic_prompt = ""
            if new_severity == "critical":
                diagnostic_prompt = _build_diagnostic_prompt(
                    subsystem_name, score, details
                )

            dedupe_key = f"{subsystem_name}_{new_severity}"

            alert = OperationalAlert.objects.create(
                subsystem=subsystem_name,
                severity=new_severity,
                status="open",
                health_score=score,
                message=message,
                diagnostic_prompt_text=diagnostic_prompt,
                details=details,
                dedupe_key=dedupe_key,
                last_notified_at=now if new_severity != "warning" else None,
            )
            created_alerts.append(alert)

            logger.warning(
                "COAS alert created: %s %s score=%d",
                new_severity.upper(),
                subsystem_name,
                score,
            )

            # Inject into admin CoS chats (alert and critical only, not warning)
            if new_severity in ("alert", "critical"):
                _inject_admin_alert(message, alert)

        except Exception as e:
            logger.error(
                "COAS: Alert evaluation failed for %s: %s",
                subsystem_name,
                e,
                exc_info=True,
            )

    return created_alerts


# =============================================================================
# MESSAGE BUILDERS
# =============================================================================

_SUBSYSTEM_LABELS = {
    "scheduler": "Scheduler Health",
    "engine": "Engine Health",
    "freshness": "Intelligence Freshness",
    "overall": "Overall System Health",
}


def _build_alert_message(subsystem, score, severity, details):
    """Build a natural-language alert message for CoS chat."""
    severity_label = {
        "warning": "Attention",
        "alert": "ALERT",
        "critical": "CRITICAL",
    }.get(severity, severity.upper())

    subsystem_label = _SUBSYSTEM_LABELS.get(subsystem, subsystem)
    detail_lines = []

    if subsystem == "scheduler":
        ise = details.get("ise", {})
        same = details.get("same", {})
        aps = details.get("apscheduler", {})
        failed = details.get("failed_tasks", {})
        if ise.get("status") != "ALIVE":
            drift = ise.get("drift_seconds")
            drift_str = f" (drift: {drift}s)" if drift is not None else ""
            detail_lines.append(f"ISE status: {ise.get('status', 'UNKNOWN')}{drift_str}")
        if same.get("status") != "ALIVE":
            drift = same.get("drift_seconds")
            drift_str = f" (drift: {drift}s)" if drift is not None else ""
            detail_lines.append(f"SAME status: {same.get('status', 'UNKNOWN')}{drift_str}")
        if not aps.get("running"):
            detail_lines.append("APScheduler process not running")
        if failed.get("count", 0) > 0:
            names = ", ".join(failed.get("names", []))
            detail_lines.append(f"{failed['count']} failed tasks: {names}")

    elif subsystem == "engine":
        hb = details.get("heartbeats", {})
        err = details.get("error_rate_30m", {})
        p1 = details.get("p1_anomalies", {})
        if hb.get("penalty", 0) > 0:
            detail_lines.append(
                f"Engines OK: {hb.get('ok', 0)}/{hb.get('total', 0)} "
                f"({int(hb.get('pct_ok', 0) * 100)}%)"
            )
        if err.get("rate", 0) > 0.05:
            detail_lines.append(
                f"30m error rate: {int(err['rate'] * 100)}% "
                f"({err.get('error_runs', 0)}/{err.get('total_runs', 0)} runs)"
            )
        if p1.get("count", 0) > 0:
            detail_lines.append(f"Active P1 anomalies: {p1['count']}")

    elif subsystem == "freshness":
        stale = [
            name
            for name, info in details.items()
            if isinstance(info, dict)
            and info.get("status") in ("STALE", "CRITICAL", "NEVER_RUN", "NOT_FOUND")
        ]
        if stale:
            detail_lines.append(f"Stale tasks: {', '.join(stale)}")

    elif subsystem == "overall":
        for comp_name, comp_data in details.items():
            if isinstance(comp_data, dict) and (comp_data.get("score") or 100) < THRESHOLD_ALERT:
                detail_lines.append(
                    f"{comp_name}: {comp_data.get('score', '?')}/100"
                )

    detail_str = ""
    if detail_lines:
        detail_str = "\n- " + "\n- ".join(detail_lines)

    return (
        f"[COAS {severity_label}] {subsystem_label} dropped to "
        f"{score}/100.{detail_str}"
    )


def _build_recovery_message(subsystem, score, alert):
    """Build a recovery notification message."""
    subsystem_label = _SUBSYSTEM_LABELS.get(subsystem, subsystem)
    return (
        f"[COAS Recovery] {subsystem_label} has recovered to {score}/100. "
        f"Previous {alert.severity} alert has been resolved."
    )


def _build_diagnostic_prompt(subsystem, score, details):
    """
    Generate a structured diagnostic prompt for Claude Code.

    Only called for critical alerts (score < 40).
    """
    prompt_lines = [
        f"## COAS Critical Alert: {subsystem} Health at {score}/100",
        f"**Timestamp:** {timezone.now().isoformat()}",
        "",
        "### Diagnostic Context",
    ]

    if subsystem == "scheduler":
        ise = details.get("ise", {})
        same = details.get("same", {})
        aps = details.get("apscheduler", {})
        failed = details.get("failed_tasks", {})

        prompt_lines.append(
            f"- ISE heartbeat: {ise.get('status', 'UNKNOWN')} "
            f"(drift: {ise.get('drift_seconds')}s)"
        )
        prompt_lines.append(
            f"- SAME heartbeat: {same.get('status', 'UNKNOWN')} "
            f"(drift: {same.get('drift_seconds')}s)"
        )
        prompt_lines.append(f"- APScheduler running: {aps.get('running', False)}")
        if failed.get("names"):
            prompt_lines.append(f"- Failed tasks: {', '.join(failed['names'])}")
        prompt_lines.extend([
            "",
            "### Suggested Investigation",
            "1. Check `railway logs` for scheduler errors or OOM kills",
            "2. Check APScheduler via `/admin-console/ops/scheduler-health/`",
            "3. Check SchedulerHeartbeat table for ISE/SAME last_tick_at",
            "4. Consider scheduler restart via Ops Wall if APScheduler is dead",
        ])

    elif subsystem == "engine":
        hb = details.get("heartbeats", {})
        err = details.get("error_rate_30m", {})
        p1 = details.get("p1_anomalies", {})

        prompt_lines.append(f"- Engines OK: {hb.get('ok', 0)}/{hb.get('total', 0)}")
        prompt_lines.append(
            f"- 30m error rate: {err.get('rate', 0):.1%} "
            f"({err.get('error_runs', 0)} errors)"
        )
        prompt_lines.append(f"- Active P1 anomalies: {p1.get('count', 0)}")
        prompt_lines.extend([
            "",
            "### Suggested Investigation",
            "1. Check Ops Wall anomaly watchlist for P1 details",
            "2. Review EngineRun errors: "
            "`EngineRun.objects.filter(status='error').order_by('-started_at')[:10]`",
            "3. Check if specific engines are stuck (MISSED heartbeat)",
            "4. Review Celery worker health if SAME-related engines are affected",
        ])

    elif subsystem == "freshness":
        prompt_lines.append("Stale intelligence tasks:")
        for task_name, info in details.items():
            if isinstance(info, dict):
                status = info.get("status", "UNKNOWN")
                ratio = info.get("ratio")
                elapsed = info.get("elapsed_seconds")
                prompt_lines.append(
                    f"- {task_name}: {status} "
                    f"(ratio: {ratio}, elapsed: {elapsed}s, "
                    f"last_status: {info.get('last_status', '?')})"
                )
        prompt_lines.extend([
            "",
            "### Suggested Investigation",
            "1. Check ScheduledIntelligenceTask table for failed/stuck tasks",
            "2. Verify ISE is running (scheduler health check)",
            "3. Check if runner functions are erroring via EngineRun table",
            "4. Manual re-run: call the runner function directly from Django shell",
        ])

    elif subsystem == "overall":
        prompt_lines.append("Subsystem scores:")
        for comp_name, comp_data in details.items():
            if isinstance(comp_data, dict):
                prompt_lines.append(
                    f"- {comp_name}: {comp_data.get('score', '?')}/100"
                )
        prompt_lines.extend([
            "",
            "### Suggested Investigation",
            "1. Identify which subsystem is dragging the overall score down",
            "2. Address the lowest-scoring subsystem first",
            "3. Check Ops Wall for real-time system posture",
        ])

    return "\n".join(prompt_lines)


# =============================================================================
# ADMIN CHAT INJECTION
# =============================================================================

def _inject_admin_alert(message, alert):
    """
    Inject an alert message into all admin users' CoS chat conversations.

    Uses the exact pattern from ProactiveCheckInService._create_proactive_message()
    (apps/ai/proactive_checkins.py lines 488-521).

    Args:
        message: str — the alert text
        alert: OperationalAlert — the alert record (for metadata)
    """
    from apps.users.models import User

    try:
        staff_users = User.objects.filter(is_staff=True, is_active=True)
    except Exception as e:
        logger.warning("COAS: Failed to query staff users: %s", e)
        return

    if not staff_users.exists():
        logger.warning("COAS: No active staff users found for alert injection")
        return

    injected_count = 0
    for user in staff_users:
        try:
            from apps.ai.models import AssistantConversation, AssistantMessage

            conversation = AssistantConversation.get_or_create_active(user)
            AssistantMessage.objects.create(
                conversation=conversation,
                role="assistant",
                content=message,
                message_type="insight",
                metadata={
                    "alert_type": "coas",
                    "subsystem": alert.subsystem,
                    "severity": alert.severity,
                    "health_score": alert.health_score,
                    "alert_id": alert.id,
                },
                quick_replies=[],
                is_proactive=True,
            )
            injected_count += 1
        except Exception as e:
            logger.warning(
                "COAS: Failed to inject alert for user %s: %s",
                user.id,
                e,
            )

    logger.info(
        "COAS: Injected %s alert into %d admin chat(s)",
        alert.severity,
        injected_count,
    )
