"""
Sync latest workout data to matching templates.

This command finds the latest completed workout for each user with templates
and syncs the weight/reps data to the template defaults.
"""

from django.core.management.base import BaseCommand

from apps.health.models import (
    TemplateExercise,
    TemplateExerciseSet,
    WorkoutSession,
    WorkoutTemplate,
)
from apps.users.models import User


class Command(BaseCommand):
    help = "Sync latest workout data to matching templates"

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            type=str,
            help="Only sync for a specific user email",
        )

    def handle(self, *args, **options):
        email = options.get("email")

        if email:
            users = User.objects.filter(email=email)
        else:
            # Get all users who have templates
            users = User.objects.filter(workouttemplates__isnull=False).distinct()

        synced_count = 0

        for user in users:
            self.stdout.write(f"Processing user: {user.email}")

            # Get all templates for this user
            templates = WorkoutTemplate.objects.filter(user=user)

            for template in templates:
                self.stdout.write(f"  Checking template: {template.name}")

                # Get template exercise IDs
                template_exercise_ids = set(
                    template.template_exercises.values_list("exercise_id", flat=True)
                )
                self.stdout.write(f"    Template has {len(template_exercise_ids)} exercises")

                if not template_exercise_ids:
                    continue

                # Find the most recent completed workout with matching exercises
                latest_workout = (
                    WorkoutSession.objects.filter(
                        user=user,
                        completed_at__isnull=False,
                        workout_exercises__exercise_id__in=template_exercise_ids,
                    )
                    .order_by("-completed_at")
                    .first()
                )

                if not latest_workout:
                    self.stdout.write(f"    No matching workout found")
                    continue

                self.stdout.write(
                    f"    Found workout: {latest_workout.name} on {latest_workout.date}"
                )

                # Link workout to template if not already linked
                if not latest_workout.from_template:
                    latest_workout.from_template = template
                    latest_workout.save(update_fields=["from_template"])

                # Sync each exercise
                for workout_exercise in latest_workout.workout_exercises.all():
                    try:
                        template_exercise = TemplateExercise.objects.get(
                            template=template,
                            exercise_id=workout_exercise.exercise_id,
                        )
                    except TemplateExercise.DoesNotExist:
                        continue

                    # Clear existing defaults and create new ones
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
                        template_exercise.save(update_fields=["default_sets"])

                synced_count += 1

        self.stdout.write(
            self.style.SUCCESS(f"Successfully synced {synced_count} templates")
        )
