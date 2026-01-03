# ==============================================================================
# File: apps/finance/migrations/0007_ensure_budget_status_column.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Final fix for missing status column in Budget table
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-03
# Last Updated: 2026-01-03
# ==============================================================================
"""
Final migration to ensure status column exists in Budget table.

Previous migrations (0005, 0006) may have been recorded as applied before
the column was actually created. This migration uses a fresh check with
explicit schema and will definitely run.
"""

from django.db import connection, migrations


def ensure_status_column(apps, schema_editor):
    """
    Ensure status column exists in finance_budget table.

    Uses explicit schema check for PostgreSQL.
    """
    with connection.cursor() as cursor:
        if connection.vendor == 'postgresql':
            # Check if column exists with explicit public schema
            cursor.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'finance_budget'
                  AND column_name = 'status'
            """)
            column_exists = cursor.fetchone() is not None

            if not column_exists:
                print("Migration 0007: Adding status column to finance_budget...")
                try:
                    cursor.execute("""
                        ALTER TABLE finance_budget
                        ADD COLUMN status varchar(10) NOT NULL DEFAULT 'active'
                    """)
                    print("Migration 0007: Status column added!")
                except Exception as e:
                    # Column might already exist - this is fine
                    print(f"Migration 0007: Column add skipped ({e})")

                # Create index if not exists
                try:
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS finance_budget_status_idx
                        ON finance_budget (status)
                    """)
                    print("Migration 0007: Index created!")
                except Exception as e:
                    print(f"Migration 0007: Index creation skipped ({e})")
            else:
                print("Migration 0007: Status column already exists in finance_budget.")
        else:
            # SQLite: Check if column exists before adding
            cursor.execute("PRAGMA table_info(finance_budget)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'status' not in columns:
                print("Migration 0007: Adding status column for SQLite...")
                cursor.execute("""
                    ALTER TABLE finance_budget
                    ADD COLUMN status varchar(10) NOT NULL DEFAULT 'active'
                """)
                print("Migration 0007: Done!")
            else:
                print("Migration 0007: Status column already exists.")


def reverse_noop(apps, schema_editor):
    """No-op for reverse migration."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0006_force_budget_status_column"),
    ]

    operations = [
        migrations.RunPython(ensure_status_column, reverse_noop),
    ]
