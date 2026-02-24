"""
CosAutoShiftService — Priority + Time-of-Day Auto-Shifting for CoS v2.

Manages intelligent event rescheduling with human-realism constraints:
- Activity-type-aware time suitability (no late-night workouts)
- Priority-based gates (auto-shift low, ask for medium/high)
- Protected event respect (never auto-shift protected events)
- Conflict-aware shifting (finds next suitable slot)
- Full audit trail via CosAutoShiftLog

Priority determination:
- Protected events → high priority (never auto-shifted)
- Activity type defaults: workout=medium, meeting=high, prayer=low, etc.
- Explicit override via caller

Time-of-day suitability per activity type:
- workout: 5:00-21:00 (no late-night)
- prayer/devotional: 5:00-22:00 (early morning OK)
- meeting: 8:00-20:00 (business hours-ish)
- bible_study: 5:00-22:00
- therapy: 8:00-18:00 (daytime only)
- default: 6:00-22:00
"""

import datetime as dt
import logging
from typing import Dict, List, Optional, Tuple

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone as dj_timezone

from apps.cos.models import CosAutoShiftLog
from apps.cos.services.prompt_templates import detect_activity_type

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────
# Time-of-Day Suitability Rules
# ──────────────────────────────────────────────────────────

# (earliest_hour, latest_hour) — events should START within this window
TIME_SUITABILITY = {
    "workout": (5, 21),
    "meeting": (8, 20),
    "prayer": (5, 22),
    "devotional": (5, 22),
    "bible_study": (5, 22),
    "therapy": (8, 18),
    "journaling": (5, 23),
    "meditation": (5, 22),
    "fasting": (5, 22),
    "appointment": (7, 19),
    "default": (6, 22),
}

# Default priority per activity type
ACTIVITY_PRIORITY = {
    "meeting": "high",
    "appointment": "high",
    "therapy": "high",
    "workout": "medium",
    "bible_study": "medium",
    "prayer": "low",
    "devotional": "low",
    "journaling": "low",
    "meditation": "low",
    "fasting": "low",
    "default": "medium",
}

# Only auto-shift these priority levels without asking
AUTO_SHIFT_PRIORITIES = {"low"}

# Minimum gap between events (minutes)
MIN_GAP_MINUTES = 5

# Maximum shift distance (hours) — don't shift more than this
MAX_SHIFT_HOURS = 6


# ──────────────────────────────────────────────────────────
# CosAutoShiftService
# ──────────────────────────────────────────────────────────


class CosAutoShiftService:
    """
    Manages intelligent event auto-shifting with human-realism constraints.

    Usage:
        svc = CosAutoShiftService(user)
        result = svc.propose_shift(event, reason="conflict_avoidance")
        if result["can_auto_shift"]:
            svc.execute_shift(event, result["proposed_start"], result["proposed_end"], ...)
        else:
            # Present to user for confirmation
    """

    def __init__(self, user):
        self.user = user

    # ── Priority Determination ─────────────────────────────

    def determine_priority(self, event):
        """
        Determine the priority level of a calendar event.

        Rules:
        1. Protected events → always "high"
        2. Activity type default → from ACTIVITY_PRIORITY
        3. Fallback → "medium"

        Returns: "low", "medium", or "high"
        """
        if getattr(event, "is_protected", False):
            return "high"

        title = getattr(event, "title", "")
        activity_type = detect_activity_type(title)
        return ACTIVITY_PRIORITY.get(
            activity_type, ACTIVITY_PRIORITY["default"]
        )

    def can_auto_shift(self, event):
        """
        Check if an event can be auto-shifted without user confirmation.

        Only low-priority, non-protected events can be auto-shifted.

        Returns: bool
        """
        priority = self.determine_priority(event)
        return priority in AUTO_SHIFT_PRIORITIES

    # ── Time Suitability ───────────────────────────────────

    def get_time_window(self, activity_type):
        """
        Get the suitable time window (earliest, latest hour) for an activity type.

        Returns: (earliest_hour, latest_hour) tuple
        """
        return TIME_SUITABILITY.get(
            activity_type, TIME_SUITABILITY["default"]
        )

    def is_time_suitable(self, proposed_start, activity_type):
        """
        Check if a proposed start time falls within the suitable window.

        Returns: bool
        """
        earliest, latest = self.get_time_window(activity_type)
        hour = proposed_start.hour
        return earliest <= hour <= latest

    def clamp_to_suitable_time(self, proposed_start, activity_type):
        """
        Adjust a proposed start time to fit within the suitable window.

        If too early, moves to earliest suitable hour.
        If too late, moves to earliest suitable hour on the NEXT day.

        Returns: adjusted datetime
        """
        earliest, latest = self.get_time_window(activity_type)
        hour = proposed_start.hour

        if hour < earliest:
            return proposed_start.replace(
                hour=earliest, minute=0, second=0, microsecond=0,
            )
        elif hour > latest:
            # Too late — move to earliest next day
            next_day = proposed_start + dt.timedelta(days=1)
            return next_day.replace(
                hour=earliest, minute=0, second=0, microsecond=0,
            )
        return proposed_start

    # ── Shift Proposal ─────────────────────────────────────

    def propose_shift(
        self,
        event,
        reason="conflict_avoidance",
        conflicting_end=None,
        preferred_direction="after",
    ):
        """
        Propose a new time slot for an event.

        Args:
            event: CalendarEvent to shift
            reason: Why the shift is needed
            conflicting_end: End time of the conflicting event (if conflict-based)
            preferred_direction: "after" (default) or "before" the conflict

        Returns dict:
        {
            "can_auto_shift": bool,  # True if low priority
            "requires_confirmation": bool,  # True if medium/high
            "proposed_start": datetime or None,
            "proposed_end": datetime or None,
            "priority": str,
            "activity_type": str,
            "reason": str,
            "rejection_reason": str,  # Why shift was rejected (if any)
        }
        """
        title = getattr(event, "title", "")
        activity_type = detect_activity_type(title)
        priority = self.determine_priority(event)
        duration = event.end_dt - event.start_dt
        auto_ok = priority in AUTO_SHIFT_PRIORITIES

        base_result = {
            "can_auto_shift": False,
            "requires_confirmation": False,
            "proposed_start": None,
            "proposed_end": None,
            "priority": priority,
            "activity_type": activity_type,
            "reason": reason,
            "rejection_reason": "",
        }

        # Protected events: never auto-shift
        if getattr(event, "is_protected", False):
            base_result["rejection_reason"] = "Protected events cannot be auto-shifted."
            base_result["requires_confirmation"] = True
            return base_result

        # Find a suitable slot
        proposed_start = self._find_next_suitable_slot(
            event,
            activity_type,
            duration,
            conflicting_end=conflicting_end,
            direction=preferred_direction,
        )

        if not proposed_start:
            base_result["rejection_reason"] = (
                "No suitable time slot found within {} hours.".format(
                    MAX_SHIFT_HOURS
                )
            )
            return base_result

        proposed_end = proposed_start + duration

        # Check shift distance
        shift_delta = abs((proposed_start - event.start_dt).total_seconds())
        if shift_delta > MAX_SHIFT_HOURS * 3600:
            base_result["rejection_reason"] = (
                "Shift distance exceeds {} hours.".format(MAX_SHIFT_HOURS)
            )
            return base_result

        base_result["proposed_start"] = proposed_start
        base_result["proposed_end"] = proposed_end

        if auto_ok:
            base_result["can_auto_shift"] = True
        else:
            base_result["requires_confirmation"] = True

        return base_result

    # ── Shift Execution ────────────────────────────────────

    def execute_shift(
        self,
        event,
        new_start,
        new_end,
        reason="",
        shift_type="conflict_avoidance",
        user_confirmed=False,
    ):
        """
        Execute an event shift and log it.

        Uses CalendarMutationService for the actual update,
        then creates a CosAutoShiftLog entry.

        Args:
            event: CalendarEvent to shift
            new_start: New start datetime
            new_end: New end datetime
            reason: Human-readable reason
            shift_type: conflict_avoidance, priority_rebalance, time_optimization
            user_confirmed: Whether user explicitly approved

        Returns dict:
        {
            "success": bool,
            "log": CosAutoShiftLog or None,
            "error": str,
        }
        """
        priority = self.determine_priority(event)

        # Gate: non-low priority requires confirmation
        if priority not in AUTO_SHIFT_PRIORITIES and not user_confirmed:
            return {
                "success": False,
                "log": None,
                "error": (
                    "Event priority '{}' requires user confirmation. "
                    "Set user_confirmed=True to proceed."
                ).format(priority),
            }

        original_start = event.start_dt
        original_end = event.end_dt

        # Perform the update via CalendarMutationService
        try:
            from apps.calendar_engine.services.calendar_mutation_service import (
                CalendarMutationService,
            )

            mutation_svc = CalendarMutationService(self.user)
            result = mutation_svc.update(
                event_id=event.pk,
                start_dt=new_start,
                end_dt=new_end,
                force=True,  # Skip conflict detection (we already handled it)
            )

            if not result.success:
                return {
                    "success": False,
                    "log": None,
                    "error": "Mutation failed: {}".format(
                        result.conflict_warning or "Unknown error"
                    ),
                }
        except ImportError:
            # Fallback: direct update (for testing without full mutation service)
            event.start_dt = new_start
            event.end_dt = new_end
            event.save(update_fields=["start_dt", "end_dt", "updated_at"])
        except Exception as e:
            return {
                "success": False,
                "log": None,
                "error": "Shift failed: {}".format(str(e)),
            }

        # Log the shift — wrapped in try/except to not lose the shift itself
        log_entry = None
        try:
            ct = ContentType.objects.get_for_model(event)
            log_entry = CosAutoShiftLog.objects.create(
                user=self.user,
                content_type=ct,
                object_id=event.pk,
                original_start=original_start,
                original_end=original_end,
                new_start=new_start,
                new_end=new_end,
                reason=reason,
                shift_type=shift_type,
                priority_level=priority,
                user_confirmed=user_confirmed,
                auto_shifted=not user_confirmed,
            )
        except Exception as e:
            logger.error(
                "Shift succeeded but audit log failed for event %s: %s",
                event.pk, e,
            )

        logger.debug(
            "Event shifted: user=%s event=%s %s→%s (%s)",
            self.user.id, event.pk,
            original_start.isoformat(), new_start.isoformat(),
            shift_type,
        )

        return {
            "success": True,
            "log": log_entry,
            "error": "",
        }

    # ── Shift History ──────────────────────────────────────

    def get_shift_history(self, days=30, limit=20):
        """Get recent auto-shift logs for this user."""
        cutoff = dj_timezone.now() - dt.timedelta(days=days)
        return CosAutoShiftLog.objects.filter(
            user=self.user,
            created_at__gte=cutoff,
        )[:limit]

    def get_shifts_for_event(self, event):
        """Get all shift logs for a specific event."""
        ct = ContentType.objects.get_for_model(event)
        return CosAutoShiftLog.objects.filter(
            user=self.user,
            content_type=ct,
            object_id=event.pk,
        )

    # ── Batch Operations ───────────────────────────────────

    def resolve_conflicts_for_day(self, date):
        """
        Find and propose shifts for all conflicting events on a given day.

        Returns list of proposal dicts, one per conflict that can be resolved.
        Only proposes shifts for low-priority events.
        """
        from apps.calendar_engine.models import CalendarEvent

        # Build timezone-aware start/end of day
        naive = dt.datetime.combine(date, dt.time.min)
        try:
            start_of_day = dj_timezone.make_aware(naive)
        except ValueError:
            start_of_day = naive

        end_of_day = start_of_day + dt.timedelta(days=1)

        events = list(
            CalendarEvent.objects.filter(
                user=self.user,
                start_dt__gte=start_of_day,
                start_dt__lt=end_of_day,
                status="scheduled",
            )
            .exclude(deleted_at__isnull=False)
            .order_by("start_dt")
        )

        proposals = []
        for i, event in enumerate(events):
            # Check for overlap with next event
            if i + 1 < len(events):
                next_event = events[i + 1]
                if event.end_dt > next_event.start_dt:
                    # Conflict detected
                    proposal = self.propose_shift(
                        event,
                        reason="Conflicts with '{}'".format(next_event.title),
                        conflicting_end=next_event.end_dt,
                    )
                    if (
                        proposal["can_auto_shift"]
                        or proposal["requires_confirmation"]
                    ) and proposal["proposed_start"]:
                        proposal["event"] = event
                        proposal["conflicting_event"] = next_event
                        proposals.append(proposal)

        return proposals

    # ── Private Helpers ────────────────────────────────────

    def _find_next_suitable_slot(
        self,
        event,
        activity_type,
        duration,
        conflicting_end=None,
        direction="after",
    ):
        """
        Find the next suitable time slot for an event.

        Considers:
        - Time-of-day suitability for the activity type
        - Existing events (no overlaps)
        - MAX_SHIFT_HOURS limit
        - MIN_GAP_MINUTES between events

        Returns: datetime or None
        """
        from apps.calendar_engine.models import CalendarEvent

        # Starting point for search
        if conflicting_end and direction == "after":
            search_start = conflicting_end + dt.timedelta(minutes=MIN_GAP_MINUTES)
        elif direction == "after":
            search_start = event.end_dt + dt.timedelta(minutes=MIN_GAP_MINUTES)
        else:
            search_start = event.start_dt

        # Clamp to suitable time window
        search_start = self.clamp_to_suitable_time(search_start, activity_type)

        # Max search boundary
        max_boundary = event.start_dt + dt.timedelta(hours=MAX_SHIFT_HOURS)

        # Get existing events in the search window
        existing = list(
            CalendarEvent.objects.filter(
                user=self.user,
                start_dt__lt=max_boundary,
                end_dt__gt=search_start,
                status="scheduled",
            )
            .exclude(pk=event.pk)
            .exclude(deleted_at__isnull=False)
            .order_by("start_dt")
        )

        # Try slots starting from search_start
        candidate = search_start
        max_attempts = 20  # Safety limit

        for _ in range(max_attempts):
            if candidate > max_boundary:
                return None

            # Check suitability
            if not self.is_time_suitable(candidate, activity_type):
                candidate = self.clamp_to_suitable_time(
                    candidate + dt.timedelta(hours=1), activity_type,
                )
                continue

            # Check for overlap with existing events
            candidate_end = candidate + duration
            has_overlap = False

            for existing_event in existing:
                if (
                    candidate < existing_event.end_dt
                    and candidate_end > existing_event.start_dt
                ):
                    # Overlap — jump past this event
                    candidate = existing_event.end_dt + dt.timedelta(
                        minutes=MIN_GAP_MINUTES
                    )
                    has_overlap = True
                    break

            if not has_overlap:
                return candidate

        return None
