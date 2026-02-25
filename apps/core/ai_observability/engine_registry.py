"""
ENGINE_REGISTRY — Centralized engine metadata.

Single source of truth for all intelligence engines:
module paths, execution mode, pipeline phase, batch runners.

Used by:
  - TriggerEngineView (manual execution)
  - run_engine_task (Celery dispatch)
  - _action_rerun_engine (ops actions)
  - SAME auto-remediation

Project: Whole Life Journey
Path: apps/core/ai_observability/engine_registry.py
"""

import importlib
import logging

logger = logging.getLogger(__name__)

ENGINE_REGISTRY = {
    # --- Phase 1: Interpretation ---
    "UAL": {
        "label": "Unified Arbitration Layer",
        "phase": 1,
        "category": "Interpret",
        "can_manual_run": True,
        "batch_runner": "apps.core.ai_scheduler.scheduler_runner.run_ual_synthetic",
        "per_user_func": "apps.core.ai_arbitration.arbitration_engine.run_arbitration",
        "needs_user_context": True,
        "execution_mode": "synthetic",
    },
    "SAE": {
        "label": "State Awareness Engine",
        "phase": 1,
        "category": "Interpret",
        "can_manual_run": True,
        "batch_runner": "apps.core.ai_scheduler.scheduler_runner.run_sae_synthetic",
        "per_user_func": "apps.core.ai_state.state_updater.update_user_state",
        "needs_user_context": True,
        "execution_mode": "synthetic",
    },
    "PIE": {
        "label": "Pattern Insight Engine",
        "phase": 1,
        "category": "Interpret",
        "can_manual_run": True,
        "batch_runner": "apps.core.ai_scheduler.scheduler_runner.run_pie_synthetic",
        "per_user_func": "apps.core.ai_insights.insight_engine.run_insights",
        "needs_user_context": True,
        "execution_mode": "synthetic",
    },
    # --- Phase 2: Execution ---
    "PRIE": {
        "label": "Predictive Intelligence Engine",
        "phase": 2,
        "category": "Execute",
        "can_manual_run": True,
        "batch_runner": "apps.core.ai_scheduler.scheduler_runner.run_prie_synthetic",
        "per_user_func": "apps.core.ai_predictions.prediction_engine.generate_predictions",
        "needs_user_context": True,
        "execution_mode": "synthetic",
    },
    "PGE": {
        "label": "Proactive Guidance Engine",
        "phase": 2,
        "category": "Execute",
        "can_manual_run": True,
        "batch_runner": "apps.core.ai_scheduler.scheduler_runner.run_guidance_refresh",
        "per_user_func": "apps.core.ai_guidance.guidance_engine.generate_guidance",
        "needs_user_context": False,
        "execution_mode": "batch",
    },
    "ICQG": {
        "label": "Intelligent Content Quality Gate",
        "phase": 2,
        "category": "Execute",
        "can_manual_run": True,
        "batch_runner": "apps.core.ai_scheduler.scheduler_runner.run_icqg_synthetic",
        "per_user_func": "apps.core.ai_quality.quality_gate.filter_guidance_candidates",
        "needs_user_context": True,
        "execution_mode": "synthetic",
    },
    "CDCE": {
        "label": "Cross-Domain Correlation Engine",
        "phase": 3,
        "category": "Post-Exec",
        "can_manual_run": True,
        "batch_runner": "apps.core.ai_scheduler.scheduler_runner.run_cdce_synthetic",
        "per_user_func": "apps.core.ai_cross_domain.cdce_engine.run_cdce",
        "needs_user_context": True,
        "execution_mode": "synthetic",
    },
    # --- Phase 3: Post-Execution ---
    "DBE": {
        "label": "Daily Briefing Engine",
        "phase": 3,
        "category": "Post-Exec",
        "can_manual_run": True,
        "batch_runner": "apps.core.ai_scheduler.scheduler_runner.run_daily_briefings",
        "per_user_func": "apps.core.ai_briefing.briefing_engine.generate_daily_briefing",
        "needs_user_context": False,
        "execution_mode": "batch",
    },
    "WIRE": {
        "label": "Weekly Intelligence Report Engine",
        "phase": 3,
        "category": "Post-Exec",
        "can_manual_run": True,
        "batch_runner": "apps.core.ai_scheduler.scheduler_runner.run_weekly_reports",
        "per_user_func": "apps.core.ai_weekly_report.report_engine.generate_weekly_report",
        "needs_user_context": False,
        "execution_mode": "batch",
    },
    "DNE": {
        "label": "Delivery & Notification Engine",
        "phase": 3,
        "category": "Post-Exec",
        "can_manual_run": True,
        "batch_runner": "apps.core.ai_scheduler.scheduler_runner.run_delivery_cycle",
        "per_user_func": "apps.core.ai_delivery.delivery_engine.deliver_due_notifications",
        "needs_user_context": False,
        "execution_mode": "batch",
    },
}


def get_engine_meta(engine_name):
    """Return metadata dict for a single engine, or None."""
    return ENGINE_REGISTRY.get(engine_name)


def get_manual_engines():
    """Return list of engine codes that support manual execution."""
    return [name for name, meta in ENGINE_REGISTRY.items() if meta["can_manual_run"]]


def resolve_batch_runner(engine_name):
    """
    Import and return the batch runner callable for an engine.

    Returns None if engine has no batch_runner configured.
    """
    meta = ENGINE_REGISTRY.get(engine_name)
    if not meta or not meta.get("batch_runner"):
        return None

    dotted_path = meta["batch_runner"]
    module_path, func_name = dotted_path.rsplit(".", 1)

    try:
        module = importlib.import_module(module_path)
        return getattr(module, func_name)
    except (ImportError, AttributeError) as e:
        logger.error("Failed to resolve batch runner for %s: %s", engine_name, e)
        return None
