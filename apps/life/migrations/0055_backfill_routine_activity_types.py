"""Backfill RoutineSchedule.activity_type from the schedule name.

Makes existing nutrition / weigh-in / measurement / prayer / workout / journal /
bible routines METADATA-DRIVEN so the Action Router routes them to their
workflow by capability (rename-safe), not by title keyword. Only touches rows
whose activity_type is currently blank, and only when the name clearly indicates
a capability — genuine household routines (shower, laundry, trash) are left
untagged. Idempotent and safe to re-run.
"""
from django.db import migrations

# Keyword → activity_type. Ordered; first hit wins. Mirrors the Action Router's
# keyword bridge so backfilled tags agree with live routing.
_RULES = [
    (("body composition", "body-composition", "measurement", "measurements",
      "waist", "circumference", "tape measure"), "measurement"),
    (("nutrition", "macro", "macros", "protein", "log food", "food log",
      "log meal", "calorie", "calories", "log nutrition"), "nutrition_anchor"),
    (("weigh", "weight", "scale"), "weigh_in"),
    (("prayer", "pray", "quiet time"), "prayer"),
    (("bible", "scripture", "devotional", "reading plan", "psalm", "gospel"),
     "bible"),
    (("journal", "journaling", "gratitude"), "journal"),
    (("workout", "lift", "cardio", "gym", "exercise", "pickleball", "run",
      "yoga", "stretch"), "workout"),
]


def _infer(name: str):
    n = (name or "").lower()
    for keywords, activity in _RULES:
        if any(k in n for k in keywords):
            return activity
    return None


def backfill(apps, schema_editor):
    RoutineSchedule = apps.get_model("life", "RoutineSchedule")
    from django.db.models import Q

    qs = RoutineSchedule.objects.filter(
        Q(activity_type__isnull=True) | Q(activity_type="")
    ).only("id", "name")
    updated = 0
    for sched in qs.iterator():
        activity = _infer(sched.name)
        if activity:
            sched.activity_type = activity
            sched.save(update_fields=["activity_type"])
            updated += 1
    print(f"[0055] backfilled activity_type on {updated} routine schedules")


def noop_reverse(apps, schema_editor):
    # Non-destructive: leave the tags in place on reverse.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("life", "0054_alter_routineschedule_activity_type"),
    ]

    operations = [
        migrations.RunPython(backfill, noop_reverse),
    ]
