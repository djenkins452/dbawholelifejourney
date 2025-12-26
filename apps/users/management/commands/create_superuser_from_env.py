"""
Management command to create superuser from environment variables.

Usage: python manage.py create_superuser_from_env

Requires:
- DJANGO_SUPERUSER_EMAIL
- DJANGO_SUPERUSER_PASSWORD
"""
import os
from django.core.management.base import BaseCommand
from apps.users.models import User, UserPreferences


class Command(BaseCommand):
    help = 'Create superuser from DJANGO_SUPERUSER_EMAIL and DJANGO_SUPERUSER_PASSWORD env vars'

    def handle(self, *args, **options):
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL')
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')

        if not email or not password:
            self.stdout.write(
                self.style.WARNING(
                    'Skipping superuser creation: DJANGO_SUPERUSER_EMAIL or '
                    'DJANGO_SUPERUSER_PASSWORD not set'
                )
            )
            return

        # Check if user already exists
        if User.objects.filter(email=email).exists():
            self.stdout.write(
                self.style.SUCCESS(f'Superuser {email} already exists')
            )
            return

        # Create superuser
        user = User.objects.create_superuser(email=email, password=password)

        # Create preferences
        UserPreferences.objects.get_or_create(user=user)

        self.stdout.write(
            self.style.SUCCESS(f'Successfully created superuser: {email}')
        )
