"""
Phase 5 — Strategy Selector.

Replaces simple tone switching with behavioral strategy switching.
Selects one of 4 strategies based on DriftPressure, capacity,
goal proximity, and historical responsiveness.

Strategies:
    ALIGN     — Minor drift. Light nudge, ask first, reinforce success.
    PROTECT   — Overload detected. Move flexible tasks, lock commitments.
    CHALLENGE — Declared values ≠ repeated behavior. Direct, evidence-based.
    COMPRESS  — Low capacity + high commitment. Reduce duration, not frequency.

Public API:
    - select_strategy(user, drift_pressure_result) -> StrategyDecision
    - select_strategies_for_user(user) -> list[StrategyDecision]
    - get_strategy_instructions(strategy) -> str
"""

import logging

logger = logging.getLogger(__name__)


# Strategy constants
STRATEGY_ALIGN = 'align'
STRATEGY_PROTECT = 'protect'
STRATEGY_CHALLENGE = 'challenge'
STRATEGY_COMPRESS = 'compress'

# Strategy instruction blocks for system prompt injection
STRATEGY_INSTRUCTIONS = {
    STRATEGY_ALIGN: (
        "STRATEGY: ALIGN — The user is slightly off track. "
        "Ask before acting. Use light nudges. Reinforce recent wins. "
        "Frame suggestions as opportunities, not corrections. "
        "Example: 'You've been solid this week — want to keep the streak going?'"
    ),
    STRATEGY_PROTECT: (
        "STRATEGY: PROTECT — The user is overloaded. "
        "Automatically deprioritize flexible items. Lock non-negotiables into the schedule. "
        "Inform after acting, don't ask permission for protective moves. "
        "Example: 'I moved your reading block to protect your workout — that's what matters today.'"
    ),
    STRATEGY_CHALLENGE: (
        "STRATEGY: CHALLENGE — The user's actions don't match their stated priorities. "
        "Be direct. Name the specific inconsistency with evidence. "
        "Ask for a conscious decision — keep or change the commitment. "
        "No emotion, no guilt, no apology. Just facts. "
        "Example: 'You said journaling is non-negotiable. You've missed it 4 of the last 5 days. "
        "Has something changed, or are we letting it slide?'"
    ),
    STRATEGY_COMPRESS: (
        "STRATEGY: COMPRESS — Capacity is low but commitments are high. "
        "Reduce duration, not frequency. Suggest minimum viable versions. "
        "Example: 'Full workout isn't realistic today. 15-minute maintenance session instead?'"
    ),
}


class StrategyDecision:
    """Result of strategy selection for a module."""
    __slots__ = (
        'module_key', 'display_name', 'strategy',
        'drift_pressure', 'commitment_level',
        'reason', 'action_items',
    )

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def to_dict(self):
        return {slot: getattr(self, slot, None) for slot in self.__slots__}


def select_strategy(user, drift_pressure_result):
    """
    Select the appropriate strategy for a module based on DriftPressure.

    Selection logic:
    1. If capacity < 50% AND commitment = non_negotiable → COMPRESS
    2. If drift_pressure >= 50 AND miss_rate >= 0.6 → CHALLENGE
    3. If capacity >= 80% OR drift_pressure >= 40 → PROTECT
    4. Otherwise → ALIGN

    Args:
        user: Django User instance.
        drift_pressure_result: DriftPressureResult from consistency evaluator.

    Returns:
        StrategyDecision
    """
    dp = drift_pressure_result
    strategy = STRATEGY_ALIGN
    reason = "Minor drift — standard guidance."
    action_items = []

    # Get capacity context
    capacity_pct = _get_capacity_pct(user)

    # Decision tree
    if (capacity_pct < 50
            and dp.commitment_level == 'non_negotiable'
            and dp.miss_rate >= 0.3):
        # Low capacity + non-negotiable + some misses → COMPRESS
        strategy = STRATEGY_COMPRESS
        reason = (
            f"Capacity at {capacity_pct}% but {dp.display_name} is non-negotiable. "
            "Reducing duration to maintain frequency."
        )
        action_items = [
            f"Suggest minimum-viable version of {dp.display_name}",
            "Protect frequency over duration",
        ]

    elif dp.drift_pressure >= 50 and dp.miss_rate >= 0.6:
        # High pressure + high miss rate → CHALLENGE
        strategy = STRATEGY_CHALLENGE
        reason = (
            f"{dp.display_name} declared as {dp.commitment_level} "
            f"but miss rate is {dp.miss_rate:.0%} over 7 days."
        )
        action_items = [
            f"Name inconsistency with {dp.display_name}",
            "Ask: keep commitment or reclassify?",
        ]

    elif capacity_pct >= 80 or dp.drift_pressure >= 40:
        # Overloaded or significant pressure → PROTECT
        strategy = STRATEGY_PROTECT
        if capacity_pct >= 80:
            reason = (
                f"Schedule at {capacity_pct}% capacity. "
                f"Protecting {dp.display_name} by moving flexible items."
            )
        else:
            reason = (
                f"Drift pressure at {dp.drift_pressure:.0f} for {dp.display_name}. "
                "Protecting before it gets worse."
            )
        action_items = [
            f"Lock {dp.display_name} in schedule",
            "Move flexible tasks to create space",
        ]

    elif dp.drift_pressure >= 15:
        # Minor drift → ALIGN
        strategy = STRATEGY_ALIGN
        reason = f"Mild drift on {dp.display_name} — light nudge appropriate."
        action_items = [
            f"Gently remind about {dp.display_name}",
            "Reinforce recent successes",
        ]

    else:
        # No significant drift — ALIGN with minimal intervention
        strategy = STRATEGY_ALIGN
        reason = f"{dp.display_name} is on track."
        action_items = []

    decision = StrategyDecision(
        module_key=dp.module_key,
        display_name=dp.display_name,
        strategy=strategy,
        drift_pressure=dp.drift_pressure,
        commitment_level=dp.commitment_level,
        reason=reason,
        action_items=action_items,
    )

    # Also set strategy on the drift pressure result
    dp.strategy = strategy

    return decision


def select_strategies_for_user(user):
    """
    Select strategies for all governance profiles.

    Returns:
        list of StrategyDecision, sorted by drift_pressure descending.
    """
    try:
        from apps.core.ai_governance.consistency_evaluator import compute_all_drift_pressures

        pressures = compute_all_drift_pressures(user)
        decisions = []

        for dp in pressures:
            decision = select_strategy(user, dp)
            decisions.append(decision)

        return decisions
    except Exception as e:
        logger.debug(f"Strategy selection failed: {e}")
        return []


def get_strategy_instructions(strategy):
    """Get system prompt instructions for a strategy."""
    return STRATEGY_INSTRUCTIONS.get(strategy, STRATEGY_INSTRUCTIONS[STRATEGY_ALIGN])


def build_strategy_system_injection(user):
    """
    Build the strategy section for system prompt injection.

    Returns:
        str — strategy instructions block.
    """
    decisions = select_strategies_for_user(user)
    if not decisions:
        return ""

    lines = ["--- GOVERNANCE STRATEGY ---"]

    # Group by strategy
    by_strategy = {}
    for d in decisions:
        by_strategy.setdefault(d.strategy, []).append(d)

    # Primary strategy = highest drift pressure item
    primary = decisions[0] if decisions else None
    if primary:
        lines.append(f"Primary: {get_strategy_instructions(primary.strategy)}")
        lines.append("")

    # At-risk items (non-negotiables with pressure)
    at_risk = [d for d in decisions
               if d.commitment_level == 'non_negotiable' and d.drift_pressure >= 20]
    if at_risk:
        items = ', '.join(f"{d.display_name} ({d.drift_pressure:.0f})" for d in at_risk[:4])
        lines.append(f"At Risk: {items}")

    # Challenge items
    challenges = by_strategy.get(STRATEGY_CHALLENGE, [])
    if challenges:
        items = ', '.join(d.display_name for d in challenges[:3])
        lines.append(f"Inconsistency Detected: {items}")

    # Compress items
    compresses = by_strategy.get(STRATEGY_COMPRESS, [])
    if compresses:
        items = ', '.join(d.display_name for d in compresses[:3])
        lines.append(f"Compress Mode: {items}")

    lines.append("--- END STRATEGY ---")
    return '\n'.join(lines)


def _get_capacity_pct(user):
    """Get current capacity percentage from today's plan directly (avoids circular import)."""
    try:
        import datetime as dt
        from django.utils import timezone
        from apps.core.blueprint.models import ArchitecturePlan

        today = timezone.localdate()
        plan = ArchitecturePlan.get_active_for_date(user, today)
        if not plan:
            return 50

        blocks = list(plan.blocks.all())
        total_minutes = 0
        for b in blocks:
            if b.start_time and b.end_time:
                s = dt.datetime.combine(today, b.start_time)
                e = dt.datetime.combine(today, b.end_time)
                d = (e - s).total_seconds() / 60
                if d > 0:
                    total_minutes += d

        waking_minutes = 16 * 60
        return min(100, round(total_minutes / waking_minutes * 100))
    except Exception:
        return 50
