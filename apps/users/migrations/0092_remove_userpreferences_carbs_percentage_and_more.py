# Foundation 1A — Nutrition Truth Consolidation.
# Backfill the single canonical target store (health.NutritionGoals, grams) from the
# duplicate UserPreferences fields (calorie goal + macro percentages), THEN drop those
# fields. The RunPython runs before the RemoveField ops, so the historical
# UserPreferences model still has the columns when we read them (data-loss-safe).
from datetime import date

from django.db import migrations


def backfill_nutrition_goals(apps, schema_editor):
    """For each user with a calorie goal in UserPreferences but no active
    NutritionGoals row, create one from the same percentage->grams formula the
    retired code used. Users whose goals were already mirrored (the old one-way
    _sync) are skipped — NutritionGoals already holds their canonical targets."""
    UserPreferences = apps.get_model('users', 'UserPreferences')
    NutritionGoals = apps.get_model('health', 'NutritionGoals')
    today = date.today()
    created = 0

    for prefs in UserPreferences.objects.filter(
        daily_calorie_goal__isnull=False,
    ).iterator():
        if not prefs.user_id:
            continue
        if NutritionGoals.objects.filter(
            user_id=prefs.user_id, effective_until__isnull=True,
        ).exists():
            continue

        cal = prefs.daily_calorie_goal or 2000

        def grams(pct, divisor):
            return round((cal * pct / 100) / divisor) if pct is not None else None

        NutritionGoals.objects.create(
            user_id=prefs.user_id,
            effective_from=today,
            daily_calorie_target=cal,
            daily_protein_target_g=grams(prefs.protein_percentage, 4),
            daily_carb_target_g=grams(prefs.carbs_percentage, 4),
            daily_fat_target_g=grams(prefs.fat_percentage, 9),
        )
        created += 1

    if created:
        print(f"  [nutrition consolidation] backfilled {created} NutritionGoals "
              f"from UserPreferences")


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0091_enable_model_interface_writes_for_owner'),
        # Cross-app write target — ensure the NutritionGoals schema exists.
        ('health', '0103_healthkitdailymetric_and_more'),
    ]

    operations = [
        # 1) Preserve the data in the canonical store BEFORE dropping the columns.
        migrations.RunPython(backfill_nutrition_goals, migrations.RunPython.noop),
        # 2) Remove the duplicate target store.
        migrations.RemoveField(
            model_name='userpreferences',
            name='carbs_percentage',
        ),
        migrations.RemoveField(
            model_name='userpreferences',
            name='daily_calorie_goal',
        ),
        migrations.RemoveField(
            model_name='userpreferences',
            name='fat_percentage',
        ),
        migrations.RemoveField(
            model_name='userpreferences',
            name='protein_percentage',
        ),
    ]
