# ==============================================================================
# File: apps/admin_console/migrations/0009_populate_task_configs.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Data migration to populate task configuration tables
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================

from django.db import migrations


def populate_configs(apps, schema_editor):
    """Populate task configuration tables with default values matching existing enums."""
    AdminTaskStatusConfig = apps.get_model('admin_console', 'AdminTaskStatusConfig')
    AdminTaskPriorityConfig = apps.get_model('admin_console', 'AdminTaskPriorityConfig')
    AdminTaskCategoryConfig = apps.get_model('admin_console', 'AdminTaskCategoryConfig')
    AdminTaskEffortConfig = apps.get_model('admin_console', 'AdminTaskEffortConfig')

    # Status configs matching STATUS_CHOICES
    status_data = [
        {'name': 'backlog', 'display_name': 'Backlog', 'execution_allowed': False, 'terminal': False, 'order': 1},
        {'name': 'ready', 'display_name': 'Ready', 'execution_allowed': False, 'terminal': False, 'order': 2},
        {'name': 'in_progress', 'display_name': 'In Progress', 'execution_allowed': True, 'terminal': False, 'order': 3},
        {'name': 'blocked', 'display_name': 'Blocked', 'execution_allowed': False, 'terminal': False, 'order': 4},
        {'name': 'done', 'display_name': 'Done', 'execution_allowed': False, 'terminal': True, 'order': 5},
    ]
    for data in status_data:
        AdminTaskStatusConfig.objects.get_or_create(name=data['name'], defaults=data)

    # Priority configs (1-5)
    priority_data = [
        {'value': 1, 'label': 'Highest', 'order': 1},
        {'value': 2, 'label': 'High', 'order': 2},
        {'value': 3, 'label': 'Normal', 'order': 3},
        {'value': 4, 'label': 'Low', 'order': 4},
        {'value': 5, 'label': 'Lowest', 'order': 5},
    ]
    for data in priority_data:
        AdminTaskPriorityConfig.objects.get_or_create(value=data['value'], defaults=data)

    # Category configs matching CATEGORY_CHOICES
    category_data = [
        {'name': 'feature', 'display_name': 'Feature', 'order': 1},
        {'name': 'bug', 'display_name': 'Bug', 'order': 2},
        {'name': 'infra', 'display_name': 'Infrastructure', 'order': 3},
        {'name': 'content', 'display_name': 'Content', 'order': 4},
        {'name': 'business', 'display_name': 'Business', 'order': 5},
    ]
    for data in category_data:
        AdminTaskCategoryConfig.objects.get_or_create(name=data['name'], defaults=data)

    # Effort configs matching EFFORT_CHOICES
    effort_data = [
        {'value': 'S', 'label': 'Small', 'order': 1},
        {'value': 'M', 'label': 'Medium', 'order': 2},
        {'value': 'L', 'label': 'Large', 'order': 3},
    ]
    for data in effort_data:
        AdminTaskEffortConfig.objects.get_or_create(value=data['value'], defaults=data)


def link_existing_tasks(apps, schema_editor):
    """Link existing tasks to their corresponding config records."""
    AdminTask = apps.get_model('admin_console', 'AdminTask')
    AdminTaskStatusConfig = apps.get_model('admin_console', 'AdminTaskStatusConfig')
    AdminTaskPriorityConfig = apps.get_model('admin_console', 'AdminTaskPriorityConfig')
    AdminTaskCategoryConfig = apps.get_model('admin_console', 'AdminTaskCategoryConfig')
    AdminTaskEffortConfig = apps.get_model('admin_console', 'AdminTaskEffortConfig')

    # Build lookup dictionaries
    status_lookup = {s.name: s for s in AdminTaskStatusConfig.objects.all()}
    priority_lookup = {p.value: p for p in AdminTaskPriorityConfig.objects.all()}
    category_lookup = {c.name: c for c in AdminTaskCategoryConfig.objects.all()}
    effort_lookup = {e.value: e for e in AdminTaskEffortConfig.objects.all()}

    # Update all existing tasks
    for task in AdminTask.objects.all():
        task.status_config = status_lookup.get(task.status)
        task.priority_config = priority_lookup.get(task.priority)
        task.category_config = category_lookup.get(task.category)
        task.effort_config = effort_lookup.get(task.effort)
        task.save()


def reverse_migration(apps, schema_editor):
    """Reverse: Clear config links from tasks and delete config records."""
    AdminTask = apps.get_model('admin_console', 'AdminTask')
    AdminTaskStatusConfig = apps.get_model('admin_console', 'AdminTaskStatusConfig')
    AdminTaskPriorityConfig = apps.get_model('admin_console', 'AdminTaskPriorityConfig')
    AdminTaskCategoryConfig = apps.get_model('admin_console', 'AdminTaskCategoryConfig')
    AdminTaskEffortConfig = apps.get_model('admin_console', 'AdminTaskEffortConfig')

    # Clear config links
    AdminTask.objects.update(
        status_config=None,
        priority_config=None,
        category_config=None,
        effort_config=None
    )

    # Delete config records
    AdminTaskStatusConfig.objects.all().delete()
    AdminTaskPriorityConfig.objects.all().delete()
    AdminTaskCategoryConfig.objects.all().delete()
    AdminTaskEffortConfig.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("admin_console", "0008_phase17_configurable_task_fields"),
    ]

    operations = [
        migrations.RunPython(populate_configs, reverse_migration),
        migrations.RunPython(link_existing_tasks, migrations.RunPython.noop),
    ]
