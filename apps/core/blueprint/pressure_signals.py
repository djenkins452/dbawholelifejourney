"""
Phase 4 — Pressure Snapshot Event-Driven Triggers.

Listens for model saves on:
- Commitment (save/close/renegotiate)
- ScheduledBlock (create/update/delete)
- ArchitecturePlan (create/update)
- Tier1OverrideEvent (create)
- LifeGoal progress updates

Calls update_pressure_snapshot(user) on each trigger.
Idempotent — safe to fire multiple times.
Non-blocking — failures are logged, never raised.

Project: Whole Life Journey
Path: apps/core/blueprint/pressure_signals.py
"""

import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _trigger_pressure_recompute(user):
    """
    Trigger an asynchronous-safe pressure recompute for a user.

    Non-blocking: catches all exceptions and logs them.
    """
    try:
        from apps.core.blueprint.pressure_engine import update_pressure_snapshot
        update_pressure_snapshot(user)
    except Exception as e:
        logger.debug(
            "Phase 4: Pressure recompute skipped for user %s: %s",
            getattr(user, 'pk', '?'), e,
        )


@receiver(post_save, sender='core.Commitment')
def on_commitment_save(sender, instance, **kwargs):
    """Recompute pressure when commitment is created or updated."""
    _trigger_pressure_recompute(instance.user)


@receiver(post_save, sender='core.CommitmentRenegotiation')
def on_commitment_renegotiation(sender, instance, **kwargs):
    """Recompute pressure when commitment is renegotiated."""
    _trigger_pressure_recompute(instance.commitment.user)


@receiver(post_save, sender='core.ScheduledBlock')
def on_scheduled_block_save(sender, instance, **kwargs):
    """Recompute pressure when a calendar block is created or updated."""
    try:
        user = instance.plan.user
        _trigger_pressure_recompute(user)
    except Exception:
        pass


@receiver(post_delete, sender='core.ScheduledBlock')
def on_scheduled_block_delete(sender, instance, **kwargs):
    """Recompute pressure when a calendar block is deleted."""
    try:
        user = instance.plan.user
        _trigger_pressure_recompute(user)
    except Exception:
        pass


@receiver(post_save, sender='core.ArchitecturePlan')
def on_architecture_plan_save(sender, instance, **kwargs):
    """Recompute pressure when a plan is created or updated."""
    _trigger_pressure_recompute(instance.user)


@receiver(post_save, sender='core.Tier1OverrideEvent')
def on_tier1_override(sender, instance, **kwargs):
    """Recompute pressure on Tier 1 override event."""
    _trigger_pressure_recompute(instance.user)


# Goal progress updates — use string reference to avoid circular imports
@receiver(post_save, sender='purpose.LifeGoal')
def on_goal_update(sender, instance, **kwargs):
    """Recompute pressure when a goal is updated."""
    _trigger_pressure_recompute(instance.user)


@receiver(post_save, sender='purpose.GoalMilestone')
def on_milestone_update(sender, instance, **kwargs):
    """Recompute pressure when a goal milestone is completed."""
    try:
        _trigger_pressure_recompute(instance.goal.user)
    except Exception:
        pass
