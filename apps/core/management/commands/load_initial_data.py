# ==============================================================================
# File: apps/core/management/commands/load_initial_data.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Management command to load initial system data (one-time loads)
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-01-01
# Last Updated: 2026-01-03 (Added DataLoadConfig for one-time loading)
# ==============================================================================
"""
Management command to load all initial/system data.

This command loads fixtures and populates reference data tables.
Now uses DataLoadConfig to track which loaders have run, so data is only
loaded once (not on every deploy).

Use --force to reload all data regardless of DataLoadConfig status.
Use --reset=<loader_name> to reset a specific loader.

Usage:
    python manage.py load_initial_data          # Normal run (skips completed loaders)
    python manage.py load_initial_data --force  # Force reload all
    python manage.py load_initial_data --reset populate_choices  # Reset specific loader
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection


# Define all loaders with their metadata
FIXTURE_LOADERS = [
    {
        'name': 'categories',
        'display': 'Journal Categories',
        'description': 'Pre-defined categories for journal entries',
    },
    {
        'name': 'encouragements',
        'display': 'Dashboard Encouragements',
        'description': 'Encouraging messages shown on dashboard',
    },
    {
        'name': 'scripture',
        'display': 'Scripture Verses',
        'description': 'Bible verses for faith module',
    },
    {
        'name': 'prompts',
        'display': 'Journal Prompts',
        'description': 'Writing prompts for journal entries',
    },
    {
        'name': 'coaching_styles',
        'display': 'AI Coaching Styles',
        'description': 'Personality styles for AI coach',
    },
    {
        'name': 'ai_prompt_configs',
        'display': 'AI Prompt Configurations',
        'description': 'System prompts for AI features',
    },
    {
        'name': 'help_topics',
        'display': 'Help Topics',
        'description': 'User help documentation topics',
    },
    {
        'name': 'admin_help_topics',
        'display': 'Admin Help Topics',
        'description': 'Admin console help documentation',
    },
    {
        'name': 'help_categories',
        'display': 'Help Categories',
        'description': 'Categories for help articles',
    },
    {
        'name': 'help_articles',
        'display': 'Help Articles',
        'description': 'Full help documentation articles',
    },
]

COMMAND_LOADERS = [
    {
        'name': 'populate_choices',
        'display': 'Dropdown Choices (Moods, Milestones, etc.)',
        'description': 'Configurable dropdown options for forms',
    },
    {
        'name': 'populate_themes',
        'display': 'Color Themes',
        'description': 'Site color theme configurations',
    },
    {
        'name': 'setup_purpose_defaults',
        'display': 'Purpose Module Defaults',
        'description': 'Default data for purpose/goals module',
    },
    {
        'name': 'populate_exercises',
        'display': 'Exercise Library',
        'description': 'Pre-defined exercises for health module',
    },
]

BLUEPRINT_LOADERS = [
    {
        'name': 'wlj_executable_work_orchestration',
        'path': 'project_blueprints/wlj_executable_work_orchestration.json',
        'display': 'Executable Work Orchestration Project',
        'description': 'Admin project tasks for WLJ development',
    },
    {
        'name': 'goals_habit_matrix_upgrade',
        'path': 'project_blueprints/Goals_Habit_Matrix_Upgrade.json',
        'display': 'Goals & Habit Matrix Upgrade Project',
        'description': 'Goals and habits feature tasks',
    },
    {
        'name': 'secure_signup_anti_fraud',
        'path': 'project_blueprints/WLJ_Secure_Signup_Anti_Fraud_System.json',
        'display': 'Secure Signup Anti-Fraud Project',
        'description': 'Security and anti-fraud tasks',
    },
    {
        'name': 'finance_module',
        'path': 'project_blueprints/WLJ_Finance_Module.json',
        'display': 'Finance Module Project',
        'description': 'Finance tracking feature tasks',
    },
]


class Command(BaseCommand):
    help = 'Load all initial system data (fixtures and reference data)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force reload all data, ignoring DataLoadConfig status'
        )
        parser.add_argument(
            '--reset',
            type=str,
            help='Reset a specific loader by name (sets is_loaded=False)'
        )
        parser.add_argument(
            '--list',
            action='store_true',
            help='List all loaders and their current status'
        )

    def _get_data_load_config(self):
        """Import DataLoadConfig model (deferred to avoid import issues during migration)."""
        try:
            from apps.admin_console.models import DataLoadConfig
            return DataLoadConfig
        except Exception:
            return None

    def _is_loader_complete(self, DataLoadConfig, loader_name):
        """Check if a loader has already been run."""
        if DataLoadConfig is None:
            return False
        try:
            return DataLoadConfig.is_loader_complete(loader_name)
        except Exception:
            return False

    def _mark_loader_complete(self, DataLoadConfig, loader_name, display_name, loader_type, description=''):
        """Mark a loader as complete in DataLoadConfig."""
        if DataLoadConfig is None:
            return
        try:
            config = DataLoadConfig.register_loader(
                loader_name=loader_name,
                display_name=display_name,
                loader_type=loader_type,
                description=description,
            )
            config.mark_loaded(loaded_by='startup')
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  Could not update DataLoadConfig: {e}'))

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

    def _list_loaders(self, DataLoadConfig):
        """List all loaders and their current status."""
        self.stdout.write('\n=== Data Loaders Status ===\n')

        self.stdout.write(self.style.MIGRATE_HEADING('Fixtures:'))
        for loader in FIXTURE_LOADERS:
            status = '✓' if self._is_loader_complete(DataLoadConfig, loader['name']) else '○'
            self.stdout.write(f'  {status} {loader["name"]}: {loader["display"]}')

        self.stdout.write(self.style.MIGRATE_HEADING('\nCommands:'))
        for loader in COMMAND_LOADERS:
            status = '✓' if self._is_loader_complete(DataLoadConfig, loader['name']) else '○'
            self.stdout.write(f'  {status} {loader["name"]}: {loader["display"]}')

        self.stdout.write(self.style.MIGRATE_HEADING('\nBlueprints:'))
        for loader in BLUEPRINT_LOADERS:
            status = '✓' if self._is_loader_complete(DataLoadConfig, loader['name']) else '○'
            self.stdout.write(f'  {status} {loader["name"]}: {loader["display"]}')

        self.stdout.write('\n✓ = loaded, ○ = not loaded\n')

    def _reset_loader(self, DataLoadConfig, loader_name):
        """Reset a specific loader so it will run again."""
        if DataLoadConfig is None:
            self.stdout.write(self.style.ERROR('DataLoadConfig model not available'))
            return False
        try:
            config = DataLoadConfig.objects.get(loader_name=loader_name)
            config.reset()
            self.stdout.write(self.style.SUCCESS(f'Reset loader: {loader_name}'))
            return True
        except DataLoadConfig.DoesNotExist:
            self.stdout.write(self.style.WARNING(f'Loader not found: {loader_name}'))
            return False

    def handle(self, *args, **options):
        force = options.get('force', False)
        reset_loader = options.get('reset')
        list_loaders = options.get('list', False)

        DataLoadConfig = self._get_data_load_config()

        # Handle --list
        if list_loaders:
            self._list_loaders(DataLoadConfig)
            return

        # Handle --reset
        if reset_loader:
            self._reset_loader(DataLoadConfig, reset_loader)
            return

        if force:
            self.stdout.write(self.style.WARNING('Force mode: reloading all data...\n'))
        else:
            self.stdout.write('Loading initial system data (skipping already loaded)...\n')

        # Fix finance_budget status column (Railway workaround) - always runs
        try:
            self.stdout.write('  Checking finance_budget.status...')
            self._fix_finance_budget_status()
        except Exception as e:
            self.stdout.write(self.style.WARNING(f' Error: {e}'))

        # Load fixtures
        for loader in FIXTURE_LOADERS:
            loader_name = loader['name']

            # Check if already loaded (unless force mode)
            if not force and self._is_loader_complete(DataLoadConfig, loader_name):
                self.stdout.write(f'  {loader_name}: ' + self.style.SUCCESS('Already loaded, skipping'))
                continue

            try:
                self.stdout.write(f'  Loading {loader_name}...')
                call_command('loaddata', loader_name, verbosity=0)
                self.stdout.write(self.style.SUCCESS(' OK'))

                # Mark as complete
                self._mark_loader_complete(
                    DataLoadConfig, loader_name, loader['display'],
                    'fixture', loader.get('description', '')
                )
            except Exception as e:
                self.stdout.write(self.style.WARNING(f' Skipped ({e})'))

        # Run data population commands
        for loader in COMMAND_LOADERS:
            loader_name = loader['name']

            # Check if already loaded (unless force mode)
            if not force and self._is_loader_complete(DataLoadConfig, loader_name):
                self.stdout.write(f'  {loader_name}: ' + self.style.SUCCESS('Already loaded, skipping'))
                continue

            try:
                self.stdout.write(f'  Running {loader_name}...')
                call_command(loader_name, verbosity=0)
                self.stdout.write(self.style.SUCCESS(' OK'))

                # Mark as complete
                self._mark_loader_complete(
                    DataLoadConfig, loader_name, loader['display'],
                    'command', loader.get('description', '')
                )
            except Exception as e:
                self.stdout.write(self.style.WARNING(f' Skipped ({e})'))

        # Load project blueprints
        for loader in BLUEPRINT_LOADERS:
            loader_name = loader['name']

            # Check if already loaded (unless force mode)
            if not force and self._is_loader_complete(DataLoadConfig, loader_name):
                self.stdout.write(f'  {loader_name}: ' + self.style.SUCCESS('Already loaded, skipping'))
                continue

            try:
                self.stdout.write(f'  Loading {loader["path"]}...')
                call_command(
                    'load_project_from_json',
                    loader['path'],
                    verbosity=1
                )
                self.stdout.write(self.style.SUCCESS(' OK'))

                # Mark as complete
                self._mark_loader_complete(
                    DataLoadConfig, loader_name, loader['display'],
                    'blueprint', loader.get('description', '')
                )
            except Exception as e:
                self.stdout.write(self.style.WARNING(f' Skipped ({e})'))

        self.stdout.write(self.style.SUCCESS('\nInitial data loading complete!'))
