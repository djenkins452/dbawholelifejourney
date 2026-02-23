"""
Phase 5 — Protective Action Engine: Event-Driven Triggers.

Listens for model saves on:
- PressureSnapshot (recompute recommendations + overload triggers)
- DeadlineSnapshot (reschedule alerts if needed)
- Commitment (reschedule alerts on renegotiation/closure)
- Tier1OverrideEvent (recompute recommendations)

Non-blocking — failures are logged, never raised.

Project: Whole Life Journey
Path: apps/core/blueprint/protective_signals.py
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _trigger_protective_recompute(user):
    """
    Trigger protective recommendation recompute for a user.

    Non-blocking: catches all exceptions and logs them.
    """
    try:
        from apps.core.blueprint.protective_engine import (
            compute_protective_recommendations,
            expire_superseded_recommendations,
            schedule_deadline_alerts,
        )
        expire_superseded_recommendations(user)
        compute_protective_recommendations(user)
        schedule_deadline_alerts(user)
    except Exception as e:
        logger.debug(
            "Phase 5: Protective recompute skipped for user %s: %s",
            getattr(user, 'pk', '?'), e,
        )


def _trigger_overload_check(user, pressure_snapshot):
    """
    Check overload triggers when a new pressure snapshot is created.

    Non-blocking: catches all exceptions.
    """
    try:
        from apps.core.blueprint.protective_engine import apply_overload_triggers
        apply_overload_triggers(user, pressure_snapshot)
    except Exception as e:
        logger.debug(
            "Phase 5: Overload check skipped for user %s: %s",
            getattr(user, 'pk', '?'), e,
        )


@receiver(post_save, sender='core.PressureSnapshot')
def on_pressure_snapshot_created(sender, instance, created, **kwargs):
    """Recompute protective recommendations when new pressure snapshot arrives."""
    if not created:
        return
    _trigger_protective_recompute(instance.user)
    _trigger_overload_check(instance.user, instance)


@receiver(post_save, sender='core.DeadlineSnapshot')
def on_deadline_snapshot_updated(sender, instance, **kwargs):
    """Reschedule alerts when deadline snapshot updates."""
    try:
        from apps.core.blueprint.protective_engine import schedule_deadline_alerts
        schedule_deadline_alerts(instance.user)
    except Exception as e:
        logger.debug(
            "Phase 5: Deadline alert reschedule skipped for user %s: %s",
            getattr(instance, 'user_id', '?'), e,
        )


@receiver(post_save, sender='core.Commitment')
def on_commitment_change_protective(sender, instance, **kwargs):
    """
    When commitment changes (created/renegotiated/closed),
    cancel old alerts and reschedule new ones.
    """
    try:
        from apps.core.blueprint.protective_engine import (
            cancel_alerts_for_object,
            schedule_deadline_alerts,
        )
        # Cancel existing alerts for this commitment and reschedule
        cancel_alerts_for_object(
            instance.user, 'Commitment', instance.id,
            reason='commitment_changed',
        )
        schedule_deadline_alerts(instance.user)
    except Exception as e:
        logger.debug(
            "Phase 5: Commitment alert reschedule skipped: %s", e,
        )


@receiver(post_save, sender='core.CommitmentRenegotiation')
def on_commitment_renegotiation_protective(sender, instance, **kwargs):
    """
    When commitment is renegotiated, cancel old alerts and schedule new set.
    """
    try:
        from apps.core.blueprint.protective_engine import (
            cancel_alerts_for_object,
            schedule_deadline_alerts,
        )
        commitment = instance.commitment
        cancel_alerts_for_object(
            commitment.user, 'Commitment', commitment.id,
            reason='renegotiated',
        )
        schedule_deadline_alerts(commitment.user)
    except Exception as e:
        logger.debug(
            "Phase 5: Renegotiation alert reschedule skipped: %s", e,
        )


@receiver(post_save, sender='core.Tier1OverrideEvent')
def on_tier1_override_protective(sender, instance, **kwargs):
    """Recompute recommendations on Tier 1 override."""
    _trigger_protective_recompute(instance.user)
