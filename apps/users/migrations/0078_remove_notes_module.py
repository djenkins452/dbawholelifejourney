# ==============================================================================
# Data migration: Remove the 'notes' ModuleDefinition
#
# Migration 0069 created a 'notes' module, but it was never part of the
# canonical catalog (0077). Remove it so the DB matches the catalog.
# ==============================================================================

from django.db import migrations


def remove_notes_module(apps, schema_editor):
    ModuleDefinition = apps.get_model('users', 'ModuleDefinition')
    ModuleDefinition.objects.filter(slug='notes').delete()


def reverse_migration(apps, schema_editor):
    # Don't recreate on reverse — notes is not canonical
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0077_populate_module_catalog'),
    ]

    operations = [
        migrations.RunPython(remove_notes_module, reverse_migration),
    ]
