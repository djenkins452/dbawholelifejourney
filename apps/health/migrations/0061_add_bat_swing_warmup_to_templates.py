"""
Data migration: Add Baseball Bat Swing as warmup to all 6-Day Strength Program templates.

3 sets x 10 reps: right swings, left swings, upside-down swings.
Inserted at order=0 so it appears first in each workout.
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


def add_warmup(apps, schema_editor):
    User = apps.get_model("users", "User")
    Exercise = apps.get_model("health", "Exercise")
    WorkoutTemplate = apps.get_model("health", "WorkoutTemplate")
    TemplateExercise = apps.get_model("health", "TemplateExercise")
    TemplateExerciseSet = apps.get_model("health", "TemplateExerciseSet")

    email = "dannyjenkins71@gmail.com"
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        print(f"  User {email} not found. Skipping bat swing warmup.")
        return

    try:
        exercise = Exercise.objects.get(name="Baseball Bat Swing")
    except Exercise.DoesNotExist:
        print("  Baseball Bat Swing exercise not found. Skipping.")
        return

    for tpl_name in TEMPLATE_NAMES:
        try:
            template = WorkoutTemplate.objects.get(user=user, name=tpl_name)
        except WorkoutTemplate.DoesNotExist:
            print(f"  Template '{tpl_name}' not found. Skipping.")
            continue

        # Skip if already added
        if TemplateExercise.objects.filter(template=template, exercise=exercise).exists():
            continue

        # Bump existing exercises' order to make room at position 0
        for te in template.template_exercises.all():
            te.order = te.order + 1
            te.save()

        # Add bat swing at order=0
        te = TemplateExercise.objects.create(
            template=template,
            exercise=exercise,
            order=0,
            default_sets=3,
            notes="Warmup: 10 right swings, 10 left swings, 10 upside-down swings",
        )

        # 3 sets x 10 reps
        for set_num in range(1, 4):
            TemplateExerciseSet.objects.create(
                template_exercise=te,
                set_number=set_num,
                reps=10,
            )

        print(f"  + Added Baseball Bat Swing warmup to {tpl_name}")


def remove_warmup(apps, schema_editor):
    User = apps.get_model("users", "User")
    Exercise = apps.get_model("health", "Exercise")
    WorkoutTemplate = apps.get_model("health", "WorkoutTemplate")
    TemplateExercise = apps.get_model("health", "TemplateExercise")

    email = "dannyjenkins71@gmail.com"
    try:
        user = User.objects.get(email__iexact=email)
        exercise = Exercise.objects.get(name="Baseball Bat Swing")
    except (User.DoesNotExist, Exercise.DoesNotExist):
        return

    for tpl_name in TEMPLATE_NAMES:
        try:
            template = WorkoutTemplate.objects.get(user=user, name=tpl_name)
        except WorkoutTemplate.DoesNotExist:
            continue

        TemplateExercise.objects.filter(template=template, exercise=exercise).delete()

        # Restore original ordering (shift back down)
        for i, te in enumerate(template.template_exercises.all().order_by("order"), start=1):
            te.order = i
            te.save()


class Migration(migrations.Migration):

    dependencies = [
        ("health", "0060_add_baseball_bat_swing_exercise"),
    ]

    operations = [
        migrations.RunPython(add_warmup, remove_warmup),
    ]
