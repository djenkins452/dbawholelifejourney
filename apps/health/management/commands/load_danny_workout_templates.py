# ==============================================================================
# File: load_danny_workout_templates.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: One-time upload of workout templates for dannyjenkins71@gmail.com
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-29
# Last Updated: 2025-12-29
# ==============================================================================
"""
Management command to load workout templates for user dannyjenkins71@gmail.com.

This is a one-time upload based on a 4-week workout program with Week 1&3 and Week 2&4 variations.
Creates 10 workout templates total (5 for each week pattern).

Usage: python manage.py load_danny_workout_templates
       python manage.py load_danny_workout_templates --clear  # Remove existing templates first
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.health.models import Exercise, WorkoutTemplate, TemplateExercise
from apps.users.models import User


# Additional exercises needed for this workout plan
ADDITIONAL_EXERCISES = {
    "resistance": {
        "Legs": [
            "Box Squat",
            "Kickbacks",
            "KB Lunges",
        ],
        "Chest": [
            "Incline Chest Press",
        ],
        "Back": [
            "Lat Pull Down",
        ],
        "Shoulders": [
            "Machine Lateral Raise",
            "BB Lateral Raise",
        ],
        "Biceps": [
            "Seated Curl",
            "EZ Bar Curl Close Grip",
            "EZ Bar Curl Wide Grip",
        ],
        "Triceps": [
            "Tricep Push Downs",
        ],
        "Core": [
            "Ab Crunch Machine",
            "Ab Twist Machine",
            "Medicine Ball Slams",
        ],
    },
    "cardio": [
        "Stationary Bike",
        "Fan Bike",
        "Rower",
        "Single Arm Farmers Carry",
        "Farmers Carry",
        "Battle Ropes",
    ],
}


# Week 1 & 3 Workout Templates
WEEK_1_3_TEMPLATES = {
    "Week 1&3 - Monday Strength": {
        "description": "Leg Press, Leg Extension, Seated Chest Press, Seated Row, Ab Crunch",
        "exercises": [
            # Warm up: 5 min bike handled separately as cardio note
            ("Leg Press", 3),
            ("Leg Extension", 3),
            ("Machine Chest Press", 3),
            ("Seated Cable Row", 3),
            ("Ab Crunch Machine", 3),
        ],
    },
    "Week 1&3 - Tuesday Cardio": {
        "description": "15 min bike, 5 min rower, stretching",
        "exercises": [
            ("Stationary Bike", 1),
            ("Rower", 1),
        ],
    },
    "Week 1&3 - Wednesday Strength": {
        "description": "Calf raises, Seated Hamstring Curls, Seated Shoulder Press, Lat Pull Down, Farmers Carry",
        "exercises": [
            ("Elliptical", 1),  # 5 min warmup
            ("Calf Raise", 3),
            ("Leg Curl", 3),
            ("Dumbbell Shoulder Press", 3),
            ("Lat Pull Down", 3),
            ("Farmers Carry", 1),
        ],
    },
    "Week 1&3 - Thursday Cardio": {
        "description": "Fan bike, battle ropes, medicine ball slams",
        "exercises": [
            ("Stationary Bike", 1),  # Easy warmup
            ("Fan Bike", 1),  # 10 min
            ("Battle Ropes", 1),  # 4x20 sec
            ("Medicine Ball Slams", 1),  # 4x8
        ],
    },
    "Week 1&3 - Friday Strength": {
        "description": "Leg Press, Leg Extension, Tricep Push Downs, Seated Curl, Ab Crunch",
        "exercises": [
            ("Leg Press", 3),
            ("Leg Extension", 3),
            ("Tricep Push Downs", 3),
            ("Seated Curl", 3),
            ("Ab Crunch Machine", 3),
        ],
    },
}


# Week 2 & 4 Workout Templates
WEEK_2_4_TEMPLATES = {
    "Week 2&4 - Monday Strength": {
        "description": "Box Squat, Kickbacks, Incline Chest Press, Seated Cable Row, Crunches",
        "exercises": [
            ("Box Squat", 3),
            ("Kickbacks", 2),  # 2x10 each side
            ("Incline Chest Press", 3),
            ("Seated Cable Row", 3),
            ("Crunches", 3),
        ],
    },
    "Week 2&4 - Tuesday Cardio": {
        "description": "15-20 min elliptical, 5 min rower, single arm farmers carry",
        "exercises": [
            ("Elliptical", 1),
            ("Rower", 1),
            ("Single Arm Farmers Carry", 1),
        ],
    },
    "Week 2&4 - Wednesday Strength": {
        "description": "KB Lunges, Hamstring Curl, Lateral Raise, Lat Pull Down",
        "exercises": [
            ("KB Lunges", 2),  # 2x6 each leg
            ("Leg Curl", 3),
            ("Machine Lateral Raise", 3),
            ("Lat Pull Down", 3),
        ],
    },
    "Week 2&4 - Thursday Cardio": {
        "description": "15 min bike, battle ropes, 5 min rower, ab twist machine",
        "exercises": [
            ("Stationary Bike", 1),
            ("Battle Ropes", 1),  # 4x25 sec
            ("Rower", 1),
            ("Ab Twist Machine", 3),  # 3x10 each side
        ],
    },
    "Week 2&4 - Friday Strength": {
        "description": "BB Calf Raises, Leg Extensions, Arnold Press, EZ Bar Curl",
        "exercises": [
            ("Calf Raise", 3),  # BB calf raises 3x10 w/5 sec pause
            ("Leg Extension", 3),
            ("Arnold Press", 3),
            ("EZ Bar Curl Close Grip", 2),
            ("EZ Bar Curl Wide Grip", 2),
        ],
    },
}


class Command(BaseCommand):
    help = "Load workout templates for dannyjenkins71@gmail.com"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Remove existing workout templates for this user before loading",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without actually creating",
        )

    def handle(self, *args, **options):
        email = "dannyjenkins71@gmail.com"

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("\n=== DRY RUN MODE ===\n"))
            self.stdout.write(f"Target user: {email}")
            self._show_plan()
            return

        # Find the user
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            self.stderr.write(
                self.style.ERROR(f"User with email {email} not found!")
            )
            return

        self.stdout.write(f"Found user: {user.email}")

        with transaction.atomic():
            # Step 1: Ensure all required exercises exist
            self._create_additional_exercises()

            # Step 2: Optionally clear existing templates
            if options["clear"]:
                deleted_count = self._clear_user_templates(user)
                self.stdout.write(
                    self.style.WARNING(f"Deleted {deleted_count} existing templates")
                )

            # Step 3: Create the workout templates
            created_count = self._create_templates(user)

            self.stdout.write(
                self.style.SUCCESS(
                    f"\nSuccessfully created {created_count} workout templates for {email}"
                )
            )

    def _show_plan(self):
        """Show what would be created in dry-run mode."""
        self.stdout.write("\nAdditional exercises to create:")
        for category, data in ADDITIONAL_EXERCISES.items():
            if category == "resistance":
                for muscle_group, exercises in data.items():
                    for name in exercises:
                        self.stdout.write(f"  + {name} ({muscle_group})")
            else:
                for name in data:
                    self.stdout.write(f"  + {name} (Cardio)")

        self.stdout.write("\nWorkout templates to create:")
        self.stdout.write("\n--- Week 1 & 3 ---")
        for name, data in WEEK_1_3_TEMPLATES.items():
            self.stdout.write(f"\n  {name}")
            self.stdout.write(f"    Description: {data['description']}")
            for exercise, sets in data["exercises"]:
                self.stdout.write(f"      - {exercise} ({sets} sets)")

        self.stdout.write("\n--- Week 2 & 4 ---")
        for name, data in WEEK_2_4_TEMPLATES.items():
            self.stdout.write(f"\n  {name}")
            self.stdout.write(f"    Description: {data['description']}")
            for exercise, sets in data["exercises"]:
                self.stdout.write(f"      - {exercise} ({sets} sets)")

    def _create_additional_exercises(self):
        """Create any exercises that don't exist yet."""
        self.stdout.write("\nChecking/creating required exercises...")

        created_count = 0

        # Create resistance exercises
        for muscle_group, exercises in ADDITIONAL_EXERCISES["resistance"].items():
            for name in exercises:
                exercise, created = Exercise.objects.get_or_create(
                    name=name,
                    defaults={
                        "category": "resistance",
                        "muscle_group": muscle_group,
                        "is_active": True,
                    },
                )
                if created:
                    created_count += 1
                    self.stdout.write(f"  + Created: {name} ({muscle_group})")

        # Create cardio exercises
        for name in ADDITIONAL_EXERCISES["cardio"]:
            exercise, created = Exercise.objects.get_or_create(
                name=name,
                defaults={
                    "category": "cardio",
                    "muscle_group": "",
                    "is_active": True,
                },
            )
            if created:
                created_count += 1
                self.stdout.write(f"  + Created: {name} (Cardio)")

        if created_count > 0:
            self.stdout.write(f"  Created {created_count} new exercises")
        else:
            self.stdout.write("  All required exercises already exist")

    def _clear_user_templates(self, user):
        """Remove all workout templates for this user."""
        templates = WorkoutTemplate.objects.filter(user=user)
        count = templates.count()
        templates.delete()
        return count

    def _create_templates(self, user):
        """Create all workout templates for the user."""
        created_count = 0

        # Create Week 1 & 3 templates
        self.stdout.write("\nCreating Week 1 & 3 templates...")
        for name, data in WEEK_1_3_TEMPLATES.items():
            if self._create_single_template(user, name, data):
                created_count += 1

        # Create Week 2 & 4 templates
        self.stdout.write("\nCreating Week 2 & 4 templates...")
        for name, data in WEEK_2_4_TEMPLATES.items():
            if self._create_single_template(user, name, data):
                created_count += 1

        return created_count

    def _create_single_template(self, user, name, data):
        """Create a single workout template with its exercises."""
        # Check if template already exists
        if WorkoutTemplate.objects.filter(user=user, name=name).exists():
            self.stdout.write(f"  - Skipping (exists): {name}")
            return False

        # Create the template
        template = WorkoutTemplate.objects.create(
            user=user,
            name=name,
            description=data["description"],
        )

        # Add exercises to template
        for order, (exercise_name, default_sets) in enumerate(data["exercises"], start=1):
            try:
                exercise = Exercise.objects.get(name=exercise_name)
                TemplateExercise.objects.create(
                    template=template,
                    exercise=exercise,
                    order=order,
                    default_sets=default_sets,
                )
            except Exercise.DoesNotExist:
                self.stderr.write(
                    self.style.WARNING(
                        f"    Warning: Exercise '{exercise_name}' not found, skipping"
                    )
                )

        self.stdout.write(f"  + Created: {name} ({template.exercise_count} exercises)")
        return True
