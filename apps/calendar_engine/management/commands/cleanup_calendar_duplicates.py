# ==============================================================================
# File: apps/calendar_engine/management/commands/cleanup_calendar_duplicates.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Find and soft-delete duplicate calendar events
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-26
# ==============================================================================
"""
Calendar Duplicate Cleanup Command

Finds calendar events with the same (user, title, date) that are duplicates
and soft-deletes the lower-priority copies.

Priority rules (higher = keep):
  1. is_protected=True always wins
  2. execution_block > manual (CoS-generated blocks are authoritative)
  3. If tied, keep the event with the longer duration (more specific scheduling)
  4. If still tied, keep the newest (latest created_at)

Usage:
    python manage.py cleanup_calendar_duplicates --dry-run
    python manage.py cleanup_calendar_duplicates --user=dannyjenkins71@gmail.com
    python manage.py cleanup_calendar_duplicates --user=dannyjenkins71@gmail.com --apply
    python manage.py cleanup_calendar_duplicates --user=dannyjenkins71@gmail.com --apply --days=90
"""

import logging
from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.calendar_engine.models import CalendarEvent

logger = logging.getLogger(__name__)


def _event_sort_key(event):
    """
    Sort key for picking the "best" event in a duplicate group.
    Higher tuple = better (we keep the max).
    """
    return (
        event.is_protected,                        # Protected wins
        event.event_kind == CalendarEvent.KIND_EXECUTION_BLOCK,  # Exec blocks > manual
        (event.end_dt - event.start_dt).total_seconds(),  # Longer duration
        event.created_at or timezone.now(),         # Newest creation
    )


class Command(BaseCommand):
    help = 'Find and soft-delete duplicate calendar events'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            type=str,
            help='Email of user to clean up (required)',
        )
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Actually soft-delete duplicates. Without this flag, dry-run only.',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=365,
            help='How many days back to scan (default: 365)',
        )
        parser.add_argument(
            '--future-days',
            type=int,
            default=90,
            help='How many days forward to scan (default: 90)',
        )

    def handle(self, *args, **options):
        user_email = options['user']
        apply = options['apply']
        days_back = options['days']
        future_days = options['future_days']

        if not user_email:
            self.stderr.write(self.style.ERROR(
                'ERROR: --user is required. Usage: --user=dannyjenkins71@gmail.com'
            ))
            return

        from apps.users.models import User
        try:
            user = User.objects.get(email=user_email)
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'User not found: {user_email}'))
            return

        mode = 'APPLYING' if apply else 'DRY RUN'
        self.stdout.write(self.style.WARNING(f'\n=== Calendar Duplicate Cleanup ({mode}) ==='))
        self.stdout.write(f'User: {user.email} (ID: {user.id})')

        # Date range
        now = timezone.now()
        start_date = now - timedelta(days=days_back)
        end_date = now + timedelta(days=future_days)
        self.stdout.write(f'Scanning: {start_date.date()} → {end_date.date()}\n')

        # Get all active events in range
        events = (
            CalendarEvent.objects
            .filter(
                user=user,
                status=CalendarEvent.STATUS_SCHEDULED,
                deleted_at__isnull=True,
                start_dt__gte=start_date,
                start_dt__lte=end_date,
            )
            .order_by('start_dt')
        )

        total_events = events.count()
        self.stdout.write(f'Total active events in range: {total_events}')

        # Group by (title_lower, date)
        groups = defaultdict(list)
        for event in events:
            key = (event.title.strip().lower(), event.start_dt.date())
            groups[key].append(event)

        # Find groups with duplicates
        dup_groups = {k: v for k, v in groups.items() if len(v) > 1}

        if not dup_groups:
            self.stdout.write(self.style.SUCCESS('\nNo duplicates found. Calendar is clean!'))
            return

        self.stdout.write(self.style.WARNING(
            f'\nFound {len(dup_groups)} duplicate groups '
            f'({sum(len(v) for v in dup_groups.values())} total events):'
        ))

        total_to_remove = 0
        events_to_delete = []

        for (title, date), group in sorted(dup_groups.items(), key=lambda x: x[1]):
            # Sort by priority — best last
            group.sort(key=_event_sort_key)
            keeper = group[-1]  # Highest priority
            dupes = group[:-1]  # Everything else

            self.stdout.write(f'\n  "{title}" on {date} ({len(group)} events):')
            for event in group:
                marker = '  KEEP' if event == keeper else '  DELETE'
                prot = ' [PROTECTED]' if event.is_protected else ''
                kind = f' ({event.get_event_kind_display()})'
                self.stdout.write(
                    f'    {marker}: ID={event.id} '
                    f'{event.start_dt.strftime("%I:%M %p")}-{event.end_dt.strftime("%I:%M %p")}'
                    f'{kind}{prot}'
                    f' (created {event.created_at.strftime("%Y-%m-%d %H:%M") if event.created_at else "?"})'
                )

            events_to_delete.extend(dupes)
            total_to_remove += len(dupes)

        self.stdout.write(self.style.WARNING(
            f'\nSummary: {total_to_remove} events to remove, '
            f'{total_events - total_to_remove} events to keep'
        ))

        if not apply:
            self.stdout.write(self.style.NOTICE(
                '\nDRY RUN — no changes made. Add --apply to execute.'
            ))
            return

        # Actually soft-delete
        deleted_count = 0
        for event in events_to_delete:
            try:
                event.soft_delete()
                deleted_count += 1
                logger.info(
                    'Dedup cleanup: soft-deleted CalendarEvent %s '
                    '(title=%s, date=%s, kind=%s)',
                    event.id, event.title, event.start_dt.date(), event.event_kind,
                )
            except Exception as e:
                self.stderr.write(self.style.ERROR(
                    f'  ERROR deleting event {event.id}: {e}'
                ))
                logger.exception('Failed to soft-delete event %s during dedup', event.id)

        self.stdout.write(self.style.SUCCESS(
            f'\nDone! Soft-deleted {deleted_count}/{total_to_remove} duplicate events.'
        ))
