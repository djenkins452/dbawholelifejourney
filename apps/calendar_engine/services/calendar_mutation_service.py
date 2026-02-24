# ==============================================================================
# File: calendar_engine/services/calendar_mutation_service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Single mutation path for all CalendarEvent create/update/delete.
#              Used by BOTH AI handlers and view-layer endpoints.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-23
# ==============================================================================
"""
CalendarMutationService — Single source of truth for CalendarEvent mutations.

All CalendarEvent writes (create, update, delete) MUST go through this service.
This ensures:
- transaction.atomic() wrapping
- select_for_update() on update/delete
- Idempotency enforcement via existing UniqueConstraint(user, idempotency_key)
- ExecutionLog write for time changes (via DriftEngine) and cancellations
- Post-commit hooks: conflict detection, drift, pressure, Google Calendar sync

Consumers:
- AI handler: handle_mutate_calendar_event() → CalendarMutationService.update/delete
- AI handler: handle_create_event() → CalendarMutationService.create
- View layer: EventDetailView.patch → CalendarMutationService.update
- View layer: EventDetailView.delete → CalendarMutationService.delete
"""

import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from django.db import IntegrityError, transaction
from django.utils import timezone as dj_timezone

from apps.calendar_engine.models import CalendarEvent
from apps.calendar_engine.utils.idempotency import compute_idempotency_key
from apps.core.time.system_clock import get_current_time

logger = logging.getLogger(__name__)


@dataclass
class MutationResult:
    """Result of a CalendarMutationService operation."""
    success: bool
    event: Optional[CalendarEvent] = None
    reused: bool = False
    error: Optional[str] = None
    fields_changed: Optional[Dict[str, Any]] = None
    gcal_synced: bool = False
    conflict_warning: Optional[str] = None
    pressure_note: Optional[str] = None
    # Phase 10: Conflict policy — pre-commit pause
    requires_decision: bool = False
    conflict_details: Optional[Dict[str, Any]] = None
    suggested_alternatives: Optional[List[Dict[str, Any]]] = None


class CalendarMutationService:
    """
    Single mutation path for CalendarEvent CRUD.

    Usage:
        service = CalendarMutationService(user)
        result = service.create(title="Meeting", start_dt=..., end_dt=..., ...)
        result = service.update(event_id=42, title="Updated", ...)
        result = service.delete(event_id=42)
    """

    # Auto-protect patterns: events matching these title substrings
    # get is_protected=True on creation (case-insensitive).
    AUTO_PROTECT_PATTERNS = [
        'workout', 'exercise', 'gym', 'training',
        'bible study', 'bible reading', 'devotional', 'scripture',
        'prayer', 'prayer time', 'quiet time',
        'journaling', 'journal', 'reflection',
        'health check', 'doctor', 'medical', 'therapy', 'appointment',
    ]

    def __init__(self, user):
        self.user = user

    # ------------------------------------------------------------------ #
    # User timezone helper
    # ------------------------------------------------------------------ #

    def _get_user_tz(self):
        """Get user's timezone for local-date comparison. Falls back to UTC."""
        try:
            from zoneinfo import ZoneInfo
            tz_name = self.user.preferences.timezone_iana
            if tz_name:
                return ZoneInfo(tz_name)
        except (AttributeError, Exception):
            pass
        return dj_timezone.utc

    # ------------------------------------------------------------------ #
    # Recurring-event duplicate detection
    # ------------------------------------------------------------------ #

    def _check_recurrence_duplicate(self, title, start_dt):
        """
        Check if *start_dt* collides with an occurrence of a recurring
        event that has the same title (case-insensitive).

        The regular semantic-dup check only matches the base row's exact
        start_dt. This method expands RecurrenceRule occurrences in a
        ±1-day window so that "add Workout next Thursday 6:15am" is
        caught when a weekly Workout series already covers that slot.

        Returns the base CalendarEvent if a match is found, else None.
        """
        from datetime import timedelta

        recurring_candidates = (
            CalendarEvent.objects
            .filter(
                user=self.user,
                title__iexact=title.strip(),
                recurrence__isnull=False,
                deleted_at__isnull=True,
            )
            .exclude(status=CalendarEvent.STATUS_CANCELED)
            .select_related('recurrence')
        )

        if not recurring_candidates.exists():
            return None

        window_start = start_dt - timedelta(days=1)
        window_end = start_dt + timedelta(days=1)

        for event in recurring_candidates:
            try:
                occurrences = event.recurrence.get_occurrences(
                    window_start, window_end,
                )
            except Exception:
                continue
            for occ_start, _occ_end in occurrences:
                if occ_start == start_dt:
                    logger.info(
                        "Recurrence duplicate blocked: user=%s title=%r "
                        "start_dt=%s matches occurrence of recurring "
                        "event pk=%s",
                        self.user.id, title, start_dt, event.pk,
                    )
                    return event
        return None

    # ------------------------------------------------------------------ #
    # Auto-protect logic
    # ------------------------------------------------------------------ #

    @classmethod
    def should_auto_protect(cls, title: str) -> bool:
        """
        Determine if an event title matches auto-protect patterns.

        Events for Workout, Bible Study, Prayer, Journaling, and Health
        are automatically marked as protected.
        """
        title_lower = title.strip().lower()
        return any(pattern in title_lower for pattern in cls.AUTO_PROTECT_PATTERNS)

    # ------------------------------------------------------------------ #
    # CREATE
    # ------------------------------------------------------------------ #

    def create(
        self,
        title: str,
        start_dt,
        end_dt,
        idempotency_key: Optional[str] = None,
        description: str = "",
        is_all_day: bool = False,
        domain=None,
        event_kind: str = CalendarEvent.KIND_MANUAL,
        source_type: str = CalendarEvent.SOURCE_NONE,
        source_id: str = "",
        is_protected: bool = False,
        status: str = CalendarEvent.STATUS_SCHEDULED,
        force: bool = False,
    ) -> MutationResult:
        """
        Create a CalendarEvent with idempotency enforcement and conflict policy.

        Phase 10 conflict policy: before creating, checks ALL scheduled events
        for time overlap. If a conflict exists and force=False, returns
        requires_decision=True with conflict details and suggested alternatives.
        The event is NOT created until the user confirms (force=True).

        Args:
            force: If True, skip conflict detection and create anyway.
                   Used when user explicitly confirms override.
        """
        if not idempotency_key:
            idempotency_key = compute_idempotency_key(
                self.user.id, title, start_dt, end_dt=end_dt,
                source_type=source_type, source_id=source_id,
            )

        # --- Auto-protect ---
        if not is_protected and self.should_auto_protect(title):
            is_protected = True
            logger.debug(
                "Auto-protect enabled for title=%r (user=%s)",
                title, self.user.id,
            )

        # --- Idempotency check (before conflict detection) ---
        # Must check BEFORE conflict detection: replaying the same create
        # should return the existing event, not trigger a conflict.
        existing = CalendarEvent.objects.filter(
            user=self.user, idempotency_key=idempotency_key,
        ).first()
        if existing:
            return MutationResult(
                success=True, event=existing, reused=True,
            )

        # --- Semantic duplicate check (before conflict detection) ---
        # Match on title + start_dt only (not end_dt).  Events with the
        # same name and start time are semantically the same even when
        # the caller supplies a different duration.
        semantic_dup = (
            CalendarEvent.objects
            .filter(
                user=self.user,
                title__iexact=title.strip(),
                start_dt=start_dt,
                deleted_at__isnull=True,
            )
            .exclude(status=CalendarEvent.STATUS_CANCELED)
            .first()
        )
        if semantic_dup:
            logger.info(
                "Semantic duplicate blocked: user=%s title=%r "
                "start_dt=%s — returning existing pk=%s",
                self.user.id, title, start_dt, semantic_dup.pk,
            )
            return MutationResult(
                success=True, event=semantic_dup, reused=True,
            )

        # --- Recurring event duplicate check ---
        # The semantic check above only matches exact start_dt on stored
        # rows.  Recurring events store ONE base row and expand occurrences
        # dynamically, so "add Workout next Thursday" won't match a weekly
        # Workout whose base row is a different Thursday.  Expand
        # occurrences in a ±1-day window around the proposed start_dt.
        recurrence_dup = self._check_recurrence_duplicate(
            title, start_dt,
        )
        if recurrence_dup:
            return MutationResult(
                success=True, event=recurrence_dup, reused=True,
            )

        # --- Phase 10: Pre-commit conflict detection ---
        if not force and not is_all_day:
            conflict_result = self._check_pre_commit_conflicts(
                start_dt, end_dt, new_is_protected=is_protected,
            )
            if conflict_result is not None:
                return conflict_result

        reused = False
        try:
            with transaction.atomic():
                # Re-check idempotency inside transaction for race safety
                existing = CalendarEvent.objects.filter(
                    user=self.user, idempotency_key=idempotency_key,
                ).first()

                if existing:
                    return MutationResult(
                        success=True, event=existing, reused=True,
                    )

                # Re-check semantic dup with lock inside transaction
                semantic_dup = (
                    CalendarEvent.objects
                    .select_for_update()
                    .filter(
                        user=self.user,
                        title__iexact=title.strip(),
                        start_dt=start_dt,
                        deleted_at__isnull=True,
                    )
                    .exclude(status=CalendarEvent.STATUS_CANCELED)
                    .first()
                )
                if semantic_dup:
                    return MutationResult(
                        success=True, event=semantic_dup, reused=True,
                    )

                # Re-check recurrence dup inside transaction
                recurrence_dup = self._check_recurrence_duplicate(
                    title, start_dt,
                )
                if recurrence_dup:
                    return MutationResult(
                        success=True, event=recurrence_dup, reused=True,
                    )

                try:
                    with transaction.atomic():  # Nested savepoint
                        event = CalendarEvent.objects.create(
                            user=self.user,
                            title=title,
                            description=description,
                            start_dt=start_dt,
                            end_dt=end_dt,
                            is_all_day=is_all_day,
                            domain=domain,
                            event_kind=event_kind,
                            source_type=source_type,
                            source_id=source_id,
                            is_protected=is_protected,
                            status=status,
                            idempotency_key=idempotency_key,
                        )
                except IntegrityError:
                    # Concurrent create — find the winner
                    event = CalendarEvent.objects.get(
                        user=self.user, idempotency_key=idempotency_key,
                    )
                    reused = True

                if not reused:
                    # Post-write verification
                    verified = CalendarEvent.objects.get(pk=event.pk)
                    if verified.start_dt != start_dt or verified.title != title:
                        raise RuntimeError(
                            f"Post-write verification failed: "
                            f"expected title={title!r}, start_dt={start_dt}, "
                            f"got title={verified.title!r}, start_dt={verified.start_dt}"
                        )

        except RuntimeError:
            logger.error(
                "CalendarMutationService.create post-write verification failed "
                "for user=%s title=%r", self.user.id, title,
            )
            return MutationResult(
                success=False, error="Post-write verification failed",
            )
        except Exception as e:
            logger.error(
                "CalendarMutationService.create failed for user=%s: %s",
                self.user.id, e, exc_info=True,
            )
            return MutationResult(success=False, error=str(e))

        # Post-commit hooks (outside transaction)
        cos_context = self._run_post_scheduling(event)

        return MutationResult(
            success=True,
            event=event,
            reused=reused,
            conflict_warning=cos_context.get('conflict_warning'),
            pressure_note=cos_context.get('pressure_note'),
            gcal_synced=cos_context.get('gcal_synced', False),
        )

    # ------------------------------------------------------------------ #
    # UPDATE
    # ------------------------------------------------------------------ #

    def update(self, event_id: int, force: bool = False, **fields) -> MutationResult:
        """
        Update a CalendarEvent with row locking, drift logging, and conflict policy.

        Only updates fields that are explicitly provided.
        Uses select_for_update() for concurrency safety.

        Phase 10 conflict policy:
        - Protected events CANNOT be moved to a different day (error).
        - Protected events CAN be moved within the same day.
        - If time overlap detected and force=False, returns requires_decision=True.

        Args:
            force: If True, skip conflict detection. Used after user confirms override.
        """
        ALLOWED_FIELDS = {
            'title', 'description', 'start_dt', 'end_dt',
            'is_all_day', 'is_protected', 'status',
        }
        update_fields = {k: v for k, v in fields.items() if k in ALLOWED_FIELDS}
        if not update_fields:
            return MutationResult(success=False, error="No valid fields to update")

        try:
            with transaction.atomic():
                try:
                    event = CalendarEvent.objects.select_for_update().get(
                        pk=event_id, user=self.user,
                    )
                except CalendarEvent.DoesNotExist:
                    return MutationResult(
                        success=False, error="Event not found",
                    )

                # --- Phase 10: Protected event day-change guard ---
                # Protected events can NEVER be moved to a different day,
                # even with force=True.  Only same-day time changes allowed.
                # Compare dates in user's local timezone to avoid UTC vs
                # local date mismatch near midnight.
                new_start_dt = update_fields.get('start_dt')
                if event.is_protected and new_start_dt:
                    user_tz = self._get_user_tz()
                    existing_local_date = event.start_dt.astimezone(user_tz).date()
                    new_local_date = new_start_dt.astimezone(user_tz).date()
                    if existing_local_date != new_local_date:
                        return MutationResult(
                            success=False,
                            requires_decision=True,
                            error=(
                                f"{event.title} is protected and cannot be moved "
                                f"to a different day. You can adjust the time "
                                f"within the same day."
                            ),
                        )

                # --- Phase 10: Pre-commit conflict detection ---
                if not force and new_start_dt:
                    new_end_dt = update_fields.get('end_dt', event.end_dt)
                    conflict_result = self._check_pre_commit_conflicts(
                        new_start_dt, new_end_dt,
                        new_is_protected=event.is_protected,
                        exclude_event_id=event.pk,
                    )
                    if conflict_result is not None:
                        return conflict_result

                # Capture old values for diff
                old_values = {}
                for field_name in update_fields:
                    old_values[field_name] = getattr(event, field_name)

                original_start_dt = event.start_dt

                # Apply updates
                for field_name, value in update_fields.items():
                    setattr(event, field_name, value)

                event.save()

                # Build diff
                fields_changed = {}
                for field_name in update_fields:
                    old_val = old_values[field_name]
                    new_val = getattr(event, field_name)
                    if old_val != new_val:
                        fields_changed[field_name] = {
                            'old': str(old_val),
                            'new': str(new_val),
                        }

                # Log schedule change if start_dt changed
                if 'start_dt' in fields_changed:
                    from apps.core.drift.engine import DriftEngine
                    DriftEngine.record_schedule_change(
                        self.user, event, original_start_dt, event.start_dt,
                    )
                elif fields_changed:
                    # Metadata-only change — log with zero instability
                    self._write_metadata_log(event, fields_changed)

                # Post-write verification
                verified = CalendarEvent.objects.get(pk=event.pk)
                for field_name, value in update_fields.items():
                    if getattr(verified, field_name) != value:
                        return MutationResult(
                            success=False,
                            error=f"Update verification failed for field '{field_name}'",
                        )

        except Exception as e:
            logger.error(
                "CalendarMutationService.update failed for user=%s event=%s: %s",
                self.user.id, event_id, e, exc_info=True,
            )
            return MutationResult(success=False, error=str(e))

        # Post-commit hooks
        cos_context = self._run_post_scheduling(event)

        return MutationResult(
            success=True,
            event=event,
            fields_changed=fields_changed,
            conflict_warning=cos_context.get('conflict_warning'),
            pressure_note=cos_context.get('pressure_note'),
            gcal_synced=cos_context.get('gcal_synced', False),
        )

    # ------------------------------------------------------------------ #
    # DELETE (soft delete via status='canceled')
    # ------------------------------------------------------------------ #

    def delete(self, event_id: int) -> MutationResult:
        """
        Soft-delete a CalendarEvent by setting status='canceled' + deleted_at.

        Uses select_for_update() for concurrency safety.
        Writes ExecutionLog with event_type='canceled'.
        """
        try:
            with transaction.atomic():
                try:
                    event = CalendarEvent.objects.select_for_update().get(
                        pk=event_id, user=self.user,
                    )
                except CalendarEvent.DoesNotExist:
                    return MutationResult(
                        success=False, error="Event not found",
                    )

                if event.status == CalendarEvent.STATUS_CANCELED:
                    return MutationResult(
                        success=True, event=event,
                        fields_changed={},
                    )

                original_status = event.status
                now = get_current_time()

                event.status = CalendarEvent.STATUS_CANCELED
                event.deleted_at = now
                event.save(update_fields=['status', 'deleted_at', 'updated_at'])

                # Write cancellation log
                self._write_cancellation_log(event, now)

                # Verification
                verified = CalendarEvent.objects.get(pk=event.pk)
                if verified.status != CalendarEvent.STATUS_CANCELED:
                    return MutationResult(
                        success=False,
                        error="Delete verification failed — status not canceled",
                    )

        except Exception as e:
            logger.error(
                "CalendarMutationService.delete failed for user=%s event=%s: %s",
                self.user.id, event_id, e, exc_info=True,
            )
            return MutationResult(success=False, error=str(e))

        # Post-commit: sync deletion to Google Calendar
        gcal_synced = self._sync_delete_to_google(event)

        return MutationResult(
            success=True,
            event=event,
            fields_changed={'status': {'old': original_status, 'new': 'canceled'}},
            gcal_synced=gcal_synced,
        )

    # ------------------------------------------------------------------ #
    # Phase 10: Pre-commit conflict detection
    # ------------------------------------------------------------------ #

    def _check_pre_commit_conflicts(
        self, start_dt, end_dt, new_is_protected=False,
        exclude_event_id=None,
    ) -> Optional[MutationResult]:
        """
        Check for time overlap with existing events BEFORE committing.

        Returns a MutationResult with requires_decision=True if conflict found,
        or None if no conflict.
        """
        from apps.calendar_engine.services.conflicts import (
            detect_all_conflicts, classify_conflict_case,
            build_conflict_message,
        )

        conflict_result = detect_all_conflicts(
            self.user, start_dt, end_dt,
            exclude_event_id=exclude_event_id,
        )

        if not conflict_result['has_conflict']:
            return None

        case = classify_conflict_case(
            conflict_result['conflicts'], new_is_protected,
        )

        # Find suggested alternative time slots
        suggested_gaps = []
        try:
            from apps.calendar_engine.services.suggestions import find_gaps_for_day
            gaps = find_gaps_for_day(self.user, date=start_dt.date())
            suggested_gaps = [
                {
                    'start_dt': g['start_dt'].isoformat(),
                    'end_dt': g['end_dt'].isoformat(),
                    'duration_minutes': g['duration_minutes'],
                }
                for g in gaps
            ]
        except Exception as e:
            logger.debug("Gap suggestion failed (non-fatal): %s", e)

        message = build_conflict_message(
            case, conflict_result['conflicts'], suggested_gaps,
        )

        return MutationResult(
            success=False,
            requires_decision=True,
            error=message,
            conflict_details={
                'case': case,
                'conflicts': conflict_result['conflicts'],
                'proposed_event': {
                    'start_dt': start_dt.isoformat(),
                    'end_dt': end_dt.isoformat(),
                },
            },
            suggested_alternatives=suggested_gaps or None,
        )

    # ------------------------------------------------------------------ #
    # Post-commit hooks
    # ------------------------------------------------------------------ #

    def _run_post_scheduling(self, event) -> dict:
        """
        Post-commit chain: conflict detection, drift, pressure, Google sync.
        Each step is exception-guarded — failures never block the user.
        """
        result = {
            'conflict_warning': None,
            'pressure_note': None,
            'gcal_synced': False,
        }

        # 1. Conflict detection
        try:
            from apps.core.blueprint.architecture_engine import get_todays_plan
            plan = get_todays_plan(self.user)
            if plan and hasattr(plan, 'blocks') and plan.blocks:
                event_date = event.start_dt.date()
                for block in plan.blocks:
                    block_start = block.get('start_dt')
                    block_end = block.get('end_dt')
                    if block_start and block_end:
                        if (event.start_dt < block_end and event.end_dt > block_start):
                            tier = block.get('tier', 99)
                            if tier <= 1:
                                result['conflict_warning'] = (
                                    f"⚠️ Overlaps protected commitment: "
                                    f"{block.get('title', 'Unknown')}"
                                )
                                break
        except Exception as e:
            logger.debug("Conflict detection skipped: %s", e)

        # 2. Drift recompute
        try:
            from apps.core.blueprint.drift_engine import compute_daily_drift_score
            compute_daily_drift_score(self.user, date=event.start_dt.date())
        except Exception as e:
            logger.debug("Drift recompute skipped: %s", e)

        # 3. Schedule instability evaluation
        try:
            from apps.core.drift.engine import DriftEngine
            DriftEngine.evaluate_schedule_instability(self.user)
        except Exception as e:
            logger.debug("Schedule instability evaluation skipped: %s", e)

        # 4. Weekly pressure recompute
        try:
            from apps.core.blueprint.drift_engine import compute_weekly_pressure
            pressure = compute_weekly_pressure(
                self.user, start_date=event.start_dt.date(), days=1,
            )
            if pressure and pressure.get('capacity_pct', 0) >= 85:
                label = pressure.get('label', 'high')
                result['pressure_note'] = (
                    f"Day is now at {label} capacity "
                    f"({pressure['capacity_pct']}%)"
                )
        except Exception as e:
            logger.debug("Weekly pressure recompute skipped: %s", e)

        # 5. Google Calendar sync
        try:
            result['gcal_synced'] = self._sync_to_google(event)
        except Exception as e:
            logger.debug("Google Calendar sync skipped: %s", e)

        return result

    def _sync_to_google(self, event) -> bool:
        """Sync event to Google Calendar if connected. Returns True if synced."""
        try:
            from apps.life.models import GoogleCalendarCredential
            cred = GoogleCalendarCredential.objects.filter(
                user=self.user, is_connected=True,
            ).first()
            if not cred:
                return False
            if cred.sync_direction not in ('export', 'both'):
                return False

            from apps.life.services.google_calendar import CalendarSyncService
            sync_service = CalendarSyncService(self.user)
            sync_service.sync_to_google(event)
            return True
        except Exception as e:
            logger.debug("Google Calendar sync failed (non-fatal): %s", e)
            return False

    def _sync_delete_to_google(self, event) -> bool:
        """Sync event deletion to Google Calendar if connected."""
        try:
            from apps.life.models import GoogleCalendarCredential
            cred = GoogleCalendarCredential.objects.filter(
                user=self.user, is_connected=True,
            ).first()
            if not cred:
                return False

            google_event_id = getattr(event, 'google_event_id', None)
            if not google_event_id:
                return False

            from apps.life.services.google_calendar import GoogleCalendarService
            service = GoogleCalendarService()
            cred_dict = cred.get_credentials_dict()
            if cred_dict:
                service.delete_event(cred_dict, google_event_id)
                return True
            return False
        except Exception as e:
            logger.debug("Google Calendar delete sync failed (non-fatal): %s", e)
            return False

    # ------------------------------------------------------------------ #
    # ExecutionLog helpers
    # ------------------------------------------------------------------ #

    def _write_metadata_log(self, event, fields_changed):
        """Write ExecutionLog for metadata-only changes (zero instability)."""
        try:
            from apps.core.drift.models import ExecutionLog

            idem_key = hashlib.sha256(
                f"{self.user.id}:{event.pk}:metadata:"
                f"{get_current_time().isoformat()}".encode()
            ).hexdigest()

            ExecutionLog.objects.get_or_create(
                user=self.user,
                idempotency_key=idem_key,
                defaults={
                    'calendar_event': event,
                    'event_type': ExecutionLog.EVENT_TYPE_TIME_SHIFT,
                    'instability_points': 0,
                    'weight': 0,
                    'meta': {
                        'mutation_type': 'metadata_update',
                        'fields_changed': fields_changed,
                    },
                },
            )
        except Exception as e:
            logger.debug("Metadata ExecutionLog write skipped: %s", e)

    def _write_cancellation_log(self, event, now):
        """Write ExecutionLog for event cancellation."""
        try:
            from apps.core.drift.models import ExecutionLog

            idem_key = hashlib.sha256(
                f"{self.user.id}:{event.pk}:canceled:{now.isoformat()}".encode()
            ).hexdigest()

            ExecutionLog.objects.get_or_create(
                user=self.user,
                idempotency_key=idem_key,
                defaults={
                    'calendar_event': event,
                    'event_type': ExecutionLog.EVENT_TYPE_CANCELED,
                    'instability_points': 0,
                    'weight': 0,
                    'meta': {
                        'mutation_type': 'soft_delete',
                        'canceled_at': now.isoformat(),
                        'original_title': event.title,
                        'original_start_dt': event.start_dt.isoformat(),
                    },
                },
            )
        except Exception as e:
            logger.debug("Cancellation ExecutionLog write skipped: %s", e)
