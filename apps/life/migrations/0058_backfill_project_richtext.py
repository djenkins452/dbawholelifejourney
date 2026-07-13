"""Backfill Project narrative fields (description / purpose / reflection) for the RTE."""
from django.db import migrations

_PAIRS = [
    ("description", "description_plain"),
    ("purpose", "purpose_plain"),
    ("reflection", "reflection_plain"),
]


def forwards(apps, schema_editor):
    from apps.core.rich_text import backfill_rich_text
    backfill_rich_text(apps.get_model("life", "Project"), _PAIRS)


def backwards(apps, schema_editor):
    from apps.core.rich_text import restore_plain_from_shadow
    restore_plain_from_shadow(apps.get_model("life", "Project"), _PAIRS)


class Migration(migrations.Migration):

    dependencies = [
        ("life", "0057_project_description_plain_project_purpose_plain_and_more"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
