"""
Management command to clean up problematic recurring tasks for a specific user.

Usage:
    python manage.py cleanup_recurring_tasks heatherjenkins74@gmail.com --dry-run
    python manage.py cleanup_recurring_tasks heatherjenkins74@gmail.com --delete
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.users.models import User
from apps.life.models import Task


class Command(BaseCommand):
    help = 'Clean up recurring tasks for a specific user'

    def add_arguments(self, parser):
        parser.add_argument('email', type=str, help='User email address')
        parser.add_argument(
            '--delete',
            action='store_true',
            help='Actually delete the tasks (without this flag, just shows what would be deleted)',
        )
        parser.add_argument(
            '--all-recurring',
            action='store_true',
            help='Delete ALL recurring tasks, not just problematic ones',
        )

    def handle(self, *args, **options):
        email = options['email']
        delete = options['delete']
        all_recurring = options['all_recurring']

        # Find user
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'User not found: {email}'))
            return

        self.stdout.write(f'Found user: {user.email} (ID: {user.id})')

        today = timezone.now().date()

        if all_recurring:
            # Delete ALL recurring tasks
            tasks_to_delete = Task.objects.filter(user=user, is_recurring=True)
            self.stdout.write(f'\nFound {tasks_to_delete.count()} total recurring tasks')
        else:
            # Find problematic recurring tasks:
            # 1. Incomplete recurring tasks with due dates in the past
            # 2. Multiple instances of the same recurring task
            tasks_to_delete = Task.objects.filter(
                user=user,
                is_recurring=True,
                is_completed=False,
                due_date__lt=today,
            )
            self.stdout.write(f'\nFound {tasks_to_delete.count()} incomplete past-due recurring tasks')

        # Show them
        for task in tasks_to_delete.order_by('due_date')[:50]:
            status = 'COMPLETED' if task.is_completed else 'INCOMPLETE'
            self.stdout.write(
                f'  - ID:{task.id} | {task.title[:40]:<40} | Due: {task.due_date} | {status} | Pattern: {task.recurrence_pattern}'
            )

        if tasks_to_delete.count() > 50:
            self.stdout.write(f'  ... and {tasks_to_delete.count() - 50} more')

        if delete:
            count = tasks_to_delete.count()
            # Use hard delete since these are problematic
            tasks_to_delete.delete()
            self.stdout.write(self.style.SUCCESS(f'\nDeleted {count} tasks'))
        else:
            self.stdout.write(self.style.WARNING(
                f'\nDry run - no tasks deleted. Use --delete to actually delete.'
            ))
