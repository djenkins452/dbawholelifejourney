"""
Journal App Signals

Post-save signal on JournalEntry for people extraction.
Only extracts when AI is enabled and user has AI consent.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='journal.JournalEntry')
def extract_people_from_journal(sender, instance, created, **kwargs):
    """
    Extract people mentions from journal entries.

    Only runs on creation (not updates) to avoid re-processing.
    Only extracts signals — never stores raw journal content.
    """
    if not created:
        return

    try:
        user = instance.user
        prefs = user.preferences

        # Gate: AI must be enabled and user must consent
        if not getattr(prefs, 'ai_enabled', False):
            return
        if not getattr(prefs, 'personal_assistant_enabled', False):
            return

        # Gate: Must have known people to match against
        from apps.core.ai_relationships.models import Person
        if not Person.objects.filter(user=user, is_active=True).exists():
            return

        # Extract from title + body
        text_parts = []
        if instance.title:
            text_parts.append(instance.title)
        if instance.body:
            text_parts.append(instance.body)

        text = ' '.join(text_parts)
        if not text.strip():
            return

        from apps.core.ai_relationships.relationship_engine import extract_people_from_text
        extract_people_from_text(
            user=user,
            text=text,
            source_type='journal',
            source_id=str(instance.pk),
        )
    except Exception as e:
        logger.debug("Journal people extraction skipped: %s", e)

    # Architecture Evolution Phase 7: Trigger async signal extraction
    try:
        from apps.journal.tasks import extract_journal_signals
        extract_journal_signals.delay(instance.pk)
    except ImportError:
        pass  # Celery not available in test
    except Exception as e:
        logger.debug("Journal signal extraction dispatch skipped: %s", e)
