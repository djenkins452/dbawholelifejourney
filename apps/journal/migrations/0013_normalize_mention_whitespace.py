"""
Normalize recognized-person mention whitespace in existing journal entries.

The rich-text editor's mention command appended a trailing space after an inserted
chip; when the author's next character was punctuation, that space became a
typographic error in the finished journal ("Heather ." instead of "Heather.").
Runtime saves now normalize this in `sanitize_rich_html`; this migration applies the
same normalization to already-stored entries so old entries read correctly too, and
re-derives the plain-text shadow from the corrected HTML.

Presentation only — the mention identity (`data-person-id`) and the author's words
are untouched. Idempotent (a corrected entry is unchanged on a second run) and scoped
to entries that actually contain a mention chip. bulk_update: no signals / no
intelligence side effects. Reverse is a no-op (there is nothing to restore — a space
before punctuation was never intended content).
"""
from django.db import migrations

BATCH = 500


def forwards(apps, schema_editor):
    from apps.core.rich_text import normalize_mention_whitespace, rich_text_to_plaintext

    JournalEntry = apps.get_model("journal", "JournalEntry")
    qs = (JournalEntry.objects.filter(body__contains="data-mention")
          .only("id", "body", "body_plain").iterator())

    batch = []
    for entry in qs:
        new_body = normalize_mention_whitespace(entry.body or "")
        if new_body == (entry.body or ""):
            continue  # nothing to fix — keep it idempotent
        entry.body = new_body
        entry.body_plain = rich_text_to_plaintext(new_body)
        batch.append(entry)
        if len(batch) >= BATCH:
            JournalEntry.objects.bulk_update(batch, ["body", "body_plain"])
            batch = []
    if batch:
        JournalEntry.objects.bulk_update(batch, ["body", "body_plain"])


def backwards(apps, schema_editor):
    # No-op: the removed whitespace was an editor artifact, never authored content.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("journal", "0012_backfill_journal_richtext"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
