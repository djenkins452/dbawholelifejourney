"""
Management command to sync test results from local SQLite to production PostgreSQL.

This allows you to run tests locally and preserve results in production database.

Usage:
    python manage.py sync_test_results
    python manage.py sync_test_results --last=5  # Only sync last 5 runs
    python manage.py sync_test_results --dry-run  # Preview without syncing
"""
import os
from django.core.management.base import BaseCommand
from django.db import connections
from apps.core.models import TestRun, TestRunDetail


class Command(BaseCommand):
    help = 'Sync test results from local SQLite to production PostgreSQL'

    def add_arguments(self, parser):
        parser.add_argument(
            '--last',
            type=int,
            default=None,
            help='Only sync the last N test runs',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview what would be synced without actually syncing',
        )
        parser.add_argument(
            '--database-url',
            type=str,
            default=None,
            help='Production DATABASE_URL (or set PRODUCTION_DATABASE_URL env var)',
        )

    def handle(self, *args, **options):
        import environ

        # Get production database URL
        database_url = options['database_url'] or os.environ.get('PRODUCTION_DATABASE_URL')

        if not database_url:
            self.stderr.write(self.style.ERROR(
                'No production database URL provided.\n'
                'Either:\n'
                '  1. Set PRODUCTION_DATABASE_URL environment variable\n'
                '  2. Pass --database-url=postgresql://...\n'
            ))
            return

        # Parse the database URL
        env = environ.Env()
        db_config = env.db_url_config(database_url)

        # Add the production database as a second connection
        connections.databases['production'] = db_config

        self.stdout.write(f'Connecting to production database at {db_config["HOST"]}...')

        # Get local test runs
        local_runs = TestRun.objects.all().order_by('-run_at')
        if options['last']:
            local_runs = local_runs[:options['last']]

        local_runs = list(local_runs)

        if not local_runs:
            self.stdout.write(self.style.WARNING('No local test runs found.'))
            return

        self.stdout.write(f'Found {len(local_runs)} local test run(s) to sync.')

        if options['dry_run']:
            self.stdout.write(self.style.WARNING('\n[DRY RUN] Would sync:'))
            for run in local_runs:
                detail_count = run.details.count()
                self.stdout.write(
                    f'  - {run.run_at.strftime("%Y-%m-%d %H:%M")} | '
                    f'{run.status} | {run.total_tests} tests | '
                    f'{detail_count} app details'
                )
            return

        # Sync each test run
        synced = 0
        skipped = 0

        for local_run in local_runs:
            # Check if this run already exists in production (by timestamp and git commit)
            existing = TestRun.objects.using('production').filter(
                run_at=local_run.run_at,
                git_commit=local_run.git_commit,
            ).first()

            if existing:
                self.stdout.write(
                    f'  Skipped: {local_run.run_at.strftime("%Y-%m-%d %H:%M")} (already exists)'
                )
                skipped += 1
                continue

            # Create the test run in production
            production_run = TestRun(
                run_at=local_run.run_at,
                duration_seconds=local_run.duration_seconds,
                status=local_run.status,
                total_tests=local_run.total_tests,
                passed=local_run.passed,
                failed=local_run.failed,
                errors=local_run.errors,
                apps_tested=local_run.apps_tested,
                pass_rate=local_run.pass_rate,
                git_branch=local_run.git_branch,
                git_commit=local_run.git_commit,
            )
            production_run.save(using='production')

            # Sync the details
            for local_detail in local_run.details.all():
                production_detail = TestRunDetail(
                    test_run=production_run,
                    app_name=local_detail.app_name,
                    passed=local_detail.passed,
                    failed=local_detail.failed,
                    errors=local_detail.errors,
                    total=local_detail.total,
                    failed_tests=local_detail.failed_tests,
                    error_tests=local_detail.error_tests,
                    error_details=local_detail.error_details,
                )
                production_detail.save(using='production')

            self.stdout.write(self.style.SUCCESS(
                f'  Synced: {local_run.run_at.strftime("%Y-%m-%d %H:%M")} | '
                f'{local_run.total_tests} tests | {local_run.details.count()} app details'
            ))
            synced += 1

        # Summary
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Sync complete: {synced} synced, {skipped} skipped'))
