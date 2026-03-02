# Data migration to add Meals ModuleDefinition for navigation

from django.db import migrations


def add_meals_module(apps, schema_editor):
    """Add Meals module to ModuleDefinition so it appears in navigation."""
    ModuleDefinition = apps.get_model("users", "ModuleDefinition")

    ModuleDefinition.objects.get_or_create(
        slug="meals",
        defaults={
            "name": "Meals",
            "description": "Meal intelligence: dinner suggestions, pantry tracking, meal planning",
            "icon_svg": (
                '<path d="M18 8h1a4 4 0 0 1 0 8h-1"/>'
                '<path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z"/>'
                '<line x1="6" y1="1" x2="6" y2="4"/>'
                '<line x1="10" y1="1" x2="10" y2="4"/>'
                '<line x1="14" y1="1" x2="14" y2="4"/>'
            ),
            "route_name": "meals:dashboard",
            "default_order": 35,
            "is_active": True,
            "preference_field": "",
        },
    )


def remove_meals_module(apps, schema_editor):
    """Remove Meals module definition."""
    ModuleDefinition = apps.get_model("users", "ModuleDefinition")
    ModuleDefinition.objects.filter(slug="meals").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0070_backfill_notes_module_prefs"),
    ]

    operations = [
        migrations.RunPython(add_meals_module, remove_meals_module),
    ]
