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


class CalendarMutationService:
    """
    Single mutation path for CalendarEvent CRUD.

    Usage:
        service = CalendarMutationService(user)
        result = service.create(title="Meeting", start_dt=..., end_dt=..., ...)
        result = service.update(event_id=42, title="Updated", ...)
        result = service.delete(event_id=42)
    """

    def __init__(self, user):
        self.user = user

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
    ) -> MutationResult:
        """
        Create a CalendarEvent with idempotency enforcement.

        Uses the existing UniqueConstraint(user, idempotency_key) with
        nested transaction savepoints for race-condition recovery.
        """
        if not idempotency_key:
            idempotency_key = compute_idempotency_key(
                self.user.id, title, start_dt, end_dt=end_dt,
                source_type=source_type, source_id=source_id,
            )

        reused = False
        try:
            with transaction.atomic():
                # Check for existing event with same idempotency key
                existing = CalendarEvent.objects.filter(
                    user=self.user, idempotency_key=idempotency_key,
                ).first()

                if existing:
                    return MutationResult(
                        success=True, event=existing, reused=True,
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

    def update(self, event_id: int, **fields) -> MutationResult:
        """
        Update a CalendarEvent with row locking and drift logging.

        Only updates fields that are explicitly provided.
        Uses select_for_update() for concurrency safety.
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
