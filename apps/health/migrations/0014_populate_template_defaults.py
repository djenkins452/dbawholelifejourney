# Generated manually on 2026-01-06
# Data migration to populate template exercise defaults from historical workouts

from django.db import migrations


def populate_template_defaults(apps, schema_editor):
    """
    For each user's templates, find their most recent completed workout
    using each template and use that workout's weights/reps as the template defaults.
    """
    User = apps.get_model("users", "User")
    WorkoutSession = apps.get_model("health", "WorkoutSession")
    WorkoutTemplate = apps.get_model("health", "WorkoutTemplate")
    TemplateExercise = apps.get_model("health", "TemplateExercise")
    TemplateExerciseSet = apps.get_model("health", "TemplateExerciseSet")

    # Get all users who have templates
    users_with_templates = User.objects.filter(
        workouttemplate_set__isnull=False
    ).distinct()

    for user in users_with_templates:
        # Get all templates for this user
        templates = WorkoutTemplate.objects.filter(user=user)

        for template in templates:
            # Get the most recent completed workout for this user
            # that has exercises matching this template
            template_exercise_ids = list(
                TemplateExercise.objects.filter(template=template).values_list(
                    "exercise_id", flat=True
                )
            )

            if not template_exercise_ids:
                continue

            # Find the most recent completed workout containing any of these exercises
            recent_workout = (
                WorkoutSession.objects.filter(
                    user=user,
                    completed_at__isnull=False,
                    workout_exercises__exercise_id__in=template_exercise_ids,
                )
                .order_by("-completed_at")
                .first()
            )

            if not recent_workout:
                continue

            # Link this workout to the template for future reference
            recent_workout.from_template = template
            recent_workout.save()

            # For each template exercise, find matching workout exercise and populate defaults
            for te in TemplateExercise.objects.filter(template=template):
                workout_exercise = recent_workout.workout_exercises.filter(
                    exercise_id=te.exercise_id
                ).first()

                if not workout_exercise:
                    continue

                # Get sets from the workout exercise and create template defaults
                for exercise_set in workout_exercise.sets.all():
                    TemplateExerciseSet.objects.update_or_create(
                        template_exercise=te,
                        set_number=exercise_set.set_number,
                        defaults={
                            "weight": exercise_set.weight,
                            "reps": exercise_set.reps,
                        },
                    )

                # Update default_sets count if needed
                set_count = workout_exercise.sets.count()
                if set_count > te.default_sets:
                    te.default_sets = set_count
                    te.save()


def reverse_populate(apps, schema_editor):
    """Remove all template exercise sets."""
    TemplateExerciseSet = apps.get_model("health", "TemplateExerciseSet")
    TemplateExerciseSet.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("health", "0013_workout_template_defaults"),
    ]

    operations = [
        migrations.RunPython(populate_template_defaults, reverse_populate),
    ]
