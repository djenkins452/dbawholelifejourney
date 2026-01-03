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
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0004_add_finance_audit_log"),
    ]

    operations = [
        migrations.AddField(
            model_name="budget",
            name="status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("archived", "Archived"),
                    ("deleted", "Deleted"),
                ],
                db_index=True,
                default="active",
                max_length=10,
            ),
        ),
    ]
