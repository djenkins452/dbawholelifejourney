# ==============================================================================
# File: apps/admin_console/management/commands/seed_admin_project_phases.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Idempotent command to seed AdminProjectPhase data (phases 1-11)
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01 (Phase 11.1 - Preflight Guard & Phase Seeding)
# ==============================================================================

from django.core.management.base import BaseCommand

from apps.admin_console.services import seed_admin_project_phases


class Command(BaseCommand):
    help = 'Seed AdminProjectPhase data with phases 1-11 (idempotent, safe for production)'

    def handle(self, *args, **options):
        """
        Seed the AdminProjectPhase table if empty.

        This command is:
        - Idempotent: safe to run multiple times
        - Production-safe: only creates data if table is empty
        - Non-destructive: never overwrites or modifies existing data

        Behavior:
        - If AdminProjectPhase table is empty:
          - Creates phases 1 through 11
          - Sets phase 1 status = "in_progress"
          - Sets all other phases status = "not_started"
        - If phases already exist:
          - Does nothing
        """
        result = seed_admin_project_phases(created_by='claude')

        if result['seeded']:
            self.stdout.write(
                self.style.SUCCESS(result['message'])
            )
        else:
            self.stdout.write(
                self.style.WARNING(result['message'])
            )
