"""
CalendarCosActions — CoS v2 action contract implementation for the Calendar module.

Wraps CalendarMutationService and conflict detection with the standard
CosActionContract interface, adding enhanced conflict resolution options.
"""

import datetime as dt
import logging
from typing import Dict, List, Optional

from django.utils import timezone as dj_timezone

from apps.calendar_engine.models import CalendarEvent
from apps.calendar_engine.services.calendar_mutation_service import (
    CalendarMutationService,
)
from apps.calendar_engine.services.conflicts import (
    classify_conflict_case,
    detect_all_conflicts,
)
from apps.calendar_engine.services.suggestions import find_gaps_for_day
from apps.cos.contracts import (
    ActionResult,
    ConflictCheck,
    CosActionContract,
    DuplicateCheck,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────
# Conflict Resolution Option Generator
# ──────────────────────────────────────────────────────────


def generate_resolution_options(
    user,
    proposed_start: dt.datetime,
    proposed_end: dt.datetime,
    conflicts: List[Dict],
    conflict_case: str,
) -> List[Dict]:
    """
    Generate conflict resolution options for the user to choose from.

    Options:
    1. shift_15min — Shift the proposed event by 15 minutes
    2. next_available — Move to the next available slot that fits
    3. shorten — Shorten duration to fit before the conflicting event
    4. force_create — Override and double-book (user's choice)

    Args:
        user: The user
        proposed_start: Start time of the proposed event
        proposed_end: End time of the proposed event
        conflicts: List of conflict dicts from detect_all_conflicts
        conflict_case: 'A', 'B', or 'C' from classify_conflict_case

    Returns:
        List of resolution option dicts
    """
    proposed_duration = proposed_end - proposed_start
    duration_minutes = int(proposed_duration.total_seconds() / 60)
    options = []

    # Find the earliest conflicting event
    earliest_conflict_end = None
    for c in conflicts:
        try:
            c_end = dt.datetime.fromisoformat(c["end_dt"])
            if earliest_conflict_end is None or c_end < earliest_conflict_end:
                earliest_conflict_end = c_end
        except (ValueError, KeyError):
            continue

    # ── Option 1: Shift by 15 minutes ────────────────────
    if earliest_conflict_end:
        shifted_start = earliest_conflict_end
        shifted_end = shifted_start + proposed_duration

        # Verify the shifted slot doesn't conflict with anything else
        shifted_conflicts = detect_all_conflicts(
            user, shifted_start, shifted_end,
        )
        if not shifted_conflicts["has_conflict"]:
            # Format friendly time
            options.append({
                "action": "shift_after_conflict",
                "label": f"Move to {_friendly_time(shifted_start)}",
                "description": (
                    f"Start right after the conflicting event ends "
                    f"({_friendly_time(shifted_start)} – {_friendly_time(shifted_end)})"
                ),
                "new_start_dt": shifted_start.isoformat(),
                "new_end_dt": shifted_end.isoformat(),
            })

    # ── Option 2: Next available slot ─────────────────────
    try:
        gaps = find_gaps_for_day(user, date=proposed_start.date())
        for gap in gaps:
            gap_start = gap["start_dt"]
            gap_end = gap["end_dt"]
            # Ensure gap_start is after proposed_start (look forward, not backward)
            if gap_start <= proposed_start:
                # Check if there's room starting from proposed_start
                if gap_end > proposed_start:
                    gap_start = proposed_start
                else:
                    continue

            gap_minutes = gap["duration_minutes"]
            if gap_minutes >= duration_minutes:
                # Found a slot that fits
                slot_start = gap_start
                slot_end = slot_start + proposed_duration
                # Don't duplicate the shift option
                if options and options[0].get("new_start_dt") == slot_start.isoformat():
                    continue
                options.append({
                    "action": "next_available",
                    "label": f"Move to {_friendly_time(slot_start)}",
                    "description": (
                        f"Next open slot: "
                        f"{_friendly_time(slot_start)} – {_friendly_time(slot_end)} "
                        f"({gap_minutes} min available)"
                    ),
                    "new_start_dt": slot_start.isoformat(),
                    "new_end_dt": slot_end.isoformat(),
                })
                break  # Only need the first available slot
    except Exception as e:
        logger.debug("Gap search for next_available failed: %s", e)

    # ── Option 3: Shorten duration ────────────────────────
    # Only offer if there's meaningful time before the conflict starts
    earliest_conflict_start = None
    for c in conflicts:
        try:
            c_start = dt.datetime.fromisoformat(c["start_dt"])
            if earliest_conflict_start is None or c_start < earliest_conflict_start:
                earliest_conflict_start = c_start
        except (ValueError, KeyError):
            continue

    if earliest_conflict_start and earliest_conflict_start > proposed_start:
        shortened_minutes = int(
            (earliest_conflict_start - proposed_start).total_seconds() / 60
        )
        if shortened_minutes >= 15:  # At least 15 min to be useful
            options.append({
                "action": "shorten",
                "label": f"Shorten to {shortened_minutes} min",
                "description": (
                    f"Keep the same start time but end at "
                    f"{_friendly_time(earliest_conflict_start)} "
                    f"({shortened_minutes} min instead of {duration_minutes} min)"
                ),
                "new_start_dt": proposed_start.isoformat(),
                "new_end_dt": earliest_conflict_start.isoformat(),
            })

    # ── Option 4: Force create (double-book) ──────────────
    # For case A (protected conflict), make this the last/least-recommended option
    options.append({
        "action": "force_create",
        "label": "Keep both (double-book)",
        "description": (
            "Create the event anyway, overlapping with the existing one. "
            "You'll have a scheduling conflict."
        ),
        "new_start_dt": proposed_start.isoformat(),
        "new_end_dt": proposed_end.isoformat(),
    })

    return options


def _friendly_time(dt_obj) -> str:
    """Format a datetime as friendly time string (e.g. '2:30 PM')."""
    try:
        return dt_obj.strftime("%-I:%M %p")
    except (ValueError, AttributeError):
        return str(dt_obj)


# ──────────────────────────────────────────────────────────
# CalendarCosActions — Contract Implementation
# ──────────────────────────────────────────────────────────


class CalendarCosActions(CosActionContract):
    """
    CoS v2 action contract for the Calendar module.

    Delegates to CalendarMutationService for actual mutations,
    adding enhanced duplicate checks, conflict resolution options,
    and reflection support on top.
    """

    @property
    def module_name(self) -> str:
        return "calendar"

    def supports_reflections(self) -> bool:
        return True

    def supports_proactive_prompts(self) -> bool:
        return True

    # ── CRUD ──────────────────────────────────────────────

    def create(self, **kwargs) -> ActionResult:
        """
        Create a calendar event via CalendarMutationService.

        If a conflict is detected and force is not True, returns
        requires_decision=True with resolution options.
        """
        svc = CalendarMutationService(self.user)
        result = svc.create(**kwargs)

        if result.requires_decision:
            # Enrich with resolution options
            conflict_details = result.conflict_details or {}
            conflicts = conflict_details.get("conflicts", [])
            proposed = conflict_details.get("proposed_event", {})

            try:
                proposed_start = dt.datetime.fromisoformat(proposed["start_dt"])
                proposed_end = dt.datetime.fromisoformat(proposed["end_dt"])
                case = conflict_details.get("case", "C")

                options = generate_resolution_options(
                    self.user, proposed_start, proposed_end, conflicts, case,
                )
            except (KeyError, ValueError) as e:
                logger.debug("Resolution option generation failed: %s", e)
                options = [{
                    "action": "force_create",
                    "label": "Create anyway",
                    "description": "Create the event despite the conflict.",
                }]

            return ActionResult(
                success=False,
                requires_decision=True,
                decision_options=options,
                error=result.error,
                metadata={
                    "conflict_case": conflict_details.get("case"),
                    "conflicts": conflicts,
                    "proposed_start": proposed.get("start_dt"),
                    "proposed_end": proposed.get("end_dt"),
                },
            )

        if result.success:
            return ActionResult(
                success=True,
                entity=result.event,
                entity_id=result.event.pk if result.event else None,
                reused=result.reused,
                metadata={
                    "conflict_warning": result.conflict_warning,
                    "pressure_note": result.pressure_note,
                },
            )

        return ActionResult(
            success=False,
            error=result.error,
        )

    def update(self, entity_id: int, **kwargs) -> ActionResult:
        """Update a calendar event via CalendarMutationService."""
        svc = CalendarMutationService(self.user)
        result = svc.update(event_id=entity_id, **kwargs)

        if result.requires_decision:
            return ActionResult(
                success=False,
                requires_decision=True,
                error=result.error,
                metadata={
                    "conflict_details": result.conflict_details,
                },
            )

        if result.success:
            return ActionResult(
                success=True,
                entity=result.event,
                entity_id=result.event.pk if result.event else None,
                metadata={"fields_changed": result.fields_changed},
            )

        return ActionResult(success=False, error=result.error)

    def delete(self, entity_id: int, **kwargs) -> ActionResult:
        """Soft-delete a calendar event via CalendarMutationService."""
        svc = CalendarMutationService(self.user)
        result = svc.delete(event_id=entity_id)

        if result.success:
            return ActionResult(
                success=True,
                entity=result.event,
                entity_id=result.event.pk if result.event else None,
                metadata={"fields_changed": result.fields_changed},
            )

        return ActionResult(success=False, error=result.error)

    def retrieve(self, entity_id: int) -> ActionResult:
        """Retrieve a calendar event by ID."""
        try:
            event = CalendarEvent.objects.get(
                pk=entity_id,
                user=self.user,
                deleted_at__isnull=True,
            )
            return ActionResult(
                success=True,
                entity=event,
                entity_id=event.pk,
            )
        except CalendarEvent.DoesNotExist:
            return ActionResult(
                success=False,
                error=f"Calendar event {entity_id} not found.",
            )

    def summarise(self, **kwargs) -> ActionResult:
        """
        Summarise calendar events for a date range.

        kwargs:
            date: specific date (default: today)
            start_date / end_date: date range
            limit: max events to return (default: 20)
        """
        target_date = kwargs.get("date")
        start_date = kwargs.get("start_date")
        end_date = kwargs.get("end_date")
        limit = kwargs.get("limit", 20)

        if target_date:
            start_date = target_date
            end_date = target_date

        if not start_date:
            start_date = dj_timezone.localdate()
        if not end_date:
            end_date = start_date

        # Build datetime range
        try:
            from zoneinfo import ZoneInfo
            tz_name = self.user.preferences.timezone_iana
            tz = ZoneInfo(tz_name) if tz_name else dj_timezone.get_current_timezone()
        except (AttributeError, Exception):
            tz = dj_timezone.get_current_timezone()

        range_start = dj_timezone.make_aware(
            dt.datetime.combine(start_date, dt.time.min), tz
        )
        range_end = dj_timezone.make_aware(
            dt.datetime.combine(end_date, dt.time.max), tz
        )

        events = (
            CalendarEvent.objects.filter(
                user=self.user,
                status=CalendarEvent.STATUS_SCHEDULED,
                start_dt__lt=range_end,
                end_dt__gt=range_start,
                deleted_at__isnull=True,
            )
            .order_by("start_dt")[:limit]
        )

        summary = []
        for e in events:
            local_start = e.start_dt.astimezone(tz)
            local_end = e.end_dt.astimezone(tz)
            summary.append({
                "id": e.pk,
                "title": e.title,
                "start": local_start.strftime("%-I:%M %p"),
                "end": local_end.strftime("%-I:%M %p"),
                "is_protected": e.is_protected,
                "domain": e.domain.name if e.domain else None,
                "duration_minutes": e.duration_minutes,
            })

        return ActionResult(
            success=True,
            metadata={
                "event_count": len(summary),
                "date_range": f"{start_date} to {end_date}",
                "events": summary,
            },
        )

    # ── Safety Checks ─────────────────────────────────────

    def check_duplicate(self, **kwargs) -> DuplicateCheck:
        """
        Check for calendar event duplicates (idempotency + semantic + recurrence).

        kwargs: title, start_dt, end_dt (same as create)
        """
        title = kwargs.get("title", "")
        start_dt = kwargs.get("start_dt")

        if not title or not start_dt:
            return DuplicateCheck(is_duplicate=False)

        # Semantic dup check
        semantic_dup = (
            CalendarEvent.objects.filter(
                user=self.user,
                title__iexact=title.strip(),
                start_dt=start_dt,
                deleted_at__isnull=True,
            )
            .exclude(status=CalendarEvent.STATUS_CANCELED)
            .first()
        )
        if semantic_dup:
            return DuplicateCheck(
                is_duplicate=True,
                existing_entity=semantic_dup,
                existing_entity_id=semantic_dup.pk,
                match_type="semantic",
                message=(
                    f"An event '{semantic_dup.title}' already exists at that time."
                ),
            )

        # Recurrence dup check
        svc = CalendarMutationService(self.user)
        recurrence_dup = svc._check_recurrence_duplicate(title, start_dt)
        if recurrence_dup:
            return DuplicateCheck(
                is_duplicate=True,
                existing_entity=recurrence_dup,
                existing_entity_id=recurrence_dup.pk,
                match_type="recurrence",
                message=(
                    f"A recurring event '{recurrence_dup.title}' already "
                    f"covers that time slot."
                ),
            )

        return DuplicateCheck(is_duplicate=False)

    def check_conflicts(self, **kwargs) -> ConflictCheck:
        """
        Check for scheduling conflicts with enhanced resolution options.

        kwargs: start_dt, end_dt, is_protected (optional), exclude_event_id (optional)
        """
        start_dt = kwargs.get("start_dt")
        end_dt = kwargs.get("end_dt")
        is_protected = kwargs.get("is_protected", False)
        exclude_event_id = kwargs.get("exclude_event_id")

        if not start_dt or not end_dt:
            return ConflictCheck(has_conflict=False)

        result = detect_all_conflicts(
            self.user, start_dt, end_dt,
            exclude_event_id=exclude_event_id,
        )

        if not result["has_conflict"]:
            return ConflictCheck(has_conflict=False)

        case = classify_conflict_case(result["conflicts"], is_protected)

        # Generate resolution options
        options = generate_resolution_options(
            self.user, start_dt, end_dt, result["conflicts"], case,
        )

        return ConflictCheck(
            has_conflict=True,
            conflicts=result["conflicts"],
            suggested_resolutions=options,
            message=f"Conflict case {case}: {len(result['conflicts'])} overlapping event(s)",
        )

    # ── Reflection hooks ──────────────────────────────────

    def capture_reflection_hook(
        self, entity_id: int, reflection_text: str, **kwargs
    ) -> bool:
        """Store a reflection note against a calendar event."""
        from django.contrib.contenttypes.models import ContentType
        from apps.cos.models import CosReflection

        try:
            event = CalendarEvent.objects.get(pk=entity_id, user=self.user)
            ct = ContentType.objects.get_for_model(CalendarEvent)

            CosReflection.objects.create(
                user=self.user,
                content_type=ct,
                object_id=event.pk,
                text=reflection_text,
                activity_date=event.start_dt.date(),
                activity_type=kwargs.get("activity_type", "calendar_event"),
                sentiment=kwargs.get("sentiment", ""),
                prompt_text=kwargs.get("prompt_text", ""),
            )
            return True
        except (CalendarEvent.DoesNotExist, Exception) as e:
            logger.error("Reflection capture failed for event %s: %s", entity_id, e)
            return False
