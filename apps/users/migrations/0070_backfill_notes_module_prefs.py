"""
Data migration to backfill UserModulePreference for the Notes module.

When ModuleDefinition for Notes was created in 0069, existing users didn't
get a UserModulePreference row because initialize_for_user() only ran on
first login (when a user had zero prefs). This migration creates the missing
preference rows so Notes appears in the navigation for all existing users.
"""

from django.db import migrations


def backfill_notes_prefs(apps, schema_editor):
    """Create UserModulePreference for Notes for all users who don't have one."""
    ModuleDefinition = apps.get_model("users", "ModuleDefinition")
    UserModulePreference = apps.get_model("users", "UserModulePreference")
    User = apps.get_model("users", "User")

    try:
        notes_module = ModuleDefinition.objects.get(slug="notes")
    except ModuleDefinition.DoesNotExist:
        return

    # Find users who already have at least one module preference but not notes
    users_with_prefs = (
        UserModulePreference.objects.values_list("user_id", flat=True).distinct()
    )
    users_with_notes = (
        UserModulePreference.objects.filter(module=notes_module)
        .values_list("user_id", flat=True)
    )

    missing_user_ids = set(users_with_prefs) - set(users_with_notes)

    created = 0
    for user_id in missing_user_ids:
        UserModulePreference.objects.create(
            user_id=user_id,
            module=notes_module,
            is_enabled=True,
            sort_order=notes_module.default_order,
        )
        created += 1

    if created:
        print(f"  Created Notes module preference for {created} existing user(s).")


def reverse_backfill(apps, schema_editor):
    """Remove Notes UserModulePreference rows created by this migration."""
    ModuleDefinition = apps.get_model("users", "ModuleDefinition")
    UserModulePreference = apps.get_model("users", "UserModulePreference")

    try:
        notes_module = ModuleDefinition.objects.get(slug="notes")
    except ModuleDefinition.DoesNotExist:
        return

    UserModulePreference.objects.filter(module=notes_module).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0069_add_notes_module_definition"),
    ]

    operations = [
        migrations.RunPython(backfill_notes_prefs, reverse_backfill),
    ]
