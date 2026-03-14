# ==============================================================================
# File: 0059_load_6day_strength_program.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Data migration to load Danny's 6-day strength training program
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-14
# ==============================================================================
"""
Data migration: Creates a 6-day strength training program for dannyjenkins71@gmail.com.

Creates:
- New Exercise entries for any exercises not already in the library
- 6 WorkoutTemplates (Monday–Saturday) with TemplateExercise + TemplateExerciseSet defaults
- 1 WorkoutPlan ("6-Day Strength Program") with WorkoutSchedule entries
- Sunday is a rest day (no schedule entry)

Safe to re-run: skips if user not found or plan already exists.
"""

import datetime

from django.db import migrations


PLAN_NAME = "6-Day Strength Program"

# All exercises referenced by the program — (name, category, muscle_group, movement_type)
# get_or_create ensures existing entries are not duplicated.
ALL_EXERCISES = [
    ("Box Squat", "resistance", "Legs", "weighted"),
    ("Romanian Deadlift", "resistance", "Legs", "weighted"),
    ("Leg Extension", "resistance", "Legs", "weighted"),
    ("Standing Calf Raise", "resistance", "Legs", "weighted"),
    ("Goblet Squat", "resistance", "Legs", "weighted"),
    ("Barbell Glute Bridge", "resistance", "Legs", "weighted"),
    ("Leg Curl", "resistance", "Legs", "weighted"),
    ("Bench Press", "resistance", "Chest", "weighted"),
    ("Incline Dumbbell Press", "resistance", "Chest", "weighted"),
    ("Dumbbell Fly", "resistance", "Chest", "weighted"),
    ("Incline Barbell Press", "resistance", "Chest", "weighted"),
    ("Lat Pulldown", "resistance", "Back", "weighted"),
    ("Seated Cable Row", "resistance", "Back", "weighted"),
    ("Dumbbell Row", "resistance", "Back", "weighted"),
    ("Wide Grip Lat Pulldown", "resistance", "Back", "weighted"),
    ("Face Pulls", "resistance", "Back", "weighted"),
    ("Dumbbell Shoulder Press", "resistance", "Shoulders", "weighted"),
    ("Cable Lateral Raise", "resistance", "Shoulders", "weighted"),
    ("Rear Delt Fly", "resistance", "Shoulders", "weighted"),
    ("Barbell Curl", "resistance", "Biceps", "weighted"),
    ("Hammer Curl", "resistance", "Biceps", "weighted"),
    ("Cable Tricep Pushdown", "resistance", "Triceps", "weighted"),
    ("Plank", "resistance", "Core", "time"),
]

# Each template: name, description, day_of_week, exercises list
# exercises: (name, sets, reps, weight_lbs, duration_seconds, movement_type_hint, notes)
TEMPLATES = [
    {
        "name": "Monday — Lower Body Strength",
        "description": "Box Squat, Romanian Deadlift, Leg Extension, Standing Calf Raise",
        "day_of_week": 0,
        "exercises": [
            ("Box Squat", 4, 8, 135, None, None),
            ("Romanian Deadlift", 3, 10, 95, None, None),
            ("Leg Extension", 3, 12, None, None, None),
            ("Standing Calf Raise", 4, 15, None, None, None),
        ],
    },
    {
        "name": "Tuesday — Chest + Triceps",
        "description": "Bench Press, Incline Dumbbell Press, Dumbbell Fly, Cable Tricep Pushdown",
        "day_of_week": 1,
        "exercises": [
            ("Bench Press", 4, 8, 135, None, None),
            ("Incline Dumbbell Press", 3, 10, 35, None, None),
            ("Dumbbell Fly", 3, 12, 20, None, None),
            ("Cable Tricep Pushdown", 3, 12, None, None, None),
        ],
    },
    {
        "name": "Wednesday — Back + Biceps",
        "description": "Lat Pulldown, Seated Cable Row, Barbell Curl, Face Pull",
        "day_of_week": 2,
        "exercises": [
            ("Lat Pulldown", 4, 10, None, None, None),
            ("Seated Cable Row", 4, 10, None, None, None),
            ("Barbell Curl", 3, 10, 60, None, None),
            ("Face Pulls", 3, 15, None, None, None),
        ],
    },
    {
        "name": "Thursday — Lower Body Stability",
        "description": "Goblet Squat, Barbell Glute Bridge, Leg Curl, Plank",
        "day_of_week": 3,
        "exercises": [
            ("Goblet Squat", 4, 10, 50, None, None),
            ("Barbell Glute Bridge", 4, 10, 135, None, None),
            ("Leg Curl", 3, 12, None, None, None),
            ("Plank", 3, None, None, 45, None),
        ],
    },
    {
        "name": "Friday — Shoulders + Chest",
        "description": "Dumbbell Shoulder Press, Cable Lateral Raise, Rear Delt Fly, Incline Barbell Press",
        "day_of_week": 4,
        "exercises": [
            ("Dumbbell Shoulder Press", 4, 8, 30, None, None),
            ("Cable Lateral Raise", 3, 12, None, None, None),
            ("Rear Delt Fly", 3, 12, None, None, None),
            ("Incline Barbell Press", 3, 10, 115, None, None),
        ],
    },
    {
        "name": "Saturday — Back + Arms",
        "description": "Dumbbell Row, Wide Grip Lat Pulldown, Hammer Curl, Cable Tricep Pushdown",
        "day_of_week": 5,
        "exercises": [
            ("Dumbbell Row", 4, 10, 45, None, None),
            ("Wide Grip Lat Pulldown", 3, 10, None, None, None),
            ("Hammer Curl", 3, 12, None, None, None),
            ("Cable Tricep Pushdown", 3, 12, None, None, None),
        ],
    },
]

PREFERRED_TIME = datetime.time(17, 0)  # 5:00 PM


def load_program(apps, schema_editor):
    User = apps.get_model("users", "User")
    Exercise = apps.get_model("health", "Exercise")
    WorkoutTemplate = apps.get_model("health", "WorkoutTemplate")
    TemplateExercise = apps.get_model("health", "TemplateExercise")
    TemplateExerciseSet = apps.get_model("health", "TemplateExerciseSet")
    WorkoutPlan = apps.get_model("health", "WorkoutPlan")
    WorkoutSchedule = apps.get_model("health", "WorkoutSchedule")
    TransformationProtocol = apps.get_model("health", "TransformationProtocol")

    email = "dannyjenkins71@gmail.com"
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        print(f"  User {email} not found. Skipping 6-day program import.")
        return

    # Skip if plan already exists
    if WorkoutPlan.objects.filter(user=user, name=PLAN_NAME).exists():
        print(f"  Plan '{PLAN_NAME}' already exists. Skipping.")
        return

    # Step 1: Ensure all referenced exercises exist
    for name, category, muscle_group, movement_type in ALL_EXERCISES:
        Exercise.objects.get_or_create(
            name=name,
            defaults={
                "category": category,
                "muscle_group": muscle_group,
                "movement_type": movement_type,
                "is_active": True,
            },
        )

    # Step 2: Create templates with exercises and set defaults
    template_map = {}  # day_of_week -> template

    for tpl_def in TEMPLATES:
        template = WorkoutTemplate.objects.create(
            user=user,
            name=tpl_def["name"],
            description=tpl_def["description"],
        )
        template_map[tpl_def["day_of_week"]] = template

        for order, (ex_name, sets, reps, weight, duration, notes) in enumerate(
            tpl_def["exercises"], start=1
        ):
            exercise = Exercise.objects.get(name=ex_name)
            te = TemplateExercise.objects.create(
                template=template,
                exercise=exercise,
                order=order,
                default_sets=sets,
                notes=notes or "",
            )

            # Create TemplateExerciseSet defaults for each set
            for set_num in range(1, sets + 1):
                TemplateExerciseSet.objects.create(
                    template_exercise=te,
                    set_number=set_num,
                    weight=weight,
                    reps=reps,
                    duration_seconds=duration,
                )

        print(f"  + Created template: {tpl_def['name']}")

    # Step 3: Find active TransformationProtocol
    protocol = TransformationProtocol.objects.filter(
        user=user, is_active=True
    ).first()

    # Step 4: Create WorkoutPlan
    plan = WorkoutPlan.objects.create(
        user=user,
        name=PLAN_NAME,
        description=(
            "6-day strength training program. "
            "Mon: Lower Strength, Tue: Chest+Triceps, Wed: Back+Biceps, "
            "Thu: Lower Stability, Fri: Shoulders+Chest, Sat: Back+Arms. "
            "Sunday rest."
        ),
        is_active=True,
        days_per_week=6,
        goal="muscle gain",
        transformation_protocol=protocol,
    )

    # Step 5: Create weekly schedule
    for day_of_week, template in template_map.items():
        WorkoutSchedule.objects.create(
            plan=plan,
            day_of_week=day_of_week,
            template=template,
            preferred_time=PREFERRED_TIME,
        )

    print(f"  + Created plan '{PLAN_NAME}' with 6 templates and 6 scheduled days.")


def reverse_program(apps, schema_editor):
    """Remove the program and its templates."""
    User = apps.get_model("users", "User")
    WorkoutPlan = apps.get_model("health", "WorkoutPlan")
    WorkoutTemplate = apps.get_model("health", "WorkoutTemplate")

    email = "dannyjenkins71@gmail.com"
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return

    # Delete plan (cascade deletes schedule entries)
    WorkoutPlan.objects.filter(user=user, name=PLAN_NAME).delete()

    # Delete templates created by this migration
    template_names = [t["name"] for t in TEMPLATES]
    WorkoutTemplate.objects.filter(user=user, name__in=template_names).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("health", "0058_classify_exercise_movement_types"),
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(load_program, reverse_program),
    ]
