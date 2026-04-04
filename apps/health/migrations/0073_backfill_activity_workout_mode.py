"""
Backfill session_mode='activity' for existing WorkoutSessions that have
duration_minutes set but no exercise sets (i.e., cardio/activity workouts
logged before the session_mode field was added).

Also backfills intensity using derive_intensity() for activity workouts
that have CardioDetails with an intensity value.
"""
from django.db import migrations, models


def backfill_activity_mode(apps, schema_editor):
    WorkoutSession = apps.get_model("health", "WorkoutSession")
    WorkoutExercise = apps.get_model("health", "WorkoutExercise")
    ExerciseSet = apps.get_model("health", "ExerciseSet")
    CardioDetails = apps.get_model("health", "CardioDetails")

    # Find sessions with duration but no exercise sets — these are activity workouts.
    # Also include Apple Health imports which are always activity-style.
    candidates = WorkoutSession.objects.filter(
        session_mode="structured",  # only un-backfilled
        duration_minutes__isnull=False,
    )

    updated_count = 0
    for session in candidates.iterator(chunk_size=200):
        # Check if this session has any resistance sets
        has_sets = ExerciseSet.objects.filter(
            workout_exercise__session=session,
        ).exists()

        if has_sets:
            continue  # Structured workout with sets — skip

        # No sets → this is an activity workout
        session.session_mode = "activity"

        # Try to pull intensity from CardioDetails
        if not session.intensity:
            cardio = CardioDetails.objects.filter(
                workout_exercise__session=session,
            ).first()
            if cardio and cardio.intensity:
                # Normalize "medium" → "moderate"
                intensity = cardio.intensity
                if intensity == "medium":
                    intensity = "moderate"
                if intensity in ("easy", "moderate", "hard"):
                    session.intensity = intensity

        session.save(update_fields=["session_mode", "intensity"])
        updated_count += 1

    if updated_count:
        print(f"  Backfilled {updated_count} workout sessions to activity mode")


def reverse_backfill(apps, schema_editor):
    WorkoutSession = apps.get_model("health", "WorkoutSession")
    WorkoutSession.objects.filter(session_mode="activity").update(
        session_mode="structured", intensity=""
    )


class Migration(migrations.Migration):
    dependencies = [
        ("health", "0072_add_session_mode_and_intensity_to_workout"),
    ]

    operations = [
        # Fix intensity choices: old migration used low/high, model uses easy/hard
        migrations.AlterField(
            model_name="workoutsession",
            name="intensity",
            field=models.CharField(
                blank=True,
                choices=[("easy", "Easy"), ("moderate", "Moderate"), ("hard", "Hard")],
                default="",
                help_text="User-reported or derived intensity level",
                max_length=20,
            ),
        ),
        migrations.RunPython(backfill_activity_mode, reverse_backfill),
    ]
