"""
UAL — Intervention Decision Engine.

Selects ONE intervention style based on the dominant scenario and
fused composites. Determines what to surface (max 3) and what to
suppress.

v2: Confidence dampening modifies surfacing. Capacity modifies
max surfaced items. Pattern hints adjust intensity.

v2.1: Capacity-based style bias. Fatigue-aware surfacing.
Pattern Tier 2 overrides. Nudge collision penalty.
"""
import logging

from apps.core.ai_observability.instrumentation import log_engine_span as _instrument_span

logger = logging.getLogger(__name__)

# Intervention styles
DIRECTIVE = "DIRECTIVE"          # Time-sensitive action required
PROTECTIVE = "PROTECTIVE"        # Reduce load, clear schedule
ACCOUNTABILITY = "ACCOUNTABILITY"  # Values misalignment
SUPPORTIVE = "SUPPORTIVE"        # Mood / emotional weight
STRATEGIC = "STRATEGIC"          # Forward planning
EXECUTION = "EXECUTION"          # Normal day shaping

# Scenario → default intervention style
SCENARIO_TO_INTERVENTION = {
    "TIME_CRITICAL": DIRECTIVE,
    "HEALTH_CRITICAL": PROTECTIVE,
    "DRIFT_CRITICAL": ACCOUNTABILITY,
    "MOOD_CRITICAL": SUPPORTIVE,
    "RELATIONSHIP_CRITICAL": STRATEGIC,
    "STABLE_EXECUTION": EXECUTION,
}

# Composites that override the default scenario→intervention mapping
COMPOSITE_OVERRIDES = {
    "LOW_CAPACITY_DAY": PROTECTIVE,
    "PHYSICAL_RISK": PROTECTIVE,
    "EMOTIONAL_OVERLOAD": SUPPORTIVE,
    "RECOVERY_NEEDED": PROTECTIVE,
    "ALIGNMENT_CRISIS": ACCOUNTABILITY,
}

# Intervention style descriptions (injected into narrative)
INTERVENTION_DESCRIPTIONS = {
    DIRECTIVE: "Time-sensitive. Lead with the urgent action. Be clear and direct.",
    PROTECTIVE: "Protect energy. Suggest reducing load. Frame suggestions as optional.",
    ACCOUNTABILITY: "Values gap detected. Name it clearly but without judgment. One step back.",
    SUPPORTIVE: "Emotional weight present. Acknowledge first. Gentle next move only.",
    STRATEGIC: "Forward planning opportunity. Frame the prep action and timeline.",
    EXECUTION: "Clean execution day. Top priority, one secondary, go.",
}

# Max items to surface (default — may be overridden by capacity)
MAX_SURFACED = 3

# Confidence-level surfacing rules (v2)
# LOW confidence: surface only 1 primary signal, soften
# MODERATE: normal (up to MAX_SURFACED)
# HIGH: full suppression allowed
CONFIDENCE_SURFACE_LIMITS = {
    "LOW": 1,
    "MODERATE": None,  # Use default/capacity
    "HIGH": None,      # Use default/capacity
}

# v2.1: Capacity-based style bias mapping
# Maps capacity_state → style_bias flag for narrative engine
CAPACITY_STYLE_BIAS = {
    "HIGH_CAPACITY": "strategic",    # Strategic framing allowed
    "NORMAL": "normal",              # Unchanged
    "LOW": "tactical",               # Tactical only, no multi-step planning
    "CRITICAL": "maintenance",       # Maintenance mode, one item, softened
}


@_instrument_span("UAL", "decide_intervention")
def decide_intervention(
    scenario_result: dict,
    composites: list,
    strengths: dict,
    signals: dict,
    capacity: dict = None,
    pattern_hints: list = None,
    fatigue_data: dict = None,
    pattern_tier2: dict = None,
) -> dict:
    """
    Select intervention style and determine surfaced/suppressed items.

    Args:
        scenario_result: output of classify_scenario()
        composites: output of fuse_signals()
        strengths: raw signal strengths (0-1)
        signals: full ArbitrationInput dict
        capacity: output of compute_capacity() (v2)
        pattern_hints: escalation hints from PatternAnalyzer (v2)
        fatigue_data: output of compute_fatigue_scores() (v2.1)
        pattern_tier2: Tier 2 pattern data (v2.1)

    Returns:
        {
            "intervention_style": str,
            "style_description": str,
            "surfaced_items": list[dict],
            "suppressed_items": list[dict],
            "primary_composite": str or None,
            "style_bias": str,  # v2.1
            "fatigue_bias_applied": dict,  # v2.1
            "pattern_tier2_active": bool,  # v2.1
        }
    """
    dominant = scenario_result["dominant_scenario"]
    style = SCENARIO_TO_INTERVENTION.get(dominant, EXECUTION)

    # Check if any composite overrides the intervention style
    primary_composite = None
    if composites:
        top_composite = composites[0]["name"]
        if top_composite in COMPOSITE_OVERRIDES:
            override = COMPOSITE_OVERRIDES[top_composite]
            # Only override if composite is stronger than scenario confidence
            if composites[0]["strength"] >= 0.5:
                style = override
                primary_composite = top_composite

    # Build candidate items for surfacing
    candidates = _build_candidates(strengths, signals)

    # v2.1: Apply fatigue bias to candidate priorities
    fatigue_bias_applied = {}
    try:
        if fatigue_data:
            scenario_bias = fatigue_data.get("scenario_bias", {})
            for candidate in candidates:
                cat = candidate.get("category", "")
                # Map category to scenario for bias lookup
                bias = scenario_bias.get(dominant, 0.0)
                if bias != 0.0:
                    # Scale bias to priority units (bias is ±0.05, priority is ~50-100)
                    # Multiply by 100 to make bias meaningful in priority space
                    candidate["priority"] += bias * 100
                    fatigue_bias_applied[dominant] = bias
    except Exception as e:
        logger.debug("UAL fatigue bias application skipped: %s", e)

    # Sort by priority (higher = more important to surface)
    candidates.sort(key=lambda x: x["priority"], reverse=True)

    # Determine max surfaced items (v2: capacity + confidence)
    max_items = _compute_max_surfaced(scenario_result, capacity)

    # v2.1: Pattern Tier 2 override — force max 1 surfaced
    pattern_tier2_active = False
    try:
        if pattern_tier2 and pattern_tier2.get("tier2_active", False):
            max_items = 1
            pattern_tier2_active = True
    except Exception as e:
        logger.debug("UAL pattern tier2 override skipped: %s", e)

    # Surface top N, suppress the rest
    surfaced = candidates[:max_items]
    suppressed = candidates[max_items:]

    # v2.1: Compute style bias from capacity state
    capacity_state = capacity.get("capacity_state", "NORMAL") if capacity else "NORMAL"
    style_bias = CAPACITY_STYLE_BIAS.get(capacity_state, "normal")

    return {
        "intervention_style": style,
        "style_description": INTERVENTION_DESCRIPTIONS.get(style, ""),
        "surfaced_items": surfaced,
        "suppressed_items": suppressed,
        "primary_composite": primary_composite,
        "style_bias": style_bias,
        "fatigue_bias_applied": fatigue_bias_applied,
        "pattern_tier2_active": pattern_tier2_active,
    }


def _compute_max_surfaced(scenario_result: dict, capacity: dict = None) -> int:
    """
    Compute maximum surfaced items based on confidence and capacity.

    Priority: confidence LOW override > capacity limit > default.
    """
    confidence_level = scenario_result.get("confidence_level", "MODERATE")

    # LOW confidence always limits to 1
    conf_limit = CONFIDENCE_SURFACE_LIMITS.get(confidence_level)
    if conf_limit is not None:
        return conf_limit

    # Capacity-based limit
    if capacity:
        return capacity.get("max_surfaced", MAX_SURFACED)

    return MAX_SURFACED


def _build_candidates(strengths: dict, signals: dict) -> list:
    """
    Build ranked candidate items from active signals.
    Only includes signals that are meaningfully active (> threshold).
    """
    candidates = []
    threshold = 0.25

    if strengths.get("medication_risk", 0) > threshold:
        health = signals.get("health_signals", {})
        missed = health.get("medications_missed", 0)
        scheduled = health.get("medications_scheduled", 0)
        taken = health.get("medications_taken", 0)
        candidates.append({
            "category": "HEALTH_GATE",
            "label": "Medication adherence",
            "detail": f"{taken}/{scheduled} taken, {missed} missed/late",
            "priority": 90 + strengths["medication_risk"] * 10,
            "signal_strength": strengths["medication_risk"],
        })

    if strengths.get("sleep_deficit", 0) > threshold:
        health = signals.get("health_signals", {})
        dur = health.get("sleep_duration_minutes")
        target = health.get("sleep_target_minutes", 480)
        detail = f"{dur or '?'}min vs {target}min target"
        candidates.append({
            "category": "HEALTH",
            "label": "Sleep deficit",
            "detail": detail,
            "priority": 70 + strengths["sleep_deficit"] * 10,
            "signal_strength": strengths["sleep_deficit"],
        })

    if strengths.get("drift_severity", 0) > threshold:
        drift = signals.get("drift_signals", {})
        candidates.append({
            "category": "ACCOUNTABILITY",
            "label": "Drift detected",
            "detail": f"Score: {drift.get('drift_score', 0)}, "
                      f"24h probability: {drift.get('drift_probability_24h', 0):.0%}",
            "priority": 75 + strengths["drift_severity"] * 10,
            "signal_strength": strengths["drift_severity"],
        })

    if strengths.get("non_negotiable_miss", 0) > threshold:
        drift = signals.get("drift_signals", {})
        candidates.append({
            "category": "ACCOUNTABILITY",
            "label": "Non-negotiables missed",
            "detail": f"{drift.get('non_negotiables_missed', 0)} missed today",
            "priority": 80 + strengths["non_negotiable_miss"] * 10,
            "signal_strength": strengths["non_negotiable_miss"],
        })

    if strengths.get("mood_decline", 0) > threshold:
        mood = signals.get("mood_signals", {})
        candidates.append({
            "category": "SUPPORTIVE",
            "label": "Mood trend",
            "detail": f"Trend: {mood.get('mood_trend', 'unknown')}",
            "priority": 60 + strengths["mood_decline"] * 10,
            "signal_strength": strengths["mood_decline"],
        })

    if strengths.get("schedule_overload", 0) > threshold:
        sched = signals.get("schedule_signals", {})
        candidates.append({
            "category": "PROTECTIVE",
            "label": "Schedule density",
            "detail": f"{sched.get('capacity_pct', 0):.0f}% capacity",
            "priority": 55 + strengths["schedule_overload"] * 10,
            "signal_strength": strengths["schedule_overload"],
        })

    if strengths.get("relationship_event", 0) > threshold:
        events = signals.get("upcoming_events", {}).get("significant_next_7d", [])
        if events:
            nearest = min(events, key=lambda e: e.get("days_until", 99))
            candidates.append({
                "category": "STRATEGIC",
                "label": f"Upcoming: {nearest.get('title', 'event')}",
                "detail": f"In {nearest.get('days_until', '?')} days"
                          f" ({nearest.get('person', '')})",
                "priority": 50 + strengths["relationship_event"] * 10,
                "signal_strength": strengths["relationship_event"],
            })

    if strengths.get("relationship_drift", 0) > threshold:
        rel = signals.get("relational_signals", {})
        drifting = rel.get("drifting_relationships", [])
        if drifting:
            top = drifting[0]
            candidates.append({
                "category": "STRATEGIC",
                "label": f"Relationship drift: {top.get('name', 'someone')}",
                "detail": f"Tier-{top.get('tier', '?')}, "
                          f"{top.get('days_since', '?')} days since contact",
                "priority": 45 + strengths["relationship_drift"] * 10,
                "signal_strength": strengths["relationship_drift"],
            })

    if strengths.get("deadline_pressure", 0) > threshold:
        upcoming = signals.get("upcoming_events", {})
        candidates.append({
            "category": "DIRECTIVE",
            "label": "Deadline pressure",
            "detail": f"{upcoming.get('overdue_tasks', 0)} overdue, "
                      f"{upcoming.get('approaching_deadlines', 0)} approaching",
            "priority": 65 + strengths["deadline_pressure"] * 10,
            "signal_strength": strengths["deadline_pressure"],
        })

    if strengths.get("calendar_urgency", 0) > threshold:
        next_4h = signals.get("schedule_signals", {}).get("next_4h_events", [])
        if next_4h:
            candidates.append({
                "category": "DIRECTIVE",
                "label": f"Next: {next_4h[0].get('title', 'event')}",
                "detail": f"At {next_4h[0].get('time', '?')}",
                "priority": 60 + strengths["calendar_urgency"] * 10,
                "signal_strength": strengths["calendar_urgency"],
            })

    if strengths.get("injury_risk", 0) > threshold:
        candidates.append({
            "category": "PROTECTIVE",
            "label": "Physical risk",
            "detail": "Injury keywords detected in recent journal",
            "priority": 85 + strengths["injury_risk"] * 10,
            "signal_strength": strengths["injury_risk"],
        })

    return candidates
