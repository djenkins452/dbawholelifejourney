"""Backfill LifeGoal narrative fields for the Rich Text Editor."""
from django.db import migrations

_PAIRS = [
    ("description", "description_plain"),
    ("why_it_matters", "why_it_matters_plain"),
    ("success_looks_like", "success_looks_like_plain"),
    ("motivation_note", "motivation_note_plain"),
    ("reflection", "reflection_plain"),
]


def forwards(apps, schema_editor):
    from apps.core.rich_text import backfill_rich_text
    backfill_rich_text(apps.get_model("purpose", "LifeGoal"), _PAIRS)


def backwards(apps, schema_editor):
    from apps.core.rich_text import restore_plain_from_shadow
    restore_plain_from_shadow(apps.get_model("purpose", "LifeGoal"), _PAIRS)


class Migration(migrations.Migration):

    dependencies = [
        ("purpose", "0020_lifegoal_description_plain_and_more"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
