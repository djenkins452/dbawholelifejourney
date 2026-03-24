# ==============================================================================
# File: apps/life/services/task_signals.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic task signals — trend detection from state
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-24
# ==============================================================================
"""
Deterministic Task Signals.

Identifies momentum, pressure, and slippage from canonical task state.

Architecture: raw data → canonical state → THIS → summary / coaching / nudges

Public API:
    build_task_signals(task_state) -> list[dict]

Rules:
    - Pure function: no DB, no user object, no caching, no side effects
    - Each signal represents ONE concept
    - Missing data → signal not emitted
"""

import logging

logger = logging.getLogger(__name__)


def _signal(key, state, value=None, insight=None):
    sig = {"key": key, "state": state}
    if value is not None:
        sig["value"] = value
    if insight is not None:
        sig["insight"] = insight
    return sig


def _eval_momentum(task_state):
    """
    Task momentum — how much progress today.

    Inputs: completed_today_detail.momentum_signal, count, total
    """
    detail = task_state.get("completed_today_detail", {})
    signal = detail.get("momentum_signal")
    count = detail.get("count", 0)

    contract = task_state.get("_contract", {})
    total_pending = contract.get("summary", {}).get("total_pending", 0)
    today_items = contract.get("today", {}).get("items", [])
    total_today = len(today_items) if today_items else 0

    if signal is None and count == 0 and total_today == 0:
        return None

    if signal == "high" or count >= 5:
        return _signal("task_momentum", "strong", value=count,
                       insight="You've made strong progress today")
    elif signal == "medium" or 2 <= count < 5:
        return _signal("task_momentum", "moderate", value=count,
                       insight="You've made some progress today")
    else:
        if total_today > 0 or total_pending > 0:
            return _signal("task_momentum", "low", value=count,
                           insight="No tasks completed yet today")
        return None


def _eval_pressure(task_state):
    """
    Task pressure — overdue + due today load.

    Inputs: overdue_count, due_today_tasks_detail
    """
    overdue = task_state.get("overdue_count", 0)
    today_detail = task_state.get("due_today_tasks_detail", [])
    today_count = len(today_detail) if today_detail else 0

    total = overdue + today_count

    if total == 0:
        return _signal("task_pressure", "low", value=0,
                       insight="No pressing tasks right now")

    if overdue >= 3 or total >= 6:
        return _signal("task_pressure", "high", value=total,
                       insight="Task pressure is high — several items need attention")
    elif overdue >= 1 or total >= 3:
        return _signal("task_pressure", "medium", value=total,
                       insight="A few tasks need attention this week")

    return _signal("task_pressure", "low", value=total,
                   insight="Task pressure is manageable")


def _eval_slippage(task_state):
    """
    Task slippage — are tasks consistently falling behind?

    Inputs: overdue_count, nn_skip_streaks, commitment summary
    """
    overdue = task_state.get("overdue_count", 0)
    skip_streaks = task_state.get("nn_skip_streaks", [])

    # Any foundational task with skip streak >= 2 = slipping
    active_streaks = [s for s in skip_streaks if s.get("streak", 0) >= 2]

    if overdue >= 3 or len(active_streaks) >= 2:
        return _signal("task_slippage", "slipping",
                       insight="Tasks are falling behind — consider reprioritizing")

    if overdue >= 1 or len(active_streaks) >= 1:
        # Check commitment consistency
        commitment = task_state.get("task_commitment_summary", {})
        consistency = commitment.get("consistency_score", 1.0)
        if consistency < 0.5:
            return _signal("task_slippage", "slipping",
                           insight="Foundational task consistency is low this week")

    return _signal("task_slippage", "stable",
                   insight="Tasks are on track")


def build_task_signals(task_state):
    """
    Build deterministic task signals from canonical state.

    Args:
        task_state: dict from get_module_state(user, 'tasks')

    Returns:
        list of signal dicts
    """
    task_state = task_state or {}
    signals = []

    momentum = _eval_momentum(task_state)
    if momentum:
        signals.append(momentum)

    pressure = _eval_pressure(task_state)
    if pressure:
        signals.append(pressure)

    slippage = _eval_slippage(task_state)
    if slippage:
        signals.append(slippage)

    return signals
