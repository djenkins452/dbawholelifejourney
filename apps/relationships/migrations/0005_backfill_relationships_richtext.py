"""Backfill Person.notes and PersonGroup.description for the Rich Text Editor."""
from django.db import migrations


def forwards(apps, schema_editor):
    from apps.core.rich_text import backfill_rich_text

    backfill_rich_text(apps.get_model("relationships", "Person"),
                       [("notes", "notes_plain")])
    backfill_rich_text(apps.get_model("relationships", "PersonGroup"),
                       [("description", "description_plain")])


def backwards(apps, schema_editor):
    from apps.core.rich_text import restore_plain_from_shadow

    restore_plain_from_shadow(apps.get_model("relationships", "Person"),
                              [("notes", "notes_plain")])
    restore_plain_from_shadow(apps.get_model("relationships", "PersonGroup"),
                              [("description", "description_plain")])


class Migration(migrations.Migration):

    dependencies = [
        ("relationships", "0004_person_notes_plain_persongroup_description_plain"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
