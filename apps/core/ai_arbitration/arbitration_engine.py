"""
UAL — Arbitration Engine (main orchestrator).

Entry point: run_arbitration(user) → ArbitrationResult

v2 Pipeline:
    collect_signals → classify_scenario (with adaptive weights) →
    confidence_assessment → fuse_signals → capacity_assessment →
    pattern_analysis → decide_intervention → build_narrative →
    log_decision → log_history → log_capacity → maybe_tune
"""
import logging
from dataclasses import dataclass, field

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


def run_arbitration(user) -> ArbitrationResult:
    """
    Execute the full UAL v2 arbitration pipeline.

    Pipeline (never raises, always returns safe fallback):
    1. Collect signals
    2. Load adaptive weights
    3. Classify scenario (with weights + confidence dampening)
    4. Fuse cross-domain signals
    5. Assess capacity
    6. Analyze patterns
    7. Decide intervention (confidence + capacity aware)
    8. Build narrative
    9. Log decision + history + capacity
    10. Maybe tune weights
    """
    result = ArbitrationResult()

    try:
        # Step 1: Collect signals
        from apps.core.ai_arbitration.signal_collector import collect_signals
        signals = collect_signals(user)
        strengths = signals.get("raw_strengths", {})
        result.raw_strengths = strengths

        # Step 2: Load adaptive weight adjustments
        from apps.core.ai_arbitration.weight_tuner import get_weight_adjustments
        weight_adjustments = get_weight_adjustments(user)

        # Step 3: Classify scenario (with adaptive weights + confidence)
        from apps.core.ai_arbitration.scenario_classifier import classify_scenario
        scenario_result = classify_scenario(strengths, weight_adjustments)
        result.dominant_scenario = scenario_result["dominant_scenario"]
        result.secondary_scenarios = scenario_result["secondary_scenarios"]
        result.scenario_scores = scenario_result["scenario_scores"]
        result.confidence = scenario_result["confidence"]
        result.confidence_level = scenario_result["confidence_level"]
        result.confidence_gap = scenario_result["confidence_gap"]

        # Step 4: Fuse cross-domain signals
        from apps.core.ai_arbitration.signal_fuser import fuse_signals
        composites = fuse_signals(strengths)
        result.composites = composites

        # Step 5: Assess capacity
        from apps.core.ai_arbitration.capacity_engine import compute_capacity
        capacity = compute_capacity(strengths)
        result.capacity_score = capacity["capacity_score"]
        result.capacity_state = capacity["capacity_state"]

        # Step 6: Analyze patterns
        from apps.core.ai_arbitration.pattern_analyzer import analyze_patterns
        patterns = analyze_patterns(user)
        result.pattern_hints = patterns.get("escalation_hints", [])

        # Step 7: Decide intervention (confidence + capacity aware)
        from apps.core.ai_arbitration.intervention_engine import decide_intervention
        intervention = decide_intervention(
            scenario_result, composites, strengths, signals,
            capacity=capacity,
            pattern_hints=result.pattern_hints,
        )
        result.intervention_style = intervention["intervention_style"]
        result.surfaced_items = intervention["surfaced_items"]
        result.suppressed_items = intervention["suppressed_items"]

        # Step 8: Build executive narrative
        from apps.core.ai_arbitration.narrative_engine import build_narrative
        narrative = build_narrative(
            scenario_result, composites, intervention, signals,
            capacity=capacity,
            pattern_hints=result.pattern_hints,
        )
        result.narrative_injection = narrative

        # Step 9: Log decision + history + capacity (non-blocking)
        try:
            _log_decision(user, result, signals)
        except Exception as log_err:
            logger.debug("UAL decision logging skipped: %s", log_err)

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

        # Step 10: Maybe tune weights (non-blocking)
        try:
            from apps.core.ai_arbitration.weight_tuner import maybe_tune_weights
            maybe_tune_weights(user)
        except Exception as tune_err:
            logger.debug("UAL weight tuning skipped: %s", tune_err)

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
