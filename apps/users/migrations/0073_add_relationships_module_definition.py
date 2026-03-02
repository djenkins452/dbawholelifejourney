# Data migration to add Relationships ModuleDefinition for navigation

from django.db import migrations


def add_relationships_module(apps, schema_editor):
    """Add Relationships module to ModuleDefinition so it appears in navigation."""
    ModuleDefinition = apps.get_model("users", "ModuleDefinition")

    ModuleDefinition.objects.get_or_create(
        slug="relationships",
        defaults={
            "name": "People",
            "description": "Track contacts, interaction history, and relational health insights",
            "icon_svg": (
                '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>'
                '<circle cx="9" cy="7" r="4"/>'
                '<path d="M23 21v-2a4 4 0 0 0-3-3.87"/>'
                '<path d="M16 3.13a4 4 0 0 1 0 7.75"/>'
            ),
            "route_name": "relationships:person_list",
            "default_order": 45,
            "is_active": True,
            "preference_field": "relationships_enabled",
        },
    )


def remove_relationships_module(apps, schema_editor):
    """Remove Relationships module definition."""
    ModuleDefinition = apps.get_model("users", "ModuleDefinition")
    ModuleDefinition.objects.filter(slug="relationships").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0072_backfill_meals_module_prefs"),
    ]

    operations = [
        migrations.RunPython(add_relationships_module, remove_relationships_module),
    ]
