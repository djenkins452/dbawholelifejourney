# Generated manually on 2026-01-06
# One-time data migration to sync latest workout to matching template

from django.db import migrations


def sync_latest_workout_to_template(apps, schema_editor):
    """
    For dannyjenkins71@gmail.com, find the latest completed workout
    and sync its data to the matching template.
    """
    User = apps.get_model("users", "User")
    WorkoutSession = apps.get_model("health", "WorkoutSession")
    WorkoutTemplate = apps.get_model("health", "WorkoutTemplate")
    TemplateExercise = apps.get_model("health", "TemplateExercise")
    TemplateExerciseSet = apps.get_model("health", "TemplateExerciseSet")

    try:
        user = User.objects.get(email="dannyjenkins71@gmail.com")
    except User.DoesNotExist:
        return

    # Get the latest completed workout
    latest_workout = (
        WorkoutSession.objects.filter(user=user, completed_at__isnull=False)
        .order_by("-completed_at")
        .first()
    )

    if not latest_workout:
        return

    # Get the exercise IDs from the workout
    workout_exercise_ids = set(
        latest_workout.workout_exercises.values_list("exercise_id", flat=True)
    )

    if not workout_exercise_ids:
        return

    # Find a matching template - one that has these exercises
    matching_template = None
    best_match_count = 0

    for template in WorkoutTemplate.objects.filter(user=user):
        template_exercise_ids = set(
            template.template_exercises.values_list("exercise_id", flat=True)
        )
        # Check how many exercises match
        match_count = len(workout_exercise_ids & template_exercise_ids)
        if match_count > best_match_count:
            best_match_count = match_count
            matching_template = template

    if not matching_template or best_match_count == 0:
        return

    # Link the workout to the template
    latest_workout.from_template = matching_template
    latest_workout.save()

    # Sync the workout data to the template
    for workout_exercise in latest_workout.workout_exercises.all():
        try:
            template_exercise = TemplateExercise.objects.get(
                template=matching_template,
                exercise_id=workout_exercise.exercise_id,
            )
        except TemplateExercise.DoesNotExist:
            continue

        # Clear existing defaults and create new ones from workout
        template_exercise.set_defaults.all().delete()

        for exercise_set in workout_exercise.sets.all():
            TemplateExerciseSet.objects.create(
                template_exercise=template_exercise,
                set_number=exercise_set.set_number,
                weight=exercise_set.weight,
                reps=exercise_set.reps,
            )

        # Update default_sets count
        set_count = workout_exercise.sets.count()
        if set_count > 0:
            template_exercise.default_sets = set_count
            template_exercise.save()


def reverse_sync(apps, schema_editor):
    """No-op reverse - data stays."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("health", "0014_populate_template_defaults"),
    ]

    operations = [
        migrations.RunPython(sync_latest_workout_to_template, reverse_sync),
    ]
