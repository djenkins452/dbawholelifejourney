"""
Management command to process recurring tasks.

Run daily via cron:
    python manage.py process_recurring_tasks
"""

from django.core.management.base import BaseCommand
from apps.life.services.recurrence import process_overdue_recurring_tasks


class Command(BaseCommand):
    help = 'Process completed recurring tasks and create next occurrences'
    
    def handle(self, *args, **options):
        created_count = process_overdue_recurring_tasks()
        
        if created_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f'Created {created_count} new recurring task(s)')
            )
        else:
            self.stdout.write('No new recurring tasks needed')
