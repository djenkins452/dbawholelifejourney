"""
Change relationships_enabled default from False to True and enable it for
all existing users. Also backfill UserModulePreference rows so the module
appears in navigation for existing users.
"""

from django.db import migrations, models


def enable_relationships_for_existing_users(apps, schema_editor):
    """Enable relationships module for all existing users and backfill nav prefs."""
    UserPreferences = apps.get_model("users", "UserPreferences")
    ModuleDefinition = apps.get_model("users", "ModuleDefinition")
    UserModulePreference = apps.get_model("users", "UserModulePreference")

    # Enable the toggle for all existing users
    updated = UserPreferences.objects.filter(
        relationships_enabled=False,
    ).update(relationships_enabled=True)
    if updated:
        print(f"  Enabled relationships for {updated} existing user(s).")

    # Backfill UserModulePreference for navigation
    try:
        rel_module = ModuleDefinition.objects.get(slug="relationships")
    except ModuleDefinition.DoesNotExist:
        return

    users_with_prefs = (
        UserModulePreference.objects.values_list("user_id", flat=True).distinct()
    )
    users_with_rel = (
        UserModulePreference.objects.filter(module=rel_module)
        .values_list("user_id", flat=True)
    )

    missing_user_ids = set(users_with_prefs) - set(users_with_rel)

    created = 0
    for user_id in missing_user_ids:
        UserModulePreference.objects.create(
            user_id=user_id,
            module=rel_module,
            is_enabled=True,
            sort_order=rel_module.default_order,
        )
        created += 1

    if created:
        print(f"  Created Relationships module preference for {created} existing user(s).")


def reverse_enable(apps, schema_editor):
    """Revert: disable relationships for all users and remove nav prefs."""
    UserPreferences = apps.get_model("users", "UserPreferences")
    UserPreferences.objects.filter(
        relationships_enabled=True,
    ).update(relationships_enabled=False)

    ModuleDefinition = apps.get_model("users", "ModuleDefinition")
    UserModulePreference = apps.get_model("users", "UserModulePreference")

    try:
        rel_module = ModuleDefinition.objects.get(slug="relationships")
        UserModulePreference.objects.filter(module=rel_module).delete()
    except ModuleDefinition.DoesNotExist:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0073_add_relationships_module_definition"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userpreferences",
            name="relationships_enabled",
            field=models.BooleanField(
                default=True,
                help_text="Enable Relationships module for tracking connections and interactions",
            ),
        ),
        migrations.RunPython(
            enable_relationships_for_existing_users,
            reverse_enable,
        ),
    ]
