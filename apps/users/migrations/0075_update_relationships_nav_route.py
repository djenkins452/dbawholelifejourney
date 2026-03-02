# Data migration to change Relationships module nav route from person_list to insights

from django.db import migrations


def update_route(apps, schema_editor):
    """Change Relationships module route to insights page."""
    ModuleDefinition = apps.get_model("users", "ModuleDefinition")
    ModuleDefinition.objects.filter(slug="relationships").update(
        route_name="relationships:insights"
    )


def revert_route(apps, schema_editor):
    """Revert Relationships module route to person_list."""
    ModuleDefinition = apps.get_model("users", "ModuleDefinition")
    ModuleDefinition.objects.filter(slug="relationships").update(
        route_name="relationships:person_list"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0074_relationships_enabled_default_true"),
    ]

    operations = [
        migrations.RunPython(update_route, revert_route),
    ]
