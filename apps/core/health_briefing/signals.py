"""
Event-triggered HealthBriefing recompute (Phase 1A · C12).

post_save handlers on four metabolic-input models dispatch the
per-user recompute task. All dispatches are async (`.delay()`) — the
ingestion save is never blocked.

Models that trigger recompute:

* GlucoseEntry  — new CGM reading
* IntakeLog     — insulin dose (filtered via the user, not the row)
* WeightEntry   — weight measurement
* LabResult     — lab value lands (HbA1c, fasting glucose, etc.)

Recompute boundedness (per Wave 3 guardrail):

* `.delay()` only — no synchronous composer invocation from a signal.
* HealthBriefingSnapshot has zero signal handlers (verified C4) —
  recomputes are terminal; no cascade.
* The composer reads SAE state read-only; it never writes to any
  domain model that could re-trigger this handler.
* No deduplication / debounce yet — multiple rapid saves enqueue
  multiple tasks, each of which produces an identical briefing_id if
  the SAE evidence is unchanged (collapses via snapshot's
  update_or_create). For Phase 1B we can add a per-user debounce
  lock if the metric warrants it.

This module is imported by `apps/core/apps.py:ready()` at Django boot.
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver


logger = logging.getLogger(__name__)


def _dispatch_recompute(user_id: int, source: str) -> None:
    """Enqueue a per-user recompute task. Tolerant of Celery being
    unavailable in dev/tests — logs a warning and returns instead of
    raising."""
    from apps.core.health_briefing.tasks import (
        recompute_health_briefing_for_user_task,
    )

    try:
        recompute_health_briefing_for_user_task.delay(user_id)
    except Exception:
        logger.warning(
            "[HEALTH_BRIEFING] dispatch failed user_id=%s source=%s — "
            "skipping (next beat tick will recompute)",
            user_id, source, exc_info=False,
        )


@receiver(post_save, sender="health.GlucoseEntry")
def on_glucose_entry_save(sender, instance, **kwargs):
    _dispatch_recompute(instance.user_id, "GlucoseEntry")


@receiver(post_save, sender="health.IntakeLog")
def on_intake_log_save(sender, instance, **kwargs):
    _dispatch_recompute(instance.user_id, "IntakeLog")


@receiver(post_save, sender="health.WeightEntry")
def on_weight_entry_save(sender, instance, **kwargs):
    _dispatch_recompute(instance.user_id, "WeightEntry")


@receiver(post_save, sender="medical.LabResult")
def on_lab_result_save(sender, instance, **kwargs):
    _dispatch_recompute(instance.user_id, "LabResult")
