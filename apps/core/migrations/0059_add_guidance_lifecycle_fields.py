"""
Migration for PGE lifecycle tracking fields on GuidanceItem.

Adds: acknowledged_at, dismissed_at, snoozed_until, acted_upon_at,
      action_type, feedback, and snoozed_until index.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0058_add_pge_guidance_item"),
    ]

    operations = [
        migrations.AddField(
            model_name="guidanceitem",
            name="acknowledged_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the user acknowledged this guidance",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="guidanceitem",
            name="dismissed_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the user dismissed this guidance",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="guidanceitem",
            name="snoozed_until",
            field=models.DateTimeField(
                blank=True,
                help_text="Guidance is hidden until this time",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="guidanceitem",
            name="acted_upon_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the user took action on this guidance",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="guidanceitem",
            name="action_type",
            field=models.CharField(
                blank=True,
                help_text="What action the user took (e.g., 'navigated', 'updated_goal')",
                max_length=100,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="guidanceitem",
            name="feedback",
            field=models.CharField(
                blank=True,
                help_text="Optional user feedback on the guidance quality",
                max_length=255,
                null=True,
            ),
        ),
        migrations.AddIndex(
            model_name="guidanceitem",
            index=models.Index(
                fields=["snoozed_until"],
                name="core_guidanc_snoozed_idx",
            ),
        ),
    ]
