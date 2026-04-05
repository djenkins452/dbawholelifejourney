"""
Fix Friday workout that had its workout_type changed to 'Cycling' by the
sync_id dedup code after an incorrect merge. Clear sync_id AND reset
workout_type so the cycling workout can create its own entry.
"""

from django.db import migrations


def fix_workout_87(apps, schema_editor):
    WorkoutSession = apps.get_model("health", "WorkoutSession")

    try:
        workout = WorkoutSession.objects.get(pk=87)
    except WorkoutSession.DoesNotExist:
        return

    # Reset the stolen fields
    workout.sync_id = ""
    workout.workout_type = ""  # structured workouts don't have a workout_type
    workout.save(update_fields=["sync_id", "workout_type"])


class Migration(migrations.Migration):

    dependencies = [
        ("health", "0077_diagnose_cycling_workout"),
    ]

    operations = [
        migrations.RunPython(fix_workout_87, migrations.RunPython.noop),
    ]
