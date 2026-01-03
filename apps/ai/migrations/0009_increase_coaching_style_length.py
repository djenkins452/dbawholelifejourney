# ==============================================================================
# File: apps/ai/migrations/0009_increase_coaching_style_length.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Increase coaching_style field length to match CoachingStyle.key
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-03
# Last Updated: 2026-01-03
# ==============================================================================
"""
Increase AIInsight.coaching_style from 20 to 50 characters.

This fixes the error "value too long for type character varying(20)" when
using coaching style keys longer than 20 characters like "loving_faith_centered_spouse".
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0008_add_habit_goal_fields_to_snapshot"),
    ]

    operations = [
        migrations.AlterField(
            model_name="aiinsight",
            name="coaching_style",
            field=models.CharField(
                blank=True,
                default="supportive",
                help_text="Coaching style used when generating this insight",
                max_length=50,
            ),
        ),
    ]
