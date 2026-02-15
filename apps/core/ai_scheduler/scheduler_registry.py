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
