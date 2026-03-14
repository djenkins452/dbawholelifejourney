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
