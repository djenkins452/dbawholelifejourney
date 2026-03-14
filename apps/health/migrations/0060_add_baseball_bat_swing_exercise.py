"""
Data migration: Add "Baseball Bat Swing" exercise to the exercise library.

Bodyweight/reps-based core exercise — user tracks reps per side (right + left).
"""

from django.db import migrations


def add_exercise(apps, schema_editor):
    Exercise = apps.get_model("health", "Exercise")
    Exercise.objects.get_or_create(
        name="Baseball Bat Swing",
        defaults={
            "category": "resistance",
            "muscle_group": "Core",
            "movement_type": "bodyweight",
            "description": "Rotational core exercise. Perform x swings from the right side, then x swings from the left side.",
            "is_active": True,
        },
    )


def remove_exercise(apps, schema_editor):
    Exercise = apps.get_model("health", "Exercise")
    Exercise.objects.filter(name="Baseball Bat Swing").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("health", "0059_load_6day_strength_program"),
    ]

    operations = [
        migrations.RunPython(add_exercise, remove_exercise),
    ]
