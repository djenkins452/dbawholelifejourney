"""
Whole Life Journey — Automatic Recovery Architecture

Project: Whole Life Journey
Path: apps/core/blueprint/recovery_engine.py
Purpose: Automatically adjust tomorrow's plan when Tier-1 override occurs

Description:
    When a user proceeds through a friction gate (overrides a Tier-1 protected
    behavior), this engine automatically:

    1. Re-adjusts tomorrow's capacity allocation
    2. Protects remaining Tier-1 items (locks them)
    3. Shifts Tier-3 items to create buffer
    4. Recomputes drift prediction
    5. Creates a recovery intervention with the adjusted plan

    This ensures that a single slip doesn't cascade into a full day of drift.

Public API:
    - apply_recovery_adjustment(user, overridden_behavior_key) -> dict
    - get_recovery_status(user) -> dict

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import datetime
import logging

from django.utils import timezone

logger = logging.getLogger(__name__)


# =============================================================================
# PUBLIC API
# =============================================================================


def apply_recovery_adjustment(user, overridden_behavior_key):
    """
    Apply automatic recovery after a Tier-1 override.

    Steps:
        1. Get tomorrow's plan (or today's remaining)
        2. Lock all remaining Tier-1 blocks
        3. Shift Tier-3 items by extending their windows / deferring
        4. Recompute drift prediction
        5. Create a recovery nudge

    Args:
        user: Django User instance.
        overridden_behavior_key: The behavior key that was overridden.

    Returns:
        dict with recovery details.
    """
    from .models import ArchitecturePlan, ScheduledBlock, InterventionLog
    from . import engine as blueprint_engine
    from . import drift_engine
    from .intervention_engine import create_intervention

    result = {
        'recovery_applied': False,
        'tier1_locked': 0,
        'tier3_deferred': 0,
        'drift_updated': False,
        'intervention_created': False,
    }

    try:
        # Get tomorrow's plan
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        plan = ArchitecturePlan.get_active_for_date(user, tomorrow)

        if not plan:
            # Try today's plan for same-day recovery
            today = timezone.localdate()
            plan = ArchitecturePlan.get_active_for_date(user, today)

        if not plan:
            logger.info(
                "Recovery: No plan to adjust for %s after override of %s",
                user.email, overridden_behavior_key,
            )
            return result

        # Step 1: Lock all remaining Tier-1 blocks
        tier1_blocks = plan.blocks.filter(
            tier=1, is_completed=False, is_locked=False,
        )
        locked_count = tier1_blocks.update(is_locked=True)
        result['tier1_locked'] = locked_count

        # Step 2: Identify Tier-3 blocks that can be deferred
        tier3_blocks = plan.blocks.filter(
            tier__gte=3, is_completed=False, is_locked=False,
        ).order_by('-tier', '-start_time')  # Lowest priority first

        deferred = 0
        for block in tier3_blocks[:3]:  # Defer up to 3 low-priority blocks
            block.rationale = (
                f"Deferred by recovery engine after {overridden_behavior_key} override. "
                f"Original: {block.start_time.strftime('%H:%M') if block.start_time else '?'}"
            )
            # Push later by 1 hour to create buffer
            if block.start_time and block.end_time:
                start_dt = datetime.datetime.combine(
                    plan.date, block.start_time,
                )
                end_dt = datetime.datetime.combine(
                    plan.date, block.end_time,
                )
                new_start = (start_dt + datetime.timedelta(hours=1)).time()
                new_end = (end_dt + datetime.timedelta(hours=1)).time()
                # Only shift if it doesn't overflow past midnight
                if new_start > block.start_time:
                    block.start_time = new_start
                    block.end_time = new_end
            block.save()
            deferred += 1

        result['tier3_deferred'] = deferred

        # Step 3: Update risk warnings on the plan
        warnings = plan.risk_warnings or []
        warnings.append(
            f"Recovery mode: {overridden_behavior_key.replace('_', ' ')} "
            f"was overridden. Tier-1 locked, Tier-3 deferred."
        )
        plan.risk_warnings = warnings
        plan.save(update_fields=['risk_warnings', 'updated_at'])

        result['recovery_applied'] = True

        # Step 4: Recompute drift prediction
        try:
            drift_engine.predict_drift_probability(user)
            result['drift_updated'] = True
        except Exception as e:
            logger.debug("Recovery: drift update failed: %s", e)

        # Step 5: Create recovery intervention
        try:
            msg = (
                f"Recovery plan activated after {overridden_behavior_key.replace('_', ' ')} override. "
                f"{locked_count} Tier-1 blocks locked. "
                f"{deferred} lower-priority items deferred to create buffer."
            )
            create_intervention(
                user=user,
                level=InterventionLog.LEVEL_NUDGE,
                trigger_type='recovery_activated',
                message=msg,
                behavior_key=overridden_behavior_key,
                evidence={
                    'overridden_behavior': overridden_behavior_key,
                    'tier1_locked': locked_count,
                    'tier3_deferred': deferred,
                },
                delivered_via='in_app',
            )
            result['intervention_created'] = True
        except Exception as e:
            logger.debug("Recovery: intervention creation failed: %s", e)

        logger.info(
            "Recovery applied for %s: locked=%d, deferred=%d, behavior=%s",
            user.email, locked_count, deferred, overridden_behavior_key,
        )

    except Exception as e:
        logger.error("Recovery engine failed for %s: %s", user.email, e)

    return result


def get_recovery_status(user):
    """
    Check if the user's current plan is in recovery mode.

    Returns:
        dict with recovery state information.
    """
    from .models import ArchitecturePlan

    status = {
        'in_recovery': False,
        'recovery_warnings': [],
        'locked_tier1_count': 0,
    }

    try:
        today = timezone.localdate()
        plan = ArchitecturePlan.get_active_for_date(user, today)

        if not plan:
            return status

        warnings = plan.risk_warnings or []
        recovery_warnings = [w for w in warnings if 'recovery' in w.lower()]

        if recovery_warnings:
            status['in_recovery'] = True
            status['recovery_warnings'] = recovery_warnings

        locked = plan.blocks.filter(tier=1, is_locked=True, is_completed=False).count()
        status['locked_tier1_count'] = locked

    except Exception:
        pass

    return status
