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
    {
        'name': 'admin_guide',
        'display': 'Admin Guide Documentation',
        'description': 'Comprehensive system documentation for the Admin Console',
        'app': 'admin_console',
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
    {
        'name': 'setup_strength_split',
        'display': 'Danny Strength Split',
        'description': '2-group strength training split for dannyjenkins71@gmail.com',
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
    {
        'name': 'load_sports_data',
        'display': 'Sports Reference Data',
        'description': 'Sports, leagues, and teams for the Sports domain',
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
                # If the error is a duplicate key / integrity error, the data
                # already exists in the DB (possibly with different PKs).
                # Mark as complete to prevent retry on every deploy.
                err_msg = str(e).lower()
                if 'duplicate key' in err_msg or 'unique constraint' in err_msg:
                    self._mark_loader_complete(
                        DataLoadConfig, loader_name, loader['display'],
                        'fixture', f'Marked complete (data exists): {e}'
                    )

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

        # One-time: Reset help_topics to reload with 40+ new context-aware help entries
        self._reset_help_topics_system_review(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for PIE Insights Inbox (release notes, teaching destinations, help topics)
        self._reset_pie_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for PGE Dashboard Guidance panel
        self._reset_pge_dashboard_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for PGE Guidance Inbox Enhancement
        self._reset_pge_inbox_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for SAE State Snapshot Panel
        self._reset_sae_state_snapshot_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for Daily Briefing Engine
        self._reset_dbe_briefing_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for Weekly Intelligence Report Engine
        self._reset_wire_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for Evidence & Explainability Engine
        self._reset_e3_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for Delivery & Notification Engine
        self._reset_dne_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for Intelligence Command Center
        self._reset_icc_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for ICQG release notes
        self._reset_icqg_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for Push Notification Delivery
        self._reset_push_notification_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for Persona Intelligence Layer
        self._reset_pil_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for Intelligence Observability Dashboard
        self._reset_iocd_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Backfill 30 days of observability snapshots
        self._backfill_observability_snapshots(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for Admin Guide documentation
        self._reset_admin_guide_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for Body Transformation Protocol
        self._reset_transformation_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Clear cached FatSecret FoodItems (serving size fix)
        self._clear_fatsecret_cached_items(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for Nutrition Log UI Upgrade (PK 50, PK 119)
        self._reset_nutrition_ui_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for Chief of Staff Assistant (PK 51, PK 120, PK 96)
        self._reset_cos_assistant_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for CoS Unification Pass (PK 4 updated, PK 121 added)
        self._reset_cos_unification_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for Feb 2026 doc audit (30 teaching dests, 5 release notes, 3 help topics)
        self._reset_feb_2026_doc_audit_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Phase 5 calibration rewrite (PK 57)
        self._reset_calibration_rewrite_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset existing user calibration to conversational system
        self._reset_existing_user_calibration(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for persistent chat panel (PK 58)
        self._reset_chat_panel_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Re-reset calibration after corrupted answers from chat panel v1
        self._reset_calibration_after_chat_panel(DataLoadConfig, force, verbosity)

        # One-time: Fix calibration_complete=True stuck after prior reset + auto-complete alignment
        self._fix_calibration_complete_flag(DataLoadConfig, force, verbosity)

        # One-time: Reset ALL users for new intro/calibration experience
        self._reset_all_calibration_for_intro(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Calendar Engine (PK 59)
        self._reset_calendar_engine_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset help_topics for updated DASHBOARD_HOME content (PK 1)
        self._reset_dashboard_help_topic(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Quick Links Deep Linking (PK 64)
        self._reset_quick_links_deep_link_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for intelligence threshold changes (PK 66)
        self._reset_intelligence_thresholds_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for CoS schedule awareness (PK 65 release note, teaching dests 152-154)
        self._reset_cos_schedule_awareness_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for CoS GPT-4o upgrade + chat timestamps (PKs 67-68)
        self._reset_cos_gpt4o_timestamps_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for calibration relationship redesign (PK 69)
        self._reset_calibration_relationship_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for CoS consolidation (PK 70 release note, help_topics PK 17)
        self._reset_cos_consolidation_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for extended HealthKit integration (PK 71)
        self._reset_healthkit_extension_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for food search & barcode fixes (PK 72)
        self._reset_food_search_barcode_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for CoS health data visibility (PK 73)
        self._reset_cos_health_visibility_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for sleep tracking fix (PK 74)
        self._reset_sleep_tracking_fix_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for password toggle (PK 75)
        self._reset_password_toggle_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for workout display (PK 76)
        self._reset_workout_display_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Monica proactive chat check-ins (PK 77)
        self._reset_monica_proactive_checkins_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Executive Operator upgrade (PK 78)
        self._reset_executive_operator_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for UAL executive judgment (PK 79)
        self._reset_ual_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for Diagnostics Console + Operations Wall (PK 80, teaching 155-156)
        self._reset_diagnostics_ops_wall_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for UAL v2.1 hardening (PK 81)
        self._reset_ual_v21_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Ops Command Center evolution (PK 83)
        self._reset_ops_command_center_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Celery + Redis infrastructure (PK 84)
        self._reset_celery_infrastructure_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for SAME Manual Execution Control (PK 85)
        self._reset_same_manual_execution_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Engine-Level Execution Controls (PK 86)
        self._reset_engine_execution_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Synthetic Engine Execution (PK 87)
        self._reset_synthetic_execution_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset teaching_destinations for Ops Command Center name/keywords update
        self._reset_ops_command_center_teaching(DataLoadConfig, force, verbosity)

        # One-time: Reset help_topics to fix 3 entries missing help_id (PKs 89-91) + brain training timestamps
        self._reset_help_topics_fixture_safe(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for CoS adaptive intelligence (PK 88)
        self._reset_cos_adaptive_intelligence_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Financial Command Center full suite (PK 89)
        self._reset_financial_command_center_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for CoS Phase 1 Learning Mode (PK 90)
        self._reset_cos_phase1_learning_mode_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset teaching_destinations + help_topics for Learning Mode content
        self._reset_cos_phase1_help_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for CoS Phase 2 Time & Deadline Authority (PK 91)
        self._reset_cos_phase2_time_authority_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for CoS Phase 3 Escalation Continuity (PK 92)
        self._reset_cos_phase3_escalation_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for CoS Phase 5 Protective Action Engine (PK 93)
        self._reset_cos_phase5_protective_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for CoS Phase 6 Observability & Concurrency (PK 94)
        self._reset_cos_phase6_observability_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for CoS Phase 8 Self-Governance (PK 95)
        self._reset_cos_phase8_self_governance_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Calendar CRUD via CoS (PK 96)
        self._reset_calendar_crud_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Calendar Conflict Policy (PK 97)
        self._reset_conflict_policy_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Seed LLMPriceBook and backfill event costs
        self._seed_pricebook_and_backfill(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for CoS v2 (PK 98)
        self._reset_cos_v2_release_notes(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Capture iOS download + transcript formatting (PK 101)
        self._reset_capture_ios_download_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Daily Routine Tasks (PK 102)
        self._reset_routine_tasks_release_notes(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for CoS Intelligence Upgrade (PK 104)
        self._reset_cos_intelligence_upgrade_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Clean up duplicate calendar events for all users
        self._cleanup_calendar_duplicates(DataLoadConfig, force, verbosity)

        # One-time: Clean up false-positive gap detection improvement tasks
        self._cleanup_false_positive_improvement_tasks(DataLoadConfig, force, verbosity)

        # Auto-sync CoS documentation to admin guide (runs if checksum changed)
        self._sync_cos_documentation(DataLoadConfig, force, verbosity)

        # One-time: Backfill calendar projections for existing tasks, goals, habits
        self._backfill_calendar_projections(DataLoadConfig, force, verbosity)

        # One-time: Fix scheduled tasks showing as deadline markers at 23:59
        self._fix_scheduled_task_projections(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for Journal Mood & Prompt fix (PK 105 release note, help PK 3 update)
        self._reset_journal_mood_fix_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for CoS Performance & Reliability (PK 106)
        self._reset_cos_performance_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset teaching_destinations to fix duplicate PK 58
        self._reset_teaching_destinations_dedup(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for Boot Architecture Hardening (PK 107 release note)
        self._reset_boot_hardening_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes to fix "Beth" → "CoS" in PK 106
        self._reset_cos_name_fix_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for Notes module (PK 108 release note, PK 158-159 teaching dests, PK 102-105 help topics)
        self._reset_notes_module_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Vision AI Analysis (PK 109)
        self._reset_vision_analysis_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for Meal Intelligence UI (PK 112 release note, PKs 160-165 teaching dests)
        self._reset_meals_intelligence_fixtures(DataLoadConfig, force, verbosity)
        self._reset_meals_activation_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for Phase 12 Pantry Photo Intelligence (PK 113 release note, PK 167 teaching dest)
        self._reset_pantry_photo_intelligence_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for Phase R1 Relational Intelligence (PK 114 release note, PK 168-169 teaching dest)
        self._reset_relationship_intelligence_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for Phase R2 Relationship Insights (PK 115 release note, PK 170 teaching dest)
        self._reset_relationship_insights_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for Phase 11 Power Preview (PK 116 release note, PKs 106-112 help topics)
        self._reset_meals_power_preview_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset module_definitions fixture to add Relationships module (PK 10)
        self._reset_relationships_module_definition_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset module_definitions for route change (person_list → insights)
        self._reset_relationships_nav_route_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Recipe Photo Import (PK 114)
        self._reset_recipe_photo_import_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for @Group Mentions (PK 119)
        self._reset_group_mentions_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Contact Import (PK 120)
        self._reset_contact_import_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Restore Beth's tasks that AI incorrectly deleted on 2026-03-02
        self._restore_beth_deleted_tasks(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Calendar Add Task + Time Fixes (PK 121)
        self._reset_calendar_add_task_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Global @Mention Autocomplete (PK 122)
        self._reset_global_mention_autocomplete_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for iOS Contact Import (PK 123)
        self._reset_ios_contact_import_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset help_topics + teaching_destinations for context-aware help system review
        self._reset_context_aware_help_system_review(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for context-aware help release note (PK 124)
        self._reset_help_system_release_note(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for multi-image CoS release note (PK 125)
        self._reset_multi_image_cos_release_note(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for state-aware morning automation (PK 126)
        self._reset_morning_automation_release_note(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for CoS deterministic coaching upgrade (PK 127)
        self._reset_cos_deterministic_coaching_release_note(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes + help_topics for tile card redesign + @mention help (PK 128)
        self._reset_tile_card_mention_help_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Select All + batch contact import (PK 129, 130)
        self._reset_select_all_batch_import_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Bulk Recipe Photo Import (PK 131)
        self._reset_bulk_recipe_import_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset for expanded relationship types, multi-recipe, prayer context (PKs 132-133)
        self._reset_session_2026_03_04_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for Email Medicine List feature (PK 134 + teaching/help updates)
        self._reset_email_medicine_list_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for cross-completion + schedule awareness (PK 135)
        self._reset_cross_completion_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Backfill health intelligence enhancements (plateau risk, phase, muscle preservation)
        self._backfill_health_intelligence_enhancements(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for Excel Export + CoS Report Generation (PKs 136-137 release notes, PK 175 teaching dest)
        self._reset_excel_export_report_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for Health Intelligence UI (release note PK 138, help PK 114, teaching PK 176)
        self._reset_health_intelligence_ui_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release notes for Relationships tile overhaul (PK 136)
        self._reset_relationships_tile_overhaul_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Rebuild health summaries after body composition pipeline fix
        self._rebuild_health_summaries_body_comp_fix(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for Guides Hub (Data Dictionary + User Guide)
        self._reset_guides_hub_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for friendly chat error recovery
        self._reset_chat_error_recovery_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for task skip status feature
        self._reset_task_skip_status_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for receipt hardening improvements (PK 141)
        self._reset_receipt_hardening_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for commitment level feature
        self._reset_commitment_level_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for personal life memory feature (PK 149)
        self._reset_personal_life_memory_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for PIE health screenshot interpretation (PK 152)
        self._reset_health_screenshot_interpretation_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for workout movement type upgrade (PK 153)
        self._reset_movement_type_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for CoS Action Governance upgrade (PK 154)
        self._reset_action_governance_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Beth humanization (PK 155)
        self._reset_beth_humanization_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for PGS proactive guidance scheduler (PK 157)
        self._reset_pgs_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for LLM-last deterministic router (PK 158)
        self._reset_deterministic_router_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Dashboard V2 Life Command Center (PK 159)
        self._reset_dashboard_v2_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for A/B/C interactive option bubbles (PK 164)
        self._reset_option_bubbles_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset module_definitions to add Notes module (PK 11)
        self._reset_notes_module_definition_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset fixtures for UI Alignment Phase (Routines, nav expansion)
        self._reset_ui_alignment_fixtures(DataLoadConfig, force, verbosity)
        self._reset_beth_decisive_behavior_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Routine Execution Truth + Morning Reconciliation (PKs 169-170)
        self._reset_routine_execution_truth_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Activity-Based Workouts (PK 180)
        self._reset_activity_workouts_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Unified Intake System / Supplement Tracking (PK 181)
        self._reset_supplement_tracking_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes to fix "Beth" → "Chief of Staff" in all entries
        self._reset_cos_naming_boundary_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for CDCE fasting/workout false-correlation fix (PK 182)
        self._reset_cdce_fasting_gating_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Workout-Tomorrow Hardening (PK 183)
        self._reset_workout_tomorrow_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Phase 6.6 Confirmation UX (PK 184)
        self._reset_phase_6_6_confirmation_ux_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Phase 6.7 Execution Isolation (PK 185)
        self._reset_phase_6_7_execution_isolation_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Phase 6.8 Lifecycle Visibility (PK 186)
        self._reset_phase_6_8_lifecycle_visibility_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Phase 3 Signal Completion (PK 187)
        self._reset_phase_3_signal_completion_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Phase 4 Unit Consistency (PK 188)
        self._reset_phase_4_unit_consistency_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Phase 5 Feature Gating (PK 189)
        self._reset_phase_5_feature_gating_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Phase 6 Cross-Layer Truth (PK 190)
        self._reset_phase_6_cross_layer_truth_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Phase 7 Decision Intelligence (PK 191)
        self._reset_phase_7_decision_intelligence_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Phase 8 Decision Hard Lock (PK 192)
        self._reset_phase_8_decision_hard_lock_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Phase 9 Execution-First (PK 193)
        self._reset_phase_9_execution_first_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Phase 10 Action Selection (PK 194)
        self._reset_phase_10_action_selection_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Phase 11 Intent-Aware (PK 195)
        self._reset_phase_11_intent_aware_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes to fix PK 182 timestamp causing infinite popup loop
        self._reset_whats_new_timestamp_fix_fixtures(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Gospel reading-plan consistency rebuild (PK 196)
        self._reset_gospel_plan_consistency_release_notes(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Action Center vocabulary fix (PK 197)
        self._reset_action_center_vocabulary_release_notes(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for dashboard_v3 experimental preview (PK 198)
        self._reset_dashboard_v3_preview_release_notes(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Primary Mission selection (PK 199)
        self._reset_primary_mission_release_notes(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Mission hero card (PK 200)
        self._reset_mission_hero_release_notes(DataLoadConfig, force, verbosity)

        # One-time: Reset release_notes for Mission Intelligence v1 (PK 201)
        self._reset_mission_intelligence_release_notes(DataLoadConfig, force, verbosity)
        # One-time: Reset release_notes for Mission Phase 3.5 Movement signal (PK 202)
        self._reset_mission_movement_release_notes(DataLoadConfig, force, verbosity)
        # One-time: Reset release_notes for Mission Phase 4 Worth Watching (PK 203)
        self._reset_mission_worth_watching_release_notes(DataLoadConfig, force, verbosity)
        # One-time: Reset release_notes for Mission Phase 5 Inspiration layer (PK 204)
        self._reset_mission_inspiration_release_notes(DataLoadConfig, force, verbosity)
        # One-time: Reset release_notes for Mission Phase 6 actionable drivers + A1C (PK 205)
        self._reset_mission_actionable_a1c_release_notes(DataLoadConfig, force, verbosity)
        # Phase 6.1 — clinically-accurate Projected A1C (GMI) release note (PK 206)
        self._reset_mission_gmi_accuracy_release_notes(DataLoadConfig, force, verbosity)
        # Phase 6.3 — A1C (GMI) slot never silently disappears release note (PK 207)
        self._reset_mission_a1c_always_visible_release_notes(DataLoadConfig, force, verbosity)
        # Phase 6.4 — A1C (GMI) truth model + trend classification + nutrition link (PK 208)
        self._reset_mission_a1c_truth_release_notes(DataLoadConfig, force, verbosity)

        # =====================================================================
        # SECOND PASS: Reload any fixtures that were reset by one-time methods
        # =====================================================================
        # The one-time reset methods above set is_loaded=False AFTER the initial
        # fixture loading loop. Without this second pass, reset fixtures would
        # only load on the NEXT deploy, causing a deploy-lag for new help topics,
        # teaching destinations, and release notes.
        for loader in FIXTURE_LOADERS:
            loader_name = loader['name']
            if not force and self._is_loader_complete(DataLoadConfig, loader_name):
                continue  # Still loaded, no reset happened
            try:
                if verbosity >= 1:
                    self.stdout.write(f'  Reloading {loader_name} (reset by one-time method)...', ending='')
                call_command('loaddata', loader_name, verbosity=0)
                if verbosity >= 1:
                    self.stdout.write(self.style.SUCCESS(' OK'))
                loaded_count += 1
                self._mark_loader_complete(
                    DataLoadConfig, loader_name, loader['display'],
                    'fixture', loader.get('description', '')
                )
            except Exception as e:
                if verbosity >= 1:
                    self.stdout.write(self.style.WARNING(f'  {loader_name}: Reload failed ({e})'))
                err_msg = str(e).lower()
                if 'duplicate key' in err_msg or 'unique constraint' in err_msg:
                    self._mark_loader_complete(
                        DataLoadConfig, loader_name, loader['display'],
                        'fixture', f'Marked complete (data exists): {e}'
                    )

        # =====================================================================
        # GUIDE SYNC: Populate Data Dictionary + User Guide from sources
        # =====================================================================
        # These are idempotent and fast — run on every deploy to keep
        # guide content in sync with docs/WLJ_Data_Dictionary.md and
        # HelpTopic/HelpArticle records.
        try:
            call_command('sync_data_dictionary', verbosity=0)
            if verbosity >= 1:
                self.stdout.write('  Synced Data Dictionary guide')
        except Exception as e:
            # Always log sync failures — never suppress errors
            self.stderr.write(self.style.WARNING(f'  sync_data_dictionary failed: {e}'))

        try:
            call_command('sync_user_guide', verbosity=0)
            if verbosity >= 1:
                self.stdout.write('  Synced User Guide')
        except Exception as e:
            # Always log sync failures — never suppress errors
            self.stderr.write(self.style.WARNING(f'  sync_user_guide failed: {e}'))

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
                completion_status='pending',
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
                    completion_status='pending',
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
                    completion_status='pending',
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
            batches = ImportBatch.objects.filter(user=user)
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

    def _reset_help_topics_system_review(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload help_topics with 40+ new context-aware entries
        added during the Feb 14 2026 system review. Also fixes duplicate PK 24
        (ADMIN_CONSOLE_TASKS moved to PK 32).
        """
        reset_tracker_name = 'reset_help_topics_system_review_2026_02_14'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            # Delete the old PK 24 ADMIN_CONSOLE_TASKS entry (will be recreated as PK 32)
            from apps.help.models import HelpTopic
            HelpTopic.objects.filter(
                context_id='ADMIN_CONSOLE_TASKS', pk=24
            ).delete()

            # Reset help_topics loader so it reloads with all new entries
            try:
                config = DataLoadConfig.objects.get(loader_name='help_topics')
                config.reset()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset help_topics loader for system review (40+ new entries)')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset help_topics for system review (Feb 2026)',
                'command', 'One-time reset to reload help_topics with 40+ new context-aware entries'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset help_topics system review FAILED: {e}'))

    def _reset_pie_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures for PIE Insights Inbox.
        Resets release_notes (PKs 33-34), teaching_destinations (PK 106),
        and help_topics (PK 83).
        """
        reset_tracker_name = 'reset_pie_fixtures_2026_02_15'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            for loader_name in ('release_notes', 'teaching_destinations', 'help_topics'):
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    config.reset()
                    if verbosity >= 1:
                        self.stdout.write(f'  Reset {loader_name} loader for PIE Insights')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for PIE Insights Inbox (Feb 2026)',
                'command', 'One-time reset to reload release notes, teaching destinations, and help topics for PIE'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset PIE fixtures FAILED: {e}'))

    def _reset_pge_dashboard_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures for PGE Dashboard Guidance panel.
        Resets release_notes (PK 35), teaching_destinations (PKs 107-108),
        and help_topics (PK 84).
        """
        reset_tracker_name = 'reset_pge_dashboard_fixtures_2026_02_15'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            for loader_name in ('release_notes', 'teaching_destinations', 'help_topics'):
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    config.reset()
                    if verbosity >= 1:
                        self.stdout.write(f'  Reset {loader_name} loader for PGE Dashboard')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for PGE Dashboard Guidance (Feb 2026)',
                'command', 'One-time reset to reload release notes, teaching destinations, and help topics for PGE'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset PGE Dashboard fixtures FAILED: {e}'))

    def _reset_pge_inbox_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures for PGE Guidance Inbox Enhancement.
        Adds release_notes (PK 36), help_topics (PK 85).
        """
        reset_tracker_name = 'reset_pge_inbox_fixtures_2026_02_15'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            for loader_name in ('release_notes', 'help_topics'):
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    config.reset()
                    if verbosity >= 1:
                        self.stdout.write(f'  Reset {loader_name} loader for PGE Inbox')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for PGE Guidance Inbox Enhancement (Feb 2026)',
                'command', 'One-time reset to reload release notes and help topics for PGE Inbox'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset PGE Inbox fixtures FAILED: {e}'))

    def _reset_sae_state_snapshot_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures for SAE State Snapshot Panel.
        Adds release_notes (PK 37), teaching_destinations (PK 109), help_topics (PK 86).
        """
        reset_tracker_name = 'reset_sae_state_snapshot_fixtures_2026_02_15'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            for loader_name in ('release_notes', 'teaching_destinations', 'help_topics'):
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    config.reset()
                    if verbosity >= 1:
                        self.stdout.write(f'  Reset {loader_name} loader for SAE State Snapshot')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for SAE State Snapshot Panel (Feb 2026)',
                'command', 'One-time reset to reload release notes, teaching destinations, and help topics for SAE State Snapshot'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset SAE State Snapshot fixtures FAILED: {e}'))

    def _reset_dbe_briefing_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures for Daily Briefing Engine.
        Adds release_notes (PK 38), teaching_destinations (PK 110), help_topics (PK 87).
        """
        reset_tracker_name = 'reset_dbe_briefing_fixtures_2026_02_15'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            for loader_name in ('release_notes', 'teaching_destinations', 'help_topics'):
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    config.reset()
                    if verbosity >= 1:
                        self.stdout.write(f'  Reset {loader_name} loader for DBE')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Daily Briefing Engine (Feb 2026)',
                'command', 'One-time reset to reload release notes, teaching destinations, and help topics for DBE'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset DBE fixtures FAILED: {e}'))

    def _reset_wire_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures for Weekly Intelligence Report Engine.
        Adds release_notes (PK 39), teaching_destinations (PK 111), help_topics (PK 88).
        """
        reset_tracker_name = 'reset_wire_fixtures_2026_02_15'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            for loader_name in ('release_notes', 'teaching_destinations', 'help_topics'):
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    config.reset()
                    if verbosity >= 1:
                        self.stdout.write(f'  Reset {loader_name} loader for WIRE')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Weekly Intelligence Report Engine (Feb 2026)',
                'command', 'One-time reset to reload release notes, teaching destinations, and help topics for WIRE'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset WIRE fixtures FAILED: {e}'))

    def _reset_e3_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures for Evidence & Explainability Engine.
        Adds release_notes (PK 40), teaching_destinations (PK 112), help_topics (PK 89).
        """
        reset_tracker_name = 'reset_e3_fixtures_2026_02_15'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            for loader_name in ('release_notes', 'teaching_destinations', 'help_topics'):
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    config.reset()
                    if verbosity >= 1:
                        self.stdout.write(f'  Reset {loader_name} loader for E3')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Evidence & Explainability Engine (Feb 2026)',
                'command', 'One-time reset to reload release notes, teaching destinations, and help topics for E3'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset E3 fixtures FAILED: {e}'))

    def _reset_dne_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures for Delivery & Notification Engine.
        Adds release_notes (PK 41), teaching_destinations (PKs 113-114), help_topics (PKs 90-91).
        """
        reset_tracker_name = 'reset_dne_fixtures_2026_02_15'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            for loader_name in ('release_notes', 'teaching_destinations', 'help_topics'):
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    config.reset()
                    if verbosity >= 1:
                        self.stdout.write(f'  Reset {loader_name} loader for DNE')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Delivery & Notification Engine (Feb 2026)',
                'command', 'One-time reset to reload release notes, teaching destinations, and help topics for DNE'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset DNE fixtures FAILED: {e}'))

    def _reset_icc_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures for Intelligence Command Center.
        Adds release_notes (PK 42), teaching_destinations (PK 115), help_topics (PK 92).
        """
        reset_tracker_name = 'reset_icc_fixtures_2026_02_15'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            for loader_name in ('release_notes', 'teaching_destinations', 'help_topics'):
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    config.reset()
                    if verbosity >= 1:
                        self.stdout.write(f'  Reset {loader_name} loader for ICC')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Intelligence Command Center (Feb 2026)',
                'command', 'One-time reset to reload release notes, teaching destinations, and help topics for ICC'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset ICC fixtures FAILED: {e}'))

    def _reset_icqg_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures for Intelligence Calibration & Quality Gate.
        Adds release_notes (PK 43).
        """
        reset_tracker_name = 'reset_icqg_fixtures_2026_02_15'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                config.reset()
                if verbosity >= 1:
                    self.stdout.write('  Reset release_notes loader for ICQG')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for ICQG (Feb 2026)',
                'command', 'One-time reset to reload release notes for ICQG'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset ICQG fixtures FAILED: {e}'))

    def _reset_push_notification_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures for Push Notification Delivery.
        Adds release_notes (PK 44).
        """
        reset_tracker_name = 'reset_push_notification_fixtures_2026_02_15'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                config.reset()
                if verbosity >= 1:
                    self.stdout.write('  Reset release_notes loader for Push Notifications')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Push Notification Delivery (Feb 2026)',
                'command', 'One-time reset to reload release notes for push notifications'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset push notification fixtures FAILED: {e}'))

    def _reset_pil_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures for Persona Intelligence Layer.
        Adds release_notes (PK 45).
        """
        reset_tracker_name = 'reset_pil_fixtures_2026_02_15'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                config.reset()
                if verbosity >= 1:
                    self.stdout.write('  Reset release_notes loader for Persona Intelligence Layer')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Persona Intelligence Layer (Feb 2026)',
                'command', 'One-time reset to reload release notes for adaptive personas'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset PIL fixtures FAILED: {e}'))

    def _reset_iocd_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures for Intelligence Observability Dashboard.
        Adds release_notes (PK 46), teaching_destinations (PK 116), help_topics (PK 93).
        """
        reset_tracker_name = 'reset_iocd_fixtures_2026_02_15'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            for loader_name in ('release_notes', 'teaching_destinations', 'help_topics'):
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    config.reset()
                    if verbosity >= 1:
                        self.stdout.write(f'  Reset {loader_name} loader for IOCD')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Intelligence Observability Dashboard (Feb 2026)',
                'command', 'One-time reset to reload release notes, teaching destinations, and help topics for IOCD'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset IOCD fixtures FAILED: {e}'))

    def _backfill_observability_snapshots(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time backfill of 30 days of observability snapshots.

        Generates IntelligenceMetricsSnapshot records for the last 30 days.
        First verifies the table exists to prevent deploy failures before migration runs.
        Each day is independently try/excepted — partial backfill is fine.
        Only runs once (tracked via DataLoadConfig) unless force=True.
        """
        loader_name = 'backfill_observability_snapshots_2026_02'

        if not force and self._is_loader_complete(DataLoadConfig, loader_name):
            return

        try:
            # Verify the table exists before attempting backfill
            from django.db import connection
            table_names = connection.introspection.table_names()
            if 'core_intelligencemetricssnapshot' not in table_names:
                if verbosity >= 1:
                    self.stdout.write(
                        '  Skipping observability backfill: table not yet created'
                    )
                return

            from datetime import timedelta
            from django.utils import timezone
            from apps.core.ai_observability.observability_engine import (
                generate_daily_snapshot,
            )

            yesterday = timezone.now().date() - timedelta(days=1)
            start_date = yesterday - timedelta(days=29)  # 30 days total
            generated = 0
            errors = 0

            if verbosity >= 1:
                self.stdout.write(
                    f'  Backfilling observability snapshots '
                    f'({start_date} to {yesterday})...'
                )

            current = start_date
            while current <= yesterday:
                try:
                    result = generate_daily_snapshot(target_date=current)
                    if result:
                        generated += 1
                except Exception as e:
                    errors += 1
                    if verbosity >= 2:
                        self.stdout.write(
                            self.style.WARNING(
                                f'    Snapshot for {current} failed: {e}'
                            )
                        )
                current += timedelta(days=1)

            if verbosity >= 1:
                self.stdout.write(self.style.SUCCESS(
                    f'  Observability backfill: {generated} snapshots generated'
                    f'{f", {errors} errors" if errors else ""}'
                ))

            self._mark_loader_complete(
                DataLoadConfig, loader_name,
                'Backfill Observability Snapshots (Feb 2026)',
                'command',
                f'One-time backfill of 30 days of observability snapshots ({generated} generated)'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(
                    f'Observability backfill FAILED: {e}'
                ))

    def _reset_admin_guide_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """One-time reset to load Admin Guide documentation fixtures."""
        reset_tracker_name = 'reset_admin_guide_fixtures_2026_02'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            try:
                config = DataLoadConfig.objects.get(loader_name='admin_guide')
                config.is_loaded = False
                config.save()
                if verbosity >= 1:
                    self.stdout.write('  Reset admin_guide loader for initial load')
            except DataLoadConfig.DoesNotExist:
                pass  # Will load fresh

            # Also reset release_notes, teaching_destinations, help_topics for new entries
            for name in ['release_notes', 'teaching_destinations', 'help_topics']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=name)
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write(f'  Reset {name} loader for Admin Guide entries')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset Admin Guide Fixtures (Feb 2026)',
                'command',
                'One-time reset to load Admin Guide documentation'
            )
        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset admin guide fixtures FAILED: {e}'))

    def _reset_transformation_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures for Body Transformation Protocol.
        Adds release_notes (PKs 48-49), teaching_destinations (PK 118), help_topics (PK 95).
        """
        reset_tracker_name = 'reset_transformation_fixtures_2026_02_17'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            for loader_name in ('release_notes', 'teaching_destinations', 'help_topics'):
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    config.reset()
                    if verbosity >= 1:
                        self.stdout.write(f'  Reset {loader_name} loader for Transformation Protocol')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Body Transformation Protocol (Feb 2026)',
                'command',
                'One-time reset to reload release notes, teaching destinations, and help topics for transformation'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset transformation fixtures FAILED: {e}'))

    def _clear_fatsecret_cached_items(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time cleanup: delete cached FatSecret FoodItems so they re-fetch
        with correct default serving size after the is_default fix.
        """
        reset_tracker_name = 'clear_fatsecret_cached_items_2026_02_17'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            from apps.health.models import FoodItem

            # Delete FoodItems cached from FatSecret and barcode scans
            # so they re-lookup with the corrected default serving logic
            deleted_count, _ = FoodItem.objects.filter(
                data_source__in=[FoodItem.SOURCE_FATSECRET, FoodItem.SOURCE_BARCODE]
            ).delete()

            if verbosity >= 1 and deleted_count > 0:
                self.stdout.write(f'  Cleared {deleted_count} cached barcode/FatSecret FoodItems (serving size fix)')

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Clear cached FatSecret FoodItems for serving size fix (Feb 2026)',
                'command',
                'One-time delete of cached barcode FoodItems so they re-fetch with correct default serving'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Clear FatSecret cache FAILED: {e}'))

    def _reset_nutrition_ui_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures for Nutrition Log UI Upgrade.
        Adds release_notes (PK 50), teaching_destinations (PK 119).
        """
        reset_tracker_name = 'reset_nutrition_ui_fixtures_2026_02_18'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            for loader_name in ('release_notes', 'teaching_destinations'):
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    config.reset()
                    if verbosity >= 1:
                        self.stdout.write(f'  Reset {loader_name} loader for Nutrition UI Upgrade')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Nutrition Log UI Upgrade (Feb 2026)',
                'command',
                'One-time reset to reload release notes and teaching destinations for nutrition UI'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset nutrition UI fixtures FAILED: {e}'))

    def _reset_cos_assistant_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures for Chief of Staff Assistant.
        Adds release_notes (PK 51), teaching_destinations (PK 120), help_topics (PK 96).
        """
        reset_tracker_name = 'reset_cos_assistant_fixtures_2026_02_18'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            for loader_name in ('release_notes', 'teaching_destinations', 'help_topics'):
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    config.reset()
                    if verbosity >= 1:
                        self.stdout.write(f'  Reset {loader_name} loader for CoS Assistant')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Chief of Staff Assistant (Feb 2026)',
                'command',
                'One-time reset to reload release notes, teaching destinations, and help topics for CoS'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset CoS Assistant fixtures FAILED: {e}'))

    def _reset_cos_unification_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures for CoS Unification Pass.
        Updates teaching_destinations PK 4 (AI Assistant → Chief of Staff) and adds PK 121 (CoS Settings).
        """
        reset_tracker_name = 'reset_cos_unification_fixtures_2026_02_19'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            for loader_name in ('teaching_destinations',):
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    config.reset()
                    if verbosity >= 1:
                        self.stdout.write(f'  Reset {loader_name} loader for CoS Unification')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for CoS Unification Pass (Feb 2026)',
                'command',
                'One-time reset to reload teaching destinations for CoS Settings and updated AI Assistant entry'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset CoS Unification fixtures FAILED: {e}'))

    def _reset_feb_2026_doc_audit_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures after Feb 2026 documentation audit.
        Adds 30 teaching destinations (PKs 122-151), 5 release notes (PKs 52-56),
        and 3 help topics (PKs 97-99).
        """
        reset_tracker_name = 'reset_feb_2026_doc_audit_2026_02_19'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            for loader_name in ('teaching_destinations', 'release_notes', 'help_topics'):
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    config.reset()
                    if verbosity >= 1:
                        self.stdout.write(f'  Reset {loader_name} loader for doc audit')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Feb 2026 documentation audit',
                'command',
                'One-time reset: 30 teaching destinations, 5 release notes, 3 help topics added'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset doc audit fixtures FAILED: {e}'))

    def _reset_calibration_rewrite_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for Phase 5 calibration rewrite.
        Adds release_notes PK 57 (Chief of Staff Gets to Know You).
        """
        reset_tracker_name = 'reset_calibration_rewrite_2026_02_19'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                config.reset()
                if verbosity >= 1:
                    self.stdout.write('  Reset release_notes loader for calibration rewrite')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Phase 5 calibration rewrite (Feb 2026)',
                'command',
                'One-time reset to reload release notes for conversational calibration'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset calibration rewrite fixtures FAILED: {e}'))

    def _reset_existing_user_calibration(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset of existing users from old calibration system to conversational.
        Equivalent to running: python manage.py reset_calibration_conversational
        """
        reset_tracker_name = 'reset_existing_user_calibration_2026_02_19'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            from apps.core.blueprint.cos_governance import reset_calibration_for_conversational
            from apps.users.models import User

            reset_count = 0
            for user in User.objects.filter(is_active=True):
                try:
                    if reset_calibration_for_conversational(user):
                        reset_count += 1
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset calibration for {user.email}')
                except Exception:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                f'Reset {reset_count} users to conversational calibration',
                'command',
                'One-time reset of existing users from old trickle calibration to conversational system'
            )

            if verbosity >= 1:
                self.stdout.write(f'  Calibration reset complete: {reset_count} users reset')

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset existing user calibration FAILED: {e}'))

    def _reset_chat_panel_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for persistent chat panel.
        Adds release_notes PK 58 (Always-On Chief of Staff Chat).
        """
        reset_tracker_name = 'reset_chat_panel_2026_02_19'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                config.reset()
                if verbosity >= 1:
                    self.stdout.write('  Reset release_notes loader for chat panel')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for persistent chat panel (Feb 2026)',
                'command',
                'One-time reset to reload release notes for always-on chat panel'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset chat panel fixtures FAILED: {e}'))

    def _reset_calibration_after_chat_panel(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time re-reset of calibration after chat panel v1 corrupted answers.
        The first chat panel deployment recorded generic messages as calibration
        answers. This resets all users back to stage 0 with clean state.
        """
        reset_tracker_name = 'reset_calibration_after_chat_panel_2026_02_19'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            from apps.core.blueprint.models import PersonalOperatingBlueprint
            from apps.users.models import User

            reset_count = 0
            for user in User.objects.filter(is_active=True):
                try:
                    blueprint = PersonalOperatingBlueprint.objects.filter(
                        user=user).first()
                    if not blueprint:
                        continue
                    # Force-reset calibration to stage 0 with clean answers
                    blueprint.calibration_complete = False
                    overrides = blueprint.governance_overrides or {}
                    overrides['calibration_stage'] = 0
                    overrides['calibration_paused'] = False
                    overrides['calibration_welcome_shown'] = False
                    overrides['calibration_answers'] = {}
                    overrides['calibration_force_reset_at'] = (
                        __import__('django.utils.timezone', fromlist=['now'])
                        .now().isoformat()
                    )
                    blueprint.governance_overrides = overrides
                    blueprint.save(update_fields=[
                        'calibration_complete', 'governance_overrides',
                        'updated_at',
                    ])
                    # Clear existing chat so calibration starts fresh
                    try:
                        from apps.ai.models import AssistantConversation
                        conv = AssistantConversation.objects.filter(
                            user=user, is_active=True).first()
                        if conv:
                            conv.messages.all().delete()
                    except Exception:
                        pass
                    reset_count += 1
                    if verbosity >= 1:
                        self.stdout.write(
                            f'  Force-reset calibration for {user.email}')
                except Exception:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                f'Force-reset {reset_count} users after chat panel v1 corrupted calibration',
                'command',
                'One-time force-reset: cleared corrupted answers and chat history'
            )

            if verbosity >= 1:
                self.stdout.write(
                    f'  Calibration force-reset complete: {reset_count} users')

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(
                    f'Reset calibration after chat panel FAILED: {e}'))

    def _fix_calibration_complete_flag(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time fix: calibration_complete model field stuck at True despite
        governance_overrides showing stage=0 and answers={}. Also auto-completes
        any stale alignment sessions blocking calibration injection.
        """
        reset_tracker_name = 'fix_calibration_complete_flag_v2_2026_02_19'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            from django.utils import timezone
            from apps.core.blueprint.models import PersonalOperatingBlueprint

            fixed = 0
            for bp in PersonalOperatingBlueprint.objects.filter(calibration_complete=True):
                overrides = bp.governance_overrides or {}
                stage = overrides.get('calibration_stage', 0)
                answers = overrides.get('calibration_answers', {})
                # If complete but stage=0 and no answers, the flag is wrong
                if stage == 0 and not answers:
                    bp.calibration_complete = False
                    overrides['calibration_welcome_shown'] = False
                    overrides['calibration_paused'] = False
                    bp.governance_overrides = overrides
                    bp.save(update_fields=[
                        'calibration_complete', 'governance_overrides',
                        'updated_at',
                    ])
                    fixed += 1
                    if verbosity >= 1:
                        self.stdout.write(f'  Fixed calibration_complete for user {bp.user_id}')

            # Auto-complete all stale alignment sessions
            alignment_fixed = 0
            try:
                from apps.core.ai_governance.models import GovernanceAlignmentSession
                for session in GovernanceAlignmentSession.objects.filter(is_complete=False):
                    session.is_complete = True
                    session.completed_at = timezone.now()
                    session.save(update_fields=['is_complete', 'completed_at', 'updated_at'])
                    alignment_fixed += 1
                    if verbosity >= 1:
                        self.stdout.write(f'  Auto-completed alignment session for user {session.user_id}')
            except Exception:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                f'Fixed {fixed} calibration flags, {alignment_fixed} alignment sessions',
                'command',
                'One-time fix for calibration_complete=True stuck + stale alignment sessions'
            )

            if verbosity >= 1:
                self.stdout.write(
                    f'  Calibration fix: {fixed} blueprints, {alignment_fixed} alignment sessions')

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(
                    f'Fix calibration_complete flag FAILED: {e}'))

    def _reset_all_calibration_for_intro(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset: All users get the new introduction/calibration flow.
        Resets calibration to stage 0 with welcome_shown=False and clears
        chat history so everyone experiences the warmer first-time greeting.
        """
        reset_tracker_name = 'reset_all_calibration_intro_v2_data_aware_2026_02_19'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            from django.utils import timezone
            from apps.core.blueprint.models import PersonalOperatingBlueprint

            reset_count = 0
            for bp in PersonalOperatingBlueprint.objects.select_related('user').all():
                try:
                    bp.calibration_complete = False
                    overrides = bp.governance_overrides or {}
                    overrides['calibration_stage'] = 0
                    overrides['calibration_paused'] = False
                    overrides['calibration_welcome_shown'] = False
                    overrides['calibration_answers'] = {}
                    overrides['calibration_complete'] = False
                    overrides['calibration_intro_reset_at'] = timezone.now().isoformat()
                    bp.governance_overrides = overrides
                    bp.save(update_fields=[
                        'calibration_complete', 'governance_overrides',
                        'updated_at',
                    ])
                    # Clear chat history so calibration starts fresh
                    try:
                        from apps.ai.models import AssistantConversation
                        conv = AssistantConversation.objects.filter(
                            user=bp.user, is_active=True).first()
                        if conv:
                            conv.messages.all().delete()
                    except Exception:
                        pass
                    reset_count += 1
                    if verbosity >= 1:
                        self.stdout.write(
                            f'  Reset calibration for intro: {bp.user.email}')
                except Exception:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                f'Reset {reset_count} users for new intro/calibration experience',
                'command',
                'One-time: all users restart calibration with new welcome flow'
            )

            if verbosity >= 1:
                self.stdout.write(
                    f'  Calibration intro reset complete: {reset_count} users')

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(
                    f'Reset all calibration for intro FAILED: {e}'))

    def _sync_cos_documentation(self, DataLoadConfig, force=False, verbosity=1):
        """
        Auto-sync CoS documentation to admin guide.

        Runs on every deploy but only writes if the dependency checksum
        has changed (or if force=True). This keeps the admin guide
        documentation in sync with the actual code.
        """
        try:
            from apps.core.ai_docs.cos_doc_sync import sync_cos_admin_guide

            result = sync_cos_admin_guide(force=force)

            if result['synced'] and verbosity >= 1:
                self.stdout.write(
                    f"  CoS docs synced: {result['articles_created']} created, "
                    f"{result['articles_updated']} updated, "
                    f"{result['articles_removed']} removed"
                )
        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.WARNING(
                    f'  CoS doc sync skipped: {e}'
                ))

    def _backfill_calendar_projections(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time backfill: Project all existing tasks, goals, milestones, and habits
        to the calendar engine. Items created before signal wiring was added have no
        CalendarEvent records. Safe to run multiple times (upsert logic).
        """
        loader_name = 'backfill_calendar_projections_2026_02_27'

        if not force and self._is_loader_complete(DataLoadConfig, loader_name):
            return

        try:
            from apps.life.models import Task
            from apps.purpose.models import LifeGoal, HabitGoal
            from apps.calendar_engine.services.projection import (
                upsert_from_task,
                upsert_from_goal,
                upsert_from_habit,
            )

            counts = {'tasks': 0, 'goals': 0, 'habits': 0, 'errors': 0}

            # Tasks with due dates
            for task in Task.objects.filter(
                due_date__isnull=False, deleted_at__isnull=True
            ).select_related('user', 'user__preferences').iterator():
                try:
                    upsert_from_task(task)
                    counts['tasks'] += 1
                except Exception:
                    counts['errors'] += 1

            # Goals (includes milestone projection)
            for goal in LifeGoal.objects.filter(
                deleted_at__isnull=True
            ).select_related('user', 'domain').prefetch_related('milestones').iterator(chunk_size=2000):
                try:
                    upsert_from_goal(goal)
                    counts['goals'] += 1
                except Exception:
                    counts['errors'] += 1

            # Active habits
            for habit in HabitGoal.objects.filter(
                deleted_at__isnull=True, status='active'
            ).select_related('user', 'domain').iterator():
                try:
                    upsert_from_habit(habit)
                    counts['habits'] += 1
                except Exception:
                    counts['errors'] += 1

            if verbosity >= 1:
                self.stdout.write(
                    f"  Calendar backfill: {counts['tasks']} tasks, "
                    f"{counts['goals']} goals, {counts['habits']} habits "
                    f"({counts['errors']} errors)"
                )

            self._mark_loader_complete(
                DataLoadConfig, loader_name,
                'Backfill calendar projections for existing tasks/goals/habits',
                'command',
                'One-time backfill of CalendarEvent records for items created before signal wiring'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.WARNING(
                    f'  Calendar backfill skipped: {e}'
                ))

    def _fix_scheduled_task_projections(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time fix: Tasks with scheduled_time were incorrectly projected as
        DEADLINE_MARKERs at 23:59 instead of EXECUTION_BLOCKs at their actual
        scheduled time. This deletes wrong markers and re-projects them correctly.
        """
        loader_name = 'fix_scheduled_task_projections_2026_02_27'

        if not force and self._is_loader_complete(DataLoadConfig, loader_name):
            return

        try:
            from apps.life.models import Task
            from apps.calendar_engine.models import CalendarEvent
            from apps.calendar_engine.services.projection import upsert_from_task

            # Find tasks with scheduled_time that have deadline markers (wrong)
            scheduled_tasks = Task.objects.filter(
                scheduled_time__isnull=False,
                due_date__isnull=False,
                deleted_at__isnull=True,
            ).select_related('user', 'user__preferences')

            fixed = 0
            errors = 0
            for task in scheduled_tasks.iterator():
                try:
                    # Delete any wrong deadline marker
                    deleted_count = CalendarEvent.objects.filter(
                        user=task.user,
                        source_type=CalendarEvent.SOURCE_TASK,
                        source_id=str(task.pk),
                        event_kind=CalendarEvent.KIND_DEADLINE_MARKER,
                    ).delete()[0]

                    if deleted_count > 0:
                        # Re-project — will now create execution block at correct time
                        upsert_from_task(task)
                        fixed += 1
                except Exception:
                    errors += 1

            if verbosity >= 1 and (fixed > 0 or errors > 0):
                self.stdout.write(
                    f"  Scheduled task fix: {fixed} tasks re-projected "
                    f"from deadline markers to execution blocks ({errors} errors)"
                )

            self._mark_loader_complete(
                DataLoadConfig, loader_name,
                'Fix scheduled tasks projected as deadline markers instead of execution blocks',
                'command',
                'Re-project tasks with scheduled_time as time-specific execution blocks'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.WARNING(
                    f'  Scheduled task fix skipped: {e}'
                ))

    def _reset_journal_mood_fix_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes (PK 105) and help_topics (PK 3 updated)
        for Journal Mood & Prompt dashboard fix.
        """
        reset_tracker_name = 'reset_journal_mood_fix_2026_02_28'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for fixture_name in ['release_notes', 'help_content']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=fixture_name)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {fixture_name} loader for Journal Mood fix')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Journal Mood & Prompt fix (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 105 and help_topics PK 3'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset journal mood fix fixtures FAILED: {e}'))

    def _reset_calendar_engine_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes and help_topics for Calendar Engine.
        Adds release_notes PK 59, help_topics PKs 100-101.
        """
        reset_tracker_name = 'reset_calendar_engine_help_2026_02_20'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            for loader_name in ('release_notes', 'help_topics'):
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    config.reset()
                    if verbosity >= 1:
                        self.stdout.write(f'  Reset {loader_name} loader for Calendar Engine')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Calendar Engine: release_notes + help_topics (Feb 2026)',
                'command',
                'One-time reset to reload release notes and help topics for calendar engine'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset calendar engine fixtures FAILED: {e}'))

    def _reset_dashboard_help_topic(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload help_topics with updated DASHBOARD_HOME content.
        PK 1 updated to cover CoS panel, Today's Guidance actions, TCC link.
        """
        reset_tracker_name = 'reset_dashboard_help_2026_02_20'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            try:
                config = DataLoadConfig.objects.get(loader_name='help_topics')
                config.reset()
                if verbosity >= 1:
                    self.stdout.write('  Reset help_topics loader for DASHBOARD_HOME rewrite')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset help_topics for DASHBOARD_HOME rewrite (Feb 2026)',
                'command',
                'One-time reset: updated DASHBOARD_HOME to cover CoS, Guidance, TCC'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset dashboard help topic FAILED: {e}'))

    def _reset_quick_links_deep_link_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures for Quick Links Deep Linking.
        - release_notes PK 64 (Smart Quick Links with Mobile App Deep Linking)
        - teaching_destinations: updated quick-links entry with deep link keywords
        - help_topics: updated SETTINGS_PREFERENCES with Quick Links section
        """
        reset_tracker_name = 'reset_quick_links_deep_link_2026_02_20'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            for loader_name in ('release_notes', 'teaching_destinations', 'help_topics'):
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    config.reset()
                    if verbosity >= 1:
                        self.stdout.write(f'  Reset {loader_name} loader for Quick Links Deep Linking')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Quick Links Deep Linking (Feb 2026)',
                'command',
                'One-time reset to reload release notes, teaching dests, help topics for deep linking'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset quick links deep link fixtures FAILED: {e}'))

    def _reset_intelligence_thresholds_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for intelligence threshold changes.
        - release_notes PK 66 (Smarter Intelligence — Instant Feedback on Every Entry)
        """
        reset_tracker_name = 'reset_intelligence_thresholds_2026_02_20'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                config.reset()
                if verbosity >= 1:
                    self.stdout.write('  Reset release_notes loader for intelligence thresholds')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release notes for intelligence threshold changes (Feb 2026)',
                'command',
                'One-time reset to reload release notes PK 66'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset intelligence thresholds fixtures FAILED: {e}'))

    def _reset_cos_schedule_awareness_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures for CoS schedule awareness:
        - release_notes PK 65 (Your Chief of Staff Now Knows Your Schedule)
        - teaching_destinations PKs 152-154 (TCC, Month View, Manage Events)
        """
        reset_tracker_name = 'reset_cos_schedule_awareness_2026_02_20'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            for loader_name in ('release_notes', 'teaching_destinations'):
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    config.reset()
                    if verbosity >= 1:
                        self.stdout.write(f'  Reset {loader_name} loader for CoS schedule awareness')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for CoS schedule awareness (Feb 2026)',
                'command',
                'One-time reset to reload release notes PK 65 and teaching dests PKs 152-154'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset CoS schedule awareness fixtures FAILED: {e}'))

    def _reset_cos_gpt4o_timestamps_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures for CoS GPT-4o upgrade and chat timestamps:
        - release_notes PKs 67-68 (timestamps, GPT-4o upgrade)
        """
        reset_tracker_name = 'reset_cos_gpt4o_timestamps_2026_02_20'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                config.reset()
                if verbosity >= 1:
                    self.stdout.write('  Reset release_notes loader for CoS GPT-4o + timestamps')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for CoS GPT-4o upgrade + chat timestamps (Feb 2026)',
                'command',
                'One-time reset to reload release notes PKs 67-68'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset CoS GPT-4o timestamps fixtures FAILED: {e}'))

    def _reset_calibration_relationship_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures for calibration relationship redesign:
        - release_notes PK 69 (calibration as relationship, user-controlled)
        """
        reset_tracker_name = 'reset_calibration_relationship_2026_02_20'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                config.reset()
                if verbosity >= 1:
                    self.stdout.write('  Reset release_notes loader for calibration relationship redesign')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for calibration relationship redesign (Feb 2026)',
                'command',
                'One-time reset to reload release notes PK 69'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset calibration relationship fixtures FAILED: {e}'))

    def _reset_cos_consolidation_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures for CoS consolidation.
        - release_notes PK 70 (Chief of Staff Consolidation)
        - help_topics PK 17 (updated ASSISTANT_HOME title/description)
        """
        reset_tracker_name = 'reset_cos_consolidation_2026_02_20'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            for loader_name in ('release_notes', 'help_topics'):
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    config.reset()
                    if verbosity >= 1:
                        self.stdout.write(f'  Reset {loader_name} loader for CoS consolidation')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for CoS consolidation (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 70 and help_topics PK 17'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset CoS consolidation fixtures FAILED: {e}'))

    def _reset_healthkit_extension_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for extended HealthKit integration.
        - release_notes PK 71 (Extended HealthKit Integration)
        """
        reset_tracker_name = 'reset_healthkit_extension_2026_02_21'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                config.reset()
                if verbosity >= 1:
                    self.stdout.write('  Reset release_notes loader for extended HealthKit')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for extended HealthKit integration (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 71'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset HealthKit extension fixtures FAILED: {e}'))

    def _reset_food_search_barcode_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for food search & barcode scanner fixes.
        - release_notes PK 72 (Food Search & Barcode Scanner fix)
        """
        reset_tracker_name = 'reset_food_search_barcode_2026_02_20'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                config.reset()
                if verbosity >= 1:
                    self.stdout.write('  Reset release_notes loader for food search & barcode fixes')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for food search & barcode scanner fixes (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 72'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset food search barcode fixtures FAILED: {e}'))

    def _reset_cos_health_visibility_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for CoS health data visibility.
        - release_notes PK 73 (CoS can see all health data)
        """
        reset_tracker_name = 'reset_cos_health_visibility_2026_02_21'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                config.reset()
                if verbosity >= 1:
                    self.stdout.write('  Reset release_notes loader for CoS health visibility')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for CoS health data visibility (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 73'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset CoS health visibility fixtures FAILED: {e}'))

    def _reset_sleep_tracking_fix_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for sleep tracking fix.
        - release_notes PK 74 (Sleep Tracking Fix — No More Fake 8-Hour Readings)
        """
        reset_tracker_name = 'reset_sleep_tracking_fix_2026_02_21'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                config.reset()
                if verbosity >= 1:
                    self.stdout.write('  Reset release_notes loader for sleep tracking fix')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for sleep tracking fix (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 74'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset sleep tracking fix fixtures FAILED: {e}'))

    def _reset_password_toggle_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for password visibility toggle.
        - release_notes PK 75 (Password Visibility Toggle)
        """
        reset_tracker_name = 'reset_password_toggle_2026_02_21'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                config.reset()
                if verbosity >= 1:
                    self.stdout.write('  Reset release_notes loader for password toggle')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for password toggle (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 75'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset password toggle fixtures FAILED: {e}'))

    def _reset_workout_display_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures for HealthKit workout display.
        - release_notes PK 76 (Apple Watch Workout Display)
        - teaching_destinations PKs 6, 134 (updated keywords for Apple Watch/HealthKit)
        - help_topics PK 27 (HEALTH_FITNESS — added Apple Watch Workouts section)
        """
        reset_tracker_name = 'reset_workout_display_2026_02_21b'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            for loader_name in ['release_notes', 'teaching_destinations', 'help_topics']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    config.reset()
                    if verbosity >= 1:
                        self.stdout.write(f'  Reset {loader_name} loader for workout display')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for workout display (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 76, teaching_destinations PKs 6/134, help_topics PK 27'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset workout display fixtures FAILED: {e}'))

    def _reset_monica_proactive_checkins_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures for Monica proactive chat check-ins.
        - release_notes PK 77 (Monica proactive check-ins)
        """
        reset_tracker_name = 'reset_monica_proactive_checkins_2026_02_21'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                config.reset()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset release_notes loader for Monica proactive check-ins')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Monica proactive check-ins (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 77'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Monica proactive check-ins fixtures FAILED: {e}'))

    def _reset_executive_operator_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for Executive Operator upgrade.
        - release_notes PK 78 (Executive Operator morning briefing)
        """
        reset_tracker_name = 'reset_executive_operator_2026_02_21'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                config.reset()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset release_notes loader for Executive Operator upgrade')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Executive Operator upgrade (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 78'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Executive Operator fixtures FAILED: {e}'))

    def _reset_diagnostics_ops_wall_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures for Diagnostics Console + Operations Wall.
        - release_notes PK 80
        - teaching_destinations PKs 155-156
        """
        reset_tracker_name = 'reset_diagnostics_ops_wall_2026_02_21'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            for loader in ['release_notes', 'teaching_destinations']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader)
                    config.reset()
                    if verbosity >= 1:
                        self.stdout.write(f'  Reset {loader} loader for Diagnostics + Ops Wall')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Diagnostics Console + Operations Wall (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 80 + teaching_destinations PKs 155-156'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Diagnostics/Ops Wall fixtures FAILED: {e}'))

    def _reset_ual_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for UAL executive judgment.
        - release_notes PK 79 (Universal Arbitration Layer)
        """
        reset_tracker_name = 'reset_ual_executive_judgment_2026_02_21'

        if not force and self._is_loader_complete(DataLoadConfig, reset_tracker_name):
            return

        try:
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                config.reset()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset release_notes loader for UAL executive judgment')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for UAL executive judgment (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 79'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset UAL fixtures FAILED: {e}'))

    def _reset_ual_v21_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for UAL v2.1 hardening.
        - release_notes PK 81 (UAL v2.1 intelligence hardening)
        """
        reset_tracker_name = 'reset_ual_v21_hardening_2026_02_21'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            config = DataLoadConfig.objects.get(loader_name='release_notes')
            if config.is_loaded:
                config.is_loaded = False
                config.save()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset release_notes loader for UAL v2.1 hardening')

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for UAL v2.1 hardening (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 81'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset UAL v2.1 fixtures FAILED: {e}'))

    def _reset_ops_command_center_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for Ops Command Center evolution.
        - release_notes PK 83 (Ops Command Center Evolution — Full Intelligence OS)
        """
        reset_tracker_name = 'reset_ops_command_center_2026_02_21'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            config = DataLoadConfig.objects.get(loader_name='release_notes')
            if config.is_loaded:
                config.is_loaded = False
                config.save()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset release_notes loader for Ops Command Center evolution')

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Ops Command Center evolution (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 83'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Ops Command Center fixtures FAILED: {e}'))

    def _reset_celery_infrastructure_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for Celery + Redis infrastructure.
        - release_notes PK 84 (Celery + Redis Background Infrastructure)
        """
        reset_tracker_name = 'reset_celery_infrastructure_2026_02_21'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            config = DataLoadConfig.objects.get(loader_name='release_notes')
            if config.is_loaded:
                config.is_loaded = False
                config.save()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset release_notes loader for Celery + Redis infrastructure')

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Celery + Redis infrastructure (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 84'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Celery infrastructure fixtures FAILED: {e}'))

    def _reset_help_topics_fixture_safe(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload help_topics and help_topics_brain_training.

        Fixes:
        - 3 help_topics entries (PKs 89-91) missing help_id, description, app_name, order
        - Model change from auto_now_add=True to default=timezone.now for loaddata compatibility
        """
        reset_tracker_name = 'reset_help_topics_fixture_safe_2026_02_21'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for loader_name in ('help_topics', 'help_topics_brain_training'):
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader_name} loader for fixture-safe timestamps')
                except DataLoadConfig.DoesNotExist:
                    pass  # Not yet loaded, will load on next pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset help_topics for fixture-safe timestamps (Feb 2026)',
                'command',
                'One-time reset: fix missing help_id on PKs 89-91, model timestamp defaults'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset help_topics fixture-safe FAILED: {e}'))

    def _reset_same_manual_execution_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for SAME Manual Execution Control.
        - release_notes PK 85 (SAME Manual Execution Control)
        """
        reset_tracker_name = 'reset_same_manual_execution_2026_02_21'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            config = DataLoadConfig.objects.get(loader_name='release_notes')
            if config.is_loaded:
                config.is_loaded = False
                config.save()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset release_notes loader for SAME Manual Execution Control')

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for SAME Manual Execution Control (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 85'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset SAME manual execution fixtures FAILED: {e}'))

    def _reset_engine_execution_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for Engine-Level Execution Controls.
        - release_notes PK 86 (Engine-Level Manual Execution & Recovery Controls)
        """
        reset_tracker_name = 'reset_engine_execution_2026_02_21'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            config = DataLoadConfig.objects.get(loader_name='release_notes')
            if config.is_loaded:
                config.is_loaded = False
                config.save()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset release_notes loader for Engine-Level Execution Controls')

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Engine-Level Execution Controls (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 86'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset engine execution fixtures FAILED: {e}'))

    def _reset_ops_command_center_teaching(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload teaching_destinations with updated Ops Command Center entry.
        - PK 155: Renamed from 'Operations Wall' to 'Ops Command Center', expanded keywords
        """
        reset_tracker_name = 'reset_ops_command_center_teaching_2026_02_21'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            config = DataLoadConfig.objects.get(loader_name='teaching_destinations')
            if config.is_loaded:
                config.is_loaded = False
                config.save()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset teaching_destinations loader for Ops Command Center update')

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Ops Command Center teaching destination (Feb 2026)',
                'command',
                'One-time reset to reload teaching_destinations PK 155'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Ops Command Center teaching FAILED: {e}'))

    def _reset_synthetic_execution_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for Synthetic Engine Execution.
        - release_notes PK 87 (Full Engine Execution Authority — Synthetic Mode)
        """
        reset_tracker_name = 'reset_synthetic_execution_2026_02_21'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            config = DataLoadConfig.objects.get(loader_name='release_notes')
            if config.is_loaded:
                config.is_loaded = False
                config.save()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset release_notes loader for Synthetic Engine Execution')

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Synthetic Engine Execution (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 87'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset synthetic execution fixtures FAILED: {e}'))

    def _reset_cos_adaptive_intelligence_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for CoS adaptive intelligence upgrade.
        - release_notes PK 88 (Smarter, Faster Chief of Staff Responses)
        """
        reset_tracker_name = 'reset_cos_adaptive_intelligence_2026_02_21'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            config = DataLoadConfig.objects.get(loader_name='release_notes')
            if config.is_loaded:
                config.is_loaded = False
                config.save()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset release_notes loader for CoS adaptive intelligence')

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for CoS adaptive intelligence (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 88'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset CoS adaptive intelligence fixtures FAILED: {e}'))

    def _reset_financial_command_center_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for Financial Command Center full suite.
        - release_notes PK 89 (Financial Command Center — Full Suite)
        """
        reset_tracker_name = 'reset_financial_command_center_2026_02_22'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            config = DataLoadConfig.objects.get(loader_name='release_notes')
            if config.is_loaded:
                config.is_loaded = False
                config.save()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset release_notes loader for Financial Command Center')

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Financial Command Center full suite (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 89'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Financial Command Center fixtures FAILED: {e}'))

    def _reset_cos_phase1_learning_mode_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for CoS Phase 1 Learning Mode.
        - release_notes PK 90 (Learning Mode & Priority System)
        """
        reset_tracker_name = 'reset_cos_phase1_learning_mode_2026_02_22'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            config = DataLoadConfig.objects.get(loader_name='release_notes')
            if config.is_loaded:
                config.is_loaded = False
                config.save()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset release_notes loader for CoS Phase 1 Learning Mode')

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for CoS Phase 1 Learning Mode (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 90'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset CoS Phase 1 fixtures FAILED: {e}'))

    def _reset_cos_phase1_help_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload teaching_destinations and help_topics
        after adding Learning Mode content.
        """
        reset_tracker_name = 'reset_cos_phase1_help_fixtures_2026_02_22'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for loader in ['teaching_destinations', 'help_topics']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader} loader for Learning Mode help content')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset help fixtures for CoS Phase 1 Learning Mode content (Feb 2026)',
                'command',
                'One-time reset to reload teaching_destinations and help_topics with Learning Mode'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset CoS Phase 1 help fixtures FAILED: {e}'))

    def _reset_cos_phase2_time_authority_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for CoS Phase 2 Time & Deadline Authority.
        - release_notes PK 91 (Smarter Time & Deadline Intelligence)
        """
        reset_tracker_name = 'reset_cos_phase2_time_authority_2026_02_23'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            config = DataLoadConfig.objects.get(loader_name='release_notes')
            if config.is_loaded:
                config.is_loaded = False
                config.save()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset release_notes loader for CoS Phase 2 Time & Deadline Authority')

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for CoS Phase 2 Time & Deadline Authority (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 91'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset CoS Phase 2 fixtures FAILED: {e}'))

    def _reset_cos_phase3_escalation_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for CoS Phase 3 Escalation Continuity.
        - release_notes PK 92 (Persistent Accountability & Recovery Tracking)
        """
        reset_tracker_name = 'reset_cos_phase3_escalation_2026_02_23'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            config = DataLoadConfig.objects.get(loader_name='release_notes')
            if config.is_loaded:
                config.is_loaded = False
                config.save()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset release_notes loader for CoS Phase 3 Escalation Continuity')

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for CoS Phase 3 Escalation Continuity (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 92'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset CoS Phase 3 fixtures FAILED: {e}'))

    def _reset_cos_phase5_protective_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for CoS Phase 5 Protective Action Engine.
        - release_notes PK 93 (Proactive Schedule Protection & Deadline Alerts)
        """
        reset_tracker_name = 'reset_cos_phase5_protective_2026_02_23'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            config = DataLoadConfig.objects.get(loader_name='release_notes')
            if config.is_loaded:
                config.is_loaded = False
                config.save()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset release_notes loader for CoS Phase 5 Protective Action Engine')

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for CoS Phase 5 Protective Action Engine (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 93'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset CoS Phase 5 fixtures FAILED: {e}'))

    def _reset_cos_phase6_observability_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for CoS Phase 6 Observability & Concurrency.
        - release_notes PK 94 (Improved Reliability & Graceful Recovery)
        """
        reset_tracker_name = 'reset_cos_phase6_observability_2026_02_23'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            config = DataLoadConfig.objects.get(loader_name='release_notes')
            if config.is_loaded:
                config.is_loaded = False
                config.save()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset release_notes loader for CoS Phase 6 Observability & Concurrency')

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for CoS Phase 6 Observability & Concurrency (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 94'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset CoS Phase 6 fixtures FAILED: {e}'))

    def _reset_cos_phase8_self_governance_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for CoS Phase 8 Self-Governance.
        - release_notes PK 95 (Sharper, More Precise Guidance)
        """
        reset_tracker_name = 'reset_cos_phase8_self_governance_2026_02_23'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            config = DataLoadConfig.objects.get(loader_name='release_notes')
            if config.is_loaded:
                config.is_loaded = False
                config.save()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset release_notes loader for CoS Phase 8 Self-Governance')

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for CoS Phase 8 Self-Governance (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 95'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset CoS Phase 8 fixtures FAILED: {e}'))

    def _reset_calendar_crud_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for Calendar CRUD via CoS.
        - release_notes PK 96 (Full Calendar Control via Chief of Staff)
        """
        reset_tracker_name = 'reset_calendar_crud_cos_2026_02_24'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            config = DataLoadConfig.objects.get(loader_name='release_notes')
            if config.is_loaded:
                config.is_loaded = False
                config.save()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset release_notes loader for Calendar CRUD via CoS')

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Calendar CRUD via CoS (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 96'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Calendar CRUD fixtures FAILED: {e}'))

    def _reset_conflict_policy_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for Calendar Conflict Policy.
        - release_notes PK 97 (Smart Conflict Detection)
        """
        reset_tracker_name = 'reset_conflict_policy_2026_02_24'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            config = DataLoadConfig.objects.get(loader_name='release_notes')
            if config.is_loaded:
                config.is_loaded = False
                config.save()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset release_notes loader for Calendar Conflict Policy')

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Calendar Conflict Policy (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 97'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Conflict Policy fixtures FAILED: {e}'))

    def _seed_pricebook_and_backfill(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time: Seed LLMPriceBook with OpenAI pricing and backfill costs
        on existing LLMUsageEvent rows that have cost_usd=0.
        """
        reset_tracker_name = 'seed_pricebook_backfill_v2_2026_02_22'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            from datetime import date as dt_date
            from decimal import Decimal
            from apps.owner_finance.models import ThirdPartyVendor, LLMPriceBook, LLMUsageEvent

            if verbosity >= 1:
                self.stdout.write('  Seeding LLMPriceBook...')

            openai_vendor, _ = ThirdPartyVendor.objects.get_or_create(
                name='OpenAI', defaults={'category': 'LLM'},
            )

            entries = [
                # GPT-4o family
                {
                    'model_name': 'gpt-4o',
                    'effective_start': dt_date(2024, 5, 1),
                    'input_cost_per_1m_tokens_usd': '2.50',
                    'output_cost_per_1m_tokens_usd': '10.00',
                },
                {
                    'model_name': 'gpt-4o-mini',
                    'effective_start': dt_date(2024, 7, 1),
                    'input_cost_per_1m_tokens_usd': '0.15',
                    'output_cost_per_1m_tokens_usd': '0.60',
                },
                # GPT-4.1 family
                {
                    'model_name': 'gpt-4.1',
                    'effective_start': dt_date(2025, 4, 1),
                    'input_cost_per_1m_tokens_usd': '2.00',
                    'output_cost_per_1m_tokens_usd': '8.00',
                },
                {
                    'model_name': 'gpt-4.1-mini',
                    'effective_start': dt_date(2025, 4, 1),
                    'input_cost_per_1m_tokens_usd': '0.40',
                    'output_cost_per_1m_tokens_usd': '1.60',
                },
                {
                    'model_name': 'gpt-4.1-nano',
                    'effective_start': dt_date(2025, 4, 1),
                    'input_cost_per_1m_tokens_usd': '0.10',
                    'output_cost_per_1m_tokens_usd': '0.40',
                },
                # Reasoning models
                {
                    'model_name': 'o3-mini',
                    'effective_start': dt_date(2025, 1, 1),
                    'input_cost_per_1m_tokens_usd': '1.10',
                    'output_cost_per_1m_tokens_usd': '4.40',
                },
                {
                    'model_name': 'o4-mini',
                    'effective_start': dt_date(2025, 4, 1),
                    'input_cost_per_1m_tokens_usd': '1.10',
                    'output_cost_per_1m_tokens_usd': '4.40',
                },
                # Audio
                {
                    'model_name': 'whisper-1',
                    'effective_start': dt_date(2024, 1, 1),
                    'input_cost_per_1m_tokens_usd': '0.00',
                    'output_cost_per_1m_tokens_usd': '0.00',
                },
            ]

            created = 0
            for entry in entries:
                _, was_created = LLMPriceBook.objects.get_or_create(
                    vendor=openai_vendor,
                    model_name=entry['model_name'],
                    effective_start=entry['effective_start'],
                    defaults={
                        'input_cost_per_1m_tokens_usd': entry['input_cost_per_1m_tokens_usd'],
                        'output_cost_per_1m_tokens_usd': entry['output_cost_per_1m_tokens_usd'],
                        'is_active': True,
                    },
                )
                if was_created:
                    created += 1

            if verbosity >= 1:
                self.stdout.write(f'    PriceBook: {created} created, {len(entries) - created} existing')

            # Backfill costs on events with cost_usd=0
            zero_events = LLMUsageEvent.objects.filter(cost_usd=0)
            total_backfilled = 0

            for model_name in zero_events.values_list('model_name', flat=True).distinct():
                price = (
                    LLMPriceBook.objects
                    .filter(model_name=model_name, is_active=True)
                    .order_by('-effective_start')
                    .first()
                )
                if not price:
                    if verbosity >= 1:
                        self.stdout.write(f'    No price for {model_name}, skipping')
                    continue

                for event in zero_events.filter(model_name=model_name):
                    input_cost = (
                        Decimal(str(event.input_tokens))
                        * price.input_cost_per_1m_tokens_usd
                        / Decimal('1000000')
                    )
                    output_cost = (
                        Decimal(str(event.output_tokens))
                        * price.output_cost_per_1m_tokens_usd
                        / Decimal('1000000')
                    )
                    event.cost_usd = input_cost + output_cost
                    event.save(update_fields=['cost_usd'])
                    total_backfilled += 1

            if verbosity >= 1:
                self.stdout.write(f'    Backfilled costs on {total_backfilled} events')

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Seed LLMPriceBook and backfill event costs (Feb 2026)',
                'command',
                'One-time seed + backfill for owner_finance'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'PriceBook seed/backfill FAILED: {e}'))

    def _reset_cos_v2_release_notes(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for CoS v2 (PK 98).
        """
        reset_tracker_name = 'reset_cos_v2_release_notes_2026_02_24'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            config = DataLoadConfig.objects.get(loader_name='release_notes')
            if config.is_loaded:
                config.is_loaded = False
                config.save()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset release_notes loader for CoS v2')

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for CoS v2 release notes (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 98'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset CoS v2 release notes FAILED: {e}'))

    def _reset_capture_ios_download_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for Capture iOS download + transcript formatting (PK 101).
        """
        reset_tracker_name = 'reset_capture_ios_download_2026_02_24'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            config = DataLoadConfig.objects.get(loader_name='release_notes')
            if config.is_loaded:
                config.is_loaded = False
                config.save()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset release_notes loader for Capture iOS download + transcript formatting')

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Capture iOS download + transcript formatting (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 101'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Capture iOS download fixtures FAILED: {e}'))

    def _reset_routine_tasks_release_notes(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for Daily Routine Tasks (PK 102).
        """
        reset_tracker_name = 'reset_routine_tasks_release_notes_2026_02_25'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            config = DataLoadConfig.objects.get(loader_name='release_notes')
            if config.is_loaded:
                config.is_loaded = False
                config.save()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset release_notes loader for Daily Routine Tasks')

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Daily Routine Tasks release notes (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 102'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset routine tasks release notes FAILED: {e}'))

    def _reset_cos_intelligence_upgrade_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for CoS Intelligence Upgrade (PK 104).
        """
        reset_tracker_name = 'reset_cos_intelligence_upgrade_2026_02_25'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            config = DataLoadConfig.objects.get(loader_name='release_notes')
            if config.is_loaded:
                config.is_loaded = False
                config.save()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset release_notes loader for CoS Intelligence Upgrade')

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for CoS Intelligence Upgrade release notes (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 104'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset CoS intelligence upgrade release notes FAILED: {e}'))

    def _cleanup_false_positive_improvement_tasks(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time cleanup of false-positive improvement tasks created by the
        gap detector before it was fixed (Feb 2026).

        The gap detector was too aggressive — it flagged ANY message containing
        'me'/'my'/'I' + unknown words as potential new data types. Common verbs
        like 'pick' from "Look at the scripture and pick one and walk me through
        it" triggered "Evaluate new data type: 'pick'" email alerts.

        This cleans up those false-positive tasks.
        """
        loader_name = 'cleanup_false_positive_improvement_tasks_2026_02'

        if not force and self._is_loader_complete(DataLoadConfig, loader_name):
            return

        try:
            from assistant.models import ImprovementTaskModel

            # Known false positive patterns — common verbs/conversational words
            # that were incorrectly flagged as potential data types
            false_positive_words = {
                'pick', 'picked', 'picking',
                'choose', 'chose', 'chosen',
                'select', 'selected',
                'grab', 'handle',
                'turn', 'push', 'pull', 'drop',
                'point', 'cover', 'focus', 'share',
                'mark', 'save', 'load', 'switch',
                'scroll', 'type', 'enter', 'exit', 'press', 'sign',
            }

            # Find tasks with these false-positive titles
            from django.db.models import Q
            q_filter = Q()
            for word in false_positive_words:
                q_filter |= Q(title__iexact=f"Evaluate new data type: '{word}'")

            false_tasks = ImprovementTaskModel.objects.filter(q_filter)
            count = false_tasks.count()

            if count > 0:
                # Mark them as resolved/rejected
                false_tasks.update(status='rejected')
                if verbosity >= 1:
                    self.stdout.write(self.style.SUCCESS(
                        f'  Cleaned up {count} false-positive improvement task(s)'
                    ))

            self._mark_loader_complete(
                DataLoadConfig, loader_name,
                'False-positive improvement task cleanup (Feb 2026)',
                'command',
                'One-time cleanup of tasks created by overly aggressive gap detector'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(
                    f'False-positive improvement task cleanup FAILED: {e}'
                ))

    def _cleanup_calendar_duplicates(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time cleanup of duplicate calendar events for all users.

        Root cause: upsert_execution_block_for_task() bypassed CalendarMutationService
        dedup checks, creating duplicate execution blocks when both signal-triggered
        projection and AcceptSuggestionView fired for the same task.
        Only runs once (tracked via DataLoadConfig) unless force=True.
        """
        loader_name = 'cleanup_calendar_duplicates_2026_02_v2'

        if not force and self._is_loader_complete(DataLoadConfig, loader_name):
            return

        try:
            from collections import defaultdict
            from apps.calendar_engine.models import CalendarEvent

            # Get all active events
            events = CalendarEvent.objects.filter(
                status=CalendarEvent.STATUS_SCHEDULED,
                deleted_at__isnull=True,
            ).select_related('user')

            # Cache user timezones to avoid repeated DB hits
            _tz_cache = {}

            def _get_user_tz(user):
                if user.id not in _tz_cache:
                    try:
                        from zoneinfo import ZoneInfo
                        _tz_cache[user.id] = ZoneInfo(user.preferences.timezone_iana)
                    except Exception:
                        from django.utils import timezone as dj_tz
                        _tz_cache[user.id] = dj_tz.utc
                return _tz_cache[user.id]

            # Group by (user_id, title_lower, local_date) — must use user's
            # local date, not UTC date, to correctly group near midnight
            groups = defaultdict(list)
            for event in events:
                user_tz = _get_user_tz(event.user)
                local_date = event.start_dt.astimezone(user_tz).date()
                key = (event.user_id, event.title.strip().lower(), local_date)
                groups[key].append(event)

            # Find duplicates and soft-delete lower-priority copies
            total_deleted = 0
            for key, group in groups.items():
                if len(group) <= 1:
                    continue

                # Sort: protected > execution_block > longer duration > newest
                group.sort(key=lambda e: (
                    e.is_protected,
                    e.event_kind == CalendarEvent.KIND_EXECUTION_BLOCK,
                    (e.end_dt - e.start_dt).total_seconds(),
                    e.created_at,
                ))
                keeper = group[-1]
                for dupe in group[:-1]:
                    dupe.soft_delete()
                    total_deleted += 1

            if total_deleted > 0 and verbosity >= 1:
                self.stdout.write(self.style.SUCCESS(
                    f'  Calendar dedup: soft-deleted {total_deleted} duplicate events'
                ))

            self._mark_loader_complete(
                DataLoadConfig, loader_name,
                'Calendar duplicate cleanup (Feb 2026)',
                'command',
                'One-time cleanup of duplicate calendar events caused by projection bypass'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Calendar dedup cleanup FAILED: {e}'))

    def _reset_cos_performance_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for CoS Performance & Reliability (PK 106).
        """
        reset_tracker_name = 'reset_beth_performance_2026_02_28'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            config = DataLoadConfig.objects.get(loader_name='release_notes')
            if config.is_loaded:
                config.is_loaded = False
                config.save()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset release_notes loader for CoS Performance & Reliability')

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for CoS Performance & Reliability release note (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 106'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset CoS performance fixtures FAILED: {e}'))

    def _reset_teaching_destinations_dedup(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload teaching_destinations after fixing duplicate PK 58.
        Notification Center was overwriting Recurring Transactions due to shared PK.
        """
        reset_tracker_name = 'reset_teaching_destinations_dedup_2026_02_28'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            config = DataLoadConfig.objects.get(loader_name='teaching_destinations')
            if config.is_loaded:
                config.is_loaded = False
                config.save()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset teaching_destinations loader to fix duplicate PK 58')

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Fix teaching_destinations duplicate PK 58 (Feb 2026)',
                'command',
                'One-time reset to reload teaching_destinations with deduplicated PKs'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset teaching_destinations dedup FAILED: {e}'))

    def _reset_boot_hardening_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for Boot Architecture Hardening (PK 107).
        """
        reset_tracker_name = 'reset_boot_hardening_2026_02_28'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            config = DataLoadConfig.objects.get(loader_name='release_notes')
            if config.is_loaded:
                config.is_loaded = False
                config.save()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset release_notes loader for Boot Architecture Hardening')

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Boot Architecture Hardening (Feb 2026)',
                'command',
                'One-time reset to reload release_notes PK 107'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset boot hardening fixtures FAILED: {e}'))

    def _reset_cos_name_fix_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes after fixing 'Beth' → 'CoS' in PK 106.
        """
        reset_tracker_name = 'reset_cos_name_fix_2026_03_01'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            config = DataLoadConfig.objects.get(loader_name='release_notes')
            if config.is_loaded:
                config.is_loaded = False
                config.save()
                if verbosity >= 1:
                    self.stdout.write(f'  Reset release_notes loader for CoS name fix (PK 106)')

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures to fix Beth → CoS in release note PK 106 (Mar 2026)',
                'command',
                'One-time reset to reload release_notes PK 106 with corrected name'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset CoS name fix fixtures FAILED: {e}'))

    def _reset_notes_module_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures for Notes module.
        - release_notes PK 108 (Notes feature announcement)
        - teaching_destinations PK 158-159 (Notes list + create)
        - help_topics PK 102-105 (Notes list, create, detail, edit)
        """
        reset_tracker_name = 'reset_notes_module_2026_03_01'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for loader_name in ['release_notes', 'teaching_destinations', 'help_topics']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader_name} loader for Notes module')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Notes module (Mar 2026)',
                'command',
                'One-time reset to reload release_notes PK 108, teaching_destinations PK 158-159, help_topics PK 102-105'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset notes module fixtures FAILED: {e}'))

    def _reset_vision_analysis_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures for Vision AI Analysis.
        - release_notes PK 109
        - help_topics PK 103-105 (updated with image upload info)
        """
        reset_tracker_name = 'reset_vision_analysis_2026_03_02'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for loader_name in ['release_notes', 'help_topics']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader_name} loader for Vision AI Analysis')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Vision AI Analysis (Mar 2026)',
                'command',
                'One-time reset to reload release_notes PK 109, help_topics PK 103-105'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset vision analysis fixtures FAILED: {e}'))

    def _reset_meals_intelligence_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload fixtures for Meal Intelligence UI.
        - release_notes PK 112
        - teaching_destinations PKs 160-165
        """
        reset_tracker_name = 'reset_meals_intelligence_2026_03_02'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for loader_name in ['release_notes', 'teaching_destinations']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader_name} loader for Meal Intelligence')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Meal Intelligence UI (Mar 2026)',
                'command',
                'One-time reset to reload release_notes PK 112, teaching_destinations PKs 160-165'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset meals intelligence fixtures FAILED: {e}'))

    def _reset_meals_activation_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload teaching_destinations for Meals Setup Wizard (PK 166).
        """
        reset_tracker_name = 'reset_meals_activation_2026_03_02'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='teaching_destinations')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset teaching_destinations loader for Meals Activation')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Meals Activation (Mar 2026)',
                'command',
                'One-time reset to reload teaching_destinations PK 166'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset meals activation fixtures FAILED: {e}'))

    def _reset_pantry_photo_intelligence_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes (PK 113) and teaching_destinations (PK 167)
        for Phase 12 Pantry Photo Intelligence.
        """
        reset_tracker_name = 'reset_pantry_photo_intelligence_2026_03_02'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for loader in ['release_notes', 'teaching_destinations']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader} loader for Pantry Photo Intelligence')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Pantry Photo Intelligence (Phase 12)',
                'command',
                'One-time reset to reload release_notes PK 113, teaching_destinations PK 167'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset pantry photo intelligence fixtures FAILED: {e}'))

    def _reset_relationship_intelligence_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes (PK 114) and teaching_destinations (PK 168-169)
        for Phase R1 Relational Intelligence.
        """
        reset_tracker_name = 'reset_relationship_intelligence_2026_03_02'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for loader in ['release_notes', 'teaching_destinations']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader} loader for Relational Intelligence')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Relational Intelligence (Phase R1)',
                'command',
                'One-time reset to reload release_notes PK 114, teaching_destinations PK 168-169'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset relationship intelligence fixtures FAILED: {e}'))

    def _reset_relationship_insights_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes (PK 115) and teaching_destinations (PK 170)
        for Phase R2 Relationship Insights Dashboard.
        """
        reset_tracker_name = 'reset_relationship_insights_2026_03_02'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for loader in ['release_notes', 'teaching_destinations']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader} loader for Relationship Insights')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Relationship Insights (Phase R2)',
                'command',
                'One-time reset to reload release_notes PK 115, teaching_destinations PK 170'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset relationship insights fixtures FAILED: {e}'))

    def _reset_relationships_module_definition_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload module_definitions fixture to add Relationships module (PK 10).
        """
        reset_tracker_name = 'reset_relationships_module_def_2026_03_02'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='module_definitions')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset module_definitions loader for Relationships module')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset module_definitions for Relationships module',
                'command',
                'One-time reset to reload module_definitions with PK 10 (Relationships/People)'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset relationships module definition fixtures FAILED: {e}'))

    def _reset_relationships_nav_route_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload module_definitions fixture to change Relationships nav route
        from person_list to insights.
        """
        reset_tracker_name = 'reset_relationships_nav_route_2026_03_02'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='module_definitions')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset module_definitions loader for Relationships nav route change')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset module_definitions for Relationships nav route',
                'command',
                'One-time reset to change route from person_list to insights'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset relationships nav route fixtures FAILED: {e}'))

    def _reset_meals_power_preview_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes (PK 116) and help_topics (PKs 106-112)
        for Meal Intelligence Phase 11: Power Preview & Anticipation Layer.
        Also reloads help_topics for all MEALS_* context IDs (MEALS_DASHBOARD,
        MEALS_SUGGESTIONS, MEALS_PANTRY, MEALS_PLAN, MEALS_RECEIPTS,
        MEALS_RECIPE_DETAIL, MEALS_SETUP).
        """
        reset_tracker_name = 'reset_meals_power_preview_2026_03_02'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for loader in ['release_notes', 'help_topics']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader} loader for Meals Power Preview (Phase 11)')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Meals Power Preview & Anticipation Layer (Phase 11)',
                'command',
                'One-time reset to reload release_notes PK 116, help_topics PKs 106-112 (MEALS_* contexts)'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset meals power preview fixtures FAILED: {e}'))

    def _reset_recipe_photo_import_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes (PK 114), teaching_destinations (PK 171),
        and help_topics (PK 113) for Recipe Photo Import feature.
        """
        reset_tracker_name = 'reset_recipe_photo_import_docs_2026_03_02'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for loader in ['release_notes', 'teaching_destinations', 'help_topics']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader} loader for Recipe Photo Import')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Recipe Photo Import',
                'command',
                'One-time reset to reload release_notes PK 114, teaching_destinations PK 171, help_topics PK 113'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset recipe photo import fixtures FAILED: {e}'))

    def _reset_group_mentions_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes fixture for @Group Mentions (PK 119).
        """
        reset_tracker_name = 'reset_group_mentions_release_2026_03_02'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes loader for @Group Mentions')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for @Group Mentions',
                'command',
                'One-time reset to reload release_notes with PK 119 (@Group Mentions)'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset group mentions fixtures FAILED: {e}'))

    def _reset_contact_import_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes fixture for Contact Import (PK 120).
        """
        reset_tracker_name = 'reset_contact_import_release_2026_03_02'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes loader for Contact Import')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for Contact Import',
                'command',
                'One-time reset to reload release_notes with PK 120 (Contact Import)'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset contact import fixtures FAILED: {e}'))

    def _restore_beth_deleted_tasks(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time: Restore tasks incorrectly deleted by AI on 2026-03-02.

        The AI misinterpreted "you shouldn't show everything" (a display preference)
        as "delete all these tasks" and soft-deleted Beth's tasks. This restores them.

        Note: deleted_at is stored in UTC. Beth deleted at ~7:14 PM Central (March 2)
        which is ~1:14 AM UTC March 3, so we search both dates.
        """
        # v2 tracker — v1 ran with wrong date filter and found 0 tasks
        tracker_name = 'restore_beth_deleted_tasks_2026_03_02_v2'
        try:
            if self._is_loader_complete(DataLoadConfig, tracker_name):
                return

            from apps.life.models import Task
            from django.utils import timezone as tz
            import datetime

            # Find Beth's user account
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                beth = User.objects.get(email='heatherljenkins@gmail.com')
            except User.DoesNotExist:
                if verbosity >= 1:
                    self.stdout.write('  Beth user not found, skipping task restore')
                self._mark_loader_complete(
                    DataLoadConfig, tracker_name,
                    'Restore Beth deleted tasks (user not found)',
                    'command', 'User not found'
                )
                return

            # Search March 2-3 UTC to cover the timezone gap
            # (7 PM Central on March 2 = 1 AM UTC March 3)
            start_utc = tz.make_aware(
                datetime.datetime(2026, 3, 2, 0, 0),
                datetime.timezone.utc,
            )
            end_utc = tz.make_aware(
                datetime.datetime(2026, 3, 4, 0, 0),
                datetime.timezone.utc,
            )
            deleted_tasks = Task.all_objects.filter(
                user=beth,
                status='deleted',
                deleted_at__gte=start_utc,
                deleted_at__lt=end_utc,
            )

            restored_count = 0
            for task in deleted_tasks:
                task.restore()
                restored_count += 1
                if verbosity >= 1:
                    self.stdout.write(f'  Restored task: {task.title}')

            if verbosity >= 1:
                if restored_count > 0:
                    self.stdout.write(self.style.SUCCESS(
                        f'  Restored {restored_count} incorrectly deleted tasks for Beth'
                    ))
                else:
                    self.stdout.write('  No deleted tasks found for Beth on 2026-03-02/03')

            self._mark_loader_complete(
                DataLoadConfig, tracker_name,
                'Restore Beth deleted tasks (2026-03-02 v2)',
                'command',
                f'Restored {restored_count} tasks incorrectly deleted by AI'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Restore Beth tasks FAILED: {e}'))

    def _reset_calendar_add_task_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes (PK 121) for Calendar Add Task button
        and time display/DST fixes.
        """
        reset_tracker_name = 'reset_calendar_add_task_2026_03_02'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes loader for Calendar Add Task')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Calendar Add Task + Time Fixes',
                'command',
                'One-time reset to reload release_notes PK 121'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset calendar add task fixtures FAILED: {e}'))

    def _reset_global_mention_autocomplete_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes (PK 122) for global @mention
        autocomplete across all text fields.
        """
        reset_tracker_name = 'reset_global_mention_autocomplete_2026_03_02'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes loader for Global @Mention Autocomplete')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Global @Mention Autocomplete',
                'command',
                'One-time reset to reload release_notes PK 122'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset global mention autocomplete fixtures FAILED: {e}'))

    def _reset_ios_contact_import_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes (PK 123) for iOS native contact
        picker import feature.
        """
        reset_tracker_name = 'reset_ios_contact_import_2026_03_02'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes loader for iOS Contact Import')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for iOS Contact Import',
                'command',
                'One-time reset to reload release_notes PK 123'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset iOS contact import fixtures FAILED: {e}'))

    def _reset_context_aware_help_system_review(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload help_topics (PKs 114-145) and teaching_destinations
        (PKs 172-174) for comprehensive context-aware help system review.
        Adds help coverage to capture, core, medical, relationships, billing, and sms modules.
        """
        reset_tracker_name = 'reset_context_aware_help_review_2026_03_03'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for fixture_name in ['help_topics', 'teaching_destinations']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=fixture_name)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {fixture_name} loader for context-aware help system review')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for context-aware help system review',
                'command',
                'One-time reset to reload help_topics PKs 114-145 and teaching_destinations PKs 172-174'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset context-aware help system review FAILED: {e}'))

    def _reset_help_system_release_note(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes (PK 124) for context-aware help
        system enhancement release note.
        """
        reset_tracker_name = 'reset_help_system_release_note_2026_03_03'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes loader for context-aware help release note')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for context-aware help release note',
                'command',
                'One-time reset to reload release_notes PK 124'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset help system release note FAILED: {e}'))

    def _reset_multi_image_cos_release_note(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes (PK 125) for multi-image CoS
        chat enhancement release note.
        """
        reset_tracker_name = 'reset_multi_image_cos_release_note_2026_03_03'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes loader for multi-image CoS release note')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for multi-image CoS release note',
                'command',
                'One-time reset to reload release_notes PK 125'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset multi-image CoS release note FAILED: {e}'))

    def _reset_morning_automation_release_note(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes (PK 126) for state-aware
        morning automation release note.
        """
        reset_tracker_name = 'reset_morning_automation_release_note_2026_03_03'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes loader for morning automation release note')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for morning automation release note',
                'command',
                'One-time reset to reload release_notes PK 126'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset morning automation release note FAILED: {e}'))

    def _reset_cos_deterministic_coaching_release_note(self, DataLoadConfig, force=False, verbosity=1):
        """One-time reset to reload release_notes for CoS deterministic coaching upgrade (PK 127)."""
        reset_tracker_name = 'reset_cos_deterministic_coaching_2026_03_03'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes loader for CoS deterministic coaching release note')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for CoS deterministic coaching release note',
                'command',
                'One-time reset to reload release_notes PK 127'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset CoS deterministic coaching release note FAILED: {e}'))

    def _reset_tile_card_mention_help_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes (PK 128 tile cards) and
        help_topics (updated RELATIONSHIPS_PEOPLE with @mention autocomplete docs).
        """
        reset_tracker_name = 'reset_tile_card_mention_help_2026_03_03'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for fixture_name in ('release_notes', 'help_topics'):
                try:
                    config = DataLoadConfig.objects.get(loader_name=fixture_name)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {fixture_name} loader for tile card + mention help')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for tile card redesign + @mention help',
                'command',
                'One-time reset to reload release_notes PK 128 + help_topics RELATIONSHIPS_PEOPLE'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset tile card + mention help fixtures FAILED: {e}'))

    def _reset_select_all_batch_import_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes (PK 129, 130) for People list
        Select All + bulk actions and batch multi-select contact import.
        """
        reset_tracker_name = 'reset_select_all_batch_import_2026_03_03'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes loader for Select All + batch import')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Select All + batch contact import',
                'command',
                'One-time reset to reload release_notes PK 129, 130'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset select all + batch import fixtures FAILED: {e}'))

    def _reset_bulk_recipe_import_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes (PK 131) for Bulk Recipe Photo Import.
        """
        reset_tracker_name = 'reset_bulk_recipe_import_2026_03_03'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes loader for Bulk Recipe Photo Import')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Bulk Recipe Photo Import',
                'command',
                'One-time reset to reload release_notes PK 131'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset bulk recipe import fixtures FAILED: {e}'))

    def _reset_session_2026_03_04_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes (PKs 132-133) and teaching_destinations (PK 175)
        for expanded relationship types, multi-recipe photo detection, and prayer context.
        """
        reset_tracker_name = 'reset_session_2026_03_04'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for fixture_name in ('release_notes', 'teaching_destinations'):
                try:
                    config = DataLoadConfig.objects.get(loader_name=fixture_name)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {fixture_name} loader for session 2026-03-04 docs')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for session 2026-03-04 docs',
                'command',
                'One-time reset to reload release_notes PKs 132-133 and teaching_destinations PK 175'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset session 2026-03-04 fixtures FAILED: {e}'))

    def _reset_email_medicine_list_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes (PK 134), teaching_destinations,
        and help_topics for Email Medicine List feature.
        """
        reset_tracker_name = 'reset_email_medicine_list_2026_03_04'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for loader_name in ('release_notes', 'teaching_destinations', 'help_topics'):
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader_name} loader for Email Medicine List')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Email Medicine List',
                'command',
                'One-time reset to reload release_notes PK 134, teaching_destinations, help_topics'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset email medicine list fixtures FAILED: {e}'))

    def _reset_cross_completion_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for cross-completion and
        schedule awareness enhancements (PK 135).
        """
        reset_tracker_name = 'reset_cross_completion_2026_03_04'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for loader_name in ('release_notes',):
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader_name} loader for cross-completion')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for cross-completion enhancements',
                'command',
                'One-time reset to reload release_notes PK 135'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset cross-completion fixtures FAILED: {e}'))

    def _backfill_health_intelligence_enhancements(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time backfill for health intelligence enhancements (March 2026).

        Rebuilds DailyHealthSummary for last 90 days to populate new fields:
        plateau_risk_score, plateau_risk_label, plateau_prediction_window_days,
        fat_loss_phase, phase_confidence, phase_start_date, muscle_preservation_status.

        Only runs once (tracked via DataLoadConfig).
        """
        loader_name = 'backfill_health_intel_enhancements_2026_03'

        if not force and self._is_loader_complete(DataLoadConfig, loader_name):
            return

        try:
            if verbosity >= 1:
                self.stdout.write('  Backfilling health intelligence enhancements (90 days)...')

            from django.core.management import call_command
            call_command('build_daily_health_summaries', '--days', '90', verbosity=0)

            if verbosity >= 1:
                self.stdout.write(self.style.SUCCESS('  Health intelligence backfill complete'))

            self._mark_loader_complete(
                DataLoadConfig, loader_name,
                'Backfill Health Intelligence Enhancements',
                'command',
                'One-time 90-day backfill for plateau risk, fat loss phase, muscle preservation fields'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Health intelligence backfill FAILED: {e}'))

    def _reset_excel_export_report_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes (PKs 136-137) and
        teaching_destinations (PK 175) for Excel Export and CoS Report Generation features.
        """
        reset_tracker_name = 'reset_excel_export_report_2026_03_04'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for loader_name in ('release_notes', 'teaching_destinations'):
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader_name} loader for Excel Export + Report Generation')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Excel Export + CoS Report Generation',
                'command',
                'One-time reset to reload release_notes PKs 136-137, teaching_destinations PK 175'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Excel Export + Report fixtures FAILED: {e}'))

    def _reset_health_intelligence_ui_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes (PK 138), help_topics (PK 114),
        and teaching_destinations (PK 176) for Health Intelligence UI.
        """
        reset_tracker_name = 'reset_health_intelligence_ui_2026_03_05'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for loader_name in ('release_notes', 'help_topics', 'teaching_destinations'):
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader_name} loader for Health Intelligence UI')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Health Intelligence UI',
                'command',
                'One-time reset to reload release_notes PK 138, help_topics PK 114, teaching_destinations PK 176'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset health intelligence UI fixtures FAILED: {e}'))

    def _reset_relationships_tile_overhaul_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes (PK 136) for Relationships tile overhaul.
        """
        reset_tracker_name = 'reset_relationships_tile_overhaul_2026_03_05'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes loader for Relationships tile overhaul')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Relationships tile overhaul',
                'command',
                'One-time reset to reload release_notes PK 136'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset relationships tile overhaul fixtures FAILED: {e}'))

    def _rebuild_health_summaries_body_comp_fix(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time: backfill BodyCompositionEntry from historical WeightEntry data,
        then rebuild DailyHealthSummary for last 90 days.

        HealthKit stored body fat % and lean mass on WeightEntry but the SAE/UI/engine
        read from BodyCompositionEntry. This migrates historical data, then rebuilds
        summaries so intelligence picks it up.

        Only runs once (tracked via DataLoadConfig).
        """
        loader_name = 'backfill_body_comp_derived_2026_03_06c'

        if not force and self._is_loader_complete(DataLoadConfig, loader_name):
            return

        try:
            from django.core.management import call_command

            if verbosity >= 1:
                self.stdout.write('  Backfilling BodyCompositionEntry from WeightEntry...')
            call_command('backfill_body_composition', verbosity=1 if verbosity >= 1 else 0)

            if verbosity >= 1:
                self.stdout.write('  Rebuilding health summaries (90 days)...')
            call_command('build_daily_health_summaries', '--days', '90', verbosity=0)

            if verbosity >= 1:
                self.stdout.write(self.style.SUCCESS('  Body comp backfill + summary rebuild complete'))

            self._mark_loader_complete(
                DataLoadConfig, loader_name,
                'Backfill Body Comp + Rebuild Summaries',
                'command',
                'One-time backfill WeightEntry → BodyCompositionEntry + 90-day summary rebuild'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Body comp backfill/rebuild FAILED: {e}'))

    def _reset_guides_hub_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes (PK 138), teaching_destinations (PKs 176-178),
        and help_topics (PKs 146-147) for the Guides Hub feature.
        """
        reset_tracker_name = 'reset_guides_hub_2026_03_07'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for loader_name in ['release_notes', 'teaching_destinations', 'help_topics']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader_name} loader for Guides Hub')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Guides Hub (Data Dictionary + User Guide)',
                'command',
                'One-time reset to reload release_notes PK 138, teaching_destinations PKs 176-178, help_topics PKs 146-147'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Guides Hub fixtures FAILED: {e}'))

    def _reset_chat_error_recovery_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for friendly chat error recovery (PK 140).
        """
        reset_tracker_name = 'reset_chat_error_recovery_2026_03_07'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for loader_name in ['release_notes']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader_name} loader for chat error recovery')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for friendly chat error recovery',
                'command',
                'One-time reset to reload release_notes PK 140'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset chat error recovery fixtures FAILED: {e}'))

    def _reset_task_skip_status_fixtures(self, DataLoadConfig, force, verbosity):
        """
        One-time reset to reload release_notes for task skip status feature (PK 145).
        """
        reset_tracker_name = 'reset_task_skip_status_2026_03_08'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for loader_name in ['release_notes']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader_name} loader for task skip status')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for task skip status feature',
                'command',
                'One-time reset to reload release_notes PK 145',
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset task skip status fixtures FAILED: {e}'))

    def _reset_receipt_hardening_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes for receipt hardening improvements (PK 141).
        """
        reset_tracker_name = 'reset_receipt_hardening_2026_03_08'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for loader_name in ['release_notes']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader_name} loader for receipt hardening')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for receipt hardening improvements',
                'command',
                'One-time reset to reload release_notes PK 141',
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset receipt hardening fixtures FAILED: {e}'))

    def _reset_commitment_level_fixtures(self, DataLoadConfig, force, verbosity):
        """
        One-time reset to reload release_notes for commitment level feature (PK 146).
        """
        reset_tracker_name = 'reset_commitment_level_2026_03_09'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for loader_name in ['release_notes']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader_name} loader for commitment level')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for commitment level feature',
                'command',
                'One-time reset to reload release_notes PK 146'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset commitment level fixtures FAILED: {e}'))

    def _reset_personal_life_memory_fixtures(self, DataLoadConfig, force, verbosity):
        """
        One-time reset to reload release_notes for personal life memory feature (PK 149).
        """
        reset_tracker_name = 'reset_personal_life_memory_2026_03_09'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for loader_name in ['release_notes']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader_name} loader for personal life memory')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for personal life memory feature',
                'command',
                'One-time reset to reload release_notes PK 149'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset personal life memory fixtures FAILED: {e}'))

    def _reset_health_screenshot_interpretation_fixtures(self, DataLoadConfig, force, verbosity):
        """
        One-time reset to reload release_notes for PIE health screenshot interpretation (PK 152).
        """
        reset_tracker_name = 'reset_health_screenshot_interpretation_2026_03_10'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for loader_name in ['release_notes']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader_name} loader for health screenshot interpretation')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for health screenshot interpretation feature',
                'command',
                'One-time reset to reload release_notes PK 152'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset health screenshot interpretation fixtures FAILED: {e}'))

    def _reset_movement_type_fixtures(self, DataLoadConfig, force, verbosity):
        """
        One-time reset to reload release_notes for workout movement type upgrade (PK 153).
        """
        reset_tracker_name = 'reset_movement_type_2026_03_10'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for loader_name in ['release_notes']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader_name} loader for movement type upgrade')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for workout movement type upgrade',
                'command',
                'One-time reset to reload release_notes PK 153'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset movement type fixtures FAILED: {e}'))

    def _reset_action_governance_fixtures(self, DataLoadConfig, force, verbosity):
        """
        One-time reset to reload release_notes for CoS Action Governance upgrade (PK 154).
        """
        reset_tracker_name = 'reset_action_governance_2026_03_11'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for loader_name in ['release_notes']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader_name} loader for action governance upgrade')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for action governance upgrade',
                'command',
                'One-time reset to reload release_notes PK 154'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset action governance fixtures FAILED: {e}'))

    def _reset_beth_humanization_fixtures(self, DataLoadConfig, force, verbosity):
        """
        One-time reset to reload release_notes for Beth humanization (PK 155).
        """
        reset_tracker_name = 'reset_beth_humanization_2026_03_11'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for loader_name in ['release_notes']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader_name} loader for Beth humanization')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Beth humanization',
                'command',
                'One-time reset to reload release_notes PK 156'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Beth humanization fixtures FAILED: {e}'))

    def _reset_pgs_fixtures(self, DataLoadConfig, force, verbosity):
        """
        One-time reset to reload release_notes for PGS proactive guidance scheduler (PK 157).
        """
        reset_tracker_name = 'reset_pgs_2026_03_11'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for loader_name in ['release_notes']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader_name} loader for PGS')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for PGS proactive guidance scheduler',
                'command',
                'One-time reset to reload release_notes PK 157'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset PGS fixtures FAILED: {e}'))

    def _reset_deterministic_router_fixtures(self, DataLoadConfig, force, verbosity):
        """
        One-time reset to reload release_notes for LLM-last deterministic router (PK 158).
        """
        reset_tracker_name = 'reset_deterministic_router_2026_03_12'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for loader_name in ['release_notes']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader_name} loader for deterministic router')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for LLM-last deterministic router',
                'command',
                'One-time reset to reload release_notes PK 158'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset deterministic router fixtures FAILED: {e}'))

    def _reset_dashboard_v2_fixtures(self, DataLoadConfig, force, verbosity):
        """
        One-time reset to reload release_notes for Dashboard V2 Life Command Center (PK 159).
        """
        reset_tracker_name = 'reset_dashboard_v2_2026_03_12'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for loader_name in ['release_notes']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader_name} loader for Dashboard V2')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for Dashboard V2 Life Command Center',
                'command',
                'One-time reset to reload release_notes PK 159'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Dashboard V2 fixtures FAILED: {e}'))

    def _reset_option_bubbles_fixtures(self, DataLoadConfig, force, verbosity):
        """
        One-time reset to reload release_notes for A/B/C interactive option bubbles (PK 164).
        """
        reset_tracker_name = 'reset_option_bubbles_2026_03_13'
        try:
            if DataLoadConfig.objects.filter(loader_name=reset_tracker_name, is_loaded=True).exists():
                return

            for loader_name in ['release_notes']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader_name} loader for A/B/C option bubbles')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for A/B/C interactive option bubbles',
                'command',
                'One-time reset to reload release_notes PK 164'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset option bubbles fixtures FAILED: {e}'))

    def _reset_notes_module_definition_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload module_definitions fixture to add Notes module (PK 11).
        """
        reset_tracker_name = 'reset_notes_module_def_2026_03_16'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='module_definitions')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset module_definitions loader for Notes module')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset module_definitions for Notes module',
                'command',
                'One-time reset to reload module_definitions with PK 11 (Notes)'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset notes module definition fixtures FAILED: {e}'))

    def _reset_ui_alignment_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes, help_topics, teaching_destinations,
        and module_definitions for UI Alignment Phase (Routines UI + nav expansion).
        """
        reset_tracker_name = 'reset_ui_alignment_2026_03_18'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return

            for loader_name in ['release_notes', 'help_topics', 'teaching_destinations']:
                try:
                    config = DataLoadConfig.objects.get(loader_name=loader_name)
                    if config.is_loaded:
                        config.is_loaded = False
                        config.save()
                        if verbosity >= 1:
                            self.stdout.write(f'  Reset {loader_name} loader for UI Alignment Phase')
                except DataLoadConfig.DoesNotExist:
                    pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset fixtures for UI Alignment Phase',
                'command',
                'One-time reset: release_notes PKs 165-166, help_topics PK 147, teaching_destinations PK 178'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset UI alignment fixtures FAILED: {e}'))

    def _reset_beth_decisive_behavior_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload coaching_styles fixture with decisive behavior updates.
        Supportive Partner style updated: removed hedging, added action-first + foundational.
        """
        reset_tracker_name = 'reset_beth_decisive_2026_03_18'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='coaching_styles')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset coaching_styles for decisive behavior update')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset coaching_styles for Beth decisive behavior',
                'command',
                'One-time reset: supportive partner style updated with action-first language'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Beth decisive behavior fixtures FAILED: {e}'))

    def _reset_routine_execution_truth_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes with Routine Execution Truth entry (PK 169).
        """
        reset_tracker_name = 'reset_routine_execution_truth_2026_03_23'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for Routine Execution Truth')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for routine execution truth',
                'command',
                'One-time reset: added PKs 169-170 for execution truth + morning reconciliation'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset routine execution truth fixtures FAILED: {e}'))

    def _reset_activity_workouts_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes with Activity-Based Workouts entry (PK 180).
        """
        reset_tracker_name = 'reset_activity_workouts_2026_04_04'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for Activity-Based Workouts')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for activity-based workouts',
                'command',
                'One-time reset: added PK 180 for activity-based workouts'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset activity workouts fixtures FAILED: {e}'))

    def _reset_supplement_tracking_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes with Supplement Tracking entry (PK 181).
        """
        reset_tracker_name = 'reset_supplement_tracking_2026_04_05'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for Supplement Tracking')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for supplement tracking',
                'command',
                'One-time reset: added PK 181 for unified intake system'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset supplement tracking fixtures FAILED: {e}'))

    def _reset_whats_new_timestamp_fix_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes after fixing PK 182's created_at
        from noon UTC to midnight UTC. The noon UTC value caused
        ReleaseNote.get_unseen_for_user() to re-show the popup on every refresh
        for users dismissing earlier in the UTC day, because the same-day-late-
        addition clause (`created_at > last_viewed_at`) kept evaluating True.
        """
        reset_tracker_name = 'reset_whats_new_timestamp_fix_2026_04_07'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write(
                            '  Reset release_notes for whats-new timestamp fix'
                        )
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for whats-new timestamp fix',
                'command',
                'One-time reset: PK 182 created_at moved from noon UTC to midnight UTC',
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(
                    f'Reset whats-new timestamp fix fixtures FAILED: {e}'
                ))

    def _reset_cdce_fasting_gating_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes with the CDCE fasting/workout
        false-correlation fix entry (PK 182).
        """
        reset_tracker_name = 'reset_cdce_fasting_gating_2026_04_07'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for CDCE fasting gating fix')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for CDCE fasting gating fix',
                'command',
                'One-time reset: added PK 182 for cross-domain insights gating',
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset CDCE fasting gating fixtures FAILED: {e}'))

    def _reset_workout_tomorrow_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes with Workout-Tomorrow Hardening
        entry (PK 183). Pairs with the 2026-04-07 hardening pass that fixed the
        "What is my workout tomorrow?" hallucination and generalized future-tense
        protection across every per-domain summary matcher.
        """
        reset_tracker_name = 'reset_workout_tomorrow_2026_04_07'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for Workout-Tomorrow Hardening')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for workout-tomorrow hardening',
                'command',
                'One-time reset: added PK 183 for future-tense workout query fix'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset workout tomorrow fixtures FAILED: {e}'))

    def _reset_phase_11_intent_aware_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        reset_tracker_name = 'reset_phase_11_intent_aware_2026_04_09'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for Phase 11 Intent-Aware')
            except DataLoadConfig.DoesNotExist:
                pass
            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for Phase 11 Intent-Aware',
                'command',
                'One-time reset: added PK 195 for Phase 11 intent-aware decision modes'
            )
        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Phase 11 intent-aware fixtures FAILED: {e}'))

    def _reset_phase_10_action_selection_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        reset_tracker_name = 'reset_phase_10_action_selection_2026_04_09'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for Phase 10 Action Selection')
            except DataLoadConfig.DoesNotExist:
                pass
            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for Phase 10 Action Selection',
                'command',
                'One-time reset: added PK 194 for Phase 10 action selection'
            )
        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Phase 10 action selection fixtures FAILED: {e}'))

    def _reset_phase_9_execution_first_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        reset_tracker_name = 'reset_phase_9_execution_first_2026_04_09'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for Phase 9 Execution-First')
            except DataLoadConfig.DoesNotExist:
                pass
            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for Phase 9 Execution-First',
                'command',
                'One-time reset: added PK 193 for Phase 9 execution-first decision selection'
            )
        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Phase 9 execution-first fixtures FAILED: {e}'))

    def _reset_phase_8_decision_hard_lock_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes with Phase 8 Decision
        Hard Lock entry (PK 192). Surfaces the structural guarantee
        that decision queries always produce Action-First responses.
        """
        reset_tracker_name = 'reset_phase_8_decision_hard_lock_2026_04_09'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for Phase 8 Decision Hard Lock')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for Phase 8 Decision Hard Lock',
                'command',
                'One-time reset: added PK 192 for Phase 8 decision hard lock'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Phase 8 decision hard lock fixtures FAILED: {e}'))

    def _reset_phase_7_decision_intelligence_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes with Phase 7 CoS
        Decision Intelligence entry (PK 191). Surfaces the decision
        contract upgrades: ACTION DISCIPLINE, PRIORITY ORDER,
        CROSS-DOMAIN PATTERNS, TOP-RANKED SIGNAL fallback, and the
        weasel-phrase validator extension.
        """
        reset_tracker_name = 'reset_phase_7_decision_intelligence_2026_04_09'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for Phase 7 Decision Intelligence')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for Phase 7 Decision Intelligence',
                'command',
                'One-time reset: added PK 191 for Phase 7 CoS decision intelligence'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Phase 7 decision intelligence fixtures FAILED: {e}'))

    def _reset_phase_6_cross_layer_truth_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes with Phase 6 Cross-Layer
        Truth Validation entry (PK 190). Surfaces the adherence /
        sleep / workout rolling-signal fresh-read fix and the labs
        AttributeError repair.
        """
        reset_tracker_name = 'reset_phase_6_cross_layer_truth_2026_04_08'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for Phase 6 Cross-Layer Truth')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for Phase 6 Cross-Layer Truth',
                'command',
                'One-time reset: added PK 190 for Phase 6 cross-layer truth validation'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Phase 6 cross-layer truth fixtures FAILED: {e}'))

    def _reset_phase_5_feature_gating_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes with Phase 5 Feature
        Gating entry (PK 189). Surfaces the nutrition/health/finance
        builder gates and the five insight-rule guards.
        """
        reset_tracker_name = 'reset_phase_5_feature_gating_2026_04_08'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for Phase 5 Feature Gating')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for Phase 5 Feature Gating',
                'command',
                'One-time reset: added PK 189 for Phase 5 feature gating'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Phase 5 feature gating fixtures FAILED: {e}'))

    def _reset_phase_4_unit_consistency_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes with Phase 4 Unit
        Consistency entry (PK 188). Surfaces the adherence-scaling
        fixes and the reconnected dead insight rules.
        """
        reset_tracker_name = 'reset_phase_4_unit_consistency_2026_04_08'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for Phase 4 Unit Consistency')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for Phase 4 Unit Consistency',
                'command',
                'One-time reset: added PK 188 for Phase 4 unit consistency'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Phase 4 unit consistency fixtures FAILED: {e}'))

    def _reset_phase_3_signal_completion_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes with Phase 3 Signal
        Completion entry (PK 187). Adds user-facing announcement for
        sleep_trend / body_fat_trend / waist_trend /
        last_workout_days_ago signals.
        """
        reset_tracker_name = 'reset_phase_3_signal_completion_2026_04_08'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for Phase 3 Signal Completion')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for Phase 3 Signal Completion',
                'command',
                'One-time reset: added PK 187 for Phase 3 signal completion'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Phase 3 signal completion fixtures FAILED: {e}'))

    def _reset_phase_6_8_lifecycle_visibility_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes with Phase 6.8 Lifecycle
        Visibility + Duplicate UX entry (PK 186). Adds the user-facing
        announcement for status badges, recovered-message styling, and
        the dedicated duplicate-request card.
        """
        reset_tracker_name = 'reset_phase_6_8_lifecycle_visibility_2026_04_08'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for Phase 6.8 Lifecycle Visibility')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for Phase 6.8 Lifecycle Visibility',
                'command',
                'One-time reset: added PK 186 for Phase 6.8 lifecycle visibility + duplicate UX'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Phase 6.8 lifecycle visibility fixtures FAILED: {e}'))

    def _reset_phase_6_7_execution_isolation_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes with Phase 6.7 Execution
        Isolation + Input Persistence entry (PK 185). Announces the
        user-facing fix for request interruption, draft persistence, and
        context-aware queries.
        """
        reset_tracker_name = 'reset_phase_6_7_execution_isolation_2026_04_08'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for Phase 6.7 Execution Isolation')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for Phase 6.7 Execution Isolation',
                'command',
                'One-time reset: added PK 185 for Phase 6.7 execution isolation + input persistence'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Phase 6.7 execution isolation fixtures FAILED: {e}'))

    def _reset_phase_6_6_confirmation_ux_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes with Phase 6.6 Confirmation UX
        entry (PK 184). Adds the user-facing announcement for the rebuilt
        CRUD confirmation flow (Action/Details/Impact, Before/After for
        updates, always-present A/B/C pills, task-class warnings).
        """
        reset_tracker_name = 'reset_phase_6_6_confirmation_ux_2026_04_08'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for Phase 6.6 Confirmation UX')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for Phase 6.6 Confirmation UX',
                'command',
                'One-time reset: added PK 184 for Phase 6.6 confirmation UX rebuild'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Phase 6.6 confirmation UX fixtures FAILED: {e}'))

    def _reset_cos_naming_boundary_fixtures(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes after replacing all 'Beth' references
        with 'Chief of Staff' to enforce the CoS naming boundary.
        """
        reset_tracker_name = 'reset_cos_naming_boundary_2026_04_05'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for CoS naming boundary fix')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for CoS naming boundary',
                'command',
                'One-time reset: replaced Beth with Chief of Staff in all release notes'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset CoS naming boundary fixtures FAILED: {e}'))

    def _reset_gospel_plan_consistency_release_notes(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes after adding PK 196 (Gospel reading-plan
        consistency rebuild — John / Luke / Matthew / Mark canonical structure).
        """
        reset_tracker_name = 'reset_gospel_plan_consistency_2026_05_16'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for Gospel reading-plan consistency (PK 196)')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for Gospel plan consistency',
                'command',
                'One-time reset: added PK 196 for Gospel reading-plan consistency rebuild'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Gospel plan consistency release notes FAILED: {e}'))

    def _reset_dashboard_v3_preview_release_notes(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes after adding PK 198 (dashboard_v3
        experimental preview — Chief-of-Staff-first dashboard at /dashboard-v3/).
        """
        reset_tracker_name = 'reset_dashboard_v3_preview_2026_05_26'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for dashboard_v3 preview (PK 198)')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for dashboard_v3 preview',
                'command',
                'One-time reset: added PK 198 for dashboard_v3 experimental preview'
            )
        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset dashboard_v3 preview release notes FAILED: {e}'))

    def _reset_primary_mission_release_notes(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes after adding PK 199 (Primary
        Mission selection — user explicitly chooses one Goal as their featured
        dashboard Mission and Chief-of-Staff coaching focus).
        """
        reset_tracker_name = 'reset_primary_mission_2026_05_31'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for Primary Mission (PK 199)')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for Primary Mission',
                'command',
                'One-time reset: added PK 199 for Primary Mission selection'
            )
        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Primary Mission release notes FAILED: {e}'))

    def _reset_mission_hero_release_notes(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes after adding PK 200 (Mission
        hero card — premium North Star visual with deterministic milestone
        progression ring).
        """
        reset_tracker_name = 'reset_mission_hero_2026_05_31_v2'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for Mission hero card (PK 200)')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for Mission hero card',
                'command',
                'One-time reset: added PK 200 for Mission hero card'
            )
        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Mission hero release notes FAILED: {e}'))

    def _reset_mission_intelligence_release_notes(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes after adding PK 201 (Mission
        Intelligence v1 — deterministic mission-state classifier surfaced on
        the Primary Mission hero card).
        """
        reset_tracker_name = 'reset_mission_intelligence_2026_05_31'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for Mission Intelligence (PK 201)')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for Mission Intelligence',
                'command',
                'One-time reset: added PK 201 for Mission Intelligence v1'
            )
        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Mission Intelligence release notes FAILED: {e}'))

    def _reset_mission_movement_release_notes(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes after adding PK 202 (Mission
        Phase 3.5 — adaptive, phase-aware Movement signal replacing step-only
        activity judgement on the Primary Mission card).
        """
        reset_tracker_name = 'reset_mission_movement_2026_05_31'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for Mission Movement (PK 202)')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for Mission Movement',
                'command',
                'One-time reset: added PK 202 for Mission Phase 3.5 Movement signal'
            )
        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Mission Movement release notes FAILED: {e}'))

    def _reset_mission_worth_watching_release_notes(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes after adding PK 203 (Mission
        Phase 4 — adaptive recovery interpretation + the new "Worth watching"
        middle column on the Primary Mission card).
        """
        reset_tracker_name = 'reset_mission_worth_watching_2026_05_31'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for Mission Worth Watching (PK 203)')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for Mission Worth Watching',
                'command',
                'One-time reset: added PK 203 for Mission Phase 4 Worth Watching'
            )
        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Mission Worth Watching release notes FAILED: {e}'))

    def _reset_mission_inspiration_release_notes(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes after adding PK 204 (Mission
        Phase 5 — emotional motivation layer: hero image, mission links, and
        lightweight victory wins on the Primary Mission).
        """
        reset_tracker_name = 'reset_mission_inspiration_2026_05_31'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for Mission Inspiration (PK 204)')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for Mission Inspiration',
                'command',
                'One-time reset: added PK 204 for Mission Phase 5 Inspiration layer'
            )
        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Mission Inspiration release notes FAILED: {e}'))

    def _reset_mission_actionable_a1c_release_notes(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes after adding PK 205 (Mission
        Phase 6 — clickable action drivers + the Projected A1C mission signal).
        """
        reset_tracker_name = 'reset_mission_actionable_a1c_2026_05_31'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for Mission Actionable + A1C (PK 205)')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for Mission Actionable + A1C',
                'command',
                'One-time reset: added PK 205 for Mission Phase 6 actionable drivers + Projected A1C'
            )
        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Mission Actionable A1C release notes FAILED: {e}'))

    def _reset_mission_gmi_accuracy_release_notes(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes after adding PK 206 (Mission
        Phase 6.1 — clinically-accurate Projected A1C / standard GMI + resilient
        confidence tiers).
        """
        reset_tracker_name = 'reset_mission_gmi_accuracy_2026_05_31'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for Projected A1C GMI accuracy (PK 206)')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for Projected A1C GMI accuracy',
                'command',
                'One-time reset: added PK 206 for Mission Phase 6.1 standard-GMI Projected A1C'
            )
        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Mission GMI accuracy release notes FAILED: {e}'))

    def _reset_mission_a1c_always_visible_release_notes(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes after adding PK 207 (Mission
        Phase 6.3 — Projected A1C (GMI) slot always renders an honest state and
        never silently disappears).
        """
        reset_tracker_name = 'reset_mission_a1c_always_visible_2026_05_31'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for A1C always-visible (PK 207)')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for A1C always-visible',
                'command',
                'One-time reset: added PK 207 for Mission Phase 6.3 always-visible Projected A1C'
            )
        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Mission A1C always-visible release notes FAILED: {e}'))

    def _reset_mission_a1c_truth_release_notes(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes after adding PK 208 (Mission
        Phase 6.4 — Projected A1C (GMI) honestly labeled as a CGM-derived
        estimate, trend-aware classification, and the Nutrition link fix).
        """
        reset_tracker_name = 'reset_mission_a1c_truth_2026_05_31'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return
            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for A1C truth model (PK 208)')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for A1C truth model',
                'command',
                'One-time reset: added PK 208 for Mission Phase 6.4 A1C/GMI truth model + nutrition link'
            )
        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Mission A1C truth release notes FAILED: {e}'))

    def _reset_action_center_vocabulary_release_notes(self, DataLoadConfig, force=False, verbosity=1):
        """
        One-time reset to reload release_notes after adding PK 197 (Action Center
        vocabulary fix — removing punitive "EXPIRED" labels, aligning with the
        Recovery Contract philosophy: "behind" for past-window items,
        "missed" reserved for genuinely time-locked HARD_EXPIRED items).
        """
        reset_tracker_name = 'reset_action_center_vocabulary_2026_05_17'
        try:
            if self._is_loader_complete(DataLoadConfig, reset_tracker_name):
                return

            try:
                config = DataLoadConfig.objects.get(loader_name='release_notes')
                if config.is_loaded:
                    config.is_loaded = False
                    config.save()
                    if verbosity >= 1:
                        self.stdout.write('  Reset release_notes for Action Center vocabulary (PK 197)')
            except DataLoadConfig.DoesNotExist:
                pass

            self._mark_loader_complete(
                DataLoadConfig, reset_tracker_name,
                'Reset release_notes for Action Center vocabulary',
                'command',
                'One-time reset: added PK 197 for Action Center vocabulary fix'
            )

        except Exception as e:
            if verbosity >= 1:
                self.stdout.write(self.style.ERROR(f'Reset Action Center vocabulary release notes FAILED: {e}'))
