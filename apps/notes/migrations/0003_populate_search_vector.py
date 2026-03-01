# Data migration to backfill search_vector for all existing notes.

from django.db import migrations


def populate_search_vectors(apps, schema_editor):
    """Populate search_vector for all existing Note records."""
    from django.contrib.postgres.search import SearchVector

    Note = apps.get_model("notes", "Note")
    # Batch update all notes with search vectors from title and body
    Note.objects.update(
        search_vector=(
            SearchVector("title", weight="A")
            + SearchVector("body", weight="B")
        )
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("notes", "0002_note_search_vector_note_notes_search_vector_gin"),
    ]

    operations = [
        migrations.RunPython(populate_search_vectors, noop),
    ]
