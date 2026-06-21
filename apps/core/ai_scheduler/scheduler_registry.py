"""
ISE — Scheduler Registry.

Defines which intelligence tasks are available for scheduling.
Each entry maps a task_name to its runner function and default interval.
"""

import logging

logger = logging.getLogger(__name__)

# Registry of scheduled intelligence tasks.
# Each entry: task_name → {function_path, interval_seconds, description}
SCHEDULED_TASKS = {
    "generate_daily_briefings": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_daily_briefings",
        "interval_seconds": 86400,  # 24 hours
        "description": "Generate daily briefings for all active users (DBE).",
    },
    "update_learning_profiles": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_learning_profile_updates",
        "interval_seconds": 21600,  # 6 hours
        "description": "Recalculate GLOE learning profiles for active users.",
    },
    "refresh_guidance": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_guidance_refresh",
        "interval_seconds": 21600,  # 6 hours
        "description": "Refresh proactive guidance for all active users (PGE).",
    },
    "generate_weekly_reports": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_weekly_reports",
        "interval_seconds": 604800,  # 7 days
        "description": "Generate weekly intelligence reports for all active users (WIRE).",
    },
    "deliver_intelligence_notifications": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_delivery_cycle",
        "interval_seconds": 600,  # 10 minutes
        "description": "Deliver intelligence notifications to user channels (DNE).",
    },
    "aggregate_quality_metrics": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_quality_metrics_aggregation",
        "interval_seconds": 604800,  # 7 days
        "description": "Aggregate ICQG quality metrics per rule/domain (weekly).",
    },
    "generate_observability_snapshot": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_observability_snapshot",
        "interval_seconds": 86400,  # 24 hours
        "description": "Generate daily intelligence observability metrics snapshot (IOCD).",
    },
    "run_architecture_pass": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_architecture_pass",
        "interval_seconds": 86400,  # 24 hours (nightly)
        "description": "Run nightly architecture pass to build tomorrow's plan (CoS).",
    },
    "run_drift_scoring": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_drift_scoring",
        "interval_seconds": 21600,  # 6 hours
        "description": "Compute drift scores and predictions for all active users (CoS).",
    },
    "run_assistant_triggers": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_assistant_triggers",
        "interval_seconds": 900,  # 15 minutes
        "description": "Check and execute assistant trigger conditions for active users (CoS).",
    },
    "compute_weekly_pressure": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_weekly_pressure",
        "interval_seconds": 21600,  # 6 hours
        "description": "Compute weekly pressure forecast for all active users (CoS).",
    },
    "queue_event_reflections": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_reflection_queue",
        "interval_seconds": 86400,  # 24 hours
        "description": "Scan previous day's events and queue post-event reflections (CoS).",
    },
    "detect_relational_drift": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_relational_drift",
        "interval_seconds": 86400,  # 24 hours
        "description": "Detect relational drift and generate reconnect guidance (CoS).",
    },
    "validate_predictions": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_prediction_validation",
        "interval_seconds": 86400,  # 24 hours
        "description": "Validate expired predictions against actual outcomes (Phase 4 feedback).",
    },
    "evaluate_intervention_effectiveness": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_intervention_effectiveness",
        "interval_seconds": 86400,  # 24 hours
        "description": "Evaluate intervention effectiveness and calibrate escalation speed (Phase 4 feedback).",
    },
    "run_cdce_correlations": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_cdce_synthetic",
        "interval_seconds": 21600,  # 6 hours
        "description": "Run cross-domain correlation engine for all active users (CDCE).",
    },
    "run_cross_domain_insights": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_cross_domain_insights",
        "interval_seconds": 21600,  # 6 hours
        "description": "Run cross-domain correlation insight rules for all active users (Phase 4 CoS).",
    },
    "run_tomorrow_protection_pass": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_tomorrow_protection_pass",
        "interval_seconds": 86400,  # 24 hours (7 PM run)
        "description": "Lock non-negotiables, detect overload, move flexible items in tomorrow's plan (Phase 5 Governance).",
    },
    # --- Phase 3: Escalation continuity + behavioral trends ---
    "update_escalation_states": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_escalation_updates",
        "interval_seconds": 86400,  # 24 hours (daily)
        "description": "Update escalation states and behavioral trends for all active users (Phase 3).",
    },
    # --- Phase 2: Deadline surfacing ---
    "compute_deadline_snapshots": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_deadline_snapshots",
        "interval_seconds": 300,  # 5 minutes
        "description": "Compute deadline snapshots for all active users (Phase 2 ECC).",
    },
    # --- Synthetic batch runners for context-dependent engines ---
    # These engines also fire per-request during chat, but scheduled
    # execution ensures cadence is maintained during idle periods.
    "run_ual_synthetic": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_ual_synthetic",
        "interval_seconds": 300,  # 5 minutes
        "description": "Run UAL arbitration for all active users (synthetic batch).",
    },
    "run_sae_synthetic": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_sae_synthetic",
        "interval_seconds": 300,  # 5 minutes
        "description": "Run SAE state rebuild for all active users (synthetic batch).",
    },
    "run_pie_synthetic": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_pie_synthetic",
        "interval_seconds": 300,  # 5 minutes
        "description": "Run PIE insight rules for all active users (synthetic batch).",
    },
    "run_prie_synthetic": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_prie_synthetic",
        "interval_seconds": 3600,  # 1 hour
        "description": "Run PRIE predictions for all active users (synthetic batch).",
    },
    # --- Phase 4: Pressure modeling ---
    "compute_pressure_snapshots": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_pressure_snapshots",
        "interval_seconds": 86400,  # 24 hours (daily sweep)
        "description": "Compute pressure snapshots for all active users (Phase 4 Pressure Modeling).",
    },
    # --- Phase 5: Protective Action Engine ---
    "run_protective_sweep": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_protective_sweep",
        "interval_seconds": 86400,  # 24 hours (daily)
        "description": "Recompute protective recommendations and schedule alerts for all active users (Phase 5).",
    },
    "deliver_protective_alerts": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_protective_alert_delivery",
        "interval_seconds": 300,  # 5 minutes
        "description": "Deliver due protective alerts via DNE with throttle respect (Phase 5).",
    },
    # --- CoS Prompting ---
    "schedule_cos_prompts": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_cos_prompt_scheduling",
        "interval_seconds": 21600,  # 6 hours
        "description": "Schedule CoS prompts for upcoming habits, goals, milestones, and events.",
    },
    "deliver_cos_prompts": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_cos_prompt_delivery",
        "interval_seconds": 300,  # 5 minutes
        "description": "Deliver due CoS prompts to all users.",
    },
    # --- CoS Situation State (Phase 2 — Behavior Architecture) ---
    "compute_cos_situation": {
        "function_path": "apps.core.ai_state.situation_computer.run_situation_compute",
        "interval_seconds": 900,  # 15 minutes
        "description": "Compute CoS situation state for all active users (pre-interpreted awareness, no LLM calls).",
    },
    "create_maturity_snapshot": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_maturity_snapshot",
        "interval_seconds": 86400,  # 24 hours
        "description": "Compute and persist daily system maturity snapshot (Phase 7.4).",
    },
    "generate_cdce_check_ins": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_cdce_check_ins",
        "interval_seconds": 21600,  # 6 hours
        "description": "Generate proactive check-ins from CDCE cross-domain correlations (Phase 7.2).",
    },
    "generate_health_trend_check_ins": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_health_trend_check_ins",
        "interval_seconds": 21600,  # 6 hours (throttler caps to ~1/day per user)
        "description": "Proactive strategic health-trend interventions — goal slipping, weight stalling/reversing, recommendation effectiveness, wins (Capability 6).",
    },
    "run_cos_event_engine": {
        "function_path": "apps.core.ai_scheduler.scheduler_runner.run_cos_event_engine_all",
        "interval_seconds": 10800,  # 3 hours
        "description": "Chief of Staff Event Engine — detect/persist/resolve strategic events (risk, opportunity, win) into the notification center + Beth context.",
    },
    # --- Proactive Guidance Scheduler ---
    "run_proactive_guidance": {
        "function_path": "apps.ai.proactive_checkins.run_proactive_guidance_scheduler",
        "interval_seconds": 900,  # 15 minutes
        "description": "Dispatch proactive check-ins based on per-user time windows (PGS).",
    },
}


def get_registered_tasks():
    """
    Return the full registry of scheduled tasks.

    Returns:
        dict — task_name → task config.
    """
    return SCHEDULED_TASKS.copy()


def get_task_function(task_name):
    """
    Dynamically import and return the runner function for a task.

    Args:
        task_name: Registered task name.

    Returns:
        callable or None.
    """
    task_config = SCHEDULED_TASKS.get(task_name)
    if not task_config:
        logger.warning(f"ISE: Unknown task: {task_name}")
        return None

    function_path = task_config["function_path"]
    try:
        module_path, func_name = function_path.rsplit(".", 1)
        import importlib
        module = importlib.import_module(module_path)
        return getattr(module, func_name)
    except (ImportError, AttributeError) as e:
        logger.error(f"ISE: Failed to import task function {function_path}: {e}")
        return None
