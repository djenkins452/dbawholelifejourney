"""
Data migration: Add Hip Hinges and Band Pull-Aparts to warmup sequence.

Adds after Baseball Bat Swing (order=0) in all 6-Day Strength Program templates:
- Hip Hinges at order=1 (1 set x 15 reps)
- Band Pull-Aparts at order=2 (1 set x 20 reps)
Bumps existing workout exercises up by 2 to make room.
"""

from django.db import migrations


TEMPLATE_NAMES = [
    "Monday — Lower Body Strength",
    "Tuesday — Chest + Triceps",
    "Wednesday — Back + Biceps",
    "Thursday — Lower Body Stability",
    "Friday — Shoulders + Chest",
    "Saturday — Back + Arms",
]

# (name, category, muscle_group, movement_type)
NEW_EXERCISES = [
    ("Hip Hinge", "resistance", "Legs", "bodyweight"),
    ("Band Pull-Apart", "resistance", "Back", "bodyweight"),
]

# (exercise_name, order, sets, reps, notes)
WARMUP_ADDITIONS = [
    ("Hip Hinge", 1, 1, 15, "Warmup: 15 reps"),
    ("Band Pull-Apart", 2, 1, 20, "Warmup: 20 reps"),
]


def add_warmup_exercises(apps, schema_editor):
    User = apps.get_model("users", "User")
    Exercise = apps.get_model("health", "Exercise")
    WorkoutTemplate = apps.get_model("health", "WorkoutTemplate")
    TemplateExercise = apps.get_model("health", "TemplateExercise")
    TemplateExerciseSet = apps.get_model("health", "TemplateExerciseSet")

    email = "dannyjenkins71@gmail.com"
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        print(f"  User {email} not found. Skipping warmup additions.")
        return

    # Ensure exercises exist
    for name, category, muscle_group, movement_type in NEW_EXERCISES:
        Exercise.objects.get_or_create(
            name=name,
            defaults={
                "category": category,
                "muscle_group": muscle_group,
                "movement_type": movement_type,
                "is_active": True,
            },
        )

    for tpl_name in TEMPLATE_NAMES:
        try:
            template = WorkoutTemplate.objects.get(user=user, name=tpl_name)
        except WorkoutTemplate.DoesNotExist:
            print(f"  Template '{tpl_name}' not found. Skipping.")
            continue

        # Bump non-warmup exercises (order >= 2) up by 2 to make room
        # Baseball Bat Swing is at order=0, main exercises start at 2+
        for te in template.template_exercises.filter(order__gte=2).order_by("-order"):
            te.order = te.order + 2
            te.save()

        # Add the two new warmup exercises
        for ex_name, order, sets, reps, notes in WARMUP_ADDITIONS:
            exercise = Exercise.objects.get(name=ex_name)

            if TemplateExercise.objects.filter(template=template, exercise=exercise).exists():
                continue

            te = TemplateExercise.objects.create(
                template=template,
                exercise=exercise,
                order=order,
                default_sets=sets,
                notes=notes,
            )

            for set_num in range(1, sets + 1):
                TemplateExerciseSet.objects.create(
                    template_exercise=te,
                    set_number=set_num,
                    reps=reps,
                )

        print(f"  + Added Hip Hinge + Band Pull-Apart warmup to {tpl_name}")


def remove_warmup_exercises(apps, schema_editor):
    User = apps.get_model("users", "User")
    Exercise = apps.get_model("health", "Exercise")
    WorkoutTemplate = apps.get_model("health", "WorkoutTemplate")
    TemplateExercise = apps.get_model("health", "TemplateExercise")

    email = "dannyjenkins71@gmail.com"
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return

    for ex_name in ["Hip Hinge", "Band Pull-Apart"]:
        try:
            exercise = Exercise.objects.get(name=ex_name)
        except Exercise.DoesNotExist:
            continue

        for tpl_name in TEMPLATE_NAMES:
            try:
                template = WorkoutTemplate.objects.get(user=user, name=tpl_name)
            except WorkoutTemplate.DoesNotExist:
                continue
            TemplateExercise.objects.filter(template=template, exercise=exercise).delete()

        # Restore ordering by shifting exercises back down
        for tpl_name in TEMPLATE_NAMES:
            try:
                template = WorkoutTemplate.objects.get(user=user, name=tpl_name)
            except WorkoutTemplate.DoesNotExist:
                continue
            for i, te in enumerate(template.template_exercises.all().order_by("order")):
                te.order = i
                te.save()


class Migration(migrations.Migration):

    dependencies = [
        ("health", "0061_add_bat_swing_warmup_to_templates"),
    ]

    operations = [
        migrations.RunPython(add_warmup_exercises, remove_warmup_exercises),
    ]
