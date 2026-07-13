"""Backfill faith reflection fields for the Rich Text Editor."""
from django.db import migrations

_MODELS = [
    ("PrayerRequest", [("description", "description_plain"),
                       ("answer_notes", "answer_notes_plain")]),
    ("FaithMilestone", [("description", "description_plain")]),
    ("BibleStudyNote", [("content", "content_plain")]),
]


def forwards(apps, schema_editor):
    from apps.core.rich_text import backfill_rich_text
    for name, pairs in _MODELS:
        backfill_rich_text(apps.get_model("faith", name), pairs)


def backwards(apps, schema_editor):
    from apps.core.rich_text import restore_plain_from_shadow
    for name, pairs in _MODELS:
        restore_plain_from_shadow(apps.get_model("faith", name), pairs)


class Migration(migrations.Migration):

    dependencies = [
        ("faith", "0022_biblestudynote_content_plain_and_more"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
