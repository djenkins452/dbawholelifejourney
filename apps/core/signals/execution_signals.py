"""
Execution Quality Signal Handlers.

Hooks into post_save signals for completion models to generate
ExecutionSignal records. This is a read-only analytical layer —
it does NOT affect completion logic, CoS, Today Engine, or UI.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='life.RoutineLog')
def record_execution_signal_on_routine_log(sender, instance, **kwargs):
    """Generate ExecutionSignal when a RoutineLog is saved with completion."""
    if not instance.completed_at and not instance.performed_at:
        return
    if instance.log_status not in ("completed", "completed_late"):
        return
    try:
        from apps.core.signals.execution_quality import record_signal_from_routine_log
        record_signal_from_routine_log(instance)
    except Exception:
        logger.warning(
            "Execution signal generation failed for RoutineLog %s",
            instance.pk, exc_info=True,
        )


@receiver(post_save, sender='health.WorkoutSession')
def record_execution_signal_on_workout(sender, instance, **kwargs):
    """Generate ExecutionSignal when a WorkoutSession is completed."""
    if not instance.completed_at:
        return
    try:
        from apps.core.signals.execution_quality import record_signal_from_workout_session
        record_signal_from_workout_session(instance)
    except Exception:
        logger.warning(
            "Execution signal generation failed for WorkoutSession %s",
            instance.pk, exc_info=True,
        )


@receiver(post_save, sender='journal.JournalEntry')
def record_execution_signal_on_journal(sender, instance, created, **kwargs):
    """Generate ExecutionSignal when a JournalEntry is created."""
    if not created:
        return
    try:
        from apps.core.signals.execution_quality import record_signal_from_journal_entry
        record_signal_from_journal_entry(instance)
    except Exception:
        logger.warning(
            "Execution signal generation failed for JournalEntry %s",
            instance.pk, exc_info=True,
        )


@receiver(post_save, sender='health.MedicineLog')
def record_execution_signal_on_medicine_log(sender, instance, **kwargs):
    """Generate ExecutionSignal when a MedicineLog is saved with taken_at."""
    if not instance.taken_at:
        return
    if instance.log_status not in ("taken", "late"):
        return
    try:
        from apps.core.signals.execution_quality import record_signal_from_medicine_log
        record_signal_from_medicine_log(instance)
    except Exception:
        logger.warning(
            "Execution signal generation failed for MedicineLog %s",
            instance.pk, exc_info=True,
        )
