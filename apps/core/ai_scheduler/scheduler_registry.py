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
