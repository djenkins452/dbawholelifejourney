# ==============================================================================
# File: apps/faith/migrations/0008_fix_status_field_restore.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Fix the status field issue - restore SoftDeleteModel.status field
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-12
# ==============================================================================
"""
Migration to fix the status field issue.

The original migration 0006 created UserReadingPlan with a 'status' field
for tracking plan progress (active/completed/paused/abandoned), but this
conflicts with the inherited SoftDeleteModel which also needs a 'status'
field for soft-delete functionality (active/archived/deleted).

Migration 0007 renamed that field to 'plan_status', but now UserReadingPlan
has no 'status' field for the SoftDeleteManager to filter on.

This migration adds the soft-delete 'status' field back to UserReadingPlan.
All existing records default to 'active' (not soft-deleted).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faith', '0007_rename_status_to_plan_status'),
    ]

    operations = [
        # Add the status field for SoftDeleteModel functionality
        # UserReadingProgress already has this field from the original migration
        migrations.AddField(
            model_name='userreadingplan',
            name='status',
            field=models.CharField(
                choices=[
                    ('active', 'Active'),
                    ('archived', 'Archived'),
                    ('deleted', 'Deleted'),
                ],
                db_index=True,
                default='active',
                max_length=10,
            ),
        ),
    ]
