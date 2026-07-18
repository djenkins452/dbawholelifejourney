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

    # --- People recognition ---
    # REPLACED (Phase 0d) by canonical @mention reconciliation — see
    # `reconcile_journal_person_mentions` below, which consumes ONLY the canonical
    # people resolver/lookup and writes canonical PersonMention truth. The legacy
    # ai_relationships extraction path is intentionally gone; Journal is a consumer of
    # the canonical Person system, never a legacy Person consumer.

    # --- Auto-complete matching RoutineSchedule items ---
    # Behavioral truth: the journal rhythm completes for the day the entry is
    # ABOUT (``entry_date``), not the day it was physically created. A user who
    # journals on June 14 about June 13 completes the June 13 Evening Journal
    # rhythm — June 14 stays open because they did not actually journal for
    # today. Anchoring to entry_date keeps adherence, streaks, rhythm
    # compliance, and CoS coaching truthful. Same-day entries (entry_date ==
    # created date) are unaffected. ``auto_complete_routine_schedules`` is
    # idempotent per (schedule, scheduled_date), so repeated saves can't
    # double-complete.
    try:
        from apps.life.services.routine_helpers import auto_complete_routine_schedules
        auto_complete_routine_schedules(
            user, 'journal', 'journal',
            completion_time=instance.created_at,
            source_object_id=instance.pk,
            target_date=instance.entry_date,
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


@receiver(post_save, sender='journal.JournalEntry')
def reconcile_journal_person_mentions(sender, instance, created, **kwargs):
    """Canonical Journal person recognition (Phase 0d). Runs on create AND update.

    TWO capabilities, ONE canonical authority (no second recognition system):
      * EXPLICIT @mentions — tokens the user selected in the editor.
      * PASSIVE recognition — a natural reference ("dinner with Heather") that
        deterministically resolves to exactly one canonical Person is wrapped into the
        SAME token, so it renders identically. Ambiguous names stay plain text (never
        guess). Every identity decision is delegated to the ONE resolver.

    Deterministic + request-path-safe (no LLM). Never breaks a save."""
    try:
        from apps.people.services.mentions import (
            normalize_mention_case, recognize_prose_mentions, reconcile_object_mentions,
        )
        # Recognition + presentation run once, then the body is re-saved so the canonical
        # token is stored and the plain shadow regenerated. The re-save re-fires this
        # signal with the guard set, which skips this block and falls through to reconcile
        # — so reconcile runs exactly once, on the final body.
        if not getattr(instance, "_prose_recognized", False):
            original = instance.body or ""
            recognized, passive_src = recognize_prose_mentions(instance.user, original)
            # Normalize every chip's capitalization to the canonical Person (passive AND
            # explicit), preserving the author's wording — "heather" → "Heather", never
            # "Heather Jenkins".
            final_body = normalize_mention_case(instance.user, recognized)
            if final_body != original:
                instance._prose_recognized = True
                instance._passive_sources = passive_src   # survives to the reconcile pass
                instance.body = final_body
                instance.save(update_fields=["body", "body_plain", "updated_at"])
                return
        reconcile_object_mentions(
            instance, instance.body or "", instance.user,
            source_overrides=getattr(instance, "_passive_sources", None),
        )
    except Exception as e:  # pragma: no cover - defensive; recognition never blocks save
        logger.warning("Journal canonical mention reconcile failed for %s: %s",
                       getattr(instance, "pk", "?"), e)


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
    # Fire-and-forget, non-blocking. Signal extraction can call OpenAI, so it
    # must NEVER run synchronously on the journal-save request path — not even
    # when the broker is down. safe_enqueue runs it inline under EAGER (tests)
    # and async in prod; the extractor's idempotency gate means a later worker
    # (or the next successful enqueue) extracts without duplication. A brief
    # delay in behavioral signals is acceptable; a blocked save is not.
    from apps.core.celery_utils import safe_enqueue
    from apps.journal.tasks import extract_journal_signals
    safe_enqueue(extract_journal_signals, entry.pk)
