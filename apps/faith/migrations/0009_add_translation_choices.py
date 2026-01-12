# ==============================================================================
# File: apps/faith/migrations/0009_add_translation_choices.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Add translation choices to Bible study tools models
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-12
# ==============================================================================
"""
Migration to add translation choices to BibleHighlight, BibleBookmark,
and BibleStudyNote models.

Note: This migration only adds choices validation - no database schema changes.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faith', '0008_fix_status_field_restore'),
    ]

    operations = [
        migrations.AlterField(
            model_name='biblehighlight',
            name='translation',
            field=models.CharField(
                choices=[
                    ('ESV', 'English Standard Version'),
                    ('NIV', 'New International Version'),
                    ('KJV', 'King James Version'),
                    ('NKJV', 'New King James Version'),
                    ('NLT', 'New Living Translation'),
                    ('NASB', 'New American Standard Bible'),
                    ('CSB', 'Christian Standard Bible'),
                    ('BSB', 'Berean Standard Bible'),
                    ('AMP', 'Amplified Bible'),
                    ('MSG', 'The Message'),
                    ('NET', 'New English Translation'),
                    ('RSV', 'Revised Standard Version'),
                    ('NRSV', 'New Revised Standard Version'),
                    ('CEV', 'Contemporary English Version'),
                    ('GNT', 'Good News Translation'),
                    ('HCSB', 'Holman Christian Standard Bible'),
                    ('WEB', 'World English Bible'),
                    ('YLT', "Young's Literal Translation"),
                    ('ASV', 'American Standard Version'),
                    ('DRA', 'Douay-Rheims Bible'),
                ],
                default='ESV',
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name='biblebookmark',
            name='translation',
            field=models.CharField(
                choices=[
                    ('ESV', 'English Standard Version'),
                    ('NIV', 'New International Version'),
                    ('KJV', 'King James Version'),
                    ('NKJV', 'New King James Version'),
                    ('NLT', 'New Living Translation'),
                    ('NASB', 'New American Standard Bible'),
                    ('CSB', 'Christian Standard Bible'),
                    ('BSB', 'Berean Standard Bible'),
                    ('AMP', 'Amplified Bible'),
                    ('MSG', 'The Message'),
                    ('NET', 'New English Translation'),
                    ('RSV', 'Revised Standard Version'),
                    ('NRSV', 'New Revised Standard Version'),
                    ('CEV', 'Contemporary English Version'),
                    ('GNT', 'Good News Translation'),
                    ('HCSB', 'Holman Christian Standard Bible'),
                    ('WEB', 'World English Bible'),
                    ('YLT', "Young's Literal Translation"),
                    ('ASV', 'American Standard Version'),
                    ('DRA', 'Douay-Rheims Bible'),
                ],
                default='ESV',
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name='biblestudynote',
            name='translation',
            field=models.CharField(
                choices=[
                    ('ESV', 'English Standard Version'),
                    ('NIV', 'New International Version'),
                    ('KJV', 'King James Version'),
                    ('NKJV', 'New King James Version'),
                    ('NLT', 'New Living Translation'),
                    ('NASB', 'New American Standard Bible'),
                    ('CSB', 'Christian Standard Bible'),
                    ('BSB', 'Berean Standard Bible'),
                    ('AMP', 'Amplified Bible'),
                    ('MSG', 'The Message'),
                    ('NET', 'New English Translation'),
                    ('RSV', 'Revised Standard Version'),
                    ('NRSV', 'New Revised Standard Version'),
                    ('CEV', 'Contemporary English Version'),
                    ('GNT', 'Good News Translation'),
                    ('HCSB', 'Holman Christian Standard Bible'),
                    ('WEB', 'World English Bible'),
                    ('YLT', "Young's Literal Translation"),
                    ('ASV', 'American Standard Version'),
                    ('DRA', 'Douay-Rheims Bible'),
                ],
                default='ESV',
                max_length=10,
            ),
        ),
    ]
