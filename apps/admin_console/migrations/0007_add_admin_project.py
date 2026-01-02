# ==============================================================================
# File: apps/admin_console/migrations/0007_add_admin_project.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Add AdminProject model and associate tasks to projects
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================

import django.db.models.deletion
from django.db import migrations, models


def create_default_project_and_assign_tasks(apps, schema_editor):
    """
    Create default 'General' project and assign all existing tasks to it.

    This is idempotent and safe to run multiple times.
    """
    AdminProject = apps.get_model('admin_console', 'AdminProject')
    AdminTask = apps.get_model('admin_console', 'AdminTask')

    # Get or create the default 'General' project
    project, created = AdminProject.objects.get_or_create(
        name='General',
        defaults={
            'description': 'Default project for existing and uncategorized tasks.',
            'status': 'open',
        }
    )

    # Assign all existing tasks that don't have a project to the 'General' project
    tasks_without_project = AdminTask.objects.filter(project__isnull=True)
    count = tasks_without_project.update(project=project)

    if count > 0:
        print(f"  Assigned {count} existing task(s) to 'General' project.")


def reverse_assignment(apps, schema_editor):
    """
    Reverse the data migration - just clear project assignment.
    """
    AdminTask = apps.get_model('admin_console', 'AdminTask')
    AdminTask.objects.all().update(project=None)


class Migration(migrations.Migration):

    dependencies = [
        ("admin_console", "0006_add_blocking_task"),
    ]

    operations = [
        # Step 1: Create the AdminProject model
        migrations.CreateModel(
            name="AdminProject",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True, default="")),
                (
                    "status",
                    models.CharField(
                        choices=[("open", "Open"), ("complete", "Complete")],
                        default="open",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Admin Project",
                "verbose_name_plural": "Admin Projects",
                "ordering": ["name"],
            },
        ),
        # Step 2: Add project field to AdminTask as nullable first
        migrations.AddField(
            model_name="admintask",
            name="project",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="tasks",
                to="admin_console.adminproject",
            ),
        ),
        # Step 3: Run data migration to create default project and assign tasks
        migrations.RunPython(
            create_default_project_and_assign_tasks,
            reverse_assignment,
        ),
        # Step 4: Make the project field non-nullable
        migrations.AlterField(
            model_name="admintask",
            name="project",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="tasks",
                to="admin_console.adminproject",
            ),
        ),
    ]
