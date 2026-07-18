"""
Normalize recognized-person mention capitalization in existing journal entries.

Passive recognition preserved the author's wording verbatim, including non-canonical
capitalization ("dinner with heather" stayed "heather"). Runtime saves now normalize a
chip's case to the canonical Person via `normalize_mention_case`; this migration applies
the same normalization to already-stored entries so old entries read correctly too, and
re-derives the plain-text shadow from the corrected HTML.

Presentation only — the mention identity (`data-person-id`) and the author's words are
untouched; only capitalization changes, and a first name is never expanded to a full
name. Idempotent (a corrected chip is unchanged on a second run) and scoped to entries
that contain a chip. Per-entry guard so one odd row can never block a deploy. Reverse is
a no-op (there is no "previous" canonical case to restore). Depends on the people app so
the canonical Person table is present; atomic=False for the cross-app reads.
"""
from django.db import migrations

BATCH = 500


def forwards(apps, schema_editor):
    from apps.core.rich_text import rich_text_to_plaintext
    from apps.people.services.mentions import normalize_mention_case

    JournalEntry = apps.get_model("journal", "JournalEntry")
    qs = (JournalEntry.objects.filter(body__contains="data-mention")
          .select_related("user").iterator())

    batch = []
    for entry in qs:
        try:
            new_body = normalize_mention_case(entry.user, entry.body or "")
        except Exception:
            continue  # never let one row block the deploy
        if new_body == (entry.body or ""):
            continue  # idempotent — nothing to fix
        entry.body = new_body
        entry.body_plain = rich_text_to_plaintext(new_body)
        batch.append(entry)
        if len(batch) >= BATCH:
            JournalEntry.objects.bulk_update(batch, ["body", "body_plain"])
            batch = []
    if batch:
        JournalEntry.objects.bulk_update(batch, ["body", "body_plain"])


def backwards(apps, schema_editor):
    # No-op: the original non-canonical capitalization was never intended content.
    pass


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ("journal", "0013_normalize_mention_whitespace"),
        ("people", "0004_personmention_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
