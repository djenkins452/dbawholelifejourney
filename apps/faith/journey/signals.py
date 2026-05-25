"""
Journey signals — internal observability only.

Six events fire to the existing WLJ domain events bus (`safe_emit_event`):

    journey.started               — UserJourney created (active)
    journey.day.completed         — UserJourneyDayProgress.is_completed flipped True
    journey.arc.completed         — Last day in current arc just completed
    journey.application.committed — UserJourneyDayProgress.application_committed
    journey.confusion.flagged     — User tapped a confusion topic
    journey.resumed               — User returned after a ≥3-day gap

NO PGE / PRIE / coaching nudges. NO Beth surfacing. NO user-facing momentum
language. These signals exist for:
    - PIE insight rules (internal observability)
    - Faith rhythm understanding
    - Editorial feedback (which confusion topics get tapped)
    - Future personalization

Re-firing protection:
    - day.completed fires only when is_completed transitions False → True
      (uses pre_save hook to compare old vs new state)
    - application.committed fires only on transition False → True
    - arc.completed only fires once per arc completion (driven by the
      mark_day_complete service, not a model signal)
    - resumed is fired by the view layer (journey_today) — not a model signal
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.faith.journey.models import UserJourney, UserJourneyDayProgress


logger = logging.getLogger(__name__)


# Event names — kept as module constants. Not added to apps.core.events.EventTypes
# to avoid touching shared infra during parallel Health Intelligence work.
EVENT_JOURNEY_STARTED = "journey.started"
EVENT_JOURNEY_DAY_COMPLETED = "journey.day.completed"
EVENT_JOURNEY_ARC_COMPLETED = "journey.arc.completed"
EVENT_JOURNEY_APPLICATION_COMMITTED = "journey.application.committed"
EVENT_JOURNEY_CONFUSION_FLAGGED = "journey.confusion.flagged"
EVENT_JOURNEY_RESUMED = "journey.resumed"


def _safe_emit(event_type: str, user, data: dict | None = None) -> None:
    """Wrapper around safe_emit_event that never raises into the caller."""
    try:
        from apps.core.events.domain_events import safe_emit_event
        safe_emit_event(event_type, user=user, data=data or {}, source="apps.faith.journey")
    except Exception as e:
        logger.warning("Journey signal: emission of %s failed: %s", event_type, e, exc_info=True)


# ---------------------------------------------------------------------------
# UserJourney.post_save — fire journey.started on first creation
# ---------------------------------------------------------------------------

@receiver(post_save, sender=UserJourney, dispatch_uid="journey.user_journey.started")
def _on_user_journey_created(sender, instance: UserJourney, created: bool, **kwargs):
    if not created:
        return
    if instance.journey_status != "active":
        return
    _safe_emit(EVENT_JOURNEY_STARTED, instance.user, {
        "journey_path_slug": instance.journey_path.slug,
        "user_journey_id": instance.pk,
    })


# ---------------------------------------------------------------------------
# UserJourneyDayProgress — fire day.completed and application.committed only
# on transition (not on every save).
# ---------------------------------------------------------------------------

@receiver(pre_save, sender=UserJourneyDayProgress, dispatch_uid="journey.progress.pre_save")
def _stash_previous_progress_state(sender, instance: UserJourneyDayProgress, **kwargs):
    """Stash prior is_completed / application_committed values on the instance.

    Read in post_save to detect True transitions and avoid duplicate emission.
    """
    if instance.pk is None:
        instance._prev_is_completed = False
        instance._prev_application_committed = False
        return
    try:
        prev = UserJourneyDayProgress.all_objects.get(pk=instance.pk)
    except UserJourneyDayProgress.DoesNotExist:
        instance._prev_is_completed = False
        instance._prev_application_committed = False
        return
    instance._prev_is_completed = prev.is_completed
    instance._prev_application_committed = prev.application_committed


@receiver(post_save, sender=UserJourneyDayProgress, dispatch_uid="journey.progress.post_save")
def _on_progress_saved(sender, instance: UserJourneyDayProgress, created: bool, **kwargs):
    prev_completed = getattr(instance, "_prev_is_completed", False)
    prev_committed = getattr(instance, "_prev_application_committed", False)

    if instance.is_completed and not prev_completed:
        _safe_emit(EVENT_JOURNEY_DAY_COMPLETED, instance.user, {
            "user_journey_id": instance.user_journey_id,
            "journey_day_id": instance.journey_day_id,
            "arc_slug": instance.journey_day.arc.slug,
            "day_number": instance.journey_day.day_number,
            "difficulty_at_completion": instance.difficulty_at_completion,
        })

    if instance.application_committed and not prev_committed:
        _safe_emit(EVENT_JOURNEY_APPLICATION_COMMITTED, instance.user, {
            "user_journey_id": instance.user_journey_id,
            "journey_day_id": instance.journey_day_id,
            "arc_slug": instance.journey_day.arc.slug,
            "day_number": instance.journey_day.day_number,
        })


# ---------------------------------------------------------------------------
# Service-layer emitters — called by views/services for events not tied to
# a single model save.
# ---------------------------------------------------------------------------

def emit_arc_completed(user, *, user_journey, arc) -> None:
    """Called by mark_day_complete when an arc's final day is completed."""
    _safe_emit(EVENT_JOURNEY_ARC_COMPLETED, user, {
        "user_journey_id": user_journey.pk,
        "arc_slug": arc.slug,
        "arc_name": arc.name,
        "days_in_arc": arc.estimated_days,
    })


def emit_confusion_flagged(user, *, user_journey, arc_slug: str, day_number: int, topic: str) -> None:
    """Called by the confusion_flagged view endpoint when a user taps a topic."""
    _safe_emit(EVENT_JOURNEY_CONFUSION_FLAGGED, user, {
        "user_journey_id": user_journey.pk if user_journey else None,
        "arc_slug": arc_slug,
        "day_number": day_number,
        "topic": topic,
    })


def emit_resumed(user, *, user_journey, days_since_last_visit: int) -> None:
    """Called by the journey_today view when user returns after a ≥3-day gap."""
    _safe_emit(EVENT_JOURNEY_RESUMED, user, {
        "user_journey_id": user_journey.pk,
        "days_since_last_visit": days_since_last_visit,
    })
