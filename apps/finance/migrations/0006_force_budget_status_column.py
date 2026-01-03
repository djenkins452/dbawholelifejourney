# ==============================================================================
# File: apps/finance/migrations/0006_force_budget_status_column.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Force add status column to Budget table
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-03
# Last Updated: 2026-01-03
# ==============================================================================
"""
Force add status column to Budget table.

Migration 0005 was recorded as applied but the column was never created.
This migration unconditionally adds the column using IF NOT EXISTS.
"""

from django.db import connection, migrations


def force_add_status_column(apps, schema_editor):
    """Unconditionally add status column to Budget table."""
    with connection.cursor() as cursor:
        if connection.vendor == 'postgresql':
            # PostgreSQL: Use ALTER TABLE ... ADD COLUMN IF NOT EXISTS
            # This syntax was added in PostgreSQL 9.6
            try:
                cursor.execute("""
                    ALTER TABLE finance_budget
                    ADD COLUMN IF NOT EXISTS status varchar(10) NOT NULL DEFAULT 'active'
                """)
            except Exception as e:
                # Log but don't fail - column might already exist in older PG versions
                print(f"Note: {e}")

            # Create index if it doesn't exist
            try:
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS finance_budget_status_idx
                    ON finance_budget (status)
                """)
            except Exception as e:
                print(f"Note: {e}")
        else:
            # SQLite: Check if column exists before adding
            cursor.execute("PRAGMA table_info(finance_budget)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'status' not in columns:
                cursor.execute("""
                    ALTER TABLE finance_budget
                    ADD COLUMN status varchar(10) NOT NULL DEFAULT 'active'
                """)


def reverse_noop(apps, schema_editor):
    """No-op for reverse migration."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0005_add_missing_budget_status"),
    ]

    operations = [
        migrations.RunPython(force_add_status_column, reverse_noop),
    ]
