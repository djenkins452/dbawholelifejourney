# ==============================================================================
# File: apps/core/management/commands/load_initial_data.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Management command to load initial system data (one-time loads)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2025-01-01
# Last Updated: 2026-01-11 (Added migration dependency fix for stale migration)
# ==============================================================================
"""
Management command to load all initial/system data.

This command loads fixtures and populates reference data tables.
Uses DataLoadConfig to track which loaders have run, so data is only
loaded once (not on every deploy).

CONSOLIDATES these Procfile commands into one:
- load_initial_data (original fixtures/commands)
- reload_help_content (now one-time only)
- load_danny_workout_templates (user-specific workout templates)
- load_reading_plans (Bible reading plans)
- load_phase1_data (project phases 1-20)
- load_project_from_json (project blueprints)

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
        'name': 'values_guardrail_patterns',
        'display': 'Values Guardrail Patterns',
        'description': 'Content filtering patterns for AI safety (Task 9.3)',
    },
    {
        'name': 'values_redirect_suggestions',
        'display': 'Values Redirect Suggestions',
        'description': 'Module-specific redirect messages for AI (Task 9.3)',
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
        'name': 'help_topics_brain_training',
        'display': 'Brain Training Help Topics',
        'description': 'Help topics for cognitive health brain training exercises',
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
    {
        'name': 'teaching_destinations',
        'display': 'Teaching Tool Destinations',
        'description': 'Navigation destinations for teaching tool (where do I...)',
    },
    {
        'name': 'blind_spots_reading_plan',
        'display': 'Blind Spots Reading Plan (Week 2)',
        'description': 'Surrendering My Blind Spots 6-day reading plan with assessment',
    },
    {
        'name': 'blind_spots_week1_reading_plan',
        'display': 'Blind Spots Reading Plan (Week 1)',
        'description': 'Opening Your Eyes 6-day reading plan with self-assessment',
    },
    {
        'name': 'blind_spots_week3_reading_plan',
        'display': 'Blind Spots Reading Plan (Week 3)',
        'description': 'Self-Centeredness 6-day reading plan with assessment',
    },
    {
        'name': 'email_notification_templates',
        'display': 'Email Notification Templates',
        'description': 'Admin-editable templates for notification emails',
    },
    {
        'name': 'games',
        'display': 'Brain Training Exercises',
        'description': 'Exercise catalog for Brain Training module',
        'app': 'brain_training',
    },
    {
        'name': 'disposable_email_domains',
        'display': 'Disposable Email Domains',
        'description': 'Blocklist of temporary/disposable email domains',
        'app': 'users',
    },
    {
        'name': 'release_notes',
        'display': 'What\'s New Release Notes',
        'description': 'Release notes shown in the What\'s New popup',
    },
    # NOTE: module_definitions removed - now handled by migration 0052_fix_module_route_names
    # Loading via fixture causes UNIQUE constraint errors since migration already creates the data
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
    {
        'name': 'load_reading_plans',
        'display': 'Bible Reading Plans',
        'description': 'Bible reading plan templates',
    },
    {
        'name': 'load_gospel_plans',
        'display': 'Gospel Reading Plans',
        'description': 'The Gospels series (Matthew, Mark, Luke, John)',
    },
    {
        'name': 'load_jonah_plan',
        'display': 'Jonah Reading Plan',
        'description': 'Jonah: The Reluctant Prophet (People of the Bible series)',
    },
    {
        'name': 'load_ruth_plan',
        'display': 'Ruth Reading Plan',
        'description': 'Ruth & Naomi: Loyalty and Redemption (People of the Bible series)',
    },
    {
        'name': 'load_noah_plan',
        'display': 'Noah Reading Plan',
        'description': 'Noah: Righteous in His Generation (People of the Bible series)',
    },
    {
        'name': 'load_daniel_plan',
        'display': 'Daniel Reading Plan',
        'description': 'Daniel: Faith in Exile (People of the Bible series)',
    },
    {
        'name': 'load_ten_commandments_plan',
        'display': 'Ten Commandments Reading Plan',
        'description': 'The Ten Commandments (Bible Foundations series)',
    },
    {
        'name': 'load_phase1_data',
        'display': 'Project Phases (1-20)',
        'description': 'AdminProjectPhase records for task management',
    },
    {
        'name': 'load_danny_workout_templates',
        'display': 'Danny Workout Templates',
        'description': 'Workout templates for dannyjenkins71@gmail.com',
    },
    {
        'name': 'setup_app_review_account',
        'display': 'App Review Demo Account',
        'description': 'Apple App Store review demo account (appreview@wholelifejourney.com)',
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

    def _fix_stale_migration_records(self, verbosity=1):
        """
        Fix stale/broken migration records in django_migrations table.

        This fixes migration dependency issues where a migration file in production
        references a parent migration that no longer exists. This can happen when:
        - A migration was created with wrong dependencies during development
        - Code was deployed from a branch with divergent migration history
        - Migration files were deleted/renamed but records remain in DB

        The fix removes stale records so Django can properly rebuild the migration graph.
        """
        with connection.cursor() as cursor:
            if connection.vendor != 'postgresql':
                return  # Only needed for production PostgreSQL

            # Fix: core.0012_feature_request_detection_release_note depends on
            # core.0011_add_sms_models which never existed. The correct migration is
            # core.0038_feature_request_detection_release_note.
            stale_migrations = [
                ('core', '0012_feature_request_detection_release_note'),
                ('core', '0011_add_sms_models'),
            ]

            for app, name in stale_migrations:
                cursor.execute(
                    "SELECT id FROM django_migrations WHERE app = %s AND name = %s",
                    [app, name]
                )
                row = cursor.fetchone()
                if row:
                    if verbosity >= 1:
                        self.stdout.write(f'  Removing stale migration record: {app}.{name}')
                    cursor.execute(
                        "DELETE FROM django_migrations WHERE app = %s AND name = %s",
                        [app, name]
                    )
                    if verbosity >= 1:
                        self.stdout.write(self.style.SUCCESS(' FIXED!'))

    def _fix_finance_budget_status(self, verbosity=1):
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
                    return  # Table doesn't exist yet, nothing to fix

                # Check if status column exists (with explicit schema)
                cursor.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'finance_budget'
                      AND column_name = 'status'
                """)
                if cursor.fetchone() is None:
                    if verbosity >= 1:
                        self.stdout.write('  Adding missing status column to finance_budget...')
                    cursor.execute("""
                        ALTER TABLE finance_budget
                        ADD COLUMN status varchar(10) NOT NULL DEFAULT 'active'
                    """)
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS finance_budget_status_idx
                        ON finance_budget (status)
                    """)
                    if verbosity >= 1:
                        self.stdout.write(self.style.SUCCESS(' FIXED!'))

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
        verbosity = options.get('verbosity', 1)

        DataLoadConfig = self._get_data_load_config()

        # Handle --list
        if list_loaders:
            self._list_loaders(DataLoadConfig)
            return

        # Handle --reset
        if reset_loader:
            self._reset_loader(DataLoadConfig, reset_loader)
            return

        if force and verbosity >= 1:
            self.stdout.write(self.style.WARNING('Force mode: reloading all data...\n'))

        # Fix stale migration records FIRST (before any other DB operations)
        # This fixes NodeNotFoundError for migrations with broken dependencies
        try:
            self._fix_stale_migration_records(verbosity)
        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.WARNING(f'stale migration fix error: {e}'))

        # Fix finance_budget status column (Railway workaround) - always runs silently
        try:
            self._fix_finance_budget_status(verbosity)
        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.WARNING(f'finance_budget fix error: {e}'))

        # Track what actually loaded for summary
        loaded_count = 0
        skipped_count = 0

        # Load fixtures
        for loader in FIXTURE_LOADERS:
            loader_name = loader['name']

            # Check if already loaded (unless force mode)
            if not force and self._is_loader_complete(DataLoadConfig, loader_name):
                skipped_count += 1
                continue

            try:
                if verbosity >= 2:
                    self.stdout.write(f'  Loading {loader_name}...', ending='')
                call_command('loaddata', loader_name, verbosity=0)
                if verbosity >= 2:
                    self.stdout.write(self.style.SUCCESS(' OK'))
                loaded_count += 1

                # Mark as complete
                self._mark_loader_complete(
                    DataLoadConfig, loader_name, loader['display'],
                    'fixture', loader.get('description', '')
                )
            except Exception as e:
                if verbosity >= 1:
                    self.stdout.write(self.style.WARNING(f'  {loader_name}: Skipped ({e})'))

        # Run data population commands
        for loader in COMMAND_LOADERS:
            loader_name = loader['name']

            # Check if already loaded (unless force mode)
            if not force and self._is_loader_complete(DataLoadConfig, loader_name):
                skipped_count += 1
                continue

            try:
                if verbosity >= 2:
                    self.stdout.write(f'  Running {loader_name}...', ending='')
                call_command(loader_name, verbosity=0)
                if verbosity >= 2:
                    self.stdout.write(self.style.SUCCESS(' OK'))
                loaded_count += 1

                # Mark as complete
                self._mark_loader_complete(
                    DataLoadConfig, loader_name, loader['display'],
                    'command', loader.get('description', '')
                )
            except Exception as e:
                if verbosity >= 1:
                    self.stdout.write(self.style.WARNING(f'  {loader_name}: Skipped ({e})'))

        # Load project blueprints
        for loader in BLUEPRINT_LOADERS:
            loader_name = loader['name']

            # Check if already loaded (unless force mode)
            if not force and self._is_loader_complete(DataLoadConfig, loader_name):
                skipped_count += 1
                continue

            try:
                if verbosity >= 2:
                    self.stdout.write(f'  Loading blueprint {loader_name}...', ending='')
                call_command(
                    'load_project_from_json',
                    loader['path'],
                    verbosity=0
                )
                if verbosity >= 2:
                    self.stdout.write(self.style.SUCCESS(' OK'))
                loaded_count += 1

                # Mark as complete
                self._mark_loader_complete(
                    DataLoadConfig, loader_name, loader['display'],
                    'blueprint', loader.get('description', '')
                )
            except Exception as e:
                if verbosity >= 1:
                    self.stdout.write(self.style.WARNING(f'  {loader_name}: Skipped ({e})'))

        # Send one-time test email to verify SMTP configuration
        self._send_smtp_test_email(DataLoadConfig, force, verbosity)

        # One-time cleanup: remove problematic recurring tasks for specific users
        self._cleanup_heather_recurring_tasks(DataLoadConfig, force, verbosity)
        self._cleanup_danny_recurring_tasks(DataLoadConfig, force, verbosity)

        # One-time: AGGRESSIVE cleanup of ALL recurring tasks for Heather (Feb 2026)
        self._nuke_heather_recurring_tasks(DataLoadConfig, force, verbosity)

        # One-time: Disable Finance module for all users (Coming Soon)
        self._disable_finance_module(DataLoadConfig, force, verbosity)

        # One-time: Add missing Task List help topic
        self._add_task_list_help_topic(DataLoadConfig, force, verbosity)

        # One-time: Reset blind_spots_week3 loader to reload with fixed PKs
        self._reset_blind_spots_week3_loader(DataLoadConfig, force, verbosity)

        # One-time: Reset blind_spots_week3 loader to reload with fixed assessment questions
        self._reset_blind_spots_week3_assessment(DataLoadConfig, force, verbosity)

        # One-time: Reset blind_spots_week3 loader to reload with True/False radio buttons
        self._reset_blind_spots_week3_truefalse(DataLoadConfig, force, verbosity)

        # One-time: Disable notifications for app review account (not a real mailbox)
        self._disable_appreview_notifications(DataLoadConfig, force, verbosity)

        # One-time: Clean up orphaned medical data for Danny (fix re-import after delete bug)
        self._cleanup_danny_medical_data(DataLoadConfig, force, verbosity)

        # One-time: Fix lab result dates (re-parse from extracted text)
        self._fix_lab_result_dates(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes loader to reload with Feb 2026 entries
        self._reset_release_notes_loader(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for Body Composition + Insight Engine
        self._reset_body_composition_fixtures(DataLoadConfig, force, verbosity)

        # Only output summary if something loaded or if verbose
        if verbosity >= 1 and loaded_count > 0:
            self.stdout.write(self.style.SUCCESS(f'Initial data: loaded {loaded_count} items'))
        elif verbosity >= 2:
            self.stdout.write(f'Initial data: {skipped_count} items already loaded')

    def _send_smtp_test_email(self, DataLoadConfig, force=False, verbosity=1):
        """
        Send a one-time test email to verify SMTP configuration.

        Only runs once (tracked via DataLoadConfig) unless force=True.
        Sends to ADMIN_EMAIL to verify email delivery works.
        """
        loader_name = 'smtp_test_email_admin'

        # Check if already sent (unless force mode)
        if not force and self._is_loader_complete(DataLoadConfig, loader_name):
            return  # Already sent, skip silently

        from django.conf import settings
        from django.core.mail import send_mail
        from django.utils import timezone

        # Only send if SMTP is configured (not console backend)
        if settings.DEBUG or 'console' in getattr(settings, 'EMAIL_BACKEND', '').lower():
            return  # Console backend, skip silently

        # Check if credentials are configured
        if not getattr(settings, 'EMAIL_HOST_USER', '') or not getattr(settings, 'EMAIL_HOST_PASSWORD', ''):
            return  # No credentials, skip silently

        try:
            if verbosity >= 2:
                self.stdout.write('  Sending SMTP test email...', ending='')

            recipient = 'admin@wholelifejourney.com'
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'admin@wholelifejourney.com')
            timestamp = timezone.now().strftime("%Y-%m-%d %H:%M:%S %Z")

            result = send_mail(
                subject='WLJ SMTP Test - Configuration Verified',
                message=f"""
This is an automated test email from Whole Life Journey.

Sent at: {timestamp}
From: {from_email}
Backend: {settings.EMAIL_BACKEND}
SMTP Host: {getattr(settings, 'EMAIL_HOST', 'N/A')}:{getattr(settings, 'EMAIL_PORT', 'N/A')}

If you received this email, your SMTP configuration is working correctly!

This test email is sent once on first deploy after SMTP is configured.
""",
                from_email=from_email,
                recipient_list=[recipient],
                fail_silently=False,
            )

            if result == 1:
                if verbosity >= 1:
                    self.stdout.write(self.style.SUCCESS(f'SMTP test email sent to {recipient}'))
                # Mark as complete so it doesn't send again
                self._mark_loader_complete(
                    DataLoadConfig, loader_name, 'SMTP Test Email',
                    'command', 'One-time SMTP configuration verification email'
                )
            elif verbosity >= 1:
                self.stdout.write(self.style.WARNING(f'SMTP test: send_mail returned {result}'))

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'SMTP test FAILED: {e}'))

    def _cleanup_heather_recurring_tasks(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time cleanup of problematic recurring tasks for heatherjenkins74@gmail.com.

        This user had recurring tasks that got corrupted/duplicated due to an earlier bug.
        This cleanup removes all incomplete past-due recurring tasks for this user.
        Only runs once (tracked via DataLoadConfig) unless force=True.
        """
        loader_name = 'cleanup_heather_recurring_tasks_2026_01'

        # Check if already run (unless force mode)
        if not force and self._is_loader_complete(DataLoadConfig, loader_name):
            return  # Already cleaned up, skip silently

        try:
            from django.utils import timezone
            from apps.users.models import User
            from apps.life.models import Task

            # Find the user
            try:
                user = User.objects.get(email='heatherjenkins74@gmail.com')
            except User.DoesNotExist:
                return  # User doesn't exist, skip silently

            today = timezone.now().date()

            # Find incomplete past-due recurring tasks
            tasks_to_delete = Task.objects.filter(
                user=user,
                is_recurring=True,
                is_completed=False,
                due_date__lt=today,
            )

            count = tasks_to_delete.count()
            if count > 0:
                if verbosity >= 1:
                    self.stdout.write(f'  Cleaning up {count} recurring tasks for heatherjenkins74@gmail.com...', ending='')

                # Delete them (hard delete since these are problematic)
                tasks_to_delete.delete()

                if verbosity >= 1:
                    self.stdout.write(self.style.SUCCESS(' DONE'))

            # Mark as complete so it doesn't run again
            self._mark_loader_complete(
                DataLoadConfig, loader_name, 'Heather Recurring Tasks Cleanup (Jan 2026)',
                'command', 'One-time cleanup of problematic recurring tasks for heatherjenkins74@gmail.com'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Recurring tasks cleanup FAILED: {e}'))

    def _cleanup_danny_recurring_tasks(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time cleanup of ALL recurring tasks for dannyjenkins71@gmail.com.

        This user had recurring tasks that got corrupted/duplicated due to an earlier bug.
        This cleanup removes ALL recurring tasks (not just past-due) and any tasks
        spawned from them.
        Only runs once (tracked via DataLoadConfig) unless force=True.
        """
        loader_name = 'cleanup_danny_recurring_tasks_2026_01'

        # Check if already run (unless force mode)
        if not force and self._is_loader_complete(DataLoadConfig, loader_name):
            return  # Already cleaned up, skip silently

        try:
            from apps.users.models import User
            from apps.life.models import Task

            # Find the user
            try:
                user = User.objects.get(email='dannyjenkins71@gmail.com')
            except User.DoesNotExist:
                return  # User doesn't exist, skip silently

            # Get all recurring tasks for this user
            recurring_tasks = Task.objects.filter(user=user, is_recurring=True)
            recurring_titles = list(recurring_tasks.values_list('title', flat=True))
            recurring_count = recurring_tasks.count()

            # Find all tasks matching recurring task titles (spawned instances)
            # These are the "scheduled" tasks created from recurring patterns
            if recurring_titles:
                spawned_tasks = Task.objects.filter(
                    user=user,
                    title__in=recurring_titles,
                    is_recurring=False,
                    is_completed=False,
                )
                spawned_count = spawned_tasks.count()

                if spawned_count > 0:
                    if verbosity >= 1:
                        self.stdout.write(f'  Deleting {spawned_count} spawned tasks for dannyjenkins71@gmail.com...')
                    spawned_tasks.delete()

            if recurring_count > 0:
                if verbosity >= 1:
                    self.stdout.write(f'  Deleting {recurring_count} recurring tasks for dannyjenkins71@gmail.com...')
                recurring_tasks.delete()

            total = recurring_count + (spawned_count if recurring_titles else 0)
            if total > 0 and verbosity >= 1:
                self.stdout.write(self.style.SUCCESS(f'  Cleaned up {total} total tasks for dannyjenkins71@gmail.com'))

            # Mark as complete so it doesn't run again
            self._mark_loader_complete(
                DataLoadConfig, loader_name, 'Danny Recurring Tasks Cleanup (Jan 2026)',
                'command', 'One-time cleanup of problematic recurring tasks for dannyjenkins71@gmail.com'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Danny recurring tasks cleanup FAILED: {e}'))

    def _nuke_heather_recurring_tasks(self, DataLoadConfig, force=False, verbosity=1):
        """
        AGGRESSIVE one-time cleanup of ALL recurring tasks for heatherjenkins74@gmail.com.

        Previous cleanup (Jan 2026) only deleted incomplete past-due recurring tasks
        using Task.objects (which excludes soft-deleted). This one:
        - Uses all_objects to catch soft-deleted tasks
        - Deletes ALL recurring tasks regardless of status, completion, or date
        - Also deletes spawned non-recurring tasks that share titles with recurring ones
        - Hard-deletes everything so nothing can come back
        """
        loader_name = 'nuke_heather_recurring_tasks_2026_02'

        if not force and self._is_loader_complete(DataLoadConfig, loader_name):
            return

        try:
            from apps.users.models import User
            from apps.life.models import Task

            try:
                user = User.objects.get(email='heatherjenkins74@gmail.com')
            except User.DoesNotExist:
                return  # User doesn't exist, skip silently

            # Get ALL recurring tasks (active, archived, soft-deleted - everything)
            all_recurring = Task.all_objects.filter(user=user, is_recurring=True)
            recurring_titles = list(all_recurring.values_list('title', flat=True).distinct())
            recurring_count = all_recurring.count()

            # Find spawned non-recurring tasks that share titles with recurring ones
            spawned_count = 0
            if recurring_titles:
                spawned_tasks = Task.all_objects.filter(
                    user=user,
                    title__in=recurring_titles,
                    is_recurring=False,
                    is_completed=False,
                )
                spawned_count = spawned_tasks.count()
                if spawned_count > 0:
                    if verbosity >= 1:
                        self.stdout.write(
                            f'  Hard-deleting {spawned_count} spawned tasks '
                            f'for heatherjenkins74@gmail.com...'
                        )
                    spawned_tasks.delete()

            if recurring_count > 0:
                if verbosity >= 1:
                    titles_preview = ', '.join(recurring_titles[:5])
                    self.stdout.write(
                        f'  Hard-deleting {recurring_count} recurring tasks '
                        f'for heatherjenkins74@gmail.com: {titles_preview}...'
                    )
                all_recurring.delete()

            total = recurring_count + spawned_count
            if total > 0 and verbosity >= 1:
                self.stdout.write(self.style.SUCCESS(
                    f'  NUKED {total} total recurring/spawned tasks for heatherjenkins74@gmail.com'
                ))
            elif verbosity >= 1:
                self.stdout.write('  No recurring tasks found for heatherjenkins74@gmail.com')

            self._mark_loader_complete(
                DataLoadConfig, loader_name,
                'Nuke Heather Recurring Tasks (Feb 2026)',
                'command',
                'Aggressive cleanup: hard-delete ALL recurring tasks + spawned instances'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(
                    f'Nuke heather recurring tasks FAILED: {e}'
                ))

    def _disable_finance_module(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time disable of Finance module for all users.

        Finance module is being moved to "Coming Soon" status.
        This sets finances_enabled=False for all existing users.
        Only runs once (tracked via DataLoadConfig) unless force=True.
        """
        loader_name = 'disable_finance_module_2026_01'

        # Check if already run (unless force mode)
        if not force and self._is_loader_complete(DataLoadConfig, loader_name):
            return  # Already done, skip silently

        try:
            from apps.users.models import UserPreferences

            # Update all users with Finance enabled
            updated = UserPreferences.objects.filter(finances_enabled=True).update(finances_enabled=False)

            if updated > 0:
                if verbosity >= 1:
                    self.stdout.write(f'  Disabled Finance module for {updated} users (Coming Soon)')

            # Mark as complete so it doesn't run again
            self._mark_loader_complete(
                DataLoadConfig, loader_name, 'Disable Finance Module (Jan 2026)',
                'command', 'One-time disable of Finance module - moved to Coming Soon status'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Finance module disable FAILED: {e}'))

    def _add_task_list_help_topic(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time add of ADMIN_CONSOLE_TASKS help topic.

        This topic was missing from HelpTopic (only existed in AdminHelpTopic),
        causing the Task List page to show generic Admin Console help.
        Only runs once (tracked via DataLoadConfig) unless force=True.
        """
        loader_name = 'add_task_list_help_topic_2026_01'

        # Check if already run (unless force mode)
        if not force and self._is_loader_complete(DataLoadConfig, loader_name):
            return  # Already done, skip silently

        try:
            from apps.help.models import HelpTopic

            # Check if topic already exists
            if HelpTopic.objects.filter(context_id='ADMIN_CONSOLE_TASKS').exists():
                # Already exists, just mark complete
                self._mark_loader_complete(
                    DataLoadConfig, loader_name, 'Add Task List Help Topic (Jan 2026)',
                    'command', 'One-time add of ADMIN_CONSOLE_TASKS help topic'
                )
                return

            # Create the help topic
            HelpTopic.objects.create(
                context_id='ADMIN_CONSOLE_TASKS',
                help_id='admin-console-tasks',
                title='Task List',
                description='View and manage all project tasks.',
                content="""## Task List

This page shows all tasks across all projects with filtering options.

### Filtering Tasks

Use the filter controls to narrow the list:
- **Phase** - Filter by phase number
- **Status** - Filter by task status (backlog, ready, in_progress, done, blocked)
- **Project** - Filter by project

### Task Status Workflow

1. **Backlog** - Task created, not ready for work
2. **Ready** - Task marked ready, available for Claude
3. **In Progress** - Claude is actively working on it
4. **Done** - Task completed successfully
5. **Blocked** - Task waiting on dependency or issue

### Mark Ready

For backlog tasks, use the **"Mark Ready"** button to make them available for Claude to execute.

### Inline Editing

Some fields can be edited inline:
- Status can be changed via dropdown
- Priority can be adjusted

### Sorting

Tasks are sorted by priority (ascending) then creation date.""",
                app_name='admin_console',
                order=5,
                is_active=True,
            )

            if verbosity >= 1:
                self.stdout.write(self.style.SUCCESS('  Added ADMIN_CONSOLE_TASKS help topic'))

            # Mark as complete so it doesn't run again
            self._mark_loader_complete(
                DataLoadConfig, loader_name, 'Add Task List Help Topic (Jan 2026)',
                'command', 'One-time add of ADMIN_CONSOLE_TASKS help topic'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Add Task List help topic FAILED: {e}'))

    def _reset_blind_spots_week3_loader(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset of blind_spots_week3_reading_plan loader.

        The initial fixture had PK conflicts. This resets the loader
        so it will reload with the fixed PKs (10003+).
        Only runs once (tracked via DataLoadConfig).
        """
        reset_tracker_name = 'reset_blind_spots_week3_2026_01_26'

        # Check if already done (unless force mode)
        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return  # Already reset, skip silently

        try:
            # Reset the fixture loader so it runs again
            fixture_loader_name = 'blind_spots_week3_reading_plan'
            try:
                config = DataLoadConfig.objects.get(loader_name=fixture_loader_name)
                config.reset()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset {fixture_loader_name} loader for reload')
            except DataLoadConfig.DoesNotExist:
                pass  # Loader not found, will load fresh

            # Mark this reset operation as complete
            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name, 'Reset Blind Spots Week 3 Loader',
                'command', 'One-time reset to reload fixture with fixed PKs'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset blind spots week3 FAILED: {e}'))

    def _reset_blind_spots_week3_assessment(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset of blind_spots_week3_reading_plan loader to reload with
        updated assessment questions (reflection-only, custom options).
        Only runs once (tracked via DataLoadConfig).
        """
        reset_tracker_name = 'reset_blind_spots_week3_assessment_2026_01_27'

        # Check if already done (unless force mode)
        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return  # Already reset, skip silently

        try:
            # Reset the fixture loader so it runs again
            fixture_loader_name = 'blind_spots_week3_reading_plan'
            try:
                config = DataLoadConfig.objects.get(loader_name=fixture_loader_name)
                config.reset()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset {fixture_loader_name} loader for assessment update')
            except DataLoadConfig.DoesNotExist:
                pass  # Loader not found, will load fresh

            # Mark this reset operation as complete
            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name, 'Reset Blind Spots Week 3 Assessment',
                'command', 'One-time reset to reload fixture with reflection-only assessment'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset blind spots week3 assessment FAILED: {e}'))

    def _reset_blind_spots_week3_truefalse(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset of blind_spots_week3_reading_plan loader to reload with
        True/False questions using radio buttons instead of Yes/No dropdowns.
        Only runs once (tracked via DataLoadConfig).
        """
        reset_tracker_name = 'reset_blind_spots_week3_truefalse_2026_01_27'

        # Check if already done (unless force mode)
        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return  # Already reset, skip silently

        try:
            # Reset the fixture loader so it runs again
            fixture_loader_name = 'blind_spots_week3_reading_plan'
            try:
                config = DataLoadConfig.objects.get(loader_name=fixture_loader_name)
                config.reset()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset {fixture_loader_name} loader for True/False radio buttons')
            except DataLoadConfig.DoesNotExist:
                pass  # Loader not found, will load fresh

            # Mark this reset operation as complete
            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name, 'Reset Blind Spots Week 3 True/False',
                'command', 'One-time reset to reload fixture with True/False radio buttons'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset blind spots week3 truefalse FAILED: {e}'))

    def _disable_appreview_notifications(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time disable of email/notifications for the app review account.

        appreview@wholelifejourney.com is not a real mailbox - it's only a demo
        login for Apple App Store reviewers. Sending digests to it causes errors.
        Only runs once (tracked via DataLoadConfig) unless force=True.
        """
        loader_name = 'disable_appreview_notifications_2026_02'

        if not force and self._is_loader_complete(DataLoadConfig, loader_name):
            return

        try:
            import os
            from apps.users.models import UserPreferences
            from django.contrib.auth import get_user_model
            User = get_user_model()

            email = os.environ.get('APP_REVIEW_EMAIL', 'appreview@wholelifejourney.com')
            try:
                user = User.objects.get(email=email)
                prefs = user.preferences
                prefs.email_notifications_enabled = False
                prefs.notifications_enabled = False
                prefs.save()
                if verbosity >= 1:
                    self.stdout.write(self.style.SUCCESS(
                        f'  Disabled notifications for app review account ({email})'
                    ))
            except User.DoesNotExist:
                if verbosity >= 1:
                    self.stdout.write(f'  App review account not found ({email}), skipping')

            self._mark_loader_complete(
                DataLoadConfig, loader_name, 'Disable App Review Notifications (Feb 2026)',
                'command', 'One-time disable of notifications for app review demo account'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Disable appreview notifications FAILED: {e}'))

    def _cleanup_danny_medical_data(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time cleanup of orphaned medical data for dannyjenkins71@gmail.com.

        Due to a bug in ImportDeleteView (not soft-deleting MedicalDocument),
        the user has orphaned records blocking re-import. This hard-deletes
        all medical data so they can start fresh.
        """
        loader_name = 'cleanup_danny_medical_data_2026_02_13'

        if not force and self._is_loader_complete(DataLoadConfig, loader_name):
            return

        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()

            email = 'dannyjenkins71@gmail.com'
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                if verbosity >= 1:
                    self.stdout.write(f'  User not found ({email}), skipping medical cleanup')
                self._mark_loader_complete(
                    DataLoadConfig, loader_name, 'Cleanup Danny Medical Data (Feb 2026)',
                    'command', 'User not found, skipped'
                )
                return

            from apps.medical.models import (
                ImportBatch, LabPanel, LabResult, MedicalAuditLog, MedicalDocument,
            )

            # Hard-delete all medical records (including soft-deleted)
            docs = MedicalDocument.all_objects.filter(user=user)
            batches = ImportBatch.all_objects.filter(user=user)
            results = LabResult.all_objects.filter(user=user)
            panels = LabPanel.all_objects.filter(user=user)

            doc_count = docs.count()
            batch_count = batches.count()
            result_count = results.count()
            panel_count = panels.count()

            # Delete error rows first
            for batch in batches:
                batch.error_rows.all().delete()

            results.delete()
            panels.delete()
            batches.delete()
            docs.delete()

            MedicalAuditLog.objects.create(
                user=user,
                action="admin_cleanup",
                detail=(
                    f"Deploy cleanup: {doc_count} docs, {batch_count} batches, "
                    f"{result_count} results, {panel_count} panels"
                ),
            )

            if verbosity >= 1:
                self.stdout.write(self.style.SUCCESS(
                    f'  Cleaned up medical data for {email}: '
                    f'{doc_count} docs, {batch_count} batches, '
                    f'{result_count} results, {panel_count} panels'
                ))

            self._mark_loader_complete(
                DataLoadConfig, loader_name, 'Cleanup Danny Medical Data (Feb 2026)',
                'command', 'One-time cleanup of orphaned medical data after ImportDeleteView bug fix'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Cleanup Danny medical data FAILED: {e}'))

    def _fix_lab_result_dates(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time fix: re-parse extracted text and correct lab result dates.

        When the date parser failed during import, timezone.now() was used as
        fallback, giving results today's date instead of the actual collection date.
        """
        loader_name = 'fix_lab_result_dates_2026_02_13'

        if not force and self._is_loader_complete(DataLoadConfig, loader_name):
            return

        try:
            from django.core.management import call_command
            call_command('fix_lab_dates', verbosity=verbosity)

            self._mark_loader_complete(
                DataLoadConfig, loader_name, 'Fix Lab Result Dates (Feb 2026)',
                'command', 'One-time fix for lab results with incorrect dates from timezone.now() fallback'
            )
        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Fix lab dates FAILED: {e}'))

    def _reset_release_notes_loader(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset of release_notes loader to reload with Feb 2026 entries.

        Release notes were previously loaded manually. This resets the loader
        so it reloads the fixture with new entries (PKs 23-30).
        Also resets teaching_destinations to pick up new Goal Engine entries.
        Only runs once (tracked via DataLoadConfig).
        """
        reset_tracker_name = 'reset_release_notes_2026_02_14'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            # Reset release_notes loader
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                config.reset()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset release_notes loader for Feb 2026 entries')
            except DataLoadConfig.DoesNotExist:
                pass  # Not loaded yet, will load fresh

            # Reset teaching_destinations loader for Goal Engine entries
            try:
                config = DataLoadConfig.objects.get(loader_name='teaching_destinations')
                config.reset()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset teaching_destinations loader for Goal Engine')
            except DataLoadConfig.DoesNotExist:
                pass  # Not loaded yet, will load fresh

            # Reset help_topics loader for HABIT_GOAL_DETAIL topic
            try:
                config = DataLoadConfig.objects.get(loader_name='help_topics')
                config.reset()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset help_topics loader for HABIT_GOAL_DETAIL')
            except DataLoadConfig.DoesNotExist:
                pass  # Not loaded yet, will load fresh

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name, 'Reset Release Notes & Teaching Destinations (Feb 2026)',
                'command', 'One-time reset to reload fixtures with Feb 2026 entries'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset release notes loader FAILED: {e}'))

    def _reset_body_composition_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures with Body Composition, Health Profile,
        and Insight Engine entries (release notes PKs 31-32, teaching destinations
        PKs 103-105, help topics PKs 29-31).
        """
        reset_tracker_name = 'reset_body_composition_2026_02_14'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            for loader_name in ('release_notes', 'teaching_destinations', 'help_topics'):
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    config.reset()
                    if verbosity >= 1:
                        self.stdout.write(f'  Reset {loader_name} loader for Body Composition/Insights')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Body Composition & Insight Engine',
                'command', 'One-time reset to reload fixtures with body comp/insights entries'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset body composition fixtures FAILED: {e}'))
