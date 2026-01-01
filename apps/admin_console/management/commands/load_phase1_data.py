# ==============================================================================
# File: apps/admin_console/management/commands/load_phase1_data.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Idempotent command to seed Phase 1 project data
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================

from django.core.management.base import BaseCommand

from apps.admin_console.models import AdminProjectPhase


class Command(BaseCommand):
    help = 'Load Phase 1 seed data for admin project tasks (idempotent)'

    def handle(self, *args, **options):
        phase, created = AdminProjectPhase.objects.get_or_create(
            phase_number=1,
            defaults={
                'name': 'Core Project Infrastructure',
                'objective': 'Set up the foundational infrastructure for the admin project task system.',
                'status': 'in_progress',
            }
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(f'Created Phase 1: {phase.name}')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'Phase 1 already exists: {phase.name}')
            )
