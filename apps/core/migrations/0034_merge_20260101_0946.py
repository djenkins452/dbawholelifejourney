# ==============================================================================
# File: apps/core/migrations/0034_merge_20260101_0946.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Merge migration for conflicting 0033 release note migrations
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0033_food_history_delete_release_note'),
        ('core', '0033_google_calendar_oauth_fix_release_note'),
    ]

    operations = [
    ]
