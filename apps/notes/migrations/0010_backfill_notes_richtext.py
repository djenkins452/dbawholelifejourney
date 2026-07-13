"""
Backfill existing Note content for the WLJ Rich Text Editor.

Legacy `body` was plain text (rendered via |linebreaksbr). Convert it losslessly
to escaped-and-wrapped HTML and derive the `body_plain` shadow (search / preview /
word count) the same way runtime saves do. Also refreshes the Postgres
search_vector from the plain shadow so full-text search stops indexing markup.
Uses bulk_update (no signals) and a raw UPDATE for the tsvector.
"""
from django.db import migrations

BATCH = 500


def forwards(apps, schema_editor):
    from apps.core.rich_text import plaintext_to_html, rich_text_to_plaintext

    Note = apps.get_model("notes", "Note")
    batch = []
    for note in Note.objects.all().only("id", "body", "body_plain").iterator():
        note.body = plaintext_to_html(note.body or "")
        note.body_plain = rich_text_to_plaintext(note.body)
        batch.append(note)
        if len(batch) >= BATCH:
            Note.objects.bulk_update(batch, ["body", "body_plain"])
            batch = []
    if batch:
        Note.objects.bulk_update(batch, ["body", "body_plain"])

    # Rebuild search_vector from the plain shadow (Postgres only).
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as cur:
            cur.execute(
                """
                UPDATE notes_note SET search_vector =
                    setweight(to_tsvector('english', coalesce(title,'')), 'A') ||
                    setweight(to_tsvector('english', coalesce(body_plain,'')), 'B') ||
                    setweight(to_tsvector('english', coalesce(tags_text,'')), 'C') ||
                    setweight(to_tsvector('english', coalesce(attachments_text,'')), 'C')
                """
            )


def backwards(apps, schema_editor):
    Note = apps.get_model("notes", "Note")
    batch = []
    for note in Note.objects.all().only("id", "body", "body_plain").iterator():
        note.body = note.body_plain or ""
        batch.append(note)
        if len(batch) >= BATCH:
            Note.objects.bulk_update(batch, ["body"])
            batch = []
    if batch:
        Note.objects.bulk_update(batch, ["body"])


class Migration(migrations.Migration):

    dependencies = [
        ("notes", "0009_note_body_plain_alter_note_body"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
