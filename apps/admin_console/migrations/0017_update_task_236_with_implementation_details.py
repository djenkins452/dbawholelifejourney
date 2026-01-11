# ==============================================================================
# File: 0017_update_task_236_with_implementation_details.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Update Task 236 with implementation-ready details
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-10
# ==============================================================================
"""
Data migration to update Task 236 with implementation-ready details.

Changes the task from a generic "review" task to an actionable implementation task.
"""

from django.db import migrations


def update_task_236(apps, schema_editor):
    """Update Task 236 with implementation-ready details."""
    AdminTask = apps.get_model('admin_console', 'AdminTask')

    try:
        task = AdminTask.objects.get(id=236)
    except AdminTask.DoesNotExist:
        # Task doesn't exist, nothing to do
        return

    # Update with implementation-ready details
    task.title = "Export my blood glucose numbers for the last week"
    task.description = {
        "objective": "Add blood glucose export functionality",
        "inputs": [
            "User request: I wish I could export my blood glucose numbers for the last week",
            "Requested by: Danny Jenkins (dannyjenkins71@gmail.com)",
            "GlucoseEntry model exists in apps/health/models.py",
            "Dexcom CGM integration already imports glucose data",
        ],
        "actions": [
            "Add export view in apps/health/views.py that generates CSV for GlucoseEntry",
            "Include date range filtering (default: last 7 days)",
            "Add 'Export' button to the blood glucose dashboard/list page",
            "Include fields: date, time, value, unit, context, trend, source",
            "Test the export with sample glucose data",
            "Update the AI Assistant to inform users about the new export feature",
        ],
        "output": "Working CSV export for blood glucose data with date range filtering",
    }
    task.status = 'backlog'  # Reset to backlog for review
    task.save()

    print(f"Updated Task #{task.id} with implementation-ready details")


def reverse_migration(apps, schema_editor):
    """Reverse is a no-op."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('admin_console', '0016_cleanup_phase_999'),
    ]

    operations = [
        migrations.RunPython(
            update_task_236,
            reverse_migration,
        ),
    ]
