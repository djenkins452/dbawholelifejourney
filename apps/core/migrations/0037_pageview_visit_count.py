# ==============================================================================
# File: apps/core/migrations/0037_pageview_visit_count.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Add visit_count field to PageView for "Most Used" feature
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-05
# Last Updated: 2026-01-05
# ==============================================================================

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0036_favoritepage_pageview'),
    ]

    operations = [
        migrations.AddField(
            model_name='pageview',
            name='visit_count',
            field=models.PositiveIntegerField(
                default=1,
                help_text='Number of times this page has been visited',
            ),
        ),
        migrations.AlterModelOptions(
            name='pageview',
            options={
                'ordering': ['-visit_count', '-viewed_at'],
                'verbose_name': 'Page View',
                'verbose_name_plural': 'Page Views',
            },
        ),
    ]
