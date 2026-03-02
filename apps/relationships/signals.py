"""
Whole Life Journey - Relationships Signals

Project: Whole Life Journey
Path: apps/relationships/signals.py
Purpose: Post-save signal handlers for @mention extraction across modules

Description:
    Listens for post_save on Journal, Task, Prayer, MealPlan, and LifeEvent.
    Extracts mentions via MentionParserService and records interactions.

    Only runs when:
    - User has AI enabled and personal assistant enabled
    - User has contacts to match against

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _extract_mentions_from_instance(instance, text_fields, context_type):
    """
    Shared mention extraction logic for any model instance.

    Args:
        instance: Model instance (must have .user attribute)
        text_fields: List of field names to scan for mentions
        context_type: Context type label for the interaction
    """
    try:
        user = instance.user
        prefs = user.preferences

        # Gate: AI must be enabled
        if not getattr(prefs, 'ai_enabled', False):
            return
        if not getattr(prefs, 'personal_assistant_enabled', False):
            return

        # Gate: Must have contacts
        from apps.relationships.models import Person
        if not Person.objects.filter(owner=user).exists():
            return

        # Collect text from specified fields
        text_parts = []
        for field in text_fields:
            value = getattr(instance, field, None)
            if value:
                text_parts.append(str(value))

        text = ' '.join(text_parts)
        if not text.strip():
            return

        from apps.relationships.services import MentionParserService
        MentionParserService.parse_and_link(
            user=user,
            text=text,
            source_obj=instance,
            context_type_label=context_type,
        )
    except Exception as e:
        logger.warning(
            "Mention extraction failed for %s #%s: %s",
            instance.__class__.__name__,
            getattr(instance, 'pk', '?'),
            e,
        )


@receiver(post_save, sender='journal.JournalEntry')
def extract_mentions_from_journal(sender, instance, created, **kwargs):
    """Extract mentions from journal entries on creation."""
    if not created:
        return
    _extract_mentions_from_instance(instance, ['title', 'body'], 'journal')


@receiver(post_save, sender='life.Task')
def extract_mentions_from_task(sender, instance, created, **kwargs):
    """Extract mentions from tasks on creation."""
    if not created:
        return
    _extract_mentions_from_instance(instance, ['title', 'notes'], 'task')


@receiver(post_save, sender='faith.PrayerRequest')
def extract_mentions_from_prayer(sender, instance, created, **kwargs):
    """Extract mentions from prayer requests on creation."""
    if not created:
        return
    _extract_mentions_from_instance(
        instance, ['title', 'description', 'answer_notes'], 'prayer',
    )


@receiver(post_save, sender='meals.MealPlan')
def extract_mentions_from_mealplan(sender, instance, created, **kwargs):
    """Extract mentions from meal plan notes on creation."""
    if not created:
        return
    _extract_mentions_from_instance(instance, ['notes'], 'meal')


@receiver(post_save, sender='life.LifeEvent')
def extract_mentions_from_event(sender, instance, created, **kwargs):
    """Extract mentions from life events on creation."""
    if not created:
        return
    _extract_mentions_from_instance(
        instance, ['title', 'description'], 'event',
    )
