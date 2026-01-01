# ==============================================================================
# File: apps/admin_console/management/commands/load_phase1_data.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Idempotent command to ensure phases 1-20 exist for project tasks
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01 (Prepopulate Phase Dropdown 1-20)
# ==============================================================================

from django.core.management.base import BaseCommand

from apps.admin_console.services import ensure_project_phases_exist


class Command(BaseCommand):
    help = 'Ensure phases 1-20 exist for admin project tasks (idempotent, safe for production)'

    def handle(self, *args, **options):
        """
        Ensure AdminProjectPhase records exist for phases 1-20.

        This command is:
        - Idempotent: safe to run multiple times
        - Production-safe: never overwrites or deletes existing data
        - Non-destructive: only creates phases that don't exist

        Behavior:
        - For each phase 1-20:
          - If phase exists: DO NOT modify it
          - If phase does not exist: Create with name "Phase X"
        - Phase 1 status = "in_progress" ONLY IF no phase is currently in_progress
        - All other new phases status = "not_started"
        """
        result = ensure_project_phases_exist(max_phase=20)

        if result['created_count'] > 0:
            self.stdout.write(
                self.style.SUCCESS(result['message'])
            )
        else:
            self.stdout.write(
                self.style.WARNING(result['message'])
            )
