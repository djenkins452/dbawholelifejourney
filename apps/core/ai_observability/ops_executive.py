"""
Executive Operations Synthesis — Ops Command Center.

Turns the raw Ops Wall telemetry (already assembled by
``build_ops_stream_payload``) into an **executive summary** that answers, in
ten seconds, the five questions every operator asks:

    1. Am I okay?            → overall_status
    2. What is wrong?        → incidents / summary
    3. Why is it happening?  → likely_cause + root_cause_chain
    4. Who is affected?      → customer_impact (per incident + overall)
    5. What do I do next?    → recommended_action

**This is NOT an AI feature and adds NO new monitoring.** It is a pure,
deterministic reduction over telemetry WLJ already computes:
* the System Integrity score + its per-component penalty breakdown,
* the active ``OpsAnomaly`` set,
* the OPS-2/3/4 section states (storage, chat_queue, upstream_health) and the
  engine/scheduler/api sections,
* the in-memory engine dependency registry (for cascade / root-cause chains),
* a small cache-persisted KPI history (for trend direction / velocity).

Every sentence and number it emits is directly traceable to a monitored value —
no hallucination, no reasoning engine. It runs at the END of the SAME
background cycle (never the request path); the HTTP path reads the cached
payload and renders it.

Project: Whole Life Journey
Path: apps/core/ai_observability/ops_executive.py
"""

import logging
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

# --- Customer-impact ordering (higher = worse) ---
IMPACT_NONE, IMPACT_LOW, IMPACT_MEDIUM, IMPACT_HIGH = 0, 1, 2, 3
_IMPACT_LABEL = {IMPACT_NONE: "None", IMPACT_LOW: "Low",
                 IMPACT_MEDIUM: "Medium", IMPACT_HIGH: "High"}

# --- Diagnosis confidence + cause language per anomaly type (deterministic) ---
# confidence = how certain the DIAGNOSIS is (not a probability of failure);
# derived from how directly the detector observes the condition.
_ANOMALY_META = {
    "MISSED_RUN": {
        "confidence": 99, "impact": IMPACT_LOW,
        "cause": "Scheduled work did not run on its expected cadence",
        "impact_phrase": "Reduced insight freshness",
    },
    "ENGINE_STARVATION": {
        "confidence": 97, "impact": IMPACT_MEDIUM,
        "cause": "Engine received no work — upstream scheduler or queue stalled",
        "impact_phrase": "Delayed insights and updates",
    },
    "ERROR_SPIKE": {
        "confidence": 95, "impact": IMPACT_LOW,
        "cause": "Elevated engine error rate vs. its 24h baseline",
        "impact_phrase": "Reduced insight reliability",
    },
    "DELIVERY_RETRY_SPIKE": {
        "confidence": 94, "impact": IMPACT_MEDIUM,
        "cause": "Notification delivery is retrying repeatedly",
        "impact_phrase": "Delayed notifications",
    },
    "SIGNAL_DROUGHT": {
        "confidence": 92, "impact": IMPACT_LOW,
        "cause": "A signal domain stopped producing new data",
        "impact_phrase": "Stale data in one life domain",
    },
    "SIGNAL_LOW_DIVERSITY": {
        "confidence": 88, "impact": IMPACT_LOW,
        "cause": "Signal intake narrowed to too few sources",
        "impact_phrase": "Narrower insight coverage",
    },
    "SUPPRESSION_STORM": {
        "confidence": 90, "impact": IMPACT_LOW,
        "cause": "Quality gate is suppressing an unusually high share of output",
        "impact_phrase": "Fewer proactive nudges",
    },
    "CONFIDENCE_VOLATILITY": {
        "confidence": 85, "impact": IMPACT_LOW,
        "cause": "Arbitration confidence is swinging widely",
        "impact_phrase": "Less consistent recommendations",
    },
    "LOOPING_REMINDER": {
        "confidence": 93, "impact": IMPACT_MEDIUM,
        "cause": "A reminder is re-firing in a loop",
        "impact_phrase": "Repeated/duplicate reminders",
    },
    "VALIDATOR_CRASH": {
        "confidence": 96, "impact": IMPACT_MEDIUM,
        "cause": "A safety validator errored while checking output",
        "impact_phrase": "Delayed or withheld responses",
    },
    "VALIDATOR_SPIKE": {
        "confidence": 90, "impact": IMPACT_LOW,
        "cause": "Validator is blocking an elevated share of actions",
        "impact_phrase": "Some actions held for review",
    },
    "COMMITMENT_RACE_CONDITION": {
        "confidence": 91, "impact": IMPACT_MEDIUM,
        "cause": "Concurrent commitment writes contended for the same turn",
        "impact_phrase": "Possible duplicate or dropped replies",
    },
    "STRUCTURAL_VIOLATION": {
        "confidence": 96, "impact": IMPACT_MEDIUM,
        "cause": "Output failed a structural contract check",
        "impact_phrase": "Malformed response risk",
    },
    "NUMERIC_DEVIATION": {
        "confidence": 92, "impact": IMPACT_MEDIUM,
        "cause": "A computed value deviated from its expected range",
        "impact_phrase": "Possible incorrect figures shown",
    },
}
_DEFAULT_ANOMALY_META = {
    "confidence": 80, "impact": IMPACT_LOW,
    "cause": "Anomalous condition detected by monitoring",
    "impact_phrase": "Possible degraded experience",
}

_SEVERITY_LABEL = {"P1": "Critical", "P2": "Warning", "P3": "Info"}
_SEVERITY_WEIGHT = {"P1": 15.0, "P2": 7.0, "P3": 2.0}

_KPI_HISTORY_KEY = "wlj:ops:exec_kpi_history"
_KPI_HISTORY_MAX = 30           # ~30 SAME cycles ≈ 30 minutes
_KPI_HISTORY_TTL = 60 * 60 * 2  # 2h


# =========================================================================
# ENGINE DEPENDENCY / DISPLAY HELPERS
# =========================================================================


def _engine_display(code):
    """Human display name for an engine code (falls back to the code)."""
    try:
        from apps.core.engine_registry import get_engine
        eng = get_engine(code)
        if eng and getattr(eng, "name", None):
            return eng.name
    except Exception:
        pass
    return code


def _downstream_dependents(code):
    """
    Engines that DEPEND ON ``code`` — i.e. what is affected if it degrades.

    Reverse-traverses the in-memory ENGINE_REGISTRY (one hop). Deterministic,
    zero DB.
    """
    out = []
    try:
        from apps.core.engine_registry import ENGINE_REGISTRY
        for c, eng in ENGINE_REGISTRY.items():
            if code and code in (getattr(eng, "dependencies", ()) or ()):
                out.append(c)
    except Exception:
        pass
    return out


# =========================================================================
# CUSTOMER IMPACT — deterministic mapping from degraded subsystem state
# =========================================================================


def _section_impacts(sections):
    """
    Translate OPS-2/3/4 + delivery section states into (level, phrase) customer
    impacts. Returns a list of (level:int, phrase:str, subsystem:str).
    """
    impacts = []

    up = sections.get("upstream_health") or {}
    up_status = up.get("status")
    if up_status == "OUTAGE":
        impacts.append((IMPACT_HIGH, "AI chat unavailable", "OpenAI upstream"))
    elif up_status == "DEGRADED":
        impacts.append((IMPACT_MEDIUM, "Slower or failing AI responses", "OpenAI upstream"))

    cq = sections.get("chat_queue") or {}
    cq_status = cq.get("status")
    if cq_status == "CRITICAL":
        if cq.get("worker_starved"):
            impacts.append((IMPACT_HIGH, "Chat responses stalled", "Chat queue"))
        else:
            impacts.append((IMPACT_MEDIUM, "Chat responses delayed", "Chat queue"))
    elif cq_status == "WARNING":
        impacts.append((IMPACT_LOW, "Slightly slower chat responses", "Chat queue"))

    st = sections.get("storage") or {}
    if (st.get("disk") or {}).get("status") == "CRITICAL":
        impacts.append((IMPACT_HIGH, "Cannot save new data (disk near full)", "Disk / volume"))
    if (st.get("redis") or {}).get("status") == "CRITICAL":
        impacts.append((IMPACT_MEDIUM, "Degraded performance / cache eviction", "Redis"))
    if (st.get("postgres") or {}).get("status") == "CRITICAL":
        impacts.append((IMPACT_HIGH, "Database near capacity", "PostgreSQL"))

    api = sections.get("api_health") or {}
    if api.get("status") == "CRITICAL":
        impacts.append((IMPACT_MEDIUM, "Slower API responses", "API"))

    return impacts


def _anomaly_impact(anomaly):
    """(level, phrase) customer impact for one anomaly, from its type."""
    meta = _ANOMALY_META.get(anomaly.get("anomaly_type"), _DEFAULT_ANOMALY_META)
    level = meta["impact"]
    # A P1 escalates the nominal impact by one band (it is worse than baseline).
    if anomaly.get("severity") == "P1":
        level = min(IMPACT_HIGH, level + 1)
    return level, meta["impact_phrase"]


# =========================================================================
# INCIDENT ENRICHMENT (Phases 4, 5, 9, 10)
# =========================================================================


def _root_cause_chain(anomaly, sections):
    """
    Deterministic dependency / cause chain for one incident.

    Built from the anomaly type, the affected engine, correlated live telemetry
    (e.g. Redis currently unavailable), and the engine dependency registry —
    NOT guessed. Returns an ordered list of short strings.
    """
    atype = anomaly.get("anomaly_type")
    engine = anomaly.get("engine_name") or ""
    chain = []

    head = f"{_engine_display(engine)} {(_SEVERITY_LABEL.get(anomaly.get('severity'),'') )}".strip()
    meta = _ANOMALY_META.get(atype, _DEFAULT_ANOMALY_META)
    chain.append(anomaly.get("summary_head") or f"{_engine_display(engine) or 'System'}: {meta['cause']}")

    # Correlate with live infrastructure telemetry when relevant.
    st = sections.get("storage") or {}
    redis_bad = (st.get("redis") or {}).get("status") in ("CRITICAL", "UNAVAILABLE")
    if atype in ("ERROR_SPIKE", "ENGINE_STARVATION", "SIGNAL_DROUGHT") and redis_bad:
        chain.append("Redis connectivity / memory pressure")

    if atype == "MISSED_RUN":
        chain.append("Scheduler dispatch or worker availability")
    elif atype == "ENGINE_STARVATION":
        chain.append("Upstream queue empty — no work dispatched")
    elif atype in ("SIGNAL_DROUGHT", "SIGNAL_LOW_DIVERSITY"):
        chain.append("Signal intake pipeline")
    elif atype == "DELIVERY_RETRY_SPIKE":
        chain.append("Notification delivery channel")

    # Downstream engines that depend on the affected one (blast radius).
    dependents = _downstream_dependents(engine)
    if dependents:
        shown = ", ".join(_engine_display(d) for d in dependents[:3])
        chain.append(f"Affects downstream: {shown}")

    # The concrete evidence tail, if present.
    ev = anomaly.get("evidence") or {}
    tail = ev.get("task_name") or ev.get("label")
    if tail and tail != engine:
        chain.append(str(tail))

    return chain


def _recovery_state(anomaly, kpi_trend):
    """
    Deterministic recovery state for an incident.

    * escalating (getting worse) if it has been escalated,
    * recovering if the overall error/incident trend is improving,
    * otherwise ongoing/monitoring based on age.
    """
    if anomaly.get("escalation_count", 0) > 0:
        return "Escalating"
    if kpi_trend and kpi_trend.get("incidents", {}).get("semantic") == "improving":
        return "Recovering"
    if kpi_trend and kpi_trend.get("errors", {}).get("semantic") in ("improving",):
        return "Recovering"
    return "Monitoring"


def _duration(created_iso, now):
    if not created_iso:
        return "unknown"
    try:
        from django.utils.dateparse import parse_datetime
        dt = parse_datetime(created_iso)
        if not dt:
            return "unknown"
        secs = int((now - dt).total_seconds())
        if secs < 60:
            return f"{secs}s"
        if secs < 3600:
            return f"{secs // 60}m"
        if secs < 86400:
            return f"{secs // 3600}h {(secs % 3600)//60}m"
        return f"{secs // 86400}d"
    except Exception:
        return "unknown"


def _enrich_incident(anomaly, sections, kpi_trend, now):
    atype = anomaly.get("anomaly_type")
    meta = _ANOMALY_META.get(atype, _DEFAULT_ANOMALY_META)
    impact_level, impact_phrase = _anomaly_impact(anomaly)

    confidence = meta["confidence"]
    if anomaly.get("escalation_count", 0) > 0:
        confidence = min(99, confidence + 2)

    engine = anomaly.get("engine_name") or ""
    affected = [_engine_display(engine)] if engine else []
    affected += [_engine_display(d) for d in _downstream_dependents(engine)[:4]]

    actions = anomaly.get("suggested_actions") or []
    suggested = actions[0].get("label") if actions and isinstance(actions[0], dict) else None
    action_key = actions[0].get("action") if actions and isinstance(actions[0], dict) else None

    status = "Active"
    if anomaly.get("escalation_count", 0) > 0:
        status = f"Escalated ×{anomaly['escalation_count']}"

    return {
        "id": anomaly.get("id"),
        "severity": anomaly.get("severity"),
        "severity_label": _SEVERITY_LABEL.get(anomaly.get("severity"), anomaly.get("severity")),
        "title": anomaly.get("summary"),
        "engine": engine,
        "anomaly_type": atype,
        "detected_at": anomaly.get("created_at"),
        "detected_ago": anomaly.get("first_detected"),
        "duration": _duration(anomaly.get("created_at"), now),
        "likely_cause": meta["cause"],
        "confidence": confidence,
        "affected_components": [a for a in affected if a] or ["System"],
        "customer_impact_level": impact_level,
        "customer_impact": impact_phrase,
        "suggested_action": suggested or f"Investigate {_engine_display(engine) or 'the affected subsystem'}",
        "action_key": action_key,
        "status": status,
        "recovery_state": _recovery_state(anomaly, kpi_trend),
        "root_cause_chain": _root_cause_chain(anomaly, sections),
    }


def _incident_priority(inc):
    """Sort key: severity, then customer impact, then most recent."""
    sev_rank = {"P1": 0, "P2": 1, "P3": 2}.get(inc.get("severity"), 3)
    return (sev_rank, -inc.get("customer_impact_level", 0), inc.get("detected_at") or "")


# =========================================================================
# SCORE EXPLANATION (Phase 2)
# =========================================================================


def _score_deductions(integrity, anomalies):
    """
    Itemized, deterministic "why not 100" list from the integrity components +
    the active anomaly set. Each entry: {label, points (negative)}.
    """
    deductions = []
    components = (integrity or {}).get("components") or {}

    # Per-anomaly deductions (the intuitive, incident-level view).
    for a in anomalies:
        w = _SEVERITY_WEIGHT.get(a.get("severity"), 2.0)
        eng = _engine_display(a.get("engine_name") or "") or "System"
        atype = (a.get("anomaly_type") or "").replace("_", " ").title()
        deductions.append({
            "label": f"{eng} — {atype}",
            "points": -round(w, 1),
            "kind": "anomaly",
        })

    # Non-anomaly structural penalties (scheduler / engine / error / etc.).
    def _add(comp_key, label):
        comp = components.get(comp_key) or {}
        pen = comp.get("penalty") or 0
        if pen and pen > 0:
            deductions.append({"label": label, "points": -round(pen, 1), "kind": "structural"})

    sched = components.get("scheduler_health") or {}
    sched_pen = sched.get("penalty") or 0
    if sched_pen > 0:
        offline = []
        for k in ("ise", "same"):
            if (sched.get(k) or {}).get("status") in ("OFFLINE", "DELAYED"):
                offline.append(f"{k.upper()} {(sched.get(k) or {}).get('status','').lower()}")
        label = "Scheduler degraded" + (f" ({', '.join(offline)})" if offline else "")
        deductions.append({"label": label, "points": -round(sched_pen, 1), "kind": "structural"})

    eng = components.get("engine_health") or {}
    if (eng.get("penalty") or 0) > 0:
        deductions.append({
            "label": f"Engine heartbeats ({eng.get('ok_count','?')}/{eng.get('total','?')} OK)",
            "points": -round(eng["penalty"], 1), "kind": "structural",
        })

    _add("error_spike", "Engine error rate (30m)")
    _add("suppression_rate", "Output suppression elevated")
    _add("confidence_volatility", "Confidence volatility")

    # Largest deductions first.
    deductions.sort(key=lambda d: d["points"])
    return deductions


# =========================================================================
# TREND / VELOCITY (Phase 8) — from cache-persisted KPI history
# =========================================================================


def _classify_trend(series, polarity):
    """
    Classify a numeric series (oldest→newest) into a direction + semantic.

    polarity: 'up_good' (higher is better, e.g. score) or 'up_bad' (higher is
    worse, e.g. error rate / queue depth / incident count).
    """
    vals = [v for v in series if v is not None]
    if len(vals) < 2:
        return {"dir": "flat", "semantic": "stable", "delta": 0, "value": vals[-1] if vals else None}

    current = vals[-1]
    # Baseline = mean of the older half (stable against single-point noise).
    older = vals[:-1]
    baseline = sum(older) / len(older)
    delta = current - baseline
    denom = max(abs(baseline), 1e-9)
    pct = delta / denom

    if abs(pct) < 0.10:
        direction, magnitude = "flat", "stable"
    elif pct > 0:
        direction = "up"
        magnitude = "fast" if pct > 0.5 else "normal"
    else:
        direction = "down"
        magnitude = "fast" if pct < -0.5 else "normal"

    # Map to good/bad semantic.
    if direction == "flat":
        semantic = "stable"
    else:
        improving = (direction == "up" and polarity == "up_good") or \
                    (direction == "down" and polarity == "up_bad")
        if improving:
            semantic = "improving"
        else:
            semantic = "rapidly_declining" if magnitude == "fast" else "declining"

    return {"dir": direction, "semantic": semantic, "delta": round(delta, 2), "value": current}


def _update_kpi_history(kpis):
    """Append current KPIs to the bounded cache history (background only)."""
    try:
        hist = cache.get(_KPI_HISTORY_KEY) or []
        hist.append(kpis)
        if len(hist) > _KPI_HISTORY_MAX:
            hist = hist[-_KPI_HISTORY_MAX:]
        cache.set(_KPI_HISTORY_KEY, hist, timeout=_KPI_HISTORY_TTL)
        return hist
    except Exception as e:
        logger.debug("exec KPI history update failed: %s", e)
        return [kpis]


def _collect_kpis(sections, integrity, active_count):
    up = sections.get("upstream_health") or {}
    cq = sections.get("chat_queue") or {}
    api = sections.get("api_health") or {}
    return {
        "score": (integrity or {}).get("score"),
        "incidents": active_count,
        "chat_depth": cq.get("queue_depth"),
        "chat_oldest": cq.get("oldest_age_s"),
        "upstream_latency": up.get("avg_latency_ms"),
        "upstream_errrate": up.get("error_rate_pct"),
        "api_errrate": api.get("error_rate_pct"),
    }


def _compute_trends(history):
    """Per-KPI trend directions from the rolling history."""
    def series(key):
        return [h.get(key) for h in history]
    return {
        "score": _classify_trend(series("score"), "up_good"),
        "incidents": _classify_trend(series("incidents"), "up_bad"),
        "chat_queue": _classify_trend(series("chat_depth"), "up_bad"),
        "chat_oldest": _classify_trend(series("chat_oldest"), "up_bad"),
        "api_latency": _classify_trend(series("upstream_latency"), "up_bad"),
        "errors": _classify_trend(series("upstream_errrate"), "up_bad"),
    }


# =========================================================================
# OVERALL STATUS + PLAIN-ENGLISH SUMMARY (Phases 1, 7)
# =========================================================================


def _overall_status(integrity, sections, incidents):
    """HEALTHY / DEGRADED / CRITICAL — deterministic from posture + sections."""
    posture = (integrity or {}).get("posture") or "NOMINAL"
    base = {
        "OPTIMAL": "HEALTHY", "NOMINAL": "HEALTHY",
        "DEGRADED": "DEGRADED", "CRITICAL": "CRITICAL",
    }.get(posture, "HEALTHY")

    # Any customer-facing CRITICAL/OUTAGE forces at least DEGRADED.
    up = (sections.get("upstream_health") or {}).get("status")
    cq = (sections.get("chat_queue") or {}).get("status")
    st = (sections.get("storage") or {}).get("status")
    has_p1 = any(i.get("severity") == "P1" for i in incidents)

    if up == "OUTAGE" or st == "CRITICAL":
        base = "CRITICAL" if base != "CRITICAL" else base
        base = "CRITICAL"
    if base == "HEALTHY" and (up == "DEGRADED" or cq == "CRITICAL" or has_p1):
        base = "DEGRADED"
    return base


_SUBSYSTEM_SECTIONS = [
    ("Chat", "chat_queue"),
    ("APIs", "api_health"),
    ("Scheduling", "scheduler_health"),
    ("Storage", "storage"),
    ("OpenAI", "upstream_health"),
]

_HEALTHY_STATES = {"HEALTHY", "OK", "OPTIMAL", "NOMINAL", "IDLE", "ALIVE", None}


def _subsystem_states(sections, incidents):
    """
    Coarse per-subsystem health for the summary + Phase 6 de-emphasis.

    Engine Execution rolls up active engine anomalies; the infra subsystems map
    directly from their section status.
    """
    states = []

    # Engine Execution — from active anomalies bound to engines.
    engine_incidents = [i for i in incidents if i.get("engine")]
    if any(i["severity"] == "P1" for i in engine_incidents):
        eng_state = "CRITICAL"
    elif engine_incidents:
        eng_state = "DEGRADED"
    else:
        eng_state = "HEALTHY"
    states.append({"name": "Engine Execution", "status": eng_state, "key": "engine"})

    for label, key in _SUBSYSTEM_SECTIONS:
        raw = (sections.get(key) or {}).get("status")
        if raw in ("CRITICAL", "OUTAGE"):
            s = "CRITICAL"
        elif raw in ("DEGRADED", "WARNING"):
            s = "DEGRADED"
        elif raw == "UNAVAILABLE":
            s = "UNKNOWN"
        else:
            s = "HEALTHY"
        states.append({"name": label, "status": s, "key": key})
    return states


def _plain_summary(overall, subsystems, impact_level, impact_phrases):
    """Deterministic plain-English summary lines."""
    lines = []
    if overall == "HEALTHY":
        lines.append("WLJ is operational.")
    elif overall == RECOVERING:
        lines.append("WLJ is recovering — confirming stability before clearing the alert.")
    elif overall == "DEGRADED":
        lines.append("WLJ is operational with degraded subsystems.")
    else:
        lines.append("WLJ is in a critical state.")

    degraded = [s for s in subsystems if s["status"] in ("DEGRADED", "CRITICAL")]
    for s in degraded:
        verb = "is experiencing elevated errors" if s["status"] == "DEGRADED" else "is critically degraded"
        lines.append(f"{s['name']} {verb}.")

    healthy = [s["name"] for s in subsystems if s["status"] == "HEALTHY"]
    if healthy and degraded:
        # Name the healthy remainder so the operator knows the blast radius is bounded.
        shown = healthy[:5]
        joined = ", ".join(shown[:-1]) + (" and " + shown[-1] if len(shown) > 1 else shown[0])
        lines.append(f"{joined} remain healthy.")

    lines.append(f"Customer impact is currently {_IMPACT_LABEL[impact_level]}.")
    return lines


def _operational_narrative(overall, subsystems, sections, trends, incidents, now):
    """Deterministic operational narrative paragraph (Phase 7)."""
    # Window = age of the oldest active incident, else the monitoring window.
    window = "the monitoring window"
    if incidents:
        oldest = min((i.get("detected_at") or "") for i in incidents if i.get("detected_at"))
        if oldest:
            window = f"the past {_duration(oldest, now)}"

    degraded = [s for s in subsystems if s["status"] in ("DEGRADED", "CRITICAL")]
    parts = []
    if not degraded:
        parts.append(f"Over {window} the platform has remained stable across all monitored subsystems.")
    else:
        names = ", ".join(s["name"] for s in degraded)
        parts.append(f"Over {window} the platform has remained stable except for {names}.")

    cq = sections.get("chat_queue") or {}
    if cq.get("status") == "UNAVAILABLE":
        parts.append("Chat queue telemetry is unavailable.")
    else:
        depth = cq.get("queue_depth")
        parts.append(f"Queue depth is {'normal' if (depth or 0) < 5 else 'elevated'}.")

    api = sections.get("api_health") or {}
    parts.append(f"API latency is {'healthy' if api.get('status') in ('HEALTHY','IDLE',None) else 'elevated'}.")

    up = sections.get("upstream_health") or {}
    up_status = up.get("status")
    parts.append(f"OpenAI is {'healthy' if up_status in ('HEALTHY','IDLE',None) else up_status.lower()}.")

    st = sections.get("storage") or {}
    parts.append(f"Storage is {'healthy' if st.get('status') in ('HEALTHY',None) else st.get('status','').lower()}.")

    if degraded:
        if len(degraded) == 1:
            parts.append(f"The degradation appears isolated to {degraded[0]['name']}.")
        else:
            parts.append(f"The degradation spans {len(degraded)} subsystems and warrants attention.")

    # Direction cue.
    score_trend = (trends or {}).get("score", {}).get("semantic")
    if score_trend == "improving":
        parts.append("Overall health is trending up.")
    elif score_trend in ("declining", "rapidly_declining"):
        parts.append("Overall health is trending down.")

    return " ".join(parts)


# =========================================================================
# RECOVERY STABILIZATION (deterministic hysteresis) — Ops Stability milestone
# =========================================================================
# The raw ``_overall_status`` is a pure snapshot of the current score band, so a
# score oscillating across the DEGRADED/NOMINAL boundary (the proven 2026-07-23
# incident: 50→51→76.5→67→76.5→69.5→98) flipped HEALTHY↔DEGRADED every cycle and
# fired a premature "recovered". Stabilization does NOT hide truth and does NOT
# change scoring — it only governs the *executive status transition*:
#   * Degradation is IMMEDIATE (never dampen a real problem going worse).
#   * Recovery to HEALTHY requires (a) the raw status HEALTHY-eligible for
#     ``RECOVERY_STABLE_CYCLES`` consecutive SAME cycles AND (b) no *significant*
#     (P1/P2) active incident. Until both hold, the status is ``RECOVERING`` —
#     a distinct, honest, transitional state (not HEALTHY, not "still degraded").
# The recovered cue / notifications fire only on the confirmed RECOVERING→HEALTHY.

RECOVERING = "RECOVERING"
RECOVERY_STABLE_CYCLES = 3               # ~3 min at the 60s SAME cadence
_SIGNIFICANT_SEVERITIES = {"P1", "P2"}   # active incidents that block recovery
_RECOVERY_STATE_KEY = "wlj:ops:exec_recovery_state"
_RECOVERY_STATE_TTL = 60 * 60 * 2        # 2h — self-heals if the cycle stalls


def _significant_active(incidents):
    return any(i.get("severity") in _SIGNIFICANT_SEVERITIES for i in (incidents or []))


def stabilize_status(prev, raw, incidents):
    """Pure hysteresis (deterministic, cache-free — testable in isolation).

    Args:
        prev: prior state dict {"status", "healthy_cycles"} or None.
        raw: the raw ``_overall_status`` for this cycle.
        incidents: enriched incident list (each has "severity").
    Returns:
        (stabilized_status, new_state_dict, recovery_meta_dict)
    """
    prev_status = (prev or {}).get("status")
    healthy_cycles = int((prev or {}).get("healthy_cycles", 0) or 0)
    blocked = _significant_active(incidents)

    if raw != "HEALTHY":
        # Immediate on the way down — timeliness for real degradations.
        state = {"status": raw, "healthy_cycles": 0}
        return raw, state, {"raw_status": raw, "healthy_cycles": 0,
                            "needed_cycles": RECOVERY_STABLE_CYCLES,
                            "blocked_by_incidents": blocked}

    # raw is HEALTHY-eligible this cycle.
    if prev_status in (None, "HEALTHY"):
        state = {"status": "HEALTHY", "healthy_cycles": healthy_cycles + 1}
        return "HEALTHY", state, {"raw_status": raw,
                                  "healthy_cycles": healthy_cycles + 1,
                                  "needed_cycles": RECOVERY_STABLE_CYCLES,
                                  "blocked_by_incidents": False}

    # We were non-healthy and raw just went healthy → require sustained stability.
    healthy_cycles += 1
    stable = healthy_cycles >= RECOVERY_STABLE_CYCLES and not blocked
    status = "HEALTHY" if stable else RECOVERING
    state = {"status": status, "healthy_cycles": healthy_cycles}
    return status, state, {"raw_status": raw, "healthy_cycles": healthy_cycles,
                           "needed_cycles": RECOVERY_STABLE_CYCLES,
                           "blocked_by_incidents": blocked}


def _apply_recovery_hysteresis(raw, incidents):
    """Cache-backed wrapper around ``stabilize_status`` (background-cycle only).

    Fails OPEN to the raw status if the cache is unavailable — stabilization is
    a smoothing layer, never a source of a false status.
    """
    try:
        prev = cache.get(_RECOVERY_STATE_KEY)
        status, state, meta = stabilize_status(prev, raw, incidents)
        cache.set(_RECOVERY_STATE_KEY, state, timeout=_RECOVERY_STATE_TTL)
        return status, meta
    except Exception as e:
        logger.debug("recovery hysteresis unavailable (%s) — using raw", e)
        return raw, {"raw_status": raw, "stabilization": "unavailable"}


# =========================================================================
# PUBLIC — the one entry point (called at the END of the SAME cycle)
# =========================================================================


def build_executive_summary(sections, now=None):
    """
    Reduce the assembled telemetry ``sections`` dict into the ``executive``
    payload section. Pure + deterministic; safe to call ONLY from the
    background build (it reads already-built sections + a cache KPI history).

    ``sections`` is the in-progress payload sections dict from
    ``build_ops_stream_payload`` (contains integrity, anomalies, chat_queue,
    upstream_health, storage, api_health, scheduler_health, …).
    """
    now = now or timezone.now()
    integrity = sections.get("integrity") or {}
    anomalies = sections.get("anomalies") or []

    # --- KPI history + trends (Phase 8) ---
    kpis = _collect_kpis(sections, integrity, len(anomalies))
    history = _update_kpi_history(kpis)
    trends = _compute_trends(history)

    # --- Incidents (Phases 4/5/9/10) ---
    incidents = [_enrich_incident(a, sections, trends, now) for a in anomalies]
    incidents.sort(key=_incident_priority)

    # --- Customer impact (Phase 4) — worst of section + anomaly impacts ---
    section_impacts = _section_impacts(sections)
    all_impacts = list(section_impacts)
    for a in anomalies:
        lvl, phrase = _anomaly_impact(a)
        all_impacts.append((lvl, phrase, a.get("engine_name") or "engine"))
    if all_impacts:
        impact_level = max(i[0] for i in all_impacts)
        # Phrases from the impacts AT the winning level (deduped, ordered).
        top_phrases = []
        for lvl, phrase, _sub in sorted(all_impacts, key=lambda x: -x[0]):
            if phrase not in top_phrases:
                top_phrases.append(phrase)
        impact_phrases = top_phrases[:4]
    else:
        impact_level = IMPACT_NONE
        impact_phrases = []

    # --- Subsystems + overall status (Phases 1/6) ---
    subsystems = _subsystem_states(sections, incidents)
    overall_raw = _overall_status(integrity, sections, incidents)
    # Recovery stabilization: immediate on the way down, stability-gated +
    # incident-aware on the way up (adds the RECOVERING transitional state).
    overall, recovery_meta = _apply_recovery_hysteresis(overall_raw, incidents)

    # --- Plain-English summary + narrative (Phases 1/7) ---
    summary_lines = _plain_summary(overall, subsystems, impact_level, impact_phrases)
    narrative = _operational_narrative(overall, subsystems, sections, trends, incidents, now)

    # --- Score explanation (Phase 2) ---
    deductions = _score_deductions(integrity, anomalies)

    # --- Prioritized single recommendation (Phase 3) ---
    recommended_action = None
    if incidents:
        top = incidents[0]
        recommended_action = {
            "title": top["suggested_action"],
            "incident_id": top["id"],
            "engine": top["engine"],
            "action_key": top.get("action_key"),
            "severity_label": top["severity_label"],
            "customer_impact": top["customer_impact"],
            "customer_impact_level": top["customer_impact_level"],
            "started_at": top["detected_at"],
            "started_ago": top["detected_ago"],
            "confidence": top["confidence"],
        }

    return {
        "overall_status": overall,
        "overall_status_raw": overall_raw,   # pre-hysteresis (transparency)
        "recovery": recovery_meta,           # stability counters + block reason
        "customer_impact_level": impact_level,
        "customer_impact": _IMPACT_LABEL[impact_level],
        "customer_impact_phrases": impact_phrases,
        "summary_lines": summary_lines,
        "narrative": narrative,
        "score": {
            "value": integrity.get("score"),
            "posture": integrity.get("posture"),
            "deductions": deductions,
            "trend": trends.get("score"),
        },
        "recommended_action": recommended_action,
        "incidents": incidents,
        "subsystems": subsystems,
        "trends": trends,
        "active_incident_count": len(incidents),
        "computed_at": now.isoformat(),
    }
