"""
Management command to populate the Exercise library.

Creates default exercises for resistance training and cardio.
Safe to run multiple times - uses get_or_create.

Usage: python manage.py populate_exercises
"""

from django.core.management.base import BaseCommand

from apps.health.models import Exercise


# Resistance exercises organized by muscle group
RESISTANCE_EXERCISES = {
    "Chest": [
        "Bench Press",
        "Incline Bench Press",
        "Decline Bench Press",
        "Dumbbell Bench Press",
        "Dumbbell Fly",
        "Push-ups",
        "Cable Crossover",
        "Chest Dips",
        "Machine Chest Press",
        "Pec Deck",
    ],
    "Back": [
        "Deadlift",
        "Bent Over Row",
        "Lat Pulldown",
        "Seated Cable Row",
        "Pull-ups",
        "Chin-ups",
        "T-Bar Row",
        "Face Pulls",
        "Single Arm Dumbbell Row",
        "Machine Row",
    ],
    "Shoulders": [
        "Overhead Press",
        "Dumbbell Shoulder Press",
        "Lateral Raise",
        "Front Raise",
        "Rear Delt Fly",
        "Arnold Press",
        "Shrugs",
        "Upright Row",
        "Cable Lateral Raise",
    ],
    "Legs": [
        "Squat",
        "Front Squat",
        "Leg Press",
        "Lunges",
        "Walking Lunges",
        "Leg Curl",
        "Leg Extension",
        "Calf Raise",
        "Seated Calf Raise",
        "Romanian Deadlift",
        "Hip Thrust",
        "Bulgarian Split Squat",
        "Goblet Squat",
        "Hack Squat",
    ],
    "Biceps": [
        "Bicep Curl",
        "Hammer Curl",
        "Preacher Curl",
        "Concentration Curl",
        "Cable Curl",
        "Incline Dumbbell Curl",
        "EZ Bar Curl",
    ],
    "Triceps": [
        "Tricep Pushdown",
        "Skull Crushers",
        "Tricep Dips",
        "Overhead Tricep Extension",
        "Close Grip Bench Press",
        "Cable Tricep Kickback",
    ],
    "Core": [
        "Plank",
        "Crunches",
        "Russian Twist",
        "Leg Raise",
        "Hanging Leg Raise",
        "Cable Crunch",
        "Ab Wheel Rollout",
        "Mountain Climbers",
        "Dead Bug",
        "Bird Dog",
    ],
}

CARDIO_EXERCISES = [
    "Running",
    "Walking",
    "Cycling",
    "Swimming",
    "Elliptical",
    "Rowing Machine",
    "Stair Climber",
    "Jump Rope",
    "HIIT",
    "Hiking",
    "Treadmill",
    "Stationary Bike",
    "Spinning",
    "Jogging",
    "Sprints",
    "Box Jumps",
    "Burpees",
    "Battle Ropes",
    "Jumping Jacks",
    "Dancing",
]


class Command(BaseCommand):
    help = "Populate the exercise library with default exercises"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear all exercises before populating (use with caution)",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            self.stdout.write(self.style.WARNING("Clearing all exercises..."))
            Exercise.objects.all().delete()

        self.stdout.write("Populating exercise library...\n")

        # Create resistance exercises
        resistance_count = 0
        for muscle_group, exercises in RESISTANCE_EXERCISES.items():
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
                    resistance_count += 1
                    self.stdout.write(f"  + {name} ({muscle_group})")

        # Create cardio exercises
        cardio_count = 0
        for name in CARDIO_EXERCISES:
            exercise, created = Exercise.objects.get_or_create(
                name=name,
                defaults={
                    "category": "cardio",
                    "muscle_group": "",
                    "is_active": True,
                },
            )
            if created:
                cardio_count += 1
                self.stdout.write(f"  + {name} (Cardio)")

        total_created = resistance_count + cardio_count
        total_existing = Exercise.objects.count()

        if total_created > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nCreated {resistance_count} resistance + {cardio_count} cardio exercises."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("\nAll exercises already exist."))

        self.stdout.write(f"Total exercises in library: {total_existing}")
