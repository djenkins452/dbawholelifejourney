"""
Whole Life Journey - Relationship Intelligence Services

Project: Whole Life Journey
Path: apps/relationships/services.py
Purpose: Analytics, mention parsing, and interaction recording services

Description:
    Platform services for relational intelligence:
    - RelationshipAnalyticsService: Interaction metrics and summaries
    - MentionParserService: @mention detection and record creation

Public API:
    - RelationshipAnalyticsService.record_interaction(person, user, context_type, source_obj)
    - RelationshipAnalyticsService.get_summary(person)
    - RelationshipAnalyticsService.last_interaction(person)
    - RelationshipAnalyticsService.interaction_count(person, timeframe=None)
    - RelationshipAnalyticsService.days_since_last_interaction(person)
    - RelationshipAnalyticsService.context_breakdown(person)
    - RelationshipAnalyticsService.top_interacted(user, limit=10)
    - MentionParserService.parse_and_link(user, text, source_obj)

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import datetime
import logging
import re

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Q
from django.utils import timezone

logger = logging.getLogger(__name__)


# =============================================================================
# RELATIONSHIP ANALYTICS SERVICE
# =============================================================================


class RelationshipAnalyticsService:
    """Interaction metrics and structured summaries for Person records."""

    @staticmethod
    def record_interaction(person, user, context_type_label, source_obj=None):
        """
        Record an interaction with a person.

        Creates a RelationshipInteraction and updates denormalized counters
        on the Person record.

        Args:
            person: Person instance
            user: User instance
            context_type_label: str — one of CONTEXT_TYPE_CHOICES values
            source_obj: Optional Django model instance (GenericFK target)

        Returns:
            RelationshipInteraction instance
        """
        from .models import RelationshipInteraction

        today = timezone.localdate()
        kwargs = {
            'person': person,
            'user': user,
            'context_type_label': context_type_label,
            'interaction_date': today,
        }

        if source_obj is not None:
            ct = ContentType.objects.get_for_model(source_obj)
            # Deduplicate: don't record same person + same source object twice
            existing = RelationshipInteraction.objects.filter(
                person=person,
                user=user,
                content_type=ct,
                object_id=source_obj.pk,
            ).exists()
            if existing:
                return None

            kwargs['content_type'] = ct
            kwargs['object_id'] = source_obj.pk

        interaction = RelationshipInteraction.objects.create(**kwargs)

        # Update denormalized counters on Person
        person.last_interaction_date = today
        person.interaction_count = RelationshipInteraction.objects.filter(
            person=person,
        ).count()
        person.save(update_fields=['last_interaction_date', 'interaction_count', 'updated_at'])

        # Also update legacy ai_relationships if it exists
        try:
            from apps.core.ai_relationships.models import Relationship
            Relationship.objects.filter(
                user=user,
                person__display_name=person.display_name,
            ).update(last_interaction=today)
        except Exception:
            pass  # Legacy model may not exist

        return interaction

    @staticmethod
    def last_interaction(person):
        """Return the date of the most recent interaction, or None."""
        return person.last_interaction_date

    @staticmethod
    def interaction_count(person, timeframe=None):
        """
        Count interactions with a person.

        Args:
            person: Person instance
            timeframe: Optional timedelta to limit window

        Returns:
            int
        """
        from .models import RelationshipInteraction

        qs = RelationshipInteraction.objects.filter(person=person)
        if timeframe:
            cutoff = timezone.localdate() - timeframe
            qs = qs.filter(interaction_date__gte=cutoff)
        return qs.count()

    @staticmethod
    def days_since_last_interaction(person):
        """Return days since last interaction, or None if never."""
        if not person.last_interaction_date:
            return None
        return (timezone.localdate() - person.last_interaction_date).days

    @staticmethod
    def context_breakdown(person):
        """
        Break down interactions by context type.

        Returns:
            dict of context_type_label → count
        """
        from .models import RelationshipInteraction

        counts = (
            RelationshipInteraction.objects
            .filter(person=person)
            .values('context_type_label')
            .annotate(count=Count('id'))
        )
        return {row['context_type_label']: row['count'] for row in counts}

    @staticmethod
    def get_summary(person):
        """
        Return a structured interaction summary for a person.

        Returns:
            dict with total_interactions, last_interaction_date,
            and per-context counts
        """
        breakdown = RelationshipAnalyticsService.context_breakdown(person)
        return {
            'total_interactions': person.interaction_count,
            'last_interaction_date': person.last_interaction_date,
            'journal_mentions': breakdown.get('journal', 0),
            'task_mentions': breakdown.get('task', 0),
            'meal_associations': breakdown.get('meal', 0),
            'prayer_mentions': breakdown.get('prayer', 0),
            'event_invitations': breakdown.get('event', 0),
        }

    @staticmethod
    def top_interacted(user, limit=10):
        """
        Return the top N most-interacted-with people for a user.

        Returns:
            QuerySet of Person instances ordered by interaction_count desc
        """
        from .models import Person

        return (
            Person.objects
            .filter(owner=user)
            .order_by('-interaction_count', '-last_interaction_date')
            [:limit]
        )


# =============================================================================
# MENTION PARSER SERVICE
# =============================================================================


class MentionParserService:
    """
    Detects @Name patterns in text and creates Mention + Interaction records.

    Matching strategy:
    1. Exact match on display_name (case-insensitive)
    2. Exact match on first_name (case-insensitive)
    3. Fuzzy prefix match on first_name (for partial names)
    """

    # Pattern: @ followed by one or two capitalized words, or quoted name
    # e.g., @John, @John Smith, @"John Smith Jr"
    MENTION_PATTERN = re.compile(
        r'@"([^"]+)"|@([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
    )

    @classmethod
    def parse_and_link(cls, user, text, source_obj, context_type_label=None):
        """
        Parse text for @mentions and create Mention + Interaction records.

        Also detects bare name references (without @) for known contacts.

        Args:
            user: User instance
            text: Text to scan
            source_obj: Django model instance being saved
            context_type_label: Override context type (auto-detected if None)

        Returns:
            list of created Mention instances
        """
        from .models import Mention, Person

        if not text or not text.strip():
            return []

        people = Person.objects.filter(owner=user)
        if not people.exists():
            return []

        ct = ContentType.objects.get_for_model(source_obj)

        if context_type_label is None:
            context_type_label = cls._detect_context_type(source_obj)

        mentions_created = []
        text_lower = text.lower()
        matched_person_ids = set()

        # Phase 1: @mention pattern matching
        for match in cls.MENTION_PATTERN.finditer(text):
            name = match.group(1) or match.group(2)
            person = cls._find_person(people, name)
            if person and person.pk not in matched_person_ids:
                matched_person_ids.add(person.pk)
                mention = cls._create_mention(person, ct, source_obj.pk)
                if mention:
                    mentions_created.append(mention)
                    RelationshipAnalyticsService.record_interaction(
                        person=person,
                        user=user,
                        context_type_label=context_type_label,
                        source_obj=source_obj,
                    )

        # Phase 2: Bare name matching (without @) against known contacts
        for person in people:
            if person.pk in matched_person_ids:
                continue
            # Match display_name or first_name with word boundaries
            names_to_check = [person.display_name.lower()]
            if person.first_name:
                names_to_check.append(person.first_name.lower())

            for name in names_to_check:
                if len(name) < 2:
                    continue
                pattern = r'\b' + re.escape(name) + r'\b'
                if re.search(pattern, text_lower):
                    matched_person_ids.add(person.pk)
                    mention = cls._create_mention(person, ct, source_obj.pk)
                    if mention:
                        mentions_created.append(mention)
                        RelationshipAnalyticsService.record_interaction(
                            person=person,
                            user=user,
                            context_type_label=context_type_label,
                            source_obj=source_obj,
                        )
                    break

        if mentions_created:
            logger.info(
                "MentionParser: %d mentions created for %s in %s #%s",
                len(mentions_created),
                user.email,
                ct.model,
                source_obj.pk,
            )

        return mentions_created

    @classmethod
    def _find_person(cls, people_qs, name):
        """Find a person by name (case-insensitive)."""
        name_lower = name.strip().lower()

        # Exact display_name match
        for person in people_qs:
            if person.display_name.lower() == name_lower:
                return person

        # Exact first_name match
        for person in people_qs:
            if person.first_name.lower() == name_lower:
                return person

        # First name prefix match (fuzzy)
        for person in people_qs:
            if person.first_name.lower().startswith(name_lower) and len(name_lower) >= 3:
                return person

        return None

    @classmethod
    def _create_mention(cls, person, content_type, object_id):
        """Create a Mention record, deduplicating."""
        from .models import Mention

        mention, created = Mention.objects.get_or_create(
            person=person,
            content_type=content_type,
            object_id=object_id,
        )
        return mention if created else None

    @classmethod
    def _detect_context_type(cls, source_obj):
        """Auto-detect context type from the source object's model."""
        model_name = source_obj.__class__.__name__.lower()
        mapping = {
            'journalentry': 'journal',
            'task': 'task',
            'mealplan': 'meal',
            'prayerrequest': 'prayer',
            'lifeevent': 'event',
        }
        return mapping.get(model_name, 'other')
