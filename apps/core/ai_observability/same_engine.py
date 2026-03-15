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
  - SIGNAL_DROUGHT: Domain has no intelligence signals for >48h
  - SIGNAL_LOW_DIVERSITY: Domain producing high volume but very few signal types
  - VALIDATOR_SPIKE: Validator gate block rate exceeds baseline

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
    detected.extend(_detect_signal_drought(now))
    detected.extend(_detect_signal_low_diversity(now))
    detected.extend(_detect_validator_spike(now))

    # Step 2.5: Cache health snapshots for polling endpoint
    _cache_signal_health()
    _cache_validator_health()
    _cache_cos_performance()

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


def _detect_signal_drought(now):
    """
    Detect domains with no intelligence signals for >48 hours.

    Uses compute_signal_health() to identify domains that have gone silent,
    indicating a potential pipeline failure or data ingestion issue.

    Thresholds:
      P2: domain silent 48h–96h (2–4 days)
      P1: domain silent >96h (4+ days)
    """
    anomalies = []

    try:
        from apps.core.ai_observability.ops_telemetry import compute_signal_health

        health = compute_signal_health()
        domains = health.get("domains", {})

        for domain, data in domains.items():
            freshness_hours = data.get("freshness_hours")
            volume_7d = data.get("volume_7d", 0)

            # Skip domains that never had signals (not a drought, just unused)
            if freshness_hours is None and volume_7d == 0:
                continue

            if freshness_hours is not None and freshness_hours > 48:
                severity = "P1" if freshness_hours > 96 else "P2"
                anomalies.append({
                    "anomaly_type": "SIGNAL_DROUGHT",
                    "severity": severity,
                    "engine_name": "",  # cross-engine anomaly
                    "summary": (
                        f"Signal drought in '{domain}' — no signals for "
                        f"{freshness_hours:.0f}h (threshold: 48h)"
                    ),
                    "evidence": {
                        "domain": domain,
                        "freshness_hours": freshness_hours,
                        "volume_7d": volume_7d,
                        "last_signal_at": data.get("last_signal_at"),
                    },
                    "suggested_actions": [
                        {
                            "action": "investigate_pipeline",
                            "label": f"Check {domain} signal pipeline",
                        },
                    ],
                })
    except Exception as e:
        logger.warning("SAME signal drought detection failed: %s", e, exc_info=True)

    return anomalies


def _detect_signal_low_diversity(now):
    """
    Detect domains with collapsing signal diversity.

    A domain producing high volume but only 1 signal type over 7 days
    suggests a pipeline regression where most signal extractors have
    stopped working.

    Thresholds:
      P2: distinct_types_7d == 1 AND volume_7d >= 10
      P3: distinct_types_7d <= 2 AND volume_7d >= 20
    """
    anomalies = []

    try:
        from apps.core.ai_observability.ops_telemetry import compute_signal_health

        health = compute_signal_health()
        domains = health.get("domains", {})

        for domain, data in domains.items():
            distinct = data.get("distinct_types_7d", 0)
            volume_7d = data.get("volume_7d", 0)

            # Only flag domains with meaningful volume but low diversity
            if distinct == 1 and volume_7d >= 10:
                anomalies.append({
                    "anomaly_type": "SIGNAL_LOW_DIVERSITY",
                    "severity": "P2",
                    "engine_name": "",  # cross-engine anomaly
                    "summary": (
                        f"Signal diversity collapse in '{domain}' — "
                        f"only 1 signal type across {volume_7d} signals (7d)"
                    ),
                    "evidence": {
                        "domain": domain,
                        "distinct_types_7d": distinct,
                        "volume_7d": volume_7d,
                    },
                    "suggested_actions": [
                        {
                            "action": "investigate_pipeline",
                            "label": f"Check {domain} signal extractors",
                        },
                    ],
                })
            elif distinct <= 2 and volume_7d >= 20:
                anomalies.append({
                    "anomaly_type": "SIGNAL_LOW_DIVERSITY",
                    "severity": "P3",
                    "engine_name": "",  # cross-engine anomaly
                    "summary": (
                        f"Low signal diversity in '{domain}' — "
                        f"only {distinct} types across {volume_7d} signals (7d)"
                    ),
                    "evidence": {
                        "domain": domain,
                        "distinct_types_7d": distinct,
                        "volume_7d": volume_7d,
                    },
                    "suggested_actions": [],
                })
    except Exception as e:
        logger.warning(
            "SAME signal diversity detection failed: %s", e, exc_info=True
        )

    return anomalies


def _cache_signal_health():
    """
    Compute and cache signal health snapshot for the polling endpoint.

    Called during every SAME cycle so OpsStreamView can read cached data
    instead of running expensive queries on each 2s poll.
    Cache TTL: 120s (2 SAME cycles, ensuring coverage even if one cycle skips).
    """
    try:
        from django.core.cache import cache

        from apps.core.ai_observability.ops_telemetry import compute_signal_health

        health = compute_signal_health()
        cache.set("wlj:ops:signal_health", health, timeout=120)
        logger.debug("SAME: cached signal health (%d domains)", len(health.get("domains", {})))
    except Exception as e:
        logger.warning("SAME: failed to cache signal health: %s", e)


def _detect_validator_spike(now):
    """
    Detect abnormal validator block/crash rates (VALIDATOR_SPIKE).

    Thresholds:
      P2: block_rate_1h > 10% with at least 5 validations
      P1: block_rate_1h > 25% with at least 5 validations, OR any crash in 1h

    Returns:
        list[dict] — anomaly descriptors for reconciliation.
    """
    anomalies = []
    try:
        from apps.core.ai_observability.ops_telemetry import compute_validator_health

        health = compute_validator_health()
        if not health or health.get("total_1h", 0) < 5:
            return anomalies

        total = health["total_1h"]
        blocks = health["blocks_1h"]
        block_rate = health["block_rate_1h"]
        crashes = health.get("crash_count_24h", 0)

        # Check for crash in last hour
        from apps.core.ai_observability.models import ValidatorMetric

        crashes_1h = ValidatorMetric.objects.filter(
            created_at__gte=now - timedelta(hours=1),
            outcome="crash",
        ).count()

        if crashes_1h > 0 or block_rate > 0.25:
            severity = "P1"
        elif block_rate > 0.10:
            severity = "P2"
        else:
            return anomalies

        anomalies.append({
            "anomaly_type": "VALIDATOR_SPIKE",
            "severity": severity,
            "engine_name": "VGE",
            "summary": (
                f"Validator block rate spike: {block_rate:.0%} "
                f"({blocks}/{total} in 1h)"
                + (f", {crashes_1h} crashes" if crashes_1h else "")
            ),
            "evidence": {
                "block_rate_1h": block_rate,
                "blocks_1h": blocks,
                "total_1h": total,
                "crashes_1h": crashes_1h,
            },
            "suggested_actions": [
                {"action": "investigate_validator", "label": "Review recent blocked responses in SelfError logs"},
                {"action": "check_prompt", "label": "Check for system prompt regression causing violations"},
            ],
        })
    except Exception as e:
        logger.warning("SAME validator spike detection failed: %s", e, exc_info=True)

    return anomalies


def _cache_validator_health():
    """
    Compute and cache validator health snapshot for the polling endpoint.

    Called during every SAME cycle so OpsStreamView can read cached data
    instead of running expensive queries on each 2s poll.
    Cache TTL: 120s (2 SAME cycles).
    """
    try:
        from django.core.cache import cache

        from apps.core.ai_observability.ops_telemetry import compute_validator_health

        health = compute_validator_health()
        cache.set("wlj:ops:validator_health", health, timeout=120)
        logger.debug("SAME: cached validator health (status=%s)", health.get("status") if health else "none")
    except Exception as e:
        logger.warning("SAME: failed to cache validator health: %s", e)


def _cache_cos_performance():
    """
    Compute and cache CoS performance snapshot for the polling endpoint.

    Called during every SAME cycle so OpsStreamView can read cached data
    instead of running expensive queries on each 2s poll.
    Cache TTL: 120s (2 SAME cycles).
    """
    try:
        from django.core.cache import cache

        from apps.core.ai_observability.ops_telemetry import compute_cos_performance

        perf = compute_cos_performance()
        cache.set("wlj:ops:cos_performance", perf, timeout=120)
        logger.debug("SAME: cached CoS performance (status=%s)", perf.get("status") if perf else "none")
    except Exception as e:
        logger.warning("SAME: failed to cache CoS performance: %s", e)


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
    ("P3", 30, "P2"),   # P3 unresolved > 30 minutes → P2
    ("P2", 60, "P1"),   # P2 unresolved > 60 minutes → P1
]

# Cooldown: minimum minutes between escalations of the same anomaly
ESCALATION_COOLDOWN_MINUTES = 15


def _escalate_anomalies(now):
    """
    Apply escalation state machine to active anomalies.

    Rules:
    - P3 unresolved > 30 minutes → promote to P2
    - P2 unresolved > 60 minutes → promote to P1
    - Cooldown: no re-escalation within 15 minutes
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

    from apps.core.ai_observability.engine_registry import ENGINE_REGISTRY
    from apps.core.ai_observability.models import AdminIntervention, OpsAnomaly

    # Only auto-remediate system engines (needs_user_context=False)
    system_engines = [
        name for name, meta in ENGINE_REGISTRY.items()
        if not meta.get("needs_user_context", False)
    ]

    actions_taken = 0
    active_p3 = OpsAnomaly.objects.filter(
        is_active=True, severity="P3", engine_name__in=system_engines,
    )

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
    """
    Auto-rerun a missed engine via Celery (non-blocking).

    Uses ENGINE_REGISTRY to validate the engine supports manual execution,
    then dispatches run_engine_task via Celery with trigger_source=auto_remediation.
    Creates EngineExecutionLog + AdminIntervention audit records.
    """
    import uuid

    from apps.core.ai_observability.engine_registry import get_engine_meta
    from apps.core.ai_observability.models import AdminIntervention, EngineExecutionLog

    engine = anomaly.engine_name
    meta = get_engine_meta(engine)
    if not meta or not meta["can_manual_run"]:
        return False

    # Idempotency: skip if already executing
    if EngineExecutionLog.is_engine_active(engine):
        logger.info("SAME auto-remediation: %s already active, skipping", engine)
        return False

    trace_id = str(uuid.uuid4())

    try:
        # Create execution log
        execution = EngineExecutionLog.objects.create(
            engine_name=engine,
            trigger_source="auto_remediation",
            status="queued",
            triggered_by=None,
        )

        # Dispatch via Celery (non-blocking)
        from apps.core.tasks import run_engine_task

        result = run_engine_task.delay(engine, execution.id)
        execution.celery_task_id = result.id
        execution.save(update_fields=["celery_task_id"])

        AdminIntervention.objects.create(
            admin_user=None,
            action_type="auto_rerun_engine",
            engine_name=engine,
            trace_id=trace_id,
            notes=(
                f"SAME autonomous remediation: {engine} "
                f"(execution_id={execution.id}, celery_task_id={result.id})"
            ),
            result_status="pending",
            is_system_initiated=True,
        )

        logger.info(
            "SAME auto-remediation: dispatched %s (trace=%s, execution_id=%s)",
            engine, trace_id, execution.id,
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
    "P1": 15.0,  # Critical — significant penalty
    "P2": 7.0,   # Warning — moderate penalty
    "P3": 2.0,   # Info — light penalty
}


def _compute_integrity_snapshot(heartbeats, now):
    """
    Compute System Integrity Index (0–100) and persist as snapshot.

    Score formula:
      base = 100
      - Engine health: subtract (1 - pct_ok) * 30
      - Anomaly penalties: subtract per active anomaly by severity (cap 40)
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

    # --- Component 1: Engine health (max 30 point penalty) ---
    total_engines = len(heartbeats) if heartbeats else 1
    ok_count = sum(1 for h in heartbeats if h.status == "OK")
    pct_ok = ok_count / total_engines if total_engines > 0 else 1.0
    engine_penalty = (1.0 - pct_ok) * 30.0
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
    # Cap anomaly penalty at 40
    anomaly_penalty = min(anomaly_penalty, 40.0)
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


# =========================================================================
# POST-EXECUTION RECOVERY — Immediate rescore after manual engine run
# =========================================================================


def recompute_integrity_after_recovery(engine_name):
    """
    Post-execution recovery hook — recompute heartbeats, resolve
    MISSED_RUN anomalies for the recovered engine, and create a fresh
    SystemIntegritySnapshot.

    Called by ``run_engine_task`` after a successful manual/synthetic
    execution.  Ensures the UI reflects the recovery on the next poll
    without waiting for the next full SAME cycle (up to 60 seconds).

    Steps:
      1. Recompute heartbeats for all engines (fast DB queries).
      2. If this engine's heartbeat is now OK, resolve its active
         MISSED_RUN anomaly (if any).
      3. Recompute the System Integrity Index with fresh data.

    Historical misses (EngineHeartbeat records with status='MISSED')
    remain in the database and age out naturally — this only clears the
    *current* missed state.

    Returns:
        SystemIntegritySnapshot — the freshly computed snapshot.
    """
    from apps.core.ai_observability.heartbeat import compute_and_save_heartbeats
    from apps.core.ai_observability.models import OpsAnomaly

    now = timezone.now()

    # 1. Recompute all heartbeats from latest EngineRun data
    heartbeats = compute_and_save_heartbeats()

    # 2. If the executed engine is now OK, resolve its MISSED_RUN anomaly
    engine_hb = next(
        (h for h in heartbeats if h.engine_name == engine_name), None
    )
    if engine_hb and engine_hb.status == "OK":
        resolved = OpsAnomaly.objects.filter(
            anomaly_type="MISSED_RUN",
            engine_name=engine_name,
            is_active=True,
        ).update(
            is_active=False,
            resolved_at=now,
        )
        if resolved:
            logger.info(
                "Recovery: resolved %d MISSED_RUN anomal%s for %s",
                resolved, "y" if resolved == 1 else "ies", engine_name,
            )

    # 3. Recompute integrity snapshot with fresh heartbeats
    snapshot = _compute_integrity_snapshot(heartbeats, now)
    logger.info(
        "Recovery rescore for %s: score=%.1f, posture=%s",
        engine_name, snapshot.score, snapshot.posture,
    )
    return snapshot
