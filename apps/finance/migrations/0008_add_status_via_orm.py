# ==============================================================================
# File: apps/finance/migrations/0008_add_status_via_orm.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Forcefully add status column to Budget table
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-03
# Last Updated: 2026-01-03
# ==============================================================================
"""
Forcefully add status column to Budget table.

This migration uses schema_editor.execute() to run raw SQL that will
add the column if it doesn't exist. Uses PostgreSQL-specific syntax
to avoid errors if column already exists.
"""

from django.db import migrations


def add_status_column_force(apps, schema_editor):
    """
    Add status column using IF NOT EXISTS (PostgreSQL 11+).
    """
    # PostgreSQL 11+ supports ADD COLUMN IF NOT EXISTS
    # This will not error if the column already exists
    if schema_editor.connection.vendor == 'postgresql':
        # First, let's try the direct approach with error handling
        try:
            schema_editor.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'finance_budget'
                          AND column_name = 'status'
                    ) THEN
                        ALTER TABLE finance_budget
                        ADD COLUMN status varchar(10) NOT NULL DEFAULT 'active';

                        CREATE INDEX IF NOT EXISTS finance_budget_status_idx
                        ON finance_budget (status);

                        RAISE NOTICE 'Migration 0008: Added status column to finance_budget';
                    ELSE
                        RAISE NOTICE 'Migration 0008: status column already exists';
                    END IF;
                END $$;
            """)
            print("Migration 0008: Executed status column check/add")
        except Exception as e:
            print(f"Migration 0008: Error in DO block: {e}")
            # Fallback: try simple ALTER TABLE
            try:
                schema_editor.execute("""
                    ALTER TABLE finance_budget
                    ADD COLUMN IF NOT EXISTS status varchar(10) NOT NULL DEFAULT 'active'
                """)
                print("Migration 0008: Used fallback ADD COLUMN IF NOT EXISTS")
            except Exception as e2:
                print(f"Migration 0008: Fallback also failed: {e2}")
    else:
        # SQLite doesn't support IF NOT EXISTS for columns
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA table_info(finance_budget)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'status' not in columns:
                schema_editor.execute("""
                    ALTER TABLE finance_budget
                    ADD COLUMN status varchar(10) NOT NULL DEFAULT 'active'
                """)
                print("Migration 0008: Added status column (SQLite)")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0007_ensure_budget_status_column"),
    ]

    operations = [
        migrations.RunPython(add_status_column_force, noop),
    ]
