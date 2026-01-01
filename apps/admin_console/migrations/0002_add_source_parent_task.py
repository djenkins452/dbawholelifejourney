# ==============================================================================
# File: apps/admin_console/migrations/0002_add_source_parent_task.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Add source and parent_task fields that were missing from Railway DB
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================
#
# This migration adds columns that should have been in 0001 but Railway's
# database was created before those fields were added to the migration.
# This is safe to run even if columns exist (uses IF NOT EXISTS via RunSQL).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admin_console', '0001_create_claudetask'),
    ]

    operations = [
        # Add source field if it doesn't exist
        migrations.RunSQL(
            sql="""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='admin_console_claudetask' AND column_name='source'
                ) THEN
                    ALTER TABLE admin_console_claudetask
                    ADD COLUMN source VARCHAR(20) DEFAULT 'user' NOT NULL;
                END IF;
            END $$;
            """,
            reverse_sql="""
            ALTER TABLE admin_console_claudetask DROP COLUMN IF EXISTS source;
            """,
        ),
        # Add parent_task_id field if it doesn't exist
        migrations.RunSQL(
            sql="""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='admin_console_claudetask' AND column_name='parent_task_id'
                ) THEN
                    ALTER TABLE admin_console_claudetask
                    ADD COLUMN parent_task_id BIGINT NULL;

                    ALTER TABLE admin_console_claudetask
                    ADD CONSTRAINT admin_console_claudetask_parent_task_fk
                    FOREIGN KEY (parent_task_id)
                    REFERENCES admin_console_claudetask(id)
                    ON DELETE SET NULL;
                END IF;
            END $$;
            """,
            reverse_sql="""
            ALTER TABLE admin_console_claudetask DROP CONSTRAINT IF EXISTS admin_console_claudetask_parent_task_fk;
            ALTER TABLE admin_console_claudetask DROP COLUMN IF EXISTS parent_task_id;
            """,
        ),
    ]
