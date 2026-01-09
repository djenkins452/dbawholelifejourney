# Generated manually - state-only migration to sync Django ORM with database
#
# The status field on Budget comes from SoftDeleteModel (via UserOwnedModel).
# Migration 0012 used RunPython/SQL to add the column directly, but Django's
# migration state tracker doesn't recognize it. This migration uses state_operations
# to tell Django the field exists without modifying the database.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0012_budget_status"),
    ]

    operations = [
        # State-only operation: Django's AddField with state_operations
        # tells the ORM the field exists without running any SQL
        migrations.SeparateDatabaseAndState(
            database_operations=[],  # Don't touch the database
            state_operations=[
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
            ],
        ),
    ]
