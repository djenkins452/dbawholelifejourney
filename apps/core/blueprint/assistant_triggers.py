"""
Whole Life Journey - Assistant Triggers

Project: Whole Life Journey
Path: apps/core/blueprint/assistant_triggers.py
Purpose: Conditions for assistant-initiated conversations and delivery

Description:
    Defines when the assistant should proactively reach out to the user.
    Uses DNE for delivery with deduplication and throttling.

    Trigger conditions:
    - Approaching non-negotiable deadline
    - High drift probability spike
    - User idle during focus block
    - Nightly architecture summary ready
    - Curveball impact notification

Public API:
    - check_triggers(user) -> list[TriggerResult]
    - execute_trigger(user, trigger_result) -> InterventionLog or None
    - register_trigger(trigger_def) -> None

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import datetime
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from django.utils import timezone

from . import engine as blueprint_engine
from . import intervention_engine

logger = logging.getLogger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================


@dataclass
class TriggerResult:
    """Result of a trigger check."""
    trigger_type: str
    should_fire: bool
    level: int = 1  # Default: nudge
    message: str = ''
    behavior_key: str = ''
    evidence: dict = field(default_factory=dict)
    dedupe_key: str = ''


# =============================================================================
# TRIGGER DEFINITIONS
# =============================================================================


def check_approaching_deadline(user, blueprint):
    """Check for non-negotiables approaching their hard deadline."""
    results = []
    now = timezone.localtime()
    current_time = now.time()

    from . import engine as be
    non_negotiables = be.get_non_negotiables_for_date(user)

    for nn in non_negotiables:
        if not nn.hard_deadline:
            continue

        # Calculate minutes until deadline
        deadline_dt = datetime.datetime.combine(now.date(), nn.hard_deadline)
        now_dt = datetime.datetime.combine(now.date(), current_time)
        minutes_until = (deadline_dt - now_dt).total_seconds() / 60

        if 0 < minutes_until <= 60:  # Within 1 hour
            level = intervention_engine.determine_escalation_level(
                user, 'approaching_deadline',
                context={'tier': blueprint.get_tier_for_behavior(nn.behavior_key)},
            )
            results.append(TriggerResult(
                trigger_type='approaching_deadline',
                should_fire=True,
                level=level,
                message=(
                    f"'{nn.display_name}' deadline is in {int(minutes_until)} minutes. "
                    f"Have you started?"
                ),
                behavior_key=nn.behavior_key,
                evidence={
                    'deadline': str(nn.hard_deadline),
                    'minutes_remaining': int(minutes_until),
                },
                dedupe_key=f"deadline_{nn.behavior_key}_{now.date()}",
            ))

    return results


def check_drift_spike(user, blueprint):
    """Check for high drift probability spike."""
    from .drift_engine import predict_drift_probability

    prediction = predict_drift_probability(user)
    p24 = prediction.get('probability_24h', 0)

    if p24 >= 0.7:
        level = intervention_engine.determine_escalation_level(
            user, 'high_drift_probability',
            context={'severity': p24},
        )
        return [TriggerResult(
            trigger_type='high_drift_probability',
            should_fire=True,
            level=level,
            message=(
                f"Drift risk is elevated ({p24:.0%}). "
                f"Key factors: {_summarize_factors(prediction.get('factors', {}))}"
            ),
            evidence=prediction,
            dedupe_key=f"drift_spike_{timezone.localdate()}",
        )]

    return []


def check_architecture_ready(user, blueprint):
    """Check if nightly architecture summary is ready."""
    from .models import ArchitecturePlan

    tomorrow = timezone.localdate() + datetime.timedelta(days=1)
    plan = ArchitecturePlan.get_active_for_date(user, tomorrow)

    if plan and plan.created_at.date() == timezone.localdate():
        block_count = plan.blocks.count()
        warnings = plan.risk_warnings or []

        return [TriggerResult(
            trigger_type='architecture_ready',
            should_fire=True,
            level=intervention_engine.InterventionLog.LEVEL_NUDGE,
            message=(
                f"Tomorrow's plan is ready: {block_count} blocks scheduled. "
                + (f"{len(warnings)} risk warning(s)." if warnings else "No risk warnings.")
            ),
            evidence={
                'plan_id': plan.pk,
                'blocks': block_count,
                'warnings': len(warnings),
            },
            dedupe_key=f"arch_ready_{tomorrow}",
        )]

    return []


def check_idle_during_focus(user, blueprint):
    """
    Check if user appears idle during a scheduled focus block.
    Uses UserDailyActivity to detect inactivity.
    """
    from .models import ArchitecturePlan

    today = timezone.localdate()
    now = timezone.localtime().time()
    plan = ArchitecturePlan.get_active_for_date(user, today)

    if not plan:
        return []

    # Find current block
    current_block = plan.blocks.filter(
        start_time__lte=now,
        end_time__gte=now,
        is_completed=False,
        tier__lte=2,  # Only track tier 1-2 blocks
    ).first()

    if not current_block:
        return []

    # Check recent activity
    try:
        from apps.core.models import UserDailyActivity
        activity = UserDailyActivity.objects.filter(
            user=user, date=today,
        ).first()

        if activity:
            # If last seen was more than 30 minutes ago during a focus block
            last_dt = datetime.datetime.combine(today, activity.last_seen)
            now_dt = datetime.datetime.combine(today, now)
            idle_minutes = (now_dt - last_dt).total_seconds() / 60

            if idle_minutes >= 30:
                return [TriggerResult(
                    trigger_type='idle_during_focus',
                    should_fire=True,
                    level=intervention_engine.InterventionLog.LEVEL_NUDGE,
                    message=(
                        f"You have '{current_block.title}' scheduled now "
                        f"(T{current_block.tier}). Are you working on it?"
                    ),
                    behavior_key=current_block.behavior_key,
                    evidence={
                        'block_title': current_block.title,
                        'idle_minutes': int(idle_minutes),
                    },
                    dedupe_key=f"idle_focus_{current_block.pk}_{today}",
                )]
    except Exception:
        pass

    return []


# =============================================================================
# PUBLIC API
# =============================================================================


def check_triggers(user):
    """
    Run all trigger checks for a user.
    Returns list of TriggerResults that should fire.
    """
    blueprint = blueprint_engine.get_blueprint(user)

    if not blueprint.auto_architect_enabled:
        return []

    all_results = []

    trigger_checks = [
        check_approaching_deadline,
        check_drift_spike,
        check_architecture_ready,
        check_idle_during_focus,
    ]

    for check_fn in trigger_checks:
        try:
            results = check_fn(user, blueprint)
            all_results.extend([r for r in results if r.should_fire])
        except Exception as e:
            logger.warning("Trigger check %s failed: %s", check_fn.__name__, e)

    return all_results


def execute_trigger(user, trigger_result):
    """
    Execute a trigger by creating an intervention and optionally delivering it.

    Args:
        user: The user
        trigger_result: TriggerResult to execute

    Returns:
        InterventionLog or None (if deduped/throttled)
    """
    # Check deduplication
    if trigger_result.dedupe_key:
        from .models import InterventionLog as IL
        recent = IL.objects.filter(
            user=user,
            trigger_type=trigger_result.trigger_type,
            created_at__gte=timezone.now() - datetime.timedelta(hours=4),
        ).exists()
        if recent:
            logger.debug(
                "Trigger deduped: %s for %s",
                trigger_result.trigger_type, user.email,
            )
            return None

    return intervention_engine.create_intervention(
        user=user,
        level=trigger_result.level,
        trigger_type=trigger_result.trigger_type,
        message=trigger_result.message,
        behavior_key=trigger_result.behavior_key,
        evidence=trigger_result.evidence,
    )


def execute_all_triggers(user):
    """Check and execute all triggers for a user."""
    results = check_triggers(user)
    interventions = []
    for result in results:
        intervention = execute_trigger(user, result)
        if intervention:
            interventions.append(intervention)
    return interventions


# =============================================================================
# INTERNAL HELPERS
# =============================================================================


def _summarize_factors(factors):
    """Summarize drift prediction factors into a readable string."""
    parts = []
    if factors.get('recent_drift_trend', 0) > 0.3:
        parts.append("recent drift trend")
    if factors.get('schedule_density', 0) > 0.5:
        parts.append("dense schedule")
    if factors.get('streak_fatigue', 0) > 0.1:
        parts.append(f"streak fatigue ({factors.get('clean_streak_days', 0)}d)")
    if factors.get('weekend_effect', 0) > 0:
        parts.append("weekend effect")
    return ", ".join(parts) if parts else "multiple factors"
