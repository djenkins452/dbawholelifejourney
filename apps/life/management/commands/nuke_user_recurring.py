"""
Management command to completely remove ALL recurring tasks for a user.

This is a NUCLEAR option - it hard deletes ALL Tasks where is_recurring=True.

Usage:
    # Dry run first (ALWAYS do this first)
    python manage.py nuke_user_recurring heatherjenkins74@gmail.com

    # Actually delete (requires explicit confirmation)
    python manage.py nuke_user_recurring heatherjenkins74@gmail.com --confirm-delete

    # Also include soft-deleted items
    python manage.py nuke_user_recurring heatherjenkins74@gmail.com --include-deleted --confirm-delete
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.users.models import User
from apps.life.models import Task


class Command(BaseCommand):
    help = 'NUCLEAR: Delete ALL recurring tasks for a user'

    def add_arguments(self, parser):
        parser.add_argument('email', type=str, help='User email address')
        parser.add_argument(
            '--confirm-delete',
            action='store_true',
            help='Actually delete (without this flag, just shows what would be deleted)',
        )
        parser.add_argument(
            '--include-deleted',
            action='store_true',
            help='Also include soft-deleted items in the cleanup',
        )

    def handle(self, *args, **options):
        email = options['email']
        confirm_delete = options['confirm_delete']
        include_deleted = options['include_deleted']

        # Find user
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'User not found: {email}'))
            return

        self.stdout.write(self.style.WARNING('=' * 70))
        self.stdout.write(self.style.WARNING('NUCLEAR RECURRING TASK CLEANUP'))
        self.stdout.write(self.style.WARNING('=' * 70))
        self.stdout.write(f'User: {user.email} (ID: {user.id})')
        self.stdout.write(f'Include soft-deleted: {include_deleted}')
        self.stdout.write('')

        today = timezone.now().date()

        # Base queryset - use all_objects to bypass soft delete manager if needed
        if include_deleted:
            task_qs = Task.all_objects.filter(user=user)
        else:
            task_qs = Task.objects.filter(user=user)

        # Find all recurring tasks
        recurring_tasks = task_qs.filter(is_recurring=True)
        count = recurring_tasks.count()

        self.stdout.write(f'Found {count} recurring tasks')
        self.stdout.write('')

        # Show all of them
        for task in recurring_tasks.order_by('due_date'):
            status = 'DONE' if task.is_completed else 'TODO'
            deleted = ' [SOFT-DELETED]' if task.deleted_at else ''
            overdue = ' [OVERDUE]' if task.due_date and task.due_date < today and not task.is_completed else ''
            self.stdout.write(
                f'  ID:{task.id:>5} | {task.title[:40]:<40} | Due: {task.due_date} | {status}{deleted}{overdue}'
            )

        self.stdout.write('')
        self.stdout.write(self.style.WARNING(f'TOTAL TO DELETE: {count}'))
        self.stdout.write('')

        if count == 0:
            self.stdout.write(self.style.SUCCESS('Nothing to delete!'))
            return

        if confirm_delete:
            # Hard delete
            deleted_result = recurring_tasks.delete()
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('=' * 70))
            self.stdout.write(self.style.SUCCESS(f'DELETED {count} recurring tasks for {email}'))
            self.stdout.write(self.style.SUCCESS('=' * 70))
            self.stdout.write('')
            self.stdout.write('User can now re-create recurring tasks from scratch.')
        else:
            self.stdout.write(self.style.ERROR('DRY RUN - Nothing deleted'))
            self.stdout.write('')
            self.stdout.write('To actually delete, run:')
            self.stdout.write(self.style.WARNING(
                f'  python manage.py nuke_user_recurring {email} --confirm-delete'
            ))
            if not include_deleted:
                self.stdout.write('')
                self.stdout.write('To also include soft-deleted items:')
                self.stdout.write(self.style.WARNING(
                    f'  python manage.py nuke_user_recurring {email} --include-deleted --confirm-delete'
                ))
