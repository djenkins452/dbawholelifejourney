"""
Management command to load all initial/system data.

This command loads fixtures and populates reference data tables.
It's safe to run multiple times - uses update_or_create patterns.

Usage: python manage.py load_initial_data
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Load all initial system data (fixtures and reference data)'

    def handle(self, *args, **options):
        self.stdout.write('Loading initial system data...\n')

        # Load fixtures (Django finds them by name in app fixtures directories)
        fixtures = [
            'categories',
            'encouragements',
            'scripture',
            'prompts',
            'coaching_styles',
        ]

        for fixture in fixtures:
            try:
                self.stdout.write(f'  Loading {fixture}...')
                call_command('loaddata', fixture, verbosity=0)
                self.stdout.write(self.style.SUCCESS(' OK'))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f' Skipped ({e})'))

        # Run data population commands
        commands = [
            'populate_choices',
            'populate_themes',
            'setup_purpose_defaults',
        ]

        for cmd in commands:
            try:
                self.stdout.write(f'  Running {cmd}...')
                call_command(cmd, verbosity=0)
                self.stdout.write(self.style.SUCCESS(' OK'))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f' Skipped ({e})'))

        self.stdout.write(self.style.SUCCESS('\nInitial data loading complete!'))
