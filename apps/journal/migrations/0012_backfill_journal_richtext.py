"""
Backfill existing JournalEntry content for the WLJ Rich Text Editor.

Existing `body` values are plain text. This migration:
  * converts each `body` to safe editor-compatible HTML (paragraphs / <br>), so
    it renders correctly in the editor and the `|safe` read views, and
  * populates the new `body_plain` shadow (search / preview / word count / export
    / narration) from the original text.

No content is lost: HTML is derived from the exact original text, and `body_plain`
is the original plain text. Reverse restores `body` to the plain shadow. Uses
bulk_update (no signals / no intelligence side effects on the request path).
"""
from django.db import migrations

BATCH = 500


def forwards(apps, schema_editor):
    from apps.core.rich_text import plaintext_to_html, rich_text_to_plaintext

    JournalEntry = apps.get_model("journal", "JournalEntry")
    qs = JournalEntry.objects.all().only("id", "body", "body_plain").iterator()

    batch = []
    for entry in qs:
        # Legacy `body` was plain text (rendered via |linebreaks, i.e. escaped),
        # so convert it losslessly to escaped-and-wrapped HTML and derive the
        # plain shadow the same way runtime saves do.
        entry.body = plaintext_to_html(entry.body or "")
        entry.body_plain = rich_text_to_plaintext(entry.body)
        batch.append(entry)
        if len(batch) >= BATCH:
            JournalEntry.objects.bulk_update(batch, ["body", "body_plain"])
            batch = []
    if batch:
        JournalEntry.objects.bulk_update(batch, ["body", "body_plain"])


def backwards(apps, schema_editor):
    """Restore `body` to the plain-text shadow (drop HTML markup)."""
    JournalEntry = apps.get_model("journal", "JournalEntry")
    batch = []
    for entry in JournalEntry.objects.all().only("id", "body", "body_plain").iterator():
        entry.body = entry.body_plain or ""
        batch.append(entry)
        if len(batch) >= BATCH:
            JournalEntry.objects.bulk_update(batch, ["body"])
            batch = []
    if batch:
        JournalEntry.objects.bulk_update(batch, ["body"])


class Migration(migrations.Migration):

    dependencies = [
        ("journal", "0011_journalentry_body_plain"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
