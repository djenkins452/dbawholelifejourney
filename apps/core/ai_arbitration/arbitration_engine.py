"""
UAL — Arbitration Engine (main orchestrator).

Entry point: run_arbitration(user) → ArbitrationResult

Pipeline:
    collect_signals → classify_scenario → fuse_signals →
    decide_intervention → build_narrative → log_decision
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
    success: bool = True


@_instrument_engine_run("UAL", 3)
def run_arbitration(user) -> ArbitrationResult:
    """
    Execute the full UAL arbitration pipeline.

    Collects signals from all engines, classifies the scenario,
    fuses cross-domain patterns, decides intervention style,
    builds a unified narrative, and logs the decision.

    This function NEVER raises — failures produce a safe
    STABLE_EXECUTION fallback.
    """
    result = ArbitrationResult()

    try:
        # Step 1: Collect signals
        from apps.core.ai_arbitration.signal_collector import collect_signals
        signals = collect_signals(user)
        strengths = signals.get("raw_strengths", {})
        result.raw_strengths = strengths

        # Step 2: Classify scenario
        from apps.core.ai_arbitration.scenario_classifier import classify_scenario
        scenario_result = classify_scenario(strengths)
        result.dominant_scenario = scenario_result["dominant_scenario"]
        result.secondary_scenarios = scenario_result["secondary_scenarios"]
        result.scenario_scores = scenario_result["scenario_scores"]
        result.confidence = scenario_result["confidence"]

        # Step 3: Fuse cross-domain signals
        from apps.core.ai_arbitration.signal_fuser import fuse_signals
        composites = fuse_signals(strengths)
        result.composites = composites

        # Step 4: Decide intervention
        from apps.core.ai_arbitration.intervention_engine import decide_intervention
        intervention = decide_intervention(
            scenario_result, composites, strengths, signals
        )
        result.intervention_style = intervention["intervention_style"]
        result.surfaced_items = intervention["surfaced_items"]
        result.suppressed_items = intervention["suppressed_items"]

        # Step 5: Build executive narrative
        from apps.core.ai_arbitration.narrative_engine import build_narrative
        narrative = build_narrative(
            scenario_result, composites, intervention, signals
        )
        result.narrative_injection = narrative

        # Step 6: Log decision (non-blocking)
        try:
            _log_decision(user, result, signals)
        except Exception as log_err:
            logger.debug("UAL decision logging skipped: %s", log_err)

        # Diagnostics: record arbitration decision
        _record_decision(
            engine_name="UAL",
            decision_type="arbitration",
            decision=f"SCENARIO={result.dominant_scenario}",
            rationale=(
                f"style={result.intervention_style} "
                f"confidence={result.confidence:.2f} "
                f"surfaced={len(result.surfaced_items)} "
                f"suppressed={len(result.suppressed_items)}"
            ),
            inputs_summary={
                "scenario_scores": result.scenario_scores,
                "composites": [c.get("name", "") for c in result.composites]
                if result.composites
                else [],
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
