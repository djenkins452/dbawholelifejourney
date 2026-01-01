# ==============================================================================
# File: apps/admin_console/migrations/0002_add_source_parent_task.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: No-op migration (fields already in 0001, this is for compatibility)
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================
#
# This is a no-op migration. The source and parent_task fields are already
# included in 0001_create_claudetask. This migration exists only for
# compatibility with databases that may have recorded 0002 in django_migrations.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('admin_console', '0001_create_claudetask'),
    ]

    operations = [
        # No operations needed - fields already exist from 0001
    ]
