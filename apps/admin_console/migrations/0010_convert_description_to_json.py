# ==============================================================================
# File: apps/admin_console/migrations/0010_convert_description_to_json.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Data migration to convert TextField descriptions to JSONField format
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================
"""
Data migration to convert existing AdminTask descriptions from TextField to JSONField.

This migration must run BEFORE the schema migration that changes the field type.
It converts text descriptions to the Executable Task Standard format:
{
    "objective": "original description text",
    "inputs": [],
    "actions": ["Review and update this task with proper action steps"],
    "output": "Task completion"
}
"""

from django.db import migrations
import json


def convert_descriptions_to_json(apps, schema_editor):
    """
    Convert existing text descriptions to JSON format.

    For existing tasks, the original text description becomes the objective,
    with placeholder values for inputs, actions, and output.
    """
    AdminTask = apps.get_model('admin_console', 'AdminTask')

    for task in AdminTask.objects.all():
        # Check if description is already a dict (shouldn't happen, but be safe)
        if isinstance(task.description, dict):
            continue

        # Get the original text description
        original_text = task.description if task.description else ""

        # Convert to JSON structure
        # Original text becomes the objective
        # Add placeholder action so the task is valid
        task.description = json.dumps({
            "objective": original_text.strip() if original_text else "Task objective not specified",
            "inputs": [],
            "actions": ["Review and update this task with specific action steps"],
            "output": "Task completion"
        })
        task.save(update_fields=['description'])


def reverse_descriptions_to_text(apps, schema_editor):
    """
    Reverse the migration by extracting objective from JSON.
    """
    AdminTask = apps.get_model('admin_console', 'AdminTask')

    for task in AdminTask.objects.all():
        try:
            if isinstance(task.description, str):
                data = json.loads(task.description)
            elif isinstance(task.description, dict):
                data = task.description
            else:
                continue

            # Extract objective as the text description
            task.description = data.get('objective', '')
            task.save(update_fields=['description'])
        except (json.JSONDecodeError, TypeError):
            # Leave as-is if we can't parse
            pass


class Migration(migrations.Migration):

    dependencies = [
        ("admin_console", "0009_populate_task_configs"),
    ]

    operations = [
        migrations.RunPython(
            convert_descriptions_to_json,
            reverse_descriptions_to_text,
        ),
    ]
