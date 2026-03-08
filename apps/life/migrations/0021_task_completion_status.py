"""
Add completion_status field to Task, migrate data from is_completed, remove is_completed.

This migration introduces a three-state completion system:
- pending: Task not yet done (default)
- completed: Task finished
- skipped: Task intentionally not completed

Previously, Task used a boolean is_completed field.
"""
from django.db import migrations, models


def populate_completion_status(apps, schema_editor):
    """Set completion_status from the old is_completed boolean."""
    Task = apps.get_model('life', 'Task')
    # Bulk update completed tasks
    Task.objects.filter(is_completed=True).update(completion_status='completed')
    # Pending tasks already have the default 'pending'


def reverse_completion_status(apps, schema_editor):
    """Restore is_completed from completion_status."""
    Task = apps.get_model('life', 'Task')
    Task.objects.filter(completion_status='completed').update(is_completed=True)
    Task.objects.exclude(completion_status='completed').update(is_completed=False)


class Migration(migrations.Migration):

    dependencies = [
        ('life', '0020_recipebulkimportphoto_image_url'),
    ]

    operations = [
        # Step 1: Add completion_status field
        migrations.AddField(
            model_name='task',
            name='completion_status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('completed', 'Completed'),
                    ('skipped', 'Skipped'),
                ],
                db_index=True,
                default='pending',
                max_length=20,
            ),
        ),
        # Step 2: Populate from is_completed
        migrations.RunPython(
            populate_completion_status,
            reverse_completion_status,
        ),
        # Step 3: Remove old boolean field
        migrations.RemoveField(
            model_name='task',
            name='is_completed',
        ),
        # Step 4: Update ordering
        migrations.AlterModelOptions(
            name='task',
            options={
                'ordering': ['completion_status', 'priority', 'scheduled_time', '-created_at'],
                'verbose_name': 'Task',
                'verbose_name_plural': 'Tasks',
            },
        ),
    ]
