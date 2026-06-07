# ==============================================================================
# File: apps/core/ai_events/adapters/body_composition.py
# Project: Whole Life Journey
# Description: Body composition adapter — deterministic event-level truth
#              for body measurements (waist, chest, arms, thighs, etc.).
# Created: 2026-06-07
# ==============================================================================
"""Body Composition Event Adapter.

Bridges the EventResolver contract used by Beth's ``query_event_history``
intent to canonical body composition truth. The adapter never returns
LLM-derived facts — every value comes from ``BodyCompositionEntry`` rows
or the deterministic snapshot at
``apps.health.services.body_composition_snapshot``.

Triggers (in Beth):
    measurements, body composition, waist, chest, arms, legs, body fat,
    "compare to last time", "what changed?", "how much did my waist change?"

Routes to the snapshot's ``render_comparison_message`` for the headline
"latest vs previous" answer, or returns per-metric EventRecords for
date-range / lookup queries.
"""

import logging
from datetime import date, timedelta

from apps.core.ai_events.event_record import EventRecord

logger = logging.getLogger(__name__)

MAX_LOOKBACK_DAYS = 365  # body measurements are lower-frequency than vitals


def _enforce_bounds(start, end):
    if (end - start).days > MAX_LOOKBACK_DAYS:
        raise ValueError(
            f"Body composition adapter lookback capped at "
            f"{MAX_LOOKBACK_DAYS} days; got {(end - start).days}"
        )


def get_events(user, start_date, end_date):
    """Return per-row EventRecords within ``[start_date, end_date]``."""
    _enforce_bounds(start_date, end_date)
    from apps.health.models import BodyCompositionEntry
    entries = (
        BodyCompositionEntry.objects.filter(
            user=user,
            measurement_date__gte=start_date,
            measurement_date__lte=end_date,
        )
        .select_related()
        .order_by("measurement_date", "metric_name")
    )
    return [_to_event(e) for e in entries]


def get_latest(user, count=1):
    """Return the most recent body composition entries (newest first).

    ``count`` here is the number of distinct ENTRIES, not metrics. Beth's
    lookup intent uses count=1 for "what's my latest?" which is too coarse
    when the user logged 8 metrics today — the adapter promotes count to
    span the entire most-recent session in that case so the user sees
    the full batch.
    """
    from apps.health.models import BodyCompositionEntry
    qs = BodyCompositionEntry.objects.filter(user=user).order_by(
        "-measurement_date", "-created_at",
    )
    if not qs.exists():
        return []
    latest_date = qs.first().measurement_date
    # When a single date holds many metrics (a full scan / measurement
    # session), surface the entire batch so the user can scan the whole
    # session in one answer — never just one metric in isolation.
    batch_entries = list(
        qs.filter(measurement_date=latest_date)[:50]
    )
    if len(batch_entries) >= count:
        return [_to_event(e) for e in batch_entries]
    # Top up with older entries up to requested count.
    older = list(
        qs.exclude(measurement_date=latest_date)[: count - len(batch_entries)]
    )
    return [_to_event(e) for e in batch_entries + older]


def get_day_events(user, target_date):
    return get_events(user, target_date, target_date)


def get_comparison_message(user) -> str:
    """Deterministic 'compare to last time' headline answer.

    Consumed by Beth's body-composition handler. Returns the rendered
    string directly; no LLM narration is allowed to layer on top.
    """
    from apps.health.services.body_composition_snapshot import (
        build_body_composition_snapshot,
        render_comparison_message,
    )
    snapshot = build_body_composition_snapshot(user)
    return render_comparison_message(snapshot)


def get_latest_message(user) -> str:
    """Deterministic 'what are my latest measurements?' answer."""
    from apps.health.services.body_composition_snapshot import (
        build_body_composition_snapshot,
        render_latest_message,
    )
    snapshot = build_body_composition_snapshot(user)
    return render_latest_message(snapshot)


def _to_event(entry):
    """Map a BodyCompositionEntry to an EventRecord."""
    from apps.health.services.body_composition_snapshot import METRIC_LABELS
    metric_label = METRIC_LABELS.get(entry.metric_name, entry.metric_name)
    unit_str = f" {entry.unit}" if entry.unit else ""
    label = f"{metric_label}: {entry.value}{unit_str}"
    # Use start-of-day timestamp; measurement_date is a date, not a datetime.
    from datetime import datetime, time as dt_time
    timestamp = datetime.combine(entry.measurement_date, dt_time.min)
    return EventRecord(
        domain="body_composition",
        event_type="body_measurement_logged",
        timestamp=timestamp,
        label=label,
        status="logged",
        detail={
            "metric": entry.metric_name,
            "metric_label": metric_label,
            "value": float(entry.value),
            "unit": entry.unit,
            "date": str(entry.measurement_date),
            "source": entry.source,
        },
        source_model="BodyCompositionEntry",
        source_id=entry.pk,
    )
