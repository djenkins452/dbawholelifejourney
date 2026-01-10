# ==============================================================================
# File: 0016_cleanup_phase_999.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Move tasks from Phase 999 to Phase 1 and delete Phase 999
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-10
# ==============================================================================
"""
Data migration to clean up Phase 999.

Moves any tasks from Phase 999 (User Requests) to Phase 1, then deletes Phase 999.
"""

from django.db import migrations


def move_tasks_and_delete_phase_999(apps, schema_editor):
    """Move tasks from Phase 999 to Phase 1 and delete Phase 999."""
    AdminProjectPhase = apps.get_model('admin_console', 'AdminProjectPhase')
    AdminTask = apps.get_model('admin_console', 'AdminTask')

    # Get Phase 1 (should always exist)
    try:
        phase_1 = AdminProjectPhase.objects.get(phase_number=1)
    except AdminProjectPhase.DoesNotExist:
        # Phase 1 doesn't exist, nothing to do
        return

    # Get Phase 999 if it exists
    try:
        phase_999 = AdminProjectPhase.objects.get(phase_number=999)
    except AdminProjectPhase.DoesNotExist:
        # Phase 999 doesn't exist, nothing to do
        return

    # Move all tasks from Phase 999 to Phase 1
    tasks_moved = AdminTask.objects.filter(phase=phase_999).update(phase=phase_1)

    if tasks_moved:
        print(f"Moved {tasks_moved} task(s) from Phase 999 to Phase 1")

    # Delete Phase 999
    phase_999.delete()
    print("Deleted Phase 999 (User Requests)")


def reverse_migration(apps, schema_editor):
    """Reverse is a no-op - we don't recreate Phase 999."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('admin_console', '0015_add_project_priority'),
    ]

    operations = [
        migrations.RunPython(
            move_tasks_and_delete_phase_999,
            reverse_migration,
        ),
    ]
