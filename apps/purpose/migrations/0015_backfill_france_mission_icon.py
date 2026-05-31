from django.db import migrations


def backfill_france_flag(apps, schema_editor):
    """One-time data backfill: give the France Primary Mission its flag icon.

    The Mission card renders ``mission_icon`` verbatim and NEVER infers an
    icon from title words at runtime (``if "France" in title`` is forbidden
    runtime logic). This is a targeted, idempotent DATA backfill for existing
    primary-mission goals that obviously want a country flag but were created
    before the Mission Icon field existed. It only touches rows where the icon
    is still blank, so a user-set icon is never overwritten.
    """
    LifeGoal = apps.get_model("purpose", "LifeGoal")
    LifeGoal.objects.filter(
        is_primary_mission=True,
        mission_icon="",
        title__icontains="france",
    ).update(mission_icon="\U0001F1EB\U0001F1F7")  # 🇫🇷


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("purpose", "0014_lifegoal_mission_icon"),
    ]

    operations = [
        migrations.RunPython(backfill_france_flag, noop),
    ]
