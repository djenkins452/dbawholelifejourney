"""
Engine Runtime — Standard telemetry wrapper for engine execution.

Wraps any engine function call with EngineRun record creation,
timing, and status tracking. Used by both the ISE scheduler (via
Celery dispatch) and direct fallback execution.

Every ISE-scheduled engine that runs through this wrapper becomes
visible to COAS health monitoring via EngineRun records.

Project: Whole Life Journey
Path: apps/core/engine_runtime.py
"""

import logging
import time
import uuid

from django.utils import timezone

logger = logging.getLogger(__name__)


# =========================================================================
# TASK NAME → ENGINE CODE MAPPING
# =========================================================================
# Maps ISE scheduler task_name to the short engine code used in EngineRun
# records and COAS heartbeat monitoring.
#
# Core engines (monitored by ENGINE_CADENCES) are listed first.
# Additional ISE tasks follow — they get EngineRun telemetry but are
# not currently part of the COAS heartbeat cadence checks.
# =========================================================================

TASK_ENGINE_MAP = {
    # Core monitored engines (must match ENGINE_CADENCES keys)
    "generate_daily_briefings": "DBE",
    "update_learning_profiles": "GLOE",
    "refresh_guidance": "PGE",
    "generate_weekly_reports": "WIRE",
    "deliver_intelligence_notifications": "DNE",
    "aggregate_quality_metrics": "ICQG",
    "run_ual_synthetic": "UAL",
    "run_sae_synthetic": "SAE",
    "run_pie_synthetic": "PIE",
    "run_prie_synthetic": "PRIE",
    # Additional ISE-scheduled tasks
    "generate_observability_snapshot": "IOCD",
    "run_architecture_pass": "ARCH",
    "run_drift_scoring": "DRIFT",
    "run_assistant_triggers": "TRIGGERS",
    "compute_weekly_pressure": "WKPRESS",
    "queue_event_reflections": "REFLECT",
    "detect_relational_drift": "RELDRIFT",
    "validate_predictions": "PREDVAL",
    "evaluate_intervention_effectiveness": "INTEFF",
    "run_cdce_correlations": "CDCE",
    "run_cross_domain_insights": "XDOMAIN",
    "run_tomorrow_protection_pass": "TMRWPROT",
    "update_escalation_states": "ESCALATE",
    "compute_deadline_snapshots": "ECC",
    "compute_pressure_snapshots": "PRESSNAP",
    "run_protective_sweep": "PROTSWEEP",
    "deliver_protective_alerts": "PROTALRT",
    "schedule_cos_prompts": "COSSCHED",
    "deliver_cos_prompts": "COSDELIV",
    "create_maturity_snapshot": "MATURITY",
    "generate_cdce_check_ins": "CDCE_CI",
    "run_proactive_guidance": "PGS",
}

# Engine → intelligence pipeline phase (legacy fallback)
# The authoritative source is apps.core.engine_registry.
# get_engine_phase() checks the central registry first, then falls back here.
ENGINE_PHASE_MAP = {
    # Phase 1: Interpretation
    "UAL": 1,
    "SAE": 1,
    # Phase 2: Execution
    "PIE": 2,
    "PRIE": 2,
    "PGE": 2,
    "ICQG": 2,
    "DBE": 2,
    "WIRE": 2,
    "DNE": 2,
    "GLOE": 2,
    "CDCE": 2,
    "IOCD": 2,
    "PGS": 2,
}
DEFAULT_PHASE = 3  # Post-execution / governance


def get_engine_phase(engine_name):
    """
    Look up engine phase from the central registry, with fallback.

    Uses apps.core.engine_registry as authoritative source.
    Falls back to ENGINE_PHASE_MAP if registry lookup fails.
    """
    try:
        from apps.core.engine_registry import get_engine
        engine_def = get_engine(engine_name)
        if engine_def:
            return engine_def.phase
    except Exception:
        pass
    return ENGINE_PHASE_MAP.get(engine_name, DEFAULT_PHASE)


def get_engine_name(task_name):
    """
    Resolve ISE task_name to engine code.

    Falls back to uppercased task_name truncated to 10 chars.
    """
    return TASK_ENGINE_MAP.get(task_name, task_name[:10].upper())


def run_engine(engine_name, fn, *args, **kwargs):
    """
    Execute an engine function with EngineRun telemetry.

    Creates an EngineRun record before execution, then updates it
    with duration and success/error status after completion.

    Args:
        engine_name: Engine code (e.g., "GLOE", "DBE").
        fn: Callable to execute.
        *args, **kwargs: Passed to fn.

    Returns:
        The return value of fn(*args, **kwargs).

    Raises:
        Re-raises any exception from fn after recording it.
    """
    from apps.core.ai_observability.models import EngineRun

    trace_id = str(uuid.uuid4())
    phase = get_engine_phase(engine_name)
    now = timezone.now()

    run = EngineRun(
        trace_id=trace_id,
        engine_name=engine_name,
        phase=phase,
        started_at=now,
        status="success",
    )

    try:
        run.save()
    except Exception as e:
        # Don't block engine execution if telemetry write fails
        logger.warning(
            "Engine telemetry: failed to create EngineRun for %s: %s",
            engine_name, e,
        )
        return fn(*args, **kwargs)

    start = time.monotonic()
    try:
        result = fn(*args, **kwargs)

        duration_ms = int((time.monotonic() - start) * 1000)
        run.status = "success"
        run.ended_at = timezone.now()
        run.duration_ms = duration_ms
        if isinstance(result, dict):
            run.metadata = result
        try:
            run.save(update_fields=[
                "status", "ended_at", "duration_ms", "metadata",
            ])
        except Exception:
            logger.warning(
                "Engine telemetry: failed to update EngineRun for %s",
                engine_name,
            )

        logger.info(
            "Engine %s completed in %dms (trace=%s)",
            engine_name, duration_ms, trace_id[:8],
        )
        return result

    except Exception as e:
        duration_ms = int((time.monotonic() - start) * 1000)
        run.status = "error"
        run.ended_at = timezone.now()
        run.duration_ms = duration_ms
        run.error_type = type(e).__name__
        run.error_message = str(e)[:1000]
        try:
            run.save(update_fields=[
                "status", "ended_at", "duration_ms",
                "error_type", "error_message",
            ])
        except Exception:
            logger.warning(
                "Engine telemetry: failed to update EngineRun for %s",
                engine_name,
            )

        logger.error(
            "Engine %s failed after %dms: %s (trace=%s)",
            engine_name, duration_ms, e, trace_id[:8],
        )
        raise
