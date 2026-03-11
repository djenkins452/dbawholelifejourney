"""
One-time management command to purge all "Approve Payroll" objects.

Removes:
- LifeTask instances (including recurring series roots and children)
- CalendarEvent instances (including recurring series)
- Orphaned RecurrenceRule records

Usage:
    python manage.py purge_approve_payroll          # dry run
    python manage.py purge_approve_payroll --execute # actually delete
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Purge all "Approve Payroll" tasks, events, and recurrence rules'

    def add_arguments(self, parser):
        parser.add_argument(
            '--execute',
            action='store_true',
            help='Actually delete (default is dry run)',
        )

    def handle(self, *args, **options):
        execute = options['execute']
        mode = 'EXECUTE' if execute else 'DRY RUN'
        self.stdout.write(f'\n=== Purge Approve Payroll ({mode}) ===\n')

        task_count = 0
        event_count = 0
        rule_count = 0

        # ── 1. LifeTask (including soft-deleted) ─────────────────
        try:
            from apps.life.models import Task

            # Get all matching tasks (including soft-deleted via all_objects)
            tasks = Task.all_objects.filter(title__icontains='Approve Payroll')
            task_count = tasks.count()
            self.stdout.write(f'LifeTasks found: {task_count}')
            for t in tasks:
                parent = t.recurring_parent_id
                self.stdout.write(
                    f'  ID={t.id} user={t.user_id} '
                    f'recurring={t.is_recurring} parent={parent} '
                    f'deleted={t.is_deleted} status={t.completion_status}'
                )

            if execute and task_count > 0:
                # Hard delete to fully purge
                deleted, _ = tasks.delete()
                self.stdout.write(self.style.SUCCESS(
                    f'  Deleted {deleted} task records'
                ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Task purge error: {e}'))

        # ── 2. CalendarEvent ─────────────────────────────────────
        try:
            from apps.calendar_engine.models import CalendarEvent

            events = CalendarEvent.objects.filter(
                title__icontains='Approve Payroll',
            )
            event_count = events.count()
            self.stdout.write(f'\nCalendarEvents found: {event_count}')
            for e in events:
                rule_id = getattr(e, 'recurrence_rule_id', None)
                self.stdout.write(
                    f'  ID={e.id} user={e.user_id} rule_id={rule_id}'
                )

            if execute and event_count > 0:
                deleted, _ = events.delete()
                self.stdout.write(self.style.SUCCESS(
                    f'  Deleted {deleted} event records'
                ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Event purge error: {e}'))

        # ── 3. Orphaned RecurrenceRule records ───────────────────
        try:
            from apps.calendar_engine.models import RecurrenceRule

            # Find rules that no longer have any events attached
            orphan_rules = RecurrenceRule.objects.filter(
                event__isnull=True,
            )
            # Also check for rules tied to the deleted events
            # by looking for rules with no remaining events
            rule_count = orphan_rules.count()
            self.stdout.write(f'\nOrphaned RecurrenceRules: {rule_count}')

            if execute and rule_count > 0:
                deleted, _ = orphan_rules.delete()
                self.stdout.write(self.style.SUCCESS(
                    f'  Deleted {deleted} orphan recurrence rules'
                ))
        except ImportError:
            self.stdout.write('  RecurrenceRule model not found, skipping')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Rule purge error: {e}'))

        # ── 4. Verify ────────────────────────────────────────────
        if execute:
            self.stdout.write('\n--- Verification ---')
            try:
                from apps.life.models import Task
                remaining = Task.all_objects.filter(
                    title__icontains='Approve Payroll',
                ).count()
                self.stdout.write(f'Remaining tasks: {remaining}')
            except Exception:
                pass
            try:
                from apps.calendar_engine.models import CalendarEvent
                remaining = CalendarEvent.objects.filter(
                    title__icontains='Approve Payroll',
                ).count()
                self.stdout.write(f'Remaining events: {remaining}')
            except Exception:
                pass

        # ── Summary ──────────────────────────────────────────────
        self.stdout.write(f'\n=== Summary ({mode}) ===')
        self.stdout.write(f'Tasks:  {task_count}')
        self.stdout.write(f'Events: {event_count}')
        self.stdout.write(f'Rules:  {rule_count}')

        if not execute:
            self.stdout.write(self.style.WARNING(
                '\nThis was a dry run. Re-run with --execute to delete.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS('\nPurge complete.'))
