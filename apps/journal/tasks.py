# ==============================================================================
# File: apps/journal/tasks.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Celery tasks for journal signal extraction
# Created: 2026-03-14 (Architecture Evolution Phase 7)
# ==============================================================================
"""
Journal Celery Tasks — Signal Extraction

Async task that extracts behavioral signals from journal entries via OpenAI.
Triggered by post_save signal on JournalEntry.

Also provides a backfill task to re-extract signals for entries created before
the extraction pipeline was deployed or when extraction silently failed.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='journal.extract_journal_signals')
def extract_journal_signals(entry_id):
    """
    Async task: extract behavioral signals from a single journal entry.

    Called by post_save signal on JournalEntry. Handles:
    - Short entries (<20 words) — skipped
    - Entries with existing signals — skipped (idempotency)
    - OpenAI failures — logged, not raised
    """
    from apps.journal.models import JournalEntry

    try:
        entry = JournalEntry.objects.get(pk=entry_id)
    except JournalEntry.DoesNotExist:
        logger.warning("Journal entry %s not found for signal extraction", entry_id)
        return {'status': 'not_found', 'entry_id': entry_id}

    from apps.journal.services.signal_extractor import JournalSignalExtractor

    try:
        signals = JournalSignalExtractor.extract_signals(entry)
        return {
            'status': 'ok',
            'entry_id': entry_id,
            'signals_extracted': len(signals),
        }
    except Exception as e:
        logger.error(
            "Signal extraction failed for entry %s: %s",
            entry_id, e, exc_info=True,
        )
        return {
            'status': 'error',
            'entry_id': entry_id,
            'error': str(e),
        }


@shared_task(name='journal.backfill_journal_signals')
def backfill_journal_signals():
    """
    Backfill task: find journal entries with no extracted signals and
    re-queue them for extraction.

    Runs once on deploy via data migration 0005. Entries that already have
    signals are skipped by the idempotency gate in JournalSignalExtractor.
    """
    from apps.journal.models import JournalEntry, JournalSignal

    # Find entries that have zero JournalSignal records
    entries_without_signals = (
        JournalEntry.objects.exclude(
            pk__in=JournalSignal.objects.values_list("entry_id", flat=True)
        )
        .order_by("created_at")
    )

    count = entries_without_signals.count()
    if count == 0:
        logger.info("Journal signal backfill: no entries without signals found")
        return {'status': 'ok', 'entries_queued': 0}

    logger.info(
        "Journal signal backfill: found %d entries without signals — queueing extraction",
        count,
    )

    queued = 0
    for entry in entries_without_signals:
        try:
            extract_journal_signals.delay(entry.pk)
            queued += 1
        except Exception as e:
            # If Celery is down, fall back to sync extraction
            logger.warning(
                "Backfill: Celery dispatch failed for entry %s, extracting synchronously: %s",
                entry.pk, e,
            )
            try:
                from apps.journal.services.signal_extractor import JournalSignalExtractor
                JournalSignalExtractor.extract_signals(entry)
                queued += 1
            except Exception as sync_err:
                logger.error(
                    "Backfill: sync extraction failed for entry %s: %s",
                    entry.pk, sync_err, exc_info=True,
                )

    logger.info("Journal signal backfill: queued %d/%d entries for extraction", queued, count)
    return {'status': 'ok', 'entries_queued': queued, 'total_without_signals': count}
