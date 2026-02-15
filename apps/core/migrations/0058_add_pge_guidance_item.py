"""
Migration for PGE (Proactive Guidance Engine) — GuidanceItem model.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0057_add_sue_semantic_decision_log"),
    ]

    operations = [
        migrations.CreateModel(
            name="GuidanceItem",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "title",
                    models.CharField(
                        help_text="Short guidance headline",
                        max_length=255,
                    ),
                ),
                (
                    "message",
                    models.TextField(
                        help_text="Detailed guidance message with context",
                    ),
                ),
                (
                    "priority",
                    models.IntegerField(
                        choices=[
                            (1, "Critical"),
                            (2, "High"),
                            (3, "Medium"),
                            (4, "Low"),
                            (5, "Info"),
                        ],
                        default=3,
                        help_text="1=Critical, 5=Info",
                    ),
                ),
                (
                    "guidance_type",
                    models.CharField(
                        help_text="Rule that generated this (e.g., 'goal_risk', 'health_trend')",
                        max_length=100,
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("pie_insight", "PIE Insight"),
                            ("prie_prediction", "PRIE Prediction"),
                            ("sae_state", "SAE State"),
                            ("composite", "Composite (multiple sources)"),
                        ],
                        default="composite",
                        help_text="Which engine provided the primary data",
                        max_length=50,
                    ),
                ),
                (
                    "module",
                    models.CharField(
                        blank=True,
                        help_text="Domain module (health, goals, habits, etc.)",
                        max_length=50,
                    ),
                ),
                (
                    "confidence_score",
                    models.FloatField(
                        blank=True,
                        help_text="Confidence score if derived from prediction (0.0-1.0)",
                        null=True,
                    ),
                ),
                (
                    "evidence",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Structured evidence supporting this guidance",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="Whether this guidance is currently active",
                    ),
                ),
                (
                    "is_read",
                    models.BooleanField(
                        default=False,
                        help_text="Whether the user has seen this guidance",
                    ),
                ),
                (
                    "expires_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="When this guidance becomes irrelevant",
                        null=True,
                    ),
                ),
                (
                    "dedupe_key",
                    models.CharField(
                        db_index=True,
                        help_text="Prevents duplicate guidance for same situation",
                        max_length=255,
                    ),
                ),
                (
                    "metadata",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Additional structured data for rendering",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="guidance_items",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Guidance Item",
                "verbose_name_plural": "Guidance Items",
                "db_table": "core_guidance_item",
                "ordering": ["priority", "-created_at"],
                "indexes": [
                    models.Index(
                        fields=["user", "is_active"],
                        name="core_guidanc_user_id_active_idx",
                    ),
                    models.Index(
                        fields=["user", "priority"],
                        name="core_guidanc_user_id_priority_idx",
                    ),
                    models.Index(
                        fields=["user", "is_active", "priority"],
                        name="core_guidanc_user_id_act_pri_idx",
                    ),
                    models.Index(
                        fields=["dedupe_key"],
                        name="core_guidanc_dedupe_idx",
                    ),
                    models.Index(
                        fields=["expires_at"],
                        name="core_guidanc_expires_idx",
                    ),
                ],
            },
        ),
    ]
