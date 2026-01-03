"""
Management command to load all initial/system data.

This command loads fixtures and populates reference data tables.
It's safe to run multiple times - uses update_or_create patterns.

Usage: python manage.py load_initial_data
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Load all initial system data (fixtures and reference data)'

    def _fix_finance_budget_status(self):
        """
        Fix missing status column in finance_budget table.

        This is a workaround for a migration state issue where migration 0005
        was recorded as applied but the column was never created.

        See CLAUDE.md "Railway Nixpacks Caching Issue" for why this is here.
        """
        with connection.cursor() as cursor:
            if connection.vendor == 'postgresql':
                # Check if finance_budget table exists (with explicit schema)
                cursor.execute("""
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = 'finance_budget'
                """)
                if cursor.fetchone() is None:
                    self.stdout.write('  finance_budget table does not exist yet, skipping fix')
                    return

                # Check if status column exists (with explicit schema)
                cursor.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'finance_budget'
                      AND column_name = 'status'
                """)
                if cursor.fetchone() is None:
                    self.stdout.write('  Adding missing status column to finance_budget...')
                    cursor.execute("""
                        ALTER TABLE finance_budget
                        ADD COLUMN status varchar(10) NOT NULL DEFAULT 'active'
                    """)
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS finance_budget_status_idx
                        ON finance_budget (status)
                    """)
                    self.stdout.write(self.style.SUCCESS(' FIXED!'))
                else:
                    self.stdout.write('  finance_budget.status column exists')

    def handle(self, *args, **options):
        self.stdout.write('Loading initial system data...\n')

        # Fix finance_budget status column (Railway workaround)
        try:
            self.stdout.write('  Checking finance_budget.status...')
            self._fix_finance_budget_status()
        except Exception as e:
            self.stdout.write(self.style.WARNING(f' Error: {e}'))

        # Load fixtures (Django finds them by name in app fixtures directories)
        fixtures = [
            'categories',
            'encouragements',
            'scripture',
            'prompts',
            'coaching_styles',
            'ai_prompt_configs',
            'help_topics',
            'admin_help_topics',
            'help_categories',
            'help_articles',
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
            'populate_exercises',
        ]

        for cmd in commands:
            try:
                self.stdout.write(f'  Running {cmd}...')
                call_command(cmd, verbosity=0)
                self.stdout.write(self.style.SUCCESS(' OK'))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f' Skipped ({e})'))

        # Load project blueprints (added here to work around Railway caching issue)
        # See CLAUDE.md "Railway Nixpacks Caching Issue" for why this is done here
        project_blueprints = [
            'project_blueprints/wlj_executable_work_orchestration.json',
            'project_blueprints/Goals_Habit_Matrix_Upgrade.json',
            'project_blueprints/WLJ_Secure_Signup_Anti_Fraud_System.json',
            'project_blueprints/WLJ_Finance_Module.json',
        ]
        for blueprint in project_blueprints:
            try:
                self.stdout.write(f'  Loading {blueprint}...')
                call_command(
                    'load_project_from_json',
                    blueprint,
                    verbosity=1
                )
                self.stdout.write(self.style.SUCCESS(' OK'))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f' Skipped ({e})'))

        self.stdout.write(self.style.SUCCESS('\nInitial data loading complete!'))
