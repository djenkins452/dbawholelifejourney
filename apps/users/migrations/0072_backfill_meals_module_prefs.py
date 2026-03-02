"""
Data migration to backfill UserModulePreference for the Meals module.

When ModuleDefinition for Meals was created in 0071, existing users didn't
get a UserModulePreference row. This migration creates the missing
preference rows so Meals appears in the navigation for all existing users.
"""

from django.db import migrations


def backfill_meals_prefs(apps, schema_editor):
    """Create UserModulePreference for Meals for all users who don't have one."""
    ModuleDefinition = apps.get_model("users", "ModuleDefinition")
    UserModulePreference = apps.get_model("users", "UserModulePreference")

    try:
        meals_module = ModuleDefinition.objects.get(slug="meals")
    except ModuleDefinition.DoesNotExist:
        return

    # Find users who already have at least one module preference but not meals
    users_with_prefs = (
        UserModulePreference.objects.values_list("user_id", flat=True).distinct()
    )
    users_with_meals = (
        UserModulePreference.objects.filter(module=meals_module)
        .values_list("user_id", flat=True)
    )

    missing_user_ids = set(users_with_prefs) - set(users_with_meals)

    created = 0
    for user_id in missing_user_ids:
        UserModulePreference.objects.create(
            user_id=user_id,
            module=meals_module,
            is_enabled=True,
            sort_order=meals_module.default_order,
        )
        created += 1

    if created:
        print(f"  Created Meals module preference for {created} existing user(s).")


def reverse_backfill(apps, schema_editor):
    """Remove Meals UserModulePreference rows created by this migration."""
    ModuleDefinition = apps.get_model("users", "ModuleDefinition")
    UserModulePreference = apps.get_model("users", "UserModulePreference")

    try:
        meals_module = ModuleDefinition.objects.get(slug="meals")
    except ModuleDefinition.DoesNotExist:
        return

    UserModulePreference.objects.filter(module=meals_module).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0071_add_meals_module_definition"),
    ]

    operations = [
        migrations.RunPython(backfill_meals_prefs, reverse_backfill),
    ]
