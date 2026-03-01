# Data migration to add Notes ModuleDefinition for navigation

from django.db import migrations


def add_notes_module(apps, schema_editor):
    """Add Notes module to ModuleDefinition so it appears in navigation."""
    ModuleDefinition = apps.get_model("users", "ModuleDefinition")

    ModuleDefinition.objects.get_or_create(
        slug="notes",
        defaults={
            "name": "Notes",
            "description": "Capture and organize thoughts, ideas, and reference notes",
            "icon_svg": (
                '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
                '<polyline points="14 2 14 8 20 8"/>'
                '<line x1="16" y1="13" x2="8" y2="13"/>'
                '<line x1="16" y1="17" x2="8" y2="17"/>'
                '<polyline points="10 9 9 9 8 9"/>'
            ),
            "route_name": "notes:note_list",
            "default_order": 60,
            "is_active": True,
            "preference_field": "",
        },
    )


def remove_notes_module(apps, schema_editor):
    """Remove Notes module definition."""
    ModuleDefinition = apps.get_model("users", "ModuleDefinition")
    ModuleDefinition.objects.filter(slug="notes").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0068_add_cos_v2_enabled"),
    ]

    operations = [
        migrations.RunPython(add_notes_module, remove_notes_module),
    ]
