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

    # ── Step 1b: Protocol expiration check ──
    protocol_type = None
    if protocol:
        if protocol.target_end_date and protocol.target_end_date < as_of_date:
            # Protocol has expired — treat as no active protocol
            protocol_type = None
        else:
            protocol_type = protocol.protocol_type

    signals = _gather_signals(user, as_of_date, today_summary)

    # ── Step 2: Body Composition Signal ──
    body_comp = compute_body_composition_trend(user, as_of_date)

    # ── Step 3: Outcome Validation ──
    outcome = validate_outcome(user, body_comp, protocol_type)

    # ── Step 4: Conflict Detection ──
    conflicts = detect_conflicts(user, signals, body_comp, outcome)

    # ── Step 5: Conflict corrections (positive conflicts fix false negatives) ──
    outcome = apply_conflict_corrections(outcome, conflicts)

    # ── Step 6: Check for expired protocol decision ──
    if (
        protocol
        and protocol.target_end_date
        and protocol.target_end_date < as_of_date
    ):
        decision = {
            "decision_type": "protocol_expired",
            "primary_issue": "protocol_expired",
            "summary": (
                f"Your {protocol.protocol_type} protocol ended on "
                f"{protocol.target_end_date.strftime('%b %d')} — "
                f"the system has no active goal to evaluate against"
            ),
            "urgency": "this_week",
            "impact": "medium",
            "recommended_action": (
                "Set a new goal now. Without one, the system cannot tell you "
                "whether your efforts are working."
            ),
            "action_type": "strategy_adjustment",
            "action_category": "clarity",
        }
    else:
        # ── Step 7: Tier Evaluation ──
        decision = _evaluate_tiers(
            signals, today_summary, body_comp, protocol, outcome
        )

    # ── Step 8: Attach composition + outcome data ──
    decision["outcome_status"] = outcome.get("outcome_status")
    decision["outcome_evidence"] = outcome.get("outcome_evidence", [])
    decision["goal_trajectory"] = outcome.get("goal_trajectory")
    decision["trajectory_detail"] = outcome.get("trajectory_detail")
    decision["body_composition"] = body_comp
    decision["conflicts"] = conflicts
    decision["has_positive_conflict"] = any(c.get("positive") for c in conflicts)
    decision["confidence"] = body_comp.get("confidence", "low")
    decision["protocol_type"] = protocol_type

    # ── Step 9: Enrichments ──
    decision = _enrich_with_momentum(decision, user, as_of_date)
    decision = _enrich_with_impact(decision, protocol_type)

    # ── Step 10: Decision stability (prevent flip-flopping) ──
    decision = _stabilize_decision(decision, user)

    # ── Step 11: Clarity enrichment (eliminate "unknown" dead-ends) ──
    decision = _enrich_with_clarity(decision, signals, body_comp)

    # ── Step 12: Build narrative ──
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
            "summary": "You are losing muscle — your deficit is too aggressive",
            "urgency": "immediate",
            "impact": "high",
            "recommended_action": (
                "Increase protein to 1g per pound body weight and reduce your deficit by 200 calories today. "
                "This stops the muscle loss within 48 hours."
            ),
            "action_type": "strategy_adjustment",
            "action_category": "performance",
        }

    if speed_label == "TOO_FAST":
        return {
            "decision_type": "health_risk",
            "primary_issue": "extreme_deficit",
            "summary": "Weight is dropping too fast — your body is burning muscle for fuel",
            "urgency": "immediate",
            "impact": "high",
            "recommended_action": (
                "Add 200-300 calories today. Losing faster than 1.5% body weight per week "
                "causes metabolic adaptation that stalls progress later."
            ),
            "action_type": "strategy_adjustment",
            "action_category": "performance",
        }

    if recovery is not None and recovery < 30:
        return {
            "decision_type": "health_risk",
            "primary_issue": "severe_fatigue",
            "summary": f"Recovery is critically low at {recovery}/100 — training today will make it worse",
            "urgency": "immediate",
            "impact": "high",
            "recommended_action": (
                "Skip today's workout. Get 8+ hours of sleep tonight. "
                "One rest day now prevents a week of forced recovery later."
            ),
            "action_type": "rest_recommendation",
            "action_category": "performance",
        }

    return None


def _build_outcome_failure_decision(protocol_type, body_comp, outcome):
    """Tier 1: Protocol failing despite compliance."""
    plateau_days = body_comp.get("plateau_days", 0)

    recommendations = {
        "cut": (
            "Recalculate your TDEE at current weight — the deficit that worked 10 lbs ago "
            "is not creating a deficit now. If stalled 21+ days, do a structured diet break: "
            "eat at maintenance for 10-14 days, then resume. This resets metabolic adaptation."
        ),
        "bulk": (
            "Your training needs a new stimulus. Increase weight or volume on compound lifts this week. "
            "If the program hasn't changed in 6+ weeks, switch to a new one."
        ),
        "recomposition": (
            "Tighten calorie cycling: surplus on training days, deficit on rest days. "
            "Keep protein at 1g per pound minimum. Recomp only works with precision."
        ),
        "maintenance": (
            "Recalculate your maintenance calories — your body composition has changed "
            "and your old targets no longer hold."
        ),
    }

    return {
        "decision_type": "outcome_failure",
        "primary_issue": "protocol_stalled",
        "summary": (
            f"Your {protocol_type or 'protocol'} is not working — "
            f"you're doing everything right but your body isn't responding"
            + (f" ({plateau_days} days stalled)" if plateau_days > 0 else "")
        ),
        "urgency": "this_week",
        "impact": "high",
        "recommended_action": recommendations.get(
            protocol_type, recommendations["maintenance"]
        ),
        "action_type": "strategy_adjustment",
        "action_category": "performance",
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
            "summary": (
                f"Protein is at {protein_pct:.0f}% of target — "
                f"this is directly limiting muscle preservation"
            ),
            "urgency": "today",
            "impact": "high",
            "recommended_action": (
                "Add 30-40g protein at your next meal. Chicken breast, "
                "protein shake, or Greek yogurt. This is the single biggest "
                "lever for protecting muscle right now."
            ),
            "action_type": "nutrition_guidance",
            "action_category": "performance",
        }

    if nutrition_score < 60:
        return {
            "decision_type": "nutrition",
            "primary_issue": "poor_nutrition",
            "summary": (
                f"Nutrition is at {nutrition_score:.0f}% — "
                f"your body cannot produce results without fuel"
            ),
            "urgency": "this_week",
            "impact": "medium",
            "recommended_action": (
                "Hit your macro targets today. Every day below 60% compliance "
                "undermines the work you put in at the gym."
            ),
            "action_type": "nutrition_guidance",
            "action_category": "performance",
        }

    return None


def _check_recovery_deficit(signals, today):
    """Check for recovery issues."""
    recovery = signals.get("recovery_score")
    if recovery is not None and recovery < 50:
        return {
            "decision_type": "recovery",
            "primary_issue": "low_recovery",
            "summary": (
                f"Recovery is at {recovery}/100 — pushing hard today "
                f"will dig the hole deeper"
            ),
            "urgency": "today",
            "impact": "medium",
            "recommended_action": (
                "Go lighter today or swap to active recovery. "
                "One easy day now protects your next 3 hard sessions."
            ),
            "action_type": "training_adjustment",
            "action_category": "performance",
        }
    return None


def _check_hydration_deficit(signals, today):
    """Check for hydration issues."""
    hydration_pct = signals.get("hydration_pct")
    if hydration_pct is not None and hydration_pct < 50:
        return {
            "decision_type": "hydration",
            "primary_issue": "low_hydration",
            "summary": (
                f"Hydration is at {hydration_pct:.0f}% — dehydration reduces "
                f"strength and makes the scale unreliable"
            ),
            "urgency": "today",
            "impact": "low",
            "recommended_action": "Drink 16 oz water right now. Set a reminder for another 16 oz in 2 hours.",
            "action_type": "hydration_nudge",
            "action_category": "performance",
        }
    return None


def _check_training_gap(signals, today):
    """Check for training consistency issues."""
    training_score = signals.get("training_score", 100)
    if training_score < 60:
        return {
            "decision_type": "training",
            "primary_issue": "training_inconsistent",
            "summary": (
                f"Training consistency is at {training_score:.0f}% — "
                f"your body adapts to what you do consistently, not occasionally"
            ),
            "urgency": "this_week",
            "impact": "medium",
            "recommended_action": (
                "Do your next scheduled workout. No modifications, no excuses. "
                "Consistency beats intensity every time."
            ),
            "action_type": "training_adjustment",
            "action_category": "performance",
        }
    return None


def _build_on_track(body_comp, outcome):
    """Tier 6: Everything is good enough."""
    outcome_status = outcome.get("outcome_status", "unknown")
    verdict = body_comp.get("verdict", "no_data")

    if verdict == "recomposition":
        summary = "Everything is dialed in — fat is dropping and muscle is growing"
    elif verdict == "effective_cut":
        summary = "Your cut is working — fat loss confirmed, muscle preserved"
    elif verdict == "effective_bulk":
        summary = "Your bulk is on track — muscle is growing as expected"
    elif outcome_status == "working":
        summary = "On track — keep doing exactly what you're doing"
    else:
        summary = "No issues detected — maintain your current approach"

    return {
        "decision_type": "on_track",
        "primary_issue": "none",
        "summary": summary,
        "urgency": "this_week",
        "impact": "low",
        "recommended_action": "Keep doing what you're doing. No changes needed.",
        "action_type": "maintain",
        "action_category": "performance",
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
# Decision Stability (Flip-Flop Protection)
# =========================================================================


def _stabilize_decision(decision, user):
    """Prevent outcome_status from flip-flopping between evaluations.

    Rules:
    1. Read previous decision from last SAE snapshot.
    2. If outcome_status changed, only allow the change if:
       a. New status has been consistent for 2+ evaluations
          (approximated by persistence_days >= 1), OR
       b. Change is severe: working → not_working AND plateau confirmed.
    3. Otherwise, keep previous outcome_status.

    Also applies light hysteresis to fat_loss_status:
    - Once "confirmed", require stronger counter-evidence to flip out.
    """
    previous = _get_previous_decision(user)
    if not previous:
        return decision  # No history — accept current as-is

    prev_outcome = previous.get("outcome_status")
    new_outcome = decision.get("outcome_status")

    # If outcome hasn't changed, no stabilization needed
    if prev_outcome == new_outcome or prev_outcome is None or new_outcome is None:
        return decision

    # ── Check if change is severe (always allowed) ──
    severe_change = (
        prev_outcome == "working"
        and new_outcome == "not_working"
        and decision.get("body_composition", {}).get("plateau_status") == "confirmed"
    )
    if severe_change:
        return decision  # Allow immediate flip for confirmed plateau

    # ── Check if new status has persistence (allows change) ──
    # persistence_days >= 1 means the underlying issue existed yesterday too
    if decision.get("persistence_days", 0) >= 1:
        return decision  # Issue is persistent, not a one-day blip

    # ── Flip not justified — hold previous outcome_status ──
    decision["outcome_status"] = prev_outcome
    decision["_stability_held"] = True  # Audit flag

    return decision


def _get_previous_decision(user):
    """Read the previous physical decision from SAE state.

    Returns None if no previous decision exists.
    """
    try:
        from apps.core.ai_state.state_engine import get_module_state
        health_state = get_module_state(user, "health") or {}
        return health_state.get("physical_decision")
    except Exception:
        return None


# =========================================================================
# Clarity Enrichment (eliminate "unknown" dead-ends)
# =========================================================================


def _enrich_with_clarity(decision, signals, body_comp):
    """When outcome is uncertain, explain WHY and provide a specific next step.

    Populates:
    - clarity_reason: WHY progress is unclear (with impact)
    - clarity_action: specific, time-bound next step
    - action_category: "clarity" (data/visibility fix) or "performance" (behavior fix)
    - signal_interpretation: one-line synthesis of contradictory signals

    Deterministic: checks signal gaps in priority order, first match wins.
    """
    decision.setdefault("clarity_reason", "")
    decision.setdefault("clarity_action", "")
    decision.setdefault("action_category", decision.get("action_category", "performance"))
    decision.setdefault("signal_interpretation", "")

    outcome = decision.get("outcome_status")
    confidence = decision.get("confidence", "low")

    # ── Only populate when uncertain ──
    needs_clarity = outcome == "unknown"
    if not needs_clarity and confidence in ("low", "medium"):
        if outcome in ("partial", "unknown", None):
            needs_clarity = True
        elif decision.get("has_positive_conflict") and outcome == "not_working":
            needs_clarity = True

    # ── Build signal_interpretation even when not unclear ──
    _build_signal_interpretation(decision, body_comp)

    if not needs_clarity:
        return decision

    # ── Determine reason (priority order, first match wins) ──
    bc = body_comp or {}
    fat_loss = bc.get("fat_loss_status", "no_data")
    muscle = bc.get("muscle_gain_status", "no_data")
    waist_trend = bc.get("waist_trend")
    weight_trend = bc.get("weight_trend")
    bc_confidence = bc.get("confidence", "low")

    nutrition_score = signals.get("nutrition_score", 100)
    training_score = signals.get("training_score", 100)

    # Priority 1: Not enough data at all
    if bc_confidence == "low" and fat_loss == "no_data":
        decision["clarity_reason"] = (
            "The system cannot assess your progress — there is not enough data yet. "
            "Without a baseline, every decision is a guess."
        )
        decision["clarity_action"] = (
            "Log your weight and measure your waist every morning for 7 days. "
            "That unlocks fat loss tracking and body composition signals."
        )
        decision["action_category"] = "clarity"
        return decision

    # Priority 2: Waist data missing or stale
    if waist_trend is None:
        decision["clarity_reason"] = (
            "We cannot confirm fat loss without waist measurements. "
            "The scale alone is unreliable — water, food timing, and creatine all distort it."
        )
        decision["clarity_action"] = (
            "Measure your waist today at navel level. Repeat in 7 days. "
            "Two measurements confirm the trend the scale cannot show."
        )
        decision["action_category"] = "clarity"
        return decision

    # Priority 3: Nutrition too inconsistent
    if nutrition_score < 60:
        decision["clarity_reason"] = (
            "Inconsistent nutrition is preventing your body from producing readable results. "
            "The system cannot separate real progress from noise when compliance is this variable."
        )
        decision["clarity_action"] = (
            "Hit your macro targets for 5 consecutive days. "
            "No partial days — 5 full days of compliance unlocks a clear progress signal."
        )
        decision["action_category"] = "performance"
        return decision

    # Priority 4: Training too inconsistent
    if training_score < 50:
        decision["clarity_reason"] = (
            "Training has been too sporadic to evaluate. "
            "Your body needs consistent stimulus before the system can measure its response."
        )
        decision["clarity_action"] = (
            "Complete your next 3 scheduled workouts without skipping. "
            "That creates enough signal to assess whether the program is working."
        )
        decision["action_category"] = "performance"
        return decision

    # Priority 5: Everything flat (possible plateau vs noise)
    if fat_loss in ("stalled", "not_confirmed") and waist_trend is not None:
        if abs(waist_trend) < 0.1 and weight_trend is not None and abs(weight_trend) < 0.3:
            decision["clarity_reason"] = (
                "Weight and waist are both flat. This is either a plateau or normal variation — "
                "the system needs 5 more days to tell the difference."
            )
            decision["clarity_action"] = (
                "Change nothing for 5 days. Stay on plan exactly as-is. "
                "If both stay flat, it confirms a plateau and the system will recommend a new strategy."
            )
            decision["action_category"] = "clarity"
            return decision

    # Priority 6: Possible early recomposition
    if fat_loss == "not_confirmed" and muscle in ("gaining", "maintaining"):
        decision["clarity_reason"] = (
            "Muscle signals are positive but fat loss is not yet confirmed. "
            "This pattern often means early recomposition — but we need one more data point to be sure."
        )
        decision["clarity_action"] = (
            "Measure your waist in 7 days. "
            "If waist drops while weight holds steady, recomposition is confirmed and your approach is working."
        )
        decision["action_category"] = "clarity"
        return decision

    # Fallback
    decision["clarity_reason"] = (
        "Signals are mixed — the system does not have enough consistency "
        "to make a confident assessment."
    )
    decision["clarity_action"] = (
        "Stay consistent with nutrition and training for the next 5 days. "
        "That clears the noise and reveals the real trend."
    )
    decision["action_category"] = "clarity"
    return decision


def _build_signal_interpretation(decision, body_comp):
    """Build a one-line synthesis when signals contradict each other.

    Only populated when signals tell a conflicting or nuanced story.
    """
    bc = body_comp or {}
    fat = bc.get("fat_loss_status", "no_data")
    muscle = bc.get("muscle_gain_status", "no_data")
    weight = bc.get("weight_trend")
    waist = bc.get("waist_trend")

    # Weight down but fat not confirmed → water loss or measurement gap
    if weight is not None and weight < -0.5 and fat == "not_confirmed":
        decision["signal_interpretation"] = (
            "Weight is dropping but fat loss is unconfirmed — "
            "this may be water loss, not true fat loss. Waist measurement will clarify."
        )
        return

    # Weight up but waist down → likely creatine or recomp
    if weight is not None and weight > 0.3 and waist is not None and waist < -0.1:
        decision["signal_interpretation"] = (
            "Weight is up but waist is down — this is not fat gain. "
            "Most likely water retention or muscle growth."
        )
        return

    # Fat confirmed but muscle losing → deficit too aggressive
    if fat == "confirmed" and muscle == "losing":
        decision["signal_interpretation"] = (
            "Fat is coming off but muscle is going with it — "
            "the deficit is too aggressive or protein is too low."
        )
        return

    # Everything flat → possible plateau
    if (fat in ("stalled", "not_confirmed")
            and weight is not None and abs(weight) < 0.3
            and waist is not None and abs(waist) < 0.1):
        decision["signal_interpretation"] = (
            "All signals are flat — the body has adapted to the current input. "
            "Something needs to change."
        )
        return

    # No contradictions — leave empty
    decision["signal_interpretation"] = ""


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
    """Behavior good + outcome good. Confident, affirming."""
    parts = []
    pt = d.get("protocol_type")
    if d.get("outcome_status") == "working":
        parts.append(f"Your {pt or 'approach'} is working.")

    if d.get("trajectory_detail"):
        parts.append(d["trajectory_detail"])

    for c in d.get("conflicts", []):
        if c.get("positive"):
            parts.append(c["resolution"])

    verdict = d.get("body_composition", {}).get("verdict")
    if verdict == "recomposition":
        parts.append("Fat is dropping and muscle is growing. This is the goal.")
    elif verdict == "effective_cut":
        parts.append("Fat loss confirmed. Muscle preserved. This is a clean cut.")
    elif verdict == "effective_bulk":
        parts.append("Muscle is growing as expected.")

    if d.get("signal_interpretation"):
        parts.append(d["signal_interpretation"])

    parts.append("Keep doing what you're doing. No changes needed.")
    return " ".join(parts)


def _narrative_investigate(d):
    """Behavior good + outcome bad. Respect the effort, redirect the strategy."""
    parts = [
        "Your compliance has been strong — nutrition and training are dialed in."
    ]
    if d.get("outcome_status") == "not_working":
        pt = d.get("protocol_type")
        parts.append(
            f"But your {pt or 'protocol'} is not producing results. "
            f"The effort is there — the strategy needs to change."
        )
    elif d.get("outcome_status") == "partial":
        parts.append(
            "Results are behind where they should be given your effort."
        )

    plateau_days = d.get("body_composition", {}).get("plateau_days", 0)
    if plateau_days > 0:
        parts.append(f"Stalled for {plateau_days} days.")

    if d.get("signal_interpretation"):
        parts.append(d["signal_interpretation"])

    for c in d.get("conflicts", []):
        if not c.get("positive"):
            parts.append(c["resolution"])

    parts.append(d.get("recommended_action", ""))
    parts.append("This is not a discipline problem. It is a strategy problem.")
    return " ".join(parts)


def _narrative_caution(d):
    """Behavior bad + outcome good. Acknowledge results, warn about sustainability."""
    parts = [
        "Your body is responding right now — but the inputs are not sustainable."
    ]
    parts.append(d.get("summary", ""))
    if d.get("impact_statement"):
        parts.append(d["impact_statement"])

    if d.get("signal_interpretation"):
        parts.append(d["signal_interpretation"])

    parts.append(
        "Early results often come regardless of optimization. "
        "Without consistency, they plateau within 4-6 weeks."
    )
    parts.append(d.get("recommended_action", ""))
    return " ".join(parts)


def _narrative_correct(d):
    """Behavior bad + outcome bad. Direct, no hedging."""
    parts = [d.get("summary", "")]
    if d.get("impact_statement"):
        parts.append(d["impact_statement"])
    if d.get("outcome_status") == "not_working":
        pt = d.get("protocol_type")
        parts.append(f"Your {pt or 'approach'} is not producing results.")

    if d.get("signal_interpretation"):
        parts.append(d["signal_interpretation"])

    phase = d.get("messaging_phase", "initial")
    persistence = d.get("persistence_days", 0)
    if phase == "escalating":
        parts.append(f"This is day {persistence + 1}. The pattern is clear.")
    elif phase == "pattern_alert":
        parts.append(
            f"This has been going on for {persistence + 1} days. "
            f"It will not fix itself."
        )

    parts.append(d.get("recommended_action", ""))
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
        "clarity_reason": "The system cannot assess your progress without data.",
        "clarity_action": "Log your weight and measure your waist daily for 7 days to unlock insights.",
        "action_category": "clarity",
        "signal_interpretation": "",
        "narrative": "Physical intelligence data not yet available. Log weight and waist measurements to unlock progress tracking.",
    }
