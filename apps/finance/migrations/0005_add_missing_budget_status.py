# ==============================================================================
# File: apps/finance/migrations/0005_add_missing_budget_status.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Fix missing status field on Budget model
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-03
# Last Updated: 2026-01-03
# ==============================================================================
"""
Migration to add missing status field to Budget table.

The initial migration (0001) defined the status field but it was not
actually created in some database instances due to a migration state issue.
This migration adds the field if missing.

NOTE: This migration is conditional - it only adds the field if it doesn't exist.
"""

from django.db import connection, migrations, models


def add_status_if_missing(apps, schema_editor):
    """Add status field to Budget table if it doesn't exist."""
    # Check if the column already exists
    with connection.cursor() as cursor:
        # Get column info based on database backend
        if connection.vendor == 'postgresql':
            # Check if column exists (with schema)
            cursor.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'finance_budget'
                  AND column_name = 'status'
            """)
            if cursor.fetchone() is None:
                # Check if table exists first
                cursor.execute("""
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = 'finance_budget'
                """)
                if cursor.fetchone() is not None:
                    # Table exists but column doesn't - add it
                    cursor.execute("""
                        ALTER TABLE finance_budget
                        ADD COLUMN status varchar(10) NOT NULL DEFAULT 'active'
                    """)
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS finance_budget_status_idx
                        ON finance_budget (status)
                    """)
        else:  # SQLite
            cursor.execute("PRAGMA table_info(finance_budget)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'status' not in columns:
                # Add the column for SQLite
                cursor.execute("""
                    ALTER TABLE finance_budget
                    ADD COLUMN status varchar(10) NOT NULL DEFAULT 'active'
                """)
                try:
                    cursor.execute("""
                        CREATE INDEX finance_budget_status_idx ON finance_budget (status)
                    """)
                except Exception:
                    pass  # Index might already exist


def reverse_noop(apps, schema_editor):
    """No-op for reverse migration."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0004_add_finance_audit_log"),
    ]

    operations = [
        migrations.RunPython(add_status_if_missing, reverse_noop),
    ]
