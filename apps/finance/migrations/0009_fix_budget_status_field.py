# ==============================================================================
# File: apps/finance/migrations/0009_fix_budget_status_field.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Final fix for Budget.status - ensures column exists after property rename
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-03
# Last Updated: 2026-01-03
# ==============================================================================
"""
Final migration to ensure Budget.status column exists.

ROOT CAUSE FIX:
The Budget model previously had a @property named 'status' that calculated
budget health (on_track/warning/over). This property shadowed the inherited
'status' field from SoftDeleteModel (active/archived/deleted).

SOLUTION:
1. Renamed property to 'health_status' in models.py
2. This migration ensures the status column exists in the database

This migration is idempotent - safe to run multiple times.
"""

from django.db import migrations


def ensure_status_column(apps, schema_editor):
    """
    Ensure status column exists in finance_budget table.
    Uses PostgreSQL-safe approach with explicit checks.
    """
    from django.db import connection

    with connection.cursor() as cursor:
        if connection.vendor == 'postgresql':
            # Check if column exists using PostgreSQL information_schema
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'finance_budget'
                  AND column_name = 'status'
            """)
            column_exists = cursor.fetchone() is not None

            if not column_exists:
                print("Migration 0009: Adding status column to finance_budget...")
                cursor.execute("""
                    ALTER TABLE finance_budget
                    ADD COLUMN status varchar(10) NOT NULL DEFAULT 'active'
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS finance_budget_status_idx
                    ON finance_budget (status)
                """)
                print("Migration 0009: Status column and index created.")
            else:
                print("Migration 0009: Status column already exists in finance_budget.")

            # Verify by listing columns
            cursor.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'finance_budget'
                ORDER BY ordinal_position
            """)
            columns = [row[0] for row in cursor.fetchall()]
            print(f"Migration 0009: finance_budget columns: {columns}")

        else:
            # SQLite fallback
            cursor.execute("PRAGMA table_info(finance_budget)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'status' not in columns:
                print("Migration 0009: Adding status column (SQLite)...")
                cursor.execute("""
                    ALTER TABLE finance_budget
                    ADD COLUMN status varchar(10) NOT NULL DEFAULT 'active'
                """)
            else:
                print("Migration 0009: Status column exists (SQLite).")


def noop(apps, schema_editor):
    """No-op for reverse migration."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0008_add_status_via_orm"),
    ]

    operations = [
        migrations.RunPython(ensure_status_column, noop),
    ]
