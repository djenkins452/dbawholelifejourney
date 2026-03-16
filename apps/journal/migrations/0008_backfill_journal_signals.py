"""
Data migration: queue backfill of journal signal extraction.

Journal entries created before the signal extraction pipeline was deployed (or
when extraction silently failed due to missing OpenAI client) have zero
JournalSignal records. This migration dispatches a Celery task to re-process
those entries.

Runs automatically on deploy via Procfile: python manage.py migrate --noinput.
"""

from django.db import migrations


def queue_backfill(apps, schema_editor):
    """Queue the backfill_journal_signals Celery task."""
    try:
        from apps.journal.tasks import backfill_journal_signals
        backfill_journal_signals.delay()
        print("\n  Queued journal signal backfill task via Celery")
    except ImportError:
        print("\n  Celery not available — skipping journal signal backfill (test environment)")
    except Exception as e:
        # Don't block migration if Celery broker is down
        print(f"\n  Could not queue journal signal backfill: {e}")
        print("  Run manually: from apps.journal.tasks import backfill_journal_signals; backfill_journal_signals()")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("journal", "0007_journalsignal"),
    ]

    operations = [
        migrations.RunPython(queue_backfill, noop),
    ]
