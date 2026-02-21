"""
SAME — System Autonomous Monitoring Engine.

Deterministic anomaly detection + narrative generation. No OpenAI calls.
Runs locally and produces OpsAnomaly + OpsNarrativeSnapshot records.

Anomaly types:
  - MISSED_RUN: Engine missed its expected cadence
  - ERROR_SPIKE: Error rate exceeds baseline
  - CONFIDENCE_VOLATILITY: UAL confidence stddev too high
  - SUPPRESSION_STORM: ICQG suppression rate exceeds baseline
  - LOOPING_REMINDER: Same topic fired repeatedly in short window
  - ENGINE_STARVATION: Engine never running despite signals
  - DELIVERY_RETRY_SPIKE: DNE retry rate exceeds baseline

Project: Whole Life Journey
Path: apps/core/ai_observability/same_engine.py
"""

import logging
from datetime import timedelta

from django.db.models import Avg, Count, StdDev
from django.utils import timezone

logger = logging.getLogger(__name__)


def run_same():
    """
    Main SAME entry point. Compute anomalies + narrative + integrity, persist all.

    Returns:
        dict with keys: anomalies_created, anomalies_resolved, narrative, integrity
    """
    from apps.core.ai_observability.heartbeat import compute_and_save_heartbeats

    now = timezone.now()

    # Step 1: Compute heartbeats
    heartbeats = compute_and_save_heartbeats()

    # Step 2: Detect anomalies from all sources
    detected = []
    detected.extend(_detect_missed_runs(heartbeats, now))
    detected.extend(_detect_error_spikes(now))
    detected.extend(_detect_confidence_volatility(now))
    detected.extend(_detect_suppression_storm(now))
    detected.extend(_detect_looping_reminders(now))
    detected.extend(_detect_engine_starvation(heartbeats, now))
    detected.extend(_detect_delivery_retry_spike(now))

    # Step 3: Reconcile anomalies (activate new, resolve old)
    stats = _reconcile_anomalies(detected, now)

    # Step 3.5: Escalation state machine
    escalated = _escalate_anomalies(now)

    # Step 3.6: Autonomous remediation (if enabled)
    remediated = _run_autonomous_remediation(now)

    # Step 4: Generate narrative
    narrative = _generate_narrative(heartbeats, detected, now)

    # Step 5: Compute System Integrity Index
    integrity = _compute_integrity_snapshot(heartbeats, now)

    return {
        "anomalies_created": stats["created"],
        "anomalies_resolved": stats["resolved"],
        "anomalies_escalated": escalated,
        "auto_remediated": remediated,
        "narrative": narrative,
        "integrity": integrity,
    }


# =========================================================================
# ANOMALY DETECTORS
# =========================================================================


def _detect_missed_runs(heartbeats, now):
    """Detect engines that missed their expected cadence."""
    anomalies = []

    for hb in heartbeats:
        if hb.status == "MISSED":
            minutes_late = hb.lateness_seconds // 60
            interval_minutes = hb.metadata.get("interval_seconds", 3600) // 60
            severity = "P1" if minutes_late > interval_minutes * 3 else "P2"

            anomalies.append({
                "anomaly_type": "MISSED_RUN",
                "severity": severity,
                "engine_name": hb.engine_name,
                "summary": (
                    f"{hb.engine_name} missed expected cadence — "
                    f"{minutes_late}m overdue (expected every {interval_minutes}m)"
                ),
                "evidence": {
                    "last_run_at": hb.last_run_at.isoformat() if hb.last_run_at else None,
                    "next_expected_at": (
                        hb.next_expected_at.isoformat() if hb.next_expected_at else None
                    ),
                    "lateness_seconds": hb.lateness_seconds,
                },
                "suggested_actions": [
                    {"action": "rerun_engine", "label": f"Re-run {hb.engine_name} now"},
                ],
            })

    return anomalies


def _detect_error_spikes(now):
    """Compare last 30m error rate vs 24h baseline."""
    from apps.core.ai_observability.models import EngineRun
    from apps.core.ai_observability.ops_aggregates import ALL_ENGINES

    thirty_min_ago = now - timedelta(minutes=30)
    twenty_four_h_ago = now - timedelta(hours=24)
    anomalies = []

    for engine in ALL_ENGINES:
        errors_30m = EngineRun.objects.filter(
            engine_name=engine,
            started_at__gte=thirty_min_ago,
            status="error",
        ).count()

        if errors_30m < 3:
            continue

        errors_24h = EngineRun.objects.filter(
            engine_name=engine,
            started_at__gte=twenty_four_h_ago,
            status="error",
        ).count()

        # Normalize 24h to 30m equivalent
        baseline_30m = errors_24h / 48 if errors_24h > 0 else 0

        if baseline_30m > 0 and errors_30m > baseline_30m * 3:
            anomalies.append({
                "anomaly_type": "ERROR_SPIKE",
                "severity": "P1" if errors_30m > 10 else "P2",
                "engine_name": engine,
                "summary": (
                    f"{engine} error spike — {errors_30m} errors in 30m "
                    f"(baseline ~{baseline_30m:.1f}/30m)"
                ),
                "evidence": {
                    "errors_30m": errors_30m,
                    "errors_24h": errors_24h,
                    "baseline_30m": round(baseline_30m, 1),
                },
                "suggested_actions": [
                    {"action": "rerun_engine", "label": f"Re-run {engine} now"},
                ],
            })
        elif errors_30m >= 3 and baseline_30m == 0:
            # First errors ever
            anomalies.append({
                "anomaly_type": "ERROR_SPIKE",
                "severity": "P2",
                "engine_name": engine,
                "summary": (
                    f"{engine} showing errors — {errors_30m} in last 30m "
                    f"(no baseline established)"
                ),
                "evidence": {
                    "errors_30m": errors_30m,
                    "errors_24h": errors_24h,
                },
                "suggested_actions": [
                    {"action": "rerun_engine", "label": f"Re-run {engine} now"},
                ],
            })

    return anomalies


def _detect_confidence_volatility(now):
    """UAL confidence stddev > 0.3 across last 24h decisions."""
    from apps.core.ai_observability.models import DecisionRecord

    twenty_four_h_ago = now - timedelta(hours=24)

    stats = DecisionRecord.objects.filter(
        engine_name="UAL",
        decision_type="arbitration",
        confidence__isnull=False,
        created_at__gte=twenty_four_h_ago,
    ).aggregate(
        stddev=StdDev("confidence"),
        avg=Avg("confidence"),
        count=Count("id"),
    )

    if (
        stats["count"]
        and stats["count"] >= 5
        and stats["stddev"]
        and stats["stddev"] > 0.3
    ):
        return [{
            "anomaly_type": "CONFIDENCE_VOLATILITY",
            "severity": "P3",
            "engine_name": "UAL",
            "summary": (
                f"UAL confidence volatile — stddev={stats['stddev']:.2f}, "
                f"avg={stats['avg']:.2f} across {stats['count']} decisions"
            ),
            "evidence": {
                "stddev": round(stats["stddev"], 3),
                "avg": round(stats["avg"], 3),
                "count": stats["count"],
            },
            "suggested_actions": [],
        }]

    return []


def _detect_suppression_storm(now):
    """ICQG suppression rate in 30m exceeds 3x the 7d baseline."""
    from apps.core.ai_observability.models import DecisionRecord

    thirty_min_ago = now - timedelta(minutes=30)
    seven_days_ago = now - timedelta(days=7)

    count_30m = DecisionRecord.objects.filter(
        engine_name="ICQG",
        decision_type="suppression",
        created_at__gte=thirty_min_ago,
    ).count()

    if count_30m < 5:
        return []

    count_7d = DecisionRecord.objects.filter(
        engine_name="ICQG",
        decision_type="suppression",
        created_at__gte=seven_days_ago,
    ).count()

    # Normalize 7d to 30m equivalent
    baseline_30m = count_7d / (7 * 48) if count_7d > 0 else 0

    if baseline_30m > 0 and count_30m > baseline_30m * 3:
        return [{
            "anomaly_type": "SUPPRESSION_STORM",
            "severity": "P2",
            "engine_name": "ICQG",
            "summary": (
                f"ICQG suppression storm — {count_30m} suppressions in 30m "
                f"(7d baseline ~{baseline_30m:.1f}/30m)"
            ),
            "evidence": {
                "count_30m": count_30m,
                "count_7d": count_7d,
                "baseline_30m": round(baseline_30m, 1),
            },
            "suggested_actions": [
                {"action": "clear_suppression_cache", "label": "Clear ICQG suppression cache"},
            ],
        }]

    return []


def _detect_looping_reminders(now):
    """Same guidance topic fired repeatedly within a short window."""
    from apps.core.ai_observability.models import DecisionRecord

    two_hours_ago = now - timedelta(hours=2)

    # Look for repeated delivery decisions with same content
    deliveries = (
        DecisionRecord.objects.filter(
            engine_name="DNE",
            created_at__gte=two_hours_ago,
        )
        .values("decision")
        .annotate(count=Count("id"))
        .filter(count__gte=3)
    )

    anomalies = []
    for entry in deliveries:
        anomalies.append({
            "anomaly_type": "LOOPING_REMINDER",
            "severity": "P2",
            "engine_name": "DNE",
            "summary": (
                f"Looping reminder detected — '{entry['decision'][:60]}' "
                f"fired {entry['count']}x in 2h"
            ),
            "evidence": {
                "decision": entry["decision"][:200],
                "count": entry["count"],
                "window_hours": 2,
            },
            "suggested_actions": [
                {"action": "clear_suppression_cache", "label": "Clear ICQG cache"},
            ],
        })

    return anomalies


def _detect_engine_starvation(heartbeats, now):
    """Engine never running even though it should be (no runs at all in 24h)."""
    from apps.core.ai_observability.models import EngineRun
    from apps.core.ai_observability.ops_aggregates import ALL_ENGINES

    twenty_four_h_ago = now - timedelta(hours=24)
    anomalies = []

    # Only flag engines that should be running frequently
    frequent_engines = {"UAL", "SAE", "PIE", "DNE", "PGE", "ICQG"}

    for engine in ALL_ENGINES:
        if engine not in frequent_engines:
            continue

        count_24h = EngineRun.objects.filter(
            engine_name=engine,
            started_at__gte=twenty_four_h_ago,
        ).count()

        if count_24h == 0:
            # Check if it ever ran
            has_any = EngineRun.objects.filter(engine_name=engine).exists()
            if has_any:
                anomalies.append({
                    "anomaly_type": "ENGINE_STARVATION",
                    "severity": "P1",
                    "engine_name": engine,
                    "summary": (
                        f"{engine} has not run in 24 hours — "
                        f"possible scheduler failure or configuration issue"
                    ),
                    "evidence": {
                        "runs_24h": 0,
                        "has_historical_runs": True,
                    },
                    "suggested_actions": [
                        {"action": "rerun_engine", "label": f"Re-run {engine} now"},
                        {"action": "restart_scheduler", "label": "Restart ISE scheduler"},
                    ],
                })

    return anomalies


def _detect_delivery_retry_spike(now):
    """DNE retry/re-delivery rate in 30m exceeds 3x baseline."""
    from apps.core.ai_observability.models import EngineRun

    thirty_min_ago = now - timedelta(minutes=30)
    twenty_four_h_ago = now - timedelta(hours=24)

    count_30m = EngineRun.objects.filter(
        engine_name="DNE",
        started_at__gte=thirty_min_ago,
    ).count()

    if count_30m < 5:
        return []

    count_24h = EngineRun.objects.filter(
        engine_name="DNE",
        started_at__gte=twenty_four_h_ago,
    ).count()

    baseline_30m = count_24h / 48 if count_24h > 0 else 0

    if baseline_30m > 0 and count_30m > baseline_30m * 3:
        return [{
            "anomaly_type": "DELIVERY_RETRY_SPIKE",
            "severity": "P2",
            "engine_name": "DNE",
            "summary": (
                f"DNE delivery spike — {count_30m} runs in 30m "
                f"(baseline ~{baseline_30m:.1f}/30m)"
            ),
            "evidence": {
                "count_30m": count_30m,
                "count_24h": count_24h,
                "baseline_30m": round(baseline_30m, 1),
            },
            "suggested_actions": [],
        }]

    return []


# =========================================================================
# ANOMALY RECONCILIATION
# =========================================================================


def _reconcile_anomalies(detected, now):
    """
    Reconcile detected anomalies with existing active ones.

    - New anomalies: create OpsAnomaly records
    - Existing anomalies that match: update timestamp
    - Active anomalies no longer detected: resolve them
    """
    from apps.core.ai_observability.models import OpsAnomaly

    created = 0
    resolved = 0

    # Build a set of (anomaly_type, engine_name) for detected anomalies
    detected_keys = set()
    for d in detected:
        key = (d["anomaly_type"], d["engine_name"])
        detected_keys.add(key)

    # Resolve active anomalies that are no longer detected
    active_anomalies = OpsAnomaly.objects.filter(is_active=True)
    for anomaly in active_anomalies:
        key = (anomaly.anomaly_type, anomaly.engine_name)
        if key not in detected_keys:
            anomaly.is_active = False
            anomaly.resolved_at = now
            anomaly.save(update_fields=["is_active", "resolved_at", "updated_at"])
            resolved += 1

    # Create or update detected anomalies
    for d in detected:
        existing = OpsAnomaly.objects.filter(
            anomaly_type=d["anomaly_type"],
            engine_name=d["engine_name"],
            is_active=True,
        ).first()

        if existing:
            # Update evidence + summary
            existing.summary = d["summary"]
            existing.evidence = d["evidence"]
            existing.severity = d["severity"]
            existing.suggested_actions = d["suggested_actions"]
            existing.save(update_fields=[
                "summary", "evidence", "severity",
                "suggested_actions", "updated_at",
            ])
        else:
            OpsAnomaly.objects.create(
                anomaly_type=d["anomaly_type"],
                severity=d["severity"],
                original_severity=d["severity"],
                engine_name=d["engine_name"],
                summary=d["summary"],
                evidence=d["evidence"],
                suggested_actions=d["suggested_actions"],
                is_active=True,
            )
            created += 1

    return {"created": created, "resolved": resolved}


# =========================================================================
# ESCALATION STATE MACHINE
# =========================================================================

# Escalation rules: (from_severity, minutes_unresolved, to_severity)
ESCALATION_RULES = [
    ("P3", 10, "P2"),   # P3 unresolved > 10 minutes → P2
    ("P2", 20, "P1"),   # P2 unresolved > 20 minutes → P1
]

# Cooldown: minimum minutes between escalations of the same anomaly
ESCALATION_COOLDOWN_MINUTES = 5


def _escalate_anomalies(now):
    """
    Apply escalation state machine to active anomalies.

    Rules:
    - P3 unresolved > 10 minutes → promote to P2
    - P2 unresolved > 20 minutes → promote to P1
    - Cooldown: no re-escalation within 5 minutes
    - Resolution resets escalation (new anomaly starts fresh)
    - P1 is terminal — no further escalation

    Returns:
        int — number of anomalies escalated this cycle.
    """
    from apps.core.ai_observability.models import OpsAnomaly

    escalated = 0
    active = OpsAnomaly.objects.filter(is_active=True)

    for anomaly in active:
        # P1 is terminal — skip
        if anomaly.severity == "P1":
            continue

        for from_sev, minutes_threshold, to_sev in ESCALATION_RULES:
            if anomaly.severity != from_sev:
                continue

            # Check if anomaly has been active long enough
            age_minutes = (now - anomaly.created_at).total_seconds() / 60
            if age_minutes < minutes_threshold:
                continue

            # Cooldown check
            if anomaly.last_escalated_at:
                cooldown_elapsed = (
                    now - anomaly.last_escalated_at
                ).total_seconds() / 60
                if cooldown_elapsed < ESCALATION_COOLDOWN_MINUTES:
                    continue

            # Promote severity
            old_severity = anomaly.severity
            anomaly.severity = to_sev
            anomaly.escalation_count += 1
            anomaly.last_escalated_at = now
            if not anomaly.original_severity:
                anomaly.original_severity = old_severity
            anomaly.summary = (
                f"[ESCALATED {old_severity}→{to_sev}] {anomaly.summary}"
                if "[ESCALATED" not in anomaly.summary
                else anomaly.summary.replace(
                    anomaly.summary.split("]")[0] + "]",
                    f"[ESCALATED {anomaly.original_severity}→{to_sev}]",
                )
            )
            anomaly.save(update_fields=[
                "severity", "escalation_count", "last_escalated_at",
                "original_severity", "summary", "updated_at",
            ])

            logger.info(
                "SAME escalation: %s %s on %s promoted %s → %s "
                "(age=%dm, count=%d)",
                anomaly.anomaly_type, anomaly.id, anomaly.engine_name,
                old_severity, to_sev, int(age_minutes), anomaly.escalation_count,
            )
            escalated += 1
            break  # Only one escalation per anomaly per cycle

    return escalated


# =========================================================================
# AUTONOMOUS REMEDIATION
# =========================================================================

# Feature flag — set to False to disable all autonomous actions
AUTONOMOUS_REMEDIATION_ENABLED = True

# Max auto-actions per SAME cycle (prevents infinite loop)
MAX_AUTO_ACTIONS_PER_CYCLE = 3

# Cooldown: minutes since last auto-action on same anomaly
AUTO_ACTION_COOLDOWN_MINUTES = 30


def _run_autonomous_remediation(now):
    """
    Execute safe automatic actions for eligible anomalies.

    Rules:
    - Only acts on P3 severity anomalies (low risk)
    - Auto-rerun for single MISSED_RUN (P3 only, once per anomaly)
    - Auto-clear suppression cache for SUPPRESSION_STORM (P3 only)
    - Logs every action as a system-initiated AdminIntervention
    - Respects MAX_AUTO_ACTIONS_PER_CYCLE to prevent runaway
    - Respects AUTO_ACTION_COOLDOWN_MINUTES to prevent infinite loops
    - Can be disabled via AUTONOMOUS_REMEDIATION_ENABLED flag

    Returns:
        int — number of auto-actions taken.
    """
    if not AUTONOMOUS_REMEDIATION_ENABLED:
        return 0

    from apps.core.ai_observability.models import AdminIntervention, OpsAnomaly

    actions_taken = 0
    active_p3 = OpsAnomaly.objects.filter(is_active=True, severity="P3")

    for anomaly in active_p3:
        if actions_taken >= MAX_AUTO_ACTIONS_PER_CYCLE:
            break

        # Check cooldown: has this anomaly already been auto-remediated recently?
        recent_auto = AdminIntervention.objects.filter(
            is_system_initiated=True,
            engine_name=anomaly.engine_name,
            created_at__gte=now - timedelta(minutes=AUTO_ACTION_COOLDOWN_MINUTES),
        ).exists()
        if recent_auto:
            continue

        if anomaly.anomaly_type == "MISSED_RUN":
            result = _auto_rerun_engine(anomaly, now)
            if result:
                actions_taken += 1

        elif anomaly.anomaly_type == "SUPPRESSION_STORM":
            result = _auto_clear_suppression(anomaly, now)
            if result:
                actions_taken += 1

    return actions_taken


def _auto_rerun_engine(anomaly, now):
    """Auto-rerun a missed engine (P3 only, system engines only)."""
    import uuid

    from apps.core.ai_observability.models import AdminIntervention

    engine = anomaly.engine_name
    # Only auto-rerun system engines (not user-context engines)
    system_engines = {"DBE", "WIRE", "DNE"}
    if engine not in system_engines:
        return False

    trace_id = str(uuid.uuid4())

    try:
        from apps.core.ai_observability.ops_views import _action_rerun_engine
        result = _action_rerun_engine(engine, trace_id)

        AdminIntervention.objects.create(
            admin_user=None,
            action_type="auto_rerun_engine",
            engine_name=engine,
            trace_id=trace_id,
            notes=f"SAME autonomous remediation: auto-rerun for P3 MISSED_RUN on {engine}",
            result_status=result["status"],
            result_detail=result["detail"],
            is_system_initiated=True,
        )

        logger.info(
            "SAME auto-remediation: rerun %s (trace=%s, result=%s)",
            engine, trace_id, result["status"],
        )
        return True

    except Exception as e:
        logger.warning("SAME auto-remediation failed for %s: %s", engine, e)
        return False


def _auto_clear_suppression(anomaly, now):
    """Auto-clear ICQG suppression cache for P3 suppression storm."""
    import uuid

    from apps.core.ai_observability.models import AdminIntervention

    trace_id = str(uuid.uuid4())

    try:
        from apps.core.ai_observability.ops_views import _action_clear_suppression_cache
        result = _action_clear_suppression_cache("ICQG")

        AdminIntervention.objects.create(
            admin_user=None,
            action_type="auto_clear_suppression",
            engine_name="ICQG",
            trace_id=trace_id,
            notes="SAME autonomous remediation: auto-clear suppression cache for P3 SUPPRESSION_STORM",
            result_status=result["status"],
            result_detail=result["detail"],
            is_system_initiated=True,
        )

        logger.info(
            "SAME auto-remediation: clear suppression (trace=%s, result=%s)",
            trace_id, result["status"],
        )
        return True

    except Exception as e:
        logger.warning("SAME auto-remediation suppression clear failed: %s", e)
        return False


# =========================================================================
# NARRATIVE GENERATION
# =========================================================================


def _generate_narrative(heartbeats, detected_anomalies, now):
    """
    Generate a human-readable narrative snapshot of system state.

    Returns saved OpsNarrativeSnapshot instance.
    """
    from apps.core.ai_observability.models import (
        EngineRun,
        OpsAnomaly,
        OpsNarrativeSnapshot,
    )

    # Determine posture
    active_anomalies = OpsAnomaly.objects.filter(is_active=True)
    p1_count = active_anomalies.filter(severity="P1").count()
    p2_count = active_anomalies.filter(severity="P2").count()

    if p1_count > 0:
        posture = "AT_RISK"
    elif p2_count > 0:
        posture = "DEGRADED"
    else:
        posture = "OK"

    # Build headline
    headline = _build_headline(posture, heartbeats, p1_count, p2_count)

    # Build "What's happening now" bullets
    bullets_now = _build_bullets_now(heartbeats, detected_anomalies, now)

    # Build recommendations
    recommendations = _build_recommendations(detected_anomalies)

    # Build "watching next"
    watching_next = _build_watching_next(heartbeats, now)

    # Compute supporting metrics
    thirty_min_ago = now - timedelta(minutes=30)
    total_runs_30m = EngineRun.objects.filter(started_at__gte=thirty_min_ago).count()
    total_errors_30m = EngineRun.objects.filter(
        started_at__gte=thirty_min_ago, status="error"
    ).count()

    supporting_metrics = {
        "total_runs_30m": total_runs_30m,
        "total_errors_30m": total_errors_30m,
        "engines_ok": sum(1 for h in heartbeats if h.status == "OK"),
        "engines_missed": sum(1 for h in heartbeats if h.status == "MISSED"),
        "engines_late": sum(1 for h in heartbeats if h.status == "LATE"),
        "active_p1": p1_count,
        "active_p2": p2_count,
    }

    snapshot = OpsNarrativeSnapshot.objects.create(
        posture=posture,
        headline=headline,
        bullets_now=bullets_now[:6],
        recommendations=recommendations[:3],
        watching_next=watching_next[:2],
        supporting_metrics=supporting_metrics,
    )

    return snapshot


def _build_headline(posture, heartbeats, p1_count, p2_count):
    """Generate a one-sentence posture headline."""
    ok_count = sum(1 for h in heartbeats if h.status == "OK")
    total = len(heartbeats)

    if posture == "OK":
        return f"All systems nominal — {ok_count}/{total} engines reporting on cadence."
    elif posture == "DEGRADED":
        return (
            f"System degraded — {p2_count} warning{'s' if p2_count != 1 else ''} active, "
            f"{ok_count}/{total} engines on cadence."
        )
    else:
        return (
            f"System at risk — {p1_count} critical anomal{'ies' if p1_count != 1 else 'y'} "
            f"require attention."
        )


def _build_bullets_now(heartbeats, detected_anomalies, now):
    """Generate 3-6 bullets about current state."""
    bullets = []

    ok = [h.engine_name for h in heartbeats if h.status == "OK"]
    missed = [h.engine_name for h in heartbeats if h.status == "MISSED"]
    late = [h.engine_name for h in heartbeats if h.status == "LATE"]
    errored = [h.engine_name for h in heartbeats if h.status == "ERROR"]

    if ok:
        if len(ok) == len(heartbeats):
            bullets.append(f"All {len(ok)} engines running on schedule.")
        else:
            bullets.append(f"{', '.join(ok[:4])} running on schedule.")

    if missed:
        bullets.append(f"{', '.join(missed)} missed expected cadence.")

    if late:
        bullets.append(f"{', '.join(late)} running late but within jitter window.")

    if errored:
        bullets.append(f"{', '.join(errored)} last run returned errors.")

    for anomaly in detected_anomalies[:3]:
        if anomaly["anomaly_type"] == "SUPPRESSION_STORM":
            bullets.append("Suppression storm active — ICQG filtering aggressively.")
        elif anomaly["anomaly_type"] == "CONFIDENCE_VOLATILITY":
            bullets.append("UAL confidence scores unstable — scenario classification noisy.")
        elif anomaly["anomaly_type"] == "LOOPING_REMINDER":
            bullets.append("Repeated reminders detected — possible content loop.")

    return bullets


def _build_recommendations(detected_anomalies):
    """Generate 1-3 actionable recommendations."""
    recs = []
    seen_actions = set()

    for anomaly in detected_anomalies:
        for action in anomaly.get("suggested_actions", []):
            label = action.get("label", "")
            if label and label not in seen_actions:
                recs.append(label)
                seen_actions.add(label)

    if not recs and detected_anomalies:
        recs.append("Monitor anomalies — no immediate action required.")

    if not recs:
        recs.append("No action needed — all systems healthy.")

    return recs


def _build_watching_next(heartbeats, now):
    """Generate 1-2 items SAME is watching."""
    watching = []

    late = [h for h in heartbeats if h.status == "LATE"]
    if late:
        names = ", ".join(h.engine_name for h in late[:2])
        watching.append(f"Monitoring {names} — approaching missed cadence threshold.")

    for hb in heartbeats:
        if hb.status == "OK" and hb.next_expected_at:
            remaining = (hb.next_expected_at - now).total_seconds()
            interval = hb.metadata.get("interval_seconds", 3600)
            if 0 < remaining < interval * 0.2:
                watching.append(
                    f"{hb.engine_name} due to run in {int(remaining // 60)}m — watching."
                )
                break

    if not watching:
        watching.append("No engines approaching thresholds.")

    return watching


# =========================================================================
# SYSTEM INTEGRITY INDEX
# =========================================================================

# Severity penalty weights (subtracted from base score)
_SEVERITY_WEIGHTS = {
    "P1": 25.0,  # Critical — heavy penalty
    "P2": 10.0,  # Warning — moderate penalty
    "P3": 3.0,   # Info — light penalty
}


def _compute_integrity_snapshot(heartbeats, now):
    """
    Compute System Integrity Index (0–100) and persist as snapshot.

    Score formula:
      base = 100
      - Engine health: subtract (1 - pct_ok) * 40
      - Anomaly penalties: subtract per active anomaly by severity
      - Error spike penalty: subtract based on 30m error rate
      - Suppression rate penalty: subtract if suppression rate > 50%
      - Confidence volatility: subtract if UAL stddev > 0.3

    Posture:
      OPTIMAL: 90–100
      NOMINAL: 70–89
      DEGRADED: 40–69
      CRITICAL: 0–39

    Returns saved SystemIntegritySnapshot instance.
    """
    from apps.core.ai_observability.models import (
        EngineRun,
        OpsAnomaly,
        SystemIntegritySnapshot,
    )

    score = 100.0
    components = {}

    # --- Component 1: Engine health (max 40 point penalty) ---
    total_engines = len(heartbeats) if heartbeats else 1
    ok_count = sum(1 for h in heartbeats if h.status == "OK")
    pct_ok = ok_count / total_engines if total_engines > 0 else 1.0
    engine_penalty = (1.0 - pct_ok) * 40.0
    score -= engine_penalty
    components["engine_health"] = {
        "ok_count": ok_count,
        "total": total_engines,
        "pct_ok": round(pct_ok, 3),
        "penalty": round(engine_penalty, 1),
    }

    # --- Component 2: Anomaly severity penalties (max ~50 point penalty) ---
    active_anomalies = OpsAnomaly.objects.filter(is_active=True)
    anomaly_penalty = 0.0
    anomaly_counts = {"P1": 0, "P2": 0, "P3": 0}
    for anomaly in active_anomalies:
        weight = _SEVERITY_WEIGHTS.get(anomaly.severity, 3.0)
        anomaly_penalty += weight
        anomaly_counts[anomaly.severity] = anomaly_counts.get(anomaly.severity, 0) + 1
    # Cap anomaly penalty at 50
    anomaly_penalty = min(anomaly_penalty, 50.0)
    score -= anomaly_penalty
    components["anomaly_severity"] = {
        "counts": anomaly_counts,
        "penalty": round(anomaly_penalty, 1),
    }

    # --- Component 3: Error spike penalty (max 10 point penalty) ---
    thirty_min_ago = now - timedelta(minutes=30)
    total_runs_30m = EngineRun.objects.filter(
        started_at__gte=thirty_min_ago
    ).count()
    error_runs_30m = EngineRun.objects.filter(
        started_at__gte=thirty_min_ago, status="error"
    ).count()
    error_rate = error_runs_30m / total_runs_30m if total_runs_30m > 0 else 0.0
    error_penalty = min(error_rate * 50.0, 10.0)  # 20% error rate = 10 pts
    score -= error_penalty
    components["error_spike"] = {
        "errors_30m": error_runs_30m,
        "total_runs_30m": total_runs_30m,
        "error_rate": round(error_rate, 3),
        "penalty": round(error_penalty, 1),
    }

    # --- Component 4: Suppression rate (max 5 point penalty) ---
    from apps.core.ai_observability.models import DecisionRecord

    suppressions_30m = DecisionRecord.objects.filter(
        engine_name="ICQG",
        decision_type="suppression",
        created_at__gte=thirty_min_ago,
    ).count()
    total_icqg_30m = DecisionRecord.objects.filter(
        engine_name="ICQG",
        created_at__gte=thirty_min_ago,
    ).count()
    suppression_rate = (
        suppressions_30m / total_icqg_30m if total_icqg_30m > 0 else 0.0
    )
    suppression_penalty = max(0.0, (suppression_rate - 0.5) * 10.0)  # Penalty above 50%
    suppression_penalty = min(suppression_penalty, 5.0)
    score -= suppression_penalty
    components["suppression_rate"] = {
        "suppressions_30m": suppressions_30m,
        "total_icqg_30m": total_icqg_30m,
        "rate": round(suppression_rate, 3),
        "penalty": round(suppression_penalty, 1),
    }

    # --- Component 5: Confidence volatility (max 5 point penalty) ---
    twenty_four_h_ago = now - timedelta(hours=24)
    stats = DecisionRecord.objects.filter(
        engine_name="UAL",
        decision_type="arbitration",
        confidence__isnull=False,
        created_at__gte=twenty_four_h_ago,
    ).aggregate(
        stddev=StdDev("confidence"),
        count=Count("id"),
    )
    confidence_stddev = stats.get("stddev") or 0.0
    volatility_penalty = 0.0
    if stats.get("count", 0) >= 5 and confidence_stddev > 0.3:
        volatility_penalty = min((confidence_stddev - 0.3) * 15.0, 5.0)
    score -= volatility_penalty
    components["confidence_volatility"] = {
        "stddev": round(confidence_stddev, 3),
        "sample_count": stats.get("count", 0),
        "penalty": round(volatility_penalty, 1),
    }

    # Clamp score
    score = max(0.0, min(100.0, score))

    # Derive posture
    if score >= 90:
        posture = "OPTIMAL"
    elif score >= 70:
        posture = "NOMINAL"
    elif score >= 40:
        posture = "DEGRADED"
    else:
        posture = "CRITICAL"

    snapshot = SystemIntegritySnapshot.objects.create(
        score=round(score, 1),
        posture=posture,
        components=components,
    )

    return snapshot
