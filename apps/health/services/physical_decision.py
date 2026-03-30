"""
Physical Intelligence V2 — Physical Decision Service.

Path: apps/health/services/physical_decision.py
Purpose: Single entry point for the Physical Intelligence System.
         Produces one deterministic PhysicalDecision per user per evaluation.

Architecture:
    - Pure function chain: gather → signal → validate → conflict → enrich → narrate
    - Called once per SAE cycle, result stored in SAE state
    - NEVER called on request path
    - No LLM dependency — all logic is deterministic
    - No new engines — this is a domain service function

Data Flow:
    Raw Data → DailyHealthSummary (pre-computed)
             → compute_body_composition_trend() (signal)
             → validate_outcome() (outcome check)
             → detect_conflicts() (contradiction detection)
             → _evaluate_tiers() (decision selection)
             → _enrich_*() (coaching context)
             → PhysicalDecision dict (output)

Copyright: (c) Whole Life Journey. All rights reserved.
"""

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)


def compute_physical_decision(user, as_of_date=None):
    """The single entry point for Physical Intelligence.

    Returns a dict representing the complete physical decision including:
    - The decision (what's happening)
    - Outcome validation (is it working)
    - Conflict detection (contradictions)
    - Impact assessment (why it matters)
    - Coaching context (how to communicate it)
    - Narrative (pre-assembled text for Beth)

    Args:
        user: Django User instance
        as_of_date: Date to compute for (default: today)

    Returns:
        dict — The complete PhysicalDecision.
    """
    if as_of_date is None:
        as_of_date = date.today()

    try:
        return _compute(user, as_of_date)
    except Exception:
        logger.error(
            "Physical decision failed for user %s", user.pk, exc_info=True
        )
        return _fallback_decision()


def _compute(user, as_of_date):
    """Core computation pipeline."""
    from .body_composition_signal import compute_body_composition_trend
    from .conflict_detection import apply_conflict_corrections, detect_conflicts
    from .outcome_validation import validate_outcome

    # ── Step 1: Gather inputs ──
    today_summary = _get_today_summary(user, as_of_date)
    protocol = _get_active_protocol(user)
    protocol_type = protocol.protocol_type if protocol else None
    signals = _gather_signals(user, as_of_date, today_summary)

    # ── Step 2: Body Composition Signal ──
    body_comp = compute_body_composition_trend(user, as_of_date)

    # ── Step 3: Outcome Validation ──
    outcome = validate_outcome(user, body_comp, protocol_type)

    # ── Step 4: Conflict Detection ──
    conflicts = detect_conflicts(user, signals, body_comp, outcome)

    # ── Step 5: Conflict corrections (positive conflicts fix false negatives) ──
    outcome = apply_conflict_corrections(outcome, conflicts)

    # ── Step 6: Tier Evaluation ──
    decision = _evaluate_tiers(signals, today_summary, body_comp, protocol, outcome)

    # ── Step 7: Attach composition + outcome data ──
    decision["outcome_status"] = outcome.get("outcome_status")
    decision["outcome_evidence"] = outcome.get("outcome_evidence", [])
    decision["goal_trajectory"] = outcome.get("goal_trajectory")
    decision["trajectory_detail"] = outcome.get("trajectory_detail")
    decision["body_composition"] = body_comp
    decision["conflicts"] = conflicts
    decision["has_positive_conflict"] = any(c.get("positive") for c in conflicts)
    decision["confidence"] = body_comp.get("confidence", "low")
    decision["protocol_type"] = protocol_type

    # ── Step 8: Enrichments ──
    decision = _enrich_with_momentum(decision, user, as_of_date)
    decision = _enrich_with_impact(decision, protocol_type)

    # ── Step 9: Build narrative ──
    decision["narrative"] = _build_narrative(decision)

    return decision


# =========================================================================
# Tier Evaluation (Priority Hierarchy)
# =========================================================================

# Tier 0: Health Risk (always first, never overridden)
# Tier 1: Outcome Failure (protocol failing despite good compliance)
# Tier 2-5: Behavior Gaps (order shifts by protocol_type)
# Tier 6: On Track


def _evaluate_tiers(signals, today, body_comp, protocol, outcome):
    """Evaluate tier hierarchy. First tier that fires wins."""
    protocol_type = protocol.protocol_type if protocol else "maintenance"

    # ── Tier 0: Health Risk ──
    risk = _check_health_risk(today)
    if risk:
        return risk

    # ── Tier 1: Outcome Failure ──
    outcome_status = outcome.get("outcome_status")
    nutrition_score = signals.get("nutrition_score", 0)
    training_score = signals.get("training_score", 0)

    if (
        outcome_status == "not_working"
        and nutrition_score >= 70
        and training_score >= 60
        and body_comp.get("plateau_status") in ("confirmed", "possible")
    ):
        return _build_outcome_failure_decision(protocol_type, body_comp, outcome)

    # ── Tiers 2-5: Behavior Gaps (protocol-ordered) ──
    checks = _get_tier_order(protocol_type)
    for check_fn in checks:
        result = check_fn(signals, today)
        if result:
            return result

    # ── Tier 6: On Track ──
    return _build_on_track(body_comp, outcome)


def _check_health_risk(today):
    """Tier 0: Health risk checks."""
    if not today:
        return None

    recovery = today.get("recovery_score")
    muscle_risk = today.get("muscle_loss_risk_level")
    speed_label = today.get("fat_loss_speed_label")

    if muscle_risk == "HIGH":
        return {
            "decision_type": "health_risk",
            "primary_issue": "muscle_loss_risk",
            "summary": "Muscle loss risk is HIGH — adjust approach",
            "urgency": "immediate",
            "impact": "high",
            "recommended_action": (
                "Increase protein intake and reduce caloric deficit. "
                "Prioritize compound lifts to maintain strength stimulus."
            ),
            "action_type": "strategy_adjustment",
        }

    if speed_label == "TOO_FAST":
        return {
            "decision_type": "health_risk",
            "primary_issue": "extreme_deficit",
            "summary": "Losing weight too fast — risk of muscle loss and metabolic adaptation",
            "urgency": "immediate",
            "impact": "high",
            "recommended_action": "Increase calories by 200-300/day to slow the rate of loss.",
            "action_type": "strategy_adjustment",
        }

    if recovery is not None and recovery < 30:
        return {
            "decision_type": "health_risk",
            "primary_issue": "severe_fatigue",
            "summary": f"Recovery critically low at {recovery}/100 — rest recommended",
            "urgency": "immediate",
            "impact": "high",
            "recommended_action": "Skip today's workout. Focus on sleep and hydration.",
            "action_type": "rest_recommendation",
        }

    return None


def _build_outcome_failure_decision(protocol_type, body_comp, outcome):
    """Tier 1: Protocol failing despite compliance."""
    plateau_days = body_comp.get("plateau_days", 0)

    recommendations = {
        "cut": (
            "Recalculate TDEE at current weight. Consider a structured diet break "
            "(maintenance for 1-2 weeks) to reset metabolic adaptation."
        ),
        "bulk": (
            "Review progressive overload — are weights increasing weekly? "
            "If training is stale, consider a new program."
        ),
        "recomposition": (
            "Recomp requires precise calorie cycling. Consider surplus on "
            "training days, deficit on rest days. Ensure protein is at 1g/lb."
        ),
        "maintenance": "Review calorie targets — maintenance needs may have changed.",
    }

    return {
        "decision_type": "outcome_failure",
        "primary_issue": "protocol_stalled",
        "summary": (
            f"{(protocol_type or 'Protocol').title()} has stalled despite "
            f"good compliance"
            + (f" ({plateau_days} days)" if plateau_days > 0 else "")
        ),
        "urgency": "this_week",
        "impact": "high",
        "recommended_action": recommendations.get(
            protocol_type, recommendations["maintenance"]
        ),
        "action_type": "strategy_adjustment",
    }


def _get_tier_order(protocol_type):
    """Return behavior gap checks in protocol-appropriate order."""
    if protocol_type == "cut":
        # Cut: nutrition > recovery > hydration > training
        return [
            _check_nutrition_gap,
            _check_recovery_deficit,
            _check_hydration_deficit,
            _check_training_gap,
        ]
    elif protocol_type == "bulk":
        # Bulk: training > nutrition > recovery > hydration
        return [
            _check_training_gap,
            _check_nutrition_gap,
            _check_recovery_deficit,
            _check_hydration_deficit,
        ]
    else:
        # Default / recomp / maintenance
        return [
            _check_recovery_deficit,
            _check_nutrition_gap,
            _check_hydration_deficit,
            _check_training_gap,
        ]


def _check_nutrition_gap(signals, today):
    """Check for protein/nutrition deficit."""
    protein_pct = signals.get("protein_pct", 100)
    nutrition_score = signals.get("nutrition_score", 100)

    if protein_pct < 70:
        return {
            "decision_type": "nutrition",
            "primary_issue": "low_protein",
            "summary": f"Protein at {protein_pct:.0f}% of target — limiting muscle preservation",
            "urgency": "today",
            "impact": "high",
            "recommended_action": "Increase protein at next meal — chicken, fish, or protein shake.",
            "action_type": "nutrition_guidance",
        }

    if nutrition_score < 60:
        return {
            "decision_type": "nutrition",
            "primary_issue": "poor_nutrition",
            "summary": f"Overall nutrition at {nutrition_score:.0f}% — undermining progress",
            "urgency": "this_week",
            "impact": "medium",
            "recommended_action": "Focus on hitting macro targets today.",
            "action_type": "nutrition_guidance",
        }

    return None


def _check_recovery_deficit(signals, today):
    """Check for recovery issues."""
    recovery = signals.get("recovery_score")
    if recovery is not None and recovery < 50:
        return {
            "decision_type": "recovery",
            "primary_issue": "low_recovery",
            "summary": f"Recovery at {recovery}/100 — consider lighter training",
            "urgency": "today",
            "impact": "medium",
            "recommended_action": "Reduce intensity or swap to active recovery.",
            "action_type": "training_adjustment",
        }
    return None


def _check_hydration_deficit(signals, today):
    """Check for hydration issues."""
    hydration_pct = signals.get("hydration_pct")
    if hydration_pct is not None and hydration_pct < 50:
        return {
            "decision_type": "hydration",
            "primary_issue": "low_hydration",
            "summary": f"Hydration at {hydration_pct:.0f}% of target",
            "urgency": "today",
            "impact": "low",
            "recommended_action": "Drink 12-16 oz water now.",
            "action_type": "hydration_nudge",
        }
    return None


def _check_training_gap(signals, today):
    """Check for training consistency issues."""
    training_score = signals.get("training_score", 100)
    if training_score < 60:
        return {
            "decision_type": "training",
            "primary_issue": "training_inconsistent",
            "summary": f"Workout consistency at {training_score:.0f}% this week",
            "urgency": "this_week",
            "impact": "medium",
            "recommended_action": "Prioritize your next scheduled workout.",
            "action_type": "training_adjustment",
        }
    return None


def _build_on_track(body_comp, outcome):
    """Tier 6: Everything is good enough."""
    outcome_status = outcome.get("outcome_status", "unknown")
    verdict = body_comp.get("verdict", "no_data")

    summary_parts = ["All systems on track"]
    if outcome_status == "working":
        summary_parts.append("protocol is working")
    if verdict == "recomposition":
        summary_parts.append("recomposition detected")
    elif verdict == "effective_cut":
        summary_parts.append("fat loss confirmed with muscle preservation")
    elif verdict == "effective_bulk":
        summary_parts.append("muscle growth on track")

    return {
        "decision_type": "on_track",
        "primary_issue": "none",
        "summary": " — ".join(summary_parts),
        "urgency": "this_week",
        "impact": "low",
        "recommended_action": "Continue current approach.",
        "action_type": "maintain",
    }


# =========================================================================
# Enrichment Functions
# =========================================================================


def _enrich_with_momentum(decision, user, as_of_date):
    """Add persistence and trend from DailyHealthSummary history."""
    if decision["decision_type"] == "on_track":
        decision["persistence_days"] = 0
        decision["trend"] = "stable"
        decision["messaging_phase"] = "initial"
        return decision

    # Count consecutive days this issue type has existed
    persistence = _count_persistence(
        user, as_of_date, decision["decision_type"], decision["primary_issue"]
    )
    decision["persistence_days"] = persistence

    # Determine trend
    decision["trend"] = "stable"  # Default — can be refined with historical data

    # Messaging phase from persistence
    if persistence == 0:
        decision["messaging_phase"] = "initial"
    elif persistence <= 2:
        decision["messaging_phase"] = "reinforcing"
    elif persistence <= 6:
        decision["messaging_phase"] = "escalating"
    else:
        decision["messaging_phase"] = "pattern_alert"

    return decision


def _enrich_with_impact(decision, protocol_type):
    """Add impact statement based on static cause→effect mapping."""
    issue = decision.get("primary_issue", "none")

    impact_map = {
        "muscle_loss_risk": {
            "statement": "Active muscle tissue loss reduces BMR — harder to lose fat going forward.",
            "outcome_risk": "critical",
            "time_horizon": "this_week",
        },
        "extreme_deficit": {
            "statement": "Extreme deficit causes hormonal disruption and accelerated muscle loss.",
            "outcome_risk": "critical",
            "time_horizon": "this_week",
        },
        "severe_fatigue": {
            "statement": "Increased injury risk and muscle breakdown exceeding repair.",
            "outcome_risk": "high",
            "time_horizon": "today",
        },
        "protocol_stalled": {
            "statement": "Current approach is not producing results despite good compliance.",
            "outcome_risk": "high",
            "time_horizon": "this_week",
        },
        "low_protein": {
            "statement": _protein_impact(protocol_type),
            "outcome_risk": "high" if protocol_type == "cut" else "medium",
            "time_horizon": "today",
        },
        "poor_nutrition": {
            "statement": "Inconsistent nutrition undermines cumulative energy balance.",
            "outcome_risk": "medium",
            "time_horizon": "this_week",
        },
        "low_recovery": {
            "statement": "Incomplete recovery limits training adaptation and muscle repair.",
            "outcome_risk": "medium",
            "time_horizon": "today",
        },
        "low_hydration": {
            "statement": "Mild dehydration impairs performance and can mislead scale weight.",
            "outcome_risk": "low",
            "time_horizon": "today",
        },
        "training_inconsistent": {
            "statement": "Missed workouts reduce stimulus for adaptation and caloric expenditure.",
            "outcome_risk": (
                "high" if protocol_type == "bulk" else "medium"
            ),
            "time_horizon": "this_week",
        },
    }

    impact = impact_map.get(issue, {})
    decision["impact_statement"] = impact.get("statement", "")
    decision["outcome_risk"] = impact.get("outcome_risk", "low")
    decision["impact_time_horizon"] = impact.get("time_horizon", "today")

    # Escalate outcome_risk with persistence
    persistence = decision.get("persistence_days", 0)
    current_risk = decision.get("outcome_risk", "low")
    if persistence >= 7 and current_risk in ("low", "medium"):
        decision["outcome_risk"] = "high"
    elif persistence >= 3 and current_risk == "low":
        decision["outcome_risk"] = "medium"

    return decision


# =========================================================================
# Narrative Builder
# =========================================================================


def _build_narrative(decision):
    """Assemble the complete narrative for Beth.

    Structure varies by the behavior × outcome quadrant:
    - Reinforce: behavior good + outcome good
    - Investigate: behavior good + outcome bad
    - Caution: behavior bad + outcome good
    - Correct: behavior bad + outcome bad
    """
    quadrant = _determine_quadrant(decision)
    builders = {
        "reinforce": _narrative_reinforce,
        "investigate": _narrative_investigate,
        "caution": _narrative_caution,
        "correct": _narrative_correct,
    }
    return builders.get(quadrant, _narrative_correct)(decision)


def _determine_quadrant(decision):
    """Classify into the 2×2 behavior × outcome matrix."""
    behavior_good = decision.get("decision_type") in ("on_track", "outcome_failure")
    outcome_good = decision.get("outcome_status") in ("working", "unknown", None)

    if behavior_good and outcome_good:
        return "reinforce"
    elif behavior_good and not outcome_good:
        return "investigate"
    elif not behavior_good and outcome_good:
        return "caution"
    else:
        return "correct"


def _narrative_reinforce(d):
    """Behavior good + outcome good."""
    parts = []
    if d.get("outcome_status") == "working":
        pt = d.get("protocol_type")
        parts.append(f"Your {pt or 'approach'} is working.")
    if d.get("trajectory_detail"):
        parts.append(d["trajectory_detail"])

    # Positive conflicts
    for c in d.get("conflicts", []):
        if c.get("positive"):
            parts.append(c["resolution"])

    verdict = d.get("body_composition", {}).get("verdict")
    if verdict == "recomposition":
        parts.append("Fat is going down and muscle is going up.")
    elif verdict == "effective_cut":
        parts.append("Fat loss confirmed with muscle preservation.")
    elif verdict == "effective_bulk":
        parts.append("Muscle growth on track.")

    parts.append("Continue current approach.")
    return " ".join(parts)


def _narrative_investigate(d):
    """Behavior good + outcome bad."""
    parts = [
        "Compliance has been strong — nutrition and training are on target."
    ]
    if d.get("outcome_status") == "not_working":
        pt = d.get("protocol_type")
        parts.append(f"But your {pt or 'protocol'} isn't producing expected results.")
    elif d.get("outcome_status") == "partial":
        parts.append("Results are mixed — not what your effort should produce.")

    plateau_days = d.get("body_composition", {}).get("plateau_days", 0)
    if plateau_days > 0:
        parts.append(f"Plateau for {plateau_days} days.")

    for c in d.get("conflicts", []):
        if not c.get("positive"):
            parts.append(c["resolution"])

    parts.append(f"Recommended: {d.get('recommended_action', '')}")
    parts.append("This isn't a discipline problem — it's a strategy adjustment.")
    return " ".join(parts)


def _narrative_caution(d):
    """Behavior bad + outcome good."""
    parts = ["Good news — your body is responding well right now."]
    parts.append(d.get("summary", ""))
    if d.get("impact_statement"):
        parts.append(d["impact_statement"])
    parts.append(
        "Results are happening now but unlikely to continue without consistent effort."
    )
    parts.append(f"To sustain this: {d.get('recommended_action', '')}")
    return " ".join(parts)


def _narrative_correct(d):
    """Behavior bad + outcome bad."""
    parts = [d.get("summary", "")]
    if d.get("impact_statement"):
        parts.append(d["impact_statement"])
    if d.get("outcome_status") == "not_working":
        pt = d.get("protocol_type")
        parts.append(f"Your {pt or 'approach'} is not producing results right now.")

    phase = d.get("messaging_phase", "initial")
    persistence = d.get("persistence_days", 0)
    if phase == "escalating":
        parts.append(f"Day {persistence + 1} of this pattern.")
    elif phase == "pattern_alert":
        parts.append(f"Persistent for {persistence + 1} days.")

    parts.append(f"Recommended: {d.get('recommended_action', '')}")
    return " ".join(parts)


# =========================================================================
# Data Gathering (Pre-computed reads only)
# =========================================================================


def _get_today_summary(user, as_of_date):
    """Read today's DailyHealthSummary."""
    from apps.health.models import DailyHealthSummary

    try:
        return (
            DailyHealthSummary.objects.filter(user=user, summary_date=as_of_date)
            .values(
                "baseline_ready",
                "recovery_score",
                "muscle_loss_risk_level",
                "fat_loss_speed_label",
                "sleep_hours",
                "workout_count",
            )
            .first()
        )
    except Exception:
        return None


def _get_active_protocol(user):
    """Get active TransformationProtocol."""
    try:
        from apps.health.models import TransformationProtocol

        return (
            TransformationProtocol.objects.filter(user=user, is_active=True)
            .order_by("-start_date")
            .first()
        )
    except Exception:
        return None


def _gather_signals(user, as_of_date, today_summary):
    """Gather behavioral signals from existing data sources.

    Returns a flat dict of signal values for tier evaluation.
    All reads from pre-computed data — no live computation.
    """
    signals = {
        "nutrition_score": 100,
        "protein_pct": 100,
        "training_score": 100,
        "recovery_score": None,
        "hydration_pct": None,
        "sleep_hours": None,
    }

    # Recovery from DailyHealthSummary
    if today_summary:
        signals["recovery_score"] = today_summary.get("recovery_score")
        signals["sleep_hours"] = (
            float(today_summary["sleep_hours"])
            if today_summary.get("sleep_hours")
            else None
        )

    # Nutrition from SAE state
    try:
        from apps.core.ai_state.state_engine import get_module_state

        nutrition_state = get_module_state(user, "nutrition") or {}
        if nutrition_state.get("macro_compliance_score") is not None:
            signals["nutrition_score"] = nutrition_state["macro_compliance_score"]
        if nutrition_state.get("protein_compliance_pct") is not None:
            signals["protein_pct"] = nutrition_state["protein_compliance_pct"]
    except Exception:
        pass

    # Training from SAE state
    try:
        from apps.core.ai_state.state_engine import get_module_state

        fitness_state = get_module_state(user, "fitness") or {}
        if fitness_state.get("workout_consistency_score") is not None:
            signals["training_score"] = fitness_state["workout_consistency_score"]
    except Exception:
        pass

    # Hydration from WaterEntry
    try:
        from apps.health.models import WaterEntry

        daily_total = WaterEntry.get_daily_total(user, as_of_date)
        # Default goal 64 oz if no custom goal
        goal = 64
        try:
            from apps.core.ai_state.state_engine import get_state_value

            custom_goal = get_state_value(user, "health.water_goal_oz")
            if custom_goal:
                goal = float(custom_goal)
        except Exception:
            pass

        if daily_total is not None and goal > 0:
            signals["hydration_pct"] = min(100, (float(daily_total) / goal) * 100)
    except Exception:
        pass

    return signals


def _count_persistence(user, as_of_date, decision_type, primary_issue):
    """Count consecutive days the same issue has existed.

    Uses DailyHealthSummary to check backward from yesterday.
    """
    if decision_type == "on_track":
        return 0

    from apps.health.models import DailyHealthSummary

    # Map issue to DHS field and check function
    ISSUE_CHECKS = {
        "muscle_loss_risk": ("muscle_loss_risk_level", lambda v: v == "HIGH"),
        "extreme_deficit": ("fat_loss_speed_label", lambda v: v == "TOO_FAST"),
        "severe_fatigue": ("recovery_score", lambda v: v is not None and v < 30),
        "low_recovery": ("recovery_score", lambda v: v is not None and v < 50),
    }

    check = ISSUE_CHECKS.get(primary_issue)
    if not check:
        return 0

    field_name, check_fn = check

    recent = (
        DailyHealthSummary.objects.filter(
            user=user, summary_date__lt=as_of_date
        )
        .order_by("-summary_date")
        .values_list(field_name, flat=True)[:14]
    )

    count = 0
    for value in recent:
        if check_fn(value):
            count += 1
        else:
            break
    return count


# =========================================================================
# Impact Helpers
# =========================================================================


def _protein_impact(protocol_type):
    """Protocol-specific protein impact statement."""
    if protocol_type == "cut":
        return (
            "Protein is the primary lever for muscle preservation during a cut. "
            "Low protein increases muscle loss risk and slows fat loss."
        )
    elif protocol_type == "bulk":
        return "Insufficient protein limits muscle protein synthesis despite caloric surplus."
    else:
        return "Low protein impairs recovery and limits muscle adaptation."


# =========================================================================
# Fallback
# =========================================================================


def _fallback_decision():
    """Safe fallback when computation fails."""
    return {
        "decision_type": "on_track",
        "primary_issue": "none",
        "summary": "Physical intelligence data not yet available.",
        "urgency": "this_week",
        "impact": "low",
        "recommended_action": "Continue logging to build baseline data.",
        "action_type": "maintain",
        "outcome_status": None,
        "outcome_evidence": [],
        "goal_trajectory": None,
        "trajectory_detail": None,
        "body_composition": {},
        "conflicts": [],
        "has_positive_conflict": False,
        "confidence": "low",
        "protocol_type": None,
        "persistence_days": 0,
        "trend": "stable",
        "messaging_phase": "initial",
        "impact_statement": "",
        "outcome_risk": "low",
        "impact_time_horizon": "today",
        "narrative": "Physical intelligence data not yet available. Continue logging to build baseline data.",
    }
