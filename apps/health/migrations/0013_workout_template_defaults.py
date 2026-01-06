# Generated manually on 2026-01-06

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("health", "0012_dexcom_cgm_integration"),
    ]

    operations = [
        # Add from_template FK to WorkoutSession
        migrations.AddField(
            model_name="workoutsession",
            name="from_template",
            field=models.ForeignKey(
                blank=True,
                help_text="Template this workout was created from, if any",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="workout_sessions",
                to="health.workouttemplate",
            ),
        ),
        # Create TemplateExerciseSet model
        migrations.CreateModel(
            name="TemplateExerciseSet",
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
                ("set_number", models.PositiveIntegerField()),
                (
                    "weight",
                    models.DecimalField(
                        blank=True,
                        decimal_places=1,
                        help_text="Default weight in pounds",
                        max_digits=6,
                        null=True,
                    ),
                ),
                ("reps", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "template_exercise",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="default_sets",
                        to="health.templateexercise",
                    ),
                ),
            ],
            options={
                "verbose_name": "template exercise set",
                "verbose_name_plural": "template exercise sets",
                "ordering": ["set_number"],
                "unique_together": {("template_exercise", "set_number")},
            },
        ),
    ]
