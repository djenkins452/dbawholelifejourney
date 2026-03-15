"""
Central Engine Registry — Single source of truth for all WLJ intelligence engines.

Project: Whole Life Journey
Path: apps/core/engine_registry.py
Purpose: Declarative registry of every engine in the system with metadata
         for discovery, validation, observability, and audit.

Usage:
    from apps.core.engine_registry import ENGINE_REGISTRY, get_engine, get_engines_by_phase

    engine = get_engine("SAE")
    phase_1 = get_engines_by_phase(1)
    scheduled = get_scheduled_engines()

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# =========================================================================
# Engine Phase Definitions
# =========================================================================

class EnginePhase(IntEnum):
    """Three-phase intelligence pipeline."""
    INTERPRETATION = 1   # Phase 1: Understand context & intent
    EXECUTION = 2        # Phase 2: Execute actions & generate intelligence
    POST_EXECUTION = 3   # Phase 3: Observe, govern, learn


# =========================================================================
# Engine Signal Types
# =========================================================================

class SignalType:
    """What an engine produces — engines should produce signals, not mutations."""
    CONTEXT = "context"              # Enriches CoS context for LLM
    INSIGHT = "insight"              # Generates Insight records
    PREDICTION = "prediction"        # Generates Prediction records
    GUIDANCE = "guidance"            # Generates GuidanceItem records
    STATE_UPDATE = "state_update"    # Updates UserState (SAE truth layer)
    NOTIFICATION = "notification"    # Delivers messages to user
    REPORT = "report"                # Generates reports (briefing, weekly)
    GOVERNANCE = "governance"        # Governance/quality signals
    MONITORING = "monitoring"        # System health monitoring
    ARBITRATION = "arbitration"      # Prioritization & conflict resolution
    DELIVERY = "delivery"            # Delivery channel management
    PERSONA = "persona"              # Personality & voice management


# =========================================================================
# Engine Definition
# =========================================================================

@dataclass(frozen=True)
class EngineDefinition:
    """Declarative definition of a WLJ intelligence engine."""
    code: str                              # Short code (e.g., "SAE", "PIE")
    name: str                              # Full name
    phase: EnginePhase                     # Pipeline phase
    module_path: str                       # Python module path
    signal_types: tuple = ()               # What it produces
    description: str = ""                  # Human-readable description
    ise_task_name: Optional[str] = None    # ISE scheduler task name (if scheduled)
    interval_seconds: Optional[int] = None # Default schedule interval
    mutates_state: bool = False            # True if engine writes to DB directly
    dependencies: tuple = ()               # Engine codes this depends on
    category: str = "core"                 # core, blueprint, domain, observability
    # --- Operational metadata (for manual triggers & observability) ---
    can_manual_run: bool = False           # Whether ops wall can trigger manually
    batch_runner: Optional[str] = None     # Dotted path to batch runner function
    per_user_func: Optional[str] = None    # Dotted path to per-user function
    execution_mode: str = "on_demand"      # on_demand, synthetic, batch


# =========================================================================
# THE REGISTRY — Single source of truth
# =========================================================================

ENGINE_REGISTRY: Dict[str, EngineDefinition] = {}

def _register(*engines: EngineDefinition):
    """Register engines into the global registry."""
    for engine in engines:
        if engine.code in ENGINE_REGISTRY:
            logger.warning(
                "Engine registry: duplicate code %s — overwriting", engine.code
            )
        ENGINE_REGISTRY[engine.code] = engine


# -------------------------------------------------------------------------
# Phase 1: Interpretation Engines
# -------------------------------------------------------------------------
_register(
    EngineDefinition(
        code="SUE",
        name="Semantic Understanding Engine",
        phase=EnginePhase.INTERPRETATION,
        module_path="apps.core.ai_semantics",
        signal_types=(SignalType.CONTEXT,),
        description="Interprets user intent semantics, ambiguity detection, confidence scoring.",
        category="core",
    ),
    EngineDefinition(
        code="SLCME",
        name="Shared Lifecycle Context Memory Engine",
        phase=EnginePhase.INTERPRETATION,
        module_path="apps.core.ai_memory",
        signal_types=(SignalType.CONTEXT,),
        description="Maintains conversation memory, rolling summaries, learned preferences.",
        category="core",
    ),
    EngineDefinition(
        code="HTIE",
        name="Holistic Temporal Intelligence Engine",
        phase=EnginePhase.INTERPRETATION,
        module_path="apps.core.time",
        signal_types=(SignalType.CONTEXT,),
        description="Time-aware intelligence: scheduling, temporal context, deadline awareness.",
        category="core",
    ),
    EngineDefinition(
        code="SAE",
        name="State Aggregation Engine",
        phase=EnginePhase.INTERPRETATION,
        module_path="apps.core.ai_state",
        signal_types=(SignalType.STATE_UPDATE, SignalType.CONTEXT),
        description="Aggregates user state into UserState truth layer. Source of truth for all engines.",
        ise_task_name="run_sae_synthetic",
        interval_seconds=21600,  # 6 hours
        mutates_state=True,
        category="core",
        can_manual_run=True,
        batch_runner="apps.core.ai_scheduler.scheduler_runner.run_sae_synthetic",
        per_user_func="apps.core.ai_state.state_updater.update_user_state",
        execution_mode="synthetic",
    ),
    EngineDefinition(
        code="UAL",
        name="User Arbitration Logic",
        phase=EnginePhase.INTERPRETATION,
        module_path="apps.core.ai_arbitration",
        signal_types=(SignalType.ARBITRATION, SignalType.CONTEXT),
        description="Arbitrates competing priorities, intervention decisions, capacity assessment.",
        ise_task_name="run_ual_synthetic",
        interval_seconds=21600,  # 6 hours
        category="core",
        can_manual_run=True,
        batch_runner="apps.core.ai_scheduler.scheduler_runner.run_ual_synthetic",
        per_user_func="apps.core.ai_arbitration.arbitration_engine.run_arbitration",
        execution_mode="synthetic",
    ),
)

# -------------------------------------------------------------------------
# Phase 2: Execution Engines
# -------------------------------------------------------------------------
_register(
    EngineDefinition(
        code="UAIO",
        name="Unified AI Orchestrator",
        phase=EnginePhase.EXECUTION,
        module_path="apps.core.ai_orchestrator",
        signal_types=(SignalType.CONTEXT,),
        description="Central orchestrator: intent routing, action execution, safety validation.",
        dependencies=("SUE", "SLCME", "HTIE", "SAE", "UAL"),
        category="core",
    ),
    EngineDefinition(
        code="PIE",
        name="Pattern Intelligence Engine",
        phase=EnginePhase.EXECUTION,
        module_path="apps.core.ai_insights",
        signal_types=(SignalType.INSIGHT,),
        description="Generates behavioral insights from user data patterns.",
        ise_task_name="run_pie_synthetic",
        interval_seconds=21600,  # 6 hours
        mutates_state=True,
        dependencies=("SAE",),
        category="core",
        can_manual_run=True,
        batch_runner="apps.core.ai_scheduler.scheduler_runner.run_pie_synthetic",
        per_user_func="apps.core.ai_insights.insight_engine.run_insights",
        execution_mode="synthetic",
    ),
    EngineDefinition(
        code="PRIE",
        name="Predictive Intelligence Engine",
        phase=EnginePhase.EXECUTION,
        module_path="apps.core.ai_predictions",
        signal_types=(SignalType.PREDICTION,),
        description="Generates forward-looking predictions from patterns and trends.",
        ise_task_name="run_prie_synthetic",
        interval_seconds=21600,  # 6 hours
        mutates_state=True,
        dependencies=("SAE",),  # PREDVAL adjusts confidence but is optional (feedback loop)
        category="core",
        can_manual_run=True,
        batch_runner="apps.core.ai_scheduler.scheduler_runner.run_prie_synthetic",
        per_user_func="apps.core.ai_predictions.prediction_engine.generate_predictions",
        execution_mode="synthetic",
    ),
    EngineDefinition(
        code="PGE",
        name="Proactive Guidance Engine",
        phase=EnginePhase.EXECUTION,
        module_path="apps.core.ai_guidance",
        signal_types=(SignalType.GUIDANCE,),
        description="Generates proactive guidance items based on insights and predictions.",
        ise_task_name="refresh_guidance",
        interval_seconds=21600,  # 6 hours
        mutates_state=True,
        dependencies=("SAE", "PIE", "PRIE", "GLOE", "ICQG"),
        category="core",
        can_manual_run=True,
        batch_runner="apps.core.ai_scheduler.scheduler_runner.run_guidance_refresh",
        execution_mode="batch",
    ),
    EngineDefinition(
        code="DBE",
        name="Daily Briefing Engine",
        phase=EnginePhase.EXECUTION,
        module_path="apps.core.ai_briefing",
        signal_types=(SignalType.REPORT,),
        description="Generates daily briefings summarizing user state and priorities.",
        ise_task_name="generate_daily_briefings",
        interval_seconds=86400,  # 24 hours
        mutates_state=True,
        dependencies=("SAE", "PIE", "PRIE", "PGE", "PERSONA", "ICQG", "EXPLAIN"),
        category="core",
        can_manual_run=True,
        batch_runner="apps.core.ai_scheduler.scheduler_runner.run_daily_briefings",
        execution_mode="batch",
    ),
    EngineDefinition(
        code="WIRE",
        name="Weekly Intelligence Report Engine",
        phase=EnginePhase.EXECUTION,
        module_path="apps.core.ai_weekly_report",
        signal_types=(SignalType.REPORT,),
        description="Generates weekly intelligence reports with trend analysis.",
        ise_task_name="generate_weekly_reports",
        interval_seconds=604800,  # 7 days
        mutates_state=True,
        dependencies=("SAE", "PIE", "PRIE", "PGE", "GLOE", "PERSONA", "ICQG", "EXPLAIN"),
        category="core",
        can_manual_run=True,
        batch_runner="apps.core.ai_scheduler.scheduler_runner.run_weekly_reports",
        execution_mode="batch",
    ),
    EngineDefinition(
        code="DNE",
        name="Delivery Notification Engine",
        phase=EnginePhase.EXECUTION,
        module_path="apps.core.ai_delivery",
        signal_types=(SignalType.DELIVERY, SignalType.NOTIFICATION),
        description="Delivers intelligence notifications across channels (push, SMS, email).",
        ise_task_name="deliver_intelligence_notifications",
        interval_seconds=600,  # 10 minutes
        dependencies=("PGE", "DBE", "WIRE", "PIE", "CDCE", "ICQG"),
        category="core",
        can_manual_run=True,
        batch_runner="apps.core.ai_scheduler.scheduler_runner.run_delivery_cycle",
        execution_mode="batch",
    ),
    EngineDefinition(
        code="GLOE",
        name="Generalized Learning & Optimization Engine",
        phase=EnginePhase.EXECUTION,
        module_path="apps.core.ai_learning",
        signal_types=(SignalType.CONTEXT,),
        description="Learns user preferences, patterns, and optimizes coaching approach.",
        ise_task_name="update_learning_profiles",
        interval_seconds=21600,  # 6 hours
        mutates_state=True,
        category="core",
    ),
    EngineDefinition(
        code="ICQG",
        name="Intelligence Confidence & Quality Gate",
        phase=EnginePhase.EXECUTION,
        module_path="apps.core.ai_quality",
        signal_types=(SignalType.GOVERNANCE,),
        description="Quality gate for intelligence outputs. Validates confidence, detects conflicts.",
        ise_task_name="aggregate_quality_metrics",
        interval_seconds=604800,  # 7 days
        category="core",
        can_manual_run=True,
        batch_runner="apps.core.ai_scheduler.scheduler_runner.run_icqg_synthetic",
        per_user_func="apps.core.ai_quality.quality_gate.filter_guidance_candidates",
        execution_mode="synthetic",
    ),
    EngineDefinition(
        code="CDCE",
        name="Cross-Domain Correlation Engine",
        phase=EnginePhase.EXECUTION,
        module_path="apps.core.ai_cross_domain",
        signal_types=(SignalType.INSIGHT, SignalType.CONTEXT),
        description="Discovers correlations across life domains (health, journal, faith, etc.).",
        ise_task_name="run_cdce_correlations",
        interval_seconds=21600,  # 6 hours
        mutates_state=True,
        dependencies=("SAE",),
        category="core",
        can_manual_run=True,
        batch_runner="apps.core.ai_scheduler.scheduler_runner.run_cdce_synthetic",
        per_user_func="apps.core.ai_cross_domain.cdce_engine.run_cdce",
        execution_mode="synthetic",
    ),
    EngineDefinition(
        code="EAE",
        name="Engagement Arbitration Engine",
        phase=EnginePhase.EXECUTION,
        module_path="apps.core.ai_eae",
        signal_types=(SignalType.ARBITRATION, SignalType.CONTEXT),
        description="Manages engagement budgets, drift escalation, capacity-aware surfacing.",
        category="core",
    ),
)

# -------------------------------------------------------------------------
# Phase 3: Post-Execution / Governance Engines
# -------------------------------------------------------------------------
_register(
    EngineDefinition(
        code="IOCD",
        name="Intelligence Observability & Compliance Dashboard",
        phase=EnginePhase.POST_EXECUTION,
        module_path="apps.core.ai_observability",
        signal_types=(SignalType.MONITORING,),
        description="Daily observability snapshots, system health metrics, maturity scoring.",
        ise_task_name="generate_observability_snapshot",
        interval_seconds=86400,  # 24 hours
        mutates_state=True,
        category="observability",
    ),
    EngineDefinition(
        code="SAME",
        name="System Autonomous Monitoring Engine",
        phase=EnginePhase.POST_EXECUTION,
        module_path="apps.core.ai_observability.same_engine",
        signal_types=(SignalType.MONITORING,),
        description="Real-time anomaly detection: missed runs, error spikes, looping, starvation.",
        interval_seconds=60,  # 60 seconds (Celery Beat)
        category="observability",
    ),
    EngineDefinition(
        code="MATURITY",
        name="System Maturity Engine",
        phase=EnginePhase.POST_EXECUTION,
        module_path="apps.core.ai_observability.maturity_engine",
        signal_types=(SignalType.MONITORING, SignalType.GOVERNANCE),
        description="6-dimension maturity scoring: coverage, adherence, quality, intelligence, engagement, governance.",
        ise_task_name="create_maturity_snapshot",
        interval_seconds=86400,  # 24 hours
        mutates_state=True,
        category="observability",
    ),
    EngineDefinition(
        code="PERSONA",
        name="Persona Engine",
        phase=EnginePhase.POST_EXECUTION,
        module_path="apps.core.ai_persona",
        signal_types=(SignalType.PERSONA, SignalType.CONTEXT),
        description="Manages Beth CoS personality, coaching styles, voice consistency.",
        category="core",
    ),
)

# -------------------------------------------------------------------------
# Blueprint Engines (Governance & Life Architecture)
# -------------------------------------------------------------------------
_register(
    EngineDefinition(
        code="ARCH",
        name="Architecture Engine",
        phase=EnginePhase.POST_EXECUTION,
        module_path="apps.core.blueprint.architecture_engine",
        signal_types=(SignalType.GOVERNANCE,),
        description="Nightly architecture pass: builds tomorrow's plan from blueprint.",
        ise_task_name="run_architecture_pass",
        interval_seconds=86400,  # 24 hours
        mutates_state=True,
        dependencies=("PRIE", "PGE", "EXPLAIN"),
        category="blueprint",
    ),
    EngineDefinition(
        code="DRIFT",
        name="Drift Engine",
        phase=EnginePhase.POST_EXECUTION,
        module_path="apps.core.drift",
        signal_types=(SignalType.GOVERNANCE, SignalType.CONTEXT),
        description="Computes drift scores measuring deviation from intended life blueprint.",
        ise_task_name="run_drift_scoring",
        interval_seconds=21600,  # 6 hours
        mutates_state=True,
        category="blueprint",
    ),
    EngineDefinition(
        code="PRESSURE",
        name="Pressure Engine",
        phase=EnginePhase.POST_EXECUTION,
        module_path="apps.core.blueprint.pressure_engine",
        signal_types=(SignalType.GOVERNANCE, SignalType.CONTEXT),
        description="Computes composite pressure index from density, compression, breach risk.",
        ise_task_name="compute_weekly_pressure",
        interval_seconds=21600,  # 6 hours
        mutates_state=True,
        category="blueprint",
    ),
    EngineDefinition(
        code="PROTECTIVE",
        name="Protective Engine",
        phase=EnginePhase.POST_EXECUTION,
        module_path="apps.core.blueprint.protective_engine",
        signal_types=(SignalType.GOVERNANCE, SignalType.NOTIFICATION),
        description="Detects deadline collisions, overload, and generates protective alerts.",
        ise_task_name="run_protective_sweep",
        interval_seconds=21600,  # 6 hours
        mutates_state=True,
        dependencies=("PRESSURE", "DRIFT"),
        category="blueprint",
    ),
    EngineDefinition(
        code="COS_GOV",
        name="CoS Governance Engine",
        phase=EnginePhase.POST_EXECUTION,
        module_path="apps.core.blueprint.cos_governance",
        signal_types=(SignalType.GOVERNANCE, SignalType.CONTEXT),
        description="Governance profile, accountability style, sensitivity boundaries.",
        category="blueprint",
    ),
)

# -------------------------------------------------------------------------
# Scheduling & Delivery Support Engines
# -------------------------------------------------------------------------
_register(
    EngineDefinition(
        code="ISE",
        name="Intelligence Scheduler Engine",
        phase=EnginePhase.EXECUTION,
        module_path="apps.core.ai_scheduler",
        signal_types=(),
        description="Orchestrates all scheduled engine runs via Celery Beat integration.",
        category="core",
    ),
    EngineDefinition(
        code="TRIGGERS",
        name="Assistant Triggers Engine",
        phase=EnginePhase.EXECUTION,
        module_path="apps.ai.assistant_intelligence",
        signal_types=(SignalType.NOTIFICATION,),
        description="Evaluates trigger conditions for proactive assistant messages.",
        ise_task_name="run_assistant_triggers",
        interval_seconds=900,  # 15 minutes
        category="core",
    ),
    EngineDefinition(
        code="ESCALATE",
        name="Escalation Engine",
        phase=EnginePhase.POST_EXECUTION,
        module_path="apps.core.ai_eae.escalation",
        signal_types=(SignalType.ARBITRATION,),
        description="Updates escalation states based on sustained drift patterns.",
        ise_task_name="update_escalation_states",
        interval_seconds=21600,  # 6 hours
        mutates_state=True,
        dependencies=("DRIFT",),
        category="core",
    ),
    EngineDefinition(
        code="REFLECT",
        name="Reflection Queue Engine",
        phase=EnginePhase.POST_EXECUTION,
        module_path="apps.core.blueprint.reflection_queue",
        signal_types=(SignalType.GUIDANCE,),
        description="Scans previous day events and queues post-event reflection prompts.",
        ise_task_name="queue_event_reflections",
        interval_seconds=86400,  # 24 hours
        mutates_state=True,
        dependencies=("PERSONA",),
        category="blueprint",
    ),
    EngineDefinition(
        code="RELDRIFT",
        name="Relational Drift Engine",
        phase=EnginePhase.POST_EXECUTION,
        module_path="apps.core.ai_relationships",
        signal_types=(SignalType.INSIGHT, SignalType.GUIDANCE),
        description="Detects relational drift and generates reconnect guidance.",
        ise_task_name="detect_relational_drift",
        interval_seconds=86400,  # 24 hours
        mutates_state=True,
        category="core",
    ),
    EngineDefinition(
        code="XDOMAIN",
        name="Cross-Domain Insight Engine",
        phase=EnginePhase.EXECUTION,
        module_path="apps.core.ai_cross_domain.insight_rules",
        signal_types=(SignalType.INSIGHT,),
        description="Applies cross-domain insight rules to discover life-domain correlations.",
        ise_task_name="run_cross_domain_insights",
        interval_seconds=21600,  # 6 hours
        mutates_state=True,
        dependencies=("SAE", "CDCE"),
        category="core",
    ),
    EngineDefinition(
        code="PREDVAL",
        name="Prediction Validation Engine",
        phase=EnginePhase.POST_EXECUTION,
        module_path="apps.core.ai_predictions.validation",
        signal_types=(SignalType.GOVERNANCE,),
        description="Validates expired predictions against actual outcomes for accuracy tracking.",
        ise_task_name="validate_predictions",
        interval_seconds=86400,  # 24 hours
        mutates_state=True,
        dependencies=("PRIE",),
        category="core",
    ),
    EngineDefinition(
        code="INTEFF",
        name="Intervention Effectiveness Engine",
        phase=EnginePhase.POST_EXECUTION,
        module_path="apps.core.ai_arbitration.intervention_effectiveness",
        signal_types=(SignalType.GOVERNANCE,),
        description="Evaluates intervention effectiveness and calibrates escalation speed.",
        ise_task_name="evaluate_intervention_effectiveness",
        interval_seconds=86400,  # 24 hours
        mutates_state=True,
        dependencies=("UAL", "ESCALATE"),
        category="core",
    ),
)

# -------------------------------------------------------------------------
# Blueprint Support Engines
# -------------------------------------------------------------------------
_register(
    EngineDefinition(
        code="ECC",
        name="Event Commitment Calendar Engine",
        phase=EnginePhase.POST_EXECUTION,
        module_path="apps.core.blueprint.ecc_engine",
        signal_types=(SignalType.GOVERNANCE,),
        description="Computes deadline snapshots for commitment tracking and pressure analysis.",
        ise_task_name="compute_deadline_snapshots",
        interval_seconds=21600,  # 6 hours
        mutates_state=True,
        category="blueprint",
    ),
    EngineDefinition(
        code="PRESSNAP",
        name="Pressure Snapshot Engine",
        phase=EnginePhase.POST_EXECUTION,
        module_path="apps.core.blueprint.pressure_snapshot",
        signal_types=(SignalType.GOVERNANCE,),
        description="Computes periodic pressure snapshots for trend analysis.",
        ise_task_name="compute_pressure_snapshots",
        interval_seconds=21600,  # 6 hours
        mutates_state=True,
        category="blueprint",
    ),
    EngineDefinition(
        code="TMRWPROT",
        name="Tomorrow Protection Engine",
        phase=EnginePhase.POST_EXECUTION,
        module_path="apps.core.blueprint.protective_engine",
        signal_types=(SignalType.GOVERNANCE, SignalType.NOTIFICATION),
        description="Forward-looking protective pass for tomorrow's schedule conflicts.",
        ise_task_name="run_tomorrow_protection_pass",
        interval_seconds=86400,  # 24 hours
        category="blueprint",
    ),
    EngineDefinition(
        code="PROTALRT",
        name="Protective Alert Delivery Engine",
        phase=EnginePhase.POST_EXECUTION,
        module_path="apps.core.blueprint.protective_engine",
        signal_types=(SignalType.NOTIFICATION,),
        description="Delivers protective alerts generated by the protective sweep.",
        ise_task_name="deliver_protective_alerts",
        interval_seconds=21600,  # 6 hours
        dependencies=("PROTECTIVE",),
        category="blueprint",
    ),
    EngineDefinition(
        code="COSSCHED",
        name="CoS Prompt Scheduler",
        phase=EnginePhase.EXECUTION,
        module_path="apps.core.ai_guidance.cos_prompts",
        signal_types=(SignalType.GUIDANCE,),
        description="Schedules proactive CoS prompts based on user state and timing.",
        ise_task_name="schedule_cos_prompts",
        interval_seconds=21600,  # 6 hours
        mutates_state=True,
        category="core",
    ),
    EngineDefinition(
        code="COSDELIV",
        name="CoS Prompt Delivery Engine",
        phase=EnginePhase.EXECUTION,
        module_path="apps.core.ai_guidance.cos_prompts",
        signal_types=(SignalType.DELIVERY,),
        description="Delivers scheduled CoS prompts at appropriate times.",
        ise_task_name="deliver_cos_prompts",
        interval_seconds=3600,  # 1 hour
        category="core",
    ),
    EngineDefinition(
        code="CDCE_CI",
        name="CDCE Check-in Generator",
        phase=EnginePhase.EXECUTION,
        module_path="apps.core.ai_cross_domain.checkin_generator",
        signal_types=(SignalType.GUIDANCE,),
        description="Generates cross-domain correlation check-in messages.",
        ise_task_name="generate_cdce_check_ins",
        interval_seconds=86400,  # 24 hours
        mutates_state=True,
        category="core",
    ),
)

# -------------------------------------------------------------------------
# Domain-Specific Engines
# -------------------------------------------------------------------------
_register(
    EngineDefinition(
        code="EXPLAIN",
        name="Explanation Engine",
        phase=EnginePhase.EXECUTION,
        module_path="apps.core.ai_explain",
        signal_types=(SignalType.CONTEXT,),
        description="Generates human-readable explanations for AI decisions and recommendations.",
        category="core",
    ),
    EngineDefinition(
        code="FEEDBACK",
        name="Feedback Engine",
        phase=EnginePhase.POST_EXECUTION,
        module_path="apps.core.ai_feedback",
        signal_types=(SignalType.GOVERNANCE,),
        description="Processes user feedback on AI outputs for quality improvement.",
        category="core",
    ),
    EngineDefinition(
        code="DOCS",
        name="Documentation Engine",
        phase=EnginePhase.POST_EXECUTION,
        module_path="apps.core.ai_docs",
        signal_types=(SignalType.CONTEXT,),
        description="AI documentation and knowledge base management.",
        category="core",
    ),
    EngineDefinition(
        code="GUID_LEARN",
        name="Guidance Learning Engine",
        phase=EnginePhase.POST_EXECUTION,
        module_path="apps.core.ai_guidance_learning",
        signal_types=(SignalType.GOVERNANCE,),
        description="Learns which guidance types are effective per user profile.",
        category="core",
    ),
    EngineDefinition(
        code="DOMAIN_REG",
        name="Domain Capability Registry",
        phase=EnginePhase.INTERPRETATION,
        module_path="apps.core.domain_registry",
        signal_types=(SignalType.CONTEXT,),
        description="Registry of domain capabilities for intent routing and action dispatch.",
        category="core",
    ),
)


# =========================================================================
# Query Functions
# =========================================================================

def get_engine(code: str) -> Optional[EngineDefinition]:
    """Get engine definition by code."""
    return ENGINE_REGISTRY.get(code)


def get_engines_by_phase(phase: int) -> List[EngineDefinition]:
    """Get all engines in a given pipeline phase."""
    return [e for e in ENGINE_REGISTRY.values() if e.phase == phase]


def get_scheduled_engines() -> List[EngineDefinition]:
    """Get all engines that have ISE scheduled tasks."""
    return [e for e in ENGINE_REGISTRY.values() if e.ise_task_name]


def get_engines_by_category(category: str) -> List[EngineDefinition]:
    """Get all engines in a given category."""
    return [e for e in ENGINE_REGISTRY.values() if e.category == category]


def get_engines_that_mutate() -> List[EngineDefinition]:
    """Get all engines that directly mutate state (audit flag)."""
    return [e for e in ENGINE_REGISTRY.values() if e.mutates_state]


def get_engine_codes() -> Set[str]:
    """Get all registered engine codes."""
    return set(ENGINE_REGISTRY.keys())


def get_engine_count() -> int:
    """Get total number of registered engines."""
    return len(ENGINE_REGISTRY)


def get_manual_engines() -> List[EngineDefinition]:
    """Get all engines that support manual execution from the Ops Wall."""
    return [e for e in ENGINE_REGISTRY.values() if e.can_manual_run]


# =========================================================================
# Dependency Graph Queries
# =========================================================================

def get_dependents(code: str) -> List[str]:
    """
    Get all engine codes that depend on the given engine.

    This answers: "If engine X is degraded, which engines are affected?"
    """
    return [
        e.code for e in ENGINE_REGISTRY.values()
        if code in e.dependencies
    ]


def get_dependency_chain(code: str, _visited: Optional[Set[str]] = None) -> List[str]:
    """
    Get the full transitive dependency chain for an engine (what it needs).

    Returns a topologically-ordered list of engine codes that must be healthy
    for this engine to function correctly. Includes cycle detection.
    """
    if _visited is None:
        _visited = set()

    engine = ENGINE_REGISTRY.get(code)
    if not engine or code in _visited:
        return []

    _visited.add(code)
    chain = []

    for dep_code in engine.dependencies:
        # Recurse into each dependency's dependencies first
        chain.extend(get_dependency_chain(dep_code, _visited))
        if dep_code not in chain:
            chain.append(dep_code)

    return chain


def get_impact_chain(code: str, _visited: Optional[Set[str]] = None) -> List[str]:
    """
    Get the full transitive impact chain for an engine (what it affects).

    Returns all engine codes that would be impacted if this engine fails.
    This is the reverse of get_dependency_chain — used for root cause analysis.
    """
    if _visited is None:
        _visited = set()

    if code in _visited:
        return []

    _visited.add(code)
    chain = []

    for dependent_code in get_dependents(code):
        if dependent_code not in chain:
            chain.append(dependent_code)
        chain.extend(get_impact_chain(dependent_code, _visited))

    # Deduplicate while preserving order
    seen = set()
    result = []
    for c in chain:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result


def get_dependency_graph() -> Dict[str, Dict]:
    """
    Build the full dependency graph for all engines.

    Returns a dict keyed by engine code with:
        {
            "code": str,
            "name": str,
            "phase": int,
            "dependencies": [str, ...],     # What this engine needs
            "dependents": [str, ...],        # What depends on this engine
            "dependency_depth": int,         # Longest chain to a root
            "impact_count": int,             # How many engines are affected if this fails
        }

    Useful for:
    - Ops Wall dependency visualization
    - Root cause analysis (high impact_count = high-value monitoring target)
    - Execution order validation
    """
    graph = {}

    for code, engine in ENGINE_REGISTRY.items():
        dependents = get_dependents(code)
        dep_chain = get_dependency_chain(code)
        impact = get_impact_chain(code)

        graph[code] = {
            "code": code,
            "name": engine.name,
            "phase": int(engine.phase),
            "category": engine.category,
            "dependencies": list(engine.dependencies),
            "dependents": dependents,
            "dependency_depth": len(dep_chain),
            "impact_count": len(impact),
            "impact_chain": impact,
        }

    return graph


def get_critical_engines(min_impact: int = 3) -> List[Dict]:
    """
    Get engines whose failure would impact the most other engines.

    These are the highest-value monitoring targets for the Ops Wall.
    Returns list of dicts sorted by impact_count descending.
    """
    graph = get_dependency_graph()
    critical = [
        node for node in graph.values()
        if node["impact_count"] >= min_impact
    ]
    return sorted(critical, key=lambda x: x["impact_count"], reverse=True)


# =========================================================================
# Registry Summary & Validation
# =========================================================================

def get_registry_summary() -> Dict:
    """
    Get a summary of the engine registry for observability/audit.

    Returns dict with counts by phase, category, scheduling, and dependency stats.
    """
    summary = {
        "total_engines": len(ENGINE_REGISTRY),
        "by_phase": {},
        "by_category": {},
        "scheduled_count": 0,
        "mutating_count": 0,
        "manual_run_count": 0,
        "with_dependencies": 0,
        "dependency_edges": 0,
    }

    for engine in ENGINE_REGISTRY.values():
        phase_name = engine.phase.name
        summary["by_phase"][phase_name] = summary["by_phase"].get(phase_name, 0) + 1
        summary["by_category"][engine.category] = summary["by_category"].get(engine.category, 0) + 1
        if engine.ise_task_name:
            summary["scheduled_count"] += 1
        if engine.mutates_state:
            summary["mutating_count"] += 1
        if engine.can_manual_run:
            summary["manual_run_count"] += 1
        if engine.dependencies:
            summary["with_dependencies"] += 1
            summary["dependency_edges"] += len(engine.dependencies)

    return summary


def validate_registry() -> List[str]:
    """
    Validate registry consistency. Returns list of warnings.

    Checks:
    - No duplicate codes
    - Phase boundaries respected
    - Scheduled engines have intervals
    - Dependencies exist in registry
    - No dependency cycles
    - Manual-run engines have batch_runner
    """
    warnings = []

    for code, engine in ENGINE_REGISTRY.items():
        # Scheduled engines must have intervals
        if engine.ise_task_name and not engine.interval_seconds:
            warnings.append(
                f"{code}: has ISE task '{engine.ise_task_name}' but no interval_seconds"
            )

        # Phase 1 engines should not mutate (except SAE which is the truth layer)
        if engine.phase == EnginePhase.INTERPRETATION and engine.mutates_state:
            if engine.code not in ("SAE",):
                warnings.append(
                    f"{code}: Phase 1 engine mutates state — review phase boundary"
                )

        # Check dependencies exist
        for dep in engine.dependencies:
            if dep not in ENGINE_REGISTRY:
                warnings.append(
                    f"{code}: depends on '{dep}' which is not in the registry"
                )

        # Manual-run engines should have a batch_runner
        if engine.can_manual_run and not engine.batch_runner:
            warnings.append(
                f"{code}: can_manual_run=True but no batch_runner configured"
            )

    # Check for dependency cycles
    cycle_warnings = _detect_dependency_cycles()
    warnings.extend(cycle_warnings)

    return warnings


def _detect_dependency_cycles() -> List[str]:
    """Detect circular dependencies in the engine graph."""
    warnings = []
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {code: WHITE for code in ENGINE_REGISTRY}
    path = []

    def dfs(code):
        color[code] = GRAY
        path.append(code)
        engine = ENGINE_REGISTRY.get(code)
        if engine:
            for dep in engine.dependencies:
                if dep not in color:
                    continue
                if color[dep] == GRAY:
                    # Found cycle
                    cycle_start = path.index(dep)
                    cycle = path[cycle_start:] + [dep]
                    warnings.append(
                        f"Dependency cycle detected: {' → '.join(cycle)}"
                    )
                elif color[dep] == WHITE:
                    dfs(dep)
        path.pop()
        color[code] = BLACK

    for code in ENGINE_REGISTRY:
        if color[code] == WHITE:
            dfs(code)

    return warnings
