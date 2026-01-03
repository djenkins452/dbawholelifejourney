# ==============================================================================
# File: apps/finance/migrations/0011_use_local_storage_for_imports.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Update TransactionImport to use local storage instead of Cloudinary
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-03
# Last Updated: 2026-01-03
# ==============================================================================
"""
Use local FileSystemStorage for transaction import files.

This avoids Cloudinary treating CSV/OFX files as images and failing.
The files are processed in memory and not stored permanently anyway.

Note: The Budget.status field was already added by migrations 0005-0009,
so we do NOT include AddField for that here.
"""

import django.core.files.storage
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0010_fix_budget_status_field"),
    ]

    operations = [
        # Only update the TransactionImport file field storage
        # Budget.status already exists from previous migrations
        migrations.AlterField(
            model_name="transactionimport",
            name="file",
            field=models.FileField(
                blank=True,
                help_text="Uploaded transaction file (deleted after processing for security)",
                null=True,
                storage=django.core.files.storage.FileSystemStorage(),
                upload_to="finance/imports/%Y/%m/",
            ),
        ),
    ]
