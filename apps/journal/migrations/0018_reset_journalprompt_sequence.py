# ==============================================================================
# File: apps/journal/migrations/0018_reset_journalprompt_sequence.py
# Description: Re-align the JournalPrompt id sequence with the rows that exist.
# ==============================================================================
"""`0003_load_journal_prompts` seeds prompts with EXPLICIT primary keys.

Assigning a pk directly does not advance the Postgres sequence, so `nextval` still
returns 1 while rows 1..N already exist. The next prompt created by anything other than
that migration collides:

    duplicate key value violates unique constraint "journal_journalprompt_pkey"
    DETAIL: Key (id)=(1) already exists.

Eight tests hit it. They were the symptom, not the problem — the same collision would
meet any code that creates a prompt, in production, on the first insert.

Django knows how to fix this: `sqlsequencereset` sets each sequence to
`max(pk)`. Idempotent, safe to re-run, and a no-op on backends without sequences
(SQLite), which is why the connection is asked rather than assumed.
"""
from django.db import migrations


def reset_sequence(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return
    JournalPrompt = apps.get_model("journal", "JournalPrompt")
    from django.core.management.color import no_style

    statements = connection.ops.sequence_reset_sql(no_style(), [JournalPrompt])
    with connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)


class Migration(migrations.Migration):

    dependencies = [
        ("journal", "0017_journalconversation_written_body"),
    ]

    operations = [
        migrations.RunPython(reset_sequence, migrations.RunPython.noop),
    ]
