"""
Journal App Signals

Post-save signal on JournalEntry:
  1. People extraction (relationship engine)
  2. Behavioral signal extraction (NLP via OpenAI)

Signal extraction uses Celery async as the primary path.
When Celery is unavailable (broker down, worker stopped), falls back to
synchronous extraction so signals are never silently lost.

Duplicate protection: JournalSignalExtractor.extract_signals() checks
`JournalSignal.objects.filter(entry=entry).exists()` before running.
If the sync fallback creates signals and Celery later processes the
queued task, the idempotency gate prevents duplicates.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='journal.JournalEntry')
def extract_people_from_journal(sender, instance, created, **kwargs):
    """
    Extract people mentions and behavioral signals from journal entries.

    Only runs on creation (not updates) to avoid re-processing.
    Only extracts signals — never stores raw journal content.
    """
    if not created:
        return

    # Gate: AI must be enabled and user must consent
    # (applies to BOTH people extraction and signal extraction)
    try:
        user = instance.user
        prefs = user.preferences
        if not getattr(prefs, 'ai_enabled', False):
            return
        if not getattr(prefs, 'personal_assistant_enabled', False):
            return
    except Exception as e:
        logger.warning("Journal signal gate check failed: %s", e)
        return

    # --- People extraction ---
    try:
        from apps.core.ai_relationships.models import Person
        if Person.objects.filter(user=user, is_active=True).exists():
            text_parts = []
            if instance.title:
                text_parts.append(instance.title)
            if instance.body:
                text_parts.append(instance.body)

            text = ' '.join(text_parts)
            if text.strip():
                from apps.core.ai_relationships.relationship_engine import extract_people_from_text
                extract_people_from_text(
                    user=user,
                    text=text,
                    source_type='journal',
                    source_id=str(instance.pk),
                )
    except Exception as e:
        logger.warning("Journal people extraction failed: %s", e)

    # --- Auto-complete matching RoutineSchedule items ---
    # When a journal entry is created, auto-complete today's journal-type routine items.
    try:
        from apps.life.services.routine_helpers import auto_complete_routine_schedules
        auto_complete_routine_schedules(
            user, 'journal', 'journal',
            completion_time=instance.created_at,
            source_object_id=instance.pk,
        )
    except Exception as e:
        logger.warning("Journal routine auto-complete failed: %s", e)

    # --- Behavioral signal extraction (async primary, sync fallback) ---
    _dispatch_signal_extraction(instance)

    # --- Deterministic emotion signal extraction (always synchronous) ---
    # Structured M2M selections → canonical signals, no LLM involved.
    # Runs separately from NLP extraction because it's instant and deterministic.
    try:
        from apps.journal.services.signal_extractor import extract_emotion_signals
        extract_emotion_signals(instance)
    except Exception as e:
        logger.warning("Emotion signal extraction failed for entry %s: %s", instance.pk, e)


def _dispatch_signal_extraction(entry):
    """
    Dispatch journal signal extraction: async via Celery, sync fallback.

    Primary path: Celery task (non-blocking, processed by worker).
    Fallback path: synchronous extraction (blocks post_save, but ensures
    signals are created when Celery is unavailable).

    Duplicate protection: JournalSignalExtractor.extract_signals() has an
    idempotency gate — if signals already exist for this entry, extraction
    is skipped. This prevents duplicates if Celery eventually processes a
    queued task after the sync fallback already ran.
    """
    # Try async dispatch first
    try:
        from apps.journal.tasks import extract_journal_signals
        extract_journal_signals.delay(entry.pk)
        return  # Async dispatch succeeded — done
    except ImportError:
        # Celery not installed (test environment) — fall through to sync
        logger.info(
            "Celery not available — using synchronous signal extraction "
            "for journal entry %s", entry.pk,
        )
    except Exception as e:
        # Broker connection failed, worker unavailable, etc.
        logger.warning(
            "Celery dispatch failed for journal entry %s: %s — "
            "falling back to synchronous extraction", entry.pk, e,
        )

    # Synchronous fallback — extract signals directly
    try:
        from apps.journal.services.signal_extractor import JournalSignalExtractor
        signals = JournalSignalExtractor.extract_signals(entry)
        if signals:
            logger.info(
                "Sync fallback extracted %d signals from journal entry %s",
                len(signals), entry.pk,
            )
    except Exception as e:
        logger.error(
            "Journal signal extraction failed (sync fallback) for entry %s: %s",
            entry.pk, e, exc_info=True,
        )
