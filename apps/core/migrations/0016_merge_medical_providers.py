# ==============================================================================
# File: 0016_merge_medical_providers.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Merge migration to resolve conflicting leaf nodes
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-29
# Last Updated: 2025-12-29
# ==============================================================================
"""
Merge migration to bring medical providers release notes into the main migration chain.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0013_medical_providers_release_notes"),
        ("core", "0015_merge_20251229_2041"),
    ]

    operations = []
