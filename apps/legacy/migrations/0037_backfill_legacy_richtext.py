"""Backfill legacy narrative fields (bio / place & milestone description / relationship notes)."""
from django.db import migrations

_MODELS = [
    ("Person", [("bio", "bio_plain")]),
    ("Place", [("description", "description_plain")]),
    ("LifeMilestone", [("description", "description_plain")]),
    ("Relationship", [("notes", "notes_plain")]),
]


def forwards(apps, schema_editor):
    from apps.core.rich_text import backfill_rich_text
    for name, pairs in _MODELS:
        backfill_rich_text(apps.get_model("legacy", name), pairs)


def backwards(apps, schema_editor):
    from apps.core.rich_text import restore_plain_from_shadow
    for name, pairs in _MODELS:
        restore_plain_from_shadow(apps.get_model("legacy", name), pairs)


class Migration(migrations.Migration):

    dependencies = [
        ("legacy", "0036_lifemilestone_description_plain_person_bio_plain_and_more"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
