"""
Management command to process recurring transactions.

This command should be run daily (ideally early morning) to:
1. Generate transactions for any recurring that is due
2. Send reminders for upcoming recurring transactions

Usage:
    python manage.py process_recurring_transactions
    python manage.py process_recurring_transactions --dry-run
    python manage.py process_recurring_transactions --user=123

Schedule via cron:
    0 6 * * * cd /app && python manage.py process_recurring_transactions
"""

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.utils import user_log_id

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process due recurring transactions and send reminders'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without making changes',
        )
        parser.add_argument(
            '--user',
            type=int,
            help='Only process for a specific user ID',
        )
        parser.add_argument(
            '--date',
            type=str,
            help='Process as if today is this date (YYYY-MM-DD format)',
        )

    def handle(self, *args, **options):
        from apps.finance.services.recurring import (
            RecurringTransactionService,
            process_recurring_transactions,
        )
        from apps.users.models import User

        dry_run = options['dry_run']
        user_id = options.get('user')
        date_str = options.get('date')

        # Determine the processing date
        if date_str:
            from datetime import datetime
            as_of_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            self.stdout.write(f'Processing as of date: {as_of_date}')
        else:
            as_of_date = timezone.now().date()

        self.stdout.write(self.style.NOTICE(
            f'Processing recurring transactions for {as_of_date}'
        ))

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes will be made'))

        # Get user filter
        user = None
        if user_id:
            try:
                user = User.objects.get(pk=user_id)
                self.stdout.write(f'Filtering to user: {user.email}')
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'User {user_id} not found'))
                return

        # Get due recurring transactions
        due_recurring = RecurringTransactionService.get_due_recurring_transactions(
            user=user, as_of_date=as_of_date
        )

        due_count = due_recurring.count()
        self.stdout.write(f'Found {due_count} recurring transaction(s) due')

        if due_count == 0:
            self.stdout.write(self.style.SUCCESS('Nothing to process'))
            return

        # List what will be processed
        for recurring in due_recurring:
            self.stdout.write(
                f'  - {recurring.name}: ${recurring.amount} '
                f'({recurring.user.email}) - due {recurring.next_due_date}'
            )

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'Would process {due_count} transaction(s) - dry run, skipping'
            ))
            return

        # Process the transactions
        if user:
            results = RecurringTransactionService.process_due_transactions(
                user=user, as_of_date=as_of_date
            )
        else:
            results = process_recurring_transactions()

        # Report results
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Created {results["created"]} transaction(s)'
        ))

        if results.get('errors'):
            self.stdout.write(self.style.ERROR(
                f'Errors: {len(results["errors"])}'
            ))
            for error in results['errors']:
                self.stdout.write(
                    f'  - {error["name"]} ({error["recurring_id"]}): {error["error"]}'
                )

        # Process reminders
        self.stdout.write('')
        self.stdout.write('Processing reminders...')
        self._process_reminders(user, as_of_date, dry_run)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Done!'))

    def _process_reminders(self, user, as_of_date, dry_run):
        """Send reminders for upcoming recurring transactions."""
        from apps.finance.services.recurring import RecurringTransactionService
        from apps.users.models import User

        if user:
            users = [user]
        else:
            users = User.objects.filter(is_active=True)

        total_reminders = 0

        for user_obj in users:
            reminders = RecurringTransactionService.get_reminders_for_date(
                user_obj, reminder_date=as_of_date
            )

            if reminders:
                self.stdout.write(
                    f'  {user_obj.email}: {len(reminders)} reminder(s)'
                )

                if not dry_run:
                    # Send reminder (for now, just log it)
                    for recurring in reminders:
                        logger.info(
                            f'Reminder: {recurring.name} due on '
                            f'{recurring.next_due_date} for {user_log_id(user_obj)}'
                        )
                        # TODO: Integrate with SMS/email reminder system
                        total_reminders += 1

        if total_reminders:
            self.stdout.write(f'  Sent {total_reminders} reminder(s)')
        else:
            self.stdout.write('  No reminders to send')
