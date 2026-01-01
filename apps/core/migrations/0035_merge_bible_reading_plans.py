# ==============================================================================
# File: apps/core/migrations/0035_merge_bible_reading_plans.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Merge migration to include bible reading plans release note
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0033_bible_reading_plans_release_note'),
        ('core', '0034_merge_20260101_0946'),
    ]

    operations = [
    ]
