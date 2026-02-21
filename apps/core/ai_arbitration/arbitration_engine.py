"""
UAL — Arbitration Engine (main orchestrator).

Entry point: run_arbitration(user) → ArbitrationResult

v2.1 Pipeline:
    1. Signal Collection
    2. Adaptive Weight Application
    3. Intervention Fatigue Bias
    4. Scenario Classification (confidence gap)
    5. Fuse Cross-Domain Signals
    6. Capacity Composite
    7. Capacity Volatility Check
    8. Pattern Analysis (Tier 1 + Tier 2)
    9. Recent Nudge Memory Penalty
    10. Intervention Decision (capacity + fatigue + pattern aware)
    11. Narrative Engine (style bias aware)
    12. Log Decision
    13. Update ScenarioHistory + InterventionResponseLog + RecentNudgeMemory
    14. Weight Tuning Check

All new steps wrapped in try/except. Failure defaults to v2 behavior.
"""
import logging
from dataclasses import dataclass, field

from apps.core.ai_observability.instrumentation import (
    log_engine_run as _instrument_engine_run,
    record_decision as _record_decision,
)

logger = logging.getLogger(__name__)


@dataclass
class ArbitrationResult:
    """Complete result of a UAL arbitration cycle."""

    dominant_scenario: str = "STABLE_EXECUTION"
    secondary_scenarios: list = field(default_factory=list)
    intervention_style: str = "EXECUTION"
    narrative_injection: str = ""
    surfaced_items: list = field(default_factory=list)
    suppressed_items: list = field(default_factory=list)
    composites: list = field(default_factory=list)
    scenario_scores: dict = field(default_factory=dict)
    raw_strengths: dict = field(default_factory=dict)
    confidence: float = 0.5
    confidence_level: str = "MODERATE"
    confidence_gap: float = 0.0
    capacity_score: float = 0.5
    capacity_state: str = "NORMAL"
    pattern_hints: list = field(default_factory=list)
    success: bool = True
    # v2.1 fields
    style_bias: str = "normal"
    fatigue_bias_applied: dict = field(default_factory=dict)
    pattern_tier2_active: bool = False
    volatility_flag: bool = False
    volatility_std_dev: float = 0.0


@_instrument_engine_run("UAL", 3)
def run_arbitration(user) -> ArbitrationResult:
    """
    Execute the full UAL v2.1 arbitration pipeline.

    Pipeline (never raises, always returns safe fallback):
    1. Signal Collection
    2. Adaptive Weight Application
    3. Intervention Fatigue Bias
    4. Scenario Classification (confidence gap)
    5. Fuse Cross-Domain Signals
    6. Capacity Composite
    7. Capacity Volatility Check
    8. Pattern Analysis (Tier 1 + Tier 2)
    9. Recent Nudge Memory Penalty (applied in intervention)
    10. Intervention Decision (capacity + fatigue + pattern aware)
    11. Narrative Engine (style bias aware)
    12. Log Decision
    13. Update ScenarioHistory + InterventionResponseLog + RecentNudgeMemory
    14. Weight Tuning Check

    All v2.1 steps wrapped in try/except. Failure defaults to v2 behavior.
    """
    result = ArbitrationResult()

    try:
        # Step 1: Signal Collection
        from apps.core.ai_arbitration.signal_collector import collect_signals
        signals = collect_signals(user)
        strengths = signals.get("raw_strengths", {})
        result.raw_strengths = strengths

        # Step 2: Adaptive Weight Application
        from apps.core.ai_arbitration.weight_tuner import get_weight_adjustments
        weight_adjustments = get_weight_adjustments(user)

        # Step 3: Intervention Fatigue Bias (v2.1)
        fatigue_data = None
        try:
            from apps.core.ai_arbitration.intervention_fatigue import compute_fatigue_scores
            fatigue_data = compute_fatigue_scores(user)
        except Exception as fat_err:
            logger.debug("UAL fatigue bias skipped (v2 fallback): %s", fat_err)

        # Step 4: Scenario Classification (with adaptive weights + confidence)
        from apps.core.ai_arbitration.scenario_classifier import classify_scenario
        scenario_result = classify_scenario(strengths, weight_adjustments)
        result.dominant_scenario = scenario_result["dominant_scenario"]
        result.secondary_scenarios = scenario_result["secondary_scenarios"]
        result.scenario_scores = scenario_result["scenario_scores"]
        result.confidence = scenario_result["confidence"]
        result.confidence_level = scenario_result["confidence_level"]
        result.confidence_gap = scenario_result["confidence_gap"]

        # Step 5: Fuse Cross-Domain Signals
        from apps.core.ai_arbitration.signal_fuser import fuse_signals
        composites = fuse_signals(strengths)
        result.composites = composites

        # Step 6: Capacity Composite
        from apps.core.ai_arbitration.capacity_engine import compute_capacity
        capacity = compute_capacity(strengths)
        result.capacity_score = capacity["capacity_score"]
        result.capacity_state = capacity["capacity_state"]

        # Step 7: Capacity Volatility Check (v2.1)
        volatility_adjustments = None
        try:
            from apps.core.ai_arbitration.capacity_volatility import (
                compute_capacity_volatility,
                apply_volatility_adjustments,
            )
            volatility = compute_capacity_volatility(user)
            volatility_adjustments = apply_volatility_adjustments(
                volatility, result.confidence_level
            )
            result.volatility_flag = volatility.get("volatility_flag", False)
            result.volatility_std_dev = volatility.get("std_dev", 0.0)
            # Apply confidence downgrade if volatile
            if volatility_adjustments.get("volatility_applied", False):
                result.confidence_level = volatility_adjustments["adjusted_confidence_level"]
                # Update scenario_result for downstream consumers
                scenario_result["confidence_level"] = result.confidence_level
        except Exception as vol_err:
            logger.debug("UAL volatility check skipped (v2 fallback): %s", vol_err)

        # Step 8: Pattern Analysis (Tier 1 + Tier 2)
        from apps.core.ai_arbitration.pattern_analyzer import analyze_patterns
        patterns = analyze_patterns(user)
        result.pattern_hints = patterns.get("escalation_hints", [])
        pattern_tier2 = patterns.get("tier2", {"tier2_active": False, "triggers": []})

        # Step 9 + 10: Intervention Decision
        # (nudge memory penalty applied inside via candidates,
        #  fatigue + pattern tier2 passed as context)
        from apps.core.ai_arbitration.intervention_engine import decide_intervention
        intervention = decide_intervention(
            scenario_result, composites, strengths, signals,
            capacity=capacity,
            pattern_hints=result.pattern_hints,
            fatigue_data=fatigue_data,
            pattern_tier2=pattern_tier2,
        )

        # v2.1: Apply nudge memory penalty to surfaced items
        try:
            from apps.core.ai_arbitration.nudge_memory import check_nudge_collisions
            intervention["surfaced_items"] = check_nudge_collisions(
                user, intervention["surfaced_items"],
                result.dominant_scenario,
            )
        except Exception as nudge_err:
            logger.debug("UAL nudge memory check skipped (v2 fallback): %s", nudge_err)

        result.intervention_style = intervention["intervention_style"]
        result.surfaced_items = intervention["surfaced_items"]
        result.suppressed_items = intervention["suppressed_items"]
        result.style_bias = intervention.get("style_bias", "normal")
        result.fatigue_bias_applied = intervention.get("fatigue_bias_applied", {})
        result.pattern_tier2_active = intervention.get("pattern_tier2_active", False)

        # Step 11: Build executive narrative (style bias + volatility aware)
        from apps.core.ai_arbitration.narrative_engine import build_narrative
        narrative = build_narrative(
            scenario_result, composites, intervention, signals,
            capacity=capacity,
            pattern_hints=result.pattern_hints,
            volatility=volatility_adjustments,
        )
        result.narrative_injection = narrative

        # Step 12: Log decision (non-blocking)
        try:
            _log_decision(user, result, signals)
        except Exception as log_err:
            logger.debug("UAL decision logging skipped: %s", log_err)

        # Step 13: Update histories (non-blocking)
        try:
            from apps.core.ai_arbitration.pattern_analyzer import log_scenario_history
            log_scenario_history(user, result)
        except Exception as hist_err:
            logger.debug("UAL history logging skipped: %s", hist_err)

        try:
            from apps.core.ai_arbitration.capacity_engine import log_daily_capacity
            log_daily_capacity(user, capacity)
        except Exception as cap_err:
            logger.debug("UAL capacity logging skipped: %s", cap_err)

        # v2.1: Log intervention response (surfaced event)
        try:
            from apps.core.ai_arbitration.intervention_fatigue import log_intervention_response
            log_intervention_response(user, result.dominant_scenario, "surfaced")
        except Exception as resp_err:
            logger.debug("UAL intervention response logging skipped: %s", resp_err)

        # v2.1: Record surfaced nudges in memory
        try:
            from apps.core.ai_arbitration.nudge_memory import record_surfaced_nudges
            record_surfaced_nudges(
                user, result.surfaced_items, result.dominant_scenario
            )
        except Exception as nudge_rec_err:
            logger.debug("UAL nudge memory recording skipped: %s", nudge_rec_err)

        # Step 14: Maybe tune weights (non-blocking)
        try:
            from apps.core.ai_arbitration.weight_tuner import maybe_tune_weights
            maybe_tune_weights(user)
        except Exception as tune_err:
            logger.debug("UAL weight tuning skipped: %s", tune_err)

        # Diagnostics: record arbitration decision
        _record_decision(
            engine_name="UAL",
            decision_type="arbitration",
            decision=f"SCENARIO={result.dominant_scenario}",
            rationale=(
                f"style={result.intervention_style} "
                f"confidence={result.confidence:.2f} "
                f"surfaced={len(result.surfaced_items)} "
                f"suppressed={len(result.suppressed_items)} "
                f"style_bias={result.style_bias} "
                f"tier2={'active' if result.pattern_tier2_active else 'inactive'} "
                f"volatility={result.volatility_std_dev:.3f}"
            ),
            inputs_summary={
                "scenario_scores": result.scenario_scores,
                "composites": [c.get("name", "") for c in result.composites]
                if result.composites
                else [],
                "fatigue_bias": result.fatigue_bias_applied,
                "pattern_tier2_active": result.pattern_tier2_active,
                "volatility_flag": result.volatility_flag,
            },
            affected_items=[
                s.get("label", "") for s in result.surfaced_items
            ],
            user_id=user.id,
            confidence=result.confidence,
        )

    except Exception as e:
        logger.warning("UAL arbitration failed, using safe fallback: %s", e)
        result.success = False
        result.narrative_injection = ""  # No injection on failure

    return result


def _log_decision(user, result: ArbitrationResult, signals: dict):
    """Log the arbitration decision for future refinement."""
    try:
        from apps.core.ai_arbitration.models import ArbitrationDecisionLog

        ArbitrationDecisionLog.objects.create(
            user=user,
            dominant_scenario=result.dominant_scenario,
            secondary_scenarios=result.secondary_scenarios,
            fused_signals={
                c["name"]: c["strength"]
                for c in result.composites
            },
            confidence_level=result.confidence_level,
            capacity_state=result.capacity_state,
            capacity_score=result.capacity_score,
            intervention_style=result.intervention_style,
            surfaced_items=[
                {"label": s["label"], "category": s["category"]}
                for s in result.surfaced_items
            ],
            suppressed_items=[
                {"label": s["label"], "category": s["category"]}
                for s in result.suppressed_items
            ],
            narrative=result.narrative_injection,
            raw_signals=result.raw_strengths,
            scenario_scores=result.scenario_scores,
        )
    except Exception as e:
        logger.debug("UAL log creation failed: %s", e)
