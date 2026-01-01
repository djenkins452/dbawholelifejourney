# ==============================================================================
# File: apps/admin_console/migrations/0003_delete_claudetask.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Remove ClaudeTask model and table
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('admin_console', '0002_add_source_parent_task'),
    ]

    operations = [
        migrations.DeleteModel(
            name='ClaudeTask',
        ),
    ]
