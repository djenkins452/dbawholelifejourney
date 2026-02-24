"""
Phase 9: Make idempotency_key NOT NULL and expand max_length to 128.

Step 1: Backfill any NULL rows with a deterministic SHA-256 hash.
Step 2: Alter field to NOT NULL, max_length=128.
"""

import hashlib

from django.db import migrations, models


def backfill_idempotency_keys(apps, schema_editor):
    """
    Compute deterministic idempotency keys for all rows where
    idempotency_key IS NULL.
    """
    CalendarEvent = apps.get_model('calendar_engine', 'CalendarEvent')
    db_alias = schema_editor.connection.alias

    null_rows = CalendarEvent.objects.using(db_alias).filter(
        idempotency_key__isnull=True,
    )
    updated = 0
    for event in null_rows.iterator():
        normalized_title = " ".join(event.title.strip().split()).lower()
        key = hashlib.sha256(
            f"{event.user_id}:{normalized_title}:{event.start_dt.isoformat()}".encode()
        ).hexdigest()
        event.idempotency_key = key
        event.save(update_fields=['idempotency_key'])
        updated += 1

    # Also backfill empty-string rows
    empty_rows = CalendarEvent.objects.using(db_alias).filter(
        idempotency_key='',
    )
    for event in empty_rows.iterator():
        normalized_title = " ".join(event.title.strip().split()).lower()
        key = hashlib.sha256(
            f"{event.user_id}:{normalized_title}:{event.start_dt.isoformat()}".encode()
        ).hexdigest()
        event.idempotency_key = key
        event.save(update_fields=['idempotency_key'])
        updated += 1

    if updated:
        print(f"\n  Backfilled {updated} idempotency key(s).")


class Migration(migrations.Migration):
    atomic = False  # RunPython + AlterField in separate transactions

    dependencies = [
        ('calendar_engine', '0003_phase9_idempotency_constraint_fix'),
    ]

    operations = [
        migrations.RunPython(
            backfill_idempotency_keys,
            migrations.RunPython.noop,
            elidable=True,
        ),
        migrations.AlterField(
            model_name='calendarevent',
            name='idempotency_key',
            field=models.CharField(
                db_index=True,
                help_text='SHA-256 hash for deterministic duplicate prevention',
                max_length=128,
            ),
        ),
    ]
